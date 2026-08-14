# moomoo OpenD activation runbook

## Current Mac preflight (2026-07-25)

- `/Applications/moomoo.app` exists.
- No process is listening on TCP port `11111`.
- Official `moomoo-api 10.9.6908` is installed only in
  `services/market_gateway/.venv`; system Python is unchanged.
- The production connectivity probe reports `OPEND_OFFLINE` in approximately
  `0.002s`, before the SDK can enter its long retry loop.

This means the code and SDK are ready, but the app cannot claim live moomoo
data until a verified OpenD is running and authenticated.

## Remaining human-owned OpenD steps

1. Download, install, and start **moomoo OpenD** only from the official OpenAPI
   download page. Do not bypass macOS Gatekeeper, code-signing, or notarization
   failures. The already-installed moomoo desktop app alone is insufficient.
2. Log in to OpenD and confirm the OpenD UI shows the quote server as connected.
3. Complete any US quote agreement or entitlement prompt shown by moomoo. The
   gateway cannot bypass account-region or quote-permission rules.
4. Keep OpenD listening on the default loopback address and port
   `127.0.0.1:11111`.
5. Verify `/health` reports `session: "healthy"` before allowing the iOS client
   to replace fixture data.

If `/health` reports:

- `sdk-unavailable`: verify the process is using
  `services/market_gateway/.venv/bin/python`; do not install into system Python.
- `offline`: start OpenD and verify port `11111`.
- `login-required`: log in inside OpenD; do not place credentials in this repo.
- `permission-denied`: accept the relevant market-data agreement or obtain the
  required quote entitlement in the moomoo account.
- `quota-exceeded`: wait for the provider window to reset; do not retry in a
  tight loop.
- `stale` or `malformed`: keep Real mode explicitly unavailable and inspect
  OpenD/SDK versions before changing the validation gate. Fixtures are only for
  an explicitly selected Demo/offline replay; Real mode never falls back to
  them.
- `unsupported-capability`: upgrade the SDK/OpenD only after checking the
  official method/version requirements. Do not substitute generated values.

## Evidence and official docs

- Watchlist:
  https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-user-security.html
- Market snapshot:
  https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-market-snapshot.html
- Historical candles:
  https://openapi.moomoo.com/moomoo-api-doc/en/quote/request-history-kline.html
- Global state:
  https://openapi.moomoo.com/moomoo-api-doc/quote/get-global-state.html
- Capital flow:
  https://openapi.moomoo.com/moomoo-api-doc/quote/get-capital-flow.html
- Capital distribution:
  https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-capital-distribution.html
- Institutional holdings:
  https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-shareholders-institutional.html

The official docs state that US snapshot and historical K-line timestamps use
US Eastern time. The adapter attaches `America/New_York`, including daylight
saving transitions, and converts all mobile output to UTC.
