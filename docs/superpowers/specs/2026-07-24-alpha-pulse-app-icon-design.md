# Alpha Pulse App Icon Design

Date: 2026-07-24  
Status: Approved

## Objective

Replace the blank white iOS icon with a simple, distinctive mark that matches
the approved Calm Alpha visual system and remains legible at iPhone home-screen
size.

## Approved Direction

The selected direction is **A — Alpha Pulse**.

- Use a full-bleed deep-navy gradient based on Calm Alpha's `#15345E` to
  `#071526` range.
- Center one rising four-point market pulse rendered in navigation blue through
  positive green.
- End the pulse with a restrained arrow corner to suggest evidence becoming a
  decision and action.
- Use no letters, text, border, transparency, or pre-rendered rounded corners.
- Keep all important artwork inside the iOS safe area so system icon masks do
  not crop it.

The icon communicates speed and market movement without implying guaranteed
returns. Its visual order is evidence, interpretation, then action.

## Deliverables

1. A 1024 × 1024 opaque PNG at
   `apps/mobile/assets/images/icon.png`.
2. The same 1024 × 1024 PNG at
   `apps/mobile/ios/USStockHelper/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png`.
3. An explicit Expo `icon` reference in `apps/mobile/app.json` so a future
   native prebuild preserves the approved asset.

No other UI or business behavior changes are in scope.

## Verification

- Confirm both PNGs are 1024 × 1024, opaque RGB/RGBA images and byte-identical.
- Confirm Expo resolves the configured icon path.
- Perform an incremental Xcode build for the connected iPhone.
- Confirm Xcode installs and launches the signed development build.
- Ask the user to verify the icon's appearance on the iPhone home screen.

## Failure Handling

- If the icon is clipped, increase the outer padding without changing the
  approved mark.
- If iOS shows the previous icon, reinstall the development build after
  confirming the asset catalog contains the new PNG.
- If a future Expo prebuild replaces the native icon, the explicit Expo icon
  setting remains the source of truth.
