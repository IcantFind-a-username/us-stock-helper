# moomoo OpenD and market-gateway runbook

The two market gateways are read-only services managed by the durable local
runtime. OpenD is external and remains loopback-only on `127.0.0.1:11111`.
The desktop trading application is not a substitute for OpenD.

## Durable local operation

From the repository root, use the lifecycle CLI:

```bash
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
python3 scripts/local_runtime.py reinstall
python3 scripts/local_runtime.py uninstall
```

The fixed gateway contracts are:

| Purpose | Exact label | Listener |
| --- | --- | --- |
| analysis input | `com.franz.us-stock-helper.market-loopback` | `127.0.0.1:8765` |
| household-LAN Debug client | `com.franz.us-stock-helper.market-lan` | `0.0.0.0:8766` |

The loopback and LAN gateways are independent LaunchAgents. Closing the shell
that ran `install` does not stop them. `scripts/run_local_dev_stack.sh` is
retired, starts no Python or Node process, and intentionally exits `2` with the
migration command.

Unknown listeners on `8765` or `8766` block lifecycle mutation and receive no
signal. `8081` and `8083` are legacy Metro ports: they are report-only and must
not be killed or handed over based on port ownership.

`uninstall` removes only the four exact local-runtime labels/plists. It
preserves the private service env, device database, logs, and audited
`.tombstone`/`.staged` quarantine artifacts. See the
[local real-market runbook](../../docs/runbooks/local-real-market.md) for the
one-file-at-a-time quarantine review policy.

## Human-owned OpenD activation

1. Download, install, and start **moomoo OpenD** only from the official OpenAPI
   download page. Do not bypass macOS Gatekeeper, code-signing, or notarization
   failures.
2. Log in to OpenD and confirm its UI shows the quote server as connected.
3. Complete any US quote agreement or entitlement prompt shown by moomoo. The
   gateway cannot bypass account-region or quote-permission rules.
4. Keep OpenD listening only on `127.0.0.1:11111`.
5. Run `python3 scripts/local_runtime.py health`; do not expose credentials or
   raw provider text while investigating a failure.

OpenD is a readiness dependency, not a process-lifetime dependency. When it is
offline, each gateway stays alive and reports the fixed offline state. Start
and log in to OpenD, then repeat `health`; the next request should recover
without a gateway restart.

If OpenD is demonstrably connected but one gateway remains wedged, verify
ownership with `status`, then restart only the affected exact label:

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.market-loopback"
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.market-lan"
```

Choose one exact command. Never replace it with `kill`, `pkill`, or a command
selected only by port. Use `reinstall` for ordinary code or configuration
changes, and re-run status and health after either recovery path.

## Health interpretation

If the gateway health reports:

- `sdk-unavailable`: verify the managed process resolves the validated
  `services/market_gateway/.venv/bin/python`; do not install into system Python.
- `offline`: start OpenD and verify its loopback listener and UI session.
- `login-required`: log in inside OpenD; do not place credentials in this repo.
- `permission-denied`: accept the market-data agreement or obtain the required
  quote entitlement.
- `quota-exceeded`: wait for the provider window to reset; do not retry in a
  tight loop.
- `stale` or `malformed`: keep Real mode explicitly unavailable and inspect
  OpenD/SDK versions. Real mode never substitutes a fixture.
- `unsupported-capability`: upgrade the SDK/OpenD only after checking the
  official method/version requirements; do not generate substitute values.

The LAN gateway is a household-LAN Debug boundary. Its token and exact client
CIDR live in the private `~/.us-stock-helper/lan.env`; the file is parsed as
inert data and is never sourced. The ignored mobile
`EXPO_PUBLIC_MARKET_API_DEV_TOKEN` must exactly match the current
`MOOMOO_GATEWAY_TOKEN`. Although the Debug bundle cannot keep that bearer
confidential, it remains sensitive and must not be committed, logged, or
shared. Rotate `~/.us-stock-helper/lan.env` and `apps/mobile/.env.local`
together, run
`python3 scripts/local_runtime.py reinstall`, and reload the development client
from the restarted Metro.

The mobile `EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN` stays empty; analysis access
uses pairing and a revocable Keychain token. A Release/TestFlight client must
instead use a paired HTTPS API without a bundled market token or Metro
dependency.

## Fresh-shell verification

After installation, close the invoking terminal. In a fresh shell in the same
worktree, run:

```bash
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
```

Both gateway labels must remain independently observable. This is the durable
acceptance gate; a still-running parent shell is not evidence.

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
