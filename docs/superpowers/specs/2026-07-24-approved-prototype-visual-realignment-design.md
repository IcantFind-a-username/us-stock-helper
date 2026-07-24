# Approved Prototype Visual Realignment

Date: 2026-07-24
Status: User approved approach A; written design awaiting final review

## 1. Decision

Rebuild the React Native visual layer to closely translate the previously
approved browser prototypes instead of incrementally styling the current
Dashboard. Preserve the typed fixtures, evidence models, navigation,
persistence, safety rules, and tested business behavior unless a visual
component requires a narrow interface adaptation.

The approved prototype sources are versioned under
`docs/design-reference/approved-browser-prototypes/` and are the visual source
of truth. Product and safety behavior remains governed by the main product
specification.

## 2. Root cause

The approved prototype files remained in an untracked brainstorming workspace
and were not available to the cloud implementation session. The cloud session
therefore implemented semantic requirements from prose and tests:

- data health became a large standalone block;
- all market drivers, counter-evidence, invalidation, and candidate reasoning
  were expanded inline;
- white cards received equal visual weight;
- the market conclusion lost the dark focal treatment;
- the first viewport became a long research report rather than a decision
  dashboard;
- tests verified content and accessibility but provided no visual contract.

The repair must address the missing source of truth and the information
hierarchy, not merely adjust colors or spacing.

## 3. Visual authority and interpretation

The native app should match the prototype's hierarchy, proportions, color
relationships, density, and interaction intent. It should not recreate the
browser prototype's surrounding desktop explanation panel, fake iPhone frame,
Dynamic Island, or browser-only choice controls.

When the browser prototype and functional specification contain different
amounts of information:

1. preserve all functional information;
2. show only decision-critical summaries on the Dashboard;
3. move supporting detail into a bottom sheet or second-level screen;
4. retain citations, counter-evidence, freshness, and invalidation;
5. never solve density by deleting safety information.

## 4. Dashboard visual contract

### 4.1 First viewport

At a 390-point-wide iPhone viewport, the first screen should establish this
order:

1. compact session greeting/header with search and alerts;
2. three-way horizon switch;
3. dark navy market-regime hero;
4. compact highest-priority alert;
5. watchlist pulse;
6. beginning of the candidate list;
7. fixed native five-tab navigation.

The user should understand the market stance and immediate action frame without
scrolling through a list of evidence factors.

### 4.2 Header

- Small line: market session and freshness.
- Main line: a short greeting or product context.
- Search and alert controls use compact circular surfaces.
- Demo status is present but visually subordinate. Repeating an amber "演示"
  label in every card is forbidden; accessibility labels may still carry the
  demo status.

### 4.3 Horizon switch

- Compact segmented control with `短线 · 0–5日`, `波段 · 1–8周`, and
  `中长线 · 2–24月`.
- Selected segment is a raised white surface.
- The control retains a minimum 44-point interaction target without visibly
  becoming oversized.
- Changing horizon updates all content and clears stale evidence-sheet state.

### 4.4 Market-regime hero

The hero is the dominant visual element:

- deep navy gradient/background with a restrained blue glow;
- small freshness label;
- large plain-language conclusion such as `谨慎偏多`;
- one-line rationale;
- circular score/progress treatment;
- inset action/playbook strip;
- no more than four compact driver chips in the collapsed state.

The complete driver list, fixed scale, contradictions, risk posture,
invalidation, timestamps, and citations remain available through `查看依据`.
They must not all be expanded inline on the Dashboard.

### 4.5 Priority alert

- One compact white card under `需要关注`.
- Symbol, two short status badges, one concise explanation, evidence and
  counter-evidence counts, freshness, and score.
- Tapping the card opens stock detail.
- A secondary affordance opens the full evidence/invalidation view.

### 4.6 Watchlist pulse

- Three compact quote cards fit across the phone width where practical.
- Each shows symbol, percentage move, a small sparkline, and a short state.
- Price, citations, fuller rationale, and source coverage live on the detail
  path.
- The section label identifies moomoo as a future read-only source and retains
  the demo-state wording in this phase.

### 4.7 Candidate rows

- Candidate presentation is a compact ranked row, not a full research memo.
- Show logo/monogram, symbol, state, one-line catalyst summary, score, and
  evidence count.
- Display the first two or three candidates, followed by a route to Discover.
- Counter-case, full reason, invalidation, citations, and long/short plan live
  in the candidate detail sheet/screen.

### 4.8 Bottom navigation

- Fixed five destinations: 首页, 发现, 提醒, 复盘, Agent.
- Active state uses the approved blue; inactive state is muted.
- Use consistent native icons rather than emoji.
- Respect safe-area insets and maintain 44-point targets.

## 5. Stock, chart, and adviser visual contracts

The later screens must follow their approved prototypes rather than start a new
visual language.

### 5.1 Stock detail

Use `ios-stock-detail-demo-v1.html` as the composition reference. Preserve:

- compact stock header and quote state;
- professional chart as the primary analytical surface;
- clear RSI and MACD portrait summaries;
- separate dated reported ownership and intraday estimated participation;
- forecast probabilities and calibration metadata;
- pattern prompts, fundamentals, evidence, and adviser entry points.

### 5.2 Candlestick and macro context

Use `kline-and-macro-context-v2.html` for chart density and context. Preserve:

- clear candles, axes, crosshair information, interval controls, and volume;
- selectable overlays and subcharts;
- Magic Nine and original Dragon Trend;
- 50% and 80% probability bands instead of a deterministic future line;
- always-visible portrait RSI and MACD;
- explicit `估算代理` presentation for intraday institutional/retail
  participation;
- visible market, macro, and geopolitical adjustment.

### 5.3 Adviser and risk-plan views

Use `advisor-architecture-v2.html` as the primary adviser reference. Preserve:

- evidence packet before opinion;
- adviser abstention and supplemental-research requests;
- bounded soft-factor adjustment;
- named public-philosophy style simulation disclaimer;
- long/short and conservative/balanced/aggressive plans;
- no order-submit, order-edit, or order-cancel action.

## 6. Native implementation boundaries

- Build native React Native views; do not ship the prototype HTML in a WebView.
- Derive reusable tokens for page background, navy surfaces, blue accent,
  positive/negative colors, typography, radius, borders, and shadow.
- Use focused presentational components with explicit props.
- Preserve repository/state interfaces and objective score behavior.
- Use SVG/native drawing for score rings, sparklines, and charts where needed.
- Keep expensive chart work isolated from normal Dashboard re-renders.
- No live APIs, LLMs, moomoo connection, authentication, or broker actions are
  added during this visual repair.

## 7. Visual regression and testing

Semantic tests are necessary but not sufficient.

Required coverage:

- component tests for interaction, accessibility, and progressive disclosure;
- a screenshot baseline at 390 × 844 points;
- an additional large-iPhone baseline at 430 × 932 points;
- explicit checks that the first viewport contains the market hero, priority
  alert, and watchlist heading;
- explicit checks that the nine full market drivers and all candidate memos are
  not expanded by default;
- manual comparison with the approved prototype for hierarchy, density,
  typography, color, and fold position;
- typecheck, lint, and the complete test suite.

Web screenshots may accelerate iteration, but they do not replace an iOS
Simulator or physical-device check.

## 8. Physical iPhone delivery

Cloud Codex can edit and push code but cannot install the app on the user's
iPhone. The final acceptance path returns to the user's Mac:

1. pull the completed branch;
2. use Node.js 22 and install dependencies;
3. regenerate or update the native iOS project;
4. run CocoaPods;
5. open the Xcode workspace;
6. sign with the user's Apple Account Personal Team;
7. connect and trust the iPhone;
8. enable Developer Mode;
9. install and launch `US Stock Helper` as an app icon;
10. start the Expo development server and verify Fast Refresh.

No signing credentials are committed. A free Personal Team build normally
expires after about seven days and must be signed and installed again. Paid
TestFlight distribution remains a later decision.

## 9. Definition of done

This visual realignment is complete only when:

- approved prototypes are present in Git and referenced by the implementation;
- the Dashboard visually follows the compact approved hierarchy;
- supporting evidence remains accessible through progressive disclosure;
- current domain, state, citation, and safety tests still pass;
- visual baselines exist for two iPhone sizes;
- the app passes typecheck, lint, and all tests;
- physical iPhone installation succeeds through Xcode;
- the app launches from the Home Screen and Fast Refresh is verified;
- the user reviews the native result before later backend work resumes.
