# US Stock Helper Product Design

Date: 2026-07-24
Status: Approved visual direction; written specification awaiting user review

## 1. Objective

Build an iPhone-first U.S. stock research assistant that:

- detects important market information early;
- explains how evidence may affect watched stocks and newly discovered candidates;
- combines news, market context, institutional-flow proxies, technical analysis, fundamentals, and calibrated adviser opinions;
- supports separate short, swing, and medium/long-term analysis;
- proposes traceable long or short trade plans without ever placing an order;
- remains factual even when the user's preferences or prior trades point in another direction.

The product is a decision-support tool, not an autonomous trader. It must never promise returns or describe a probabilistic forecast as certain.

## 2. Non-negotiable principles

1. **Evidence is the source of truth.** Every factual claim and material inference must link to source records.
2. **Algorithms create the base score.** LLM advisers are capped, backtest-calibrated soft factors.
3. **No LLM can create an action alert by itself.**
4. **No trading permission exists.** The app may save or copy a proposed plan and open moomoo, but it cannot submit, modify, or cancel orders.
5. **Facts are isolated from user preference.** Preferences may change presentation and risk-plan optimization, never evidence credibility, direction, or model confidence.
6. **No future functions or look-ahead leakage.** Research, backtest, paper, and live observation use point-in-time inputs and the same signal contracts.
7. **Estimates are labeled.** Intraday "institutional versus retail" activity is a proxy, not a claim that account identity is known.
8. **Uncertainty is visible.** Conflicts, missing evidence, stale data, calibration error, and adviser abstentions are shown rather than hidden.
9. **Token use is measured.** Deterministic processing precedes LLM calls; each escalation must provide expected information gain.

## 3. Delivery decomposition

The complete product is too large and data-dependent for one implementation cycle. It is divided into independently testable projects.

### Project 1: runnable iPhone product demo

Build the approved interface and navigation as a real React Native application using Expo and TypeScript. The user installs Expo Go on an iPhone and scans a QR code to test the app immediately. This phase uses clearly labeled deterministic demo fixtures and requires no API keys.

The demo validates:

- visual hierarchy;
- mobile interaction;
- navigation and page contents;
- chart clarity;
- information density;
- wording and safety boundaries.

It does not pretend that fixture data is live. A standalone TestFlight build comes after the interaction model stabilizes.

### Project 2: information and evidence foundation

Implement source adapters, normalization, entity resolution, deduplication, event detection, source provenance, point-in-time evidence snapshots, citations, and alert ingestion.

### Project 3: deterministic analysis and backtesting

Implement horizon-specific features, indicators, market context, institutional proxies, candidate discovery, forecasting, calibration, risk-plan generation, and point-in-time backtests.

### Project 4: evidence-gated adviser system

Implement compact evidence packets, research requests, adviser routing, bounded adviser influence, debate triggers, structured outputs, caching, and token observability.

### Project 5: adaptive market learning and user journal

Implement versioned market-experience memory, offline reflection, champion/challenger promotion, rollback, user operation and P&L journaling, and the preference/objectivity firewall.

### Project 6: production iOS beta

Add authentication, privacy controls, production data subscriptions, push notifications, monitoring, TestFlight distribution, and App Store readiness.

Only Project 1 is in scope for the next implementation plan.

## 4. Mobile information architecture

The bottom navigation has five destinations:

1. **Dashboard**
2. **Discover**
3. **Alerts**
4. **Journal**
5. **Agent**

Search and notification access remain globally available.

### 4.1 Dashboard

The default horizon is short term. The user can switch between:

- short: intraday through 5 trading days;
- swing: 1 through 8 weeks;
- medium/long: 2 through 24 months.

Dashboard components:

- market-sentiment conclusion and current playbook;
- key sentiment inputs and freshness;
- highest-priority evidence-gated alert;
- moomoo watchlist pulse;
- whole-market opportunity candidates;
- data-health and market-session state.

The sentiment card leads with a plain-language conclusion and risk posture, then exposes the supporting data. It must never show only an unexplained score.

### 4.2 Discover

The Discover page contains:

- asymmetric-upside candidate rankings;
- long and short candidate filters;
- horizon selector;
- catalyst, evidence freshness, liquidity, volatility, institutional proxy, technical, fundamental, and risk filters;
- observation-pool and action-eligible states;
- ranking explanations with citations.

"Potential multibagger" is a candidate-search label, never a promised outcome.

### 4.3 Alerts

Alerts are grouped as:

- information notice;
- observation;
- action-worthy research alert;
- risk warning.

Every alert includes:

- ticker and horizon;
- trigger and timestamp;
- source freshness;
- evidence and counter-evidence counts;
- base-score contribution;
- adviser adjustment, if any;
- invalidation conditions;
- direct citations.

Duplicate or superseded alerts must collapse into one event thread.

### 4.4 Journal

The journal records user-entered or imported:

- action and timestamp;
- quantity and execution price;
- realized and unrealized P&L;
- plan followed or overridden;
- execution delay and slippage;
- user notes.

Journal data can improve execution review, risk reminders, and UI preferences. It cannot become evidence that a stock will rise or fall.

### 4.5 Agent

The conversation interface supports:

- questions about a stock, event, market regime, or prior analysis;
- requests to inspect sources;
- comparison of long and short theses;
- requests for an alternative risk/return plan;
- explicit display of facts, inferences, scenarios, and rumors;
- research follow-up requests to the information layer.

The response order is:

1. objective conclusion;
2. evidence and counter-evidence;
3. uncertainty and missing information;
4. personalized risk scenario;
5. citations.

## 5. Stock detail

### 5.1 Header and horizon

The page shows symbol, company, exchange, price, change, market session, quote latency, watchlist state, and horizon.

### 5.2 Candlestick chart

The chart follows familiar professional-market conventions without copying another app's proprietary assets:

- clear candle bodies and wicks;
- right-side price scale and bottom time scale;
- open, high, low, close, volume, and change under the crosshair;
- 1-minute, 5-minute, 15-minute, 30-minute, hourly, daily, and weekly intervals;
- portrait overview and landscape full-screen mode;
- separate main-chart and sub-chart indicator controls;
- configurable colors and parameters;
- event markers that expand on tap rather than covering candles;
- visible source and data-latency state.

Main-chart overlays include:

- MA and EMA;
- VWAP;
- Bollinger Bands;
- Magic Nine / TD-style sequential;
- proprietary Dragon Trend indicator;
- detected chart patterns;
- support and resistance;
- calibrated forecast probability bands.

Sub-chart indicators include:

- volume;
- MACD;
- RSI;
- institutional/retail activity proxy;
- chip/position distribution where a defensible data source exists.

**RSI is a mandatory, default-visible portrait summary card.** It shows the value, threshold state, trend, divergence when detected, parameters, and time interval. It cannot be omitted merely because the landscape chart currently displays MACD.

MACD is also a default-visible portrait summary card and shows DIF, DEA, histogram direction, crossover state, and interval.

### 5.3 Forecast display

Forecasts display:

- horizon;
- median path;
- 50% and 80% probability bands;
- up, flat, and down scenario probabilities;
- historical calibration error;
- prediction timestamp and model version;
- invalidation conditions.

A single deterministic-looking future price line is forbidden.

### 5.4 Chart-pattern prompts

Pattern prompts include:

- three-bar fractals;
- head-and-shoulders and inverse head-and-shoulders;
- double top and double bottom;
- five-day moving-average pullback;
- "look-back smile" and other documented proprietary patterns;
- Magic Nine state;
- Dragon Trend state;
- RSI overbought, oversold, and divergence;
- MACD bullish, bearish, expansion, contraction, and crossover states.

Each pattern reports status, confirmation level, invalidation, horizon, and whether it is complete. Incomplete patterns cannot be reported as confirmed.

### 5.5 Institutional and retail views

The interface must not merge incompatible concepts.

**Reported ownership structure** uses dated filings such as institutional holdings, beneficial ownership, fund reports, and insider filings. It shows the reporting period and known lag.

**Intraday participation proxy** estimates institutional-like and retail-like activity using defensible market microstructure features. It shows:

- histogram or stacked share;
- estimation method version;
- confidence;
- source coverage;
- timestamp;
- explicit "estimated proxy" label.

These two views are both mandatory on the stock-detail page. Neither may be described as exact real-time account ownership.

### 5.6 Evidence and fundamentals

The stock page also exposes:

- current news and event chain;
- company filings and earnings;
- financial health;
- cash, debt, dilution, runway, margins, growth, valuation, and material risks;
- industry and supply-chain context;
- institutional reports and changes;
- source-level citations.

## 6. Market, macro, and geopolitical context

Market context is part of the deterministic base model, not a decorative news widget.

### 6.1 Market trend inputs

Adapters may use read-only moomoo data where permitted and must support fallback providers. Inputs include:

- broad and relevant indices;
- market breadth;
- sector and industry relative strength;
- realized and implied volatility;
- volatility term structure;
- rates and yield-curve changes;
- U.S. dollar;
- credit conditions;
- commodities and energy;
- liquidity and correlation stress.

### 6.2 Geopolitical event processing

The information layer detects geopolitical events during ingestion and separates:

- confirmed facts;
- disputed reports;
- inferred exposures;
- scenario assumptions.

It maps events to:

- regions;
- companies and subsidiaries;
- suppliers and customers;
- commodities and shipping routes;
- sanctions and export controls;
- defense, energy, semiconductor, financial, and other affected industries.

The model records directness, severity, direction, confidence, expected duration, and citations. A rumor cannot receive the same treatment as an official action.

### 6.3 Advice adjustment

The app shows:

- raw stock base score;
- market-context adjustment;
- adjusted score;
- exact plan changes caused by context.

Macro or geopolitical risk may lower leverage, tighten eligibility, change entry conditions, or raise alert severity. The adjustment cannot silently rewrite source facts.

## 7. Information and evidence layer

### 7.1 Source priorities

Source classes include:

1. regulators, exchanges, court records, government releases, and company filings;
2. company investor relations and official management communications;
3. licensed market, options, short-interest, and ownership data;
4. reputable news and industry sources;
5. social and community sources as lower-confidence leads.

The system must respect licenses, robots policies, paywalls, and provider terms. It must not bypass access controls.

### 7.2 Required provenance

Every evidence item stores:

- source URL and canonical identifier;
- publisher;
- title;
- author when available;
- publication time;
- first-seen time;
- fetched time;
- relevant excerpt or structured fact;
- affected entities;
- source class and reliability;
- fact, inference, scenario, or rumor label;
- correction and supersession links.

### 7.3 Evidence packet

An evidence packet is an immutable, versioned point-in-time snapshot containing:

- ticker and horizon;
- relevant events;
- market and sector context;
- key price and flow features;
- fundamental facts;
- supporting evidence;
- counter-evidence;
- conflicts;
- missing information;
- source references;
- snapshot hash.

Advisers read evidence packets and may issue structured supplemental-research requests. They do not browse directly.

## 8. Deterministic algorithms

### 8.1 Separate horizon scores

Short, swing, and medium/long models have separate features, weights, calibration, outcomes, and score histories. A signal from one horizon cannot silently alter another.

### 8.2 Signal families

Base scores may combine:

- event and news impact;
- overall market sentiment;
- market, macro, and geopolitical context;
- price, volume, volatility, liquidity, and market microstructure;
- institutional ownership and activity proxies;
- technical patterns and indicators;
- fundamentals, valuation, dilution, and financial health;
- catalyst timing;
- risk and tradability.

### 8.3 Candidate discovery

The discovery engine searches the full eligible universe, not only the moomoo watchlist. It must first enforce price, liquidity, tradability, data-quality, and event-risk constraints.

The ranking explanation shows positive contributors, negative contributors, missing data, and why a candidate is still only in observation or is eligible for an alert.

### 8.4 Magic Nine and Dragon Trend

Magic Nine uses a documented, independently implemented sequential-count method with configurable confirmation and cancellation rules.

Dragon Trend is an original indicator developed from documented components. It must:

- avoid copied proprietary formulas;
- avoid future functions;
- expose parameters and state transitions;
- include unit and point-in-time tests;
- publish backtest assumptions and failure regimes.

No indicator may be marketed as reliably profitable without evidence.

## 9. Adviser layer

The adviser module is inspired by the architectural lessons of
[`virattt/ai-hedge-fund`](https://github.com/virattt/ai-hedge-fund), but its outputs are never blindly followed.

The app offers 13 investor-style advisers. They are clearly labeled as style simulations, not the actual people or endorsements.

### 9.1 Invocation

Advisers run only for:

- high-scoring candidates;
- material algorithm/adviser conflicts;
- user-requested deep consultation.

The router selects only advisers relevant to the current horizon and question. The user may manually request others.

### 9.2 Output contract

Each adviser returns:

- adviser and version;
- horizon;
- direction and bounded value;
- calibrated confidence;
- thesis;
- strongest counterarguments;
- evidence references;
- missing evidence;
- research requests;
- abstention state;
- prompt, model, and snapshot versions;
- input, output, and cached token counts.

### 9.3 Fusion

- strong algorithm plus adviser agreement: raise rank or alert severity within the calibrated cap;
- strong algorithm plus adviser disagreement: retain the alert, expose conflict, and lower confidence;
- weak algorithm plus strong adviser: observation or research request only;
- insufficient evidence: no escalation.

Per-adviser and aggregate caps are chosen from out-of-sample calibration, not fixed by persona prestige.

## 10. Long, short, and risk-plan generation

Long and short plans use the same evidence and objective score. Selecting a direction does not reverse or rewrite facts.

Plans may propose:

- entry method and limit range;
- quantity;
- risk budget;
- invalidation and stop logic;
- target scenarios;
- holding horizon;
- maximum leverage;
- conditions that cancel the plan.

Short plans add:

- borrow availability and timestamp;
- estimated borrow fee;
- short-interest and crowding;
- squeeze and gap risk;
- halt and recall risk;
- explicit unbounded-loss warning.

The user can select conservative, balanced, or aggressive risk/return preferences. The choice may change position size, leverage, entry strictness, and eligible scenario. It cannot:

- raise forecast confidence;
- remove counter-evidence;
- change source credibility;
- override a hard risk constraint.

Plan numbers are generated by a deterministic risk engine. The LLM explains them but cannot override the engine.

## 11. Sentiment model

The sentiment model produces interpretable conclusions at event, stock, sector, and whole-market levels.

Inputs include:

- source credibility;
- novelty and first-seen time;
- surprise relative to consensus;
- urgency and propagation speed;
- stance dispersion;
- affected entities and exposure;
- expected duration;
- price and volume confirmation;
- breadth, volatility, options, rates, credit, dollar, and sector state;
- spam and bot-adjusted social signals.

The UI shows the conclusion, recommended posture, confidence, change, dominant drivers, contradictions, and citations.

## 12. Token-efficient LLM architecture

1. Collect, normalize, deduplicate, calculate indicators, and rank candidates without LLMs where deterministic logic suffices.
2. Send compact structured facts, numbers, short excerpts, and reference identifiers rather than raw documents.
3. Use small or inexpensive models for extraction and classification.
4. Escalate only difficult conflicts, top candidates, and user-requested deep analysis.
5. Cache by evidence snapshot hash, adviser, model, prompt version, and horizon.
6. Batch similar work and cancel stale requests.
7. Limit debate participants to advisers with expected relevance.
8. Track cache hit rate, tokens per useful alert, rank change after inference, and expected information gain per token.

A full adviser council must never scan every ticker or market tick.

## 13. Learning and memory

The design borrows bounded, curated, frozen memory snapshots and periodic reflection from
[`NousResearch/hermes-agent`](https://github.com/NousResearch/hermes-agent).

### 13.1 Market experience memory

This store may affect future candidate models after validation. It records:

- point-in-time evidence;
- market regime;
- prediction and proposed plan;
- subsequent market outcome;
- calibration error;
- inferred lesson and scope;
- version and provenance.

New lessons enter a research queue. They must pass offline backtests, out-of-sample validation, review, and champion/challenger promotion before affecting production. Every change is reversible.

### 13.2 User ledger and preferences

This separate store records user actions, P&L, execution outcomes, explicit preferences, and interface choices.

It may affect:

- presentation order;
- notification settings;
- risk-budget scenarios;
- execution-discipline feedback.

It may not affect:

- market facts;
- evidence ranking;
- source reliability;
- predicted direction;
- model confidence;
- candidate base score.

## 14. Safety and objectivity controls

The system-level order of precedence is:

1. verified facts;
2. source hierarchy;
3. uncertainty and contradiction;
4. abstention;
5. user preference.

Required controls:

- fact/inference/scenario/rumor labels;
- mandatory strongest-countercase pass;
- citation coverage check;
- no unsupported action claim;
- preference firewall;
- stale-data and market-session labels;
- risk-engine hard limits;
- prompt, model, evidence, and memory version ledger;
- no broker order endpoints or trading credentials.

## 15. Failure and degraded states

- If market data is stale, the chart and plan show staleness and action alerts are suppressed.
- If sources conflict, both versions and their reliability are displayed.
- If an official source corrects a report, dependent evidence packets and alerts are superseded.
- If an LLM fails or returns invalid structure, the adviser abstains; deterministic analysis remains available.
- If ownership data is old, the reporting period is shown and no real-time claim is made.
- If intraday proxy coverage is insufficient, the histogram is hidden behind an "insufficient data" state.
- If forecasting calibration is unavailable, the probability overlay is not shown.
- If moomoo is unavailable, the app uses its local watchlist snapshot and clearly labels delayed refresh.

## 16. Project 1 technical design

### 16.1 Stack

- Expo-managed React Native application;
- TypeScript;
- Expo Router;
- React Native SVG for the demo candlestick and indicator views;
- local typed fixture repository;
- lightweight local state only;
- no secrets and no production API calls.

This choice gives the fastest real-device feedback loop. A later EAS/TestFlight build can use the same application code.

### 16.2 Demo routes

- `/` — short-term Dashboard;
- `/discover` — candidate scanner;
- `/alerts` — alert feed;
- `/stocks/[symbol]` — stock detail;
- `/stocks/[symbol]/chart` — landscape-style chart;
- `/stocks/[symbol]/advisers` — adviser and long/short plan;
- `/journal` — user operation and P&L journal;
- `/agent` — safe conversation interface.

### 16.3 Demo interaction

The demo must support:

- three-horizon switching;
- opening stock detail from watchlist, alert, or discovery candidate;
- timeframe and indicator toggles;
- always-visible portrait RSI and MACD summaries;
- institutional/retail proxy and dated reported-ownership views;
- chart event-marker expansion;
- adviser selection;
- long/short switching;
- conservative/balanced/aggressive plan switching;
- evidence drawers with citations;
- saving a plan locally;
- adding a journal entry;
- safe Agent conversation fixtures;
- back navigation and bottom navigation.

### 16.4 Fixture rules

- Every demo screen displays "demo data" status.
- Fixtures use realistic but non-current values.
- Citation links use clearly labeled example sources or stable public sources.
- No fixture is presented as a live recommendation.

## 17. Project 1 acceptance criteria

The first runnable demo is complete when:

1. it launches with `npx expo start`;
2. an iPhone running Expo Go can load it by QR code on the same network;
3. all routes and primary interactions work without an API key;
4. Dashboard defaults to the short horizon;
5. stock detail visibly contains the candlestick chart, Magic Nine, forecast band, pattern prompt, RSI, MACD, and both ownership/activity views;
6. adviser view supports selected style advisers, algorithm/adviser conflict, long/short plans, risk preference, leverage, entry, quantity, invalidation, and target;
7. no screen contains an order-submission action;
8. citations, demo-data labels, stale/conflict states, and risk warnings are visible;
9. TypeScript, lint, and automated component/navigation tests pass;
10. the layout remains usable on current standard and compact iPhone viewports.

## 18. Explicitly deferred from Project 1

- live moomoo integration;
- production market and news feeds;
- web crawling;
- production push notifications;
- real institutional-flow estimation;
- real forecasting;
- real LLM calls;
- authentication and cloud sync;
- TestFlight distribution;
- order execution of any kind.

These items are deferred so the user can first validate the mobile product shape without mistaking mock data for production analysis.
