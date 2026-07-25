# Real Market Mobile Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixture-driven stock pages with one point-in-time-safe moomoo vertical slice that shows a real watchlist, completed K-lines, MA5/RSI/MACD/Magic Nine, delayed institutional disclosures, and a per-candle 100% main-force/retail order-size activity histogram on the iPhone.

**Architecture:** Keep `market_gateway` as the only OpenD boundary and `analysis_core` as the deterministic algorithm boundary. Add one gateway snapshot assembler that acquires normalized provider batches under a single decision cutoff, passes completed candles and validated capital-flow rows into `analysis_core`, and returns one versioned contract. The mobile client validates that contract, stores explicit live/stale/unavailable/demo state in a market-data provider, and renders the existing approved UI without silently mixing fixtures into a live screen.

**Tech Stack:** Python 3.11, standard-library gateway HTTP server, moomoo OpenD quote context, typed dataclasses, unittest, mypy; Expo SDK 57, React Native 0.86, TypeScript 6 strict mode, Expo Router, `react-native-svg`, Jest Expo, React Native Testing Library.

## Global Constraints

- Written authority: `docs/superpowers/specs/2026-07-25-real-market-backend-v1-design.md`.
- Use only `OpenQuoteContext`; do not import, instantiate, unlock, or expose `OpenSecTradeContext`.
- Consume only completed candles. Every input `availableAt` must be less than or equal to the response `decisionCutoff`.
- Store and compare timestamps in UTC; use exchange-local time only to assign rows to US sessions and K-line buckets.
- The 100% bar is an order-size activity proxy: dark = `|Δsuper| + |Δbig|`, light = `|Δmid| + |Δsmall|`. It is not institution/retail identity or reported ownership.
- Never invent or interpolate a participation bar. Missing, zero-denominator, mixed-session, future, duplicate, or insufficient-coverage input produces a missing bar with a reason.
- `mainShare + retailShare == 1` within `1e-9` for every available bar.
- Institutional holdings remain a separate delayed disclosure section with their reporting and availability dates.
- Production mode never falls back to fixtures. Demo mode is explicit and labels the complete screen `demo`.
- A stale cache retains its original timestamp and is labeled `stale`; it is never relabeled `live`.
- Forecasts remain hidden/unavailable in this slice unless a real, versioned forecast exists. Existing fixture forecasts must not be placed on a real chart.
- The app is analysis-only. No order, trade unlock, account balance, or position mutation route may exist.
- Every task follows red-green-refactor, runs focused tests first, and commits only its scoped files after the full relevant suite passes.

---

### Task 1: Add point-in-time capital participation primitives

**Files:**
- Create: `services/analysis_core/us_stock_helper_core/participation.py`
- Modify: `services/analysis_core/us_stock_helper_core/models.py`
- Modify: `services/analysis_core/us_stock_helper_core/__init__.py`
- Create: `services/analysis_core/tests/test_participation.py`

**Interfaces:**
- Produce `CapitalFlowPoint(symbol, timestamp, available_at, total_net, super_net, big_net, mid_net, small_net, session)`
- Produce `ParticipationBar(symbol, interval, closed_at, available_at, main_share, retail_share, main_activity, retail_activity, net_flow, coverage, quality_status, missing_reason, method_version)`
- Produce `build_participation_bars(flow_points, completed_bars, decision_cutoff, *, noise_floor=1e-9, bucket_abs_tol=1e-6, bucket_rel_tol=1e-9)`

- [ ] **Step 1: Write the failing validation tests**

Add tests covering UTC enforcement, finite numbers, strictly increasing timestamps, symbol equality, per-row `total_net ≈ super+big+mid+small`, no input after `decision_cutoff`, and no cross-session differencing.

```python
def test_rejects_future_duplicate_and_inconsistent_flow_rows(self) -> None:
    with self.assertRaisesRegex(ValueError, "strictly increasing"):
        build_participation_bars((point0, point0), bars, cutoff)
    with self.assertRaisesRegex(ValueError, "decision cutoff"):
        build_participation_bars((replace(point1, available_at=cutoff + ONE_SECOND),), bars, cutoff)
    with self.assertRaisesRegex(ValueError, "bucket sum"):
        build_participation_bars((replace(point1, total_net=999.0),), bars, cutoff)
```

- [ ] **Step 2: Run the focused test and observe RED**

```bash
PYTHONPATH=services/analysis_core python3 -m unittest -v services.analysis_core.tests.test_participation
```

Expected: FAIL because `participation` and its models do not exist.

- [ ] **Step 3: Implement immutable validated input/output models**

Use frozen, slotted dataclasses. `ParticipationBar` represents absence with `main_share=None`, `retail_share=None`, a non-empty `missing_reason`, and `quality_status="unavailable"`; an available bar requires both shares, a null missing reason, and `quality_status="live"`.

- [ ] **Step 4: Write the failing aggregation tests**

Use one session with minute cumulative values:

```text
09:30 super=10 big=20 mid=30 small=40
09:31 super=13 big=18 mid=34 small=42
09:32 super=17 big=24 mid=32 small=47
```

The two usable deltas yield:

```text
mainActivity = |3|+|-2|+|4|+|6| = 15
retailActivity = |4|+|2|+|-2|+|5| = 13
mainShare = 15/28
retailShare = 13/28
```

Also assert the first cumulative point alone cannot create a bar, a zero denominator is missing, a bar with incomplete minute coverage is missing, and adding rows available after the cutoff cannot change a historical result because those rows are rejected.

- [ ] **Step 5: Implement deterministic differencing and K-line aggregation**

Use left-open/right-closed K-line assignment `(opened_at, closed_at]`. Reset the differencing baseline when `session` changes. Require every expected minute after the baseline for a supported intraday bar; set `coverage = observed_delta_count / expected_delta_count`. For `day` and `week`, return unavailable in V1 because OpenD supplies only one intraday cumulative-flow session.

- [ ] **Step 6: Run analysis tests and static checks**

```bash
PYTHONPATH=services/analysis_core python3 -m unittest discover -s services/analysis_core/tests -v
PYTHONPATH=services/analysis_core python3 -m mypy services/analysis_core/us_stock_helper_core
```

Expected: all tests pass; mypy reports no issues.

- [ ] **Step 7: Commit**

```bash
git add services/analysis_core/us_stock_helper_core services/analysis_core/tests/test_participation.py
git commit -m "feat: compute point-in-time capital participation"
```

---

### Task 2: Assemble one versioned real-market snapshot

**Files:**
- Modify: `services/market_gateway/pyproject.toml`
- Create: `services/market_gateway/src/us_stock_helper_market_gateway/snapshot.py`
- Modify: `services/market_gateway/src/us_stock_helper_market_gateway/service.py`
- Modify: `services/market_gateway/src/us_stock_helper_market_gateway/http_gateway.py`
- Modify: `services/market_gateway/tests/test_service.py`
- Modify: `services/market_gateway/tests/test_http_gateway.py`
- Create: `services/market_gateway/tests/test_snapshot.py`

**Interfaces:**
- Produce `MarketGatewayService.stock_snapshot(symbol, timeframe, count) -> dict[str, Any]`
- Expose `GET /stock-snapshot?symbol=NVDA&interval=5m&count=200`
- Return schema version `2`:

```json
{
  "schemaVersion": "2",
  "source": "moomoo",
  "sourceStatus": "live",
  "symbol": "NVDA",
  "interval": "5m",
  "decisionCutoff": "2026-07-25T16:00:00Z",
  "quote": {},
  "completedCandles": [],
  "participationBars": [],
  "indicators": {"ma5": {}, "rsi": {}, "macd": {}, "magicNine": {}},
  "institutionalHoldings": [],
  "provenance": [],
  "warnings": []
}
```

- [ ] **Step 1: Declare the analysis-core dependency**

Set gateway `requires-python = ">=3.11"` and add `us-stock-helper-analysis-core==0.1.0`. Development installs both local packages:

```bash
python3 -m pip install -e services/analysis_core -e services/market_gateway
```

- [ ] **Step 2: Write the failing snapshot assembler tests**

Extend `FakeProvider` so one call returns a quote, 20 completed 5-minute candles, cumulative capital-flow rows, and delayed holdings. Assert:

- one health check guards the operation;
- every child `availableAt <= decisionCutoff`;
- incomplete candles are absent;
- `participationBars[i].closedAt == completedCandles[i].timestamp`;
- MA5, Wilder RSI14, MACD 12/26/9, and Magic Nine use only returned completed closes;
- delayed holdings never set the whole snapshot to `live` ownership;
- capital-flow validation failure creates missing participation bars plus a warning, not fabricated numbers;
- provider errors are sanitized.

- [ ] **Step 3: Run the focused tests and observe RED**

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m unittest -v services.market_gateway.tests.test_snapshot
```

Expected: FAIL because `stock_snapshot` does not exist.

- [ ] **Step 4: Implement a single-cutoff snapshot assembler**

Add pure conversion helpers in `snapshot.py`:

```python
def assemble_stock_snapshot(
    *,
    symbol: str,
    interval: str,
    decision_cutoff: datetime,
    quote_items: list[dict[str, Any]],
    candle_items: list[dict[str, Any]],
    flow_items: list[dict[str, Any]],
    holding_items: list[dict[str, Any]],
) -> dict[str, Any]:
    ...
```

`MarketGatewayService.stock_snapshot` performs one health check, calls only the read-only provider methods, validates every `ProviderBatch.received_at`, normalizes the inputs, computes analytics, and marks each child with `source`, `asOf`, `availableAt`, `methodVersion`, and `qualityStatus`.

- [ ] **Step 5: Add the allowlisted HTTP route**

Add `/stock-snapshot` to `_PATHS`, parse the same symbol/interval/count constraints as `/candles`, and dispatch to `service.stock_snapshot`. Add a route test and keep `/trade/orders` and every write method rejected.

- [ ] **Step 6: Run gateway and analysis suites**

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m unittest discover -s services/market_gateway/tests -v
PYTHONPATH=services/analysis_core python3 -m unittest discover -s services/analysis_core/tests -v
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m mypy services/analysis_core/us_stock_helper_core services/market_gateway/src/us_stock_helper_market_gateway
```

Expected: all pass; no trading route or trade-context import appears.

- [ ] **Step 7: Audit the read-only boundary and commit**

```bash
rg -n "OpenSecTradeContext|unlock_trade|place_order|modify_order|cancel_order" services
```

Expected: no matches.

```bash
git add services/market_gateway services/analysis_core
git commit -m "feat: expose unified real market snapshot"
```

---

### Task 3: Validate the snapshot contract on the phone

**Files:**
- Modify: `apps/mobile/src/domain/models.ts`
- Modify: `apps/mobile/src/data/marketGateway.ts`
- Modify: `apps/mobile/src/data/__tests__/marketGateway.test.ts`
- Create: `apps/mobile/src/data/__tests__/stockSnapshot.fixture.ts`

**Interfaces:**
- Add `DataStatus = "live" | "delayed" | "stale" | "unavailable" | "demo"`
- Add `ParticipationBar` keyed by candle close timestamp
- Add `LiveStockSnapshot` with nullable real forecast and explicit source status
- Add `ChartSnapshot` as the minimal chart-facing shape shared by live and explicit demo data
- Produce `decodeStockSnapshotEnvelope(value, options): LiveStockSnapshot`
- Produce `client.getStockSnapshot(symbol, interval, count)`

- [ ] **Step 1: Write failing decoder tests**

Create a minimal valid schema-v2 object and assert exact decoding of:

- symbol/interval/request match;
- completed, strictly increasing candles;
- single decision cutoff;
- aligned participation timestamps;
- available shares in `[0,1]` and summing to 1;
- unavailable bars with null shares and a missing reason;
- RSI/MA5/MACD/Magic Nine timestamps no later than the cutoff;
- delayed holdings with report dates;
- provenance and warnings.

Reject future data, duplicate candles, misaligned bars, `institutionalIdentity=true`, invalid shares, unsupported method versions, fixture source in a live decoder, and stale responses.

- [ ] **Step 2: Run focused decoder tests and observe RED**

```bash
cd apps/mobile
npm test -- src/data/__tests__/marketGateway.test.ts
```

Expected: FAIL because the snapshot decoder and types do not exist.

- [ ] **Step 3: Add a live discriminated model without breaking explicit demo fixtures**

Keep the existing fixture `StockSnapshot` and its `demoData: true` discriminator. Add:

```ts
type SnapshotSource = {
  source: "moomoo" | "fixture";
  status: DataStatus;
  asOf: string;
  decisionCutoff: string;
};
```

`LiveStockSnapshot` has `demoData: false`, `forecast: ForecastSnapshot | null`, and only real fields supplied by schema v2. `ChartSnapshot` contains symbol, quote, completed candles, participation bars, indicators, Magic Nine, and optional forecast. Fixture adapters explicitly set `source="fixture"` and `status="demo"`; live snapshots use `source="moomoo"` and never inherit fixture conclusions, forecasts, fundamentals, or market context.

- [ ] **Step 4: Implement fail-closed schema-v2 decoding**

Reuse timestamp and finite-number validators. Require `methodVersion="order-size-activity-share-v1"` for present participation data. Derive no values in the client; it only verifies and converts the server response.

- [ ] **Step 5: Add the client call**

Call:

```text
/stock-snapshot?symbol={SYMBOL}&interval={INTERVAL}&count={COUNT}
```

`getStockSnapshot` throws a typed error for offline, login-required, permission, stale, malformed, or timeout states. It must not return a fixture fallback.

- [ ] **Step 6: Run mobile data tests and typecheck**

```bash
cd apps/mobile
npm test -- src/data/__tests__/marketGateway.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/domain/models.ts apps/mobile/src/data
git commit -m "feat: validate live stock snapshots on mobile"
```

---

### Task 4: Add explicit mobile market-data state

**Files:**
- Create: `apps/mobile/src/config/runtimeConfig.ts`
- Create: `apps/mobile/src/data/marketRepository.ts`
- Create: `apps/mobile/src/state/MarketDataProvider.tsx`
- Create: `apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx`
- Modify: `apps/mobile/src/app/_layout.tsx`
- Modify: `apps/mobile/src/screens/DashboardScreen.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Produce `useMarketWatchlist()`
- Produce `useStockSnapshot(symbol, interval, count)`
- Expose `{status, data, error, lastVerifiedAt, refresh}` where status is explicit
- Accept `EXPO_PUBLIC_MARKET_API_URL`; accept a development bearer token only when `__DEV__` is true

- [ ] **Step 1: Write failing provider tests**

Inject a fake repository and assert:

- loading becomes live after a valid response;
- refresh keeps the last verified snapshot but marks it stale on a later failure;
- first-load failure is unavailable;
- changing symbol cancels/ignores the old request;
- concurrent consumers share one in-flight request;
- production configuration rejects an embedded development token;
- no state path labels fixture data as live.

- [ ] **Step 2: Run the provider test and observe RED**

```bash
cd apps/mobile
npm test -- src/state/__tests__/MarketDataProvider.test.tsx
```

- [ ] **Step 3: Implement repository caching and request deduplication**

Cache by `{symbol, interval, count}` and retain the original `asOf`. Use an abort signal and an exponential retry schedule of 1, 2, 4, 8, then 30 seconds only while a mounted screen is waiting. Do not retry permission or validation failures indefinitely.

- [ ] **Step 4: Mount the provider once**

Place `MarketDataProvider` inside the root layout and outside routed screens. Keep journal/app preference state in `AppStateProvider`.

- [ ] **Step 5: Wire the dashboard watchlist**

Render moomoo watchlist rows when live. If unavailable, show one actionable state with the error category; if stale, keep rows with the original time and a stale badge. Keep a separate developer-only “演示模式” switch rather than an automatic fallback.

- [ ] **Step 6: Run focused and full mobile checks**

```bash
cd apps/mobile
npm test -- src/state/__tests__/MarketDataProvider.test.tsx src/screens/__tests__/DashboardScreen.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/config apps/mobile/src/data/marketRepository.ts apps/mobile/src/state apps/mobile/src/app/_layout.tsx apps/mobile/src/screens/DashboardScreen.tsx apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx
git commit -m "feat: manage explicit live market state"
```

---

### Task 5: Render per-candle 100% participation bars

**Files:**
- Modify: `apps/mobile/src/domain/chart.ts`
- Modify: `apps/mobile/src/domain/__tests__/chart.test.ts`
- Modify: `apps/mobile/src/components/chart/PriceChart.tsx`
- Create: `apps/mobile/src/components/chart/__tests__/PriceChart.test.tsx`
- Modify: `apps/mobile/src/components/chart/ChartLegend.tsx`

**Interfaces:**
- Extend `buildChartGeometry(candles, forecastOrNull, participationBars, width, height)`
- Add `ParticipationGeometry(timestamp, x, width, top, height, mainHeight, retailHeight, available)`
- Preserve identical `x` and `width` for each candle and its participation bar

- [ ] **Step 1: Write failing geometry invariants**

Assert:

- every completed candle has exactly one aligned participation geometry row;
- every available bar has constant total height;
- `mainHeight + retailHeight == totalHeight`;
- main/retail share changes segment sizes but not total bar height;
- missing data produces an outlined empty slot, not a zero or inferred share;
- bars after the decision cutoff are rejected;
- candle order cannot be changed by participation input.

- [ ] **Step 2: Run geometry tests and observe RED**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/chart.test.ts
```

- [ ] **Step 3: Reserve a dedicated histogram lane**

Use the approved hierarchy: price area, volume lane, then one compact fixed-height participation lane. Keep the same x scale and body width as each candle. Dark navy is main-force proxy; blue-gray is retail proxy. Do not add a zero line or encode inflow/outflow direction.

- [ ] **Step 4: Render accessible stacked bars**

Render two stacked `Rect` elements inside each available slot and an outlined slot for missing data. Add a legend reading `订单规模活动占比 · 深色主力代理 / 浅色散户代理`. Provide an accessibility label containing exact percentages, coverage, source, bar close, and “非真实机构身份”.

- [ ] **Step 5: Add interaction without blocking the chart**

A press/long-press on the chart sets the selected candle and displays a native detail strip below the SVG. The strip shows OHLCV, main/retail shares, coverage, source, close time, and missing reason. It never claims account identity.

- [ ] **Step 6: Run component, geometry, and accessibility tests**

```bash
cd apps/mobile
npm test -- src/domain/__tests__/chart.test.ts src/components/chart/__tests__/PriceChart.test.tsx
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/domain/chart.ts apps/mobile/src/domain/__tests__/chart.test.ts apps/mobile/src/components/chart
git commit -m "feat: align capital participation with each candle"
```

---

### Task 6: Replace stock-page fixtures with the live snapshot

**Files:**
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Modify: `apps/mobile/src/screens/FullChartScreen.tsx`
- Modify: `apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx`
- Create: `apps/mobile/src/screens/__tests__/FullChartScreen.test.tsx`
- Modify: `apps/mobile/src/components/stock/StockHeader.tsx`
- Modify: `apps/mobile/src/components/stock/IndicatorStrip.tsx`
- Modify: `apps/mobile/src/components/stock/ParticipationCard.tsx`

**Interfaces:**
- Stock pages consume `useStockSnapshot(symbol, "5m", 200)`
- Live page displays only fields returned by the real snapshot
- Adviser, forecast, fundamentals, and market-context cards remain disabled with an explicit “尚未接入真实分析” state until their real services arrive

- [ ] **Step 1: Rewrite the screen contracts as failing live-data tests**

Inject a live repository and assert one NVDA row only, a `实时只读` source badge, real price/as-of time, K-lines, MA5, RSI, MACD, Magic Nine, participation legend, missing-bar behavior, and delayed holdings. Assert the page contains neither `DEMO` nor fixture forecast/conclusion text.

Inject unavailable and stale repositories and assert clear status UI without a render error.

- [ ] **Step 2: Run the screen tests and observe RED**

```bash
cd apps/mobile
npm test -- src/screens/__tests__/StockDetailScreen.test.tsx src/screens/__tests__/FullChartScreen.test.tsx
```

- [ ] **Step 3: Compose the real compact screen**

Keep the approved visual order and toolbar. Replace fixture score/conclusion with a factual real-data summary: quote, latest completed-bar state, indicator states, and source freshness. Hide forecast controls until a real forecast is present.

- [ ] **Step 4: Compose the real full chart**

Show the same snapshot and selection state in the full chart, always render RSI/MACD, and label delayed institutional disclosures separately from the activity histogram.

- [ ] **Step 5: Preserve explicit demo mode**

When runtime config explicitly selects demo mode, use the fixture repository and display `演示数据 · 非实时行情` across the screen. Do not enter demo mode as a network fallback.

- [ ] **Step 6: Run all mobile checks**

```bash
cd apps/mobile
npm test -- --runInBand
npm run typecheck
npm run lint
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/mobile/src/screens apps/mobile/src/components/stock
git commit -m "feat: show real moomoo stock analysis"
```

---

### Task 7: Prove the slice with OpenD and a physical iPhone

**Files:**
- Create: `services/market_gateway/scripts/smoke_real_snapshot.py`
- Create: `services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json`
- Create: `docs/runbooks/local-real-market.md`
- Modify: `.gitignore`

**Interfaces:**
- `smoke_real_snapshot.py --symbol NVDA --interval 5m --count 200 --base-url http://127.0.0.1:8765`
- Exit non-zero on unhealthy OpenD, no completed candles, future data, invalid shares, misalignment, or accidental trading surface

- [ ] **Step 1: Write the smoke validator against a deterministic redacted replay**

The checked-in replay contains no account ID, login data, private watchlist, cookie, bearer token, or trade data. It preserves timestamps and numeric market rows required to reproduce the invariants.

- [ ] **Step 2: Run the offline replay**

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 services/market_gateway/scripts/smoke_real_snapshot.py --fixture services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json
```

Expected: `PASS snapshot=NVDA candles>0 valid_participation>0 future_rows=0`.

- [ ] **Step 3: Start the latest loopback gateway and run the live smoke**

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m us_stock_helper_market_gateway
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 services/market_gateway/scripts/smoke_real_snapshot.py --symbol NVDA --interval 5m --count 200 --base-url http://127.0.0.1:8765
```

Expected: health is healthy; real completed candles and at least the currently covered trading-day participation bars pass. Older candles may be explicitly unavailable.

- [ ] **Step 4: Document local iPhone runtime**

The runbook states:

1. OpenD must be logged into the Singapore account with US quote permission.
2. Gateway LAN mode uses a fresh 32-byte token and explicit phone subnet.
3. Metro uses `npm run start:dev-client`.
4. The phone and Mac share a reachable network.
5. `EXPO_PUBLIC_MARKET_API_URL` points to the Mac LAN IP.
6. The temporary LAN token is development-only and must never be used in a release build.

- [ ] **Step 5: Verify on the physical iPhone**

Acceptance:

- dashboard watchlist matches moomoo;
- NVDA opens once, without duplicate rows or render errors;
- actual completed K-lines appear;
- supported K-lines have aligned constant-height stacked bars;
- each available bar sums to 100%;
- unsupported older bars are visibly missing;
- RSI, MACD, MA5, and Magic Nine use the same decision cutoff;
- OpenD stop/restart changes unavailable → live without crashing;
- no forecast or fixture conclusion appears on a live screen.

- [ ] **Step 6: Run final repository checks**

```bash
PYTHONPATH=services/analysis_core python3 -m unittest discover -s services/analysis_core/tests -v
PYTHONPATH=services/analysis_core:services/market_gateway/src python3 -m unittest discover -s services/market_gateway/tests -v
cd apps/mobile && npm test -- --runInBand && npm run typecheck && npm run lint
rg -n "OpenSecTradeContext|unlock_trade|place_order|modify_order|cancel_order" services apps/mobile
```

Expected: all tests/checks pass and the final `rg` has no matches.

- [ ] **Step 7: Commit**

```bash
git add services/market_gateway/scripts services/market_gateway/tests/fixtures docs/runbooks/local-real-market.md .gitignore
git commit -m "test: prove the real market mobile slice"
```
