# Overnight Demo Completion and Prototype Fidelity Design

Date: 2026-07-25  
Status: Approved for immediate execution by the user's request to plan and continue overnight

## Objective

Turn the current iPhone build into a complete, usable deterministic product
demo for morning review. The implementation must remove render errors and
placeholder tabs while translating the already-approved browser prototypes
into native React Native screens.

This delivery remains primarily Project 1 of the main product design. At the
user's request, it may also add a narrow Project 2 bridge for read-only moomoo
watchlist, quote, and candlestick access. It does not add web crawling, an LLM
provider, push notifications, or broker order permissions.

## Evidence and root cause

The user's device screenshots show:

- `TSLA` navigation raises `Missing stock fixture: TSLA:short`;
- Discover, Alerts, Journal, and Agent render `TemporaryScreen`;
- the evidence view is functional but visually oversized and sparse compared
  with the approved compact prototype hierarchy;
- development-client chrome is visible during testing and must not be confused
  with product UI.

The repository confirms that Dashboard routes to `NVDA`, `TSLA`, and `PLTR`,
while `stockFixtures` and `tradePlanFixtures` only cover `NVDA`. Existing tests
assert router calls but do not render the destination for each routed symbol.

## Chosen approach

Use incremental completion inside the existing typed fixture architecture.
Preserve the approved Dashboard, theme tokens, state provider, repository
boundary, safety language, and the in-progress stock/chart/adviser components.
Add focused native screens and shared compact components only where multiple
new pages need the same behavior.

Rejected alternatives:

1. A visual rewrite of the entire app would risk breaking the accepted
   Dashboard and is not required to fix the missing flows.
2. Adding live APIs now would mix data-provider uncertainty with UI defects and
   violate the approved Project 1 boundary.

## Visual authority

The following tracked files remain the source of truth:

- `docs/design-reference/approved-browser-prototypes/ios-dashboard-demo-v1.html`
- `docs/design-reference/approved-browser-prototypes/ios-stock-detail-demo-v1.html`
- `docs/design-reference/approved-browser-prototypes/kline-and-macro-context-v2.html`
- `docs/design-reference/approved-browser-prototypes/advisor-architecture-v2.html`
- `docs/superpowers/specs/2026-07-24-approved-prototype-visual-realignment-design.md`

New screens use the same Calm Alpha language: light gray canvas, compact white
surfaces, navy focal cards, blue navigation/action accents, restrained green,
red, and amber status colors, dense information hierarchy, 44-point minimum
touch targets, and progressive disclosure for evidence.

Centered placeholder compositions, giant single-purpose cards, emoji
navigation, disabled-looking live controls, and decorative animation are
forbidden.

## Functional architecture

### Route-safe fixture layer

Every symbol exposed by Dashboard or Discover must have stock snapshots for
`short`, `swing`, and `long`, plus deterministic long/short plans. Screens
continue to consume `FixtureRepository`; no component imports raw fixture
tables.

### Dashboard closure

Search opens a compact local-symbol chooser. Every watchlist, candidate, alert,
section action, and evidence affordance produces navigation or disclosure.
The moomoo affordance explains the demo's read-only future integration instead
of doing nothing.

### Stock analysis

Stock detail preserves the approved hierarchy:

1. quote and horizon;
2. objective conclusion and counter-case;
3. professional chart and forecast bands;
4. RSI and MACD;
5. reported ownership and estimated participation;
6. patterns, fundamentals, market/macro/geopolitical context;
7. evidence and adviser/risk-plan actions.

Unsupported direct-link symbols render a compact unavailable state rather than
a developer red screen.

### Discover

Discover ranks the active horizon's candidates and supports all, long, short,
and asymmetric-upside filters. Each row exposes score, status, catalyst,
technical/fundamental context, evidence counts, counter-case, invalidation,
citations, and stock navigation.

### Alerts

Alerts expose information, observation, action, and risk groups. Each thread
shows timestamp, freshness, base contribution, bounded adviser adjustment,
evidence/counter-evidence, invalidation, citations, and a stock-detail path.

### Journal

Journal reads saved analysis plans and locally persisted journal entries. It
supports a small labeled form for symbol, side, quantity, execution price,
P&L, decision adherence, and notes. Journal facts may improve execution review
but are explicitly isolated from market-direction evidence.

### Agent

Agent renders the safe response order defined in the main product
specification. Local prompt chips and a composer append deterministic demo
responses, clearly labeled as non-live. It also provides evidence disclosure,
supplemental-research state, and an entry into the thirteen style-adviser
council.

### Optional read-only moomoo bridge

The iPhone never connects to OpenD directly and never receives moomoo account
credentials. A local gateway connects to OpenD on loopback, exposes only an
allowlisted read API to the phone, normalizes timestamps and source metadata,
and reports permission, quota, latency, and fallback state.

The app uses live data only when the gateway explicitly reports `source:
moomoo`, a successful OpenD session, and a fresh timestamp. Otherwise the
existing deterministic fixtures remain visible with an `演示回退` label.
Trading contexts, account positions, order submission, order modification,
order cancellation, and watchlist mutation are excluded.

## Failure handling

- Known UI routes must never rely on absent fixture records.
- Empty saved plans or journal history receive useful empty states.
- Invalid numeric journal fields show inline validation and are not persisted.
- Demo research and Agent actions acknowledge locally without external calls.
- Unknown direct-link symbols show an unavailable screen with Back and
  Dashboard actions.
- OpenD offline, login-required, permission-denied, quota-exhausted, and stale
  responses map to explicit data-health states and deterministic fallback.
- No control may submit, edit, or cancel a broker order.

## Testing and acceptance

Test-first coverage must prove:

- all Dashboard-exposed symbols resolve for all horizons;
- all exposed symbols have six long/short risk combinations;
- TSLA and PLTR detail paths render without throwing;
- no tab route uses `TemporaryScreen`;
- Discover filters and opens evidence/stock detail;
- Alerts disclose invalidation and citations;
- Journal validates and persists a local entry;
- Agent preserves objective-first section order and labels demo responses;
- objective score and confidence remain unchanged by risk preference;
- all interactive controls have descriptive roles and 44-point targets.

Final verification requires full Jest, TypeScript, ESLint, Expo route/config,
390- and 430-point visual checks, a physical-device Xcode build, installation,
launch, and Metro bundle inspection.
