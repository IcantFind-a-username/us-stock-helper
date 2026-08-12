"""An independent, transparent trend-state system.

This performs the same job as the paid "神龙" style trend indicators — tell the
reader which regime the market is in and where the risk boundary sits — without
claiming to reproduce any vendor's formula. Every rule here is stated in the
open: exponential-average alignment for the regime, a Wilder ATR channel for
the risk boundary, and relative volume as a confirmation flag. Values stay
unavailable through warm-up rather than being filled with an early guess, and a
value that has been published never changes when later bars arrive.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Sequence

from .indicators import warmup_ema_series, wilder_atr
from .models import Direction, OHLCVBar


DRAGON_TREND_VERSION = "dragon-trend-ema-atr-volume-v1"


class TrendState(str, Enum):
    WARMING_UP = "warming_up"
    UNAVAILABLE = "unavailable"
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class TrendTransition:
    direction: Direction
    confirmed_at_index: int
    strength: float
    relative_volume: float | None
    volume_confirmed: bool
    algorithm_version: str = DRAGON_TREND_VERSION


@dataclass(frozen=True, slots=True)
class DragonTrendResult:
    states: tuple[TrendState, ...]
    strength: tuple[float | None, ...]
    fast_line: tuple[float | None, ...]
    medium_line: tuple[float | None, ...]
    slow_line: tuple[float | None, ...]
    upper_channel: tuple[float | None, ...]
    lower_channel: tuple[float | None, ...]
    signals: tuple[TrendTransition, ...]
    algorithm_version: str = DRAGON_TREND_VERSION


def dragon_trend(
    bars: Sequence[OHLCVBar],
    *,
    fast_period: int = 8,
    medium_period: int = 21,
    slow_period: int = 55,
    atr_period: int = 14,
    volume_period: int = 20,
    atr_multiplier: float = 1.5,
    volume_confirmation_ratio: float = 1.2,
) -> DragonTrendResult:
    """Classify each completed bar into a trend regime with a risk channel."""

    periods = (fast_period, medium_period, slow_period, atr_period, volume_period)
    if any(period <= 0 for period in periods):
        raise ValueError("all periods must be positive")
    if not fast_period < medium_period < slow_period:
        raise ValueError("periods must satisfy fast < medium < slow")
    if atr_multiplier <= 0 or volume_confirmation_ratio <= 0:
        raise ValueError("multiplier and confirmation ratio must be positive")

    rows = tuple(bars)
    if any(not row.complete for row in rows):
        raise ValueError("trend state requires completed candles")
    if len({row.symbol for row in rows}) > 1:
        raise ValueError("trend state requires a single symbol")
    if len({row.interval for row in rows}) > 1:
        raise ValueError("trend state requires a single interval")
    for index in range(1, len(rows)):
        if rows[index].closed_at <= rows[index - 1].closed_at:
            raise ValueError("bars must be strictly increasing in time")

    closes = [row.close for row in rows]
    volumes = [row.volume for row in rows]
    fast_line = warmup_ema_series(closes, fast_period)
    medium_line = warmup_ema_series(closes, medium_period)
    slow_line = warmup_ema_series(closes, slow_period)
    atr_line = wilder_atr(rows, atr_period)
    # Simple average of the bars *before* each one: the published methodology
    # says SMA, and a baseline that already contains the bar being measured
    # divides a spike by a mean the spike itself inflated.
    volume_line: list[float | None] = [None] * len(rows)
    for index in range(volume_period, len(rows)):
        window = volumes[index - volume_period : index]
        volume_line[index] = sum(window) / volume_period

    states: list[TrendState] = []
    strength: list[float | None] = []
    upper: list[float | None] = []
    lower: list[float | None] = []
    signals: list[TrendTransition] = []

    for index in range(len(rows)):
        fast = fast_line[index]
        medium = medium_line[index]
        slow = slow_line[index]
        atr = atr_line[index]
        if fast is None or medium is None or slow is None or atr is None:
            states.append(TrendState.WARMING_UP)
            strength.append(None)
            upper.append(None)
            lower.append(None)
            continue
        if atr <= 0.0 or not isfinite(atr):
            # A collapsed range leaves no risk boundary to draw and no scale to
            # normalize the spread against; say so instead of dividing by it.
            states.append(TrendState.UNAVAILABLE)
            strength.append(None)
            upper.append(None)
            lower.append(None)
            continue

        upper.append(slow + atr_multiplier * atr)
        lower.append(slow - atr_multiplier * atr)
        strength.append(max(-3.0, min(3.0, (fast - slow) / atr)))
        if fast > medium > slow and closes[index] > medium:
            state = TrendState.BULLISH
        elif fast < medium < slow and closes[index] < medium:
            state = TrendState.BEARISH
        else:
            state = TrendState.NEUTRAL
        states.append(state)

        if state not in {TrendState.BULLISH, TrendState.BEARISH}:
            continue
        previous = states[index - 1] if index else TrendState.WARMING_UP
        if previous == state:
            continue
        if previous in {TrendState.WARMING_UP, TrendState.UNAVAILABLE}:
            # A transition means the regime changed. With no measurable regime
            # on the previous bar there is nothing to have changed from, and
            # calling it a transition would put the signal wherever the caller's
            # window happened to start.
            continue
        average_volume = volume_line[index]
        relative_volume = (
            volumes[index] / average_volume
            if average_volume is not None and average_volume > 0.0
            else None
        )
        current_strength = strength[index]
        assert current_strength is not None
        signals.append(
            TrendTransition(
                direction=(
                    Direction.BULLISH
                    if state is TrendState.BULLISH
                    else Direction.BEARISH
                ),
                confirmed_at_index=index,
                strength=current_strength,
                relative_volume=relative_volume,
                volume_confirmed=(
                    relative_volume is not None
                    and relative_volume >= volume_confirmation_ratio
                ),
            )
        )

    return DragonTrendResult(
        states=tuple(states),
        strength=tuple(strength),
        fast_line=fast_line,
        medium_line=medium_line,
        slow_line=slow_line,
        upper_channel=tuple(upper),
        lower_channel=tuple(lower),
        signals=tuple(signals),
    )
