"""Sector relative strength and cross-sector correlation regime.

Two independent readings live here, both computed from daily bar series and
both honest about warm-up:

``relative_strength_ranking`` measures how far each sector's latest close
sits above (or below) its own trailing EMA, relative to how far the
benchmark sits above its own EMA. The EMA anchor is reused from
``warmup_ema_series`` — the exact function MACD and Dragon Trend already use
— so the warm-up rule is the same one proven elsewhere in this package: no
value is published until a full window has closed, and a published value
never changes when later bars arrive.

``correlation_regime`` measures how tightly a group of sectors is moving
together over a disclosed trailing window of daily returns, classifying the
result as a coarse risk-on/neutral/risk-off regime. A flat series has no
defined correlation with anything (division by zero variance), so it is
excluded from the pairwise set rather than silently contributing a zero.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from typing import Mapping, Sequence

from .indicators import warmup_ema_series
from .models import OHLCVBar, require_utc
from .temporal import select_bars_as_of


SECTOR_RS_VERSION = "sector-rs-v1"

DEFAULT_LOOKBACKS = (21, 63, 126)  # ~1M / 3M / 6M trading days
DEFAULT_RS_MINIMUM_UNIVERSE = 2

DEFAULT_CORRELATION_WINDOW = 20
DEFAULT_CORRELATION_MINIMUM_UNIVERSE = 3
DEFAULT_RISK_ON_THRESHOLD = 0.3
DEFAULT_RISK_OFF_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class SectorRelativeStrength:
    """One sector's EMA-anchored return versus the benchmark, for one lookback.

    ``sector_return`` and ``benchmark_return`` are each
    ``latest_close / EMA(lookback) - 1`` for their own series.
    ``excess_return`` is the sector's return minus the benchmark's. A rank of
    1 is the strongest excess return among the symbols eligible in this
    lookback's cross-section.
    """

    symbol: str
    lookback: int
    sector_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    rank: int | None
    quality_status: str
    missing_reason: str | None
    method_version: str = SECTOR_RS_VERSION

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "unavailable":
            values = (
                self.sector_return,
                self.benchmark_return,
                self.excess_return,
                self.rank,
            )
            if any(value is not None for value in values):
                raise ValueError("an unavailable result carries no values or rank")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
        else:
            floats = (self.sector_return, self.benchmark_return, self.excess_return)
            if any(value is None or not isfinite(value) for value in floats):
                raise ValueError("a live result requires finite returns")
            assert self.sector_return is not None and self.benchmark_return is not None
            assert self.excess_return is not None
            if self.excess_return != self.sector_return - self.benchmark_return:
                raise ValueError(
                    "excess_return must equal sector_return minus benchmark_return"
                )
            if self.rank is not None and self.rank < 1:
                raise ValueError("rank must be at least one when present")
            if self.missing_reason is not None:
                raise ValueError("a live result cannot carry a missing reason")


@dataclass(frozen=True, slots=True)
class RelativeStrengthRanking:
    """One cross-section of sector relative strength per requested lookback."""

    as_of: datetime
    benchmark_symbol: str
    universe_size: int
    minimum_universe: int
    lookbacks: tuple[int, ...]
    results: tuple[SectorRelativeStrength, ...]
    method_version: str = SECTOR_RS_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if not self.benchmark_symbol.strip():
            raise ValueError("benchmark_symbol is required")
        if self.universe_size < 0:
            raise ValueError("universe_size must be non-negative")
        if self.minimum_universe < 1:
            raise ValueError("minimum_universe must be at least one")
        if not self.lookbacks:
            raise ValueError("lookbacks must not be empty")


@dataclass(frozen=True, slots=True)
class CorrelationRegimeResult:
    """Average pairwise return correlation across a sector universe.

    ``regime`` is ``"risk_off"`` when the average is at or above
    ``risk_off_threshold`` (the group is moving together — a macro-driven
    tape), ``"risk_on"`` when it is at or below ``risk_on_threshold`` (moves
    are differentiated / idiosyncratic), and ``"neutral"`` between the two.
    Both thresholds and the ``window`` are carried on the result so a
    consumer never has to guess what produced the label.
    """

    as_of: datetime
    window: int
    universe_size: int
    minimum_universe: int
    eligible_symbols: tuple[str, ...]
    average_pairwise_correlation: float | None
    regime: str | None
    risk_on_threshold: float
    risk_off_threshold: float
    quality_status: str
    missing_reason: str | None
    method_version: str = SECTOR_RS_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if self.window <= 1:
            raise ValueError("window must be at least two")
        if self.universe_size < 0:
            raise ValueError("universe_size must be non-negative")
        if self.minimum_universe < 2:
            raise ValueError("minimum_universe must be at least two")
        if not 0.0 <= self.risk_on_threshold < self.risk_off_threshold <= 1.0:
            raise ValueError(
                "thresholds must satisfy 0 <= risk_on_threshold < risk_off_threshold <= 1"
            )
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "unavailable":
            if self.average_pairwise_correlation is not None or self.regime is not None:
                raise ValueError("an unavailable result carries no correlation or regime")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
        else:
            if (
                self.average_pairwise_correlation is None
                or not isfinite(self.average_pairwise_correlation)
            ):
                raise ValueError("a live result requires a finite average correlation")
            if not -1.0 <= self.average_pairwise_correlation <= 1.0:
                raise ValueError("average correlation must be between -1 and 1")
            if self.regime not in {"risk_on", "neutral", "risk_off"}:
                raise ValueError("a live result requires a recognized regime")
            if self.missing_reason is not None:
                raise ValueError("a live result cannot carry a missing reason")


def relative_strength_ranking(
    sectors: Mapping[str, Sequence[OHLCVBar]],
    benchmark: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    lookbacks: Sequence[int] = DEFAULT_LOOKBACKS,
    minimum_universe: int = DEFAULT_RS_MINIMUM_UNIVERSE,
) -> RelativeStrengthRanking:
    """Rank each sector's EMA-anchored excess return over ``benchmark``.

    For each lookback, a sector only receives a rank once both it and the
    benchmark have warmed up (``warmup_ema_series`` has published a value)
    and the number of warmed-up sectors meets ``minimum_universe`` — a
    cross-section too small to call a "ranking" returns every symbol as
    typed unavailable for that lookback rather than a partial or misleading
    order.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if not lookbacks:
        raise ValueError("lookbacks must contain at least one period")
    if any(period <= 0 for period in lookbacks):
        raise ValueError("lookback periods must be positive")
    if minimum_universe < 1:
        raise ValueError("minimum_universe must be at least one")
    _validate_series_map(sectors)
    if not benchmark:
        raise ValueError("benchmark must have at least one bar")
    _validate_single_series(benchmark)

    benchmark_symbol = benchmark[0].symbol.upper()
    benchmark_pit_closes = [
        row.close for row in select_bars_as_of(benchmark, decision_cutoff)
    ]
    sector_pit_closes = {
        symbol: [row.close for row in select_bars_as_of(bars, decision_cutoff)]
        for symbol, bars in sectors.items()
    }
    universe_size = len(sectors)

    results: list[SectorRelativeStrength] = []
    for lookback in lookbacks:
        benchmark_return = _ema_anchored_return(benchmark_pit_closes, lookback)
        sector_returns = {
            symbol: _ema_anchored_return(closes, lookback)
            for symbol, closes in sector_pit_closes.items()
        }
        eligible = {
            symbol: value
            for symbol, value in sector_returns.items()
            if value is not None and benchmark_return is not None
        }
        rankable = (
            universe_size >= minimum_universe and len(eligible) >= minimum_universe
        )
        ranks: dict[str, int] = {}
        if rankable:
            ordered = sorted(
                eligible.items(),
                key=lambda item: item[1] - benchmark_return,  # type: ignore[operator]
                reverse=True,
            )
            ranks = {symbol: index + 1 for index, (symbol, _) in enumerate(ordered)}

        for symbol in sectors:
            sector_return = sector_returns[symbol]
            if benchmark_return is None or sector_return is None:
                results.append(
                    SectorRelativeStrength(
                        symbol=symbol,
                        lookback=lookback,
                        sector_return=None,
                        benchmark_return=None,
                        excess_return=None,
                        rank=None,
                        quality_status="unavailable",
                        missing_reason=(
                            f"insufficient warm-up history for the {lookback}-bar "
                            "EMA anchor"
                        ),
                    )
                )
                continue
            if not rankable:
                results.append(
                    SectorRelativeStrength(
                        symbol=symbol,
                        lookback=lookback,
                        sector_return=None,
                        benchmark_return=None,
                        excess_return=None,
                        rank=None,
                        quality_status="unavailable",
                        missing_reason=(
                            f"insufficient sector universe for ranking: "
                            f"{len(eligible)} of {minimum_universe} eligible "
                            f"(universe {universe_size})"
                        ),
                    )
                )
                continue
            results.append(
                SectorRelativeStrength(
                    symbol=symbol,
                    lookback=lookback,
                    sector_return=sector_return,
                    benchmark_return=benchmark_return,
                    excess_return=sector_return - benchmark_return,
                    rank=ranks[symbol],
                    quality_status="live",
                    missing_reason=None,
                )
            )

    return RelativeStrengthRanking(
        as_of=decision_cutoff,
        benchmark_symbol=benchmark_symbol,
        universe_size=universe_size,
        minimum_universe=minimum_universe,
        lookbacks=tuple(lookbacks),
        results=tuple(results),
    )


def correlation_regime(
    sectors: Mapping[str, Sequence[OHLCVBar]],
    decision_cutoff: datetime,
    *,
    window: int = DEFAULT_CORRELATION_WINDOW,
    minimum_universe: int = DEFAULT_CORRELATION_MINIMUM_UNIVERSE,
    risk_on_threshold: float = DEFAULT_RISK_ON_THRESHOLD,
    risk_off_threshold: float = DEFAULT_RISK_OFF_THRESHOLD,
) -> CorrelationRegimeResult:
    """Average pairwise Pearson correlation of daily returns over ``window`` days.

    A sector is eligible once it has ``window + 1`` completed bars knowable
    at the cutoff (enough to form ``window`` daily returns) *and* its return
    series is not perfectly flat — a flat window has zero variance, which
    makes correlation with anything mathematically undefined, not zero.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if window <= 1:
        raise ValueError("window must be at least two")
    if minimum_universe < 2:
        raise ValueError("minimum_universe must be at least two")
    if not 0.0 <= risk_on_threshold < risk_off_threshold <= 1.0:
        raise ValueError(
            "thresholds must satisfy 0 <= risk_on_threshold < risk_off_threshold <= 1"
        )
    _validate_series_map(sectors)

    universe_size = len(sectors)
    returns_by_symbol: dict[str, tuple[float, ...]] = {}
    for symbol, bars in sectors.items():
        pit_bars = select_bars_as_of(bars, decision_cutoff)
        if len(pit_bars) < window + 1:
            continue
        window_closes = [row.close for row in pit_bars[-(window + 1):]]
        returns = tuple(
            window_closes[index] / window_closes[index - 1] - 1.0
            for index in range(1, len(window_closes))
        )
        if len(set(returns)) <= 1:
            # A perfectly flat window: every pairwise correlation touching it
            # is undefined (zero variance), not a measured zero.
            continue
        returns_by_symbol[symbol] = returns

    eligible = tuple(sorted(returns_by_symbol))

    def _unavailable(reason: str) -> CorrelationRegimeResult:
        return CorrelationRegimeResult(
            as_of=decision_cutoff,
            window=window,
            universe_size=universe_size,
            minimum_universe=minimum_universe,
            eligible_symbols=eligible,
            average_pairwise_correlation=None,
            regime=None,
            risk_on_threshold=risk_on_threshold,
            risk_off_threshold=risk_off_threshold,
            quality_status="unavailable",
            missing_reason=reason,
        )

    if universe_size < minimum_universe or len(eligible) < minimum_universe:
        return _unavailable(
            f"insufficient eligible sectors: {len(eligible)} of {minimum_universe} "
            f"(universe {universe_size})"
        )

    pair_correlations: list[float] = []
    for i in range(len(eligible)):
        for j in range(i + 1, len(eligible)):
            correlation = _pearson_correlation(
                returns_by_symbol[eligible[i]], returns_by_symbol[eligible[j]]
            )
            if correlation is not None:
                pair_correlations.append(correlation)

    if not pair_correlations:
        return _unavailable("no computable pairwise correlations")

    average = sum(pair_correlations) / len(pair_correlations)
    if average >= risk_off_threshold:
        regime = "risk_off"
    elif average <= risk_on_threshold:
        regime = "risk_on"
    else:
        regime = "neutral"

    return CorrelationRegimeResult(
        as_of=decision_cutoff,
        window=window,
        universe_size=universe_size,
        minimum_universe=minimum_universe,
        eligible_symbols=eligible,
        average_pairwise_correlation=average,
        regime=regime,
        risk_on_threshold=risk_on_threshold,
        risk_off_threshold=risk_off_threshold,
        quality_status="live",
        missing_reason=None,
    )


def _ema_anchored_return(closes: Sequence[float], period: int) -> float | None:
    """``latest_close / EMA(period) - 1``, ``None`` through EMA warm-up."""

    if len(closes) < period:
        return None
    ema_value = warmup_ema_series(closes, period)[-1]
    if ema_value is None or ema_value == 0.0:
        return None
    return closes[-1] / ema_value - 1.0


def _pearson_correlation(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) == 0 or len(x) != len(y):
        return None
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    variance_x = sum((a - mean_x) ** 2 for a in x)
    variance_y = sum((b - mean_y) ** 2 for b in y)
    if variance_x <= 0.0 or variance_y <= 0.0:
        return None
    denominator = sqrt(variance_x * variance_y)
    if denominator <= 0.0 or not isfinite(denominator):
        return None
    correlation = covariance / denominator
    return max(-1.0, min(1.0, correlation))


def _validate_series_map(sectors: Mapping[str, Sequence[OHLCVBar]]) -> None:
    for symbol, bars in sectors.items():
        if not symbol.strip():
            raise ValueError("universe symbols must be non-empty")
        _validate_single_series(bars, expected_symbol=symbol)


def _validate_single_series(
    bars: Sequence[OHLCVBar], *, expected_symbol: str | None = None
) -> None:
    reference = expected_symbol.upper() if expected_symbol is not None else None
    for row in bars:
        if reference is None:
            reference = row.symbol.upper()
        elif row.symbol.upper() != reference:
            raise ValueError("all bars in a series must share one symbol")
        if row.interval != "day":
            raise ValueError("relative strength requires daily bars")
        if not row.complete:
            raise ValueError("relative strength requires completed candles")
