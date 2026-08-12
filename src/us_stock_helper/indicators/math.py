"""No-lookahead rolling calculations used by indicator plugins."""

from typing import List, Optional, Sequence


def ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not values:
        return []

    alpha = 2.0 / (period + 1.0)
    result: List[Optional[float]] = [float(values[0])]
    for value in values[1:]:
        previous = result[-1]
        assert previous is not None
        result.append(alpha * float(value) + (1.0 - alpha) * previous)
    return result


def sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result: List[Optional[float]] = [None] * len(values)
    rolling_sum = 0.0
    for index, value in enumerate(values):
        rolling_sum += float(value)
        if index >= period:
            rolling_sum -= float(values[index - period])
        if index >= period - 1:
            result[index] = rolling_sum / period
    return result


def wilder_atr(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    period: int,
) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")
    if not (len(high) == len(low) == len(close)):
        raise ValueError("high, low and close must have identical lengths")
    if not close:
        return []

    true_ranges: List[float] = []
    for index in range(len(close)):
        if index == 0:
            true_range = float(high[index]) - float(low[index])
        else:
            true_range = max(
                float(high[index]) - float(low[index]),
                abs(float(high[index]) - float(close[index - 1])),
                abs(float(low[index]) - float(close[index - 1])),
            )
        true_ranges.append(true_range)

    result: List[Optional[float]] = [None] * len(close)
    if len(close) < period:
        return result

    first_atr = sum(true_ranges[:period]) / period
    result[period - 1] = first_atr
    previous_atr = first_atr
    for index in range(period, len(close)):
        previous_atr = (
            previous_atr * (period - 1) + true_ranges[index]
        ) / period
        result[index] = previous_atr
    return result

