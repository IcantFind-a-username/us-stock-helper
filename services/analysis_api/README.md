# analysis_api

The read-only HTTP boundary for the point-in-time decision chain. It composes
`information_layer`, `analysis_core`, `adviser_layer` and `decision_engine`
behind two GET paths and turns their output into one JSON answer the app can
render. A third path exists and does exactly one other thing: it exchanges a
pairing code for a device token, which is where every credential this service
accepts comes from.

Technical inputs for a composed decision use completed daily candles by
default. Intraday intervals are chart views, not an implicit basis for every
short-, swing- and long-horizon conclusion. Each response carries `interval`
so clients can state the analytical basis instead of guessing it.

## Safety invariants

- The path allowlist is exactly `GET /health`, `GET /decision` and
  `POST /v1/device-pairings`; every other method on every path fails closed
  with 405, and the pairing path answers nothing but POST.
- The pairing path is unauthenticated because it is where a credential comes
  from. What protects it is the code — single use, minutes long, and rate
  limited per caller in the credential database, so the count survives a
  restart. Every other path requires a device token that `device_auth`
  verifies and that the operator can revoke one phone at a time.
- No field in any response can carry an order, an account or a credential, and
  the risk plan states in its own warnings that it cannot place one.
- Provider failures are replaced with a fixed message: their text can contain
  credentials.

## What the contract refuses to hide

The chain declines to state some things, and those refusals travel to the
screen rather than being smoothed over in serialization:

- `score.factorCoverage` and `score.unavailableFactors` — Treasury data and SEC
  XBRL fundamentals fill macro and fundamental inputs when public records are
  available. Geopolitics and institutional flow remain explicit abstentions;
  unsupported or failed sources reduce coverage instead of becoming fake
  neutral values.
- `forecast: null` with a note — when realized volatility cannot be measured
  there is no honest width for a scenario range, and a band of no width shown
  as confidently as a measured one is worse than showing nothing.
- `status: "unavailable"` — no completed candles means no analysis, stated as
  such.
- `citations[].freshnessSeconds` and `citations[].stale` — how old each cited
  item was when it was read, and whether that passed the configured window.
  Both are `null` when the evidence never passed a collector: zero seconds old
  is a measurement, no measurement is not.

## Run the server

`market_gateway` must already be serving on the same host; its `/candles`
endpoint is this service's only deterministic price source. Optional sections
of a stock snapshot, including holdings, cannot affect a decision.

```bash
PYTHONPATH=services/analysis_api/src:services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m us_stock_helper_analysis_api

curl --fail --silent --show-error http://127.0.0.1:8770/health
curl --fail --silent --show-error \
  'http://127.0.0.1:8770/decision?symbol=NVDA&horizon=short'
```

The default request above never calls a model. The phone's paid button sends
`adviser=news`, which performs one traceable news-interpretation call for that
one symbol and returns measured token usage and cost. `adviser=1` remains the
explicit full council mode for operator use; it performs the additional,
larger 13-framework call and is never used by watchlists or automatic refresh.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYSIS_API_HOST` | `127.0.0.1` | Bind address. |
| `ANALYSIS_API_PORT` | `8770` | Bind port. |
| `ANALYSIS_API_ALLOW_LAN` | unset | Opt-in required before a non-loopback bind. |
| `ANALYSIS_API_TRUST_PROXY` | unset | Declares a reverse proxy in front; requires a credential database and makes the pairing throttle count the forwarded address. |
| `DEVICE_AUTH_DATABASE` | unset | `device_auth` credential file. Set it and every read demands a device token; leave it unset and no pairing path is served at all. |
| `ANALYSIS_API_ALLOWED_CLIENTS` | loopback | Comma-separated client CIDRs, required in LAN mode. |
| `ANALYSIS_API_GATEWAY_URL` | `http://127.0.0.1:8765` | Market gateway origin, loopback only. |
| `ANALYSIS_API_CANDLE_COUNT` | `200` | Candles requested per decision, 1–1000. |
| `ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS` | `10` | Bound on one gateway read. |
| `US_STOCK_HELPER_CONTACT_EMAIL` | unset | Contact address for the feed User-Agent; required, SEC EDGAR serves only clients it can reach. |
| `ANALYSIS_API_EVIDENCE_LOOKBACK_SECONDS` | `21600` | How far back each poll asks its sources. |
| `ANALYSIS_API_EVIDENCE_STALE_AFTER_SECONDS` | `86400` | Age past which a cited item is marked stale. |
| `ANALYSIS_API_EVIDENCE_RETENTION_SECONDS` | `604800` | Memory bound on collected evidence; must exceed the staleness window. |

`ANALYSIS_API_TOKEN` is gone. It was one static bearer token that every phone
shared, could not expire and could not be revoked one device at a time, so a
deployment that still sets it is stopped at startup rather than started with it
ignored. The gateway URL must be loopback: this service carries no gateway
credential and therefore cannot authenticate to a LAN gateway.

## Explicit iPhone LAN mode

Do not commit these values. Choose the actual Wi-Fi subnet used by the Mac and
iPhone, and point the credential database somewhere only this account can read:

```bash
export ANALYSIS_API_ALLOW_LAN=1
export ANALYSIS_API_HOST=0.0.0.0
export ANALYSIS_API_ALLOWED_CLIENTS=192.168.50.0/24
export DEVICE_AUTH_DATABASE="$HOME/.us-stock-helper/device-auth.sqlite3"
```

Print a pairing code with
`python3 -m us_stock_helper_device_auth pair --label "iPhone"` and type it into
the app. Every request then needs `Authorization: Bearer <device token>`, and
the app stores that token in the Keychain rather than in the bundle.

## Point-in-time mapping of gateway candles

Completed daily candles arrive through `GET /candles`; the envelope's `asOf` is
the decision cutoff. The gateway states two instants per completed candle, and
both are required:
`availableAt` is when the exchange published the bar and is the earliest moment
the chain may claim to have known it, `receivedAt` is when the gateway itself
held it. `availableAt` becomes the bar's `available_at`; `receivedAt` is checked
against it and against the candles envelope's `asOf`. Neither is ever defaulted
or substituted for the other — doing so would move the moment of knowledge
earlier than it really was.

Deterministic `currentPrice` intentionally remains the latest completed daily
close. Live quotes are a separate Watchlist/current-session input and never
change the daily analysis interval.

An unreachable gateway, an error envelope, or a candle missing either instant
raises `MarketGatewayUnavailable`. Only a gateway that answers with a genuinely
empty candle series yields no bars, which the contract reports as
`status: "unavailable"`.

## Where evidence comes from

Candles and evidence arrive from different systems and fail in different ways,
so they have separate providers and `CompositeAnalysisProvider` holds both. The
evidence half polls the public sources declared in `information_layer`'s source
registry — SEC EDGAR filings, Federal Reserve, BLS and BEA releases, and issuer
newsrooms.

A source that cannot be read raises rather than shrinking the result. This
matters because the chain treats thin evidence as a reason to hold back: if a
broken feed looked like a quiet market, that restraint would be triggered by an
outage rather than by the market. Only a round where every source answered can
produce an empty `citations` list.

The whole evidence path refuses to start without `US_STOCK_HELPER_CONTACT_EMAIL`
— EDGAR ships in the registry and serves only clients whose User-Agent names a
reachable contact, so an anonymous deployment has no evidence path at all and
should say so at startup instead of reporting an empty market per request.

## Run tests

```bash
PYTHONPATH=services/analysis_api/src:services/analysis_api/tests:services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m unittest discover -s services/analysis_api/tests -v
```
