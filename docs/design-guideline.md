# US Stock Helper — Calm Alpha Design Guidelines

Generated: 2026-07-24

## Design style

Calm Alpha combines institutional clarity with compact mobile market tooling.
It is restrained, evidence-first, and optimized for fast scanning without
turning the product into a visually aggressive trading game.

## Color system

- Primary ink: `#0B1729`
- Hero navy: `#15345E` → `#0A1A30`
- Interaction blue: `#2878E5`
- Positive: `#0BBF78`
- Negative: `#F64F5E`
- Warning: `#B17608`
- Background: `#F3F6FA`
- Surface: `#FFFFFF`
- Border: `#DBE3ED`

Blue creates trust and indicates interaction. Green and red are reserved for
market meaning. Amber communicates uncertainty or an unresolved countercase.

## Typography

- Primary: SF Pro Text / PingFang SC
- Display: SF Pro Display / PingFang SC
- Numeric: SF Pro with tabular figures

Hierarchy:

- Display verdict: 27 pt / heavy / 1.05
- Screen title: 22–27 pt / heavy / 1.1
- Section: 17 pt / heavy / 1.2
- Card title: 14–17 pt / semibold-heavy / 1.25
- Body: 11–13 pt / regular-medium / 1.45–1.6
- Metadata: 9–10 pt / medium / 1.35

## Layout

- 8 pt base grid with 4 pt half-steps
- 16 pt page margin
- 8–14 pt inter-component gaps
- 15–23 pt card radii
- 44 pt minimum touch target
- Primary frames: 390 × 844 and 430 × 932

The market hero is the only dominant dark surface. Supporting cards use white,
thin borders, and subtle shadow. Complexity is revealed on demand.

## Components

- Horizon segmented control
- Market sentiment hero
- Score ring and score box
- Driver and evidence chips
- Alert card
- Watchlist mini-card and sparkline
- Candidate row
- Candlestick chart
- Indicator tabs
- RSI and MACD panels
- Forecast probability band
- Ownership/activity proxy bar
- Long/short selector
- Risk preference selector
- Deterministic plan card
- Evidence item and countercase
- Adviser profile chip
- Consensus bar
- Evidence-first chat message
- Safe conversation composer

## Motion

- Press response within 16 ms
- 180–240 ms ease-out for entry and selection
- 150–200 ms ease-in for exits
- Transform and opacity only for routine micro-interactions
- No looping signal animation
- Reduced-motion equivalents required

## Accessibility

- WCAG AA contrast target
- 44 × 44 pt minimum touch target
- Dynamic Type-safe layout
- Color never carries meaning alone
- Visible focus and selected states
- Screen-reader labels include full evidence meaning
- Charts have equivalent textual summaries

## Guardrails

- No automatic or one-tap trading action
- Forecasts use ranges, calibration, and invalidation
- Institutional/retail intraday data is labeled as a proxy
- Style advisers are not the real people or endorsements
- Every action recommendation exposes sources and counter-evidence
- User preferences cannot alter facts, direction, or confidence

