# Overnight App Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the interrupted `feature/iphone-demo` worktree into a launchable, broadly usable U.S. stock helper whose real UI shows complete Magic Nine sequences, dated institutional disclosures, time-zone-correct greetings, honest cross-symbol degradation, and an explicitly on-demand Claude adviser.

**Architecture:** Preserve the existing React Native → market gateway / analysis API split and finish the uncommitted slice in place. Deterministic market and evidence processing remains the default request path; the Claude adviser is a separately requested, measured, cached-on-screen enhancement and is never fanned out across a watchlist. Native Simulator screenshots and interactions are the acceptance surface after automated tests pass.

**Tech Stack:** Expo SDK 57, React Native 0.86, TypeScript, Jest, Python 3.11/3.12 standard-library services, Anthropic SDK in the isolated adviser package, Xcode Simulator.

## Global Constraints

- Preserve all existing uncommitted work; do not reset or rewrite Claude's partial implementation.
- Use `Asia/Shanghai` for the greeting regardless of the simulator's locale or host time zone.
- A normal dashboard, watchlist, or stock-detail load must not invoke Claude.
- A model call requires a visible user action on one stock and one horizon.
- Never print, persist, or return `ANTHROPIC_API_KEY` or device tokens.
- Reported holdings remain delayed disclosure and separate from the intraday participation proxy.
- Magic Nine labels are derived point-in-time from completed candles and cannot use future bars.
- Missing sources degrade with a named reason; they do not turn into zeros, neutral scores, or blank cards.
- The app remains read-only and exposes no order submission path.

---

### Task 1: Recover the interrupted test baseline

**Files:**
- Modify: `apps/mobile/src/components/chart/__tests__/__svgdump.test.tsx`
- Verify: all currently modified mobile and service files

**Interfaces:**
- Consumes: the dirty worktree left by Claude
- Produces: a default test command that contains only automated assertions, while retaining the optional SVG inspection utility

- [ ] **Step 1: Capture the current failures**

Run `npm test -- --runInBand` and `npm run typecheck` in `apps/mobile`.

Expected: the missing `InstitutionalHoldingsCard` is the product failure; the SVG dump fails only because `SVG_OUT` was not supplied.

- [ ] **Step 2: Make the SVG dump explicitly opt-in**

Use an environment-gated test declaration:

```ts
const svgDump = process.env.SVG_OUT ? it : it.skip;

svgDump("dumps the canvas for a human to look at", async () => {
  // existing body, including writeFileSync(process.env.SVG_OUT!, body)
});
```

- [ ] **Step 3: Verify the recovery change**

Run the SVG test without `SVG_OUT`; expected: skipped, not failed. Run it once with an output path under `/tmp`; expected: pass and a non-empty SVG file.

---

### Task 2: Render a Shanghai-time greeting

**Files:**
- Create: `apps/mobile/src/domain/greeting.ts`
- Create: `apps/mobile/src/domain/__tests__/greeting.test.ts`
- Modify: `apps/mobile/src/components/dashboard/DashboardHeader.tsx`
- Modify: `apps/mobile/src/screens/DashboardScreen.tsx`
- Test: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Consumes: `Date`
- Produces: `shanghaiGreeting(now: Date, name: string): string`

- [ ] **Step 1: Write failing boundary tests**

Cover 01:45, 06:00, 12:00, 15:00, and 20:00 in `Asia/Shanghai`, including a UTC instant whose host-local date differs.

Expected copy:

```ts
expect(shanghaiGreeting(atShanghai("2026-08-14T01:45:00"), "Franz"))
  .toBe("夜深了，Franz");
expect(shanghaiGreeting(atShanghai("2026-08-14T20:00:00"), "Franz"))
  .toBe("晚上好，Franz");
```

- [ ] **Step 2: Implement the smallest formatter**

Extract the Shanghai hour with `Intl.DateTimeFormat(..., { timeZone: "Asia/Shanghai", hour: "2-digit", hourCycle: "h23" })` and map 00–04 to `夜深了`, 05–11 to `早上好`, 12–13 to `中午好`, 14–17 to `下午好`, and 18–23 to `晚上好`.

- [ ] **Step 3: Feed the ticking clock into the header**

Call `useNow()` in `DashboardScreen`, pass `now` into `DashboardHeader`, and render the formatter result instead of the hard-coded string.

- [ ] **Step 4: Verify**

Run the greeting tests and dashboard tests, then inspect the Simulator at the current Shanghai time.

---

### Task 3: Carry the complete Magic Nine series to the chart

**Files:**
- Modify: `services/market_gateway/src/us_stock_helper_market_gateway/snapshot.py`
- Modify: `services/market_gateway/tests/test_snapshot.py`
- Modify: `apps/mobile/src/domain/models.ts`
- Modify: `apps/mobile/src/data/marketGateway.ts`
- Modify: `apps/mobile/src/data/__tests__/marketGateway.test.ts`
- Modify: `apps/mobile/src/components/chart/PriceChart.tsx`
- Modify: `apps/mobile/src/components/chart/ChartCanvas.tsx`
- Modify: `apps/mobile/src/components/chart/__tests__/PriceChart.test.tsx`

**Interfaces:**
- Consumes: `TDSetupResult.bullish_counts` and `TDSetupResult.bearish_counts`
- Produces: `MagicNineCountPoint[]`, where each point has `index`, `count`, and `direction`

- [ ] **Step 1: Write the failing gateway contract test**

Assert that `indicators.magicNine.series` aligns one-for-one with `candles`, uses zero/null for bars outside a run, restarts after a completed nine, and never names an index outside the candle array.

- [ ] **Step 2: Serialize the existing point-in-time counts**

The gateway must serialize the counts already returned by `td_setup`; it must not recompute them in the phone:

```py
"series": [
    {"index": i, "count": bullish, "direction": "bullish"}
    if bullish else
    {"index": i, "count": bearish, "direction": "bearish"}
    if bearish else None
    for i, (bullish, bearish) in enumerate(
        zip(setup.bullish_counts, setup.bearish_counts)
    )
],
```

- [ ] **Step 3: Decode and validate the series on the phone**

Reject wrong lengths, non-integer counts, counts outside 1..9, conflicting directions, and out-of-range indices. Preserve `lastCompleted` for the textual summary.

- [ ] **Step 4: Draw every visible non-null count**

Map each point through `geometry.candles.sourceIndex`, place bearish counts above candles and bullish counts below candles where space allows, and retain direction-specific colors. Do not fabricate labels for candles outside the visible chart window.

- [ ] **Step 5: Verify**

Run gateway, decoder, chart, and stock-screen tests. In the Simulator, open SOFI and at least one second symbol, confirm multiple consecutive labels are visible, then pan/zoom and confirm labels stay attached to their candles.

---

### Task 4: Finish the institutional holdings surface

**Files:**
- Create: `apps/mobile/src/components/stock/InstitutionalHoldingsCard.tsx`
- Modify: `apps/mobile/src/components/stock/ParticipationCard.tsx`
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Modify: `apps/mobile/src/screens/FullChartScreen.tsx`
- Test: `apps/mobile/src/components/stock/__tests__/InstitutionalHoldingsCard.test.tsx`
- Test: `apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx`

**Interfaces:**
- Consumes: `DelayedInstitutionalHolding[]` in newest-first order
- Produces: a dedicated delayed-disclosure card with a latest-quarter summary and bounded history

- [ ] **Step 1: Keep Claude's failing tests as the acceptance contract**

The existing tests require SOFI's 56.59%, 1,062 institutions, 7.31 亿 shares, quarter-over-quarter deltas, 44-day period-end lag, readable dates, an explicit history count, honest empty state, and a 12pt minimum font floor.

- [ ] **Step 2: Implement only that contract**

Use pure helpers for compact share counts, signed deltas, quarter/date labels, and lag calculation. Invalid dates render `滞后未知`, never `0 天`.

- [ ] **Step 3: Separate holdings from participation**

Remove the one-line holdings summary from `ParticipationCard`; keep its intraday proxy and label. Render `InstitutionalHoldingsCard` as its own stock-detail section so the quarterly disclosure cannot disappear when participation bars are unavailable.

- [ ] **Step 4: Verify across populated and empty symbols**

Run component/screen tests and inspect SOFI plus a symbol with no holdings. The latter must show `未提供机构持仓披露`, not `0%`.

---

### Task 5: Make deterministic analysis degrade per source, not per stock

**Files:**
- Modify: `services/information_layer/information_layer/cik_registry.py`
- Modify: `services/information_layer/information_layer/feeds/collector.py`
- Modify: `services/information_layer/information_layer/feeds/generic.py`
- Modify: `services/analysis_api/src/us_stock_helper_analysis_api/evidence_provider.py`
- Modify: `services/analysis_api/src/us_stock_helper_analysis_api/service.py`
- Modify: `services/analysis_api/src/us_stock_helper_analysis_api/http_app.py`
- Test: corresponding `services/information_layer/tests/*` and `services/analysis_api/tests/*`
- Test: `services/analysis_core/tests/test_factor_coverage.py`

**Interfaces:**
- Consumes: completed candles, whatever evidence sources answered, CIK/ticker mapping, and factor readings
- Produces: a `live` decision with explicit coverage/gaps whenever the deterministic chain has enough bars; `unavailable` only when no completed bars exist or a hard invariant fails

- [ ] **Step 1: Run the interrupted service tests with an isolated test environment**

Use an available Python environment or install test-only dependencies into a temporary venv under `/tmp`; do not alter global Python.

- [ ] **Step 2: Complete Claude's partial-source work**

One failed feed must be named in `notes` while successful feeds still reach the decision engine. An all-source failure remains unavailable rather than masquerading as a quiet news window.

- [ ] **Step 3: Verify broad symbol attribution**

Exercise representative listed issuers (`SOFI`, `NVDA`, `AAPL`, `MSFT`, `TSLA`) through the CIK registry and generic/EDGAR adapters. A missing fundamental or macro factor is a stated unavailable contribution and must not crash the whole decision.

- [ ] **Step 4: Verify phone rendering of partial coverage**

The stock page must show the objective technical decision, factor coverage, unavailable factors, and named source gaps without displaying a blank or generic malformed-data state.

---

### Task 6: Expose Claude only as an explicit, measured request

**Files:**
- Modify: `apps/mobile/src/data/analysisGateway.ts`
- Modify: `apps/mobile/src/data/__tests__/analysisGateway.test.ts`
- Modify: `apps/mobile/src/state/MarketDataProvider.tsx`
- Modify: `apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx`
- Modify: `apps/mobile/src/components/news/DecisionInterpretationCard.tsx`
- Modify: `apps/mobile/src/components/news/DecisionNewsSection.tsx`
- Modify: `apps/mobile/src/components/news/__tests__/DecisionNewsSection.test.tsx`
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Verify: `services/analysis_api/tests/test_adviser_briefing.py`

**Interfaces:**
- Consumes: `getDecision(symbol, horizon, signal?, { adviser?: boolean })`
- Produces: an on-demand adviser request for one visible symbol/horizon and a measured `AdviserUsage`

- [ ] **Step 1: Prove normal loads never request the model**

Assert dashboard/watchlist and initial stock-detail calls omit `adviser`; the server-side `ExplodingAdviser` test must remain green for ordinary decisions.

- [ ] **Step 2: Add a visible one-stock action**

Only the `not-requested` model card shows a button such as `请求一次模型解读`. Pressing it sends `adviser=1` for the currently open symbol and horizon. Disable the button while that request is in flight.

- [ ] **Step 3: Keep the result on screen and avoid duplicate spend**

Cache the returned adviser decision in the mounted stock screen by `(symbol, horizon, decisionCutoff)`. Re-renders and chart interactions reuse it; changing symbol/horizon returns to the deterministic result and requires another explicit press.

- [ ] **Step 4: Show the receipt and degradation**

Render measured input/output tokens, cache-read tokens when non-zero, cost, and model. A missing credential or rejected response renders `unavailable` with a redacted reason and keeps the deterministic decision usable.

- [ ] **Step 5: Use at most one live smoke call**

Only after all mock tests pass and only if the running analysis service reports the credential as configured, request one SOFI short-horizon interpretation. Record the returned usage; do not convene calls for any other symbol.

---

### Task 7: Build, install, and inspect the actual app

**Files:**
- Modify only files required by failures found in the native acceptance loop
- Do not commit generated `apps/mobile/ios` products

**Interfaces:**
- Consumes: the verified source tree and current Expo configuration
- Produces: a launchable `com.franz.usstockhelper.dev` Simulator app

- [ ] **Step 1: Run fresh static and automated verification**

Run mobile typecheck, lint, all Jest suites, relevant Python suites, and the repository smoke tests. Read full exit codes and failure counts.

- [ ] **Step 2: Rebuild and install**

Build/install on the already booted iPhone 17 Pro Max simulator, launch `com.franz.usstockhelper.dev`, and confirm Metro serves the current bundle.

- [ ] **Step 3: Execute the real UI route matrix**

Inspect dashboard, SOFI detail, a second populated symbol, a partial-data symbol, full chart, holdings history, and the model card. Capture screenshots after each meaningful state change.

- [ ] **Step 4: Fix only reproduced native defects**

For every defect found in the Simulator, add an automated regression test that fails for the same reason, implement the minimal fix, rerun tests, and return to the same native screen.

- [ ] **Step 5: Final verification and commit**

Rerun the complete verification commands, review `git diff` for secrets and unrelated files, then commit coherent batches. Report any environment-only limitation separately from product defects.

