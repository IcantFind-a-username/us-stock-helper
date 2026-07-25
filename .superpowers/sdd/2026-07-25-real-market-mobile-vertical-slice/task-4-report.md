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
