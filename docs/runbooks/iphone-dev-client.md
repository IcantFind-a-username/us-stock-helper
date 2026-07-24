# iPhone Dev Client Installation

The native project is an Expo development build, not Expo Go. JavaScript and
TypeScript UI changes use Fast Refresh; native dependency or signing changes
require a rebuild.

## Verified project settings

- Workspace: `apps/mobile/ios/USStockHelper.xcworkspace`
- Scheme: `USStockHelper`
- Bundle identifier: `com.franz.usstockhelper.dev`
- Minimum iOS version: 16.4
- Node: `/opt/homebrew/opt/node@22/bin/node`
- Simulator Debug build: verified with `BUILD SUCCEEDED`
- Physical iPhone Debug build: verified on 2026-07-25
- Installed app: verified as `US Stock Helper 0.1.0 (1)` on the connected
  iPhone; installation does not launch the app

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

## Fast Refresh

Run from `apps/mobile` with the Mac and iPhone on the same local network:

```bash
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  npm run start:dev-client -- --lan --port 8088
```

Open the installed app and choose the displayed local development server. UI
edits should refresh automatically. Use the development menu to confirm
**Fast Refresh** is enabled if an edit does not appear.

Rebuild the app after changing native packages, `app.json` native settings,
entitlements, signing, or the iOS project. Ordinary `.ts` and `.tsx` edits do
not require reinstalling the app.
