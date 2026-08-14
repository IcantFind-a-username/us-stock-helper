# iPhone Dev Client Installation

The native project is an Expo development build, not Expo Go. JavaScript and
TypeScript UI changes use Fast Refresh; native dependency, app configuration,
scheme, entitlement, signing, or iOS-project changes require a rebuild.

## Verified project settings

- Workspace: `apps/mobile/ios/USStockHelper.xcworkspace`
- Scheme: `USStockHelper`
- URL scheme: `usstockhelper`
- Bundle identifier: `com.franz.usstockhelper.dev`
- Minimum iOS version: 16.4
- Node: `/opt/homebrew/opt/node@22/bin/node`
- Canonical Metro: `0.0.0.0:8088`
- Simulator Debug build: verified with `BUILD SUCCEEDED`
- Physical iPhone Debug build: verified on 2026-07-25
- Installed app: verified as `US Stock Helper 0.1.0 (1)` on the connected
  iPhone; installation does not itself launch the app

`8081` and `8083` are legacy listener ports. They may be reported by runtime
status, but they are never migration targets and must not be killed by port
alone.

## Start or verify the durable development runtime

From the repository root, use the lifecycle CLI rather than a foreground Metro
command:

```bash
python3 scripts/local_runtime.py install
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
```

The Metro LaunchAgent runs the absolute Node 22 and Expo CLI paths with
`start --dev-client --lan --port 8088`. It remains alive after the installing
terminal closes. `scripts/run_local_dev_stack.sh` is a retired fail-fast shim;
it intentionally starts nothing and exits `2`.

After runtime or `.env.local` changes, use:

```bash
python3 scripts/local_runtime.py reinstall
```

Do not start a second Metro on a different port to work around a failed status.
Resolve the ownership or configuration failure on the canonical `8088` label.

## First physical-device install

1. Connect the unlocked iPhone to the Mac, tap **Trust**, and keep the device
   connected for the first install.
2. Open `USStockHelper.xcworkspace` in Xcode.
3. Select the `USStockHelper` target, open **Signing & Capabilities**, enable
   **Automatically manage signing**, and select the user's Personal Team.
   Apple credentials stay in Xcode/Keychain and must never be copied into this
   repository.
4. If Xcode reports that the bundle identifier is unavailable, replace it with
   a unique personal identifier and update `app.json` to the same value before
   rebuilding.
5. Select the connected iPhone as the run destination and press **Run**.
6. If prompted on the iPhone, enable **Developer Mode** under
   **Settings → Privacy & Security**, restart, and confirm. Trust the developer
   profile under **Settings → General → VPN & Device Management** if iOS asks.
7. Launch **US Stock Helper** from the Home Screen.

## Open the project through Metro 8088

The development-client launcher can discover the server on the household LAN.
Select only the entry whose manifest URL uses the Mac LAN address and port
`8088`. If discovery fails, choose **Enter URL manually** or use the exact QR or
deep link printed by the managed Expo process.

For the headless LaunchAgent, obtain the launcher URL from Expo's fixed
loopback endpoint through the repository's narrow extractor:

```bash
python3 scripts/metro_deep_link.py
```

The helper makes one bounded read-only request to
`http://127.0.0.1:8088/_expo/open?platform=ios&runtime=custom`. It prints only
the single URL after verifying the project development-build scheme and path,
canonical encoded manifest parameter, private-LAN IPv4 host, plain-HTTP Debug
transport, port `8088`, and absence of user information, extra paths, queries,
or fragments. It never prints the response or an exception. If it reports the
fixed unavailable error, check runtime health and reload Metro; never scrape a
whole log or invent a launcher URL from a remembered host or port.

The expected deep-link shape is:

```text
exp+us-stock-helper://expo-development-client/?url=<URL-encoded manifest URL on port 8088>
```

Do not hand-build or guess the encoded manifest URL; use the exact value the
extractor returns from Expo for this running worktree. For a simulator, that
same deep link can be opened without changing it:

```bash
xcrun simctl openurl booted '<exact expo-development-client URL printed for 8088>'
```

Expo documents the reserved `expo-development-client` path and encoded
manifest parameter in its
[development-build workflow](https://docs.expo.dev/develop/development-builds/development-workflows/).
The separately registered `usstockhelper://...` scheme remains valid for
ordinary app routes only after the project has already opened in the
development client; it is not the Expo launcher scheme and is not a substitute
for the `exp+us-stock-helper://...` URL on a cold start.

If the launcher remembers `8081` or `8083`, return to its launcher and choose or
enter the `8088` project. Do not kill the remembered legacy listener by port.

## Fast Refresh versus rebuild

Ordinary `.ts` and `.tsx` edits should refresh automatically through the
already installed development client. Use the development menu to confirm
**Fast Refresh** is enabled when an edit does not appear.

Rebuild and reinstall after changing any of the following:

- a package with native code;
- `app.json` native settings or the URL scheme;
- entitlements, signing, bundle identifier, or deployment target;
- the generated iOS project, Pods, or native source.

If native generation is intentionally required:

```bash
cd apps/mobile
npx expo prebuild --platform ios
cd ios
pod install
```

Then build from `USStockHelper.xcworkspace` again. A rebuild does not replace
the need for a healthy Metro `8088` when running the Debug client.

## Fresh-shell acceptance

Close the shell or Codex task that ran `install`, open a fresh terminal in the
same worktree, and run:

```bash
python3 scripts/local_runtime.py status
python3 scripts/local_runtime.py health
```

Only after all four components are independently observable should the device
be opened through the `8088` deep link. This proves the app is not relying on a
terminal-owned process.

## Debug versus Release/TestFlight

This development client is a household-LAN Debug artifact. Its ignored
`EXPO_PUBLIC_*` endpoint/token values are visible in the JavaScript bundle but
remain sensitive bearer credentials: never commit, log, or share them.
`EXPO_PUBLIC_MARKET_API_DEV_TOKEN` must exactly equal the current
`MOOMOO_GATEWAY_TOKEN` in `~/.us-stock-helper/lan.env`;
`EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN` stays empty because analysis uses pairing
and Keychain. Rotate `lan.env` and `apps/mobile/.env.local` together, run
`python3 scripts/local_runtime.py reinstall`, and reload the project from Metro
`8088`.

A Release/TestFlight build is a separate product gate: it works without Metro,
uses a paired HTTPS API, and contains no static market or analysis token. Do not
describe a successful `8088` Debug session as Release readiness.
