# Read-only moomoo market gateway

This service is the only boundary between the app and moomoo OpenD. It exposes
quotes, the user's watchlist, completed historical candles, explicitly labelled
capital-flow proxies, and delayed institutional disclosures. It contains no
brokerage context, order endpoint, or order-capable route.

## Safety invariants

- `OpenQuoteContext` is the only OpenD context constructed.
- The HTTP allowlist is exactly `GET /health`, `/watchlist`, `/quotes`,
  `/candles`, `/capital-flow`, `/capital-distribution`, and
  `/institutional-holdings`; write methods fail closed.
- A response can use `session: "healthy"` only when the OpenD health check and
  the just-received provider batch are fresh and identify `source: "moomoo"`.
- Every timestamp returned to the app is timezone-aware UTC.
- Incomplete or not-yet-available candles never enter the mobile JSON response.
- Capital flow and order-size distribution carry
  `institutionalIdentity: false`. They are large-order/transaction-size
  proxies, not proof that an institution bought or sold.
- Institutional holdings are delayed disclosures. Every row preserves separate
  `reportedAt` and `availableAt` timestamps plus its disclosure source.
  `reportedAtBasis: "reporting-period-end"` makes clear that OpenD supplies a
  reporting quarter, not an exact filing timestamp.
- SDK versions that do not expose an optional quote method return
  `UNSUPPORTED_CAPABILITY`; the gateway never fabricates a replacement value.
- Provider errors are classified and sanitized. Raw SDK errors, credentials,
  tokens, cookies, account identifiers, and environment values are never
  returned.
- The default listener is `127.0.0.1`; LAN access requires an explicit opt-in,
  a runtime token, and an explicit client CIDR.

## Mobile JSON contract

A successful watchlist or quote snapshot has this shape:

```json
{
  "schemaVersion": "1",
  "source": "moomoo",
  "session": "healthy",
  "asOf": "2026-07-25T15:59:49Z",
  "availableAt": "2026-07-25T15:59:51Z",
  "items": [
    {
      "code": "US.NVDA",
      "price": 142.25,
      "changePercent": 2.4,
      "availableAt": "2026-07-25T15:59:49Z"
    }
  ]
}
```

Completed candles add top-level `symbol` and `interval`. Each item contains
`timestamp`, `availableAt`, `complete`, and numeric OHLCV fields. Operational
failures keep the same envelope, use a non-healthy `session`, return an empty
`items` array, and add a sanitized `error` object.

`timestamp` is the bar-close time, not the bar-open label returned by OpenD.
This prevents an in-progress bar from being treated as known before it closes.

## Run tests

No third-party package is required for the deterministic tests:

```bash
PYTHONPATH=services/market_gateway/src \
  python3 -m unittest discover -s services/market_gateway/tests -v
```

## Run against OpenD

The SDK is optional so a machine without it degrades to `SDK_UNAVAILABLE`
instead of crashing. This workspace already has the official SDK isolated at
`services/market_gateway/.venv`; it does not modify the system Python.

```bash
PYTHONPATH=services/market_gateway/src \
  services/market_gateway/.venv/bin/python \
  -m us_stock_helper_market_gateway
```

OpenD must already be running, logged in to the quote server, and listening on
`127.0.0.1:11111`. The regular moomoo desktop trading app does not replace
OpenD.

Before importing the SDK or constructing `OpenQuoteContext`, the adapter runs a
one-second TCP probe. A stopped OpenD therefore fails quickly as
`OPEND_OFFLINE`, instead of entering the SDK's long connection retry loop.

Check status:

```bash
curl --fail --silent --show-error http://127.0.0.1:8765/health
curl --fail --silent --show-error http://127.0.0.1:8765/watchlist
curl --fail --silent --show-error \
  'http://127.0.0.1:8765/quotes?symbols=NVDA,TSLA'
curl --fail --silent --show-error \
  'http://127.0.0.1:8765/candles?symbol=NVDA&interval=5m&count=200'
curl --fail --silent --show-error \
  'http://127.0.0.1:8765/capital-flow?symbol=NVDA'
curl --fail --silent --show-error \
  'http://127.0.0.1:8765/capital-distribution?symbol=NVDA'
curl --fail --silent --show-error \
  'http://127.0.0.1:8765/institutional-holdings?symbol=NVDA'
```

## Explicit iPhone LAN mode

Do not commit these values. Generate the token at runtime and choose the actual
Wi-Fi subnet used by the Mac and iPhone:

```bash
export MOOMOO_GATEWAY_ALLOW_LAN=1
export MOOMOO_GATEWAY_HOST=0.0.0.0
export MOOMOO_GATEWAY_TOKEN="$(openssl rand -hex 32)"
export MOOMOO_GATEWAY_ALLOWED_CLIENTS=192.168.50.0/24
us-stock-helper-market-gateway
```

The iOS client must retrieve the token from Keychain or an equivalent runtime
secret source and send `Authorization: Bearer <token>`. It must never hardcode
the token into the app bundle. Browser access additionally requires an exact
`MOOMOO_GATEWAY_ALLOWED_ORIGINS` list. Native iOS requests normally do not send
an `Origin` header.

## Official interfaces used

- `get_global_state()` for quote-server login health
- `get_user_security(group_name)` for the selected watchlist group
- `get_market_snapshot(codes)` for current price and update time
- `request_history_kline(...)` for paginated historical candles
- `get_capital_flow(code)` for transaction-size flow proxies
- `get_capital_distribution(code)` for order-size inflow/outflow buckets
- `get_shareholders_institutional(code, ...)` for delayed holdings history

See the official moomoo OpenAPI documentation linked from the repository
runbook before upgrading the SDK or changing field mappings.
