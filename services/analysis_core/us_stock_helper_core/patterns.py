"""Conservative, confirmation-only price pattern detectors."""

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .indicators import moving_average
from .models import Direction, OHLCVBar


class PatternKind(str, Enum):
    FRACTAL_TOP = "fractal_top"
    FRACTAL_BOTTOM = "fractal_bottom"
    MA5_PULLBACK = "ma5_pullback"
    DOUBLE_BOTTOM = "double_bottom"
    HEAD_AND_SHOULDERS = "head_and_shoulders"


@dataclass(frozen=True, slots=True)
class PatternSignal:
    kind: PatternKind
    direction: Direction
    confirmed_at_index: int
    confidence: float
    explanation: str


@dataclass(frozen=True, slots=True)
class MagicNineSignal:
    direction: Direction
    count: int
    completed: bool
    confirmed_at_index: int
    algorithm_version: str = "sequential-close-4-v1"


def magic_nine(closes: Sequence[float]) -> MagicNineSignal | None:
    if len(closes) < 5:
        return None
    count = 0
    direction: Direction | None = None
    for index in range(4, len(closes)):
        if closes[index] > closes[index - 4]:
            candidate = Direction.BEARISH
        elif closes[index] < closes[index - 4]:
            candidate = Direction.BULLISH
        else:
            count = 0
            direction = None
            continue
        if candidate == direction:
            count += 1
        else:
            direction = candidate
            count = 1
        if count == 9:
            return MagicNineSignal(
                direction=direction,
                count=count,
                completed=True,
                confirmed_at_index=index,
            )
    if direction is None or count == 0:
        return None
    return MagicNineSignal(
        direction=direction,
        count=count,
        completed=False,
        confirmed_at_index=len(closes) - 1,
    )


def three_bar_fractals(bars: Sequence[OHLCVBar]) -> tuple[PatternSignal, ...]:
    completed = _completed(bars)
    if len(completed) < 3:
        return ()
    signals: list[PatternSignal] = []
    for index in range(1, len(completed) - 1):
        left, middle, right = completed[index - 1 : index + 2]
        if middle.high > left.high and middle.high > right.high:
            signals.append(
                PatternSignal(
                    kind=PatternKind.FRACTAL_TOP,
                    direction=Direction.BEARISH,
                    confirmed_at_index=index + 1,
                    confidence=0.55,
                    explanation=(
                        "Middle bar high exceeded both neighbors; confirmed only "
                        "after the right bar closed."
                    ),
                )
            )
        if middle.low < left.low and middle.low < right.low:
            signals.append(
                PatternSignal(
                    kind=PatternKind.FRACTAL_BOTTOM,
                    direction=Direction.BULLISH,
                    confirmed_at_index=index + 1,
                    confidence=0.55,
                    explanation=(
                        "Middle bar low was below both neighbors; confirmed only "
                        "after the right bar closed."
                    ),
                )
            )
    return tuple(signals)


def detect_ma5_pullback(
    bars: Sequence[OHLCVBar], tolerance: float = 0.015
) -> PatternSignal | None:
    completed = _completed(bars)
    if len(completed) < 8:
        return None
    closes = [row.close for row in completed]
    current_ma = moving_average(closes, 5)
    prior_ma = moving_average(closes[:-3], 5)
    if current_ma is None or prior_ma is None:
        return None
    near_ma = abs(closes[-1] - current_ma) / current_ma <= tolerance
    is_pullback = closes[-1] < closes[-2]
    if near_ma and is_pullback and current_ma > prior_ma:
        return PatternSignal(
            kind=PatternKind.MA5_PULLBACK,
            direction=Direction.BULLISH,
            confirmed_at_index=len(completed) - 1,
            confidence=0.6,
            explanation="Price pulled back toward a rising five-bar average after the bar closed.",
        )
    if near_ma and closes[-1] > closes[-2] and current_ma < prior_ma:
        return PatternSignal(
            kind=PatternKind.MA5_PULLBACK,
            direction=Direction.BEARISH,
            confirmed_at_index=len(completed) - 1,
            confidence=0.6,
            explanation="Price rebounded toward a falling five-bar average after the bar closed.",
        )
    return None


def detect_double_bottom(
    bars: Sequence[OHLCVBar], low_tolerance: float = 0.04
) -> PatternSignal | None:
    completed = _completed(bars)
    if len(completed) < 7:
        return None
    lows = _local_extrema(completed, use_high=False)
    for first_position in range(len(lows) - 1):
        first = lows[first_position]
        for second in lows[first_position + 1 :]:
            if second - first < 3:
                continue
            first_low = completed[first].low
            second_low = completed[second].low
            relative_gap = abs(first_low - second_low) / min(first_low, second_low)
            if relative_gap > low_tolerance:
                continue
            neckline = max(row.high for row in completed[first + 1 : second])
            if completed[-1].close <= neckline or len(completed) - 1 <= second:
                continue
            return PatternSignal(
                kind=PatternKind.DOUBLE_BOTTOM,
                direction=Direction.BULLISH,
                confirmed_at_index=len(completed) - 1,
                confidence=0.7,
                explanation=(
                    "Two similar closed-bar lows were followed by a close above "
                    "the intervening neckline."
                ),
            )
    return None


def detect_head_and_shoulders(
    bars: Sequence[OHLCVBar], shoulder_tolerance: float = 0.08
) -> PatternSignal | None:
    completed = _completed(bars)
    if len(completed) < 8:
        return None
    peaks = _local_extrema(completed, use_high=True)
    for index in range(len(peaks) - 2):
        left, head, right = peaks[index : index + 3]
        left_high = completed[left].high
        head_high = completed[head].high
        right_high = completed[right].high
        shoulders_close = (
            abs(left_high - right_high) / min(left_high, right_high)
            <= shoulder_tolerance
        )
        head_clear = head_high >= max(left_high, right_high) * 1.03
        if not shoulders_close or not head_clear:
            continue
        left_trough = min(row.low for row in completed[left + 1 : head])
        right_trough = min(row.low for row in completed[head + 1 : right])
        neckline = (left_trough + right_trough) / 2.0
        if len(completed) - 1 <= right or completed[-1].close >= neckline:
            continue
        return PatternSignal(
            kind=PatternKind.HEAD_AND_SHOULDERS,
            direction=Direction.BEARISH,
            confirmed_at_index=len(completed) - 1,
            confidence=0.72,
            explanation=(
                "Three confirmed peaks formed shoulders around a higher head, "
                "followed by a close below the neckline."
            ),
        )
    return None


def _completed(bars: Sequence[OHLCVBar]) -> tuple[OHLCVBar, ...]:
    return tuple(row for row in bars if row.complete)


def _local_extrema(bars: Sequence[OHLCVBar], *, use_high: bool) -> list[int]:
    attribute = "high" if use_high else "low"
    result: list[int] = []
    for index in range(1, len(bars) - 1):
        left = getattr(bars[index - 1], attribute)
        middle = getattr(bars[index], attribute)
        right = getattr(bars[index + 1], attribute)
        if use_high and middle > left and middle > right:
            result.append(index)
        if not use_high and middle < left and middle < right:
            result.append(index)
    return result
