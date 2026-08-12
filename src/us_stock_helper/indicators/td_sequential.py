"""Public-rule TD Setup / 神奇九转 implementation."""

from typing import List

from .base import (
    CandleSeries,
    IndicatorMetadata,
    IndicatorResult,
    Signal,
    SourceReference,
)
from .registry import register_indicator


METADATA = IndicatorMetadata(
    key="td_nine_count",
    display_name="神奇九转（TD Setup）",
    description=(
        "Counts consecutive closes above or below the close four candles earlier. "
        "A completed count of nine is a momentum-exhaustion warning, not a trade order."
    ),
    implementation_kind="public_rule_reimplementation",
    sources=(
        SourceReference(
            title="神奇九轉指標：TD序列公式與常見陷阱",
            url="https://zlglobal.htsc.com.hk/zl/course/td-sequential.html",
            note="Public description of the close-versus-four-bars-earlier setup rule.",
        ),
        SourceReference(
            title="东方财富期货帮助中心：神奇九转",
            url="https://qhweb.eastmoney.com/videos/10/2454874.html",
            note="Public description and market-regime limitations.",
        ),
    ),
)


def _is_perfected(
    candles: CandleSeries, setup_start: int, direction: str
) -> bool:
    bar_6 = setup_start + 5
    bar_7 = setup_start + 6
    bar_8 = setup_start + 7
    bar_9 = setup_start + 8

    if direction == "bullish":
        reference = min(float(candles.low[bar_6]), float(candles.low[bar_7]))
        return min(float(candles.low[bar_8]), float(candles.low[bar_9])) <= reference

    reference = max(float(candles.high[bar_6]), float(candles.high[bar_7]))
    return max(float(candles.high[bar_8]), float(candles.high[bar_9])) >= reference


@register_indicator(METADATA.key)
def td_nine_count(
    candles: CandleSeries,
    lookback: int = 4,
    setup_length: int = 9,
) -> IndicatorResult:
    """Calculate high-nine and low-nine setups without future data.

    `bullish_count` is a potential low-nine reversal setup: close is below the
    close `lookback` candles earlier. `bearish_count` is the corresponding
    high-nine setup.
    """

    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if setup_length < 2:
        raise ValueError("setup_length must be at least two")

    bullish_count: List[int] = [0] * len(candles)
    bearish_count: List[int] = [0] * len(candles)
    bullish_streak = 0
    bearish_streak = 0
    signals: List[Signal] = []

    for index in range(lookback, len(candles)):
        current_close = float(candles.close[index])
        comparison_close = float(candles.close[index - lookback])

        if current_close < comparison_close:
            bullish_streak += 1
            bearish_streak = 0
            if bullish_streak <= setup_length:
                bullish_count[index] = bullish_streak
        elif current_close > comparison_close:
            bearish_streak += 1
            bullish_streak = 0
            if bearish_streak <= setup_length:
                bearish_count[index] = bearish_streak
        else:
            bullish_streak = 0
            bearish_streak = 0

        if bullish_streak == setup_length:
            setup_start = index - setup_length + 1
            perfected = (
                _is_perfected(candles, setup_start, "bullish")
                if setup_length == 9
                else False
            )
            signals.append(
                Signal(
                    index=index,
                    kind="td_setup_complete",
                    direction="bullish",
                    confidence=0.65 if perfected else 0.5,
                    reason="下跌九转完成，提示下行动能可能衰竭",
                    evidence={
                        "count": setup_length,
                        "lookback": lookback,
                        "perfected": perfected,
                        "close": current_close,
                        "comparison_close": comparison_close,
                    },
                )
            )

        if bearish_streak == setup_length:
            setup_start = index - setup_length + 1
            perfected = (
                _is_perfected(candles, setup_start, "bearish")
                if setup_length == 9
                else False
            )
            signals.append(
                Signal(
                    index=index,
                    kind="td_setup_complete",
                    direction="bearish",
                    confidence=0.65 if perfected else 0.5,
                    reason="上涨九转完成，提示上行动能可能衰竭",
                    evidence={
                        "count": setup_length,
                        "lookback": lookback,
                        "perfected": perfected,
                        "close": current_close,
                        "comparison_close": comparison_close,
                    },
                )
            )

    return IndicatorResult(
        metadata=METADATA,
        values={
            "bullish_count": tuple(bullish_count),
            "bearish_count": tuple(bearish_count),
        },
        signals=tuple(signals),
    )

