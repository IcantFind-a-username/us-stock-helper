# Alpha Pulse App Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blank iOS development icon with the approved Alpha Pulse icon and launch the updated build on the connected iPhone.

**Architecture:** Render the approved geometric mark from a deterministic SVG into one opaque 1024 × 1024 PNG. Use that PNG as both Expo's source-of-truth icon and the existing iOS asset-catalog image, then verify the files and perform an incremental signed Xcode run.

**Tech Stack:** SVG, macOS Quick Look image renderer, `sips`, Expo configuration, Xcode 18, React Native/Expo development client.

## Global Constraints

- Use the approved A — Alpha Pulse design only.
- Use a full-bleed `#15345E` to `#071526` deep-navy gradient.
- Render one blue-to-green rising four-point pulse with a restrained arrow corner.
- Use no letters, text, border, transparency, or pre-rendered rounded corners.
- Keep important artwork inside the iOS icon safe area.
- Do not change any screen, component, data, or investment behavior.

---

### Task 1: Produce and wire the approved icon

**Files:**
- Modify: `apps/mobile/assets/images/icon.png`
- Modify: `apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png`
- Modify: `apps/mobile/app.json`
- Temporary render source: `/tmp/alpha-pulse-app-icon.svg`

**Interfaces:**
- Consumes: the approved Alpha Pulse geometry and Calm Alpha color tokens.
- Produces: one byte-identical 1024 × 1024 PNG used by Expo and the iOS asset catalog.

- [ ] **Step 1: Verify the current configuration fails the approved source-of-truth requirement**

Run:

```bash
cd apps/mobile
node -e 'const c=require("./app.json").expo; if (c.icon !== "./assets/images/icon.png") process.exit(1)'
```

Expected: exit code `1`, because `expo.icon` is currently absent.

- [ ] **Step 2: Create the deterministic SVG render source**

Create `/tmp/alpha-pulse-app-icon.svg` with a 1024 × 1024 view box, an opaque
navy gradient background, and the approved pulse path:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#15345E"/>
      <stop offset="1" stop-color="#071526"/>
    </linearGradient>
    <linearGradient id="pulse" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#2E8CFF"/>
      <stop offset=".72" stop-color="#52D7A1"/>
      <stop offset="1" stop-color="#B8FFE0"/>
    </linearGradient>
  </defs>
  <rect width="1024" height="1024" fill="url(#background)"/>
  <circle cx="178" cy="175" r="270" fill="#2878E5" opacity=".10"/>
  <circle cx="840" cy="838" r="300" fill="#0BBF78" opacity=".07"/>
  <path d="M214 702 L395 541 L510 625 L778 330"
        fill="none" stroke="#FFFFFF" stroke-opacity=".16"
        stroke-width="112" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M214 702 L395 541 L510 625 L778 330"
        fill="none" stroke="url(#pulse)" stroke-width="58"
        stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M671 330 H778 V437" fill="none" stroke="#B8FFE0"
        stroke-width="58" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="214" cy="702" r="23" fill="#FFFFFF"/>
  <circle cx="395" cy="541" r="23" fill="#FFFFFF"/>
  <circle cx="510" cy="625" r="23" fill="#FFFFFF"/>
</svg>
```

- [ ] **Step 3: Render and copy the icon**

Run:

```bash
mkdir -p /tmp/alpha-pulse-render
qlmanage -t -s 1024 -o /tmp/alpha-pulse-render /tmp/alpha-pulse-app-icon.svg
sips -s format png /tmp/alpha-pulse-render/alpha-pulse-app-icon.svg.png --out apps/mobile/assets/images/icon.png
cp apps/mobile/assets/images/icon.png apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png
```

Expected: both project PNG files are replaced with the approved artwork.

- [ ] **Step 4: Set the Expo icon source**

Add this direct child of the `expo` object in `apps/mobile/app.json`:

```json
"icon": "./assets/images/icon.png",
```

- [ ] **Step 5: Verify the generated assets and configuration**

Run:

```bash
sips -g pixelWidth -g pixelHeight -g hasAlpha apps/mobile/assets/images/icon.png
sips -g pixelWidth -g pixelHeight -g hasAlpha apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png
cmp apps/mobile/assets/images/icon.png apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png
node -e 'const c=require("./apps/mobile/app.json").expo; if (c.icon !== "./assets/images/icon.png") process.exit(1)'
```

Expected: both images report `1024` × `1024`, both report no alpha channel,
`cmp` exits `0`, and the Node check exits `0`.

- [ ] **Step 6: Inspect the rendered artwork**

Open `apps/mobile/assets/images/icon.png` with the local image viewer and
confirm the mark matches the approved A preview, has no white border, and keeps
the arrow inside the safe area.

- [ ] **Step 7: Commit only the icon implementation**

```bash
git add apps/mobile/app.json \
  apps/mobile/assets/images/icon.png \
  apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png
git commit -m "feat: add Alpha Pulse app icon"
```

### Task 2: Install and verify on the connected iPhone

**Files:**
- Read: `apps/mobile/ios/USStockHelper.xcworkspace`
- Read: `docs/runbooks/iphone-dev-client.md`

**Interfaces:**
- Consumes: the signed iOS target and verified Alpha Pulse asset.
- Produces: an updated development build installed and running on Franz's iPhone.

- [ ] **Step 1: Confirm the development server is listening**

Run:

```bash
lsof -nP -iTCP:8088 -sTCP:LISTEN
```

Expected: a Node/Expo process is listening on TCP port `8088`. If no process is
listed, run:

```bash
cd apps/mobile
env PATH=/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  npm run start:dev-client -- --lan --port 8088
```

- [ ] **Step 2: Confirm Xcode target and signing**

In Xcode, verify:

- scheme: `USStockHelper`;
- destination: `Franz’s iPhone`;
- team: `Personal Team`;
- automatic signing: enabled.

- [ ] **Step 3: Run the incremental build**

Click Xcode `Run`.

Expected: Xcode builds, installs, and launches `USStockHelper` without a
Developer Mode or untrusted-certificate alert.

- [ ] **Step 4: Verify runtime connection**

Confirm Xcode remains attached to the app and the Expo development server logs
the iPhone bundle request without an uncaught JavaScript error.

- [ ] **Step 5: Verify the user-visible result**

Ask the user to return to the iPhone home screen and confirm:

- the Alpha Pulse icon replaces the blank white icon;
- the icon is not clipped or surrounded by a white edge;
- tapping it opens the approved dashboard.
