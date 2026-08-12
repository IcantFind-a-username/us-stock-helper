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


TD_SETUP_VERSION = "td-setup-close-4-v2"


@dataclass(frozen=True, slots=True)
class MagicNineSignal:
    direction: Direction
    count: int
    completed: bool
    confirmed_at_index: int
    # None means the bar 8/9 comparison was not performed — a close-only
    # summary cannot see highs and lows, and a non-standard setup length has no
    # defined comparison. Publishing False there would present "not checked" as
    # "checked and not perfected".
    perfected: bool | None = None
    algorithm_version: str = TD_SETUP_VERSION


@dataclass(frozen=True, slots=True)
class TDSetupResult:
    """Per-bar TD Setup counts, every completed run, and the state right now."""

    bullish_counts: tuple[int, ...]
    bearish_counts: tuple[int, ...]
    signals: tuple[MagicNineSignal, ...]
    latest: MagicNineSignal | None
    algorithm_version: str = TD_SETUP_VERSION


def td_setup(
    bars: Sequence[OHLCVBar],
    *,
    lookback: int = 4,
    setup_length: int = 9,
) -> TDSetupResult:
    """Count closes against the close ``lookback`` bars earlier.

    A completed count is an exhaustion warning, never an instruction. Counting
    restarts after each completed run so a long one-sided stretch reports every
    exhaustion point rather than only its first.
    """

    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if setup_length < 2:
        raise ValueError("setup_length must be at least two")
    completed = tuple(bars)
    if any(not row.complete for row in completed):
        raise ValueError("TD setup requires completed candles")

    bullish_counts = [0] * len(completed)
    bearish_counts = [0] * len(completed)
    signals: list[MagicNineSignal] = []
    streak = 0
    direction: Direction | None = None

    for index in range(lookback, len(completed)):
        current = completed[index].close
        reference = completed[index - lookback].close
        if current < reference:
            candidate = Direction.BULLISH
        elif current > reference:
            candidate = Direction.BEARISH
        else:
            streak = 0
            direction = None
            continue
        streak = streak + 1 if candidate == direction else 1
        direction = candidate
        if candidate is Direction.BULLISH:
            bullish_counts[index] = streak
        else:
            bearish_counts[index] = streak
        if streak == setup_length:
            start = index - setup_length + 1
            signals.append(
                MagicNineSignal(
                    direction=candidate,
                    count=streak,
                    completed=True,
                    confirmed_at_index=index,
                    perfected=_is_perfected(completed, start, setup_length, candidate),
                )
            )
            streak = 0
            direction = None

    latest: MagicNineSignal | None = None
    if signals and signals[-1].confirmed_at_index == len(completed) - 1:
        latest = signals[-1]
    elif direction is not None and streak > 0:
        latest = MagicNineSignal(
            direction=direction,
            count=streak,
            completed=False,
            confirmed_at_index=len(completed) - 1,
        )

    return TDSetupResult(
        bullish_counts=tuple(bullish_counts),
        bearish_counts=tuple(bearish_counts),
        signals=tuple(signals),
        latest=latest,
    )


def magic_nine(closes: Sequence[float]) -> MagicNineSignal | None:
    """Summarize the TD Setup state as of the last close.

    Reports the run in progress right now, not the first one in history: a
    "current state" reading that ignores everything after an old completed
    sequence would describe a market that no longer exists.
    """

    if len(closes) < 5:
        return None
    values = [float(close) for close in closes]
    streak = 0
    direction: Direction | None = None
    for index in range(4, len(values)):
        if values[index] < values[index - 4]:
            candidate = Direction.BULLISH
        elif values[index] > values[index - 4]:
            candidate = Direction.BEARISH
        else:
            streak = 0
            direction = None
            continue
        streak = streak + 1 if candidate == direction else 1
        direction = candidate
        if streak == 9:
            if index == len(values) - 1:
                return MagicNineSignal(
                    direction=candidate,
                    count=9,
                    completed=True,
                    confirmed_at_index=index,
                )
            streak = 0
            direction = None
    if direction is None or streak == 0:
        return None
    return MagicNineSignal(
        direction=direction,
        count=streak,
        completed=False,
        confirmed_at_index=len(values) - 1,
    )


def _is_perfected(
    bars: Sequence[OHLCVBar],
    start: int,
    setup_length: int,
    direction: Direction,
) -> bool | None:
    if setup_length != 9:
        return None
    bar_six, bar_seven = bars[start + 5], bars[start + 6]
    bar_eight, bar_nine = bars[start + 7], bars[start + 8]
    if direction is Direction.BULLISH:
        return min(bar_eight.low, bar_nine.low) <= min(bar_six.low, bar_seven.low)
    return max(bar_eight.high, bar_nine.high) >= max(bar_six.high, bar_seven.high)


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
