# Authoritative Source Adapters Implementation Plan (R1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Before Task 1, read** `docs/handoffs/2026-08-17-agent-handoff.md` §零 (the three disciplines: simulator-driven development, TDD, SDD) and §七 (the recurring traps). Keep the iOS simulator panel open for the whole session.

**Goal:** Widen the evidence intake so real-mode analysis stops being uniformly blocked. Today every watchlist symbol shows `不可行动 · 证据不足` because the only live evidence sources are SEC 8-K + Form 4 current feeds, three macro press feeds, and exactly two company newsrooms (Apple, NVIDIA). The scoring gate is not too strict — the system has too few eyes.

**Architecture:** The feed layer is already declarative and does not need new dispatch code. `SourceSpec` entries in `feeds/registry.py::PUBLIC_SOURCES` describe every source; `build_adapters` maps each spec through `_adapter_for`, which routes a spec carrying `sec_form_type` to `SecCurrentFilingsAdapter` and everything else to a plain `GenericFeedAdapter`. Adding coverage is therefore mostly *registering specs and proving their parsing against real captured payloads*, not writing new adapters. The one genuinely new mechanism in this plan is coordinator snapshot persistence (Task 4) — the mechanism exists and is tested, but production wiring never uses it.

**Tech Stack:** Python 3.12 stdlib only in `information_layer` (no third-party HTTP), `unittest`, the existing `UrllibHttpsTransport` (HTTPS-only, host allowlist, credential-free, redirect re-validation), Expo/RN + Jest on the mobile side.

## Global Constraints

- **Red lines unchanged.** In particular: unavailable stays visibly unavailable with a *named* reason; "没读到" must never be scored as "读了是中性"; PIT (`available_at`) violations fail loudly; no data source may carry credentials (the transport rejects `Authorization`/`Cookie` headers by construction).
- **No unlicensed news wire.** `SourceKind.NEWS_WIRE` stays unused. Reuters/Bloomberg-class feeds require a commercial licence; scraping them is out of scope regardless of technical feasibility. Do not add a source to work around this.
- **Politeness is a contract, not a formality.** Every EDGAR source requires `requires_contact_user_agent=True` and the `US_STOCK_HELPER_CONTACT_EMAIL` env var; poll intervals must respect each kind's floor (`REGULATORY_FILING` 60s, `MACRO_DATA` 300s, `OFFICIAL_ANNOUNCEMENT` 300s). Never lower an interval to make a test faster — inject a clock instead.
- **`robots_allows_polling` is self-declared and never verified against a live robots.txt.** Before registering any new host, a human-checkable note in the task's ledger entry must record that its robots.txt and terms were actually read and permit polling. If you cannot confirm, do not register the source.
- **New sources must not silently change scores.** Any change to how evidence reaches `evidence_confidence` or `market_sentiment` needs a test pinning the before/after and a note in the served payload if the meaning changed (the 形态-factor lesson from roadmap 四点七).
- **Every task ends with the DoD in the handoff doc §四.6**: red-then-green tests, all affected suites green, simulator acceptance for anything user-visible, explicit-pathspec commit, ledger line.
- Ledger: `.superpowers/sdd/2026-08-17-authoritative-source-adapters/progress.md` (create with Task 1; `git add -f`, the directory is gitignored).

---

### Task 1: Extend SEC current-filings coverage to 10-Q, 10-K, 13D, 13G

**Files:**
- Modify: `services/information_layer/information_layer/feeds/registry.py` (`PUBLIC_SOURCES`)
- Modify: `services/information_layer/information_layer/feeds/sec.py` only if the form-code check below demands it
- Test: `services/information_layer/tests/test_adapters.py`
- Test: `services/information_layer/tests/test_source_registry.py`

**Why this is small:** `SecCurrentFilingsAdapter` is form-agnostic — it builds the `browse-edgar?action=getcurrent&type={form}` Atom URL, and `_TITLE_FORM` already parses the *actual* form out of each entry title because EDGAR's `type=` matches by prefix (asking for `4` also returns `424B2`/`425`). `requiring_cik_registry()` picks up any spec with `sec_form_type`, so the mandatory-registry guard from `29e1fbe` covers new forms with no wiring change.

- [x] **Step 1: Confirm the real EDGAR form codes before writing specs.** Beneficial-ownership filings are `SC 13D` / `SC 13G`, not `13D` / `13G`. Fetch one live sample per candidate form (`10-Q`, `10-K`, `SC 13D`, `SC 13G`) with the project's own User-Agent, save the Atom bytes as test fixtures, and record in the ledger what each `type=` actually returned. **If a code differs from the assumption, the fixture wins.**
- [x] **Step 2 (RED):** Add `FormTypePrefixTests`-style cases in `test_adapters.py` driving `SecCurrentFilingsAdapter` with each new form over the captured fixtures: the emitted events carry the parsed form (not the requested prefix), issuer attribution resolves through `CikTickerRegistry` (13D/13G name the *subject* issuer and the *filing* holder — assert which one the event is attributed to and why), `claim_status` is `VERIFIED`, and `available_at`/`retrieved_at` stamping is unchanged. Run and watch them fail.
- [x] **Step 3 (GREEN):** Register four `SourceSpec` entries mirroring `sec-current-8-k` (kind `REGULATORY_FILING`, publisher `sec-edgar`, `allowed_hosts=("www.sec.gov",)`, `reliability=0.99`, `poll_interval_seconds=300.0`, `requires_contact_user_agent=True`, `claim_status=VERIFIED`). Extend `test_source_registry.py` to assert the registry now requires a CIK registry for all six SEC sources.
- [x] **Step 4: Decide the standalone factory's fate.** `build_sec_current_filings_adapters(forms=("8-K","4"))` is *not* what production calls (production goes through `SourceSpec`/`_adapter_for`). Either update its default to match the registry or delete it if nothing but its own test uses it — record the decision in the ledger. Do not leave two disagreeing lists.
- [x] **Step 5: Verify + simulator.** Run `information_layer` and `analysis_api` suites. Restart `analysis-api`, open a stock page in the simulator, and record in the ledger whether the evidence count / factor coverage actually moved. Commit `feat: widen sec current-filings coverage`.

---

### Task 2: Generalize company investor-relations sources

**Files:**
- Modify: `services/information_layer/information_layer/feeds/registry.py`
- Test: `services/information_layer/tests/test_source_registry.py`, `test_adapters.py`

**Why:** `apple-newsroom` and `nvidia-newsroom` are hardcoded one-offs. Franz's watchlist is 46 symbols; two of them having a newsroom is not coverage. The `SourceSpec` shape already supports this — what's missing is a way to declare many IR feeds without hand-writing each `KeywordMapping`.

- [ ] **Step 1 (RED):** Test that a small table of `(symbol, company name, feed URL, host)` rows expands into valid `SourceSpec`s with correct `symbol_mappings`/`entity_mappings`, that a malformed row fails loudly at construction (blank symbol, non-HTTPS URL, host not in `allowed_hosts`), and that duplicate `source_id`s are refused by `SourceRegistry`.
- [ ] **Step 2 (GREEN):** Add the builder plus an initial table covering the largest watchlist names whose IR feeds you have **actually verified** (fetched once, robots/terms read, recorded in the ledger). Quality over count: five verified feeds beat twenty guessed URLs. Keep `reliability=0.95` and the 900s poll interval of the existing two.
- [ ] **Step 3: Keyword honesty.** A symbol mapping that fires on a common English word will mis-attribute (e.g. `GRAB`, `SOUN`). Test the mis-attribution case explicitly and require distinctive keywords or a higher-precision rule for such tickers; if a symbol cannot be safely keyed, leave it out and say so in the ledger.
- [ ] **Step 4: Verify + simulator + commit** `feat: register verified company ir feeds`.

---

### Task 3: Add regulatory and agency sources beyond EDGAR

**Files:** same registry + tests

**Scope, in priority order** (only register what you verify; each needs a public feed, permissive robots, and a stable schema):
1. Exchange trading halts (Nasdaq/NYSE halt feeds) — highest short-term relevance;
2. FDA press announcements / drug approvals — moves single names hard;
3. DOJ / FTC press releases — antitrust and enforcement events;
4. Treasury/OFAC sanctions — the only realistic path to a *geopolitics* source today. Note `geopolitical_mappings` plumbing exists in `FeedConfig`/`SourceSpec` but **no source configures it**, which is why the dashboard's 地缘政治 driver says "尚未接入".

- [ ] **Step 1 (RED):** Per source: a captured real payload fixture, a parsing test asserting event fields and `claim_status`, and an attribution test (symbol mapping where applicable; macro/geopolitical mapping otherwise).
- [ ] **Step 2 (GREEN):** Register the verified subset. For any source you investigated and rejected, write **why** in the ledger (no public feed / robots forbids / schema unstable) — a documented rejection is a result, an undocumented gap is a trap for the next agent.
- [ ] **Step 3: Wire the geopolitics driver.** If a sanctions/geopolitics source lands, the market brief's `geopolitics` driver entry must stop being permanently `available: false` — but only when data genuinely flows; keep the named-reason unavailable path for empty windows.
- [ ] **Step 4: Verify + simulator + commit** `feat: add verified regulatory and agency sources`.

---

### Task 4: Wire coordinator snapshot persistence (the fixed machine nobody plugged in)

**Files:**
- Modify: `services/information_layer/information_layer/feeds/collector.py` (expose the coordinator or accept a snapshot path)
- Modify: `services/analysis_api/src/us_stock_helper_analysis_api/evidence_provider.py` (`evidence_provider_from_environment`)
- Modify: `services/analysis_api/src/us_stock_helper_analysis_api/__main__.py` (save on shutdown)
- Modify: `scripts/local_runtime_support.py` (`build_component_environment`, the analysis-api branch)
- Test: `services/information_layer/tests/test_evidence_collector.py`, `services/analysis_api/tests/test_evidence_provider.py`, `scripts/tests/`

**The defect:** `PollingCoordinator.snapshot()`/`from_snapshot()` are implemented, locked, and unit-tested — and **never called outside tests**. `evidence_provider_from_environment` constructs `EvidenceCollector(build_adapters(...))` with no `coordinator=`, so every process start gets an empty coordinator and re-announces every item still inside each feed's lookback window as brand-new evidence. `EvidenceCollector` also exposes no accessor for its private coordinator, and there is no atexit/signal/`finally` hook that could save one. This is exactly the roadmap-四点七 class: *函数被测试调用不算被产品调用*.

- [ ] **Step 1 (RED):** A test proving today's behavior is wrong: two successive `evidence_provider_from_environment()` calls sharing one snapshot path, with a fake adapter returning the same items both times — the second must publish nothing new. It must fail today because no snapshot is ever read or written.
- [ ] **Step 2 (GREEN):** Add the minimum surface needed (a public coordinator accessor or a snapshot-path parameter on the collector — prefer whichever keeps `information_layer` I/O-free; the *file* write belongs in `analysis_api`, not in `information_layer`). Load at startup when the path exists and parses; a malformed snapshot is **rejected whole** with a named reason and a fresh coordinator (never partially loaded — that rule already exists in `from_snapshot`, keep it).
- [ ] **Step 3: Save on shutdown, and periodically.** A crash between saves must degrade to the current behavior, not corrupt state: write atomically (temp file + rename), mode `0600`, under `~/.us-stock-helper/state/` alongside `devices.sqlite3`. Add the env var in `build_component_environment`'s existing `analysis-api` branch the same way `DEVICE_AUTH_DATABASE` is injected, and document it in `services/analysis_api/README.md`'s env table (that README is pinned by `test_documentation.py` — keep it true).
- [ ] **Step 4: Verify.** `information_layer`, `analysis_api`, `scripts` suites; then a real restart: `launchctl kickstart -k` the analysis-api label twice and confirm from the ledger's own evidence that the second start does not re-announce. Commit `fix: remember what each feed already published across restarts`.

---

### Task 5: Re-examine the evidence gate now that the eyes are open

**Files:** `services/analysis_core/us_stock_helper_core/scoring.py`, its tests; possibly `services/analysis_api` notes

**Why last:** `evidence_confidence < 0.35 → HardGate.INSUFFICIENT_EVIDENCE` is a bare literal at the call site (`scoring.py:450-451`). With more sources landing, this threshold starts *mattering* instead of always firing. Do not touch it before Tasks 1–4 land — tuning a gate against a starved input is how you end up with a gate that passes on nothing.

- [ ] **Step 1: Measure first.** With the new sources live, record in the ledger the actual `evidence_confidence` distribution across the 46-symbol watchlist (a throwaway script under `/tmp`, not a committed tool). State how many symbols clear 0.35 and why.
- [ ] **Step 2 (RED):** Promote the literal to a named constant with a docstring stating its rationale and the measurement date; pin the gate's behavior at the boundary (just below fires, just above does not) and pin that a zero-evidence window still fires.
- [ ] **Step 3:** Only change the *value* if the measurement justifies it, and if you do, disclose it: bump the scoring `method_version` and say so in the served explanation, exactly as the 形态 factor did when its semantics changed (`explainable-horizon-score-v2`). A silent threshold change is a silent score change.
- [ ] **Step 4: Simulator acceptance is the point of this whole plan.** Open the dashboard and three stock pages; record in the ledger what the 综合结论 now says for each — how many are still 不可行动, and for those, what named reason is shown. Commit `refactor: name the evidence gate and pin its boundary`.

---

### Task 6 (optional, scope carefully): Filing document text for measurable filing sentiment

**Read this before starting:** SEC filing sentiment is currently *structurally* unmeasurable, not buggy — the EDGAR Atom feed carries titles only, and `EvidenceEvent` has no document-text field. Making it measurable is a **new capability**, not an extension: a second fetch per filing (the primary document), text extraction, size limits, and a materially higher request volume against EDGAR. That last point is a politeness and ban risk, and the throttle exists precisely because of it.

Decide with Franz whether this is worth doing before writing code. If yes: fetch only for filings already attributed to a watchlist symbol, cache by accession number, respect the existing poll floors, keep extracted text out of the served payload (feed the scorer, cite the URL), and use real captured document fixtures (the `test_factor_fundamentals.py` fixture style, not synthetic strings). If no: record the decision in the ledger and delete this task's checkbox rather than leaving it dangling.

---

### Task 7: Methodology, README, and ledger close-out

- [ ] Extend `docs/indicator-methodology.md` with each new source: what it publishes, its cadence, its attribution rule, its known limitations (e.g. 13D/13G attribution ambiguity, IR feeds being issuer-authored and therefore promotional).
- [ ] Update `services/README.md` / `services/analysis_api/README.md` if any command or env var changed — `test_documentation.py` executes the documented command verbatim and `AllowlistDriftTests` pins the route claim, so a stale README is a red test, not a cosmetic issue.
- [ ] Update `docs/roadmap-to-delivery.md` 阶段 6：tick 补齐权威源适配器 with the commit list, and record any source you deliberately did not add.
- [ ] Close the ledger with the final suite counts, the simulator acceptance notes, and the open questions left for Franz.

---

## Final Result

Real mode has enough eyes to say something. Concretely: SEC coverage spans the filing types that actually move prices; company announcements come from a verified, extensible table instead of two hardcoded newsrooms; regulatory and agency events (halts, FDA, enforcement, sanctions) reach the evidence layer; a restart no longer re-announces yesterday's news as breaking; and the evidence gate is a named, measured, versioned decision rather than an unexamined literal. Everything that still has no source keeps saying so, by name.
