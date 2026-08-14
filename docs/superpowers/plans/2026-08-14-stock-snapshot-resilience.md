# Stock Snapshot Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make every Watchlist stock open with usable daily price analysis even when optional institutional-holdings or capital-flow data is anomalous, while migrating new clients to the sectioned v3 snapshot contract without breaking legacy v2 clients.

**Architecture:** The analysis API reads completed daily candles from the dedicated v1 candles endpoint and no longer depends on the all-in-one stock snapshot. Its deterministic price basis remains the latest completed daily close; the independent live quote is reserved for Watchlist display and current-session flow, so an intraday quote cannot silently change a daily score. The market gateway keeps the existing unversioned/v2 encoder, adds a separately routed v3 sectioned encoder with independent provider failures, and the mobile client prefers v3 with a narrowly defined 404/426 compatibility fallback. Existing chart consumers receive a flattened view of usable v3 sections plus explicit section metadata, so a missing optional section cannot blank the whole screen.

**Tech Stack:** Python 3.11+ standard library, unittest, ThreadingHTTPServer, Expo SDK 57, React Native 0.86, TypeScript 6, Jest Expo, React Native Testing Library.

## Global Constraints

- Existing /stock-snapshot and /v2/stock-snapshot serve schemaVersion "2"; /v3/stock-snapshot serves only schemaVersion "3".
- A v3 mobile request falls back to the existing /stock-snapshot route only for HTTP 404 or 426. It never falls back after authentication, provider, timeout, decode, validation, or unknown-version errors.
- Quote and completed candles are independent minimum price sections. The whole page is unavailable only when neither section is usable or top-level request identity/cutoff metadata is invalid.
- V3 echoes the validated request parameter `count` at the top level. The mobile client rejects a response whose count differs from its request.
- Slice 1 requests exactly quote, candles, technical, currentSessionFlow, and holdings. All nine section keys are emitted, but fundamentals, marketContext, news, and forecastDecision are explicitly unrequested and do not affect top-level status.
- Institutional holding percentages above 100 are preserved, marked anomalous, and accompanied by: “供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释”. They are never clamped or used as a normalized ownership score.
- NaN, infinity, negative values, malformed periods, wrong sources, and future timestamps are excluded at row/section scope; genuine top-level point-in-time violations still fail closed.
- Automatic deterministic analysis uses completed daily candles by default. Selecting a five-minute chart never changes the decision interval.
- Deterministic currentPrice is the latest completed daily close in this slice. A current intraday quote may be shown separately but is never mixed into daily indicator or forecast inputs.
- Every section carries availabilityStatus, qualityStatus, source, asOf, availableAt, receivedAt, data, errorCode, reason, warnings, anomalies, and methodVersion.
- Per-source timeout is five seconds, stock-snapshot deadline is twelve seconds, and provider concurrency is at most four.
- No fixture data may appear in Real mode. No normal Watchlist, dashboard, stock-detail, or decision request invokes Claude.
- Keep the product read-only. Do not add broker, account, order, position, or trading-credential paths.
- Do not print or commit market tokens, device tokens, Anthropic credentials, local .env contents, or raw provider error text.
- Use TDD for every behavior change: write the test, run it and observe the expected failure, implement the minimum behavior, rerun the focused suite, then commit.

## Baseline Evidence

- Mobile: 712 tests pass and TypeScript typecheck passes.
- Backend: analysis_core 136, information_layer 221, adviser_layer 9, decision_engine 14, market_gateway 113, analysis_api 135, device_auth 98, and adviser_llm 114 tests pass when each package is run from its supported test boundary.
- Mobile lint has one pre-existing react-hooks/set-state-in-effect error in apps/mobile/src/state/DeviceSessionProvider.tsx. This plan must not claim full-repository lint green; the durable-runtime plan owns that pairing/runtime cleanup.
- Live audit: CRCL, AVGO, GRRR, SMTC, LULU, PTON, ETSY, and GPCR have valid quotes and 249 completed daily candles but fail because holdingPercent exceeds 100.

---

### Task 1: Decouple deterministic analysis from the all-in-one snapshot

**Files:**
- Modify: services/analysis_api/src/us_stock_helper_analysis_api/gateway_provider.py
- Modify: services/analysis_api/tests/test_gateway_provider.py
- Modify: services/analysis_api/tests/test_analysis_service.py
- Modify: services/analysis_api/tests/test_http_app.py
- Modify: services/analysis_api/README.md

**Interfaces:**
- Consumes: GET /candles?symbol={symbol}&interval={interval}&count={count}, schemaVersion "1"
- Produces: MarketGatewayProvider.bars_for(symbol: str, interval: str) -> tuple[OHLCVBar, ...]
- Preserves: MarketGatewayUnavailable as the single public failure type
- Preserves: AnalysisService current_price=bars[-1].close and current_price_available_at=bars[-1].available_at. This is the completed-daily decision basis; do not fetch /quotes or substitute an intraday quote in this task.

- [ ] **Step 1: Replace the test fixture with the real candles envelope and assert the requested route**

Add a complete literal helper in test_gateway_provider.py:

~~~python
def candle_envelope(
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "1",
        "source": "moomoo",
        "session": "healthy",
        "asOf": "2026-07-25T16:00:00Z",
        "availableAt": "2026-07-25T16:00:00Z",
        "symbol": "NVDA",
        "interval": "5m",
        "items": [candle()] if items is None else items,
    }
    payload.update(overrides)
    return payload
~~~

Change the route assertion to the literal expected URL:

~~~python
self.assertEqual(
    gateway.urls,
    ["http://127.0.0.1:8765/candles?symbol=NVDA&interval=5m&count=200"],
)
~~~

Add cases proving a non-healthy v1 error envelope raises, a genuinely empty healthy items list returns an empty tuple, and missing availableAt/receivedAt remains a loud point-in-time failure.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

~~~bash
PYTHONPATH="$PWD/services/analysis_api/src:$PWD/services/analysis_api/tests:$PWD/services/analysis_core:$PWD/services/information_layer:$PWD/services/adviser_layer:$PWD/services/decision_engine:$PWD/services/device_auth/src:$PWD/services/adviser_llm/src" \
  /opt/homebrew/anaconda3/bin/python3 -m unittest \
  services.analysis_api.tests.test_gateway_provider -v
~~~

Expected: FAIL because production still requests /stock-snapshot and reads completedCandles/decisionCutoff instead of items/asOf.

- [ ] **Step 3: Implement the dedicated candles reader**

In gateway_provider.py replace SNAPSHOT_PATH and _snapshot with:

~~~python
CANDLES_PATH = "/candles"

def _candles(self, symbol: str, interval: str) -> dict[str, Any]:
    query = urlencode(
        {"symbol": symbol, "interval": interval, "count": self.count}
    )
    payload = self._read_json(f"{self.base_url}{CANDLES_PATH}?{query}")
    if payload.get("schemaVersion") != "1":
        raise MarketGatewayUnavailable(
            "the market gateway returned an unsupported candle contract"
        )
    if payload.get("source") != "moomoo":
        raise MarketGatewayUnavailable(
            "the market gateway returned an unknown candle source"
        )
    if payload.get("session") != "healthy":
        failure = payload.get("error")
        code = failure.get("code") if isinstance(failure, dict) else None
        raise MarketGatewayUnavailable(
            f"the market gateway reported {code or 'an error'}"
        )
    return payload
~~~

Have bars_for validate payload symbol/interval, use _timestamp(payload, "asOf") as the cutoff, and read payload["items"]. Keep _bar and ordering validation unchanged. Extract only the existing JSON/transport checks into _read_json; do not add retries or fallback to v2.

- [ ] **Step 4: Add the integration regression**

In test_analysis_service.py and test_http_app.py use a provider whose bars_for returns valid completed daily bars while an unrelated stock-snapshot/holdings fake would raise. Assert:

~~~python
self.assertEqual(result["status"], "live")
self.assertEqual(result["interval"], "day")
self.assertIsInstance(result["score"]["value"], float)
~~~

The HTTP result must be 200, not ANALYSIS_FAILED. The test must exercise AnalysisService and AnalysisApplication, not assert on a mock call count.

- [ ] **Step 5: Run all analysis API tests and verify GREEN**

Run:

~~~bash
PYTHONPATH="$PWD/services/analysis_api/src:$PWD/services/analysis_api/tests:$PWD/services/analysis_core:$PWD/services/information_layer:$PWD/services/adviser_layer:$PWD/services/decision_engine:$PWD/services/device_auth/src:$PWD/services/adviser_llm/src" \
  /opt/homebrew/anaconda3/bin/python3 -m unittest discover \
  -s services/analysis_api/tests -v
~~~

Expected: 135 or more tests, all OK.

- [ ] **Step 6: Update the analysis API contract and commit**

Update README.md so completed daily candles come from /candles, optional snapshot sections cannot affect a decision, and deterministic currentPrice intentionally remains the latest completed daily close. State that live quotes are a separate Watchlist/current-session input and never change the daily analysis interval.

~~~bash
git add services/analysis_api
git commit -m "fix: decouple analysis candles from stock snapshots"
git push origin feature/iphone-demo
~~~

---

### Task 2: Build the pure v3 section and holdings contracts

**Files:**
- Create: services/market_gateway/src/us_stock_helper_market_gateway/snapshot_v3.py
- Create: services/market_gateway/tests/test_snapshot_v3.py

**Interfaces:**
- Produces: SnapshotSection dataclass and section_payload(section: SnapshotSection) -> dict[str, Any]
- Produces: normalize_holdings_v3(items: list[dict[str, Any]], cutoff: datetime, received_at: datetime) -> SnapshotSection
- Produces: assemble_stock_snapshot_v3(symbol: str, interval: str, count: int, decision_cutoff: datetime, sections: Mapping[str, SnapshotSection]) -> dict[str, Any]

- [ ] **Step 1: Write the failing section-contract tests**

Define a literal anomalous holdings row with holding_percent 345.937 and assert:

~~~python
section = normalize_holdings_v3(
    [holding_row(holding_percent=345.937)],
    CUTOFF,
    CUTOFF - timedelta(seconds=1),
)

self.assertEqual(section.availability_status, "delayed")
self.assertEqual(section.quality_status, "anomalous")
self.assertEqual(section.data[0]["holdingPercent"], 345.937)
self.assertEqual(
    section.warnings,
    (
        "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
    ),
)
~~~

Add table-driven cases for CRCL, AVGO, GRRR, SMTC, LULU, PTON, ETSY, and GPCR using hand-written percentages above 100. Add cases that exclude one missing-field, negative, NaN/infinite, future, wrong-source, malformed-period, or out-of-order row while preserving a valid sibling row. Assert every excluded row creates the exact anomaly below and never becomes data. The provider period grammar is exactly `^\d{4}/Q[1-4]$`, matching values such as `2026/Q1`; a merely non-empty string is not sufficient.

Use this fixed code/reason table; never put an exception or provider message in an anomaly:

| code | reason |
|---|---|
| `MISSING_REQUIRED_FIELD` | `机构持仓记录缺少必填字段` |
| `INVALID_REPORTING_PERIOD` | `机构持仓报告期格式无效` |
| `INVALID_NUMERIC_VALUE` | `机构持仓数值无效` |
| `WRONG_HOLDINGS_SOURCE` | `机构持仓来源无效` |
| `FUTURE_HOLDINGS_ROW` | `机构持仓记录晚于决策截止时间` |
| `OUT_OF_ORDER_HOLDINGS_ROW` | `机构持仓记录顺序无效` |

A retained row whose holding_percent is above 100 adds `AGGREGATE_PERCENT_ABOVE_100` with the same fixed reason as the required warning. Unlike the six rejection codes, that anomaly does not exclude the row.

For holdings only, a future row is excluded with `FUTURE_HOLDINGS_ROW`; it does not invalidate valid sibling rows. If at least one valid sibling remains, the section is `availabilityStatus: "delayed"`, `qualityStatus: "anomalous"`. If no row remains, it is `availabilityStatus: "unavailable"`, `qualityStatus: "invalid"`, with the anomaly list preserved. Quote, candle, and current-session-flow future values follow the source-level rule in Task 3 and invalidate their whole section.

Add top-level tests:

~~~python
payload = assemble_stock_snapshot_v3(
    symbol="AVGO",
    interval="day",
    count=200,
    decision_cutoff=CUTOFF,
    sections=sections_with_valid_candles_and_anomalous_holdings(),
)
self.assertEqual(payload["schemaVersion"], "3")
self.assertEqual(payload["status"], "partial")
self.assertEqual(payload["sections"]["candles"]["qualityStatus"], "validated")
self.assertEqual(payload["sections"]["holdings"]["qualityStatus"], "anomalous")
~~~

Quote-only and candles-only snapshots are partial and usable. With neither price section they are unavailable.

Assert the payload echoes `count: 200`; non-integer/out-of-range count is rejected before assembly. Add a validated candles envelope whose data contains an empty candles array and assert it does not satisfy the minimum price condition.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  /opt/homebrew/anaconda3/bin/python3 -m unittest \
  services.market_gateway.tests.test_snapshot_v3 -v
~~~

Expected: import failure because snapshot_v3 does not exist.

- [ ] **Step 3: Implement the section model**

Create:

~~~python
@dataclass(frozen=True, slots=True)
class SnapshotSection:
    availability_status: Literal["live", "delayed", "stale", "unavailable"]
    quality_status: Literal["validated", "partial", "anomalous", "invalid"]
    source: str | None
    as_of: datetime | None
    available_at: datetime | None
    received_at: datetime | None
    data: Any
    error_code: str | None
    reason: str | None
    warnings: tuple[str, ...] = ()
    anomalies: tuple[dict[str, Any], ...] = ()
    method_version: str = "unavailable-v1"
~~~

section_payload must emit all twelve section-envelope keys even when unavailable. It converts UTC timestamps with iso_z and never serializes an exception or raw provider message.

- [ ] **Step 4: Implement independent v3 holdings normalization**

normalize_holdings_v3 validates each row separately. Require `reported_at <= available_at <= received_at <= cutoff`, the exact provider source, the exact period grammar, finite numeric values, non-negative institution_count/shares_held/holding_percent, and newest-to-oldest available_at ordering. Signed change fields remain allowed but must be finite. Finite non-negative aggregate percentages above 100 are kept and marked anomalous. Invalid rows produce:

~~~python
{
    "rowIndex": index,
    "code": one_of_the_fixed_codes_above,
    "reason": the_corresponding_fixed_chinese_reason,
}
~~~

Do not call the v2 _normalize_institutional_holdings and do not change its output. The v3 method version is reported-holdings-v2-anomaly-aware.

- [ ] **Step 5: Implement top-level assembly**

The sections mapping has these exact keys:

~~~python
SECTION_NAMES = (
    "quote",
    "candles",
    "technical",
    "currentSessionFlow",
    "holdings",
    "fundamentals",
    "marketContext",
    "news",
    "forecastDecision",
)

REQUESTED_SECTIONS = (
    "quote",
    "candles",
    "technical",
    "currentSessionFlow",
    "holdings",
)
~~~

Emit `requestedSections` at the top level with exactly `REQUESTED_SECTIONS`. Missing sections become explicit unavailable envelopes. The four unrequested Slice-2 sections — fundamentals, marketContext, news, and forecastDecision — use `errorCode: "NOT_REQUESTED"`, `reason: "此切片未请求该数据"`; they never affect status.

Use this exact status algorithm:

1. invalid symbol/interval/decisionCutoff is a top-level request error and is not assembled;
2. quote is usable only when its section has `availabilityStatus` live/delayed, `qualityStatus` validated, and a non-null finite positive quote price;
3. candles are usable only when their section has `availabilityStatus` live/delayed, `qualityStatus` validated, and `data.candles` contains at least one fully validated completed candle; an empty validated array is not usable;
4. if neither price predicate is true, status is unavailable;
5. otherwise status is live only when every requested section has availability live/delayed and quality validated;
6. otherwise status is partial. An anomalous but displayable holdings section therefore makes the top level partial.

Add a RED test proving all requested sections validated yields live even though every unrequested section is unavailable/NOT_REQUESTED. Add a separate test proving anomalous requested holdings yields partial without discarding price.

- [ ] **Step 6: Verify and commit**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  /opt/homebrew/anaconda3/bin/python3 -m unittest \
  services.market_gateway.tests.test_snapshot_v3 \
  services.market_gateway.tests.test_snapshot \
  services.market_gateway.tests.test_service -v
~~~

Expected: all tests OK and existing v2 tests unchanged.

~~~bash
git add services/market_gateway/src/us_stock_helper_market_gateway/snapshot_v3.py \
  services/market_gateway/tests/test_snapshot_v3.py
git commit -m "feat: add sectioned stock snapshot v3 contract"
git push origin feature/iphone-demo
~~~

---

### Task 3: Collect v3 sections independently and expose explicit routes

**Files:**
- Modify: services/market_gateway/src/us_stock_helper_market_gateway/service.py
- Modify: services/market_gateway/src/us_stock_helper_market_gateway/http_gateway.py
- Modify: services/market_gateway/tests/test_service.py
- Modify: services/market_gateway/tests/test_http_gateway.py
- Modify: services/market_gateway/tests/test_snapshot_v3.py

**Interfaces:**
- Produces: MarketGatewayService.stock_snapshot_v3(symbol: str, timeframe: str, count: int) -> dict[str, Any]
- Routes: /stock-snapshot and /v2/stock-snapshot -> stock_snapshot; /v3/stock-snapshot -> stock_snapshot_v3
- Extends: MarketGatewayService.__init__ with injected monotonic clock, source timeout, snapshot deadline, and executor factory for deterministic deadline tests

- [ ] **Step 1: Write route-selection tests**

Extend StubService with stock_snapshot_v3 returning schemaVersion "3". Assert the exact matrix:

~~~python
for path, expected_version in (
    ("/stock-snapshot", "2"),
    ("/v2/stock-snapshot", "2"),
    ("/v3/stock-snapshot", "3"),
):
    status, _, body = self.app.handle(
        "GET",
        path,
        {"symbol": ["NVDA"], "interval": ["day"], "count": ["200"]},
        {},
        "127.0.0.1",
    )
    self.assertEqual(status, 200)
    self.assertEqual(body["schemaVersion"], expected_version)
~~~

Assert POST remains 405 and unknown versioned routes remain PATH_NOT_ALLOWED.

- [ ] **Step 2: Write partial-failure and deadline tests**

Use a provider fake with independently injectable quote, candles, flow, and holdings behaviors. Cover exception, five-second timeout, malformed data, stale data, and future data for each input. For quote, candles, and flow, a future value invalidates that whole source section. Holdings are the deliberate exception from Design §5: normalize rows independently, exclude each future row with `FUTURE_HOLDINGS_ROW`, preserve valid siblings, and invalidate the holdings section only when none remain. For every case assert unrelated validated price data remains.

Use an injected executor/clock so tests do not sleep. Assert no more than four provider operations are submitted and a twelve-second overall deadline stops waiting. Invalid request symbol/interval/count fails before health/provider calls. An invalid top-level cutoff is never assembled.

- [ ] **Step 3: Run and verify RED**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  /opt/homebrew/anaconda3/bin/python3 -m unittest \
  services.market_gateway.tests.test_http_gateway \
  services.market_gateway.tests.test_service \
  services.market_gateway.tests.test_snapshot_v3 -v
~~~

Expected: FAIL because the versioned routes and stock_snapshot_v3 do not exist.

- [ ] **Step 4: Implement bounded independent collection**

Add source constants:

~~~python
SNAPSHOT_SOURCE_TIMEOUT_SECONDS = 5.0
SNAPSHOT_DEADLINE_SECONDS = 12.0
SNAPSHOT_MAX_PROVIDER_OPERATIONS = 4
~~~

Extend the constructor with defaults equivalent to:

~~~python
monotonic: Callable[[], float] = time.monotonic
source_timeout_seconds: float = SNAPSHOT_SOURCE_TIMEOUT_SECONDS
snapshot_deadline_seconds: float = SNAPSHOT_DEADLINE_SECONDS
executor_factory: Callable[[int], Executor] = ThreadPoolExecutor
~~~

stock_snapshot_v3 validates identity first, checks health once, records requestedAt, and submits quote, candles, capital_flow, and institutional_holdings as four separate operations. Each operation gets at most five seconds from its own submission and the entire collector gets at most twelve seconds from requestedAt; the smaller remaining limit governs every wait. Each completed future is validated and normalized into its own SnapshotSection. A failed optional future never enters _snapshot_error and its exception text is never serialized. Use the injected monotonic clock for elapsed deadlines. In a finally block cancel unfinished futures and call executor.shutdown(wait=False, cancel_futures=True).

Derive technical indicators only from a validated, non-empty candle section. If candles are unavailable or empty, technical is unavailable with `CANDLES_UNAVAILABLE`. Convert the validated normalized capital-flow rows directly to currentSessionFlow with `institutionalIdentity: false` and `methodVersion: "provider-capital-flow-normalized-v1"`; never pass them through candle-aligned v2 participation logic, and keep this section usable when candles fail. If flow cannot be validated, use `CURRENT_SESSION_FLOW_UNAVAILABLE`. Pass holdings batch `received_at` into the row-aware Task-2 normalizer. Create the four unrequested section envelopes with `NOT_REQUESTED`, then pass the validated request count into the pure assembler from Task 2 for every response.

A structurally valid v3 snapshot with `status: "unavailable"` is still HTTP 200 and carries no top-level `error`; its section errorCodes explain the missing price inputs and let the mobile decoder produce `GatewaySnapshotUnavailableError`. Only invalid request/auth/path/method and other request-boundary failures are non-2xx. Add an HTTP integration RED test proving a no-price v3 payload is HTTP 200/status unavailable/no top-level error, while an invalid count remains HTTP 400.

- [ ] **Step 5: Register the three routes**

Add /v2/stock-snapshot and /v3/stock-snapshot to the GET allowlist. Dispatch the exact path to stock_snapshot or stock_snapshot_v3; do not inspect Accept headers or body schema to guess a version.

- [ ] **Step 6: Verify gateway regression suite and commit**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  /opt/homebrew/anaconda3/bin/python3 -m unittest discover \
  -s services/market_gateway/tests -v
~~~

Expected: 113 or more tests, all OK.

~~~bash
git add services/market_gateway/src/us_stock_helper_market_gateway/service.py \
  services/market_gateway/src/us_stock_helper_market_gateway/http_gateway.py \
  services/market_gateway/tests
git commit -m "feat: serve independently collected snapshot v3 sections"
git push origin feature/iphone-demo
~~~

---

### Task 4: Decode v3 on mobile with strict compatibility fallback

**Files:**
- Modify: apps/mobile/src/domain/models.ts
- Modify: apps/mobile/src/data/marketGateway.ts
- Modify: apps/mobile/src/data/marketRepository.ts
- Modify: apps/mobile/src/i18n/marketErrorCopy.ts
- Modify: apps/mobile/src/state/MarketDataProvider.tsx
- Create: apps/mobile/src/data/__tests__/stockSnapshotV3.fixture.ts
- Modify: apps/mobile/src/data/__tests__/marketGateway.test.ts
- Modify: apps/mobile/src/data/__tests__/marketRepository.test.ts
- Modify: apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx

**Interfaces:**
- Produces: SnapshotSection<T>, SnapshotAvailability, SnapshotQuality, SnapshotCompatibility
- Produces: decodeStockSnapshotV3Envelope(value: unknown, options?: DecodeOptions) -> LiveStockSnapshot
- Preserves: decodeStockSnapshotEnvelope as the v2-only decoder
- Produces: usable LiveStockSnapshot.snapshotStatus/source.status = "live" | "partial", compatibility = "v3" | "v2-fallback", requestedCount, requestedSections, and sections
- Extends: GatewayRequestErrorKind and MarketDataErrorCategory with "client-update-required" for a syntactically valid unknown major schema

- [ ] **Step 1: Add client-domain section types**

Add:

~~~typescript
export type SnapshotAvailability =
  | "live"
  | "delayed"
  | "stale"
  | "unavailable";

export type SnapshotQuality =
  | "validated"
  | "partial"
  | "anomalous"
  | "invalid";

export interface SnapshotSection<T> {
  availabilityStatus: SnapshotAvailability;
  qualityStatus: SnapshotQuality;
  source: string | null;
  asOf: string | null;
  availableAt: string | null;
  receivedAt: string | null;
  data: T | null;
  errorCode: string | null;
  reason: string | null;
  warnings: string[];
  anomalies: { code: string; reason: string; rowIndex?: number }[];
  methodVersion: string;
}
~~~

Add exact section names/types:

~~~typescript
export type SnapshotSectionName =
  | "quote" | "candles" | "technical" | "currentSessionFlow"
  | "holdings" | "fundamentals" | "marketContext" | "news"
  | "forecastDecision";

export interface StockSnapshotSections {
  quote: SnapshotSection<LiveQuote>;
  candles: SnapshotSection<{ candles: Candle[]; priceAdjustment: PriceAdjustment }>;
  technical: SnapshotSection<{
    indicators: LiveTechnicalIndicators;
    magicNine: MagicNineSnapshot;
  }>;
  currentSessionFlow: SnapshotSection<NormalizedCapitalFlowPoint[]>;
  holdings: SnapshotSection<DelayedInstitutionalHolding[]>;
  fundamentals: SnapshotSection<unknown>;
  marketContext: SnapshotSection<unknown>;
  news: SnapshotSection<unknown>;
  forecastDecision: SnapshotSection<unknown>;
}

export interface NormalizedCapitalFlowPoint {
  timestamp: string;
  availableAt: string;
  session: string;
  totalNetFlow: number;
  extraLargeOrderNetFlow: number;
  largeOrderNetFlow: number;
  mediumOrderNetFlow: number;
  smallOrderNetFlow: number;
  largeOrderProxyNetFlow: number;
  institutionalIdentity: false;
}
~~~

Extend LiveStockSnapshot with required `snapshotStatus: "live" | "partial"`, `compatibility`, `requestedCount: number`, `requestedSections: SnapshotSectionName[]`, and `sections: StockSnapshotSections`. Change `source.status` from the fixed `"live"` to `"live" | "partial"`. Keep its flattened quote/candles/indicators/holdings fields so existing chart components do not need a parallel model.

To represent the contract's candles-only minimum honestly, change `ChartSnapshot.quote` and `LiveStockSnapshot.quote` to `LiveQuote | null`, and change `LiveStockSnapshot.priceAdjustment` to `PriceAdjustment | null`. Keep `DemoChartSnapshot.quote` narrowed to its existing non-null fixture quote. Extract the current live-indicators object to a named `LiveTechnicalIndicators` interface so `StockSnapshotSections.technical` does not refer recursively through `LiveStockSnapshot`. A quote-only response has null priceAdjustment and empty candles; a candles-only response has null quote. Neither decoder synthesizes the missing price source.

The v3 top-level status `unavailable` is not a usable LiveStockSnapshot. `decodeStockSnapshotV3Envelope` throws `GatewaySnapshotUnavailableError` after validating its section envelopes; the repository/screen uses that typed error for the existing full-page unavailable state. The decoder never fabricates a quote to satisfy the flattened model.

- [ ] **Step 2: Create literal v3 fixtures and failing decoder tests**

The fixture must include all section keys and complete envelopes. Add tests for:

- valid v3 with holdings 345.937 and anomalous quality;
- quote-only and candles-only partial snapshots;
- direct normalized currentSessionFlow rows remain identical across day/5m fixtures and reject `institutionalIdentity: true`, future timestamps, or a wrong methodVersion;
- one invalid optional section without losing price;
- v2 body delivered on the v3 decoder;
- v3 body delivered on the v2 decoder;
- unknown schemaVersion "4";
- top-level unavailable with neither usable quote nor candles, which throws GatewaySnapshotUnavailableError;
- count echo mismatch against the client request;
- missing envelope fields, future timestamps, and inconsistent quality/data.

Expected holding assertion:

~~~typescript
expect(snapshot.institutionalHoldings[0]?.holdingPercent).toBe(345.937);
expect(snapshot.sections.holdings.qualityStatus).toBe("anomalous");
expect(snapshot.warnings).toContain(
  "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
);
~~~

- [ ] **Step 3: Write failing request/fallback tests**

Use the real client with a fetch fake returning controlled Response objects. Assert:

~~~typescript
expect(requestedPaths).toEqual([
  "/v3/stock-snapshot?symbol=NVDA&interval=day&count=200",
]);
~~~

For 404 and 426, assert the second path is /stock-snapshot and compatibility is v2-fallback. For 401, 403, 500, timeout, malformed v3, and schemaVersion "4", assert there is exactly one request and no fallback. Unknown version must map to the new `GatewayRequestErrorKind` value `client-update-required`, then the same `MarketDataErrorCategory`, not validation/malformed-provider-data. Assert `marketErrorCopy` contains closed Chinese copy instructing the reader to update the App and gateway together.

- [ ] **Step 4: Run and verify RED**

Run:

~~~bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand \
  src/data/__tests__/marketGateway.test.ts \
  src/data/__tests__/marketRepository.test.ts \
  src/state/__tests__/MarketDataProvider.test.tsx
~~~

Expected: FAIL because v3 types, decoder, path, and fallback are absent.

- [ ] **Step 5: Implement strict v3 decoding**

Decode top-level symbol/interval/count/decisionCutoff/status/requestedSections before sections. Expose count as required `LiveStockSnapshot.requestedCount`; after decoding, `getStockSnapshot` rejects a count that differs from the request just as it rejects symbol/interval mismatch. Require requestedSections to equal quote, candles, technical, currentSessionFlow, holdings with no duplicates; all nine section keys must still exist. A section decoder validates every envelope field and its timestamps against decisionCutoff. A candles section marked validated must contain at least one completed validated candle to be a usable price section; add a decoder test proving an empty validated candle array cannot produce live/partial. Only decode flattened data from usable sections. For missing optional data, create existing honest unavailable indicator/participation values; never insert fixture values or numeric zeros.

Holdings above 100 are accepted only as non-negative finite values in a section whose quality is anomalous and whose warnings contain the specified provider warning. Negative/non-finite rows fail their section contract.

Decode currentSessionFlow only as the gateway's direct normalized capital-flow rows with section `methodVersion: "provider-capital-flow-normalized-v1"`. Validate every finite number, ordered/future-safe timestamp, non-empty session, and literal `institutionalIdentity: false`. Do not convert these rows into candle-aligned ParticipationBars: chart interval and current-session flow are independent. Keep the flattened legacy `participationBars` field as honest unavailable placeholders for v3 until the dedicated session-flow UI slice consumes `sections.currentSessionFlow`.

Add `GatewayClientUpdateRequiredError extends GatewayValidationError` and throw it before ordinary validation when an object carries a syntactically valid unknown major schema. Add `GatewaySnapshotUnavailableError extends GatewayValidationError` with a `kind: GatewayRequestErrorKind`; the v3 decoder derives that kind from the fixed quote/candle section errorCodes through the existing `kindByGatewayCode` table and uses `unspecified` when neither maps. In `toSnapshotRequestError`, check update-required first and return `GatewayRequestError("client-update-required", ...)`, then check snapshot-unavailable and return `GatewayRequestError(error.kind, ...)`, before the general GatewayValidationError branch. Do not fall back in either case.

- [ ] **Step 6: Implement strict fallback**

Request /v3/stock-snapshot first. Catch only the typed HTTP status error with status 404 or 426 before issuing /stock-snapshot. Do not use a broad catch around decodeStockSnapshotV3Envelope. Convert a usable legacy v2 snapshot without changing its existing values and always set `snapshotStatus: "live"`, `source.status: "live"`, `compatibility: "v2-fallback"`, and `requestedCount` from the validated client request. Create synthetic sections as follows:

- quote: live/validated with the decoded v2 quote;
- candles: live/validated when non-empty, otherwise unavailable/invalid;
- technical: live/validated when the decoded technical object is present; nested warm-up unavailability remains inside its existing values;
- currentSessionFlow: unavailable/invalid with `LEGACY_V2_CANDLE_ALIGNED_ONLY`; keep the already-decoded v2 values only in the flattened legacy participationBars field, because they are candle-aligned and are not the v3 direct-flow contract;
- holdings: delayed/validated when rows exist, otherwise unavailable/invalid;
- fundamentals, marketContext, news, forecastDecision: unavailable/invalid with `NOT_REQUESTED`;
- requestedSections is the same fixed five-name list as v3.

The legacy compatibility adapter does not recompute top-level status from synthetic sections; it faithfully records the usable v2 contract as live.

- [ ] **Step 7: Verify mobile data/state suites and commit**

Run:

~~~bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand \
  src/data/__tests__/marketGateway.test.ts \
  src/data/__tests__/marketRepository.test.ts \
  src/state/__tests__/MarketDataProvider.test.tsx
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run typecheck
~~~

Expected: all selected tests and typecheck pass.

~~~bash
git add apps/mobile/src/domain/models.ts \
  apps/mobile/src/data/marketGateway.ts \
  apps/mobile/src/data/marketRepository.ts \
  apps/mobile/src/i18n/marketErrorCopy.ts \
  apps/mobile/src/state/MarketDataProvider.tsx \
  apps/mobile/src/data/__tests__ \
  apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx
git commit -m "feat: consume sectioned stock snapshots on mobile"
git push origin feature/iphone-demo
~~~

---

### Task 5: Render usable price sections and anomalous holdings honestly

**Files:**
- Modify: apps/mobile/src/screens/StockDetailScreen.tsx
- Modify: apps/mobile/src/components/stock/StockHeader.tsx
- Modify: apps/mobile/src/components/chart/PriceChart.tsx
- Modify: apps/mobile/src/components/stock/InstitutionalHoldingsCard.tsx
- Modify: apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx
- Create: apps/mobile/src/components/stock/__tests__/StockHeader.test.tsx
- Modify: apps/mobile/src/components/chart/__tests__/PriceChart.test.tsx
- Modify: apps/mobile/src/components/stock/__tests__/InstitutionalHoldingsCard.test.tsx
- Modify: apps/mobile/src/components/stock/__tests__/institutionalHoldings.fixture.ts

**Interfaces:**
- Consumes: LiveStockSnapshot.sections and flattened usable data
- Produces: a stock screen that renders quote or daily candles even when an optional section is unavailable/anomalous
- Produces: InstitutionalHoldingsCard section status, warning, original provider value, and delayed-disclosure label

- [ ] **Step 1: Write screen regression tests for all eight failed symbols**

Use v3 fixtures for CRCL, AVGO, GRRR, SMTC, LULU, PTON, ETSY, and GPCR. For each symbol render StockDetailScreen in Real mode and assert:

~~~typescript
expect(screen.getByText(symbol)).toBeTruthy();
expect(screen.getByText("日K")).toBeTruthy();
expect(screen.getByText("神奇九转")).toBeTruthy();
expect(
  screen.getByText(
    "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释",
  ),
).toBeTruthy();
~~~

Assert neither the full-page malformed-data state nor a Demo badge appears. Add a separate fixture where holdings are unavailable and quote/candles remain rendered.

Add candles-only and quote-only fixtures. Candles-only renders the last completed close with the explicit label `最新日K收盘` and does not invent a change percentage; quote-only renders the live quote and an honest no-completed-candles chart state. PriceChart accessibility text follows the same rule and never dereferences a null quote.

The new StockHeader test file first pins the existing quote-present rendering unchanged, then adds the candles-only latest close/`最新日K收盘`/no-percentage case and a quote-only case. The initial RED must be an assertion failure from nullable-quote behavior, not merely Jest reporting a missing path.

- [ ] **Step 2: Write holdings-card behavior tests**

Pass the v3 holdings section, not only a bare array. Assert:

- the exact original percentage is visible;
- delayed reporting period and source remain visible;
- anomalous warning is visible;
- the card never says a named institution bought or sold today;
- unavailable shows its sanitized section reason, not 0%;
- font styles preserve the established 13–16 pt readable floor.

The card may render only the fixed v3 section `reason`, `warnings`, and anomaly reasons specified in Tasks 2–3. It must not derive copy from raw provider content. Top-level transport/decode/update-required errors remain owned by `marketErrorCopy.ts` from Task 4; `serverVocabulary.ts` is only for the analysis service's allowlisted prose and is not changed here.

- [ ] **Step 3: Run and verify RED**

Run:

~~~bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand \
  src/screens/__tests__/StockDetailScreen.test.tsx \
  src/components/stock/__tests__/StockHeader.test.tsx \
  src/components/stock/__tests__/InstitutionalHoldingsCard.test.tsx
~~~

Expected: FAIL because the screen/card do not consume v3 section metadata.

- [ ] **Step 4: Implement section-aware rendering**

Keep the full-page blocking state only when no quote and no candle is available. Render each optional card from its own section status. Pass the holdings section into InstitutionalHoldingsCard and display warnings/anomalies without reinterpreting the percentage.

Update StockHeader and PriceChart for nullable quotes: prefer the validated quote; otherwise use only the last completed candle close and label it as such. Do not derive a fake percentage from one candle and do not call it a real-time price.

Do not render raw provider or Python exception messages. Transport/decode errors go through `marketErrorCopy.ts`; section copy is already fixed/sanitized by the v3 contract.

- [ ] **Step 5: Verify screen, chart, decision, and accessibility regressions**

Run:

~~~bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand \
  src/screens/__tests__/StockDetailScreen.test.tsx \
  src/components/stock/__tests__/StockHeader.test.tsx \
  src/components/stock/__tests__/InstitutionalHoldingsCard.test.tsx \
  src/components/chart/__tests__/PriceChart.test.tsx \
  src/components/stock/__tests__/ParticipationCard.test.tsx \
  src/components/stock/__tests__/DecisionCard.test.tsx
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run typecheck
~~~

Expected: all selected tests and typecheck pass.

- [ ] **Step 6: Commit and push**

~~~bash
git add apps/mobile/src/screens/StockDetailScreen.tsx \
  apps/mobile/src/components/stock/StockHeader.tsx \
  apps/mobile/src/components/chart/PriceChart.tsx \
  apps/mobile/src/components/stock/InstitutionalHoldingsCard.tsx \
  apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx \
  apps/mobile/src/components/chart/__tests__/PriceChart.test.tsx \
  apps/mobile/src/components/stock/__tests__
git commit -m "fix: keep stock pages usable through optional data failures"
git push origin feature/iphone-demo
~~~

---

### Task 6: Verify migration, live symbols, and actual App behavior

**Files:**
- Modify: services/market_gateway/README.md
- Modify: services/analysis_api/README.md
- Modify: docs/runbooks/local-real-market.md
- Modify: scripts/smoke_live.py
- Modify: scripts/tests/test_smoke_live.py
- Modify: services/market_gateway/scripts/smoke_real_snapshot.py
- Modify: services/market_gateway/tests/test_smoke_real_snapshot.py
- Create: services/market_gateway/tests/fixtures/snapshot_v3_anomalous_holdings.json

**Interfaces:**
- Produces: validate_snapshot_v2 and validate_snapshot_v3 plus `--contract-version {v2,v3}` route dispatch in smoke_real_snapshot.py
- Produces: smoke_live.py `--all-watchlist`, `--snapshot-version {v2,v3}`, and `--report PATH`
- Proves: all Watchlist symbols yield a usable price section or a precise section-level limitation

- [ ] **Step 1: Write failing smoke-contract tests**

Rename the existing validator to `validate_snapshot_v2` without changing its checks. Add `validate_snapshot_v3`, which requires schemaVersion "3", the fixed requestedSections list, all nine complete section envelopes, and the quote-or-candles minimum. Feed the anomalous-holdings fixture and assert it passes as partial.

Add a response with neither price section and assert it fails with a named validation reason.

Add CLI tests proving `--contract-version v2` requests `/stock-snapshot`, `--contract-version v3` requests `/v3/stock-snapshot`, and each dispatches only its corresponding validator. Add smoke_live parser/report tests for `--all-watchlist --snapshot-version v3 --interval day --report PATH`; assert the JSON has one entry per `/watchlist` symbol and contains no pairing code, device token, Authorization value, market token, or environment dump.

- [ ] **Step 2: Run and verify RED**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core:. \
  /opt/homebrew/anaconda3/bin/python3 -m unittest \
  services.market_gateway.tests.test_smoke_real_snapshot \
  scripts.tests.test_smoke_live -v
~~~

Expected: FAIL because the v3 validator and fixture are absent.

- [ ] **Step 3: Implement dual-version smoke validation and update docs**

In `services/market_gateway/scripts/smoke_real_snapshot.py`, `--contract-version` defaults to v2 for backward compatibility and dispatches route/validator exactly:

- v2 -> `/stock-snapshot`, `validate_snapshot_v2`;
- v3 -> `/v3/stock-snapshot`, `validate_snapshot_v3`.

In `scripts/smoke_live.py`, `--all-watchlist` obtains symbols from GET `/watchlist`, defaults its interval to day unless the caller explicitly supplies another interval, requests the selected snapshot version, and calls `/decision?symbol={symbol}&horizon={horizon}` for each symbol. One paired device token is reused for the whole run and revoked in the existing finally path. `--report` writes a JSON object containing run metadata and, per symbol, top-level status, each v3 section availability/quality/errorCode, daily candle count/interval, holdings quality/anomalies, decision HTTP status/score/factor coverage/interval. It never records authorization headers, tokens, pairing codes, environment variables, or raw server/provider error text. Keep a separate single-symbol v2 validation path.

Document:

- /stock-snapshot and /v2/stock-snapshot are legacy v2;
- /v3/stock-snapshot is the sectioned contract;
- analysis reads /candles with interval=day by default;
- delayed holdings and current-session order-size flow are not the same feature.

- [ ] **Step 4: Run the complete automated slice verification**

Run:

~~~bash
PYTHONPATH=services/market_gateway/src:services/analysis_core \
  /opt/homebrew/anaconda3/bin/python3 -m unittest discover \
  -s services/market_gateway/tests -v

PYTHONPATH="$PWD/services/analysis_api/src:$PWD/services/analysis_api/tests:$PWD/services/analysis_core:$PWD/services/information_layer:$PWD/services/adviser_layer:$PWD/services/decision_engine:$PWD/services/device_auth/src:$PWD/services/adviser_llm/src" \
  /opt/homebrew/anaconda3/bin/python3 -m unittest discover \
  -s services/analysis_api/tests -v

cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm test -- --runInBand
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/bin:/bin \
  npm run typecheck
~~~

Expected: all gateway/API/mobile tests and typecheck pass. Do not claim lint green in this plan.

- [ ] **Step 5: Run the 46-symbol live audit**

With the already configured private runtime environment and paired credentials, run the smoke tool without echoing credentials. For every active Watchlist symbol record:

- quote/candles section usable or exact unavailable reason;
- daily candle count and interval;
- holdings quality, including anomalies;
- decision HTTP status, score, and factor coverage.

Acceptance:

- CRCL, AVGO, GRRR, SMTC, LULU, PTON, ETSY, and GPCR no longer fail the entire page or decision because of holdings;
- every successful analysis response states interval day;
- no auth failures, contract decode failures, or Demo fallback;
- a genuine future timestamp remains rejected in only its contaminated section.

Use this exact live command (the private environment is inherited; do not print it):

~~~bash
PYTHONPATH=services/device_auth/src \
  /opt/homebrew/anaconda3/bin/python3 scripts/smoke_live.py \
  --gateway-url http://127.0.0.1:8765 \
  --analysis-url http://127.0.0.1:8770 \
  --device-database /Users/franz/.us-stock-helper/state/devices.sqlite3 \
  --all-watchlist \
  --snapshot-version v3 \
  --interval day \
  --count 250 \
  --horizon short \
  --report /tmp/us-stock-helper-watchlist-v3.json
~~~

Then run the legacy compatibility check without a report:

~~~bash
PYTHONPATH=services/device_auth/src \
  /opt/homebrew/anaconda3/bin/python3 scripts/smoke_live.py \
  --gateway-url http://127.0.0.1:8765 \
  --analysis-url http://127.0.0.1:8770 \
  --device-database /Users/franz/.us-stock-helper/state/devices.sqlite3 \
  --symbol SOFI --snapshot-version v2 --interval day --count 250 --horizon short
~~~

- [ ] **Step 6: Inspect the actual app**

Launch the current dev client on the simulator and connected iPhone. Inspect SOFI plus the eight formerly failing symbols:

- default chart says 日K;
- complete Magic Nine sequence remains attached to daily candles;
- quote/chart/decision remain visible with anomalous or unavailable holdings;
- holdings card shows delayed disclosure and the exact warning;
- no full-page generic malformed state and no Demo badge in Real mode.

Capture screenshots under /tmp only; do not commit them.

- [ ] **Step 7: Commit verification assets and push**

~~~bash
git add services/market_gateway/README.md \
  services/analysis_api/README.md \
  docs/runbooks/local-real-market.md \
  scripts/smoke_live.py \
  scripts/tests/test_smoke_live.py \
  services/market_gateway/scripts/smoke_real_snapshot.py \
  services/market_gateway/tests/test_smoke_real_snapshot.py \
  services/market_gateway/tests/fixtures/snapshot_v3_anomalous_holdings.json
git commit -m "test: verify sectioned snapshots across live watchlist"
git push origin feature/iphone-demo
~~~

## Plan Completion Gate

This plan is complete only when:

- every task has a recorded RED and GREEN test command;
- all task reviews have spec-compliance and code-quality approval;
- local and remote feature/iphone-demo point to the same final commit;
- the live 46-symbol report demonstrates section-level degradation;
- actual simulator and iPhone screens demonstrate daily chart, Magic Nine, decision, and holdings behavior for SOFI and the eight formerly failing symbols;
- the broader product goal remains active for durable runtime, order-size-flow history, Real market/candidates/alerts, news/journal/adviser parity, and production iPhone deployment.
