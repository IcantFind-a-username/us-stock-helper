# analysis_api

The read-only HTTP boundary for the point-in-time decision chain. It composes
`information_layer`, `analysis_core`, `adviser_layer` and `decision_engine`
behind two GET paths and turns their output into one JSON answer the app can
render.

## Safety invariants

- The path allowlist is exactly `GET /health` and `GET /decision`; every write
  method fails closed with 405.
- No field in any response can carry an order, an account or a credential, and
  the risk plan states in its own warnings that it cannot place one.
- Provider failures are replaced with a fixed message: their text can contain
  credentials.

## What the contract refuses to hide

The chain declines to state some things, and those refusals travel to the
screen rather than being smoothed over in serialization:

- `score.factorCoverage` and `score.unavailableFactors` — macro, geopolitical,
  institutional-flow and fundamental factors have no feed yet, so a score is
  explicitly partial rather than quietly averaging in judgements nobody made.
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

`market_gateway` must already be serving on the same host; its
`/stock-snapshot` candles are this service's only price source.

```bash
PYTHONPATH=services/analysis_api/src:services/analysis_core:services/information_layer:services/adviser_layer:services/decision_engine \
  python3 -m us_stock_helper_analysis_api

curl --fail --silent --show-error http://127.0.0.1:8770/health
curl --fail --silent --show-error \
  'http://127.0.0.1:8770/decision?symbol=NVDA&horizon=short'
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYSIS_API_HOST` | `127.0.0.1` | Bind address. |
| `ANALYSIS_API_PORT` | `8770` | Bind port. |
| `ANALYSIS_API_ALLOW_LAN` | unset | Opt-in required before a non-loopback bind. |
| `ANALYSIS_API_TOKEN` | unset | Bearer token, 32+ characters, required in LAN mode. |
| `ANALYSIS_API_ALLOWED_CLIENTS` | loopback | Comma-separated client CIDRs, required in LAN mode. |
| `ANALYSIS_API_GATEWAY_URL` | `http://127.0.0.1:8765` | Market gateway origin, loopback only. |
| `ANALYSIS_API_CANDLE_COUNT` | `200` | Candles requested per decision, 1–1000. |
| `ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS` | `10` | Bound on one gateway read. |
| `US_STOCK_HELPER_CONTACT_EMAIL` | unset | Contact address for the feed User-Agent; required, SEC EDGAR serves only clients it can reach. |
| `ANALYSIS_API_EVIDENCE_LOOKBACK_SECONDS` | `21600` | How far back each poll asks its sources. |
| `ANALYSIS_API_EVIDENCE_STALE_AFTER_SECONDS` | `86400` | Age past which a cited item is marked stale. |
| `ANALYSIS_API_EVIDENCE_RETENTION_SECONDS` | `604800` | Memory bound on collected evidence; must exceed the staleness window. |

A loopback deployment ignores any token that is set, because a token that is
never demanded reads as protection that does not exist. The gateway URL must be
loopback: this service carries no gateway credential and therefore cannot
authenticate to a LAN gateway.

## Explicit iPhone LAN mode

Do not commit these values. Generate the token at runtime and choose the actual
Wi-Fi subnet used by the Mac and iPhone:

```bash
export ANALYSIS_API_ALLOW_LAN=1
export ANALYSIS_API_HOST=0.0.0.0
export ANALYSIS_API_TOKEN="$(openssl rand -hex 32)"
export ANALYSIS_API_ALLOWED_CLIENTS=192.168.50.0/24
```

Every request then needs `Authorization: Bearer <token>`, and the iOS client
must read that token from Keychain rather than hardcode it into the bundle.

## Point-in-time mapping of gateway candles

The gateway states two instants per completed candle, and both are required:
`availableAt` is when the exchange published the bar and is the earliest moment
the chain may claim to have known it, `receivedAt` is when the gateway itself
held it. `availableAt` becomes the bar's `available_at`; `receivedAt` is checked
against it and against the snapshot's own `decisionCutoff`. Neither is ever
defaulted or substituted for the other — doing so would move the moment of
knowledge earlier than it really was.

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
