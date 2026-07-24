# Calm Alpha iOS Figma Design Specification

Date: 2026-07-24  
Status: Dashboard, stock detail, and adviser council visual direction approved; editable Figma file pending account login and final user review.

## 1. Objective

Create the visual source of truth for the first usable iPhone version of US
Stock Helper. The design must feel calm, institutional, fast, and trustworthy
while retaining the information density needed by a short-term investor.

The user-approved visual direction is **Calm Alpha**:

- deep navy is reserved for the primary market conclusion and decision surface;
- white surfaces carry supporting information;
- green and red express price or risk semantics only;
- blue expresses navigation and interaction;
- evidence and counter-evidence remain one tap away through progressive
  disclosure.

The final approved Figma file is the authority for visual implementation. This
specification remains the authority for behavior, data truthfulness, safety,
accessibility, and degraded states. A visual ambiguity must not weaken those
requirements.

## 2. Initial Figma scope

The first Figma delivery contains:

1. design system and reusable components;
2. Dashboard;
3. stock detail — chart and indicators state;
4. stock detail — decision and evidence state;
5. adviser council — committee overview;
6. adviser council — evidence-first conversation.

Discovery, alert feed, journal, and standalone Agent screens will reuse this
system in later design rounds.

No application code is changed until the user approves the final Figma file.

## 3. Canvas and device

- Primary frame: iPhone portrait, 390 × 844 pt.
- Secondary validation frame: iPhone portrait, 430 × 932 pt.
- Safe-area behavior must be explicit.
- All screens use an 8 pt spacing system with 4 pt half-steps.
- Minimum touch target: 44 × 44 pt.
- Primary page margin: 16 pt.
- Card radius: 15–23 pt depending on hierarchy.
- Supporting cards use borders and very light shadows; the market hero may use
  the only materially elevated shadow.

## 4. Visual tokens

### 4.1 Color

- Ink: `#0B1729`
- Secondary text: `#62728A`
- Muted text: `#75869C`
- App background: `#F3F6FA`
- Surface: `#FFFFFF`
- Border: `#DBE3ED`
- Hero start: `#15345E`
- Hero end: `#0A1A30`
- Navigation blue: `#2878E5`
- Positive green: `#0BBF78`
- Confirmation green surface: `#E1F7EE`
- Negative red: `#F64F5E`
- Warning amber: `#B17608`
- Warning surface: `#FFF4DF`

Color may not be the only carrier of meaning. Every positive, negative,
warning, freshness, or uncertainty state also includes text or an icon.

### 4.2 Typography

Use the native iOS type stack: SF Pro Display / SF Pro Text with PingFang SC
fallback for Chinese.

- Hero verdict: 27 pt, heavy, 1.0–1.1 line height.
- Screen greeting/title: 22–27 pt, heavy.
- Section title: 17 pt, heavy.
- Card title: 14–17 pt, semibold or heavy.
- Body: 11–13 pt, regular or medium.
- Metadata: 9–10 pt, medium.
- No required information may be set below 9 pt in the implementation.

Numeric fields use tabular figures where available.

### 4.3 Motion

- Press feedback begins within 16 ms.
- Normal state transition: 180–240 ms, ease-out.
- Exit transition: 150–200 ms, ease-in.
- Animate opacity and transforms instead of layout-heavy properties.
- No looping attention animation is allowed on trading signals.
- Reduced-motion users receive an equivalent static transition.

## 5. Dashboard

### 5.1 Reading order

1. market session and greeting;
2. short / swing / long-term horizon;
3. market sentiment conclusion;
4. recommended posture and risk constraint;
5. strongest current alert;
6. moomoo watchlist;
7. discovery candidates;
8. bottom navigation.

### 5.2 Market hero

The market hero is the only dominant dark card. It contains:

- freshness;
- direct conclusion such as “谨慎偏多”;
- plain-language explanation;
- calibrated score;
- today’s recommended posture;
- total risk and leverage ceiling;
- dominant driver chips;
- “查看判断依据与来源” entry point.

The conclusion and recommendation must remain visually distinct. A bullish
conclusion does not imply immediate buying.

### 5.3 Alert and watchlist

The top alert contains the ticker once, a separate signal title, evidence and
counter-evidence counts, freshness, and a horizon-specific score.

The watchlist source is labeled as moomoo. Watchlist membership is not evidence
for a bullish score.

## 6. Stock detail

### 6.1 Chart state

The chart state includes:

- price, session, freshness, and demo/live status;
- horizon selector;
- objective short-term conclusion;
- clear candlestick chart modeled after mature market software;
- configurable timeframe;
- completed-candle Magic Nine markers;
- probabilistic forecast band and dashed median path;
- pattern prompts including three-day fractal and five-day-line pullback;
- RSI value and overbought/oversold interpretation;
- MACD state and histogram;
- institutional/retail activity proxy histogram;
- explicit proxy methodology and data-quality label.

Forecast graphics must not look like guaranteed future prices. Magic Nine and
all other indicators use completed point-in-time data and never future
functions.

Institutional/retail intraday participation is an inferred proxy. It must not
be presented as direct real-time account ownership. Dated 13F or other filings
are shown separately with their reporting period.

### 6.2 Decision state

The decision state includes:

- objective scores for news/sentiment, technicals, funds, fundamentals, and
  macro context;
- broad-market and geopolitical context;
- long and short modes sharing the same fact layer;
- conservative, balanced, and aggressive risk-return preferences;
- limit range, position risk, invalidation, stop logic, target range, holding
  window, and leverage ceiling;
- explicit cancellation conditions;
- evidence package and counter-evidence;
- adviser entry point;
- persistent statement that the application cannot place orders.

Plan numbers are generated by a deterministic risk engine. An LLM may explain
them but cannot override the risk engine.

## 7. Thirteen-style adviser council

### 7.1 Profiles

The interface provides these style simulations:

1. Damodaran — valuation narrative;
2. Benjamin Graham — margin of safety;
3. Bill Ackman — concentration and catalysts;
4. Cathie Wood — innovation growth;
5. Charlie Munger — business quality;
6. Michael Burry — contrarian and bubble risk;
7. Mohnish Pabrai — low-risk asymmetry;
8. Nassim Taleb — tail risk;
9. Peter Lynch — understandable growth;
10. Phil Fisher — deep growth research;
11. Rakesh Jhunjhunwala — long-term growth;
12. Stanley Druckenmiller — macro momentum;
13. Warren Buffett — quality at a reasonable price.

Each profile is visibly labeled as a style simulation, not the person, an
endorsement, or current personal advice.

### 7.2 Committee overview

The screen shows:

- immutable objective algorithm conclusion;
- adviser aggregate soft factor and calibrated cap;
- intelligent relevant-adviser mode and full 13-adviser mode;
- expected token usage;
- each adviser’s focus, direction, confidence, abstention, and version;
- consensus distribution;
- strongest disagreements and missing evidence;
- research request entry.

Default routing activates only advisers relevant to the horizon and conflict.
The user may request the full council. Adviser prestige never determines
weight; weights and caps come from out-of-sample calibration.

### 7.3 Evidence-first conversation

The conversation shows:

- active evidence snapshot and freshness;
- evidence and counter-evidence counts;
- objective answer before personalized scenarios;
- adviser-specific arguments with inline citations;
- strongest countercase;
- missing evidence and “申请补充调查” action;
- a deterministic plan summary;
- fact, inference, scenario, and rumor labels;
- a persistent no-trading statement.

The council may abstain. Insufficient or stale evidence cannot produce an
escalated action recommendation.

## 8. Safety and objectivity

The mandatory precedence is:

1. verified facts;
2. source hierarchy;
3. uncertainty and contradiction;
4. abstention;
5. user preference.

The application:

- has no broker order API or trading credentials;
- never submits orders;
- never changes facts, direction, source reliability, or confidence to please
  the user;
- may record user actions, P&L, discipline, interface choices, and explicit
  preferences in a separate ledger;
- may use that ledger for presentation, notification, risk-budget scenarios,
  and discipline feedback only;
- learns market experience only after offline validation and reversible
  promotion.

## 9. Evidence and degraded states

Every material conclusion supports source citations, first-seen time,
freshness, evidence snapshot, and strongest counter-evidence.

- Stale market data suppresses action alerts and marks plans stale.
- Conflicting sources are displayed together with reliability.
- Corrected sources supersede dependent evidence.
- Missing institutional proxy coverage hides the histogram.
- Missing calibration hides the forecast overlay.
- Adviser failure produces abstention while deterministic analysis remains.
- moomoo failure uses a labeled local watchlist snapshot.

## 10. Figma file structure

The editable file uses these pages:

1. `00 Cover & Decisions`
2. `01 Foundations`
3. `02 Components`
4. `03 Dashboard`
5. `04 Stock Detail`
6. `05 Adviser Council`
7. `06 Interaction & States`
8. `07 Accessibility & Handoff`

Components use Auto Layout and named variants. Color, spacing, radius, and type
tokens are variables or shared styles. Frames include annotations for data
truthfulness, source visibility, degraded states, and motion.

## 11. Acceptance criteria

The design phase is complete only when:

- all three approved flows exist as editable Figma frames;
- the component and variable pages are present;
- 390 × 844 and 430 × 932 layouts have been checked;
- Dashboard information hierarchy matches the approved Calm Alpha direction;
- stock detail contains K-line, Magic Nine, forecast band, pattern prompt, RSI,
  MACD, and ownership/activity proxy;
- adviser council contains all 13 style simulations, consensus, disagreement,
  citations, research requests, and safe conversation;
- no screen contains an order-submission action;
- all material recommendations expose evidence and counter-evidence;
- the user reviews and explicitly approves the final Figma file.

