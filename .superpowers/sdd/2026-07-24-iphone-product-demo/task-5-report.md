# Task 5 — Short-first Dashboard report

## Implementation summary

Built the route-independent, fixture-backed Dashboard screen with short as the default state from `AppStateProvider`. It now presents a conclusion-first market playbook, the selected horizon's deterministic score/confidence/drivers, priority alert, explicitly fake `moomoo watchlist · 演示占位`, long/short candidates, and an inline evidence sheet.

The typed dashboard contract now includes the nine requested driver families, market invalidation, and explicit candidate designation, strongest counter-case, invalidation, and citation IDs. All data remains deterministic and local; no network, broker, trading, authentication, cloud, LLM, news, or market-data integration was added.

## Files changed

- `apps/mobile/src/components/dashboard/MarketPlaybookCard.tsx` (new)
- `apps/mobile/src/components/dashboard/PriorityAlertCard.tsx` (new)
- `apps/mobile/src/components/dashboard/WatchlistStrip.tsx` (new)
- `apps/mobile/src/components/dashboard/CandidateList.tsx` (new)
- `apps/mobile/src/screens/DashboardScreen.tsx`
- `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx` (new)
- `apps/mobile/src/domain/models.ts`
- `apps/mobile/src/fixtures/dashboard.ts`
- `apps/mobile/src/fixtures/__tests__/repository.test.ts`
- `apps/mobile/src/components/ui/DemoDataBadge.tsx`
- `apps/mobile/src/app/__tests__/routes.test.ts`

`apps/mobile/src/app/(tabs)/index.tsx` remains the existing thin `DashboardScreen` export, so it required no source change.

## TDD RED

Command:

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx
```

Observed output (after correcting the test mock setup, before any Task 5 production implementation):

```text
FAIL src/screens/__tests__/DashboardScreen.test.tsx
✕ shows the short-first conclusion, objective dashboard context, and accessible actions
✕ switches all fixture-backed horizon views independently
✕ routes alert, quotes, and both long/short candidates while disclosing their evidence

Unable to find an element with text: 演示数据 · 非实时行情
...
US Stock Helper
演示数据 · 非实时建议
演示页面将在后续任务中完善。
```

This was expected because `DashboardScreen` was still a `TemporaryScreen`, and the shared badge still used the superseded `非实时建议` text. The tests therefore had no Dashboard content, horizon views, actions, or accessibility semantics to find.

## GREEN / final verification

Focused command:

```bash
cd apps/mobile
npm test -- src/screens/__tests__/DashboardScreen.test.tsx src/fixtures/__tests__/repository.test.ts
```

Result: `2 passed, 8 passed`.

Final commands:

```bash
cd apps/mobile
npm test
npm run typecheck
EXPO_NO_TELEMETRY=1 npm run lint
```

Results:

```text
Test Suites: 6 passed, 6 total
Tests:       17 passed, 17 total
Snapshots:   0 total

> mobile@1.0.0 typecheck
> tsc --noEmit

> mobile@1.0.0 lint
> expo lint
```

All commands exited with status 0. npm emitted the environment's non-blocking `Unknown env config "http-proxy"` / npm-update notices only.

## Self-review findings

- Exact page badge and VoiceOver label now use `演示数据 · 非实时行情`.
- Short, swing, and long snapshots are independently fixture-backed and differ in conclusion, score, confidence, score change, advice, invalidation, contradictions, and driver scores; they do not use risk preference.
- All nine requested driver families, fixed `-100..100` bar scale, textual conclusion, freshness, contradiction, evidence route, update time, score/confidence/change, advice, and invalidation are visible.
- Alert exposes trigger/state, evidence/counter-evidence counts, freshness/timestamp, optional adviser adjustment, invalidation, evidence action, and stock-detail action.
- Watchlist quotes expose price/change/direction/pulse and use only the explicit fake placeholder label; all quote/candidate/alert navigation uses the local Expo route payload.
- Candidate fixtures/UI include long and short candidates, all three exact state labels, designation, reason, counter-case, invalidation, evidence counts/freshness, citations, and detail actions.
- Financial cards visibly carry an `演示` marker; all Dashboard actions have descriptive VoiceOver role/label/hint and 44pt-or-larger press targets (52pt quote rows). Layout uses flex/wrap/minWidth protection and the existing scrolling `Screen`, with no fixed card widths.
- `git diff --check` passed. No unrelated Python, native iOS, or later-task files were changed.

## Concerns

None.
