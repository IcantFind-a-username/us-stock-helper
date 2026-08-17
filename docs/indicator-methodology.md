# Indicator methodology and live-use gates

## What this project will reproduce

An indicator may be added when at least one of the following is available:

1. A public mathematical specification.
2. A legitimately supplied formula or licensed specification.
3. A behavior that can be independently implemented with standard, public
   techniques without claiming formula-level equivalence.

Unknown vendor source code, leaked formulas, paywall bypasses and decompilation
are out of scope. A transparent alternative must be labeled as an alternative.

## Where the code lives

`services/analysis_core/us_stock_helper_core` is the canonical home for every
indicator. `patterns.td_setup` carries the per-bar counts, each completed run
and its bar 8/9 perfection under `td-setup-close-4-v2`; `trend.dragon_trend`
carries the transparent trend system under `dragon-trend-ema-atr-volume-v1`;
`patterns_shapes.py` (distinct from `patterns.py`) carries the chart-shape
detectors — 顶分型/底分型/W底/双头/头肩顶/头肩底/回踩五日线企稳 — under
`patterns-shapes-v1`. An earlier standalone prototype of the first two lives
in the repository history on `main` (commit `4170859`) and is not maintained.
`breadth.py` (`breadth-v1`), `relative_strength.py` (`sector-rs-v1`),
`rvol.py` (`rvol-tod-v1`) and the two new range estimators added to
`volatility.py` (`range-vol-v1`) live in the same package. `plain_language.py`
(`plain-language-v1`) is the reviewed, versioned vocabulary that turns those
results (and the existing TD Setup / Magic Nine ones) into the plain-language
copy described below; its mobile mirror is
`apps/mobile/src/i18n/plainLanguage.ts`. `institutional_flow_provider.py`
lives one layer up, in `services/analysis_api/src/us_stock_helper_analysis_api`,
because it blends two market-gateway sections rather than computing anything
from raw bars.

Every published series here stays `None` through warm-up rather than showing an
early guess, and a published value never changes when later bars arrive. That
property is what the regression tests protect, and it is the precondition for
any backtest or calibration to mean anything.

## Current implementations

### TD nine count / 神奇九转

For candle `t`, compare `close[t]` with `close[t-4]`.

- Consecutively lower closes count toward a potential bullish exhaustion setup.
- Consecutively higher closes count toward a potential bearish exhaustion setup.
- A count of nine emits an exhaustion warning.
- “Perfected” checks use only bars already closed at the ninth count.

The output is a warning, not an automatic buy or sell instruction. Public
descriptions also note that the pattern behaves differently in strong trends
and range-bound markets.

### Open Dragon Trend

“神龙指标” is not a single public standard. The implementation in this
repository is an independent, fully disclosed trend system:

- EMA 8 / 21 / 55 alignment for trend state.
- Wilder ATR 14 around the slow line for a dynamic risk channel.
- Relative volume for transition confidence: the bar's volume over the simple
  average of the twenty bars *before* it. The bar is excluded from its own
  baseline, so a spike is not divided by a mean it inflated.
- Signals only on a state transition and only use current or earlier candles.

Its parameters will be optimized only through walk-forward validation. It is
not represented as the formula of any specific paid vendor product.

### Pattern shapes / 形态检测 (`patterns_shapes.py`, `patterns-shapes-v1`)

Distinct from `patterns.td_setup` above: this module only detects classic
candlestick *shapes*, each on completed bars only, each with an explicit
`forming` / `confirmed` / `invalidated` status and a machine-checkable
invalidation condition. It never claims a historical hit rate; every served
reading carries the fixed disclosure "历史胜率待回测" until a phase-2
walk-forward backtest attaches one.

**顶分型 / 底分型 (three-bar fractal top/bottom).** For bar `i` (`1 <=
i <= n-2`): a 顶分型 fires when `high[i] > high[i-1]` and `high[i] >
high[i+1]`; a 底分型 fires when `low[i] < low[i-1]` and `low[i] <
low[i+1]`. Confirmed the instant the third bar closes — there is no partial
fractal to call "forming". Minimum window: 3 bars.

**W底 / 双头 (double bottom/top with neckline).** Two local extrema (troughs
for W底, peaks for 双头) at least three bars apart, within 4% of each other's
depth/height. The neckline is the highest high (W底) or lowest low (双头)
between them. Scanning forward bar-by-bar from the second extremum: the
first close to break the neckline in the pattern's favor confirms it; the
first close to break back past the second extremum *before* the neckline
breaks invalidates it. Neither happening yet within the given bars reads as
`forming`. Minimum window: 7 bars.

**头肩顶 / 头肩底 (head and shoulders with neckline).** Three extrema
(left shoulder, head, right shoulder) where the shoulders are within 8% of
each other and the head clears both by at least 3%. The neckline is the
average of the two troughs (头肩顶) or peaks (头肩底) flanking the head.
Same forward scan as W底/双头: neckline break confirms, a close reclaiming
the head's own extreme first invalidates. Minimum window: 8 bars.

**回踩五日线企稳（回眸一笑）.** A colloquial retail pattern with no textbook
definition, so this rule *is* the spec (v1):

1. MA5 must be rising at the touch bar (`MA5[t] > MA5[t-3]`).
2. A touch bar: close within 1.5% of that day's MA5, and below the prior
   bar's close (the pullback).
3. Confirmation ("回眸一笑"): the first later bar whose close is above the
   prior close, at or above that day's MA5, with MA5 still rising.
4. Invalidation: a close before confirmation falling below `MA5 × (1 -
   2%)`.
5. Neither happening yet reads as `forming`.

Minimum window: 8 bars (the earliest index at which both `MA5[t]` and
`MA5[t-3]` exist).

**No-lookahead guarantee.** Every detector only ever reads bars up to its own
`event_index`; a `confirmed`/`invalidated` signal, once emitted for a given
bar sequence, is reproduced byte-for-byte by a later call over a longer
sequence that still contains that same prefix (see the PIT tests in
`services/analysis_core/tests/test_patterns_shapes.py`). Below its own
minimum window, a detector reports typed-unavailable
(`quality_status="unavailable"` with a `missing_reason`) rather than a
measured zero — the same lesson recorded in `docs/roadmap-to-delivery.md`
§四点七 about the pattern factor claiming "measured 0" for a window no
detector had actually read.

`scoring.py`'s `pattern` factor and the market-gateway snapshot's
`indicators.patternShapes` entry both read the same `detect_pattern_shapes`
output — only `confirmed` signals vote in the score, so the served hint and
the decision score can never disagree about what "confirmed" means.

**Known limitations.** No detector here has an attached historical hit rate —
`reading_honesty` fixes "历史胜率待回测" on every emitted signal until the
phase-2 walk-forward backtest engine attaches one; until then these are
structural descriptions, not evidence of edge. The v1 double-extreme and
head-and-shoulders scanners resolve each candidate the first time either the
confirming or failing condition is hit and do not currently walk a
`confirmed` breakout back to `invalidated` if price later reverses through
the neckline again (the module docstring calls this out explicitly) — the
`invalidation` string still names that condition for the reader, it is just
not auto-tracked past confirmation yet. 回踩五日线企稳（回眸一笑）has no
textbook definition; the rule in this module *is* the spec, not a
transcription of an external standard, so it should be read and versioned
as this project's own definition.

### Market breadth (`breadth.py`, `breadth-v1`)

Three independent metrics, each computed over a caller-supplied `universe` —
a mapping of symbol to that symbol's own daily bar history. The module never
labels its own scope: a five-name watchlist and the full exchange produce the
same shaped result, and every result carries `universe_size` so the caller
can choose, and disclose, the honest label (自选广度 vs 市场广度).

**Advance/decline line.** Each symbol's own bar history is walked
independently: for every pair of consecutive completed bars knowable as of
the cutoff, that symbol contributes one advance (`close[t] > close[t-1]`),
decline (`close[t] < close[t-1]`), or unchanged event, dated by the later
bar's `closed_at`. Events are grouped by date; a date only publishes a
`BreadthPoint` — `advancers`, `decliners`, `unchanged`, `net = advancers -
decliners`, and the running `cumulative` — once at least `minimum_universe`
symbols contributed that date.

**Percent above MA(period).** For each symbol with at least `period`
completed bars knowable at the cutoff — reusing `indicators.moving_average`
unmodified, so "eligible" means exactly what that function needs to publish a
value — compares `close[-1]` to its own `MA(period)`: a strictly greater
close counts "above", a strictly lower close counts "below", an exact tie
counts toward neither. The result is `100 * above_count / eligible_symbols`.
`market_brief.py` calls this with `period=50` over the operator's watchlist
by default (capped at 60 symbols), and its own `_breadth_label` mirrors this
module's 55%/45% strong/weak thresholds (see the plain-language table below)
so the wire's conclusion text and the vocabulary layer never disagree.

**New-high/new-low differential.** Over a trailing `lookback` (default 252
completed daily bars, the conventional 52-week window), a symbol makes a new
high when its latest bar's `high` is at least the maximum `high` across the
window (inclusive of itself), symmetrically for new low on `low`; a single
outside bar can count toward both tallies. `differential = new_highs -
new_lows`. A symbol is "eligible" once it has at least `lookback` bars
knowable at the cutoff.

**Minimum-sample gates.** Every metric is gated on two independent axes:
`universe_size < minimum_universe` (default 5 — small enough to be usable,
large enough that "most of the universe" describes more than one or two
names), and — separately — how many symbols individually have enough of
their *own* history to compute that metric (`eligible_symbols`). Falling
short on either axis returns a typed-unavailable result
(`quality_status="unavailable"`, populated `missing_reason`), never a zero or
a partial number dressed up as complete.

**PIT rule.** Every function selects each symbol's bars through
`select_bars_as_of(bars, decision_cutoff)` before any tally runs, so a bar
not yet knowable at the cutoff cannot enter any count. `test_breadth.py`
pins that a bar added after the cutoff cannot change yesterday's advance/
decline point, percent-above-MA reading, or new-high/low differential.

**Validation rules (what the tests pin).** Hand-computed fixtures for the
A/D line, percent-above-MA, and new-high/low differential
(`test_hand_computed_*`); sub-minimum universe → typed unavailable, not zero
(`test_sub_minimum_universe_is_typed_unavailable_not_zero`); insufficient
per-symbol history → typed unavailable even when the universe itself is
large enough (`test_insufficient_per_symbol_history_is_typed_unavailable`);
daily-bar-only and completed-bar-only input validation
(`test_daily_bars_are_required`); an empty universe is unavailable, not an
error (`test_empty_universe_is_typed_unavailable_not_an_error`).

**Known limitations.** Breadth computed over a watchlist is not market
breadth — this module deliberately never stamps its own scope label, so the
caller must (and `market_brief.py` does: "自选广度"); a genuine full-market
breadth reading needs a universe source this project does not yet have.
Small universes (5–60 names in current wiring) make the percentage far more
sensitive to any single name moving than a true market-wide breadth reading
would be.

### Sector relative strength and correlation regime (`relative_strength.py`, `sector-rs-v1`)

Two independent readings, both computed from daily bar series.

**RS ranking.** For each requested lookback (default `(21, 63, 126)` trading
days, roughly 1/3/6 months) and each sector, `sector_return = latest_close /
EMA(lookback) - 1`, where the EMA anchor comes from `warmup_ema_series` — the
exact function MACD and Dragon Trend already use, so the warm-up discipline
(no value before a full window has closed; a published value never changes
when later bars arrive) is one proven implementation reused, not a second one
to independently trust. `benchmark_return` is the same formula applied to the
benchmark series. `excess_return = sector_return - benchmark_return`; within
each lookback's cross-section, sectors are ranked by `excess_return`
descending (rank 1 = strongest excess return). A sector without a warmed-up
EMA at a given lookback is typed unavailable for that lookback only — one
starved lookback does not block the others. If the cross-section of
warmed-up sectors falls below `minimum_universe` (default 2), every sector at
that lookback returns unavailable rather than a partial or misleading order.

**Correlation regime.** The average pairwise Pearson correlation of daily
returns over a disclosed trailing `window` (default 20 sessions). A sector
is eligible once it has `window + 1` completed bars knowable at the cutoff
(enough to form `window` returns) *and* its return series is not perfectly
flat — a flat window has zero variance, which makes correlation with
anything mathematically undefined, not a measured zero, so it is excluded
rather than silently contributing one. `regime = "risk_off"` when the
average pairwise correlation is at or above `risk_off_threshold` (default
0.6 — the group is moving together, a macro-driven tape), `"risk_on"` when
at or below `risk_on_threshold` (default 0.3 — moves are differentiated /
idiosyncratic), `"neutral"` between the two. Both thresholds and `window`
are carried on the result so a consumer never has to guess what produced the
label. `minimum_universe` defaults to 3 — the smallest group for which a
pairwise average describes more than one single pair.

**PIT rule.** Both functions PIT-select bars via `select_bars_as_of` before
any return or EMA is computed; `test_relative_strength.py` pins that a bar
added after the cutoff cannot change yesterday's ranking or yesterday's
correlation regime.

**Validation rules.** Hand-computed excess return and rank fixture
(`test_hand_computed_excess_return_and_rank`); insufficient warm-up on one
sector does not block others from ranking
(`test_insufficient_warm_up_is_typed_unavailable_without_blocking_others`);
sub-minimum universe → unavailable, not zero; hand-computed risk-on
(average pairwise correlation ≈ −1/3) and risk-off (≈ 1.0) fixtures; a flat
series is excluded from the eligible set and can itself trip typed-
unavailable when that drops the eligible count below `minimum_universe`;
insufficient window length → unavailable.

**Known limitations.** RS ranking only ever compares against one configured
benchmark and one configured sector-ETF universe — there is no broader
"which sectors exist" discovery; a sector missing from that configured list
is simply never ranked. The risk-on/risk-off/neutral regime is a coarse
two-threshold bucketing of a continuous statistic (0.3/0.6), an engineering
judgment call, not a calibrated or validated regime-detection model.

### Time-of-day relative volume (`rvol.py`, `rvol-tod-v1`)

**Formula.** `ratio = current_cumulative_volume / historical_mean_cumulative_volume`.
`current_cumulative_volume` is the sum of volume from the current session's
start through its most recent time-of-day bucket.
`historical_mean_cumulative_volume` is the mean, across exactly
`lookback_sessions` (default 20, roughly one trading month) prior sessions,
of each prior session's own cumulative volume through the bar matching the
current session's latest bucket. This compares "now" to the *same clock
time* on prior sessions — never to yesterday's full-day total, which
conflates two different session lengths and always reads "low" in the
morning and "high" by the close regardless of what is actually happening.

**Session-bucketing injection.** The module has no notion of when a US
session opens, when lunch goes quiet, or when the close prints extra volume
— none of it is hardcoded here. Every bar is placed into a session and a
time-of-day bucket by a single caller-supplied `session_bucket: OHLCVBar ->
SessionBucket(session, bucket)` function, keeping the module exchange- and
calendar-agnostic and trivially testable with synthetic clocks.

**Unavailability rules — four situations, never a padded 1.0×.**
1. *No data at cutoff*: `select_bars_as_of` leaves zero bars knowable as of
   `decision_cutoff` — there is no completed candle yet to place into any
   session or bucket at all.
2. *Early session*: fewer than `minimum_buckets_elapsed` (default 2 — a
   single bar is the opening print itself, not yet comparable to anything)
   buckets have elapsed in the current session.
3. *Insufficient history*: fewer than `lookback_sessions` prior sessions
   have a bar landing in exactly the current bucket. A prior session missing
   that exact bucket does not interpolate or pad a substitute value — it
   simply does not count toward N.
4. *Zero baseline*: the matched historical baseline sums to zero or less.

A live result always used exactly `lookback_sessions` — never fewer dressed
up as complete (`RelativeVolumeResult.__post_init__` enforces
`sessions_used == lookback_sessions` on every live result).

**PIT rule.** `select_bars_as_of(bars, decision_cutoff)` runs before session
grouping; `test_a_bar_available_after_the_cutoff_cannot_join_the_baseline`
and `test_a_later_bar_added_after_the_fact_never_revises_an_earlier_result`
pin this directly.

**Validation rules.** Hand-computed ratio at a bucket boundary; the
disclosed lookback never silently shrinks on a live result; early-session
and missing-history both return unavailable, never a padded ratio
(`test_early_session_is_unavailable_not_a_padded_ratio`,
`test_missing_history_is_unavailable_not_a_padded_ratio`); a session missing
the exact bucket does not count toward history; single-symbol,
single-interval, completed-bars-only, intraday-only input validation (daily
and weekly bars are rejected explicitly, since RVOL's whole premise is a
sub-day clock position).

**Known limitations.** RVOL needs real intraday bar history — at least
`lookback_sessions` full prior sessions at the same intraday interval must
already be accumulated by the market gateway. A symbol newly added to
tracking, or one only ever fetched at daily granularity, reads unavailable
until that history genuinely exists; there is no shortcut or synthetic
backfill. This module quantifies what was previously informal "量价确认"
language, but the 20-session lookback and 2-bucket early-session floor are
engineering defaults, not calibrated thresholds.

### Range-based volatility: Parkinson and Garman-Klass (`volatility.py`, `range-vol-v1`)

Two new estimators sit beside the existing close-to-close
`estimate_annualized_volatility` (`close-to-close-realized-v1`, formula
unchanged). All three return the same `VolatilityEstimate` shape with the
producing `estimator` name (`"close_to_close"` / `"parkinson"` /
`"garman_klass"`) and its matching `method_version` stamped explicitly, so a
consumer never has to guess which formula produced a number —
`VolatilityEstimate.__post_init__` asserts `method_version` matches
`estimator`, so the two cannot disagree on a valid instance.

**Parkinson (1980).** Each completed bar contributes `ln(high/low)^2 /
(4·ln 2)`; the annualized estimate is `sqrt(mean(terms) * periods_per_year)`.
Source: Parkinson, M. (1980), "The Extreme Value Method for Estimating the
Variance of the Rate of Return", *Journal of Business* 53(1), 61–65. Unlike
close-to-close, `sample_size` here counts *bars*, not *returns* — a single
bar already carries a usable high/low range observation.

**Garman-Klass (1980).** Each completed bar contributes `0.5·ln(high/low)^2
− (2·ln 2 − 1)·ln(close/open)^2`; same annualization. Source: Garman, M.B. &
Klass, M.J. (1980), "On the Estimation of Security Price Volatilities from
Historical Data", *Journal of Business* 53(1), 67–78. Because `OHLCVBar`
already guarantees `low <= min(open, close) <= max(open, close) <= high`,
every single-bar term is provably non-negative — a structural guarantee, not
just an empirical observation.

**Estimator metadata.** `estimator` and `method_version` are always stamped
together and validated as a pair (`_ESTIMATOR_VERSIONS` maps `close_to_close`
→ `close-to-close-realized-v1`, and both `parkinson` and `garman_klass` →
`range-vol-v1`).

**Degenerate handling.** A perfectly flat window (every bar's `high == low`,
and for Garman-Klass also `open == close`) drives the aggregate variance to
exactly zero — reported as "no price variation in the observed window" and
returned typed-unavailable, never a manufactured zero, for the same reason
the close-to-close estimator already treats a flat window as unavailable: a
zero-width band would look like a real, if narrow, forecast band rather than
a window the data genuinely cannot speak to.

**Validation rules.** Both new estimators are matched against hand-derived
closed forms on synthetic series
(`test_parkinson_matches_the_hand_derived_closed_form`,
`test_garman_klass_matches_the_hand_derived_closed_form`); a wider intrabar
range increases both range estimators but leaves close-to-close unchanged,
isolating what each formula actually measures
(`test_wider_intrabar_range_increases_range_estimators_but_not_close_to_close`);
all three estimators land in the same order of magnitude on one realistic
series; each has its own minimum-sample gate (default 20 bars) and rejects
incomplete bars and bars not yet knowable at the cutoff; a perfectly flat
window is unavailable for both new estimators, matching the existing
close-to-close behavior.

**Known limitations.** Both range estimators assume no overnight gaps and no
jumps between bars — a real gap-up or gap-down inflates close-to-close but is
invisible to Parkinson, and only partially visible to Garman-Klass through
its open-close term. Neither estimator is drift-aware (Garman-Klass reduces
but does not eliminate drift sensitivity). The `_BARS_PER_DAY`
annualization factors are fixed regular-session assumptions (390 bars/day at
1-minute, 252 trading days/year, and so on) and exclude extended hours,
matching what the market gateway actually serves.

### Plain-language vocabulary (`plain_language.py`, `plain-language-v1`)

Franz is a quant-finance novice; every number this package computes has to
answer, in plain Chinese: 这是什么 / 现在说明什么 / 什么情况下这个判断作废.
`plain_language.py` is the reviewed, versioned vocabulary that answers the
first two questions for every classifiable state above (breadth, sector RS,
RVOL, range volatility) plus the pre-existing Magic Nine counter; the mobile
app carries an independent but copy-identical mirror in
`apps/mobile/src/i18n/plainLanguage.ts` (documented inline as tracking this
module state-for-state). The third question — 失效条件 — is assembled by the
caller alongside the actual served numbers, because it is honest,
already-typed data (sample sizes, thresholds, missing reasons) that belongs
with the result, not with static prose.

**Three-layer contract.**

1. 一句话白话结论 — `PlainReading.headline`. Varies by *state*.
2. 展开解释 — `PlainReading.explanation`. What the indicator measures, with a
   lived-world analogy. Fixed *per indicator*, not per state — every state of
   one indicator shares the same explanation text, because the mechanism does
   not change, only the current reading does.
3. 数字层 — value, sample size, 失效条件. Never stored in this module; it
   comes from the actual result object the caller already has (e.g.
   `RelativeVolumeResult.ratio`, `VolatilityEstimate.sample_size`).

**Banned-verb constraint.** No reading generated by this module may contain
an instruction to act. The banned list is `买入`／`卖出`／`加仓`／`抄底`／
`梭哈`, enforced in `PlainReading.__post_init__` — at *construction* time,
not only in a test — so a banned verb anywhere in a shipped headline or
explanation breaks the import of the whole `us_stock_helper_core` package
rather than shipping quietly. The mobile mirror's `reading()` constructor
enforces the identical list the same way.

**Completeness guarantee.** Every `classify_*` function maps its result to a
state key drawn from a finite, explicitly enumerated domain (ratio buckets,
count buckets, direction, perfected, ...); a value outside that documented
domain raises `ValueError` rather than guessing or falling back to jargon.
Every state a `classify_*` function can produce has a `PlainReading` in the
matching `*_READINGS` dict (or, for Magic Nine's per-count headline, a
template rendered by its own `*_reading` function).
`tests/test_plain_language.py` exercises every state in each domain against
the real `classify_*` function and asserts a reading comes back, so a new
state introduced without matching copy fails that test — and, for the
banned-verb guard, fails at import time regardless of whether a test ever
runs.

The tables below reproduce the shipped headline copy for review; the
`explanation` (展开解释) column links to the fixed per-indicator text quoted
once beneath each table rather than repeated per row.

#### RVOL reading table (8 states)

| State key | Headline (一句话白话结论) |
| --- | --- |
| `rvol-light` | 现在的成交量比平时同一时间明显缩量，交投比较清淡。 |
| `rvol-normal` | 现在的成交量和平时同一时间差不多，属于正常范围。 |
| `rvol-moderate-high` | 现在的成交量比平时同一时间温和放量，交投略微活跃。 |
| `rvol-heavy` | 现在的成交量比平时同一时间明显放量，交投显著活跃。 |
| `rvol-unavailable-no-data` | 成交量对比暂不可用：这个时间点还没有已完成的K线。 |
| `rvol-unavailable-early-session` | 成交量对比暂不可用：开盘时间太短，比较还不可靠。 |
| `rvol-unavailable-insufficient-history` | 成交量对比暂不可用：历史场次不够，凑不出可信的基准。 |
| `rvol-unavailable-zero-baseline` | 成交量对比暂不可用：历史同一时间点的成交量基准为空。 |

Ratio buckets: `< 0.7` → light, `< 1.3` → normal, `< 2.0` → moderate-high,
otherwise heavy (`classify_rvol`, mirroring `_RVOL_LIGHT_MAX` /
`_RVOL_NORMAL_MAX` / `_RVOL_MODERATE_HIGH_MAX`). Every unavailable reason
`time_of_day_relative_volume` can actually emit is matched by prefix; an
unrecognized reason raises rather than falling through to a guess
(`test_an_unrecognized_unavailable_reason_raises_rather_than_falling_back`).
Shared explanation (展开解释): "RVOL 比较的是「现在这个时间点」的累计成交量，
和过去同一时间点的历史平均累计成交量……开盘时间太短、或历史场次不够时不给出
比值，因为凑出来的『正常』看起来像测量结果，其实只是没有数据。"

#### Range-volatility reading table (3 estimators × 6 buckets = 18 states)

Each of `close_to_close` / `parkinson` / `garman_klass` shares the same
bucket headlines and boundaries, but each estimator carries its own
explanation text (its own analogy for what it measures).

| Bucket key | Headline (shared across all three estimators) |
| --- | --- |
| `low` | 最近这段时间的价格波动幅度偏低，走势相对平稳。 |
| `normal` | 最近这段时间的价格波动幅度处于正常区间。 |
| `elevated` | 最近这段时间的价格波动幅度温和偏高，起伏比平时明显一些。 |
| `high` | 最近这段时间的价格波动幅度明显偏高，起伏比平时大很多。 |
| `unavailable-insufficient-sample` | 波动率暂不可用：已收盘的K线数量还不够计算。 |
| `unavailable-flat` | 波动率暂不可用：这段窗口里价格完全没有波动，无法算出有意义的数值。 |

Bucket boundaries on the annualized value: `< 0.15` → low, `< 0.30` →
normal, `< 0.50` → elevated, otherwise high (`classify_volatility`, keys
formatted `volatility-{estimator}-{bucket}`). Per-estimator explanations:
close-to-close ("只看每根K线的收盘价，和上一根收盘价之间的变化幅度"),
Parkinson ("看的是每根K线自己的最高价和最低价之间的距离"), Garman-Klass
("综合了每根K线的最高、最低、开盘和收盘价").

#### Breadth reading table (4 states)

| State key | Headline |
| --- | --- |
| `breadth-strong` | 自选列表里大多数股票都站上了自己的50日均线，参与上涨的股票较多。 |
| `breadth-weak` | 自选列表里大多数股票都跌破了自己的50日均线，参与下跌的股票较多。 |
| `breadth-mixed` | 自选列表里站上和跌破50日均线的股票数量差不多，涨跌互现，没有明显的一致方向。 |
| `breadth-unavailable` | 自选广度暂不可用：历史K线不够计算50日均线。 |

Thresholds: `percent_above >= 55.0` → strong, `<= 45.0` → weak, otherwise
mixed — the same 55%/45% split `market_brief.py`'s own `_breadth_label` uses,
mirrored here on purpose so the vocabulary layer and the wire's own
conclusion text can never disagree.

#### Sector relative strength reading table (3 states)

| State key | Headline |
| --- | --- |
| `sector-rs-leading` | 当前领先的板块跑赢了基准，相对走势偏强。 |
| `sector-rs-lagging` | 当前排名靠前的板块也没有跑赢基准，板块轮动整体偏弱。 |
| `sector-rs-unavailable` | 板块强弱暂不可用：样本不足或历史数据不够计算相对强弱。 |

Classification: `excess_return > 0.0` → leading, otherwise lagging, applied
by the caller to whichever `SectorRelativeStrength` result it is presenting
(`market_brief.py` applies it to the current leader's own record).

#### The Magic Nine reading table (`patterns.py`'s TD Setup, `td-setup-close-4-v2`)

Two independent readings share one fixed explanation of the mechanism (what
TD Setup counts, what reaching 9 suggests, what 完美 adds, what interruption
means), reproduced once below rather than per row.

Shared explanation (展开解释): "神奇九转（TD Setup）数的是：收盘价连续比「4根K
线之前」的收盘价更低（看跌方向）或更高（看涨方向）的次数，序列一旦中断（不再
满足这个比较）就从头开始数——就像数一串连续绿灯，闯一次红灯就得重新数。数到 9
本身不是买卖信号，而是提醒这段单边走势已经持续很久，进入历史上更容易出现停顿
或反转的『警惕区』，仅此而已，不代表现在这一刻一定会反转。「完美」是在数到 9
之后多看一眼第8、9根K线的最高/最低价有没有超过第6、7根——超过了才叫完美，是对
这次计数的一次额外确认；不完美不代表这次计数无效，只是确认强度弱一些。"

**Progress reading (`classify_magic_nine_progress`) — what the chart badge
shows right now.** `setup is None` (no bars at all) and `setup.latest is
None` (the last comparison broke, count reset to zero) are distinguished as
two different states, mirroring the wire's own `qualityStatus` discipline —
"unavailable" and "genuinely nothing in progress" are not the same claim.

| State key | Headline |
| --- | --- |
| `magic-nine-unavailable` | 神奇九转暂不可用：这次没有足够的K线数据来计数。 |
| `magic-nine-no-active-run` | 当前没有正在进行中的九转计数：最近一次的连续比较被打断了，计数已经清零重新开始。 |
| `magic-nine-bullish-early` (count 1–3) | 上涨方向的九转刚数到 {count}——离『警惕反转』的 9 还早，当前只是记录趋势的持续性。 |
| `magic-nine-bearish-early` (count 1–3) | 下跌方向的九转刚数到 {count}——离『警惕反转』的 9 还早，当前只是记录趋势的持续性。 |
| `magic-nine-bullish-mid` (count 4–6) | 上涨方向的九转已经数到 {count}，过了一半但还没到 9，继续观察即可，不是操作提示。 |
| `magic-nine-bearish-mid` (count 4–6) | 下跌方向的九转已经数到 {count}，过了一半但还没到 9，继续观察即可，不是操作提示。 |
| `magic-nine-bullish-late` (count 7–8) | 上涨方向的九转数到 {count}，非常接近 9，进入需要多留意的『警惕反转』临界阶段，但仍然不是操作提示。 |
| `magic-nine-bearish-late` (count 7–8) | 下跌方向的九转数到 {count}，非常接近 9，进入需要多留意的『警惕反转』临界阶段，但仍然不是操作提示。 |
| `magic-nine-bullish-complete-perfected` | 上涨方向的九转刚好数满 9，并且通过了『完美』的额外确认——是这轮单边走势持续最久、最值得留意反转风险的时刻，但依然只是提醒，不是操作提示。 |
| `magic-nine-bearish-complete-perfected` | 下跌方向的九转刚好数满 9，并且通过了『完美』的额外确认——是这轮单边走势持续最久、最值得留意反转风险的时刻，但依然只是提醒，不是操作提示。 |
| `magic-nine-bullish-complete-unperfected` | 上涨方向的九转刚好数满 9，但没有通过『完美』的额外确认——提醒依然成立，只是确认强度弱一些。 |
| `magic-nine-bearish-complete-unperfected` | 下跌方向的九转刚好数满 9，但没有通过『完美』的额外确认——提醒依然成立，只是确认强度弱一些。 |
| `magic-nine-bullish-complete-unknown` | 上涨方向的九转刚好数满 9，但这次没有进行『完美』核对，无法判断是否通过确认。 |
| `magic-nine-bearish-complete-unknown` | 下跌方向的九转刚好数满 9，但这次没有进行『完美』核对，无法判断是否通过确认。 |

**Last-completed reading (`classify_magic_nine_last_completed`) — the most
recently *completed* run, carried separately on the wire as `lastCompleted`**
so it stays visible after counting restarts (mobile ships the four directed
states; the server module additionally distinguishes an "unknown perfection"
variant for a completed run whose perfection was never checked):

| State key | Headline |
| --- | --- |
| `magic-nine-last-completed-none` | 目前还没有出现过完整数到 9 的九转记录。 |
| `magic-nine-last-completed-bullish-perfected` | 最近一次数满 9 的九转方向是上涨，并且通过了『完美』确认——这是历史记录，不代表现在这一刻还成立。 |
| `magic-nine-last-completed-bullish-unperfected` | 最近一次数满 9 的九转方向是上涨，但没有通过『完美』确认——这是历史记录，不代表现在这一刻还成立。 |
| `magic-nine-last-completed-bearish-perfected` | 最近一次数满 9 的九转方向是下跌，并且通过了『完美』确认——这是历史记录，不代表现在这一刻还成立。 |
| `magic-nine-last-completed-bearish-unperfected` | 最近一次数满 9 的九转方向是下跌，但没有通过『完美』确认——这是历史记录，不代表现在这一刻还成立。 |
| `magic-nine-last-completed-bullish-unknown` *(server only)* | 最近一次数满 9 的九转方向是上涨，但当时没有进行『完美』核对——这是历史记录，不代表现在这一刻还成立。 |
| `magic-nine-last-completed-bearish-unknown` *(server only)* | 最近一次数满 9 的九转方向是下跌，但当时没有进行『完美』核对——这是历史记录，不代表现在这一刻还成立。 |

**Validation rules.** Every banned verb is present in the guard list; a
banned verb in either the headline or explanation raises at construction;
no shipped reading (including every Magic Nine progress/last-completed
state) contains a banned verb; every state in each documented domain — RVOL
ratio buckets and every unavailable reason the module actually emits,
volatility estimator × bucket combinations and their unavailable reasons,
breadth strong/weak/mixed/unavailable, sector RS leading/lagging/
unavailable, every Magic Nine direction × count-bucket in progress, every
direction × perfection state at completion, every last-completed direction
× perfection state — has copy, exercised against the real `classify_*`
function; an out-of-range count or an unrecognized unavailable reason raises
rather than silently falling back to a default.

**Known limitations.** The vocabulary is fixed and versioned, not generated
— a genuinely new state (a new RVOL unavailable reason, a new volatility
bucket) requires an explicit code change and passes only once its copy and
completeness test exist; there is no dynamic path that could silently ship
jargon. Presentation-layer bucket thresholds (RVOL's 0.7/1.3/2.0, volatility's
0.15/0.30/0.50, breadth's 55%/45%) are judgment calls over an already-honest
number — they never change what the underlying estimator computed, but they
are not themselves calibrated or backtested cut points.

### The institutional-capital factor blend (`institutional_flow_provider.py`, `institutional-flow-participation-holdings-v1`)

The decision score used to list `institutional_flow`/机构资金 as permanently
unavailable — no free source was timely enough. That stopped being true once
the market gateway started serving, for the symbols it covers, two
ingredients this module blends (or honestly reports absent).

**Ingredients.**

1. *Intraday order-size participation proxy* — from the gateway's
   `currentSessionFlow` section, built via
   `us_stock_helper_core.participation.build_participation_bars`'s
   main-vs-retail lot-size split and net capital flow. Explicitly an
   *estimate*: the gateway itself stamps every row `institutionalIdentity:
   false`, and only the latest bar with `quality_status == "live"` is read
   (`_latest_live_bar`) — a non-live bar does not count as present.
2. *Dated institutional-holdings disclosure trend* — from the gateway's
   `holdings` section, an actual filed disclosure rather than an estimate.
   `gateway_provider.MarketGatewayProvider._holdings` PIT-filters this
   before the row ever reaches this module: a disclosure whose
   `available_at` is after the requested cutoff never enters
   `InstitutionalFlowInputs.holdings` in the first place — nothing here ever
   reads a filing before its own `availableAt`.

**Formula.**

- `proxy_component = clamp(net_flow / (main_activity + retail_activity), -1, 1)`
  — bounded in [-1, 1] by construction (the triangle inequality on four
  signed per-minute bucket deltas already guarantees `|net_flow| <=
  main_activity + retail_activity`; the clamp is a defensive floor, not the
  load-bearing bound).
- `disclosure_component = clamp(holding_percent_change / DISCLOSURE_TREND_SCALE_POINTS, -1, 1)`,
  with `DISCLOSURE_TREND_SCALE_POINTS = 5.0` — a five-percentage-point swing
  in aggregate institutional ownership between consecutive disclosures reads
  as a full-strength signal; larger moves clamp rather than overshoot.
- **Both present:** `value = clamp((proxy_component * PROXY_CONFIDENCE +
  disclosure_component * DISCLOSURE_CONFIDENCE) / (PROXY_CONFIDENCE +
  DISCLOSURE_CONFIDENCE))`, with `PROXY_CONFIDENCE = 0.5` and
  `DISCLOSURE_CONFIDENCE = 1.0` — the intraday proxy never claims more
  conviction than half of what a real disclosure would for the same raw
  reading, because it is order-size activity, not a verified institutional
  trade.
- **Only one present:** that component alone, scaled by its own confidence
  (the proxy still capped at 0.5×; the disclosure at full 1.0×).
- **Neither present:** `FactorUnavailable.NO_DATA_AT_CUTOFF` — never a
  neutral-looking 0.0, the same rule every other soft factor in
  `information_layer.factors` follows.
- **Gateway failure** (`MarketGatewayUnavailable`):
  `FactorUnavailable.SOURCE_UNREACHABLE`.

**PIT boundary.** The disclosure ingredient's PIT gate lives one layer below
this module, in `MarketGatewayProvider._holdings` (`available_at > as_of` ⇒
excluded, and `reported_at > available_at` is itself rejected as malformed).
The proxy ingredient's own bars are already PIT-scoped upstream by
`build_participation_bars`. `InstitutionalFlowReading.__post_init__` enforces
"exactly one of `value`/`unavailable_reason`, never both" at construction —
deliberately mirroring `information_layer.factors.base.FactorReading`'s own
invariant without inheriting from it, because institutional flow is not a
citable public HTTPS source the way macro/fundamentals factors are.

**Validation rules.** Both ingredients present blend at their stated
confidence (`test_both_ingredients_present_blend_at_their_stated_confidence`);
the proxy is discounted below its own raw reading
(`test_the_proxy_is_discounted_below_its_own_raw_reading`); neither
ingredient present is honestly unavailable, never zero-filled; a
participation bar that is not live does not count as present; only the
latest live bar is read even when older ones exist; a reading can never
carry both a value and a reason, nor neither; a gateway failure degrades
into `SOURCE_UNREACHABLE`, not a silent zero.

**Known limitations.** The intraday ingredient is a lot-size proxy, not
verified institutional identity — the gateway itself disclaims
`institutionalIdentity: false`, and this module never upgrades that
disclaimer regardless of how confidently the raw ratio reads. Factor
coverage rises only for symbols the gateway actually serves both sections
for; most symbols will see one ingredient, the other, or neither, and the
factor stays proportionally weaker (or entirely absent) rather than
backfilled to look complete.

## Evidence sources (information layer registry, 2026-08-17)

Every source below is a channel its publisher operates for syndication; each
was fetched with the project's own User-Agent and its robots policy read
before registration (captured payloads live in
`services/information_layer/tests/fixtures/`). Reliability, cadence and
attribution rules are declared per source in
`information_layer/feeds/registry.py::PUBLIC_SOURCES`.

### SEC EDGAR current filings (6 feeds, poll 300s, reliability 0.99, VERIFIED)

`8-K`, `4`, `10-Q`, `10-K`, `SCHEDULE 13D`, `SCHEDULE 13G` — the last two are
the codes EDGAR actually serves since its 2024 revision; the retired
`SC 13D`/`SC 13G` queries answer "No recent filings" (the captured empty
feeds are kept as fixtures). Attribution is by filer identity through the
CIK→ticker registry, never by prose. **Limitations:** each Schedule 13D/13G
produces a *pair* of entries under one accession — the holder's `(Filed by)`
entry claims no symbol (a listed holder would otherwise swallow the subject
issuer's event, the DaVita/Berkshire failure shape), the issuer's
`(Subject)` entry carries the attribution. Filing titles are metadata and
carry no sentiment; the Atom feed has no document text, so filing sentiment
stays structurally unmeasured. Each party's entry now keys off
`sec|{accession}|{party CIK}` rather than the bare accession, so the two
sides of a pair (and the same split for Form 4) no longer chain onto each
other as fake mutual "revisions" every poll — same-party updates still
revision normally. The pair is still recognized as one story: clustering
groups events sharing an accession into a single cluster, and the attributed
`(Subject)` entry is preferred as that cluster's representative over its
unattributed `(Filed by)` sibling. Fixed 2026-08-17 (`ead0bd7`); a production
deployment's first poll after upgrading re-announces each filing still inside
the lookback window once, bounded, as a fresh claim (not chained to the old
key) — see the ledger for the snapshot-compatibility test that pins this.

### Company newsrooms (7 feeds, poll 900s, reliability 0.95, VERIFIED)

AAPL, NVDA, MSFT, INTC, BA, AMZN, GOOGL — declared row-by-row through
`company_ir_source()`. Attribution is earned from the text (a release that
never names the company gets no symbol), symbol keywords carry 0.9.
**Limitations:** issuer-authored and therefore promotional — reliability
describes authenticity (the company really said it), not balance. Tickers
whose only obvious keyword doubles as a common English word (GRAB, SOUN,
COIN, RIOT…) are deliberately absent until they have a distinctive
multi-word key; the mis-attribution trap is pinned by test.

### Nasdaq trade halts (poll 60s — the publisher's own feed declares ttl=1min; reliability 0.99, VERIFIED)

A dedicated adapter (`feeds/nasdaq.py`) reads the `ndaq:*` fields because
halt items carry neither `<guid>` nor `<link>`. The exchange names the
halted issue itself, so attribution is 1.0 — exact like a CIK match, not a
keyword guess. A resumption fills the same item's resumption fields and is
published as a *revision* of the original halt. Halt notices are metadata
and carry no sentiment. The feed's own `pubDate` is date-granular — stamped
at midnight ET for every item regardless of when the halt actually
happened — so it is never trusted for the entry's timestamp: `published_at`
(and `event_time`) are synthesized from `ndaq:HaltDate`/`ndaq:HaltTime`
(ET, converted to UTC), and `updated_at` additionally tracks a later
`ndaq:ResumptionDate`/`ResumptionTradeTime` (falling back to
`ResumptionQuoteTime`) once a resumption is filled in. Trusting `pubDate`
previously backdated every halt by up to ~20 hours and dropped every
same-day halt from the collector's 6-hour production lookback for any poll
after roughly 06:00 ET — i.e. during the whole regular session. An item
whose `HaltDate`/`HaltTime` cannot be parsed is dropped rather than
timestamped from `pubDate`. **Limitations:** Nasdaq-listed issues only
(NYSE publishes no feed, only a CSV download).

### Agency press feeds: FDA / FTC / DOJ (poll 900s, reliability 0.99, VERIFIED)

Regulator statements about third parties, so company attribution is a 0.85
keyword guess (below the 0.9 of an issuer's own channel and the 1.0 of
registry/exchange identity). FDA additionally maps watchlist drug
developers (CRISPR Therapeutics, Structure Therapeutics, Merck). Agency
prose is scored for sentiment, unlike filing metadata. **Limitations:** an
event that names no mapped company reaches no symbol-scoped read; the DOJ
feed really publishes future-dated planning items ("FY26 Q4 Data Due"),
which the PIT guard rejects and counts in `future_entries_rejected`.

### Deliberately absent

- **News wires** (Reuters/Bloomberg class): require a commercial licence;
  the `NEWS_WIRE` slot stays empty by policy, not oversight.
- **OFAC / Treasury sanctions**: no RSS/Atom endpoint exists since the site
  redesign (the 404s are recorded in the 2026-08-17 ledger), so the
  geopolitics driver keeps its named "尚未接入" state.
- **Merck, Cisco, Qualcomm, PayPal, Sony, AMD, Coca-Cola newsrooms**:
  investigated and rejected — empty feed, no public feed, or access denied.

## Required gates before a signal reaches the live alert channel

1. **No future data:** appending future candles must not alter historical output.
2. **Timestamp correctness:** decisions use the information availability time,
   not a later corrected or publication date.
3. **Corporate actions:** price history must be consistently adjusted.
4. **Realistic execution:** include spread, commissions, slippage, halts and
   market-session restrictions.
5. **Out-of-sample testing:** tune on one period and evaluate on unseen periods.
6. **Regime breakdown:** report results in bullish, bearish, range-bound and
   high-volatility markets.
7. **Survivorship control:** retain delisted and failed companies in the test
   universe.
8. **Traceability:** every displayed signal records indicator key, parameters,
   version, candle timestamp and source-data identifier.

## Performance report

No indicator should be called profitable from win rate alone. The report must
include:

- Net return after trading costs
- Maximum drawdown
- Profit factor and expectancy per trade
- Win rate and average win/loss ratio
- Exposure, turnover and trade count
- Performance by ticker, sector, market regime and holding horizon
- Difference between backtest, paper trading and live fills

The product goal is positive, repeatable net expectancy with controlled
drawdown. A familiar or premium-sounding indicator name is not evidence of
profitability.

