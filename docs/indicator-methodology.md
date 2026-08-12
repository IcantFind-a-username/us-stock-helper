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
carries the transparent trend system under `dragon-trend-ema-atr-volume-v1`.
An earlier standalone prototype of both lives in the repository history on
`main` (commit `4170859`) and is not maintained.

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
- Relative volume against SMA 20 for transition confidence.
- Signals only on a state transition and only use current or earlier candles.

Its parameters will be optimized only through walk-forward validation. It is
not represented as the formula of any specific paid vendor product.

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

