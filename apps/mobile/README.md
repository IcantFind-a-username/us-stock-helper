# US Stock Helper mobile app

Expo/React Native client for the read-only US-stock assistant.

## Local development

```bash
npm install
npm run start:dev-client
```

Runtime endpoints belong in an ignored `.env.local` or `.env`; never commit
LAN bearer tokens. The supported variables are:

```dotenv
EXPO_PUBLIC_MARKET_API_URL=http://192.168.0.10:8766
EXPO_PUBLIC_MARKET_API_DEV_TOKEN=
EXPO_PUBLIC_ANALYSIS_API_URL=http://192.168.0.10:8770
EXPO_PUBLIC_ANALYSIS_API_DEV_TOKEN=
EXPO_PUBLIC_INITIAL_DEMO_MODE=false
```

`EXPO_PUBLIC_INITIAL_DEMO_MODE=true` opens deterministic demo data immediately
for unattended visual QA. Production bundles ignore the flag even if it is
present. App and native configuration lives in `app.json`; this project does
not use a Codex or Claude `config.yaml`.

## iOS native generation

The checked-in Expo config plugin sets React Native and Expo modules to build
from source. This keeps their linkage mode coherent with the pinned Expo/RN
versions when the ignored `ios/` project is regenerated.

```bash
npx expo prebuild --platform ios
cd ios && pod install
```

## Verification

```bash
npm test -- --runInBand
npm run typecheck
```
