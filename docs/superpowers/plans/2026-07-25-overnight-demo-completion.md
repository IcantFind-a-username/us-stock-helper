# Overnight Demo Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all current render errors and placeholder tabs, complete the deterministic iPhone demo, and align every implemented flow with the approved compact Calm Alpha prototypes.

**Architecture:** Preserve Expo Router, `FixtureRepository`, `AppStateProvider`, theme tokens, and the accepted Dashboard. Extend typed fixtures for every exposed symbol, compose four focused tab screens from small native components, and use progressive evidence sheets instead of dense inline research reports.

**Tech Stack:** Expo SDK 57, React Native 0.86, React 19.2, TypeScript, Expo Router, React Native SVG, AsyncStorage, Jest Expo, React Native Testing Library, Xcode.

## Global Constraints

- All financial values remain visibly labeled deterministic demo data.
- Visual authority is the tracked prototype directory and approved visual-realignment specification.
- Default horizon is short: intraday through 5 trading days.
- Swing is 1–8 weeks; medium/long is 2–24 months.
- Every factual or analytical claim exposes traceable citations.
- Adviser output is a capped soft factor and never independently creates an alert.
- Risk preference may change plan sizing, never objective score, direction, evidence credibility, or confidence.
- Long and short plans are analysis-only and cannot place, edit, or cancel orders.
- Intraday institution/retail values say `估算代理`; reported ownership shows its reporting date.
- No future functions, deterministic-looking promised price line, or guaranteed-return language.
- All interactive targets are at least 44 points with accessibility labels and pressed feedback.
- Preserve unrelated user changes and stage only task-owned files.

---

### Task 1: Close route and fixture gaps

**Files:**
- Modify: `apps/mobile/src/fixtures/__tests__/repository.test.ts`
- Modify: `apps/mobile/src/fixtures/stocks.ts`
- Modify: `apps/mobile/src/fixtures/advisers.ts`
- Modify: `apps/mobile/src/fixtures/alerts.ts`
- Modify: `apps/mobile/src/fixtures/repository.ts`
- Test: `apps/mobile/src/fixtures/__tests__/repository.test.ts`

**Interfaces:**
- Consumes: `FixtureRepository.getDashboard`, `getStock`, `getTradePlans`
- Produces: complete `NVDA`, `TSLA`, and `PLTR` records for every horizon and six risk plans per symbol

- [ ] Write a repository test that collects every Dashboard watchlist and candidate symbol and calls `getStock(symbol, horizon)` for all three horizons.
- [ ] Run the test and verify RED reports `Missing stock fixture: TSLA:short`.
- [ ] Add per-symbol typed profiles and construct stock snapshots without weakening the existing missing-fixture exception.
- [ ] Add deterministic long/short × conservative/balanced/aggressive plans for every exposed symbol.
- [ ] Add alert threads spanning `info`, `observation`, `action`, and `risk` severities.
- [ ] Run the focused repository test and full fixture tests; verify GREEN.
- [ ] Commit only the fixture and fixture-test files.

### Task 2: Make every Dashboard affordance produce a result

**Files:**
- Create: `apps/mobile/src/components/search/StockSearchSheet.tsx`
- Test: `apps/mobile/src/components/search/__tests__/StockSearchSheet.test.tsx`
- Modify: `apps/mobile/src/components/dashboard/WatchlistStrip.tsx`
- Modify: `apps/mobile/src/screens/DashboardScreen.tsx`
- Modify: `apps/mobile/src/screens/__tests__/DashboardScreen.test.tsx`

**Interfaces:**
- Consumes: known symbol summaries and existing `DashboardDetailSheet`
- Produces: local search navigation and moomoo read-only disclosure

- [ ] Write failing tests for opening Search, choosing `TSLA`, and opening the moomoo source explanation.
- [ ] Verify RED because Search and moomoo actions currently do nothing.
- [ ] Implement a compact searchable sheet with a labeled `TextInput`, empty state, close action, and 44-point rows.
- [ ] Route symbol selection through the existing typed stock route.
- [ ] Connect the moomoo action to a compact disclosure explaining that sync is not connected in demo mode.
- [ ] Run Dashboard tests and verify every visible affordance has a navigation or disclosure result.
- [ ] Commit the Dashboard closure as one independent change.

### Task 3: Stabilize and visually complete stock, chart, evidence, and adviser flows

**Files:**
- Modify: `apps/mobile/src/screens/StockDetailScreen.tsx`
- Modify: `apps/mobile/src/screens/FullChartScreen.tsx`
- Modify: `apps/mobile/src/screens/AdvisersScreen.tsx`
- Modify: `apps/mobile/src/components/dashboard/DashboardDetailSheet.tsx`
- Modify: `apps/mobile/src/components/chart/PriceChart.tsx`
- Modify: `apps/mobile/src/components/stock/*.tsx`
- Modify: `apps/mobile/src/components/advisers/*.tsx`
- Test: `apps/mobile/src/screens/__tests__/StockDetailScreen.test.tsx`
- Test: `apps/mobile/src/screens/__tests__/AdvisersScreen.test.tsx`

**Interfaces:**
- Consumes: complete stock/adviser/plan fixtures from Task 1
- Produces: route-safe stock detail, professional chart, compact evidence disclosure, and deterministic adviser plans

- [ ] Add parameterized failing screen tests for `NVDA`, `TSLA`, and `PLTR`.
- [ ] Verify RED on the current absent `TSLA` and `PLTR` records.
- [ ] Render quote, horizon, objective conclusion, counter-case, chart, forecast metadata, RSI, MACD, ownership, participation proxy, patterns, fundamentals, macro/geopolitical context, evidence, and adviser entry in prototype order.
- [ ] Tighten evidence-sheet typography and spacing while retaining every section and citation.
- [ ] Verify long/short and three risk selections keep objective score/confidence frozen and expose risk warnings.
- [ ] Run stock, chart, adviser, and plan tests; verify GREEN.
- [ ] Commit the complete analysis path.

### Task 4: Implement Discover

**Files:**
- Create: `apps/mobile/src/components/discover/CandidateCard.tsx`
- Modify: `apps/mobile/src/screens/DiscoverScreen.tsx`
- Create: `apps/mobile/src/screens/__tests__/DiscoverScreen.test.tsx`

**Interfaces:**
- Consumes: `FixtureRepository.getDashboard(horizon).candidates`
- Produces: horizon-aware all/long/short/asymmetric filtering, evidence disclosure, and stock navigation

- [ ] Write failing tests for content, side filtering, asymmetric filtering, evidence disclosure, and stock navigation.
- [ ] Verify RED because the screen is a `TemporaryScreen`.
- [ ] Implement the compact page header, HorizonSwitch, summary strip, filter chips, and ranked candidate cards.
- [ ] Put reason, counter-case, invalidation, freshness, and citations behind progressive disclosure.
- [ ] Run the focused screen test and verify GREEN.
- [ ] Commit Discover independently.

### Task 5: Implement Alerts

**Files:**
- Create: `apps/mobile/src/components/alerts/AlertThreadCard.tsx`
- Modify: `apps/mobile/src/screens/AlertsScreen.tsx`
- Create: `apps/mobile/src/screens/__tests__/AlertsScreen.test.tsx`

**Interfaces:**
- Consumes: `FixtureRepository.getAlerts()`
- Produces: severity filters, compact event threads, evidence/invalidation disclosure, and stock navigation

- [ ] Write failing tests for all four severity classes, filtering, evidence disclosure, and detail navigation.
- [ ] Verify RED because the screen is a `TemporaryScreen`.
- [ ] Implement the prototype-aligned header, status summary, severity chips, and event-thread cards.
- [ ] Make bounded adviser contribution visually subordinate to the deterministic base contribution.
- [ ] Run the focused screen test and verify GREEN.
- [ ] Commit Alerts independently.

### Task 6: Implement Journal and persistent entry validation

**Files:**
- Create: `apps/mobile/src/domain/journal.ts`
- Create: `apps/mobile/src/domain/__tests__/journal.test.ts`
- Create: `apps/mobile/src/components/journal/JournalEntryForm.tsx`
- Create: `apps/mobile/src/components/journal/SavedPlanCard.tsx`
- Modify: `apps/mobile/src/screens/JournalScreen.tsx`
- Create: `apps/mobile/src/screens/__tests__/JournalScreen.test.tsx`

**Interfaces:**
- Consumes: `savedPlans`, `journalEntries`, `addJournalEntry`
- Produces: summary metrics, saved-plan cards, validated local entries, and an objectivity firewall notice

- [ ] Write failing pure tests for numeric validation and realized/unrealized P&L aggregation.
- [ ] Verify RED because journal helpers do not exist.
- [ ] Implement the minimal pure validation and summary functions.
- [ ] Write failing screen tests for empty state, opening the form, invalid input, and saved entry rendering.
- [ ] Implement labeled inputs, inline errors, side/decision controls, and local persistence.
- [ ] Render saved adviser plans and state that journal behavior cannot alter market facts or direction.
- [ ] Run domain, state, and Journal tests; verify GREEN.
- [ ] Commit Journal independently.

### Task 7: Implement the safe Agent conversation

**Files:**
- Create: `apps/mobile/src/components/agent/ConversationTurnCard.tsx`
- Create: `apps/mobile/src/components/agent/AgentComposer.tsx`
- Modify: `apps/mobile/src/screens/AgentScreen.tsx`
- Create: `apps/mobile/src/screens/__tests__/AgentScreen.test.tsx`

**Interfaces:**
- Consumes: `FixtureRepository.getConversation`, citations, and the `NVDA` adviser route
- Produces: objective-first conversation, local prompt response, research acknowledgement, citations, and adviser-council navigation

- [ ] Write failing tests for the required six-section order, composer interaction, evidence disclosure, research acknowledgement, and adviser entry.
- [ ] Verify RED because the screen is a `TemporaryScreen`.
- [ ] Implement a compact navy objective card followed by evidence, counter-evidence, uncertainty, personalized risk scenario, and citations.
- [ ] Add prompt chips and a labeled composer that returns a deterministic non-live demo response without pretending to call an LLM.
- [ ] Add the thirteen style-adviser entry and public-philosophy simulation disclaimer.
- [ ] Run Agent tests and verify GREEN.
- [ ] Commit Agent independently.

### Task 8: Remove placeholders and complete automated/visual/device acceptance

**Files:**
- Modify: `apps/mobile/src/app/__tests__/routes.test.ts`
- Delete only if unreferenced: `apps/mobile/src/screens/TemporaryScreen.tsx`
- Update: `docs/runbooks/iphone-dev-client.md`

**Interfaces:**
- Consumes: all completed tasks
- Produces: morning-ready iPhone demo and reproducible install instructions

- [ ] Add a route contract test proving no tab screen imports `TemporaryScreen`.
- [ ] Run full Jest, typecheck, lint, and Expo config checks.
- [ ] Start the development server and inspect every route at 390×844 and 430×932 against the approved prototypes.
- [ ] Check 44-point touch targets, safe areas, text clipping, reduced motion, Dynamic Type tolerance, and absence of developer red screens.
- [ ] Build the signed iOS app for the connected device with `xcodebuild`.
- [ ] Install and launch with `xcrun devicectl`; confirm Metro bundles without runtime errors.
- [ ] Re-run the complete verification suite after final visual adjustments.
- [ ] Commit the verification/runbook changes and prepare the branch for the user's morning review.

