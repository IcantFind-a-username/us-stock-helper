# Local Real-Market iPhone Runbook

This runbook operates the read-only local stack on one Mac. It is a
household-LAN **Debug** workflow, not a Release/TestFlight deployment, and it
never calls a brokerage transaction API.

## Fixed runtime contract

The durable runtime is four independent user LaunchAgents:

| Component | Exact label | Listener |
| --- | --- | --- |
| loopback market gateway | `com.franz.us-stock-helper.market-loopback` | `127.0.0.1:8765` |
| LAN market gateway | `com.franz.us-stock-helper.market-lan` | `0.0.0.0:8766` |
| analysis API | `com.franz.us-stock-helper.analysis-api` | `0.0.0.0:8770` |
| Expo dev-client Metro | `com.franz.us-stock-helper.metro` | `0.0.0.0:8088` |

`8088` is the only canonical Metro port. Listeners on `8081` or `8083` are
legacy evidence only: status reports them, but the lifecycle command never
signals, kills, or automatically hands them over. Never act on a PID merely
because it owns one of those ports.

OpenD remains an external desktop dependency on `127.0.0.1:11111`. The
gateway stays running while OpenD is offline and reports that condition until
OpenD is available again.

The retired `scripts/run_local_dev_stack.sh` no longer starts anything. It
prints the migration command and intentionally exits `2`, so old automation
cannot mistake the notice for a running stack.

## Security and deployment boundary

The local LaunchAgents and plain-HTTP LAN listeners are for a trusted
household network and Debug build only. Restrict both LAN services to the exact
phone subnet. Debug `EXPO_PUBLIC_*` values are bundled into client JavaScript
and cannot be kept confidential. A bearer value remains a sensitive,
short-lived credential despite that limitation: never commit, log, or share it.

A production Release/TestFlight build is a separate acceptance gate. It must:

- work without Metro;
- use a paired HTTPS API rather than the direct LAN gateway;
- contain no static market token, analysis token, OpenD credential, or other
  `EXPO_PUBLIC_*` development credential.

This local runtime does not claim that production gate has passed.

## Prerequisites and private configuration

- OpenD is installed from the official source, logged in to the user's
  Singapore moomoo account, and entitled for US quotes.
- The Mac and iPhone share a mutually reachable private network.
- Node 22, the checked-in mobile dependencies, the market-gateway virtual
  environment, and its CA bundle are present at the paths validated by the
  runtime.
- The installed Expo development client follows
  [iphone-dev-client.md](iphone-dev-client.md).

Service credentials remain in the operator-owned
`~/.us-stock-helper/lan.env`. Its parent must be mode `0700`, the file must be
mode `0600`, and its contents are inert `KEY=VALUE` data. Do not `source` it,
put shell syntax in it, print it, or copy it into the repository. The runtime
parser supplies only the allowlisted values each component needs; market and
Metro never receive the Anthropic key, and analysis never receives the market
token.

The durable stack requires these operator values; describe them in an editor,
not by exporting or echoing them in shell history:

| Key | Purpose |
| --- | --- |
| `MOOMOO_GATEWAY_ALLOWED_CLIENTS` | exact household-LAN CIDR allowed to reach `8766` |
| `MOOMOO_GATEWAY_TOKEN` | high-entropy, short-lived Debug gateway token |
| `ANALYSIS_API_ALLOWED_CLIENTS` | exact household-LAN CIDR allowed to reach `8770` |
| `US_STOCK_HELPER_CONTACT_EMAIL` | reachable contact for public-source User-Agent policy |
| `ANTHROPIC_API_KEY` | optional, analysis-only key for explicit paid adviser actions |

Mobile Debug endpoints belong in ignored `apps/mobile/.env.local` or
`apps/mobile/.env`. They must point to the Mac LAN address on `8766` and
`8770`, with `EXPO_PUBLIC_INITIAL_DEMO_MODE=false`. This project does not use
`config.yaml`; the private service env and ignored Expo env are the two
intentional local configuration boundaries.

`EXPO_PUBLIC_MARKET_API_DEV_TOKEN` must exactly equal the current
`MOOMOO_GATEWAY_TOKEN` in `lan.env`. Leave
`EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN` empty; use the one-time pairing flow and
let the app store the revocable analysis token in Keychain. To rotate the Debug
market token, update `lan.env` and `.env.local` together, run
`python3 scripts/local_runtime.py reinstall`, then reload the development
client from the restarted Metro. Do not leave either side on the prior value.

## Install and operate the stack

Run every lifecycle command from the exact worktree that should remain pinned:

```bash
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py status --json
python3 scripts/local_runtime.py health
python3 scripts/local_runtime.py health --json
python3 scripts/local_runtime.py reinstall
python3 scripts/local_runtime.py uninstall
```

- `install` validates all four rendered plists and all ownership boundaries
  before installing or bootstrapping any label.
- `status` reports each fixed component independently and reports legacy
  `8081`/`8083` listeners without changing them.
- `health` makes bounded, credential-free checks. A protected `401`/`403` is
  evidence that the LAN boundary is reachable, not permission to print or
  bypass a credential.
- `reinstall` is the normal way to load runtime/code/configuration changes. It
  operates only after exact ownership has been re-established.
- `uninstall` boots out and removes only the four exact managed plists. It
  preserves `~/.us-stock-helper/lan.env`,
  `~/.us-stock-helper/state/devices.sqlite3`, all logs, and forensic
  quarantine artifacts.

An unknown listener on `8765`, `8766`, `8770`, or `8088` makes a mutating
command fail closed and receives no signal. Inspect the full executable,
arguments, working directory, PID, and start time before deciding what owns an
unexpected process.

## OpenD offline recovery

Do not restart the gateways merely because OpenD is offline.

1. Start OpenD, log in, and wait until its UI shows the quote service as
   connected on `127.0.0.1:11111`.
2. Run `python3 scripts/local_runtime.py health` again. The loopback gateway
   should recover on a later request without a gateway restart.
3. If OpenD is healthy but a gateway remains wedged, first run
   `python3 scripts/local_runtime.py status`. Then restart only the exact owned
   label that needs recovery:

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.market-loopback"
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.market-lan"
```

Choose one command, not both by habit, and re-run status and health afterward.
Never replace an exact-label restart with a port-based kill. The same isolation
rule applies to the other two managed labels when explicitly testing restart
behavior:

```bash
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.analysis-api"
launchctl kickstart -k "gui/$(id -u)/com.franz.us-stock-helper.metro"
```

For ordinary updates use `reinstall`; direct `kickstart -k` is an exceptional
single-component recovery or acceptance step.

## Fresh-shell durability proof

After a successful install, close the shell or Codex session that issued it.
Open a fresh terminal, enter the same worktree, and run:

```bash
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
```

All four labels must still be independently observable. This fresh-shell gate,
not the lifetime of a foreground supervisor, proves terminal independence.

## Deterministic offline proof

From the repository root:

```bash
PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --fixture services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json

PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --contract-version v3 --symbol AVGO --interval day --count 250 \
  --fixture services/market_gateway/tests/fixtures/snapshot_v3_anomalous_holdings.json
```

Expected:

```text
PASS snapshot=NVDA candles>0 valid_participation>0 future_rows=0
```

The replay contains only contract timestamps and numeric market rows. It fails
closed on an unhealthy OpenD, empty or invalid candles, future data, incomplete
repairs, or an accidental transaction capability. Fixtures are an explicitly
selected Demo/offline proof; Real mode never falls back to them.

## Live smoke

First confirm runtime state through the lifecycle CLI, then issue one live
daily snapshot through the loopback gateway:

```bash
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health

PYTHONPATH=services/analysis_core:services/market_gateway/src \
  python3 services/market_gateway/scripts/smoke_real_snapshot.py \
  --contract-version v3 --symbol SOFI --interval day --count 250 \
  --base-url http://127.0.0.1:8765
```

For the complete Watchlist gate, use one paired device for the whole run and
write only a permission-restricted report outside the repository:

```bash
umask 077
MAC_LAN_IP="<allowlisted Mac LAN IP>"
PYTHONPATH=services/device_auth/src \
  python3 scripts/smoke_live.py \
  --gateway-url http://127.0.0.1:8765 \
  --analysis-url "http://${MAC_LAN_IP}:8770" \
  --device-database "$HOME/.us-stock-helper/state/devices.sqlite3" \
  --all-watchlist --snapshot-version v3 \
  --interval day --count 250 --horizon short \
  --report /tmp/us-stock-helper-watchlist-v3.json
```

The batch reads market data from loopback `8765` and device-authenticated
analysis from `8770`. Do not widen the client allowlist merely to make the
smoke pass. It preserves Watchlist order, uses one device token until its
guaranteed revocation, and excludes provider text, credentials, response
reasons, and environment data from its mode-`0600` report.

## Quarantine artifacts and manual review

Trusted plist replacement/removal never overwrites or automatically deletes an
unknown same-user file. Prior verified plists and failed stages therefore stay
under `~/Library/LaunchAgents` with names ending in `.tombstone` or `.staged`.
They are mode `0600`, never end in `.plist`, and are ignored by exact-path
runtime ownership and by launchd plist loading.

The runtime caps the combined `.tombstone`/`.staged` artifacts at `1024` per
managed target. At the cap, mutation fails closed with a quarantine-full error;
it does not weaken the check or bulk-delete evidence. Ordinary uninstall also
leaves these artifacts intact.

The first hash in each artifact name identifies the canonical target:

| Artifact prefix | Managed plist |
| --- | --- |
| `.us-stock-helper.75f62f3f7959fd0a.` | `com.franz.us-stock-helper.market-loopback.plist` |
| `.us-stock-helper.066f2c2eda3c50cd.` | `com.franz.us-stock-helper.market-lan.plist` |
| `.us-stock-helper.ff4111646502099f.` | `com.franz.us-stock-helper.analysis-api.plist` |
| `.us-stock-helper.4c02da3b685845a8.` | `com.franz.us-stock-helper.metro.plist` |

Do not enumerate this directory with a shell wildcard or `find`. Read-only
inspection is limited to one exact literal artifact path supplied by a reviewed
lifecycle diagnostic. For that one path, an auditor may `lstat`, open
read-only/no-follow, `fstat`, hash, and parse the plist only after verifying all
of these conditions:

- the path is directly under the current user's `~/Library/LaunchAgents`;
- `lstat` and the opened descriptor identify the same regular file owned by the
  current uid at mode `0600`;
- its basename has exactly one of the four prefixes in the table above and ends
  in `.tombstone` or `.staged`, never `.plist`;
- its label and fixed launch contract match the mapped managed plist;
- every operation remains read-only and emits no credential-bearing content.

This runbook intentionally provides no delete, move, glob, directory-inventory,
recursive-cleanup, or automated-retention command. If the `1024` cap is reached,
stop the lifecycle mutation, preserve every artifact, and escalate either to a
reviewed lifecycle-tool change or to a separately approved manual forensic
procedure. Read-only verification does not authorize cleanup. If any ownership
or content is unclear, leave the artifact in place.

## Physical iPhone acceptance

Confirm the device is connected before making any device claim:

```bash
xcrun devicectl list devices
```

If it is absent, stop device acceptance rather than inferring success. If it is
connected, follow [iphone-dev-client.md](iphone-dev-client.md), then verify:

- Dashboard Watchlist matches moomoo and audited symbols open without duplicate
  rows or render errors.
- The chart defaults to `日K`; every successful decision states `interval: day`;
  Magic Nine and other indicators share the daily cutoff.
- Quote, chart, and decision remain available when optional holdings are
  anomalous or unavailable.
- Current-session flow remains separate from the daily price basis.
- After an intentional OpenD stop, Real mode becomes unavailable without a
  crash; after OpenD restarts and logs in, live daily data returns without
  splicing an unknown interval.
- No Real screen contains a fixture conclusion or Demo badge.

Do not stop OpenD until the initial live state is recorded, and do not call any
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

Both searches must have no matches. Keep live responses and reports outside the
repository with mode `0600`, redact them before sharing, and remove them only
under the operator's normal audited retention process.
