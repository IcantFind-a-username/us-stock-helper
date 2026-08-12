"""Technical indicators calculated from closed point-in-time bars."""

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from .models import OHLCVBar


@dataclass(frozen=True, slots=True)
class MACDValue:
    line: float
    signal: float
    histogram: float


def moving_average(values: Sequence[float], period: int) -> float | None:
    checked = _validated(values, period)
    if len(checked) < period:
        return None
    return sum(checked[-period:]) / period


def ema_series(values: Sequence[float], period: int) -> tuple[float, ...]:
    checked = _validated(values, period)
    if not checked:
        return ()
    multiplier = 2.0 / (period + 1.0)
    result = [checked[0]]
    for value in checked[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return tuple(result)


def warmup_ema_series(
    values: Sequence[float], period: int
) -> tuple[float | None, ...]:
    """EMA that publishes nothing until one full window has closed.

    ``ema_series`` seeds from the first value, so its early output reflects a
    single bar rather than the requested period.  Anything drawn for a user or
    fed into a trend state must use this variant instead: it stays ``None``
    through the warm-up and, once published, a value never changes when later
    bars arrive.
    """

    checked = _validated(values, period)
    result: list[float | None] = [None] * len(checked)
    if len(checked) < period:
        return tuple(result)
    multiplier = 2.0 / (period + 1.0)
    current = sum(checked[:period]) / period
    result[period - 1] = current
    for index in range(period, len(checked)):
        current = (checked[index] - current) * multiplier + current
        result[index] = current
    return tuple(result)


def wilder_atr(
    bars: "Sequence[OHLCVBar]", period: int = 14
) -> tuple[float | None, ...]:
    """Wilder's average true range, published only after a complete window."""

    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return tuple(result)
    true_ranges: list[float] = []
    for index, current in enumerate(bars):
        if index == 0:
            true_ranges.append(current.high - current.low)
            continue
        previous_close = bars[index - 1].close
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )
    average = sum(true_ranges[:period]) / period
    result[period - 1] = average
    for index in range(period, len(bars)):
        average = (average * (period - 1) + true_ranges[index]) / period
        result[index] = average
    return tuple(result)


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    checked = _validated(values, period)
    if len(checked) < period + 1:
        return None
    deltas = [
        checked[index] - checked[index - 1] for index in range(1, len(checked))
    ]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for index in range(period, len(deltas)):
        average_gain = (
            average_gain * (period - 1) + gains[index]
        ) / period
        average_loss = (
            average_loss * (period - 1) + losses[index]
        ) / period
    if average_gain == 0.0 and average_loss == 0.0:
        return 50.0
    if average_loss == 0.0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def macd(
    values: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDValue | None:
    checked = _validated(values, 1)
    if min(fast_period, slow_period, signal_period) <= 0:
        raise ValueError("period values must be positive")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    if len(checked) < slow_period:
        return None
    fast = ema_series(checked, fast_period)
    slow = ema_series(checked, slow_period)
    lines = tuple(fast_value - slow_value for fast_value, slow_value in zip(fast, slow))
    signals = ema_series(lines, signal_period)
    return MACDValue(
        line=lines[-1],
        signal=signals[-1],
        histogram=lines[-1] - signals[-1],
    )


def _validated(values: Sequence[float], period: int) -> tuple[float, ...]:
    if period <= 0:
        raise ValueError("period must be positive")
    checked = tuple(float(value) for value in values)
    if any(not isfinite(value) for value in checked):
        raise ValueError("indicator values must be finite")
    return checked
