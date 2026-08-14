# US Stock Helper mobile app

Expo/React Native client for the read-only US-stock assistant.

## Local dependencies and durable development runtime

Install mobile dependencies from `apps/mobile` when the lockfile changes:

```bash
npm install
```

Operate the development stack from the repository root. Do not start a second
foreground Metro:

```bash
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
python3 scripts/local_runtime.py reinstall
python3 scripts/local_runtime.py uninstall
```

The managed Expo dev-client Metro uses the validated Node 22 and Expo CLI paths
on canonical port `8088`. Listeners on `8081` or `8083` are legacy report-only
state and must not be killed or handed over by port. The retired
`scripts/run_local_dev_stack.sh` starts nothing and intentionally exits `2`.

Closing the shell that issued `install` must not stop Metro or the three API
components. Verify them from a fresh shell with `status` and `health` before
opening the app. Use `reinstall` after changing runtime configuration.

## Debug endpoint configuration

Runtime endpoints belong in an ignored `.env.local` or `.env`; never commit a
LAN token. The supported Debug variables are:

```dotenv
EXPO_PUBLIC_MARKET_API_URL=http://192.168.0.10:8766
EXPO_PUBLIC_MARKET_API_DEV_TOKEN=
EXPO_PUBLIC_ANALYSIS_API_URL=http://192.168.0.10:8770
EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN=
EXPO_PUBLIC_INITIAL_DEMO_MODE=false
```

Replace the example address with the allowlisted Mac LAN IP. `EXPO_PUBLIC_*`
values are compiled into client JavaScript and cannot be kept confidential;
bearer values are still sensitive, short-lived credentials that must never be
committed, logged, or shared.

For household Debug, `EXPO_PUBLIC_MARKET_API_DEV_TOKEN` must exactly match the
current `MOOMOO_GATEWAY_TOKEN` in `~/.us-stock-helper/lan.env`. Keep
`EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN` empty and use device pairing so the
revocable analysis token is stored in iOS Keychain. When rotating the market
token, update `lan.env` and `.env.local` together, run
`python3 scripts/local_runtime.py reinstall`, and reload the project from the
restarted Metro. Never leave the client and gateway on different token values.

`EXPO_PUBLIC_INITIAL_DEMO_MODE=true` opens deterministic Demo data for explicit
visual QA. Production bundles ignore the flag. App and native configuration
lives in `app.json`; this project does not use a Codex or Claude `config.yaml`.

See [the iPhone dev-client runbook](../../docs/runbooks/iphone-dev-client.md)
for the canonical `8088` launcher/deep-link path, signing, Fast Refresh, and
rebuild criteria.

## Household Debug versus Release/TestFlight

The LaunchAgent runtime plus plain-HTTP LAN endpoints is a Debug bridge only.
A Release/TestFlight build is accepted separately and must:

- run without Metro;
- connect to a paired HTTPS API;
- contain no static market token, analysis token, OpenD credential, or other
  development bearer value.

Do not interpret a working `8088` session as Release readiness.

## iOS native generation

The checked-in Expo config plugin sets React Native and Expo modules to build
from source. This keeps their linkage mode coherent with the pinned Expo/RN
versions when the ignored `ios/` project is regenerated.

```bash
npx expo prebuild --platform ios
cd ios
pod install
```

Rebuild after native dependency, app configuration, entitlement, signing, URL
scheme, or iOS-project changes. Ordinary `.ts` and `.tsx` edits use Fast
Refresh through the already installed development client.

## Verification

```bash
npm test -- --runInBand
npm run typecheck
```
