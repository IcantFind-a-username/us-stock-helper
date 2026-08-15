# `GET /market-brief` wire contract (as implemented)

Landed in commit `799d6c4` on `feature/iphone-demo` (Task 3 of
`docs/superpowers/plans/2026-08-15-demo-parity-market-brief-and-council.md`):

- `services/analysis_api/src/us_stock_helper_analysis_api/market_brief.py`
  (new — `MarketBriefService`)
- `services/analysis_api/src/us_stock_helper_analysis_api/service.py`
  (`AnalysisService.read_market_evidence()`)
- `services/analysis_api/src/us_stock_helper_analysis_api/http_app.py`
  (`MARKET_BRIEF_PATH`, `_READ_PATHS`, `AnalysisApplication.handle`)
- `deploy/Caddyfile` + `deploy/tests/test_deployment_configuration.py`
- Tests: `services/analysis_api/tests/test_market_brief.py`

Extended (Task 5 of
`docs/superpowers/plans/2026-08-15-quant-foundations-plain-language.md`,
"Serve the factors") to source two of the previously-placeholder driver
categories — `breadth` and `sector` — from `us_stock_helper_core`'s
`breadth-v1` and `sector-rs-v1` engines over a configurable daily-bar
universe read from the market gateway:

- `services/analysis_api/src/us_stock_helper_analysis_api/market_brief.py`
  (`MarketBriefUniverseConfig`, `MarketBriefUniverse`, the breadth/sector
  compute-and-cache path)
- `services/analysis_api/src/us_stock_helper_analysis_api/market_universe_cache.py`
  (new — `MarketUniverseCache`)
- `services/analysis_api/src/us_stock_helper_analysis_api/gateway_provider.py`
  (`MarketGatewayProvider.watchlist_symbols()`)
- `services/analysis_api/src/us_stock_helper_analysis_api/evidence_provider.py`
  (`CompositeAnalysisProvider.watchlist_symbols()` passthrough)
- `services/analysis_api/src/us_stock_helper_analysis_api/http_app.py` /
  `__main__.py` (`AnalysisApplication.market_brief_universe`,
  `build_server(..., market_brief_universe=...)`)
- Tests: `services/analysis_api/tests/test_market_brief.py`
  (`BreadthDriverTests`, `SectorDriverTests`, `UniverseCacheTests`,
  `UniverseConfigEnvironmentTests`, `DataHealthInterplayTests`),
  `test_gateway_provider.py` (`WatchlistSymbolsTests`),
  `test_evidence_provider.py` (watchlist passthrough)

This document is the as-shipped wire semantics for whoever wires the mobile
decoder — it describes the server exactly as it now behaves, not a proposal.
The per-symbol RVOL/range-vol half of Task 5 (the decision payload, not this
route) is not covered here.

## Route

`GET /market-brief` — no query parameters are read; any that are sent are
ignored. Same read-only boundary as `/decision`: GET-only (405 on any write
method), same device-token gate ordering, same 404 space for everything not
on the allowlist. Never triggers a model call. A burst of requests inside the
evidence collector's minimum poll interval performs at most one feed sweep,
because it reads through the same shared `AnalysisService` (and therefore the
same evidence collector and poll coordinator) that `/decision` already uses —
no second collector is stood up per request.

## Envelope shape

```
{
  "schemaVersion": "1",
  "status": "available" | "unavailable",
  "reason": string | null,
  "decisionCutoff": string,               // ISO 8601 UTC, "...Z"
  "marketSession": "premarket" | "regular" | "afterhours" | "closed",
  "dataHealth": "fresh" | "stale" | "conflict" | "insufficient" | null,
  "sentiment": {
    "conclusion": string,                 // e.g. "偏多" | "偏空" | "中性"
    "actionScore": number,                // always a measured float, 0.0 when unmeasured (see below)
    "uncertainty": string[]                // e.g. "情绪未测量", "来源冲突", "独立来源不足"
  } | null,
  "driverCoverage": [
    {
      "category": string,                 // one of the 9 designed categories, see below
      "available": boolean,
      "conclusion": string | null,        // non-null only when available
      "actionScore": number | null,       // non-null only when available
      "missingReason": string | null,     // non-null only when NOT available
      "computedAt": string | null         // ISO 8601 UTC; non-null only when available AND the
                                           // category is cache-backed (breadth, sector); always
                                           // null for news-sentiment and every unsourced category
    },
    ...                                    // always exactly 9 entries
  ],
  "citations": [
    {
      "id": string,
      "headline": string,
      "publisher": string,
      "url": string,                      // always "https://..."; non-https citations are dropped, never served
      "availableAt": string,              // ISO 8601 UTC
      "freshnessSeconds": number | null,  // null only when age was never measured (not a real production path)
      "stale": boolean | null
    },
    ...
  ],
  "sourceGaps": string[],                  // e.g. "sec-current-8-k（unreachable）"; empty when the sweep was complete
  "notes": string[]                        // e.g. point-in-time exclusion disclosure; empty when there is nothing to disclose
}
```

No `symbol`, `horizon`, `interval`, `score`, `baselineScore`, `forecast`,
`riskPlan`, `adviserAdjustment`, `adviserCouncil`, `adviserUsage`, or
`newsInterpretation` field is present anywhere in this envelope — pinned by
`test_market_brief.py`'s `HttpBoundaryTests`. No order or credential field
(`orderId`, `submitOrder`, `quantity`, `accountId`, `brokerToken`) can appear
anywhere in it either, checked recursively.

## `status` / `reason`

- `"available"` — the evidence layer answered (fully or partially); `reason`
  is `null`.
- `"unavailable"` — every configured evidence source failed and nothing was
  already held for any symbol (`information_layer.feeds.EvidenceUnavailable`
  was raised with no prior store to fall back on). `reason` names every
  failed source in the exact format
  `"本次未能读取任何情报源：{source_id}（{reason}）、{source_id}（{reason}）..."`.
  This is the fail-closed path: an outage is never served looking like a
  quiet market. When `status: "unavailable"`, `dataHealth` and `sentiment`
  are both `null`, `citations` is `[]`, `notes` is `[]` (no packet was ever
  built, so there is nothing to disclose), and every `driverCoverage` entry
  has `available: false` with the shared reason
  `"本次没有可读取的情报源，无法给出该驱动的结论。"`. `decisionCutoff` and
  `marketSession` are still populated (the clock read needs no evidence).
  HTTP status is still `200` in this case — business-level unavailability
  lives in the JSON body, exactly like `/decision`'s "no completed candles"
  case; a `5xx` is reserved for a genuinely unexpected internal failure.

## `decisionCutoff`

Sampled from the service clock **after** the evidence fetch returns, for the
same reason a decision's cutoff is: a live collector stamps
`available_at = retrieved_at`, so sampling the clock any earlier would file
whatever this request's own fetch just retrieved as being from the future.

## `marketSession`

A best-effort NYSE session label computed from the wall clock alone (US/
Eastern via `zoneinfo`), with **no exchange calendar** consulted — a holiday
reads as a plain weekday session. Four values only:

- `"premarket"` — weekday, 04:00–09:30 ET
- `"regular"` — weekday, 09:30–16:00 ET
- `"afterhours"` — weekday, 16:00–20:00 ET
- `"closed"` — weekends, and weekdays outside 04:00–20:00 ET

## `dataHealth`

Derived from evidence-gap and staleness accounting, most-severe-first
(`null` only when `status: "unavailable"`):

1. **`"insufficient"`** — `sentiment.action_score_measured` is `False` (no
   actionable cluster was ever measured; the response also carries
   `"情绪未测量"` in `sentiment.uncertainty`). Includes the zero-evidence
   case.
2. **`"conflict"`** — (else) `sentiment.uncertainty` contains `"来源冲突"`
   (a cluster has both a strongly positive and a strongly negative measured
   report).
3. **`"stale"`** — (else) `sourceGaps` is non-empty (a source could not be
   read this round) **or** any served citation is `stale: true`.
4. **`"fresh"`** — none of the above.

## `sentiment`

Built by `EvidencePacketBuilder().build(events, as_of=decisionCutoff,
focus_symbols=())` — an **empty focus**, so every visible event (symbol-
specific and macro/geopolitical alike) contributes, exactly the "EvidencePacketBuilder
with empty focus symbols" the plan specifies. `MarketSentiment` is read off
the resulting packet with the same discipline `/decision`'s `sentiment` block
already uses:

- `actionScore` is **always a float**, never `null` — `0.0` when nothing was
  measured, exactly like `/decision`. The disambiguator between "measured
  zero" and "nothing measured" is the `"情绪未测量"` string inside
  `uncertainty`, not a null value. (`sentiment` itself is `null`, not this
  field, when the whole brief is `unavailable`.)
- `uncertainty` is the packet's own list verbatim (`"情绪未测量"`,
  `"来源冲突"`, `"含未证实传闻"`, `"独立来源不足"` as applicable).

## `driverCoverage`

Always exactly 9 entries, one per category designed in
`apps/mobile/src/domain/models.ts`'s `MarketDriverCategory`:

```
news-sentiment, breadth, volatility-options, sector, rates-dollar,
macro-credit-energy, liquidity-correlation, broad-market-trend, geopolitics
```

Three categories are sourced today: **`news-sentiment`**, **`breadth`** and
**`sector`**. The other six (`volatility-options`, `rates-dollar`,
`macro-credit-energy`, `liquidity-correlation`, `broad-market-trend`,
`geopolitics`) are always `available: false` with a named, category-specific
`missingReason` (Chinese) and `conclusion`/`actionScore`/`computedAt` all
`null` — no invented driver values.

### `news-sentiment`

Conditional on `sentiment.action_score_measured`:

- When `action_score_measured` is `True`: `available: true`, `conclusion`
  and `actionScore` mirroring the top-level `sentiment` fields exactly,
  `missingReason: null`, `computedAt: null` (this category is recomputed
  fresh from the evidence sweep on every request — it is never cache-backed,
  so there is no separate "computed at" instant to disclose).
- When `action_score_measured` is `False` (no actionable cluster was
  measured this round — e.g. the zero-evidence case): `available: false`,
  `conclusion` and `actionScore` both `null`, `missingReason:
  "情绪未测量（该时段无可读事件）"`. This mirrors the top-level
  `sentiment.uncertainty`'s `"情绪未测量"` disambiguator at the entry level,
  so a consumer reading `driverCoverage` alone (never the top-level
  `sentiment` block) is never told a driver was sourced when nothing was
  actually measured — an entry claiming `available: true` next to a
  中性/0.0 that was never measured would reproduce the same
  measured-looking-neutral failure `sentiment.action_score_measured` exists
  to prevent, just one level down.

### `breadth`

Sourced from `us_stock_helper_core.percent_above_moving_average` (`breadth-v1`,
50-day moving average) over a daily-bar universe:

- **Universe**: `ANALYSIS_API_BREADTH_UNIVERSE` (comma-separated US symbols,
  ≤60) when set; otherwise the operator's own watchlist, read live from the
  loopback gateway's `GET /watchlist`. Neither source configured, or a
  watchlist the gateway cannot currently serve, leaves this category
  `available: false`.
- **Scope label**: `conclusion` always opens with `"自选广度（N 只）"` where
  `N` is the size of the *configured* universe (explicit list or watchlist,
  after the ≤60 truncation) — **never** `"市场广度"`, because this reading
  never claims full-market coverage. Example:
  `"自选广度（5 只）· 多数走强 · 60% 收于50日均线上方"`.
- **actionScore**: `(percent_above_ma50 − 50) / 50`, clamped to `[-1, 1]`.
- **Partial fetches**: a symbol the gateway could not answer for this round
  is dropped from the universe (never fabricated), and — as long as enough
  symbols remain to satisfy `breadth-v1`'s own 5-symbol minimum — the
  reading is still served, with a top-level `notes` entry naming exactly
  which symbols were dropped (e.g. `"自选广度：1 只未能获取日K线（FFF），已用其余
  5 只计算。"`). Too few symbols survive (or none at all) → `available:
  false` with a `missingReason` naming the shortfall.
- **`computedAt`**: the `decisionCutoff` of whichever request actually
  computed this reading — see "Caching" below.

### `sector`

Sourced from `us_stock_helper_core.relative_strength_ranking` (`sector-rs-v1`,
21-trading-day EMA-anchored excess return) over a configured sector-ETF
universe against a configured benchmark:

- **Universe**: `ANALYSIS_API_SECTOR_RS_SYMBOLS` (comma-separated US symbols,
  ≤30) plus `ANALYSIS_API_SECTOR_RS_BENCHMARK` (single symbol). Both are
  required together — configuring one without the other fails deployment
  startup (`MarketBriefUniverseConfig.from_environment`), rather than
  silently ignoring the half that was set. Neither configured leaves this
  category `available: false` with `"板块强弱尚未配置板块 ETF 与基准品种"`.
- **Unfetchable universe**: the benchmark failing to fetch (or every sector
  ETF failing) makes the whole reading `available: false`, with
  `missingReason` naming exactly which configured symbols the gateway could
  not answer for this round — e.g. `"板块强弱所需品种本次未能从行情网关获取日K线（SPY），
  暂无法给出结论。"`. A partial sector-ETF fetch that still leaves at least
  `sector-rs-v1`'s own 2-symbol minimum is served instead, with a `notes`
  entry naming what was dropped, the same partial-handling shape breadth
  uses.
- **conclusion**: names the single leading (rank 1) sector ETF at the
  21-day lookback and its excess return over the benchmark, e.g.
  `"板块强弱（21日，对比 SPY）· 领涨 XLK 超额收益 +9.1%"`.
- **actionScore**: the leader's `excess_return` (a fraction, e.g. `0.091`),
  clamped to `[-1, 1]`.
- **`computedAt`**: same caching semantics as `breadth`, below.

### Caching (`breadth` and `sector`)

Both are computed at most once per "trading date" (the ET calendar date,
rolled back a day before the 16:00 ET close — the same no-exchange-calendar
simplification `marketSession` already discloses) and held in an in-process
cache shared across every request through the process's own
`MarketBriefUniverse` — built once at startup, not per request, unlike
`MarketBriefService` itself. A second brief requested the same trading date
reuses the cached entry outright, including its original `computedAt`; it
never re-fetches the universe. A burst of concurrent requests landing on a
cache miss is serialized through one lock, so at most one universe fetch (per
category) happens even under concurrency — mirroring the throttle discipline
`EvidenceCollector`'s poll coordinator already holds for the news sweep.

`dataHealth` is derived purely from sentiment/gap/citation accounting (see
below) and never reads `breadth`/`sector`'s availability — a sourced driver
can never soften an `"insufficient"` or `"conflict"` reading into something
healthier-looking.

## `citations`

Same shape as `/decision`'s citations (`id`, `headline`, `publisher`, `url`,
`availableAt`, `freshnessSeconds`, `stale`), built from the same
`packet.citations`, but filtered to `url.startswith("https://")` before
serialization — a non-https citation is dropped rather than served. In
practice every shipped feed adapter is https already; the filter is defense
in depth on a boundary that promises https-only citations, not a routing
around an existing non-https source.

## `sourceGaps`

The exact same pre-formatted strings `/decision`'s partial-sweep notes
already use (`"{source_id}（{reason}）"`), one per source the evidence
collector could not reach this round. Empty when the sweep was complete.
Independent of `dataHealth`'s "insufficient" state — gaps only ever push
`dataHealth` to (at worst) `"stale"`; only an unmeasured sentiment reading
pushes it to `"insufficient"`.

## `notes`

Mirrors `/decision`'s point-in-time exclusion disclosure. The point-in-time
invariant may exclude an event stamped after even this honestly-taken
`decisionCutoff` (an embargo, a skewed publisher clock); the exclusion is
legitimate, but hiding it is not. When
`packet.excluded_future_event_ids` is non-empty, `notes` carries exactly one
entry in the same format `/decision` uses:

```
"有 {len(excluded)} 条证据在决策截点之后才可用，未纳入本次结论：{event_id}、{event_id}..."
```

Empty (`[]`) when nothing was excluded, and always `[]` on the `unavailable`
path (no packet is ever built there).

## Example payload — available, clean

```json
{
  "schemaVersion": "1",
  "status": "available",
  "reason": null,
  "decisionCutoff": "2026-08-15T14:03:00Z",
  "marketSession": "regular",
  "dataHealth": "fresh",
  "sentiment": {
    "conclusion": "偏多",
    "actionScore": 0.42,
    "uncertainty": ["独立来源不足"]
  },
  "driverCoverage": [
    {
      "category": "news-sentiment",
      "available": true,
      "conclusion": "偏多",
      "actionScore": 0.42,
      "missingReason": null,
      "computedAt": null
    },
    {
      "category": "breadth",
      "available": true,
      "conclusion": "自选广度（5 只）· 多数走强 · 60% 收于50日均线上方",
      "actionScore": 0.2,
      "missingReason": null,
      "computedAt": "2026-08-15T14:03:00Z"
    },
    {
      "category": "volatility-options",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "波动率与期权持仓数据源尚未接入。",
      "computedAt": null
    },
    {
      "category": "sector",
      "available": true,
      "conclusion": "板块强弱（21日，对比 SPY）· 领涨 XLK 超额收益 +9.1%",
      "actionScore": 0.091,
      "missingReason": null,
      "computedAt": "2026-08-15T14:03:00Z"
    },
    {
      "category": "rates-dollar",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "利率与美元指数数据源尚未接入。",
      "computedAt": null
    },
    {
      "category": "macro-credit-energy",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "信用利差与能源价格数据源尚未接入。",
      "computedAt": null
    },
    {
      "category": "liquidity-correlation",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "流动性与相关性压力数据源尚未接入。",
      "computedAt": null
    },
    {
      "category": "broad-market-trend",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "大盘趋势判定数据源尚未接入。",
      "computedAt": null
    },
    {
      "category": "geopolitics",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。",
      "computedAt": null
    }
  ],
  "citations": [
    {
      "id": "C1",
      "headline": "NVIDIA raises full-year revenue guidance",
      "publisher": "reuters",
      "url": "https://reuters.example/a",
      "availableAt": "2026-08-15T13:44:00Z",
      "freshnessSeconds": 1140,
      "stale": false
    }
  ],
  "sourceGaps": [],
  "notes": []
}
```

## Example payload — unavailable, fail-closed

```json
{
  "schemaVersion": "1",
  "status": "unavailable",
  "reason": "本次未能读取任何情报源：sec-current-8-k（HTTP 503）、fred-releases（unreachable）",
  "decisionCutoff": "2026-08-15T14:03:00Z",
  "marketSession": "regular",
  "dataHealth": null,
  "sentiment": null,
  "driverCoverage": [
    {
      "category": "news-sentiment",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "本次没有可读取的情报源，无法给出该驱动的结论。",
      "computedAt": null
    }
    // ... same shape for the remaining 8 categories, computedAt included and
    // null throughout -- the unavailable path never computes breadth/sector
    // either, since no packet was ever built to source anything from
  ],
  "citations": [],
  "sourceGaps": [
    "sec-current-8-k（HTTP 503）",
    "fred-releases（unreachable）"
  ],
  "notes": []
}
```

## Example fragment — available but unmeasured news-sentiment

`status: "available"` still applies whenever the evidence layer answered at
all, even if nothing it returned yielded an actionable cluster this round;
that keeps `driverCoverage[0]` (`news-sentiment`) `available: false` and
`dataHealth: "insufficient"` distinct from the `status: "unavailable"` case
above (evidence layer never answered at all):

```json
{
  "status": "available",
  "dataHealth": "insufficient",
  "sentiment": {
    "conclusion": "中性",
    "actionScore": 0.0,
    "uncertainty": ["情绪未测量"]
  },
  "driverCoverage": [
    {
      "category": "news-sentiment",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "情绪未测量（该时段无可读事件）",
      "computedAt": null
    }
    // ... same shape for the remaining 8 categories -- breadth/sector are
    // unaffected by this and may still be available:true here, since their
    // sourcing has nothing to do with the evidence sweep this fragment
    // describes (see "Caching (breadth and sector)" above)
  ]
}
```

## Example fragment — an excluded future event, disclosed in `notes`

The rest of the envelope is unaffected — `driverCoverage[0]` still reads
`available: true` off the measured `sentiment` block, exactly like the
clean example above:

```json
{
  "status": "available",
  "notes": [
    "有 1 条证据在决策截点之后才可用，未纳入本次结论：future-1"
  ]
}
```
