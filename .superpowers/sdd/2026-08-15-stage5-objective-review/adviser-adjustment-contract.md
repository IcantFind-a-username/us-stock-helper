# `adviserAdjustment` wire contract (as implemented)

Server-side fix for `adviser-adjustment-null-contract` landed in commit
`b05de28` on `feature/iphone-demo`
(`services/analysis_api/src/us_stock_helper_analysis_api/service.py`,
`AnalysisService.decision()` and `AnalysisService._unavailable()`). This
document is the as-shipped wire semantics for whoever wires the mobile
decoder — it describes the server exactly as it now behaves, not a proposal.

## Field

Top-level field on the `/decision` response, sibling of `score`,
`baselineScore`, `adviserCouncil`:

```
"adviserAdjustment": number | null
```

Old behavior (fixed): this field was structurally always `0.0`, because
`DecisionEngine.evaluate()` is never handed adviser opinions on the live
path (`output.adviser_adjustment` is always `0.0`). The real council
adjustment lived only inside `adviserCouncil.value.scoreAdjustment`, so a
response could show `adviserAdjustment: 0.0` right next to
`adviserCouncil.value.scoreAdjustment: 2.0` — two disagreeing numbers for
the same concept, and no way to tell "the council moved nothing" apart from
"no council ran at all."

New behavior: `adviserAdjustment` is derived from `adviserCouncil.value`
(not from the engine's own field) at response-build time. There is exactly
one adjustment authority.

## Null semantics

`adviserAdjustment` is `null` whenever `adviserCouncil.value` is `null` —
i.e. whenever no council actually ran for this response. This covers every
state where `adviserCouncil.status !== "available"`:

- `adviserCouncil.status === "not-requested"` — the caller passed
  `adviser=off` (the default), or passed `adviser="news"` (news
  interpretation only requested; the council is never convened in that
  mode).
- `adviserCouncil.status === "unavailable"` — the adviser SDK is not
  installed, the API credential is missing/unreachable, the model call
  failed unexpectedly, or the decision itself was `status: "unavailable"`
  (no completed candles at the cutoff, so nothing to brief a council on).

`null` is never accompanied by a `0.0` anywhere that claims to be the
adjustment. `0.0` is reserved for the case below where a council actually
ran and was voided.

**Explanatory note**: whenever `adviserAdjustment` is `null` *and the
decision itself is otherwise live* (`status: "live"`), the response's
top-level `notes` array contains this exact string:

```
"本次没有召开顾问委员会，顾问调整为空，而非测得的零。"
```

(Round-2 fix: this note was English boilerplate appended to every
default-mode response, diluting the notes channel on a Chinese UI. It is
now emitted directly in Chinese by the server — consistent with the
served-vocabulary conventions in `apps/mobile/src/i18n/serverVocabulary.ts`
and with the directly-Chinese notes this same fold block already emits
elsewhere (the excluded-evidence and unread-source notes) — rather than
relying on a client-side translation table. Any consumer still matching
on the old English string (`"No adviser council ran for this response,
so adviserAdjustment is null rather than a measured zero."`) needs to
switch to the string above; the field itself (`adviserAdjustment: null`)
is unchanged.)

Exception: when the whole decision is `status: "unavailable"` (no candles
at all — `score`, `baselineScore`, `adviserAdjustment` are all `null`), no
separate note is added for `adviserAdjustment` specifically; the response's
one governing reason (e.g. `"No completed candles were available at the
decision cutoff."`) is the first entry of `notes` and already covers why
nothing — including any adjustment — was produced.

## Available semantics (the fold)

When `adviserCouncil.value` is not null (`adviserCouncil.status ===
"available"`), the server folds the council's own verdict into the
top-level fields as the sole source of truth:

```
adviserAdjustment == adviserCouncil.value.scoreAdjustment   (exact equality, same float)
score.value        == adviserCouncil.value.adjustedScore     (exact equality, same float)
```

`adviserCouncil.value.scoreAdjustment` was already, before this fix,
computed by `adviser_llm`'s `apply_hard_gate()`
(`services/adviser_llm/src/adviser_llm/gating.py`):

- **Cap**: clamped to `±ADVISER_SCORE_CAP` before this fix ever runs.
  `ADVISER_SCORE_CAP = 3.0` (single authority:
  `us_stock_helper_core.scoring.ADVISER_SCORE_CAP`, re-exported from
  `us_stock_helper_core`). So `|adviserAdjustment| <= 3.0` always holds when
  non-null. The server asserts this at the fold point
  (`assert abs(adviser_adjustment) <= ADVISER_SCORE_CAP`) rather than
  trusting it silently — an assertion failure there is a bug in
  `adviser_llm`, not a state the wire contract needs to represent.
- **Gate-zeroing**: if `adviserCouncil.value.blockedBy` is non-empty (a
  hard gate voided the council), `adviserCouncil.value.scoreAdjustment` is
  exactly `0.0`, and so `adviserAdjustment` is `0.0` — **not** `null`. The
  council did run; the gate voided what it would have said. `null` means
  "no council," `0.0` means "a council ran and was voided, or genuinely
  found nothing to move."
- `score.value` in the gated case therefore equals `baselineScore.value`
  unchanged (`adjustedScore == baselineScore` inside `apply_hard_gate` when
  gated).
- In the ungated case, `score.value == baselineScore.value +
  adviserAdjustment`, clamped to `[0, 100]` — which is exactly what
  `adviserCouncil.value.adjustedScore` already is, so the server just
  copies that number in rather than recomputing the clamp.

**Important**: only `score.value` (the numeric field) is overwritten by the
fold. `score.direction`, `score.actionable`, `score.contributions`,
`score.factorCoverage`, `score.unavailableFactors`, `score.blockedBy`, and
`score.methodVersion` are **not** touched — they continue to describe the
objective (pre-council) computation, matching the existing design decision
already encoded in `adviser_llm`'s `CouncilVerdict.objective_direction`
("the council never overrides the objective direction; it only nudges the
score inside the cap"). A reader wanting the pre-adjustment number reads
`baselineScore.value`, which is unchanged and still equals the objective
score `score` used to always report.

## State truth table

| Request                                   | `adviserCouncil.status` | `adviserCouncil.value` | `adviserAdjustment`         | `score.value`                              | note added? |
|--------------------------------------------|--------------------------|--------------------------|-------------------------------|----------------------------------------------|--------------|
| `adviser=off` (default)                    | `not-requested`          | `null`                    | `null`                          | `baselineScore.value`                          | yes |
| `adviser="news"`                           | `not-requested`          | `null`                    | `null`                          | `baselineScore.value`                          | yes |
| `adviser=true`/`"full"`, SDK/credential unavailable or model call failed | `unavailable` | `null` | `null` | `baselineScore.value` | yes |
| `adviser=true`/`"full"`, council ran, hard gate present | `available` | non-null, `blockedBy` non-empty | `0.0` | `baselineScore.value` (unchanged) | no |
| `adviser=true`/`"full"`, council ran, no hard gate | `available` | non-null | `adviserCouncil.value.scoreAdjustment` (`-3.0..3.0`) | `baselineScore.value + adviserAdjustment`, clamped `[0,100]`, `== adviserCouncil.value.adjustedScore` | no |
| decision itself `status: "unavailable"` (no candles) | whatever `unavailable_for_mode`/`not_requested` produced | `null` | `null` | `score` and `baselineScore` are both `null` too | no (the governing `reason` note covers it) |

## Example payloads

Council off (the common case):

```json
{
  "status": "live",
  "score": { "value": 62.78, "...": "..." },
  "baselineScore": { "value": 62.78, "...": "..." },
  "adviserAdjustment": null,
  "adviserCouncil": { "status": "not-requested", "reason": "本次请求没有调用模型；只有用户对单只股票明确点击后才会调用。", "value": null },
  "notes": [
    "...",
    "本次没有召开顾问委员会，顾问调整为空，而非测得的零。"
  ]
}
```

Council available, ungated, bullish:

```json
{
  "status": "live",
  "score": { "value": 65.78, "...": "..." },
  "baselineScore": { "value": 62.78, "...": "..." },
  "adviserAdjustment": 3.0,
  "adviserCouncil": {
    "status": "available",
    "reason": null,
    "value": {
      "baselineScore": 62.78,
      "adjustedScore": 65.78,
      "scoreAdjustment": 3.0,
      "actionable": true,
      "blockedBy": [],
      "...": "..."
    }
  }
}
```

Council available but hard-gated:

```json
{
  "status": "live",
  "score": { "value": 62.78, "blockedBy": ["stale_data"], "...": "..." },
  "baselineScore": { "value": 62.78, "...": "..." },
  "adviserAdjustment": 0.0,
  "adviserCouncil": {
    "status": "available",
    "value": {
      "baselineScore": 62.78,
      "adjustedScore": 62.78,
      "scoreAdjustment": 0.0,
      "actionable": false,
      "blockedBy": ["stale_data"],
      "...": "..."
    }
  }
}
```

## What the mobile decoder needs to do

Per `fix-units.json`'s `redTestFirst` for this unit, the mobile-side
decoder (`decodeDecisionEnvelope` in
`apps/mobile/src/data/analysisGateway.ts`) needs to accept
`adviserAdjustment: null` as a normal, expected value (not a decode
failure) — the domain model already types it as `number | null`
(`apps/mobile/src/domain/models.ts:871`), so this is very likely a decoder
gap rather than a domain-model gap. Whatever currently reads the top-level
`adviserAdjustment` (or should, if nothing does yet — a repo-wide check
found no current call site in `analysisGateway.ts`) must not assume it is
always a number, and any UI surface built on it should render "no
adjustment" distinctly from "adjustment of zero," mirroring the
distinction the server now makes.

## Server-side tests pinning this contract

`services/analysis_api/tests/test_adviser_briefing.py`:
- `AdviserAdjustmentContractTests.test_council_off_reports_null_not_a_fake_zero`
- `AdviserAdjustmentContractTests.test_council_unavailable_reports_null_not_a_fake_zero`
- `AdviserAdjustmentContractTests.test_news_only_mode_never_convenes_a_council_and_reports_null`
- `AdviserAdjustmentContractTests.test_an_available_council_is_the_sole_adjustment_authority`
- `HardGateTests.test_the_council_cannot_lift_a_score_the_hard_gate_blocked` (extended with the
  `adviserAdjustment == 0.0` / `score.value == baselineScore.value` pins)
