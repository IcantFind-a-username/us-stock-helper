# Local Real-Market iPhone Runbook

This runbook proves the read-only moomoo vertical slice on one Mac and one
physical iPhone. It never calls a brokerage transaction API.

## Prerequisites

- OpenD listens on `127.0.0.1:11111`.
- OpenD is logged in to the user's Singapore moomoo account and that account
  has US quote permission.
- The Mac and iPhone share a mutually reachable network.
- The installed Expo development client follows
  [iphone-dev-client.md](iphone-dev-client.md). Keep the existing Metro process
  when it is already serving the correct worktree.

The desktop trading application is not a substitute for OpenD. Do not expose
port `11111` on the LAN and do not put an account identifier, login material,
watchlist, cookie, bearer token, or runtime output in the repository.

## Deterministic offline proof

From the repository root:

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --fixture services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json
```

Expected:

```text
PASS snapshot=NVDA candles>0 valid_participation>0 future_rows=0
```

The replay contains only the contract timestamps and numeric market rows needed
to reproduce validation. The smoke fails closed on an unhealthy OpenD, an
empty candle series, a future source child, unordered or duplicate candles,
misaligned participation, any invalid share without tolerance, a partial
repair, or an accidental transaction capability.

## Latest loopback gateway and live smoke

First identify listeners. Do not stop a process based on a port number alone:

```bash
lsof -nP -iTCP:11111 -sTCP:LISTEN
lsof -nP -iTCP:8765 -sTCP:LISTEN
ps -p <8765-pid> -o pid=,ppid=,command=
```

If port `8765` is owned by an older gateway, record its PID and full command.
Stop only the PID whose command is the Python
`us_stock_helper_market_gateway` process on `8765`; never stop OpenD or an
unrelated listener. Start the gateway from the current worktree using the
Python environment that contains the moomoo SDK:

```bash
umask 077
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  services/market_gateway/.venv/bin/python \
  -m us_stock_helper_market_gateway
```

In another terminal:

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --symbol NVDA --interval 5m --count 200 \
  --base-url http://127.0.0.1:8765
```

The validator issues only `GET /health` and `GET /stock-snapshot`. A valid live
response has real completed candles, at least one currently covered
trading-day participation bar, explicit unavailable older bars, one decision
cutoff for every source child, and no transaction capability.

## Temporary iPhone LAN runtime

For the already paired local development setup, keep all three read-only
services in one foreground supervisor:

```bash
scripts/run_local_dev_stack.sh
```

It reads the existing operator-owned
`~/.us-stock-helper/lan.env`, writes only redacted process logs under `/tmp`,
and stops the remaining services if any one of them exits. It does not contain
or print the market token, device credentials, or an Anthropic key. Run it in a
terminal or a user launch job when the stack must survive a calling shell.

The lower-level commands below remain useful when bringing up only the market
gateway or rotating the LAN token.

Choose the Mac's active LAN address and the exact CIDR that contains only the
phone network. Generate a fresh 32-byte token for every session:

```bash
export MOOMOO_GATEWAY_ALLOW_LAN=1
export MOOMOO_GATEWAY_HOST=0.0.0.0
export MOOMOO_GATEWAY_ALLOWED_CLIENTS=192.168.50.0/24
export MOOMOO_GATEWAY_TOKEN="$(openssl rand -hex 32)"
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  services/market_gateway/.venv/bin/python \
  -m us_stock_helper_market_gateway
```

Use the real Mac LAN IP, not loopback, in the development client:

```bash
cd apps/mobile
export EXPO_PUBLIC_MARKET_API_URL=http://192.168.50.10:8765
export EXPO_PUBLIC_MARKET_API_DEV_TOKEN="$MOOMOO_GATEWAY_TOKEN"
npm run start:dev-client -- --lan --port 8088
```

Run Metro from a shell that has received the same in-memory runtime token; do
not paste it into a committed script or shell history. The smoke CLI also reads
`MOOMOO_GATEWAY_TOKEN` from its environment and sends it only in the
Authorization header, so the LAN path can be checked before opening the app:

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --symbol NVDA --interval 5m --count 200 \
  --base-url http://192.168.50.10:8765
```

Replace the example IP and CIDR with the current network values. The temporary
LAN token is development-only. It must never be committed, logged, hardcoded,
stored in a fixture, or included in a release build. Production runtime rejects
development tokens.

## Physical iPhone acceptance

Confirm the device is connected before making any device claim:

```bash
xcrun devicectl list devices
```

If it is absent, stop device acceptance and report `DONE_WITH_CONCERNS`; do not
infer installation or launch success. If it is connected, follow the signed
install and launch steps in [iphone-dev-client.md](iphone-dev-client.md), then
record each observed result:

- Dashboard watchlist matches moomoo.
- NVDA opens once without duplicate rows or render errors.
- Actual completed K-lines appear.
- Supported K-lines have aligned, constant-height stacked participation bars.
- Every available bar totals exactly 100%; unsupported older bars are visibly
  missing, never interpolated or repaired.
- RSI, MACD, MA5, and Magic Nine show the same decision cutoff.
- After an intentional OpenD stop, the app becomes unavailable without
  crashing; after OpenD restarts and logs in, it returns to live without
  splicing an unknown interval.
- A live screen contains no forecast and no fixture conclusion.

Do not stop OpenD until the initial live state is recorded. Do not call any
transaction endpoint during this test.

## Final safety checks

```bash
rg -ni \
  '"(account(id)?|login|watchlist|cookie|token|authorization|trade(data)?)"[[:space:]]*:' \
  services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json
rg -n \
  'OpenSecTradeContext|unlock_trade|place_order|modify_order|cancel_order' \
  services apps/mobile
git status --short
```

Both searches must have no matches. Keep any live response or process log under
a permission-restricted temporary directory outside the repository, redact it
before sharing, and delete it after the acceptance record is written.
