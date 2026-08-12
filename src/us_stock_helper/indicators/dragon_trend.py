"""Transparent trend-system alternative to ambiguous proprietary dragon indicators."""

from typing import List, Optional

from .base import (
    CandleSeries,
    IndicatorMetadata,
    IndicatorResult,
    Signal,
    SourceReference,
)
from .math import ema, sma, wilder_atr
from .registry import register_indicator


METADATA = IndicatorMetadata(
    key="open_dragon_trend",
    display_name="Open Dragon Trend",
    description=(
        "Independent trend-state system using EMA alignment, an ATR risk channel "
        "and relative-volume confirmation. It performs the same category of job "
        "as paid trend-state indicators without claiming formula equivalence."
    ),
    implementation_kind="independent_transparent_alternative",
    sources=(
        SourceReference(
            title="富途牛牛帮助中心：技术指标",
            url="https://support.futunn.com/zh-hk/topic68",
            note="Public reference for configurable and custom technical indicators.",
        ),
    ),
    proprietary_equivalent=False,
)


@register_indicator(METADATA.key)
def open_dragon_trend(
    candles: CandleSeries,
    fast_period: int = 8,
    medium_period: int = 21,
    slow_period: int = 55,
    atr_period: int = 14,
    volume_period: int = 20,
    atr_multiplier: float = 1.5,
) -> IndicatorResult:
    """Return trend state, dynamic risk channel and transition signals."""

    periods = (fast_period, medium_period, slow_period, atr_period, volume_period)
    if any(period <= 0 for period in periods):
        raise ValueError("all periods must be positive")
    if not fast_period < medium_period < slow_period:
        raise ValueError("periods must satisfy fast < medium < slow")
    if atr_multiplier <= 0:
        raise ValueError("atr_multiplier must be positive")

    closes = [float(value) for value in candles.close]
    highs = [float(value) for value in candles.high]
    lows = [float(value) for value in candles.low]
    volumes = [float(value) for value in candles.volume]

    fast_line = ema(closes, fast_period)
    medium_line = ema(closes, medium_period)
    slow_line = ema(closes, slow_period)
    atr_line = wilder_atr(highs, lows, closes, atr_period)
    volume_average = sma(volumes, volume_period)

    upper_channel: List[Optional[float]] = [None] * len(candles)
    lower_channel: List[Optional[float]] = [None] * len(candles)
    state: List[str] = ["warming_up"] * len(candles)
    strength: List[Optional[float]] = [None] * len(candles)
    signals: List[Signal] = []

    for index in range(len(candles)):
        atr_value = atr_line[index]
        slow_value = slow_line[index]
        if atr_value is not None and slow_value is not None:
            upper_channel[index] = slow_value + atr_multiplier * atr_value
            lower_channel[index] = slow_value - atr_multiplier * atr_value

        if index < slow_period - 1 or atr_value in (None, 0):
            continue

        fast_value = fast_line[index]
        medium_value = medium_line[index]
        assert fast_value is not None
        assert medium_value is not None
        assert slow_value is not None

        normalized_spread = (fast_value - slow_value) / atr_value
        strength[index] = max(-3.0, min(3.0, normalized_spread))

        if fast_value > medium_value > slow_value and closes[index] > medium_value:
            state[index] = "bullish"
        elif fast_value < medium_value < slow_value and closes[index] < medium_value:
            state[index] = "bearish"
        else:
            state[index] = "neutral"

        previous_state = state[index - 1] if index else "warming_up"
        average_volume = volume_average[index]
        relative_volume = (
            volumes[index] / average_volume
            if average_volume not in (None, 0)
            else None
        )
        volume_confirmed = relative_volume is not None and relative_volume >= 1.2

        if state[index] == "bullish" and previous_state != "bullish":
            signals.append(
                Signal(
                    index=index,
                    kind="trend_transition",
                    direction="bullish",
                    confidence=0.75 if volume_confirmed else 0.55,
                    reason="快中慢趋势线转为多头排列",
                    evidence={
                        "relative_volume": relative_volume,
                        "volume_confirmed": volume_confirmed,
                        "normalized_spread": strength[index],
                    },
                )
            )
        elif state[index] == "bearish" and previous_state != "bearish":
            signals.append(
                Signal(
                    index=index,
                    kind="trend_transition",
                    direction="bearish",
                    confidence=0.75 if volume_confirmed else 0.55,
                    reason="快中慢趋势线转为空头排列",
                    evidence={
                        "relative_volume": relative_volume,
                        "volume_confirmed": volume_confirmed,
                        "normalized_spread": strength[index],
                    },
                )
            )

    return IndicatorResult(
        metadata=METADATA,
        values={
            "fast_line": tuple(fast_line),
            "medium_line": tuple(medium_line),
            "slow_line": tuple(slow_line),
            "upper_channel": tuple(upper_channel),
            "lower_channel": tuple(lower_channel),
            "state": tuple(state),
            "strength": tuple(strength),
            "relative_volume_average": tuple(volume_average),
        },
        signals=tuple(signals),
    )

