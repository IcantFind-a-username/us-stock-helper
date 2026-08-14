# US Stock Helper Live Parity, Capital Flow, and Durable Runtime

**Date:** 2026-08-14

**Status:** Draft — pending user review

**Primary scope:** Watchlist plus broad-market and sector benchmarks first
**Design inputs:**

- `2026-07-24-us-stock-helper-product-design.md`
- `2026-07-25-real-market-backend-v1-design.md`
- `2026-07-25-overnight-demo-completion-design.md`

This document is a proposed implementation amendment. It does not replace the
existing product boundaries: the app remains a read-only research, alerting,
explanation, and risk-planning assistant. It never submits, modifies, or cancels
orders. Implementation must not begin until the user accepts this amendment.

## 1. Why this amendment exists

The existing Demo communicates the intended product, but the current Real mode
is still a narrow live-data slice. A 2026-08-14 audit of the running app, local
services, and all 46 watchlist symbols established four systemic gaps.

1. The backend and Metro are terminal/Codex child processes. Ending that session
   ends the services, even though the Python servers themselves are healthy.
2. Eight symbols (`CRCL`, `AVGO`, `GRRR`, `SMTC`, `LULU`, `PTON`, `ETSY`, and
   `GPCR`) have valid quotes and 249 valid daily candles, but the optional
   institutional-holdings section rejects provider percentages above 100 and
   makes the entire stock snapshot and decision fail.
3. Moomoo returns a complete current-session capital-flow series. SOFI returned
   391 minute observations in the live audit. The current participation v1
   deliberately rejects daily/weekly candles, so the default daily chart shows
   every participation bar as unavailable even though a useful current-session
   summary can be computed independently.
4. Market verdicts, priority alerts, candidate discovery, the full Alerts page,
   Agent conversations, full adviser council, and several stock-detail cards are
   still Demo-only or disconnected in Real mode.

The amendment makes partial live data useful without weakening provenance or
inventing coverage.

## 2. Chosen delivery strategy

Use progressive, honest live parity.

- Scan the user's moomoo Watchlist plus a small configured set of broad-market
  and sector benchmarks first.
- Use deterministic collection, feature computation, ranking, and alert rules
  for all automatic work.
- Use Claude only for an explicit single-stock news interpretation, an explicit
  full adviser consultation, an explicit Agent question, or an explicit journal
  reflection.
- Render every established Demo component in Real mode with real data, a precise stale
  state, or a precise unavailable state. Never fall back to Demo fixtures.
- Expand from the Watchlist to a licensed full-market universe only after the
  first slice is stable and provider quotas and entitlements are verified.

Alternatives were rejected for this slice:

- A paid-data-provider-first rewrite would improve full-market breadth, news,
  options, and historical order-flow coverage but would block delivery on new
  subscriptions and credentials.
- Filling live components with fixture values or unsupported derived estimates
  would be fast but would violate the existing truthfulness boundary.

## 3. Runtime architecture

### 3.1 Immediate durable local runtime

Install five independent user-level LaunchAgents:

| Service | Bind | Purpose |
| --- | --- | --- |
| loopback market gateway | `127.0.0.1:8765` | trusted market input for analysis |
| LAN market gateway | `0.0.0.0:8766` | temporary direct iPhone market access |
| analysis API | `0.0.0.0:8770` | paired read-only analysis access |
| Expo dev-client Metro | `0.0.0.0:8088` | development bundle only |
| background worker | no listener | collection, scan, alert, and close jobs |

Each service has its own label, restart policy, log files, and minimal
environment. A failure in one service must not terminate the others.

The move from the currently running Metro port `8083` to the canonical `8088`
is an explicit migration. The installer records PID, process start time,
executable, absolute repository working directory, command fingerprint, and
listening port, then rechecks that complete identity immediately before any
signal. A process is project-owned when it has an installer ownership marker or
all executable/directory/command/port fingerprints match a known project launch;
parent PID is not an ownership requirement because an Expo process can be
reparented to PID 1 after its terminal exits. Only an unknown listener on the
target `8088` or a target service port blocks installation. Unknown listeners on
legacy `8081`/`8083` are reported but left untouched and do not block the new
stack. A proven project-owned legacy listener may be handed over gracefully.
The installer sends `TERM`, waits up to 15 seconds, verifies the exact recorded
PID and start time exited, and never escalates to an unrelated PID. It then
updates the development URL, mobile environment, runbooks, and health checks
together.

The installer is idempotent and non-interactive. It must:

- reject unknown listeners instead of killing them;
- use absolute Python, Node 22, working-directory, and launcher paths;
- validate plist syntax before bootstrap;
- use `KeepAlive`, restart throttling, and `Umask` `077`;
- create log and runtime directories as `0700` and files as `0600`;
- support status, health, reinstall, and uninstall commands;
- preserve credentials, device data, and logs on ordinary uninstall;
- never print secrets or place secrets in process arguments.

The launcher parses a private `0600` environment file as strict key/value data;
it does not `source` arbitrary shell. Each child receives only the variables it
needs. In particular, market gateways never receive the Anthropic key and Metro
never receives it.

OpenD is a readiness dependency, not a process dependency. A gateway remains
alive and reports `OPEND_OFFLINE` until OpenD is logged in, then recovers on the
next request without restarting.

### 3.2 Production boundary

LaunchAgents are a reliable development and household-LAN bridge, not the final
independent iPhone deployment. The proposed production boundary remains a
Release/TestFlight build connecting to a paired HTTPS API without Metro. Direct
LAN market tokens embedded through `EXPO_PUBLIC_*` are treated as short-lived
development credentials restricted to an exact LAN CIDR.

The household-LAN milestone uses the existing one-time device pairing flow and
stores the analysis token in iOS Keychain. A development market token may be
embedded only in a Debug bundle; it has a maximum lifetime of seven days, is
restricted to the exact LAN CIDR, and is rotated by reinstalling/reloading both
gateway and Debug bundle. The gateway stores a server-side `issuedAt` and
`expiresAt`, rejects the token at or after `expiresAt`, and never accepts a
client-supplied timestamp; tests advance the server clock across the seven-day
boundary and prove rejection. A Release build contains no static market or
analysis token. Before Release, mobile market reads go through the paired API
boundary so the only persistent device credential is the revocable Keychain
pairing token. Plain HTTP LAN traffic is visibly labelled a development-only
transport and is not accepted as the final production security boundary.

### 3.3 Durable worker, storage, and recovery

The background worker is the sole scheduler. Request-serving APIs do not own
recurring jobs. It uses a private SQLite database in WAL mode with ordered,
transactional schema migrations. Initial tables are:

```text
schema_migrations
job_lease
flow_session_summary
scan_run
candidate_snapshot
alert_event
news_event
source_health
llm_budget_ledger
```

Every job has a deterministic idempotency key, scheduled session/time, attempt,
lease owner, lease expiry, heartbeat, and terminal state. A worker acquires a
lease transactionally, renews it while running, and makes all writes idempotent.
After a crash, an expired lease is recoverable by the next worker. Database
writes and job completion occur in one transaction where possible; otherwise a
replayed write is a no-op or an immutable revision, never a duplicate alert.

Worker health exposes last heartbeat, last successful scan, last close job,
active lease, queue age, provider cooldown, database migration version, and the
last error code without secrets. A launchd restart, abrupt `SIGKILL`, database
busy condition, and partially completed job each have fault-injection tests.

## 4. Partial-failure stock snapshot

### 4.1 Independent sections and versioned status

The stock response becomes a versioned sectioned snapshot. Symbol identity,
request parameters, `schemaVersion`, and `decisionCutoff` are top-level metadata.
Quote and candles are independent sections: a quote failure must not erase valid
completed candles, and a candle failure must not erase a valid current quote.

Sections are:

- quote;
- completed candles and adjustment metadata;
- technical indicators and patterns;
- current-session order-size participation;
- delayed institutional holdings;
- fundamentals;
- market context;
- news evidence;
- forecast and decision.

Every section has an explicit envelope:

```text
availabilityStatus: live | delayed | stale | unavailable
qualityStatus: validated | partial | anomalous | invalid
source
asOf
availableAt
receivedAt
data
errorCode
reason
warnings[]
anomalies[]
methodVersion
```

A section can therefore be both `delayed` and `anomalous`. The top-level status
is `live`, `partial`, or `unavailable`: it is `partial` whenever at least one
requested section is usable and another is not. The minimum usable stock page
is either a validated quote or at least one validated completed candle. Only an
invalid request, invalid identity/cutoff metadata, or absence of every price
section makes the whole response unavailable.

The new sectioned contract is `schemaVersion: "3"`; the current deployed flat
contract remains `schemaVersion: "2"`. Routing, not payload guessing, selects
the contract: the existing `/stock-snapshot` and explicit `/v2/stock-snapshot`
serve v2 unchanged, while `/v3/stock-snapshot` serves only v3. A v3-capable
mobile client calls the v3 route and falls back to the old route only on HTTP
`404` or `426`, recording that compatibility state; it never falls back after a
v3 decode, validation, authentication, or provider error. Unknown major versions
fail with a “client update required” state rather than “provider data malformed”.
Contract tests cover old-client/old-route, new-client/v3-route, new-client/old-
server fallback, and deliberate v2/v3 cross-route rejection. The unversioned v2
route is removed only in a later breaking release after installed-client usage
shows it is no longer needed.

Point-in-time violations are never repaired or hidden. The offending values are
excluded, the exact section error code is preserved, and no downstream score may
count that section as evidence. Invalid top-level cutoff/identity metadata
invalidates the whole snapshot; a future value inside one source invalidates that
section without erasing unrelated validated price sections.

Quote, candles, capital flow, distribution, holdings, factors, and news each
have a five-second source timeout and a twelve-second stock-snapshot deadline.
Independent calls run with at most four concurrent provider operations. Tests
inject exception, timeout, malformed, stale, and future data into each section
and prove that only the contaminated section is excluded. The decision route has
a 25-second total deadline, matching the observed live latency envelope while
leaving a visible timeout state.

### 4.2 Decouple analysis candles

The deterministic decision service must not require the all-in-one stock
snapshot merely to obtain candles. It reads the quote/candle core directly, then
requests optional evidence independently. A holdings failure can lower factor
coverage; it cannot turn valid technical analysis into `ANALYSIS_FAILED`.

## 5. Delayed institutional holdings

The holdings card remains a delayed reporting view and must never be presented
as today's buying or selling.

- Preserve provider values; do not clamp percentages to 100.
- Accept finite non-negative aggregate percentages above 100, because the
  provider contract does not publish a maximum and live results contain them.
- Mark any percentage above 100 as `anomalous` and state only the verified fact:
  “供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释”. Do not
  invent an explanation for the provider's denominator.
- Reject NaN, infinity, negative counts/shares, malformed periods, incorrect
  source values, and invalid or future timestamps.
- Keep report period, provider update time, institution count/change, shares,
  percentage/change, source, and quality status visible.

Rows are validated independently. One malformed row becomes an excluded row
with an anomaly record; it does not erase other valid periods. An anomalous row
may be displayed with a warning but must not contribute a normalised ownership
score until a documented interpretation is available.

## 6. Current-session order-size flow

### 6.1 Semantics

The feature is named **大单型资金参与** or **订单规模资金结构**, not real-time
institutional ownership.

Moomoo groups transactions by transaction-turnover size. Therefore:

- extra-large plus large orders form the `institutionLike` proxy;
- medium plus small orders form the `retailLike` proxy;
- `institutionalIdentity` is always false;
- the UI always exposes the proxy label, source, timestamp, coverage, and method
  version.

### 6.2 Current-session summary

Add a regular-session summary independent from the selected price-candle
interval. Premarket and after-hours observations are excluded from v1. Session
boundaries come from the official NYSE calendar in `America/New_York`, including
holidays, early closes, and daylight-saving changes.

The gateway captures one `requestedAt` before issuing quote, capital-flow, and
capital-distribution calls and one `decisionCutoff` after all accepted inputs are
received. Every input must have `availableAt <= decisionCutoff`, match the same
symbol and exchange session, and complete inside a five-second request window.
The summary `asOf` is the oldest of the three input `asOf` values, not the newest.
During the regular session, quote and distribution must be no more than two
minutes old for high confidence and no more than five minutes old for medium
confidence. After close, each final update must be within ten minutes of the
official close. Each input retains separate provenance:

```text
inputProvenance.quote: { source, asOf, availableAt, receivedAt }
inputProvenance.capitalFlow: { source, asOf, availableAt, receivedAt }
inputProvenance.capitalDistribution: { source, asOf, availableAt, receivedAt }
```

The summary contract is:

```text
symbol
session
sessionState: regular-open | regular-closed
requestedAt
decisionCutoff
asOf
priceChangePercent
priceChangeBasis: previous-close
extraLargeNetFlow
largeNetFlow
mediumNetFlow
smallNetFlow
institutionLikeNetFlow
retailLikeNetFlow
institutionLikeGrossActivity
retailLikeGrossActivity
institutionLikeActivityShare
retailLikeActivityShare
flowCoverage
classification
confidence
inputProvenance
methodVersion: order-size-session-distribution-v1
institutionalIdentity: false
```

Gross activity is computed from the distribution inflow plus outflow buckets.
Net flow is inflow minus outflow. Activity shares use gross activity, not the
sign of net flow, and sum to 100% when available. The price change uses the
provider quote's current/last price relative to its previous close, matching the
existing quote contract; v1 does not claim an open-to-current return.

Capital distribution is authoritative for session gross activity and session
bucket net flow. The final capital-flow point is authoritative for the intraday
trend and `flowCoverage`. For each bucket, compare its cumulative capital-flow
net with distribution net. The inputs agree when the absolute difference is at
most `max(1 USD, 0.005 * totalGross)`. Any larger difference produces an
`input-net-flow-mismatch` anomaly, makes quality `partial`, and forces
classification to `unavailable`; both raw provider values remain visible in the
provenance diagnostics and are never averaged.

### 6.3 Intraday trend

The cumulative minute capital-flow series is converted into non-overlapping
deltas. Five-minute display points are the default. This input exposes
cumulative **net** flow only, not gross inflow/outflow at each minute. Therefore
the trend uses the distinct method `order-size-net-change-trend-v1` and provides:

- institution-like and retail-like net-flow lines;
- an explicitly labelled absolute-net-change activity share, computed from the
  sum of absolute bucket deltas inside each five-minute window;
- session price line for confirmation;
- selectable exact values and an accessible textual summary.

It never calls the five-minute share gross activity or ownership. Missing
minutes reduce coverage and are never interpolated. The expected denominator is
the number of elapsed official regular-session minute pairs, or the complete
official session length after close.

- `coverage >= 0.95` is complete enough for high confidence;
- `0.80 <= coverage < 0.95` is partial and caps confidence at medium;
- `coverage < 0.80` makes the trend unavailable.

During the regular session, the newest accepted flow point must be no more than
two minutes old for high confidence and no more than five minutes old for medium
confidence. After close, the final point must be within ten minutes of the
official close. A mismatched session is unavailable.

### 6.4 Price/flow classification

Classification v1 uses exact, reproducible thresholds. Let:

```text
priceDirection = up when priceChangePercent >= +0.50
                 down when priceChangePercent <= -0.50
                 flat otherwise
totalGross = sum of all distribution inflow and outflow buckets
institutionIntensity = institutionLikeNetFlow / totalGross
retailIntensity = retailLikeNetFlow / totalGross
positive material flow >= +0.02
negative material flow <= -0.02
```

`totalGross` must be positive and finite. The session summary, quote, and
distribution must meet at least medium freshness and `flowCoverage` must be
`>= 0.80`; otherwise classification is unavailable. The states are descriptive,
never buy/sell commands:

- `large-order-supported-rise`: price up and institution intensity `>= +0.02`;
- `retail-like-supported-rise`: price up, institution intensity is between
  `-0.02` and `+0.02`, and retail intensity `>= +0.02`;
- `large-order-selling-divergence`: price up and institution intensity
  `<= -0.02`;
- `large-order-buying-divergence`: price down and institution intensity
  `>= +0.02`;
- `broad-selling`: price down and both intensities `<= -0.02`;
- `mixed`: no robust directional agreement;
- `unavailable`: stale or insufficient source coverage.

Confidence is `high` only when `flowCoverage` is at least `0.95`, all three inputs meet
the high freshness window, and `abs(institutionIntensity) >= 0.05` for a
large-order state. It is `medium` for other available classifications. The
Chinese copy uses phrases such as “上涨但大单型资金净流出” and never claims that
a named institution bought or sold.

### 6.5 Multi-session history

OpenD supplies the current session, not a trustworthy historical daily flow
series for this contract. Persist each validated final summary locally at market
close in SQLite. Rows are immutable revisions with a generated ID,
`(symbol, session, source, methodVersion)`, `observedAt`, `revision`, and optional
`supersedesId`. A current-history view selects the newest valid revision.

- The history begins on the day collection is enabled.
- Never backfill missing days from price or volume.
- Show collection coverage and gaps.
- A method-version upgrade starts a new series; a final summary alone is not
  claimed to be sufficient for recomputation.
- Raw minute flow is retained beyond the current session only after a provider
  terms/licence review explicitly permits private retention. Until then, the
  worker keeps it only in the current-session cache and persists the derived
  summary plus input provenance and hashes.
- A close job is keyed by official exchange session, not local calendar date.
  It runs ten minutes after official close, retries at `+20`, `+40`, and `+90`
  minutes, and records a visible gap if all attempts fail. A restart scans the
  prior two sessions for missing jobs and retries only when OpenD can still
  supply that session; it never substitutes another day's values.
- Re-running a job with byte-identical inputs is idempotent. Changed provider
  inputs create a new immutable revision linked through `supersedesId`.
- Default views are 5, 10, and 20 collected sessions.

## 7. Real-mode product parity

### 7.1 Dashboard

Real mode renders:

- timezone-correct greeting and US market session;
- market verdict, posture, key drivers, strongest counter-evidence, freshness,
  and coverage;
- highest-priority alert;
- real Watchlist pulse with partial-row isolation;
- ranked Watchlist candidates;
- source health and delayed/unavailable states.

The first market model uses SPY, QQQ, IWM, VIX-compatible available inputs,
sector benchmarks, Watchlist breadth, rates, dollar, and existing public-factor
sources. Missing factors lower coverage instead of becoming zero.

The greeting uses the device's resolved IANA timezone from
`Intl.DateTimeFormat().resolvedOptions().timeZone`; it never derives the greeting
from the US exchange timezone or a server clock hour. `Asia/Singapore` may be a
test fixture or an explicit configured fallback, but is not silently hardcoded
for every user. Local-time boundaries are exact:

```text
05:00-10:59  早上好
11:00-13:59  中午好
14:00-17:59  下午好
18:00-22:59  晚上好
23:00-04:59  深夜好
```

Tests convert UTC instants through the selected IANA zone, including a daylight-
saving zone, and prove that `01:45 Asia/Singapore` renders “深夜好”. Market
session status remains a separate NYSE-calendar calculation.

`market-verdict-watchlist-v1` is descriptive and reproducible. Every factor is
clipped to `[-1, 1]` and retains its source/cutoff:

```text
SPY trend      weight 0.25 = clip((close / MA20 - 1) / 0.03)
QQQ trend      weight 0.15 = clip((close / MA20 - 1) / 0.03)
IWM trend      weight 0.10 = clip((close / MA20 - 1) / 0.03)
watch breadth  weight 0.20 = (advancers - decliners) / measured symbols
sector breadth weight 0.10 = (sector ETFs above MA20 - below MA20) / measured ETFs
volatility     weight 0.10 = clip((20 - VIX) / 10), unavailable without a licensed input
rates/dollar   weight 0.10 = mean of available:
                              clip(-(US10Y - US10Y_MA20) / 0.50 percentage points)
                              clip(-(DXY / DXY_MA20 - 1) / 0.02)
```

`clip(x)` means `min(1, max(-1, x))`. The scan freezes its eligible universes at
the cutoff. Watch breadth eligibility is every ordinary equity in the active
Watchlist; measured symbols are eligible symbols with a validated current return.
Sector breadth eligibility is every ETF in the versioned configured sector-ETF
registry; measured ETFs have a validated latest completed close and MA20. Each
breadth factor's effective weight is its base weight multiplied by
`measuredCount / eligibleCount`; an empty eligible universe makes the factor
unavailable. Unchanged symbols remain measured and contribute zero to the
numerator. Thus one measured symbol out of 46 cannot consume the full 0.20
weight. The rates/dollar factor similarly has coverage `availableSubfactors / 2`.

Every other missing factor has zero effective weight rather than a zero value.
Overall coverage is the sum of effective weights and must be at least `0.60`;
otherwise the verdict abstains. The score is
`sum(effectiveWeight * factorValue) / coverage`. `>= +0.25` is risk-on,
`<= -0.25` is defensive, and the interval between is mixed. Intraday quotes must
be within five minutes; daily trends must use the latest completed exchange
session; rates/dollar inputs must be no more than 24 hours old on a business day.
The card cites eligible/measured counts, every factor, and the strongest opposing
factor, and labels this a Watchlist-oriented market context, not a backtested
market-timing strategy.

### 7.2 Stock detail

The designed cards are restored or connected in this order:

1. quote and daily K default;
2. complete Magic Nine markers and current state;
3. MA/MACD/RSI, Dragon Trend, pattern analysis, and volume context;
4. current-session order-size flow summary and trend;
5. delayed institutional holdings history;
6. fundamentals and dilution/event risks;
7. market/sector context;
8. news evidence and deterministic decision;
9. explicit on-demand news interpretation and adviser council.

Changing the chart interval does not silently change the decision horizon. The
screen clearly states whether an analysis is intraday, daily short-term, swing,
or long-term.

### 7.3 Discover and Alerts

The first candidate universe is Watchlist plus configured benchmarks. Ranking
uses deterministic price/volume anomalies, technical states, order-size-flow
confirmation/divergence, evidence freshness, liquidity, and risk gates.

This section is labelled **自选池机会**, never “全市场机会”. The designed
full-market discovery component remains visibly `unavailable` with the reason
“尚未配置合规的全市场股票池与配额” until a later licensed universe is approved.

`watchlist-opportunity-v1` ranks only ordinary Watchlist stocks; SPY/QQQ/IWM,
VIX inputs, and sector benchmarks are context and are excluded from candidates.
For each long direction, normalised inputs and weights are:

```text
deterministic decision score 0.50 = clip((score - 50) / 50)
price/volume anomaly         0.20 = sign(return) * min(abs(return)/5%, 1)
                                      * min(relativeVolume/3, 1)
session flow                 0.20 = +1 supported rise, -1 selling divergence,
                                      +0.5 buying divergence, 0 mixed;
                                      unavailable is a missing input
measured news sentiment      0.10 = existing deterministic event sentiment
```

Short ranking reverses the directional sign but still passes the short-specific
hard risk gates. V1 has one fixed ranking horizon, `daily-short-term`: decision,
technical state, and `relativeVolume` use completed **daily** candles regardless
of the chart interval the user is viewing. `return` is the current provider quote
change from previous close. `relativeVolume` is the latest completed daily
candle's volume divided by the mean of its prior 20 completed daily candles,
excluding the evaluated candle. Current-session flow remains a separately
timestamped confirmation/divergence input; it does not change the technical
candle interval. Five-minute and other intraday candidate rankings are outside
v1 and require separately named, tested methods.

Missing inputs are removed. Coverage is the sum of available base weights and
must be at least `0.65`; the composite is exactly
`sum(weight * normalisedInput) / coverage`, so missing inputs cannot merely shrink
the raw score. The selected chart interval never changes this score.
The existing decision engine's freshness, liquidity, volatility, data-quality,
and short-borrow gates can block actionability without hiding the candidate.
Composite ties sort by higher coverage, then symbol. Every row shows its two
largest contributions, strongest counter-signal, cutoff, coverage, and method
version. No model output is an input.

Alert types include:

- price/volume anomaly;
- Magic Nine completion or invalidation;
- large-order flow confirmation or divergence;
- new high-quality event/news evidence;
- stale data and risk-state changes.

Alerts are persisted, deduplicated into event threads, rate-limited, and can be
new, read, superseded, expired, or unavailable. A model opinion alone cannot
create an actionable alert.

Automatic alert conditions and severities are versioned and deterministic.
All severities are integers clamped to `0..100`:

| `conditionVersion` | False-to-true condition | Severity |
| --- | --- | --- |
| `price-volume-session-v1` | During the regular session after its first 30 minutes, `abs(previous-close return) >= 2%` and `sessionVolumePace >= 1.5`, with a fresh quote and 20 validated prior daily volumes. `sessionVolumePace = (current session volume / mean prior-20 completed daily volumes) / max(elapsed regular-session fraction, 0.10)`. It is displayed as a linear pace estimate and is not used as a completed-daily technical input. | `round(100 * (0.60 * min(abs(return)/5%, 1) + 0.40 * min(sessionVolumePace/3, 1)))` |
| `magic-nine-transition-v1` | The canonical daily Magic Nine state changes on a newly completed daily candle to setup-completed or setup-invalidated. An intraday chart selection cannot trigger it. | `75` for completion; `45` for invalidation |
| `order-size-flow-state-v1` | A medium/high-confidence session-flow classification changes from `mixed`/`unavailable` or another state to supported rise, selling divergence, buying divergence, retail-like supported rise, or broad selling. `relevantIntensity` is institution intensity for large-order states, retail intensity for retail support, and the smaller absolute leg for broad selling. | `round(50 + 50 * min(max(abs(relevantIntensity)-0.02, 0)/0.08, 1))` |
| `material-news-v1` | Exact symbol/entity linkage, source reliability `>= 0.80`, and deterministic materiality `>= 0.60`. Materiality is `1.00` for bankruptcy/default, financing/dilution, definitive M&A, or regulatory approval/rejection/recall; `0.80` for earnings/guidance, material filing, litigation ruling, or senior-leadership change; `0.60` for an official material product/contract event. Other categories do not trigger v1. | `round(100 * (0.60 * materiality + 0.40 * reliability))` |
| `quote-stale-v1` | A previously fresh Watchlist quote becomes older than five minutes during a regular session; it clears only after a validated fresh quote. | `35` |
| `worker-stale-v1` | Worker heartbeat is older than two configured scan periods. | `60` |
| `hard-risk-transition-v1` | The deterministic decision engine's hard-risk blocked state changes, with the changed gate IDs preserved. | `80` when entering blocked; `40` when clearing |

News deduplication keys on `(symbol, materialityCategory, primaryEntity,
sourceEventId)` when the source supplies an immutable ID; otherwise it uses a
versioned normalised-title/time-window hash and retains every underlying source.
Changing a threshold or formula requires a new `conditionVersion`; it never
silently rewrites an existing alert thread.

The alert idempotency key is `(symbol, type, horizon, conditionVersion,
conditionKey, exchangeSession)`. `conditionKey` is the price-move direction,
flow state, Magic Nine setup/invalidation ID, news semantic-cluster ID, stale
source ID, or hard-risk gate ID as applicable. A new event is emitted only on a
false-to-true condition transition; first observation of a new immutable news
cluster is that transition.
Price/volume and flow threads have a 30-minute notification cooldown;
Magic Nine emits once per completed setup/invalidation; news emits once per
semantic event cluster. A thread updates without a new notification when only
freshness changes. It can notify again when severity moves by at least 20 points
or an independent higher-reliability source changes the evidence state. Price/
flow conditions invalidate after two consecutive false five-minute scans or at
session close. Price/flow alerts expire after 24 hours, Magic Nine after five
trading sessions, and news after seven calendar days unless superseded sooner.
Severity `0..39` is information, `40..69` is watch, and `70..100` is eligible for
actionable research. The actionable-research label additionally requires fresh
price data, no hard risk gate, and originating-method coverage `>= 0.70`; if
those gates fail the level is capped at watch without changing the stored raw
severity.

### 7.4 News, Journal, Agent, and advisers

- Persist the existing event collector through the background worker and connect
  its evidence model to the production News panel. The first source registry is
  explicitly limited to SEC filings, configured macro/government feeds, and the
  currently registered AAPL/NVDA official-company feeds. For every other symbol,
  the UI states “未配置公司官方消息源”; it never turns absence of a registered
  source into “没有新闻”. Additions require a documented licence/robots/terms
  review and, where applicable, an explicit new credential gate. Show source
  coverage, source health, event time, discovered time, reliability, conflicts,
  citations, and unavailable states.
- Registered-source wiring is an intermediate milestone, not completion of the
  original Watchlist-wide news promise. A later news-source gate configures a
  lawful symbol-search feed whose declared universe includes every ordinary
  equity in the active Watchlist, maps provider identifiers explicitly, and
  retains the SEC/official-source feeds as higher-reliability evidence. Only
  after a symbol has a healthy registered search source may an empty result say
  “所选时间范围内未找到匹配消息”; otherwise it says “消息源未配置/不可用”. Benchmarks
  and instruments outside a provider's declared universe remain separately
  labelled. If this requires a subscription or credential, implementation stops
  at that external gate for the user's provider choice rather than fabricating
  coverage. The broader product goal is not complete until this gate passes or
  the user explicitly narrows the Watchlist-news scope.
- Extend Journal inputs with plan adherence, execution delay, slippage, notes,
  and outcome. Persist locally first with encrypted-at-rest platform storage for
  user-authored notes. Provide export and recoverable delete, plus a separately
  confirmed permanent purge. User history personalises risk and display, never
  the objective market score, evidence confidence, direction probabilities, or
  model calibration.
- Preference learning runs only when the user explicitly asks to reflect on
  selected journal entries or update preferences. It has no background model
  job. Structured journal fields first produce versioned deterministic measures
  for holding horizon, tolerated drawdown, plan adherence, execution slippage,
  sector concentration, and preferred risk-plan presentation. An optional
  Claude reflection may propose a narrative or preference change, but the user
  must inspect and accept it before it becomes active.
- The device-local encrypted journal database, separate from the worker SQLite,
  owns `journal_entry`, `preference_revision`, and `preference_snapshot`.
  `journal_entry` stores encrypted entry payloads and minimal non-sensitive
  indexing metadata. `preference_revision` stores immutable accepted,
  corrected, or deletion-derived revisions with source entry IDs, calculation
  version, creation time, and supersession link. `preference_snapshot` is the
  current materialised projection and can always be rebuilt from active
  revisions. The user can inspect the source entries for every preference,
  correct it by creating a new revision, move entries to recoverable trash, or
  permanently purge them. Trash removal and permanent purge recompute the
  snapshot and invalidate dependent reflection/model caches by evidence hash;
  deleted evidence cannot remain active through a stale summary.
- The mobile client appends its compact accepted preference snapshot to an
  explicit adviser/Agent request as `userRiskContext`, after the objective
  conclusion, evidence, confidence, and calibrated outputs have been fixed. It
  may change risk-budget wording,
  suitable hold-window options, presentation order, or which already-valid plan
  is emphasised. It cannot enter objective feature vectors, change the decision
  score, evidence confidence, direction probability, calibration, or remove a
  hard risk gate. Property tests hold market evidence constant, vary every
  preference, and prove those objective fields remain byte-identical.
- Journal sync and server-side journal storage are outside this amendment. An
  explicit reflection request sends only the user-selected entries through the
  paired authenticated channel; an adviser/Agent request sends only the active
  compact `userRiskContext`. The API does not persist decrypted notes or context
  and clears request-scoped plaintext after the response. No worker job or
  scheduler reads journal data or computes preferences.
- A random journal data-encryption key is wrapped by an iOS Keychain key; journal
  and preference plaintext is unavailable while the protected device is locked,
  and SQLite/file backups contain ciphertext only. An explicit portable backup
  is separately encrypted with a user-supplied recovery secret and has a tested
  restore path. If both the Keychain key and portable backup secret are lost,
  the data is truthfully reported unrecoverable and can only be purged; the app
  never resets a key and silently presents old ciphertext as empty history.
- Agent answers in the established order: conclusion, evidence, strongest
  counter-evidence, missing information, risk scenarios, citations.
- The 13 adviser profiles are public-style simulations, not the real people.
  Full council runs only on an explicit user request in this amendment. It reads
  a compact evidence packet, may abstain, and remains a bounded soft adjustment.
  Any future automatic trigger requires a separate user-approved design.

### 7.5 Demo-to-Real acceptance matrix

| Component | First Real source/behaviour | Honest unavailable state |
| --- | --- | --- |
| market verdict/playbook | benchmarks, breadth, public factors | missing factor list and coverage |
| priority alert | persisted deterministic alert engine | no qualifying alert / worker unhealthy |
| Dashboard candidates | Watchlist ranking | labelled self-pool, never full market |
| full-market candidates | none in this amendment | licensed universe not configured |
| Alerts page | persisted alert threads | worker/source status |
| daily chart and Magic Nine | completed moomoo daily candles | section error without blank stock page |
| Dragon Trend/patterns | canonical deterministic analysis core | method-specific reason |
| session flow | capital flow + distribution + quote | coverage/freshness/input-source reason |
| institutional holdings | delayed provider rows | per-row anomaly and section health |
| fundamentals/context | existing public-factor providers | factor coverage and freshness |
| News panel | registered sources only | per-symbol source coverage |
| forecast probability band | calibrated walk-forward model only | “尚未校准”, no decorative band |
| deterministic risk plans | decision engine with hard gates | blocked plan with reasons |
| Journal and saved plan | user input + real decision | local/encryption/export status |
| Agent | explicit evidence-grounded request | missing evidence/model budget state |
| 13-style council | explicit full request | abstention/model budget state |

Forecast calibration, probability bands, and risk plans remain required product
components, but an unavailable calibrated forecast is more correct than an
uncalibrated line. A real deterministic plan must display direction, entry
method/range, risk budget, invalidation, stop logic, targets, reward/risk, hold
window, cancellation conditions, data cutoff, and the no-auto-trading boundary.

## 8. Token and provider budgets

Automatic Watchlist scanning consumes zero LLM tokens.

- Cache deterministic snapshots and evidence packets by content hash.
- Deduplicate news before any model call.
- Never invoke full council from dashboard refresh, background polling, or
  Watchlist row rendering.
- Use one explicit symbol and one evidence snapshot per model request.
- Cache model output by symbol, horizon, evidence hash, model, and prompt version.
- Cancel or ignore stale in-flight results after a newer evidence snapshot.
- Record input/output tokens, latency, cache hit, and estimated cost.
- Before dispatch, atomically reserve the estimated request budget in SQLite.
  Default hard caps are 60,000 input tokens, 12,000 output tokens, and five model
  requests per Asia/Singapore calendar day. Per-request caps are 8,000/1,500 for
  news interpretation and 20,000/4,000 for full council or Agent. Maximum model
  concurrency is one. Identical in-flight requests coalesce, and a failed call
  releases only unused reserved output budget. Hitting a hard cap disables only
  model features, never deterministic data or analysis. These defaults are
  versioned operator settings, not `EXPO_PUBLIC_*` client configuration.

Provider collection uses TTLs, batching, single-flight, bounded concurrency, and
priority rather than one all-data request per ticker per refresh:

| Input | Regular-session cadence | Closed-session cadence |
| --- | --- | --- |
| batch Watchlist quotes | 60 seconds | 15 minutes while worker awake |
| completed daily candles | once after close; on-demand cache TTL 6 hours | cache until next session close |
| current-symbol intraday candles | selected interval boundary | on demand |
| holdings | 24-hour TTL | 24-hour TTL |
| flow/distribution, foreground symbol | 60 seconds while visible | final close request |
| flow/distribution, priority symbols | up to 8 symbols every 5 minutes | none |
| flow/distribution, full Watchlist | rotating so each symbol is sampled at most every 30 minutes; one final close pass | none |
| registered news feeds | source-declared minimum, never faster than 5 minutes | 15 minutes |

Quotes use the provider batch endpoint. Per-symbol calls are single-flight with a
shared cache. Market gateway concurrency defaults to four overall and two for
capital-flow endpoints. Visible/current symbol, risk alerts, and top quote
movers take priority; background rotations are dropped before foreground work.
Quota/429 responses trigger full-jitter backoff with bases of 60, 300, and 900
seconds, then a provider cooldown visible in source health. No tight retry loop
is allowed. Cadence automatically slows when provider quota health is unknown or
degraded.

## 9. Mobile visual and accessibility contract

Keep the established Calm Alpha palette and information hierarchy. Do not introduce
casino-like motion or a second visual system.

- Default body copy is approximately 16 pt with comfortable line height.
- Secondary explanation is normally 13–14 pt; 12 pt is reserved for short data
  labels with adequate contrast.
- Prices and percentages use tabular numerals.
- Touch targets are at least 44 by 44 points, with hit slop where needed.
- Color is never the only signal; flow and alert states include text/icons or
  line-style distinctions.
- Charts provide a numeric summary and selected-point readout.
- Long lists use virtualised rendering.
- Loading, partial, stale, error, and retry states remain visibly distinct.
- Every detail sheet receives provenance explicitly; Real data must never carry
  a Demo badge.

## 10. Delivery slices and acceptance gates

### Slice 1: stop the current failures

- institutional percentage values above 100 no longer break stock snapshot;
- optional holdings failure does not break quote, candles, indicators, or
  decision;
- the eight audited symbols return usable stock pages and decisions;
- real point-in-time violations remain excluded and explicitly reported;
- all new contracts begin with failing tests and pass after implementation.

### Slice 2: make the service survive the session

- install/status/uninstall scripts and five LaunchAgents;
- close the launching terminal/Codex session and verify services remain;
- kill each child and verify launchd restarts only that service;
- verify logs and installed configuration contain no current secrets;
- verify iPhone access, paired authentication, Debug-token rotation, and OpenD
  offline/recovery behavior;
- prove worker lease/crash recovery and idempotent database migrations.

### Slice 3: daily-trader capital flow

- current-session summary and five-minute trend for SOFI and representative
  positive/negative/empty symbols;
- price/flow classification with method-version tests;
- immutable close snapshots and 5/10/20-session history;
- daily price chart remains daily while the session-flow card remains useful;
- exact proxy disclosure is visible and accessible.

### Slice 4: real Dashboard, Discover, and Alerts

- Watchlist-first deterministic scan;
- real market verdict and coverage;
- candidate ranking and persisted alert threads;
- partial failures do not block other rows or sections;
- no automatic LLM calls in network/request tests.

### Slice 5: News, Journal, Agent, and adviser parity

- registered-source News panel, coverage, health, and evidence citations, then
  a separately gated lawful Watchlist-wide symbol-search source before the
  original news promise is considered complete;
- richer Journal entry/outcome, encrypted notes, export/delete, and saved real
  plans with versioned, inspectable preference revisions and the objective-score
  firewall;
- evidence-grounded Agent route;
- explicit full council route in mobile with usage/cost display;
- model failures abstain while deterministic analysis remains usable.

### Slice 6: household-LAN milestone hardening

- typecheck and all unit/integration suites pass;
- 46-symbol live smoke passes or reports section-level provider limitations
  without whole-stock failure;
- simulator and connected iPhone are checked after each vertical slice;
- Debug build reconnects after terminal/Codex exit and service restart;
- commits are small, intentional, and pushed to the remote feature branch.

This slice is a household-LAN milestone only. It must not be reported as an
independent production iPhone deployment.

### Slice 7: independent iPhone production deployment

- deploy the paired API and background worker to the user-selected Singapore host;
- expose only a managed HTTPS hostname with valid TLS; OpenD and private service
  ports are not publicly reachable;
- migrate the device through a versioned endpoint configuration and retain a
  tested rollback to the prior API deployment;
- rotate/revoke pairing credentials without shipping a new static secret;
- build and install a Release/TestFlight app containing no Metro dependency or
  `EXPO_PUBLIC_*` market/analysis token;
- validate Wi-Fi and cellular use, process restart, host reboot, database backup
  and restore, migration rollback, source outage, and certificate renewal;
- document cloud cost, credential ownership, recovery steps, and provider terms.

This slice requires the user's cloud account/credential choice when deployment
reaches that external boundary. Until it passes, the broader product goal is not
complete even if the household-LAN milestone is usable.

## 11. Definition of done

This amendment is complete only when the real app, not just tests or Demo mode,
proves all of the following:

- it opens without a terminal-owned service lifetime;
- every Watchlist stock opens with daily candles and partial-section isolation;
- Magic Nine and other daily analysis use completed daily candles by default;
- delayed holdings and current-session flow are visibly separate;
- current-session and accumulated multi-session flow answer whether price action
  is supported or contradicted by large-order activity without claiming identity;
- market verdict, candidates, alerts, news, Journal, Agent, and explicit adviser
  paths are connected in Real mode;
- every ordinary-equity Watchlist symbol is mapped to a healthy lawful search
  source before the app claims Watchlist-wide news coverage; registered-source-
  only delivery is explicitly an incomplete milestone;
- journal-derived preferences are inspectable, correctable, removable, and can
  alter only user risk context or presentation, never objective analysis;
- the greeting follows the device IANA timezone; `01:45` in `Asia/Singapore`
  renders “深夜好”;
- model token use is on-demand, bounded, cached, and observable;
- availability (`live`, `delayed`, `stale`, `unavailable`), quality
  (`validated`, `partial`, `anomalous`, `invalid`), and Demo provenance cannot
  be mistaken for each other;
- self-pool discovery is not labelled full-market discovery, and missing news
  source coverage is not labelled “no news”;
- the Release/TestFlight build works over paired HTTPS without Metro or a static
  bundled API token;
- the complete verification matrix and live UI checks pass, and all intended
  commits are pushed.
