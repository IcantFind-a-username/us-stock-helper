# Stock Detail and Adviser Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stock-detail, full-chart, and adviser placeholders with native React Native screens that match the approved Calm Alpha prototypes and are ready for physical-iPhone installation.

**Architecture:** Keep Expo Router files thin and continue reading deterministic typed fixtures through `fixtureRepository`. Isolate SVG chart geometry from screen composition, split stock evidence into focused cards, and keep risk-plan selection deterministic in a pure domain helper. The adviser layer may explain or challenge the objective conclusion but may not mutate scores, confidence, facts, or risk-engine outputs.

**Tech Stack:** Expo SDK 57, React Native 0.86, React 19.2, TypeScript 6 strict mode, Expo Router, `react-native-svg`, React Native Testing Library, Jest Expo.

## Global Constraints

- Visual authorities: `ios-stock-detail-demo-v1.html`, `kline-and-macro-context-v2.html`, and `advisor-architecture-v2.html`.
- Written authority: `docs/superpowers/specs/2026-07-24-calm-alpha-figma-design.md`.
- Build native React Native views; never embed the prototypes in a WebView.
- Every screen says `演示数据 · 非实时行情`.
- The stock screen always exposes candlesticks, Magic Nine, forecast bands, patterns, RSI, MACD, institutional/retail proxy, macro/geopolitical context, evidence, and adviser entry.
- Forecasts are probabilistic 50%/80% bands with calibration and invalidation; no deterministic future-price promise.
- Intraday institutional/retail values are visibly labeled `估算代理`; dated reported ownership remains separate.
- Adviser names are visibly labeled as public-philosophy style simulations, not endorsements or current statements.
- Risk preference and long/short selection may select a deterministic plan but may not change `objectiveScore` or `confidence`.
- No order-submit, order-edit, or order-cancel action exists.
- All interactive controls have at least a 44-point target and an accessibility label.
- Use native system fonts and the existing Calm Alpha tokens; do not accept the Skill database's unrelated luxury-font suggestion.

---

### Task 1: Pin the stock and adviser screen contracts

**Files:**
- Create: `apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx`
- Create: `apps/mobile/src/screens/__tests__/AdvisersScreen.test.tsx`

**Interfaces:**
- Consumes: `StockDetailScreen`, `AdvisersScreen`, `AppStateProvider`, mocked Expo Router params
- Produces: stable test IDs `stock-chart-card`, `indicator-rsi`, `indicator-macd`, `participation-proxy`, `market-context-card`, `adviser-council`, and `trade-plan-card`

- [ ] **Step 1: Write the failing stock contract**

Render `/stocks/NVDA` under `AppStateProvider`, assert one demo disclosure, the objective conclusion, professional chart, `九转 7`, `RSI 63.8`, `MACD`, `估算代理`, `机构代理 58%`, `散户代理 42%`, macro and geopolitical copy, then press `问顾问 / 制定方案` and expect the advisers route.

- [ ] **Step 2: Run the focused stock test**

Run:

```bash
npm test -- src/screens/__tests__/StockDetailScreen.test.tsx
```

Expected: FAIL because the screen is still `TemporaryScreen`.

- [ ] **Step 3: Write the failing adviser contract**

Render `AdvisersScreen`, assert objective score `72`, the style-simulation disclaimer, four active adviser summaries, default `做多` + `均衡`, unchanged confidence `68%`, deterministic entry/stop/target/leverage fields, and the persistent `不会自动下单` boundary. Switch to `做空` and `进取`, then assert borrow/fee/unlimited-loss warnings without any submit-order control.

- [ ] **Step 4: Run both contract tests**

Run:

```bash
npm test -- \
  src/screens/__tests__/StockDetailScreen.test.tsx \
  src/screens/__tests__/AdvisersScreen.test.tsx
```

Expected: both fail only because the new hierarchy is absent.

---

### Task 2: Implement chart geometry and professional price chart

**Files:**
- Create: `apps/mobile/src/domain/chart.ts`
- Create: `apps/mobile/src/domain/__tests__/chart.test.ts`
- Create: `apps/mobile/src/components/chart/PriceChart.tsx`
- Create: `apps/mobile/src/components/chart/ChartLegend.tsx`

**Interfaces:**
- Produces: `buildChartGeometry(candles, forecast, width, height)` returning candle bodies/wicks, price labels, historical boundary, forecast 50%/80% polygons, median path, volume bars, and bounds
- Produces: `PriceChart({ stock, compact?: boolean })`

- [ ] **Step 1: Write failing pure geometry tests**

Assert that candle/wick coordinates remain within bounds, positive candles are marked `up`, the forecast begins after the historical boundary, `lower80 <= lower50 <= median <= upper50 <= upper80`, and empty input returns empty geometry without throwing.

- [ ] **Step 2: Run the geometry test and observe RED**

```bash
npm test -- src/domain/__tests__/chart.test.ts
```

- [ ] **Step 3: Implement minimal deterministic geometry**

Use one shared price scale covering candle highs/lows and forecast 80% bounds. Reserve the lower 20% of the SVG for volume, use a fixed gap between historical candles and forecast points, and return semantic series rather than JSX.

- [ ] **Step 4: Render the native SVG chart**

Render grid lines and right-side price labels first, then forecast 80% and 50% bands, dashed median, candle wicks/bodies, volume, completed Magic Nine markers, and a dashed `现在 / 预测起点` divider. Include a textual chart summary for screen readers and a visible legend so color is never the only encoding.

- [ ] **Step 5: Run geometry tests and typecheck**

```bash
npm test -- src/domain/__tests__/chart.test.ts
npm run typecheck
```

Expected: PASS.

---

### Task 3: Compose the stock-detail analysis surface

**Files:**
- Create: `apps/mobile/src/components/stock/StockHeader.tsx`
- Create: `apps/mobile/src/components/stock/IndicatorStrip.tsx`
- Create: `apps/mobile/src/components/stock/ParticipationCard.tsx`
- Create: `apps/mobile/src/components/stock/MarketContextCard.tsx`
- Create: `apps/mobile/src/components/stock/PatternCard.tsx`
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Modify: `apps/mobile/src/screens/FullChartScreen.tsx`

**Interfaces:**
- Consumes: one `StockSnapshot`
- Produces: compact stock page plus a full-chart route using the same `PriceChart`

- [ ] **Step 1: Implement the compact quote header**

Show symbol/company/exchange, price/change, session/latency, watchlist state, horizon switch, and one subordinate demo-data label. Back and adviser controls use 44-point targets.

- [ ] **Step 2: Implement always-visible RSI and MACD**

The portrait strip shows RSI value/state/direction/divergence and MACD DIF/DEA/crossover/histogram. Text accompanies every color state.

- [ ] **Step 3: Implement participation and ownership separation**

The first card uses a two-part horizontal histogram labeled `机构代理 58%` and `散户代理 42%`, plus confidence, methodology version, coverage, and the sentence that it is not real account identity. A separate reported-ownership block shows the `2026-06-30` reporting date.

- [ ] **Step 4: Implement market and geopolitical context**

Show broad-market, sector, macro, and geopolitical state with the score adjustment and resulting leverage/entry constraints. Keep sources available through an evidence sheet.

- [ ] **Step 5: Implement pattern and fundamentals summaries**

Show Magic Nine completeness, original Dragon Trend version/invalidation, five pattern states, financial health, cash/debt, growth/margins, valuation, supply-chain context, and material risks through progressive disclosure.

- [ ] **Step 6: Compose the screen**

Use the order: header → horizon → conclusion → chart toolbar → chart → RSI/MACD → participation → patterns → market context → fundamentals → evidence/actions. `查看大图` opens the full-chart route; `问顾问 / 制定方案` opens advisers.

- [ ] **Step 7: Run the stock contract**

```bash
npm test -- src/screens/__tests__/StockDetailScreen.test.tsx
npm run typecheck
```

Expected: PASS.

---

### Task 4: Add deterministic adviser and risk-plan selection

**Files:**
- Create: `apps/mobile/src/domain/plan.ts`
- Create: `apps/mobile/src/domain/__tests__/plan.test.ts`
- Create: `apps/mobile/src/components/advisers/AdviserSummary.tsx`
- Create: `apps/mobile/src/components/advisers/TradePlanCard.tsx`
- Create: `apps/mobile/src/components/advisers/PlanSelector.tsx`

**Interfaces:**
- Produces: `selectTradePlan(plans, side, preference): TradePlan`
- Produces: `PlanSelector({ side, preference, onSideChange, onPreferenceChange })`

- [ ] **Step 1: Write failing plan-selection tests**

For all six side/preference combinations, assert exact plan IDs. Assert every plan retains objective score `72`, confidence `0.68`, and maximum leverage `1.5`; short plans require non-null short-risk data.

- [ ] **Step 2: Run the plan test and observe RED**

```bash
npm test -- src/domain/__tests__/plan.test.ts
```

- [ ] **Step 3: Implement exact deterministic selection**

Select by `side` and `preference`; throw a descriptive error when a fixture is missing. Do not calculate or modify risk values in the UI.

- [ ] **Step 4: Implement selectors and plan presentation**

Use segmented long/short and conservative/balanced/aggressive controls. Present entry method/range, quantity, risk budget, leverage ceiling, invalidation, stop logic, targets, reward/risk, holding window, cancellation conditions, evidence snapshot, and warnings.

- [ ] **Step 5: Run plan tests**

```bash
npm test -- src/domain/__tests__/plan.test.ts
```

Expected: PASS.

---

### Task 5: Compose the thirteen-style adviser council

**Files:**
- Modify: `apps/mobile/src/screens/AdvisersScreen.tsx`

**Interfaces:**
- Consumes: `fixtureRepository.getStock`, `getAdvisers`, `getTradePlans`, and `selectTradePlan`
- Produces: evidence-first council, bounded soft-factor explanation, and analysis-only plan

- [ ] **Step 1: Implement the objective header**

Show evidence snapshot freshness, objective conclusion/score/confidence, base versus market-adjusted score, and the rule that preference cannot alter the fact layer.

- [ ] **Step 2: Implement relevant-adviser routing**

Default to active advisers, show direction/confidence/focus/thesis/counterargument, visibly show abstention, and provide a collapsed `查看全部 13 位` list. State expected token mode as `按需调用 · 节省 Token`.

- [ ] **Step 3: Implement disagreement and research request**

Show strongest disagreement, missing evidence, and a `申请补充调查` control that opens a local explanatory state only; no backend request is sent in this phase.

- [ ] **Step 4: Attach the deterministic plan**

Changing selectors calls `selectTradePlan`. The objective score and confidence at the top remain unchanged. Short mode exposes borrow availability, checked time, fee, short interest, crowding, squeeze/recall/unlimited-loss warnings.

- [ ] **Step 5: Add the persistent safety footer**

State `仅分析与建议，不连接券商，不会自动下单。` No order action exists.

- [ ] **Step 6: Run the adviser contract**

```bash
npm test -- src/screens/__tests__/AdvisersScreen.test.tsx
npm run typecheck
```

Expected: PASS.

---

### Task 6: Verify visual quality and iPhone readiness

**Files:**
- Update if visual output changed: `docs/design-reference/baselines/*`
- Update: `docs/design-reference/dashboard-visual-regression.md`

**Interfaces:**
- Consumes: complete native app
- Produces: verified build ready for Xcode Personal Team installation

- [ ] **Step 1: Run the UI/UX validation searches**

```bash
python3 .agents/skills/ui-ux-pro-max/scripts/search.py \
  "mobile financial chart accessibility touch safe area" --domain ux
python3 .agents/skills/ui-ux-pro-max/scripts/search.py \
  "financial time series probability forecast" --domain chart
python3 .agents/skills/ui-ux-pro-max/scripts/search.py \
  "accessibility performance navigation" --stack react-native
```

- [ ] **Step 2: Run the complete quality suite**

```bash
npm run typecheck
npm run lint
npm test
```

Expected: all exit 0.

- [ ] **Step 3: Build the iOS simulator target**

```bash
xcodebuild \
  -workspace ios/USStockHelper.xcworkspace \
  -scheme USStockHelper \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build
```

Expected: `** BUILD SUCCEEDED **`.

- [ ] **Step 4: Inspect at 390 × 844 and 430 × 932**

Compare native screenshots with the approved prototypes for chart clarity, first-fold hierarchy, touch size, safe areas, RSI/MACD visibility, institutional-proxy labeling, evidence access, and the no-order boundary.

- [ ] **Step 5: Prepare the physical-device handoff**

Confirm the workspace, bundle identifier, dev-client command, and Xcode signing path. Do not store Apple credentials or provisioning profiles. The next goal is to select the user's Personal Team, connect/trust the iPhone, enable Developer Mode, install, launch from the Home Screen, and verify Fast Refresh.
