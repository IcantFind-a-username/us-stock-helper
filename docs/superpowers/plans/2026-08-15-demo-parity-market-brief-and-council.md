# Demo Parity: Market Brief and Adviser Council Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close the two demo-only surface clusters that are reachable almost entirely from parts that already exist and are tested: (1) the Dashboard market hero/header gets an honest real-mode counterpart served by a new read-only `GET /market-brief` route; (2) the thirteen-seat adviser council — already servable over `adviser=true` and already decoded on the phone — becomes invocable and rendered in real mode, with the council's capped score adjustment becoming the single served adviser adjustment. Two small red-line fixes land first.

**Context (2026-08-15 gap map):** The app's 演示模式 is the living design prototype: the market hero, priority alert, candidates, agent conversation, and adviser council render deterministic fixture content there, while real mode explicitly refuses ("市场分析尚未接入真实数据", AnalysisNotConnected). This plan advances real-mode parity only where honest data exists today. Deliberately deferred: alerts / candidate radar / agent conversation (each needs a resident scanning or conversation service — 阶段 10 territory), and the chart probability band (design withholds it until calibration exists — 阶段 10).

**Architecture:** analysis_api composes existing pieces only (EvidencePacketBuilder with empty focus, MarketSentiment, evidence-gap accounting, citation freshness) into a versioned market-brief envelope; no new data sources. The route must disclose driver coverage honestly — most designed driver categories have no source yet, and the envelope says so instead of fabricating drivers. Mobile decodes it with the same strictness discipline as the Decision envelope and renders it in place of the placeholder card. The adviser council path reuses the existing `/decision?adviser=` machinery; the council's hard-gate-zeroed, cap-clamped `scoreAdjustment` becomes the served top-level `adviserAdjustment` so the response stops carrying two disagreeing adjustment fields.

**Tech Stack:** Python 3.12 stdlib services + unittest, Expo SDK 57 / React Native 0.86 / TypeScript / Jest, existing device-token auth, existing deploy pinning tests.

## Global Constraints

- Red lines apply unchanged: read-only market data; no order/credential capability; real/proxy/inferred/demo data explicitly separated; unavailable is visibly unavailable; PIT cutoffs loud; adviser influence capped by the shared ±3 constant; fail-closed auth.
- No demo string may render over real data; no real surface may fall back to fixture content.
- The market brief must never invent drivers: categories without a data source appear only inside an explicit `driverCoverage` disclosure naming them unavailable.
- A normal dashboard load may hit `/market-brief` but must never trigger an LLM call; the thirteen-seat council remains one explicit user tap on one symbol and one horizon.
- Scores: objective score and confidence never change with risk preference; the adviser adjustment is display-attributed ("顾问软因子调整后") and zeroed by hard gates.
- Route-set changes update `http_app._READ_PATHS`, `AnalysisApplication.handle`, `deploy/Caddyfile`, and the deploy pinning tests in the same commit.
- Every task: red test first (watch it fail), implement to green, run the affected full suites, then commit only that task's files.
- Test invocations use absolute-path PYTHONPATH (see services/analysis_api/README.md, fixed by the stage-5 review bookkeeping).

---

### Task 1: Render the v3 current-session flow instead of a false unavailability

**Files:**
- Modify: `apps/mobile/src/data/marketGateway.ts`
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx` (participation surface wiring)
- Test: `apps/mobile/src/data/__tests__/marketGateway.test.ts`
- Test: participation surface component tests

**Why:** v3 snapshots fully decode `sections.currentSessionFlow`, but the flattened `participationBars` are hardcoded placeholders with `missingReason: CURRENT_SESSION_FLOW_NOT_CANDLE_ALIGNED`, so real mode permanently claims "暂无可用活动占比" — an unavailability the server never asserted. v2-fallback gateways still show live bars; v3 gateways must not look worse.

- [x] **Step 1 (RED):** Jest tests: given a v3 snapshot whose `currentSessionFlow` is `live/validated`, the participation surface renders the five order-size flow buckets and never the placeholder copy; given the section genuinely `unavailable`, the server's `errorCode`/reason shows verbatim. Both must fail against current behavior.
- [x] **Step 2 (GREEN):** Adapt decoded `NormalizedCapitalFlowPoint[]` into the participation surface for v3; keep the v2 path byte-identical. No contract or backend change.
- [x] **Step 3:** Full mobile suite + typecheck; commit `fix: render served session flow instead of a false unavailability`.

### Task 2: De-demo the real-mode search copy

**Files:**
- Modify: `apps/mobile/src/components/dashboard/StockSearchSheet.tsx`
- Test: its test file

**Why:** Real mode renders "本地关注列表 · 演示" / "没有匹配的演示标的" over real watchlist data — a direct violation of the demo/real labeling red line.

- [x] **Step 1 (RED):** Render the sheet in real mode; assert no string containing 演示 appears and honest watchlist-scope copy does (naming that whole-market search is not yet served). Fails today.
- [x] **Step 2 (GREEN):** Mode-aware copy; demo mode keeps its labels.
- [x] **Step 3:** Commit `fix: stop labeling real search results as demo`.

### Task 3: Serve GET /market-brief from existing evidence pieces

**Files:**
- Create: `services/analysis_api/src/us_stock_helper_analysis_api/market_brief.py`
- Modify: `http_app.py` (`_READ_PATHS`, `handle`), `service.py`
- Modify: `deploy/Caddyfile` + deploy pinning tests
- Test: `services/analysis_api/tests/test_market_brief.py`

**Envelope (schemaVersion "1"):** `status` (`available`/`unavailable` + `reason`), `decisionCutoff`, `marketSession`, `dataHealth` (`fresh`/`stale`/`conflict`/`insufficient` derived from evidence-gap + staleness accounting), `sentiment` (conclusion, actionScore, uncertainty — from MarketSentiment over an empty-focus EvidencePacket), `driverCoverage` (every designed category with `available: false` + `missingReason` where no source exists; only sourced categories carry values), `citations` (https-only, freshness-tagged), `sourceGaps` (named). No symbol scores, no forecast, no adviser content.

- [x] **Step 1 (RED):** Failing tests pin: GET-only (405 writes), device-token gate ordering unchanged, 404 space unchanged elsewhere; envelope shape incl. `driverCoverage` naming unsourced categories; fail-closed `unavailable` naming sources when nothing is readable; structural rejection of order/credential fields; deploy pinning test red until Caddyfile matcher updated.
- [x] **Step 2 (GREEN):** Compose existing builders only. Reuse the evidence provider's collector; do not add new feed fetch paths. Per-request sweep is acceptable only if the existing coordinator throttling provably bounds outbound requests — add a test that a burst of N brief requests within the minimum poll interval performs at most one feed sweep (wire the existing coordinator snapshot/throttle state into the provider if needed; that wiring is in scope here).
- [x] **Step 3:** Full analysis_api + deploy suites; commit `feat: serve an honest market brief over the read-only boundary`.

### Task 4: Decode the market brief on the phone

**Files:**
- Modify: `apps/mobile/src/data/analysisGateway.ts`
- Test: `apps/mobile/src/data/__tests__/analysisGateway.test.ts`

- [x] **Step 1 (RED):** Decoder tests against the frozen Task-3 schema: absent-field → null; non-https citation → reject; embedded order field → whole-payload reject; `unavailable` → typed unavailable with reason; clock-skew tolerance identical to the Decision envelope.
- [x] **Step 2 (GREEN):** `decodeMarketBriefEnvelope` + client method reusing Decision conventions. The decoded type must remain structurally distinct from the demo `DashboardSnapshot` (`demoData: true` stays demo-only by construction).
- [x] **Step 3:** Commit `feat: decode the market brief envelope`.

### Task 5: Real-mode dashboard renders the brief

**Files:**
- Modify: `apps/mobile/src/screens/DashboardScreen.tsx`, `DashboardHeader.tsx`
- Wire: `DataHealthBanner` (currently orphaned)
- Test: `apps/mobile/src/screens/__tests__/DemoAnalysisGating.test.tsx` + dashboard tests

- [x] **Step 1 (RED):** Real mode + brief available → conclusion/actionScore/uncertainty/coverage disclosure/citations render; zero fixture strings. Real mode + brief unavailable → explicit 不可用 card with the server reason, never fixture fallback. Demo mode byte-identical. Header shows session/data-health from the brief in real mode.
- [x] **Step 2 (GREEN):** Replace the placeholder card; priority-alert card and candidate strip stay hidden with copy naming their still-missing services (no fake parity).
- [x] **Step 3:** Full mobile suite; commit `feat: show the real market brief on the dashboard`.

### Task 6: Invoke and render the thirteen-seat council in real mode

**Files:**
- Modify: `apps/mobile/src/data/analysisGateway.ts` (AnalysisRequestOptions `adviser: 'full'` → `&adviser=true`; council-path timeout ≥ server's 300s ceiling)
- Create: `useAdviserCouncil` hook (mirror useAdviserDecision: one explicit tap = one call, no mount effect, abort on leave, cost display)
- Modify: `apps/mobile/src/screens/AdvisersScreen.tsx` real mode
- Test: gateway request-shape + screen tests

**Taxonomy note:** ship the de-branded framework taxonomy the real adviser_llm implements (per-horizon seat counts short 7 / swing 12 / long 9); the demo's named-investor framing stays demo-only. Flagged for Franz's product call; copy keeps "风格模型，非本人意见".

- [x] **Step 1 (RED):** Request-shape test `adviser:'full'` → `&adviser=true`; screen test with a mocked available council pinning per-framework stance/blind-spot/conclusions with verbatim quotes, baseline vs adjusted score, blockedBy gating, usage cost; distinct copy for not-deployed / not-requested / unavailable; exactly one network call per tap, aborted on unmount.
- [x] **Step 2 (GREEN):** Implement hook + rendering; AnalysisNotConnected remains only for the genuinely-not-deployed case.
- [x] **Step 3:** Commit `feat: bring the real adviser council to the phone`.

### Task 7: One adviser adjustment authority

**Files:**
- Modify: `services/analysis_api/.../service.py` (fold council `scoreAdjustment` into served `adviserAdjustment`/`adjustedScore` post-evaluate; explanatory note when council off)
- Modify: `apps/mobile` DecisionCard (baseline/adjusted split rendered only when a council actually ran)
- Test: both sides

- [x] **Step 1 (RED):** Python: council available → top-level `adviserAdjustment == council.scoreAdjustment`, `adjustedScore == baseline + adjustment`, zeroed when `blockedBy` non-empty, `|adjustment| <= ADVISER_SCORE_CAP`; council off → 0 with note. Jest: DecisionCard shows the split only when council status is available (watchlist scores never imply adviser input).
- [x] **Step 2 (GREEN):** Fold post-evaluate where the briefing already computes baseline; engine untouched.
- [x] **Step 3:** Commit `fix: give the served adviser adjustment one authority`.

### Task 8: Pin the ±3 cap across layers

**Files:**
- Modify: `services/adviser_layer/adviser_layer/council.py` (defaults sourced from the shared constant)
- Create: cross-language contract test parsing `apps/mobile/src/domain/models.ts` `ADVISER_SCORE_CAP` and asserting equality with the Python constant

- [x] **Step 1 (RED):** Tests fail while council.py hardcodes 4.0/3.0 and while the TS mirror is comment-enforced only.
- [x] **Step 2 (GREEN):** Single authority; commit `fix: pin the adviser cap across languages`.

### Task 9: Bookkeeping — roadmap and README truth

**Files:**
- Modify: `docs/roadmap-to-delivery.md` (record the stage-5 review outcome as 四点七; tick 阶段 4 live-proof item with the recorded evidence; correct stale 愿景-6 chart claims; note banked 阶段 7 progress)
- Modify: `services/README.md` + `services/analysis_api/README.md` (test commands that fail verbatim)
- Test: extend the documentation pinning test to cover the analysis_api command

- [ ] **Step 1 (RED):** Doc-pinning test executes the README's analysis_api test command and fails while the command is wrong.
- [ ] **Step 2 (GREEN):** Fix commands and roadmap; commit `docs: record the third review and repair command drift`.

---

## Final Result

Real mode gains: an honest market brief on the Dashboard (with named coverage gaps), session/data-health in the header, a working participation surface on v3 gateways, de-demoed search copy, an invocable and rendered thirteen-seat adviser council with one capped adjustment authority, and documentation that tells the truth about commands and progress. Alerts, candidate radar, agent conversation, and the probability band remain visibly deferred with named reasons — no fake parity.
