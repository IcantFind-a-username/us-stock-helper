# Quant Foundations with Plain-Language Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first tier of genuinely useful quantitative algorithms — market breadth, sector relative strength, time-of-day-normalized relative volume, and range-based volatility — and present every one of them in language an ordinary investor can understand, without ever crossing into 喊单.

**Prerequisite:** Runs after the demo-parity plan (2026-08-15-demo-parity-market-brief-and-council.md); Task 5 wires new factors into the `GET /market-brief` driver slots that plan creates.

**Owner context:** Franz is a quant-finance novice. Every surfaced number must answer, in plain Chinese: 这是什么 / 现在说明什么 / 什么情况下这个判断作废. Plain language is a presentation layer over honest numbers — it must never soften uncertainty or hide sample sizes.

## Global Constraints (additive to the standing red lines)

- 白话不喊单: plain-language copy states what an indicator measures and its current reading; it never instructs an action. Banned verbs in generated copy: 买入/卖出/加仓/抄底/梭哈 (test-enforced, extending the existing safety-copy test pattern).
- Three-layer presentation contract for every quant surface: (1) 一句话白话结论; (2) 展开解释 — what it measures, with a lived-world analogy, fixed per indicator, versioned; (3) 数字层 — value, historical context, sample size, and 失效条件. Layers 1-2 come from a reviewed static vocabulary file, not free generation.
- Honest scope labels: breadth computed over the watchlist universe is labeled 自选广度, never 市场广度; full-market breadth requires a universe source and stays visibly unavailable until one exists.
- Every new indicator ships with: no-lookahead test (PIT), degenerate-input tests (empty/short/flat series), a methodology section in docs/indicator-methodology.md, and an algorithm version string carried to the wire.
- No new data sources in this plan beyond what the market gateway already serves (daily/intraday bars for watchlist symbols and liquid sector ETFs). Universe expansion is a separate decision.

## Tasks

### Task 1: Breadth engine (analysis_core)
`breadth.py`: advance/decline line, percent-above-MA50/MA200, new-high/new-low differential over a configurable symbol universe of daily bars; every metric returns typed unavailable below minimum sample. Version `breadth-v1`. RED first: hand-computed fixtures, PIT test (a bar added after cutoff cannot change yesterday's breadth), sub-minimum universe → unavailable.

### Task 2: Sector relative strength (analysis_core)
`relative_strength.py`: RS ranking of sector ETFs vs benchmark over configurable lookbacks with warm-up honesty; average pairwise correlation regime (risk-on/off) with the window disclosed. Version `sector-rs-v1`.

### Task 3: Time-of-day relative volume (analysis_core)
`rvol.py`: current cumulative intraday volume ÷ same-time-of-day historical mean curve (N sessions, N disclosed); early-session and missing-history return unavailable, never a padded 1.0×. Version `rvol-tod-v1`. This quantifies the currently informal 量价确认 language.

### Task 4: Range-based volatility upgrade (analysis_core)
Parkinson and Garman-Klass estimators beside the existing close-to-close `volatility.py`; estimator choice explicit in output metadata; cross-checked against close-to-close on synthetic series with known variance. Version `range-vol-v1`.

### Task 5: Serve the factors (analysis_api + market-brief)
Wire breadth/sector-RS into the market-brief driver slots created by the demo-parity plan (replacing their named-unavailable placeholders where honest data now exists, keeping 自选广度 scope labels); RVOL and range-vol join the per-symbol decision payload. Contract tests pin scope labels and version strings on the wire.

### Task 6: Plain-language vocabulary layer (server + mobile)
- Server: `plain_language.py` — fixed, versioned mapping from each indicator state to 白话结论 + 展开解释, with the banned-verb test and a completeness test (every reachable state has copy; a new state without copy fails the build, never falls back to jargon or silence).
- Mobile: `PlainReadingCard` component implementing the three-layer contract (headline → expandable explainer → numbers with sample size and 失效条件); wired on the stock page for RVOL/volatility and the dashboard brief for breadth/sector drivers.
- RED first: screen tests pinning all three layers render, jargon-only rendering fails, banned verbs absent.

### Task 7: Magic Nine plain-language reading (Franz request, 2026-08-15)
The served magicNine state currently renders as jargon ("九转 2 · 尚未完成 · 完美 · 14 根前"). Add its full three-layer reading to the plain-language vocabulary: what TD Setup counts (consecutive closes vs. four bars earlier), what reaching 9 suggests (trend persistence nearing exhaustion — a caution zone, not a trade signal), what 完美/perfection adds, what interruption means ("序列中断则重新计数"), and the reading for every reachable state (counting up/down × count bucket × completed recently × perfected). Rendered via PlainReadingCard beside the existing chart badge; the badge itself stays.

### Task 8: Candlestick pattern detection engine with explained hints (Franz request, 2026-08-15)
`analysis_core/patterns_shapes.py` (name distinct from the existing td_setup module): deterministic, completed-bars-only detectors, each with a versioned rule spelled out in the methodology doc:
- 顶分型/底分型 (three-bar fractal top/bottom);
- W底/双头 (double bottom / double top with neckline);
- 头肩顶/头肩底 (head and shoulders top/bottom with neckline);
- 回踩五日线企稳 / 回眸一笑 (pullback to MA5 that holds and turns — define the exact rule transparently in the methodology doc; this is a colloquial retail pattern, so the definition we ship IS the spec).
Each detection returns: name, status (`forming`/`confirmed`/`invalidated`), the exact invalidation condition (e.g. "收盘跌破颈线"), the bars involved (for chart markers), minimum-window honesty (below the detector's window → typed unavailable, per the 四点七 pattern-factor lesson), and version `patterns-shapes-v1`.
Wire: serve through the snapshot/decision technical section (the demo `PatternSignal` mobile contract already models this); mobile renders a pattern card listing current detections and draws tap-to-expand markers on the chart. Every pattern hint carries its three-layer reading: 一句话含义 (e.g. 底分型: "连续下跌后，中间这根K线的最低点比两边都低，又收回来了——短线卖压可能衰竭的第一个迹象"), 展开解释 (formation logic and what confirms/voids it), 数字层 (which bars, invalidation price, and the honesty line "历史胜率待回测" until the phase-2 walk-forward engine attaches real hit rates).
PIT tests: a pattern may only use completed bars; adding a future bar must never change an already-emitted detection for earlier timestamps; forming→confirmed/invalidated transitions must be reproducible from the bar sequence alone.
Presentation red line unchanged: hints describe structure and invalidation, never instruct an action; no efficacy claims before backtest.

### Task 9: Methodology documentation
Extend docs/indicator-methodology.md with each new algorithm: formula, source references, validation rules, known limitations, and the plain-language vocabulary table — including every pattern definition from Task 8 and the Magic Nine reading table from Task 7 (so the copy is reviewable as part of the methodology, not scattered in code).

## Phase 2 (separate plan, larger)
Conformal calibration for the forecast band (the unlock for the withheld probability overlay), walk-forward backtest engine attaching honest hit rates to TD Setup / Dragon Trend / patterns, and the event-study engine over information-layer events once 阶段 6 source adapters widen coverage.
