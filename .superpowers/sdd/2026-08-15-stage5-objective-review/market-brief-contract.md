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

This document is the as-shipped wire semantics for whoever wires the mobile
decoder (Task 4) — it describes the server exactly as it now behaves, not a
proposal.

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
      "missingReason": string | null      // non-null only when NOT available
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
  "sourceGaps": string[]                   // e.g. "sec-current-8-k（unreachable）"; empty when the sweep was complete
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
  are both `null`, `citations` is `[]`, and every `driverCoverage` entry has
  `available: false` with the shared reason
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

Today only **`news-sentiment`** is sourced (`available: true`, `conclusion`
and `actionScore` mirroring the top-level `sentiment` fields exactly,
`missingReason: null`). The other 8 are `available: false` with a named,
category-specific `missingReason` (Chinese) and `conclusion`/`actionScore`
both `null` — no invented driver values. A later plan
(`docs/superpowers/plans/2026-08-15-quant-foundations-plain-language.md`) is
expected to wire breadth/sector-RS into these same slots, replacing their
`missingReason` placeholders in place.

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
      "missingReason": null
    },
    {
      "category": "breadth",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "大盘涨跌家数、新高新低等广度数据源尚未接入。"
    },
    {
      "category": "volatility-options",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "波动率与期权持仓数据源尚未接入。"
    },
    {
      "category": "sector",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "板块轮动强弱数据源尚未接入。"
    },
    {
      "category": "rates-dollar",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "利率与美元指数数据源尚未接入。"
    },
    {
      "category": "macro-credit-energy",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "信用利差与能源价格数据源尚未接入。"
    },
    {
      "category": "liquidity-correlation",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "流动性与相关性压力数据源尚未接入。"
    },
    {
      "category": "broad-market-trend",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "大盘趋势判定数据源尚未接入。"
    },
    {
      "category": "geopolitics",
      "available": false,
      "conclusion": null,
      "actionScore": null,
      "missingReason": "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。"
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
  "sourceGaps": []
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
      "missingReason": "本次没有可读取的情报源，无法给出该驱动的结论。"
    }
    // ... same shape for the remaining 8 categories
  ],
  "citations": [],
  "sourceGaps": [
    "sec-current-8-k（HTTP 503）",
    "fred-releases（unreachable）"
  ]
}
```
