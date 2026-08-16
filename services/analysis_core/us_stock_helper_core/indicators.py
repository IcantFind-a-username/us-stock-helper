"""Technical indicators calculated from closed point-in-time bars."""

from dataclasses import dataclass
from math import fsum, isfinite
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from .models import OHLCVBar


@dataclass(frozen=True, slots=True)
class MACDValue:
    line: float
    signal: float
    histogram: float


@dataclass(frozen=True, slots=True)
class MACDSeries:
    """The three drawable MACD lines, each index-aligned with its input.

    Positions inside the warm-up are ``None`` rather than 0.0: an undefined
    indicator and one that happens to equal zero are different facts, and a
    zero-filled warm-up draws a line the market never had.
    """

    line: tuple[float | None, ...]
    signal: tuple[float | None, ...]
    histogram: tuple[float | None, ...]


def moving_average_series(
    values: Sequence[float], period: int
) -> tuple[float | None, ...]:
    """SMA at every index, ``None`` until one full window has closed."""

    # fsum, not the built-in sum: plain left-to-right float accumulation
    # rounds differently depending on which values land in the window, so
    # the same closes can print as 101.9 in one window and
    # 101.89999999999999 in the next -- noise, not a real distinct price.
    # fsum is the correctly-rounded sum regardless of term order, so a
    # window's value depends only on its contents.
    checked = _validated(values, period)
    result: list[float | None] = [None] * len(checked)
    for index in range(period - 1, len(checked)):
        result[index] = fsum(checked[index - period + 1 : index + 1]) / period
    return tuple(result)


def moving_average(values: Sequence[float], period: int) -> float | None:
    # Delegates so the value a chart draws at the last bar and the value the
    # scoring path reads can never come from two different implementations.
    series = moving_average_series(values, period)
    return series[-1] if series else None


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


def rsi_series(
    values: Sequence[float], period: int = 14
) -> tuple[float | None, ...]:
    """Wilder's RSI at every index, ``None`` through the warm-up.

    ``period`` deltas need ``period + 1`` closes, so the first defined
    position is ``period`` — one later than a moving average of the same
    length, and the chart must not close that gap by guessing.
    """

    checked = _validated(values, period)
    result: list[float | None] = [None] * len(checked)
    if len(checked) < period + 1:
        return tuple(result)
    deltas = [
        checked[index] - checked[index - 1] for index in range(1, len(checked))
    ]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    result[period] = _relative_strength_index(average_gain, average_loss)
    for index in range(period, len(deltas)):
        average_gain = (
            average_gain * (period - 1) + gains[index]
        ) / period
        average_loss = (
            average_loss * (period - 1) + losses[index]
        ) / period
        # deltas[index] closes the bar at checked[index + 1].
        result[index + 1] = _relative_strength_index(average_gain, average_loss)
    return tuple(result)


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    series = rsi_series(values, period)
    return series[-1] if series else None


def _relative_strength_index(
    average_gain: float, average_loss: float
) -> float:
    if average_gain == 0.0 and average_loss == 0.0:
        return 50.0
    if average_loss == 0.0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def macd_series(
    values: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDSeries:
    """DIF, DEA and the histogram at every index, index-aligned with input.

    Both EMAs seed from the first close, so their early output describes one
    bar rather than the requested window. Nothing is published before the slow
    window has closed — the same threshold that makes the single value ``None``
    — so a value never appears on the chart before it means anything.
    """

    checked = _validated(values, 1)
    if min(fast_period, slow_period, signal_period) <= 0:
        raise ValueError("period values must be positive")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    blank = (None,) * len(checked)
    if len(checked) < slow_period:
        return MACDSeries(line=blank, signal=blank, histogram=blank)
    fast = ema_series(checked, fast_period)
    slow = ema_series(checked, slow_period)
    lines = tuple(fast_value - slow_value for fast_value, slow_value in zip(fast, slow))
    signals = ema_series(lines, signal_period)
    warmup = slow_period - 1
    return MACDSeries(
        line=tuple(
            value if index >= warmup else None for index, value in enumerate(lines)
        ),
        signal=tuple(
            value if index >= warmup else None for index, value in enumerate(signals)
        ),
        histogram=tuple(
            line_value - signal_value if index >= warmup else None
            for index, (line_value, signal_value) in enumerate(zip(lines, signals))
        ),
    )


def macd(
    values: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDValue | None:
    series = macd_series(values, fast_period, slow_period, signal_period)
    if not series.line:
        return None
    line, signal, histogram = series.line[-1], series.signal[-1], series.histogram[-1]
    if line is None or signal is None or histogram is None:
        return None
    return MACDValue(line=line, signal=signal, histogram=histogram)


def _validated(values: Sequence[float], period: int) -> tuple[float, ...]:
    if period <= 0:
        raise ValueError("period must be positive")
    checked = tuple(float(value) for value in values)
    if any(not isfinite(value) for value in checked):
        raise ValueError("indicator values must be finite")
    return checked
