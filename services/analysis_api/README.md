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

The analysis service does not read `/stock-snapshot`, `/v2/stock-snapshot`, or
`/v3/stock-snapshot`. Its deterministic price path reads only `/candles` with
`interval=day` by default, so delayed holdings, current-session order-size flow,
and every other optional snapshot section cannot change a score or its daily
price basis. A live quote remains a separate Watchlist/current-session value.
The two point-in-time boundaries on that candle envelope are defined below;
the decision still prices from the latest completed daily close.

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

## Operate the durable local service

`market_gateway` must already be serving on the same host; its `/candles`
endpoint is this service's only deterministic price source. Optional sections
of a stock snapshot, including holdings, cannot affect a decision.

From the repository root, use the lifecycle CLI instead of starting a
foreground Python process:

```bash
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
python3 scripts/local_runtime.py reinstall
python3 scripts/local_runtime.py uninstall
```

The exact analysis label is `com.franz.us-stock-helper.analysis-api`, bound to
`0.0.0.0:8770` for the allowlisted household LAN. The protected health result
is checked without printing credentials. Closing the installing shell does not
stop the service; verify that property from a fresh shell with `status` and
`health`.

For exceptional single-component recovery after ownership is verified:

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"
```

Use `reinstall` for normal code/configuration changes. Never replace an exact
label with a PID or port-based kill. Metro is canonical only on `8088`;
listeners on `8081`/`8083` are report-only legacy state.

Ordinary uninstall preserves `~/.us-stock-helper/lan.env`, the durable pairing
database at `~/.us-stock-helper/state/devices.sqlite3`, logs, and non-plist
quarantine artifacts. The foreground `scripts/run_local_dev_stack.sh` is
retired and intentionally exits `2` without starting anything.

The default decision request never calls a model. The phone's paid button sends
`adviser=news`, which performs one traceable news-interpretation call for that
one symbol and returns measured token usage and cost. `adviser=1` remains the
explicit full council mode for operator use; it performs the additional,
larger 13-framework call and is never used by watchlists or automatic refresh.

The table below describes the application parser's standalone defaults. The
durable local launcher fixes the LAN host/port, loopback gateway URL, and
`DEVICE_AUTH_DATABASE=$HOME/.us-stock-helper/state/devices.sqlite3`.

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
| `ANALYSIS_API_BREADTH_UNIVERSE` | unset | Comma-separated US symbols (≤60) for `GET /market-brief`'s breadth driver. Unset falls back to the operator's watchlist, read live from the gateway's `GET /watchlist`; neither source leaves breadth `available: false`. |
| `ANALYSIS_API_SECTOR_RS_SYMBOLS` | unset | Comma-separated sector-ETF symbols (≤30) for the brief's sector-RS driver. Must be set together with `ANALYSIS_API_SECTOR_RS_BENCHMARK`. |
| `ANALYSIS_API_SECTOR_RS_BENCHMARK` | unset | Single benchmark symbol (e.g. `SPY`) for sector-RS. Must be set together with `ANALYSIS_API_SECTOR_RS_SYMBOLS`. |

`ANALYSIS_API_TOKEN` is gone. It was one static bearer token that every phone
shared, could not expire and could not be revoked one device at a time, so a
deployment that still sets it is stopped at startup rather than started with it
ignored. The gateway URL must be loopback: this service carries no gateway
credential and therefore cannot authenticate to a LAN gateway.

## Explicit iPhone LAN mode

This is a household-LAN Debug workflow. Put the exact phone CIDR in the private
`~/.us-stock-helper/lan.env` as `ANALYSIS_API_ALLOWED_CLIENTS`; the runtime
supplies the fixed LAN host/port, loopback gateway URL, and durable pairing path
without sourcing the file. Do not export an ad-hoc second server or commit the
values.

Create a short-lived pairing code against the same durable database used by the
LaunchAgent:

```bash
DEVICE_AUTH_DATABASE="$HOME/.us-stock-helper/state/devices.sqlite3" \
PYTHONPATH=services/device_auth/src \
  services/market_gateway/.venv/bin/python \
  -m us_stock_helper_device_auth pair --label "iPhone"
```

Type the code into the app rather than a shell log or issue tracker. Every
request then needs `Authorization: Bearer <device token>`, and the app stores
the resulting token in Keychain rather than in the bundle.

Leave `EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN` empty. A static analysis token in
`.env.local` would bypass the intended pairing/Keychain lifecycle and must not
be used. The separate `EXPO_PUBLIC_MARKET_API_DEV_TOKEN` must exactly equal the
current `MOOMOO_GATEWAY_TOKEN` in `~/.us-stock-helper/lan.env`. Rotate
`lan.env` and `apps/mobile/.env.local` together, run
`python3 scripts/local_runtime.py reinstall`, and reload Metro.

The Debug client may use ignored `EXPO_PUBLIC_*` LAN endpoint values, which are
visible in its JavaScript bundle and remain sensitive even though they cannot
be kept confidential there. Never commit, log, or share a bearer value. A
Release/TestFlight build is a separate gate: it must use the paired HTTPS
boundary without Metro or any static market or analysis token.

## Point-in-time mapping of gateway candles

Completed daily candles arrive through `GET /candles`. The envelope's `asOf` is
the latest data publication/measurement boundary; its `availableAt` is the
batch receipt boundary at which the gateway held the response. The gateway
also states two required instants per completed candle: row `availableAt` is
when the exchange published the bar and is the earliest moment the chain may
claim to have known it, while row `receivedAt` is when the gateway itself held
that row. The boundary enforces `row.availableAt <= envelope.asOf`,
`row.receivedAt <= envelope.availableAt`, and
`envelope.asOf <= envelope.availableAt`. Row `availableAt` becomes the domain
bar's `available_at`. No instant is defaulted or substituted for another —
doing so would move the moment of knowledge earlier than it really was.

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
# Absolute paths are required: one test spawns a subprocess with a different
# working directory, and relative PYTHONPATH entries stop resolving there.
PYTHONPATH=$PWD/services/analysis_api/src:$PWD/services/analysis_api/tests:$PWD/services/analysis_core:$PWD/services/information_layer:$PWD/services/adviser_layer:$PWD/services/decision_engine:$PWD/services/market_gateway/src:$PWD/services/adviser_llm/src:$PWD/services/device_auth/src \
  python3 -m unittest discover -s services/analysis_api/tests -v
```
