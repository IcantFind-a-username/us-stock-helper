# Task 4 Report: Explicit Mobile Market-Data State

## Status

Complete. Mobile now exposes explicit `loading`, `live`, `stale`,
`unavailable`, and developer-only `demo` states for stock snapshots and the
dashboard watchlist.

## Implementation

- Added runtime configuration for `EXPO_PUBLIC_MARKET_API_URL`.
  `EXPO_PUBLIC_MARKET_API_DEV_TOKEN` is read only inside the `__DEV__` branch;
  production configuration rejects an injected development token and has no
  public bearer-token input.
- Added a strict market repository with cache keys
  `{symbol, interval, count}`, raw snapshot preservation, same-key in-flight
  sharing, per-consumer aborts, immediate eviction of fully cancelled requests,
  and strict watchlist rejection when the legacy gateway helper returns a
  fixture fallback.
- Added `MarketDataProvider`, `useStockSnapshot`, `useMarketWatchlist`, and
  `useMarketDataMode`. Retriable errors use `1s, 2s, 4s, 8s, 30s`, then `30s`
  while mounted. Permission, validation, login, malformed, and configuration
  failures do not enter that retry loop. Timers and subscriptions are cancelled
  on cleanup.
- Cached verified data is surfaced as `stale` and force-revalidated. It becomes
  `live` only after a new strict response. Failure after verification preserves
  the exact prior object, `source.asOf`, and `decisionCutoff`; a first failure is
  `unavailable`.
- Mounted `MarketDataProvider` once around routed screens while leaving
  preference, journal, and saved-plan state in `AppStateProvider`.
- Wired the Dashboard watchlist to market state without changing the existing
  market hero, alert, or candidate hierarchy. Live and stale rows use market
  data; unavailable is one actionable retry state with its error category.
  Demo is an explicit developer-only switch and demo data has
  `status: "demo"` plus `source: "fixture"`.
- With parent approval, adapted `routes.test.ts` and
  `DashboardVisualContract.test.tsx` because those tests render
  `DashboardScreen` directly instead of through root layout. Both now inject an
  explicit deterministic demo provider; their original route and visual
  assertions were not changed, and no test fixture is labelled live.

## TDD Evidence

RED was observed before each production behavior:

- Initial provider suite failed because the new config/repository/provider
  modules did not exist.
- Dashboard suite kept its five existing tests green while four new tests failed
  for missing live, stale, unavailable, and explicit-demo UI.
- Cache regression failed with `Expected: "stale", Received: "live"`.
- Demo provenance regression failed with
  `Expected: "fixture", Received: "moomoo"`.
- Cancel/remount regression failed with
  `Expected calls: 2, Received calls: 1`.

GREEN:

- Focused provider + dashboard: 2 suites, 19 tests passed.
- Full mobile: 23 suites, 111 tests passed.
- `npm run typecheck`: exit 0.
- `npm run lint`: exit 0.
- `git diff --check`: clean.

## Files

- `apps/mobile/src/config/runtimeConfig.ts`
- `apps/mobile/src/data/marketRepository.ts`
- `apps/mobile/src/state/MarketDataProvider.tsx`
- `apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx`
- `apps/mobile/src/app/_layout.tsx`
- `apps/mobile/src/screens/DashboardScreen.tsx`
- `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`
- `apps/mobile/src/app/__tests__/routes.test.ts` (approved test-only expansion)
- `apps/mobile/src/screens/__tests__/DashboardVisualContract.test.tsx`
  (approved test-only expansion)

Unrelated untracked plan documents were preserved and excluded from the commit.

## Self-Review

- No production real-data path returns or relabels fixture data as live.
- Repository cache retains original snapshot objects and timestamps.
- Old symbol responses cannot update the new subscription.
- Same-key consumers share one request; fully cancelled entries cannot capture a
  later remount.
- Retry timers exist only while a consumer is mounted and are cleared on
  cleanup.
- Production runtime has no accepted `EXPO_PUBLIC` bearer-token input.
- Changes are limited to the brief plus the two explicitly approved test
  wrappers and this report.

## Concerns

- `createMarketGatewayClient` does not accept a caller-provided `AbortSignal`.
  The repository cancels/ignores the app subscription immediately, but the
  underlying production fetch can continue until the gateway client's internal
  timeout. End-to-end transport abort requires a later gateway API extension.
- The existing `WatchlistStrip` accessibility container says
  `自选行情，演示` even when supplied live rows. It was outside the brief and
  was not changed; visual state and row data are explicit, but that legacy
  accessibility label should be parameterized in a follow-up.

## Fix Round 1

### Status

Complete. Both concerns above are resolved, and the review-requested strict
watchlist and runtime-config boundaries are covered at their production entry
points.

### Changes

- Gateway snapshot, candle, and watchlist requests now accept a caller
  `AbortSignal`. The gateway combines it with its own timeout controller,
  removes the caller listener, and clears the timeout in `finally`.
- The production repository forwards request cancellation through to the
  gateway. Unmounting the last provider consumer now aborts the actual fetch
  signal, while the gateway timeout still aborts and reports `timeout`.
- Added strict `getWatchlist`; the production repository no longer calls the
  fixture fallback API. Login-required, permission, offline, stale, and schema
  validation errors keep their categories through the repository. Only
  offline, stale, and timeout failures retry while a consumer remains mounted.
- The real runtime-config getter now reads
  `EXPO_PUBLIC_MARKET_GATEWAY_TOKEN` in every build so production fails closed
  if it is present; only development returns it as an authorization token.
  Tests restore both `__DEV__` and environment variables after every case.
- `WatchlistStrip` now receives its accessibility label from Dashboard.
  VoiceOver distinguishes demo, verified-live time, and stale original time.

### TDD Evidence

RED:

- Caller-cancellation tests observed that both the strict snapshot fetch and
  the provider's last-consumer unmount left the actual fetch signal un-aborted.
- Strict watchlist tests initially failed because `getWatchlist` did not exist.
- Repository category tests observed `validation` instead of
  `login-required`, `permission`, and `stale` while the legacy fallback helper
  was still in use.
- The real config getter neither rejected the production gateway token nor
  returned it in development.
- Dashboard live and stale accessibility queries found only the hard-coded
  `自选行情，演示` label.

GREEN:

- Focused config + gateway + repository + provider + Dashboard:
  5 suites, 77 tests passed.
- Full mobile: 25 suites, 132 tests passed.
- `npm run typecheck`: exit 0.
- `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin npm run lint`: exit 0
  under Node `22.23.1`, with no warnings.
- `git diff --check`: clean.

### Files

- `apps/mobile/src/config/runtimeConfig.ts`
- `apps/mobile/src/config/__tests__/runtimeConfig.test.ts`
- `apps/mobile/src/data/marketGateway.ts`
- `apps/mobile/src/data/__tests__/marketGateway.test.ts`
- `apps/mobile/src/data/marketRepository.ts`
- `apps/mobile/src/data/__tests__/marketRepository.test.ts`
- `apps/mobile/src/state/__tests__/MarketDataProvider.test.tsx`
- `apps/mobile/src/components/dashboard/WatchlistStrip.tsx`
- `apps/mobile/src/screens/DashboardScreen.tsx`
- `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

### Self-Review

- Abort propagation is transport-level, not merely subscription-level, and
  listener/timer cleanup is deterministic.
- Production watchlist code has no fixture fallback and preserves actionable
  error categories.
- Production rejects any configured public gateway token rather than silently
  ignoring it.
- Accessibility metadata matches the same market state and verified timestamp
  shown visually.
- Unrelated untracked plan documents remain untouched and excluded.

### Concerns

None.

## Fix Round 2

### Status

Complete. Already-aborted consumers now fail before repository work starts,
gateway cancellation classification is determined by the first internal abort
cause, and the original development-token environment variable is primary
again without removing the compatibility alias.

### Changes

- `getStockSnapshot` and `getWatchlist` reject an already-aborted consumer
  before checking cache, joining or creating an in-flight entry, or scheduling
  either loader.
- Gateway requests now record a single first abort cause, `caller` or
  `timeout`, before aborting the combined fetch signal. Timeout-first always
  becomes `GatewayRequestError("timeout")`; caller-first remains an
  `AbortError`; a raw fetch `AbortError` with no known cause becomes `offline`.
  The timeout and caller listener are still removed in `finally`.
- `getMarketRuntimeConfig()` reads
  `EXPO_PUBLIC_MARKET_API_DEV_TOKEN` as the primary development token and
  recognizes `EXPO_PUBLIC_MARKET_GATEWAY_TOKEN` only as a compatibility alias.
  Production rejects either name. Development accepts either name alone and
  rejects both names, including equal values, as an explicit configuration
  conflict.
- Existing strict-watchlist behavior and status-aware accessibility labels
  remain unchanged and are covered in the focused Dashboard/provider run.

### TDD Evidence

RED:

- The first cancellation run failed four regressions:
  snapshot and watchlist `loadStarted` were both `true` instead of `false`;
  timeout-first followed by caller abort returned raw `AbortError` instead of
  `GatewayRequestError("timeout")`; and an uncaused raw fetch `AbortError`
  reported `timeout` instead of `offline`.
- The first minimal gateway pass exposed one remaining boundary failure:
  caller-first was converted to `GatewayRequestError` instead of remaining an
  `AbortError`. Preserving only the already-classified raw caller abort at the
  strict method boundary fixed it without reading later caller state.
- The config RED run failed four cases: production ignored
  `EXPO_PUBLIC_MARKET_API_DEV_TOKEN`; development omitted its authorization
  token; and different or equal dual-name configurations did not throw the
  explicit conflict error.

GREEN:

- Cancellation-focused gateway + repository: 2 suites, 54 tests passed.
- Config getter: 1 suite, 6 tests passed.
- Focused config + gateway + repository + provider + Dashboard under Node
  `22.23.1`: 5 suites, 85 tests passed.
- Full mobile under Node `22.23.1`: 25 suites, 140 tests passed.
- `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin npm run typecheck`:
  exit 0.
- `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin npm run lint`: exit 0,
  with pristine output.
- `git diff --check`: clean.

### Files

- `apps/mobile/src/config/runtimeConfig.ts`
- `apps/mobile/src/config/__tests__/runtimeConfig.test.ts`
- `apps/mobile/src/data/marketGateway.ts`
- `apps/mobile/src/data/__tests__/marketGateway.test.ts`
- `apps/mobile/src/data/marketRepository.ts`
- `apps/mobile/src/data/__tests__/marketRepository.test.ts`

### Self-Review

- Both repository resources check caller cancellation before all cache,
  in-flight, entry, and loader paths.
- Abort cause is assigned once, synchronously before the combined controller is
  aborted; later timeout or caller events cannot overwrite it.
- Strict snapshot, candle, and watchlist callers receive the same deterministic
  cancellation semantics, while uncaused transport aborts remain retryable as
  offline.
- Tests restore `__DEV__` and both token environment variables after every
  real-getter case.
- The strict watchlist path, fallback boundary, Dashboard status labels, and
  unrelated untracked plan documents are untouched.

### Concerns

None.
