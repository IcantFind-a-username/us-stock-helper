# Dual-Entry Filing Re-announcement Fix Plan (awaiting Franz's approval)

> **Status: PROPOSAL — do not implement until Franz approves the direction.**
> Drafted 2026-08-17 during the authoritative-source-adapters round, where the
> defect was discovered and empirically confirmed (ledger:
> `.superpowers/sdd/2026-08-17-authoritative-source-adapters/progress.md`).
> This is a pre-existing defect: it affects Form 4 in production today and
> was not introduced by the 13D/13G work — that work only doubled its reach.

**Goal:** Stop the coordinator from re-publishing every multi-party SEC filing
as an endless chain of fake "revisions" on every poll, without breaking the
two things the shared claim key currently buys: one filing clusters as one
story, and the attributed party's entry wins as the cluster's representative.

## The defect, with reproduction evidence

EDGAR's getcurrent feed emits **one entry per party** of a filing. A Form 4
pairs `(Reporting)` with `(Issuer)`; a Schedule 13D/13G pairs `(Filed by)`
with `(Subject)`. Both entries share the accession number and even the same
Atom `<id>` (`urn:tag:sec.gov,2008:accession-number=…`), so
`SecCurrentFilingsAdapter._claim_key` gives both the same claim key
`sec|{accession}` — but their titles differ, so their content hashes differ.

`PollingCoordinator.poll`'s commit loop keeps **one** `_PublishedRecord` per
claim key. Within one batch the pair therefore collides:

1. Poll 1: entry A (Filed by) publishes; entry B (Subject) sees A's record,
   hash differs → published as *revision 2 of A*. Record now holds B's hash.
2. Poll 2, unchanged feed: A's hash ≠ stored (B's) → published as revision 3;
   B's hash ≠ stored (now A's) → published as revision 4. And so on, forever,
   while the filing stays inside the lookback window.

Empirical confirmation (2026-08-17, against the captured fixture
`sec_current_schedule_13d.atom`, 40 entries = 20 filings × 2 parties):
two coordinator polls of the identical body published **40 events both
times**, the second poll's revision numbers reading 2, 3, 2, 3, …

Two harms, in severity order:

- **PIT/freshness dishonesty.** Each re-publication is a "new" event whose
  `available_at` is the latest poll's `retrieved_at`. `EvidenceCollector`
  upserts by `event_id` (which is stable — it hashes claim key + title/summary
  preview), so the stored copy's `available_at` keeps moving forward: the
  filing always reads as just-arrived, `freshness_seconds` ≈ 0, and the
  `stale` marker can never fire for these events. Decision ordering
  (`evidence()` sorts by `available_at`) always ranks them newest.
- **Unbounded fake revision chains.** `revision_number` grows without bound
  and `revision_of` alternates between the two party entries, neither of
  which is a revision of the other.

Note what is *not* harmed: the collector's `event_id` upsert prevents
unbounded memory growth, and coordinator snapshot persistence (`4ef2226`)
correctly suppresses cross-restart replay for single-entry sources — but for
paired entries the ping-pong resumes immediately after every restart too,
because the snapshot stores only the last-written hash of the pair.

## Why the shared claim key is load-bearing (do not "just" split it)

`information_layer/clustering.py` unions events into clusters by exact
`claim_key` (and `content_hash`, and `revision_of` lineage). The shared key
is what makes the two party entries of one filing **one cluster**:

- `_summarize_cluster` computes `superseded = {revision_of…}` and drops
  superseded events from the *active* set. Because the Subject/Issuer entry
  is published as a "revision" of the Filed-by/Reporting entry, the
  metadata-only party entry is superseded and the **attributed** entry
  becomes the cluster's representative — accidentally correct behavior that
  a naive key split would destroy.
- One filing = one cluster also keeps `independent_source_count` honest
  (both entries are the same publisher saying the same thing once).

Splitting the claim key with no clustering compensation would leave two
separate single-event clusters per filing: double-counted stories in any
cluster-level view, and the metadata-only party entry no longer suppressed.

## Candidate fixes and their risks

### A. Per-party claim keys + accession-based cluster union (recommended)

Change `SecCurrentFilingsAdapter._claim_key` to
`sec|{accession}|{party-cik-or-role}`, and teach `_group_related`
(clustering) one more exact-key union: events sharing an `accession`
attribute join the same cluster (a third owners-map next to the existing
`claim_owner`/`hash_owner`, reading the attribute the adapter already
emits).

- Fixes: ping-pong ends (each party entry dedupes against itself);
  `available_at` stops being refreshed; genuine per-party revisions (EDGAR
  re-lists an entry with changed content under the same accession) still
  publish as real revisions of the right parent.
- Preserves: one filing = one cluster (via accession union).
- **Changed behavior to re-pin (verified 2026-08-17, not a hedge):** the
  Subject entry is no longer marked `revision_of` the Filed-by entry, so
  `_summarize_cluster`'s superseded logic no longer demotes the
  metadata-only party. `_representative_sort_key` was read and it does
  **not** prefer symbol-attributed events — it ranks by claim status,
  revision number, reliability, confidence, timestamp, then event_id; the
  party entries tie on all of these and the winner today would be decided
  by event-id string order, i.e. arbitrarily. The function therefore
  **must** grow a "carries symbol attribution" rank ahead of the tiebreaks,
  with its own before/after pin, since it orders every cluster in the
  system. This is the one genuinely new scoring-adjacent decision in this
  plan.
- Risks: coordinator snapshots written before the change hold old-format
  claim keys; after deploy, the first poll re-announces each in-window
  filing once under its new key (a bounded, one-time replay — disclose in
  the ledger). Amendments (13D/A) have their *own* accession, so they
  remain separate claims/clusters, unchanged from today.

### B. Multi-hash published records in the coordinator

Keep the shared claim key; let `_PublishedRecord` hold a *set* of content
hashes so the pair coexists under one key.

- Fixes the ping-pong, but cannot tell "two simultaneous party entries"
  from "a genuine revision over time" — both are "same claim, new hash".
  Revisions would need heuristics (timestamps? title similarity?), which is
  exactly the kind of guessing this codebase refuses. Also a coordinator
  semantics change felt by **every** feed, not just SEC.
- Not recommended.

### C. Suppress the non-attributing party entry at the adapter

Emit only the Subject/Issuer entry; drop Filed-by/Reporting.

- Fixes the ping-pong trivially, but loses traceability that today's tests
  pin (`InsiderFilingAttributionTests` asserts the reporting entry exists,
  carrying its `cik`/`filer_role` attributes), silently changes
  market-brief-level event counts, and discards the only record naming the
  *holder* — which matters precisely for 13D (who is accumulating).
- Not recommended.

## Recommended minimal path

Option A, in one small task each:

- [ ] **Task 1 (RED first):** Pin today's wrong behavior as a failing test:
  coordinator polls the captured `sec_current_schedule_13d.atom` twice →
  the second poll must publish nothing (fails today with 40 re-publications);
  and the stored events' `available_at` must not move between polls.
- [ ] **Task 2:** Per-party claim key in `sec.py` (accession + the entry's
  own CIK; fall back to the role string when no CIK parses; fall back to
  today's key when neither exists). Re-run the Task 1 test to green.
- [ ] **Task 3 (RED first):** Clustering: pin that the two party entries of
  one filing still form **one** cluster whose representative is the
  symbol-attributed entry; then add the accession-union pass to
  `_group_related` **and** the "carries symbol attribution" rank to
  `_representative_sort_key` (verified necessary — see above; the party
  entries otherwise tie down to an arbitrary event-id tiebreak), each with
  its own before/after pin.
- [ ] **Task 4:** Mutation checks (revert the key split → Task 1 red; drop
  the accession union → Task 3 red), full suites
  (`information_layer`, `analysis_api`, `decision_engine`, `scripts`),
  a live double-restart check against the running stack, ledger entry, and
  one commit `fix: stop republishing multi-party filings as fake revisions`.

**Out of scope (stays as-is):** evidence-event persistence across restarts
(separate open question #6 in the ledger), and any change to how a single
party entry's genuine revision is versioned.

## Test strategy

- Fixture-driven, against the captured EDGAR payloads already in
  `services/information_layer/tests/fixtures/` — no synthetic feed shapes.
- Every key assertion mutation-verified (reverse the fix, watch red).
- Cluster-level pins: cluster count per filing, representative identity,
  `independent_source_count`, and the freshness/staleness honesty of stored
  events across repeated polls.
- A before/after pin on coordinator snapshot compatibility: an old-format
  snapshot must load (keys are opaque strings) and cause at most one bounded
  re-announcement per in-window filing, never a crash.
