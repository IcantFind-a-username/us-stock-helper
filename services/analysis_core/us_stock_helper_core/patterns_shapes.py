"""Deterministic, completed-bars-only chart-shape pattern detectors.

Distinct from ``patterns.py`` (which owns TD Setup / Magic Nine counting):
this module only detects classic candlestick *shapes* -- 顶分型/底分型
(three-bar fractals), W底/双头 (double bottom/top with a neckline), 头肩顶/
头肩底 (head and shoulders with a neckline), and 回踩五日线企稳（回眸一笑）
(a pullback to a rising five-day average that holds and turns).

Every detector only ever looks at the bars it is given -- never a bar beyond
the tail of its input -- so a detector run on a prefix of a series always
agrees with the same detector run on the full series, restricted to that
prefix. Each pattern instance is emitted with an explicit ``status``:

``forming``     -- the structure exists but neither its confirming nor its
                    failing condition has happened yet, within the bars given.
                    This reading is inherently provisional: more bars can (and
                    are expected to) resolve it one way or the other.
``confirmed``   -- the decisive bar-close event that completes the pattern
                    happened at ``event_index``. Once emitted for a given
                    ``event_index``, a confirmed signal's fields never change:
                    appending future bars can add *new* signals, but this v1
                    detector set does not walk a confirmed breakout back to
                    "invalidated" if price later reverses through the
                    neckline again -- the ``invalidation`` string still names
                    that condition for the reader, it is just not auto-tracked
                    past confirmation yet.
``invalidated`` -- the pattern failed before it ever confirmed (support or
                    resistance broke first). Also permanent once emitted.

This gives the PIT guarantee the plan asks for: a signal detected using bars
``[0:T]`` is reproduced byte-for-byte by a later call over bars ``[0:T+k]``,
because the scan that produced it only ever consulted bars up to its own
``event_index`` -- see the PIT tests in ``test_patterns_shapes.py``.

The exact replay invariant, pinned by ``ReplayInvariantPropertyTests``: for
every prefix length ``k``, ``detect(bars[:k])`` restricted to signals that
resolved (confirmed or invalidated) at an index below ``k`` equals exactly
those signals in ``detect(bars)`` -- a full-history recompute never erases
or mutates an already-resolved signal. Structurally this holds because every
candidate (each similar-depth extremum pair, each shoulder/head/shoulder
triple, each MA5 pullback episode) resolves independently against the bars
that follow it: no scan shares a cursor between candidates, so one
candidate's late resolution cannot consume another's history. Only the
still-``forming`` tail read is provisional, and only the most recent
unresolved candidate is surfaced as that read.

Below each detector's own minimum window, it returns a typed-unavailable
``PatternShapeDetection`` (``quality_status="unavailable"`` with a
``missing_reason``) rather than silently reporting "no pattern found" for a
window nobody actually looked at.

回踩五日线企稳（回眸一笑）is a colloquial retail pattern with no textbook
definition, so the rule this module ships IS the spec (v1):

1. The five-day average (MA5) must be rising at the touch bar: comparing MA5
   at the touch bar to MA5 three bars earlier, the later value must be
   greater.
2. A touch bar is any bar whose close sits within ``near_tolerance`` (default
   1.5%) of that day's MA5, and whose close is below the previous bar's close
   (the "回踩" -- pulling back toward the average). Each touch opens an
   episode; while that episode is still unresolved, a further qualifying
   touch re-anchors it to the most recent touch bar. Once an episode has
   resolved (rule 3 or 4), it is emitted immutably and a later qualifying
   touch starts a new episode -- it never re-anchors, and thereby never
   erases, an episode that already resolved.
3. Confirmation ("回眸一笑"): the first later bar whose close is above the
   previous bar's close, is not below that day's MA5, and whose MA5 is still
   higher than it was three bars earlier. That bar's index is the
   confirmation event.
4. Invalidation: if, before confirmation, a bar's close falls below
   ``MA5 * (1 - break_tolerance)`` (default 2%), the pullback failed to hold
   and the pattern is invalidated at that bar.
5. If neither has happened within the given bars, the pattern is still
   forming as of the last bar.

Every detection also carries a fixed three-layer plain-language reading
(``reading_summary``, ``reading_detail``, and the honesty line
``reading_honesty``) drawn from :data:`PATTERN_SHAPE_READING_COPY`, a
reviewed, versioned mapping from every reachable ``(kind, status)`` to its
copy -- see :data:`REACHABLE_PATTERN_SHAPE_STATES` and the completeness test
that pins every one of them has an entry. None of this copy ever names an
action: it describes structure and its failure condition only.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence

from .indicators import moving_average_series
from .models import Direction, OHLCVBar, require_utc


PATTERNS_SHAPES_VERSION = "patterns-shapes-v1"

_FRACTAL_MIN_WINDOW = 3
_DOUBLE_EXTREME_MIN_WINDOW = 7
_HEAD_SHOULDERS_MIN_WINDOW = 8
_MA5_PULLBACK_MIN_WINDOW = 8


class PatternShapeKind(str, Enum):
    FRACTAL_TOP = "fractal_top"
    FRACTAL_BOTTOM = "fractal_bottom"
    DOUBLE_BOTTOM = "double_bottom"
    DOUBLE_TOP = "double_top"
    HEAD_SHOULDERS_TOP = "head_shoulders_top"
    HEAD_SHOULDERS_BOTTOM = "head_shoulders_bottom"
    MA5_PULLBACK = "ma5_pullback"


class PatternShapeStatus(str, Enum):
    FORMING = "forming"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


_KIND_NAME_ZH: dict[PatternShapeKind, str] = {
    PatternShapeKind.FRACTAL_TOP: "顶分型",
    PatternShapeKind.FRACTAL_BOTTOM: "底分型",
    PatternShapeKind.DOUBLE_BOTTOM: "W底",
    PatternShapeKind.DOUBLE_TOP: "双头",
    PatternShapeKind.HEAD_SHOULDERS_TOP: "头肩顶",
    PatternShapeKind.HEAD_SHOULDERS_BOTTOM: "头肩底",
    PatternShapeKind.MA5_PULLBACK: "回踩五日线企稳（回眸一笑）",
}

# Every (kind, status) this module can ever emit. The completeness test pins
# that PATTERN_SHAPE_READING_COPY has an entry for each -- a new reachable
# state added to a detector without matching copy fails that test rather than
# silently serving jargon (or nothing) to the reader.
REACHABLE_PATTERN_SHAPE_STATES: tuple[tuple[PatternShapeKind, PatternShapeStatus], ...] = (
    (PatternShapeKind.FRACTAL_TOP, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.FRACTAL_BOTTOM, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.FORMING),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.INVALIDATED),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.FORMING),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.INVALIDATED),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.FORMING),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.INVALIDATED),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.FORMING),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.INVALIDATED),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.FORMING),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.CONFIRMED),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.INVALIDATED),
)

# 一句话含义 / 展开解释 per reachable (kind, status). Reviewed, versioned copy --
# not free generation. Every string here describes structure and its failure
# condition; none names an action (enforced by
# ReadingCopyCompletenessTests.test_no_reading_copy_uses_a_banned_action_verb).
PATTERN_SHAPE_READING_COPY: dict[
    tuple[PatternShapeKind, PatternShapeStatus], tuple[str, str]
] = {
    (PatternShapeKind.FRACTAL_TOP, PatternShapeStatus.CONFIRMED): (
        "顶分型：连续上涨后，中间这根K线的高点比两边都高，短线上攻可能遇到阻力的第一个迹象。",
        "顶分型是最小的三根K线反转结构：中间K线的最高价同时高于左右两根K线的最高价，"
        "第三根K线收盘后才能确认。它只描述K线形态本身，不代表趋势一定反转。",
    ),
    (PatternShapeKind.FRACTAL_BOTTOM, PatternShapeStatus.CONFIRMED): (
        "底分型：连续下跌后，中间这根K线的最低点比两边都低，又收回来了"
        "——短线卖压可能衰竭的第一个迹象。",
        "底分型是最小的三根K线反转结构：中间K线的最低价同时低于左右两根K线的最低价，"
        "第三根K线收盘后才能确认。它只描述K线形态本身，不代表趋势一定反转。",
    ),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.FORMING): (
        "W底正在形成：价格两次探到相近的低点，目前还没有收盘站上颈线，形态尚未成立。",
        "两个低点幅度接近，中间隔着一个反弹高点（颈线）。在收盘价站上颈线之前，"
        "这只是一个观察中的结构；如果价格先跌破前一个低点，形态会直接失败。",
    ),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.CONFIRMED): (
        "W底已确认：价格两次探底后，收盘站上了颈线，短线动能转强的信号出现了。",
        "两个相近的低点之间夹着一个反弹高点，即颈线；收盘价升破颈线视为形态确认。"
        "确认后的关注点是颈线能否守住——收盘再次跌破颈线，说明这次突破可能是假突破。",
    ),
    (PatternShapeKind.DOUBLE_BOTTOM, PatternShapeStatus.INVALIDATED): (
        "W底未能成立：价格在收盘站上颈线之前，先跌破了前一个低点，这个结构已经作废。",
        "第二个低点本应与第一个低点幅度接近并守住，但收盘价在突破颈线前先跌破了它，"
        "说明下跌压力仍在延续，双底结构不再成立。",
    ),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.FORMING): (
        "双头正在形成：价格两次冲到相近的高点，目前还没有收盘跌破颈线，形态尚未成立。",
        "两个高点幅度接近，中间隔着一个回落低点（颈线）。在收盘价跌破颈线之前，"
        "这只是一个观察中的结构；如果价格先升破前一个高点，形态会直接失败。",
    ),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.CONFIRMED): (
        "双头已确认：价格两次冲高后，收盘跌破了颈线，短线动能转弱的信号出现了。",
        "两个相近的高点之间夹着一个回落低点，即颈线；收盘价跌破颈线视为形态确认。"
        "确认后的关注点是颈线能否压住——收盘再次升破颈线，说明这次跌破可能是假跌破。",
    ),
    (PatternShapeKind.DOUBLE_TOP, PatternShapeStatus.INVALIDATED): (
        "双头未能成立：价格在收盘跌破颈线之前，先升破了前一个高点，这个结构已经作废。",
        "第二个高点本应与第一个高点幅度接近并受阻，但收盘价在跌破颈线前先升破了它，"
        "说明上涨动能仍在延续，双头结构不再成立。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.FORMING): (
        "头肩顶正在形成：出现了左肩、头部、右肩的雏形，目前还没有收盘跌破颈线，形态尚未成立。",
        "头部的高点明显高于两侧的肩部，两个肩部幅度接近；两个肩部之间的低点连线是颈线。"
        "收盘价跌破颈线才算确认；如果价格先升破头部高点，形态会直接失败。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.CONFIRMED): (
        "头肩顶已确认：左肩、头部、右肩形成后，收盘跌破了颈线，短线转弱的信号出现了。",
        "头部高点明显高于两侧肩部，右肩形成后收盘价跌破颈线视为形态成立。"
        "确认后的关注点是颈线能否压住——收盘再次升破颈线，说明这次跌破可能是假跌破。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_TOP, PatternShapeStatus.INVALIDATED): (
        "头肩顶未能成立：价格在收盘跌破颈线之前，先升破了头部高点，这个结构已经作废。",
        "右肩形成后本应受阻回落，但收盘价在跌破颈线前反而升破了头部的最高点，"
        "说明上涨动能仍在延续，头肩顶结构不再成立。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.FORMING): (
        "头肩底正在形成：出现了左肩、头部、右肩的雏形，目前还没有收盘升破颈线，形态尚未成立。",
        "头部的低点明显低于两侧的肩部，两个肩部幅度接近；两个肩部之间的高点连线是颈线。"
        "收盘价升破颈线才算确认；如果价格先跌破头部低点，形态会直接失败。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.CONFIRMED): (
        "头肩底已确认：左肩、头部、右肩形成后，收盘升破了颈线，短线转强的信号出现了。",
        "头部低点明显低于两侧肩部，右肩形成后收盘价升破颈线视为形态成立。"
        "确认后的关注点是颈线能否守住——收盘再次跌破颈线，说明这次突破可能是假突破。",
    ),
    (PatternShapeKind.HEAD_SHOULDERS_BOTTOM, PatternShapeStatus.INVALIDATED): (
        "头肩底未能成立：价格在收盘升破颈线之前，先跌破了头部低点，这个结构已经作废。",
        "右肩形成后本应企稳回升，但收盘价在升破颈线前反而跌破了头部的最低点，"
        "说明下跌压力仍在延续，头肩底结构不再成立。",
    ),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.FORMING): (
        "回踩五日线：价格靠近了五日均线，目前还没有收盘走稳，形态尚未确认。",
        "五日均线保持上升，价格回落到均线附近；如果接下来收盘价重新走高并守住均线，"
        "视为“回眸一笑”确认；如果先明显跌破均线，视为回踩失败。",
    ),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.CONFIRMED): (
        "回眸一笑：价格回踩五日均线后，收盘重新走高并守住了均线，短线企稳的信号出现了。",
        "五日均线保持上升，价格回落到均线附近后收盘转强，且收盘价仍在均线之上"
        "——这是回踩确认的判定标准。均线转跌或收盘再次跌破均线，会让这个企稳读数作废。",
    ),
    (PatternShapeKind.MA5_PULLBACK, PatternShapeStatus.INVALIDATED): (
        "回踩未能企稳：价格靠近五日均线后没有站稳，收盘明显跌破了均线。",
        "价格回落到五日均线附近后，没有出现收盘走高守住均线的确认，反而收盘跌破了均线"
        "一定幅度，说明这次回踩未能企稳。",
    ),
}


def _reading_copy(kind: PatternShapeKind, status: PatternShapeStatus) -> tuple[str, str]:
    try:
        return PATTERN_SHAPE_READING_COPY[(kind, status)]
    except KeyError as error:  # pragma: no cover - defensive, caught by tests
        raise ValueError(
            f"no plain-language reading defined for {kind.value}/{status.value}"
        ) from error


@dataclass(frozen=True, slots=True)
class PatternBar:
    """One bar's identity for chart marker placement."""

    index: int
    closed_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.closed_at, "closed_at")
        if self.index < 0:
            raise ValueError("index must be non-negative")


@dataclass(frozen=True, slots=True)
class PatternShapeSignal:
    """One detected pattern instance, its status, and its explained hint."""

    kind: PatternShapeKind
    name: str
    status: PatternShapeStatus
    direction: Direction
    # The structural bars (pivots, shoulders, touch bar...) in chronological
    # order -- for chart markers.
    bars: tuple[PatternBar, ...]
    # Which bar in ``bars`` a chart marker should anchor to.
    anchor: PatternBar
    # The bar index at which this status became true (confirmed_at /
    # invalidated_at / "as of" the last bar for a still-forming read).
    event_index: int
    invalidation: str
    explanation: str
    reading_summary: str
    reading_detail: str
    reading_honesty: str = "历史胜率待回测"
    algorithm_version: str = PATTERNS_SHAPES_VERSION
    # Machine-readable twin of the served ``invalidation`` sentence: the
    # price level whose strict breach against the signal's direction (a
    # close strictly below it for a bullish signal, strictly above it for a
    # bearish one -- 跌破/升破 are strict) voids the signal. Confirmed
    # signals carry it so downstream consumers (the 形态 score factor) can
    # check "still in force" without re-deriving necklines; forming signals
    # carry the level whose breach fails the candidate. ``None`` when the
    # boundary is not a fixed level (回踩五日线 tracks each day's own MA5)
    # or the signal is already invalidated.
    invalidation_level: float | None = None

    def __post_init__(self) -> None:
        if self.algorithm_version != PATTERNS_SHAPES_VERSION:
            raise ValueError("unsupported patterns-shapes algorithm version")
        if (
            self.status is PatternShapeStatus.CONFIRMED
            and self.kind is not PatternShapeKind.MA5_PULLBACK
            and self.invalidation_level is None
        ):
            raise ValueError(
                "a confirmed signal requires its machine-readable invalidation level"
            )
        if not self.bars:
            raise ValueError("a pattern signal requires at least one structural bar")
        indices = [b.index for b in self.bars]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            raise ValueError("structural bars must be strictly increasing")
        if self.anchor not in self.bars:
            raise ValueError("anchor must be one of the structural bars")
        if self.event_index < 0:
            raise ValueError("event_index must be non-negative")
        if self.name.strip() != _KIND_NAME_ZH[self.kind]:
            raise ValueError("name must match the kind's Chinese display name")
        if not self.invalidation.strip():
            raise ValueError("invalidation condition is required")
        if not self.explanation.strip():
            raise ValueError("explanation is required")
        if self.reading_honesty != "历史胜率待回测":
            raise ValueError("reading_honesty must carry the fixed backtest disclosure")
        if not self.reading_summary.strip() or not self.reading_detail.strip():
            raise ValueError("reading_summary and reading_detail are required")


@dataclass(frozen=True, slots=True)
class PatternShapeDetection:
    """One detector's result: either its emitted signals, or typed-unavailable."""

    detector: str
    minimum_window: int
    sample_size: int
    quality_status: str
    missing_reason: str | None
    signals: tuple[PatternShapeSignal, ...]
    algorithm_version: str = PATTERNS_SHAPES_VERSION

    def __post_init__(self) -> None:
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.minimum_window < 1:
            raise ValueError("minimum_window must be positive")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")
        if self.quality_status == "unavailable":
            if self.signals:
                raise ValueError("an unavailable detection carries no signals")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable detection requires a reason")
        elif self.missing_reason is not None:
            raise ValueError("a live detection cannot carry a missing reason")


def _completed_bars(bars: Sequence[OHLCVBar]) -> tuple[OHLCVBar, ...]:
    rows = tuple(bars)
    if any(not row.complete for row in rows):
        raise ValueError("pattern shape detectors require completed candles")
    if len({row.symbol.upper() for row in rows}) > 1:
        raise ValueError("pattern shape detectors require a single symbol")
    if len({row.interval for row in rows}) > 1:
        raise ValueError("pattern shape detectors require a single interval")
    for index in range(1, len(rows)):
        if rows[index].closed_at <= rows[index - 1].closed_at:
            raise ValueError("bars must be strictly increasing in time")
    return rows


def _bar_ref(bars: Sequence[OHLCVBar], index: int) -> PatternBar:
    return PatternBar(index=index, closed_at=bars[index].closed_at)


def _unavailable(detector: str, minimum_window: int, sample_size: int, reason: str) -> PatternShapeDetection:
    return PatternShapeDetection(
        detector=detector,
        minimum_window=minimum_window,
        sample_size=sample_size,
        quality_status="unavailable",
        missing_reason=reason,
        signals=(),
    )


# ---------------------------------------------------------------------------
# 顶分型 / 底分型
# ---------------------------------------------------------------------------


def detect_fractal_patterns(bars: Sequence[OHLCVBar]) -> PatternShapeDetection:
    """Three-bar fractal tops and bottoms, confirmed the instant they exist.

    A fractal is structurally atomic -- it takes exactly three closed bars to
    identify the middle one as a local extreme -- so every emitted signal is
    ``confirmed`` (there is no partial fractal to call "forming").
    """

    completed = _completed_bars(bars)
    if len(completed) < _FRACTAL_MIN_WINDOW:
        return _unavailable(
            "fractal",
            _FRACTAL_MIN_WINDOW,
            len(completed),
            f"完整K线不足 {_FRACTAL_MIN_WINDOW} 根，暂无法识别分型",
        )
    signals: list[PatternShapeSignal] = []
    for index in range(1, len(completed) - 1):
        left, middle, right = completed[index - 1], completed[index], completed[index + 1]
        if middle.high > left.high and middle.high > right.high:
            signals.append(_build_fractal_signal(completed, index, PatternShapeKind.FRACTAL_TOP))
        if middle.low < left.low and middle.low < right.low:
            signals.append(_build_fractal_signal(completed, index, PatternShapeKind.FRACTAL_BOTTOM))
    return PatternShapeDetection(
        detector="fractal",
        minimum_window=_FRACTAL_MIN_WINDOW,
        sample_size=len(completed),
        quality_status="live",
        missing_reason=None,
        signals=tuple(signals),
    )


def _build_fractal_signal(
    bars: Sequence[OHLCVBar], index: int, kind: PatternShapeKind
) -> PatternShapeSignal:
    is_top = kind is PatternShapeKind.FRACTAL_TOP
    middle = bars[index]
    extreme = middle.high if is_top else middle.low
    direction = Direction.BEARISH if is_top else Direction.BULLISH
    invalidation = (
        f"收盘价升破分型高点 {extreme:.2f}"
        if is_top
        else f"收盘价跌破分型低点 {extreme:.2f}"
    )
    explanation = (
        "中间K线的最高价同时高于左右两根K线，第三根K线收盘后确认。"
        if is_top
        else "中间K线的最低价同时低于左右两根K线，第三根K线收盘后确认。"
    )
    summary, detail = _reading_copy(kind, PatternShapeStatus.CONFIRMED)
    bars_ref = (_bar_ref(bars, index - 1), _bar_ref(bars, index), _bar_ref(bars, index + 1))
    return PatternShapeSignal(
        kind=kind,
        name=_KIND_NAME_ZH[kind],
        status=PatternShapeStatus.CONFIRMED,
        direction=direction,
        bars=bars_ref,
        anchor=bars_ref[1],
        event_index=index + 1,
        invalidation=invalidation,
        explanation=explanation,
        reading_summary=summary,
        reading_detail=detail,
        invalidation_level=extreme,
    )


# ---------------------------------------------------------------------------
# W底 / 双头
# ---------------------------------------------------------------------------


def detect_double_extreme_patterns(
    bars: Sequence[OHLCVBar], *, tolerance: float = 0.04
) -> PatternShapeDetection:
    """W底 (double bottom) and 双头 (double top), each with a neckline.

    Two similar-depth troughs (or peaks) at least three bars apart, with a
    neckline drawn from the extreme between them. A candidate is ``forming``
    until either a close breaks the neckline in the pattern's favor
    (``confirmed``) or a close breaks back past the second extreme first
    (``invalidated``) -- whichever happens first, scanning forward through
    only the bars given.
    """

    completed = _completed_bars(bars)
    if len(completed) < _DOUBLE_EXTREME_MIN_WINDOW:
        return _unavailable(
            "double_extreme",
            _DOUBLE_EXTREME_MIN_WINDOW,
            len(completed),
            f"完整K线不足 {_DOUBLE_EXTREME_MIN_WINDOW} 根，暂无法识别双重顶/底",
        )
    signals: list[PatternShapeSignal] = []
    signals.extend(
        _scan_double_pattern(
            completed, use_high=False, kind=PatternShapeKind.DOUBLE_BOTTOM, tolerance=tolerance
        )
    )
    signals.extend(
        _scan_double_pattern(
            completed, use_high=True, kind=PatternShapeKind.DOUBLE_TOP, tolerance=tolerance
        )
    )
    return PatternShapeDetection(
        detector="double_extreme",
        minimum_window=_DOUBLE_EXTREME_MIN_WINDOW,
        sample_size=len(completed),
        quality_status="live",
        missing_reason=None,
        signals=tuple(signals),
    )


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


def _scan_double_pattern(
    bars: Sequence[OHLCVBar], *, use_high: bool, kind: PatternShapeKind, tolerance: float
) -> list[PatternShapeSignal]:
    """Each candidate pair resolves independently, so replay never lies.

    Every extremum anchors at most one candidate: it pairs, as the second
    touch of the pattern, with the most recent similar-depth extremum far
    enough before it. Each candidate then scans forward through the bars on
    its own: no shared cursor, so one candidate's late resolution can never
    consume the history -- or the already-resolved episode -- of another.
    Every episode that confirmed or invalidated within the given bars is
    emitted, immutable under any longer replay (both pairings and
    resolutions read only bars at or before their own indices, so a prefix
    rerun reproduces them byte-for-byte); of the candidates still unresolved
    at the tail, only the most recent is surfaced as the single provisional
    ``forming`` read.
    """

    extrema = _local_extrema(bars, use_high=use_high)
    signals: list[PatternShapeSignal] = []
    forming_candidate: tuple[int, int, float, float] | None = None
    for position, second in enumerate(extrema):
        matched: tuple[int, int, float, float] | None = None
        for probe in range(position - 1, -1, -1):
            first = extrema[probe]
            if second - first < 3 or first + 1 >= second:
                continue
            first_extreme = getattr(bars[first], "high" if use_high else "low")
            second_extreme = getattr(bars[second], "high" if use_high else "low")
            relative_gap = abs(first_extreme - second_extreme) / min(first_extreme, second_extreme)
            if relative_gap > tolerance:
                continue
            matched = (first, second, first_extreme, second_extreme)
            break
        if matched is None:
            continue
        first, second, first_extreme, second_extreme = matched
        between = bars[first + 1 : second]
        neckline = min(row.low for row in between) if use_high else max(row.high for row in between)
        resolution = _resolve_forward(bars, second, neckline, second_extreme, use_high=use_high)
        if resolution is not None:
            status, event_index = resolution
            signals.append(
                _build_double_signal(
                    bars, kind, first, second, neckline, status, event_index, second_extreme
                )
            )
            continue
        forming_candidate = (first, second, neckline, second_extreme)
    if forming_candidate is not None:
        first, second, neckline, second_extreme = forming_candidate
        signals.append(
            _build_double_signal(
                bars,
                kind,
                first,
                second,
                neckline,
                PatternShapeStatus.FORMING,
                len(bars) - 1,
                second_extreme,
            )
        )
    return signals


def _resolve_forward(
    bars: Sequence[OHLCVBar],
    from_index: int,
    neckline: float,
    extreme_to_defend: float,
    *,
    use_high: bool,
) -> tuple[PatternShapeStatus, int] | None:
    for probe in range(from_index + 1, len(bars)):
        close = bars[probe].close
        if use_high:
            if close < neckline:
                return PatternShapeStatus.CONFIRMED, probe
            if close > extreme_to_defend:
                return PatternShapeStatus.INVALIDATED, probe
        else:
            if close > neckline:
                return PatternShapeStatus.CONFIRMED, probe
            if close < extreme_to_defend:
                return PatternShapeStatus.INVALIDATED, probe
    return None


def _build_double_signal(
    bars: Sequence[OHLCVBar],
    kind: PatternShapeKind,
    first: int,
    second: int,
    neckline: float,
    status: PatternShapeStatus,
    event_index: int,
    second_extreme: float,
) -> PatternShapeSignal:
    is_top = kind is PatternShapeKind.DOUBLE_TOP
    direction = Direction.BEARISH if is_top else Direction.BULLISH
    if status is PatternShapeStatus.FORMING:
        invalidation = (
            f"确认前收盘升破前高 {second_extreme:.2f} 视为形态失败"
            if is_top
            else f"确认前收盘跌破前低 {second_extreme:.2f} 视为形态失败"
        )
    elif status is PatternShapeStatus.CONFIRMED:
        invalidation = (
            f"收盘升破颈线 {neckline:.2f}" if is_top else f"收盘跌破颈线 {neckline:.2f}"
        )
    else:
        invalidation = (
            f"确认前收盘升破前高 {second_extreme:.2f}，形态未能成立"
            if is_top
            else f"确认前收盘跌破前低 {second_extreme:.2f}，形态未能成立"
        )
    explanation = (
        f"两个高点分别在第 {first} 根与第 {second} 根K线附近，幅度接近；颈线 {neckline:.2f}。"
        if is_top
        else f"两个低点分别在第 {first} 根与第 {second} 根K线附近，幅度接近；颈线 {neckline:.2f}。"
    )
    summary, detail = _reading_copy(kind, status)
    bars_ref = (_bar_ref(bars, first), _bar_ref(bars, second), _bar_ref(bars, event_index))
    if bars_ref[2].index == bars_ref[1].index:
        bars_ref = bars_ref[:2]
    if status is PatternShapeStatus.FORMING:
        invalidation_level: float | None = second_extreme
    elif status is PatternShapeStatus.CONFIRMED:
        invalidation_level = neckline
    else:
        invalidation_level = None
    return PatternShapeSignal(
        kind=kind,
        name=_KIND_NAME_ZH[kind],
        status=status,
        direction=direction,
        bars=bars_ref,
        anchor=_bar_ref(bars, second),
        event_index=event_index,
        invalidation=invalidation,
        explanation=explanation,
        reading_summary=summary,
        reading_detail=detail,
        invalidation_level=invalidation_level,
    )


# ---------------------------------------------------------------------------
# 头肩顶 / 头肩底
# ---------------------------------------------------------------------------


def detect_head_and_shoulders_patterns(
    bars: Sequence[OHLCVBar],
    *,
    shoulder_tolerance: float = 0.08,
    head_clearance: float = 1.03,
) -> PatternShapeDetection:
    """头肩顶 (top) and 头肩底 (bottom), each with a neckline.

    Three extrema (left shoulder, head, right shoulder) where the shoulders
    are within ``shoulder_tolerance`` of each other and the head clears both
    by at least ``head_clearance``. The neckline is the average of the two
    troughs (or peaks) flanking the head. ``forming`` until either the
    neckline breaks in the pattern's favor (``confirmed``) or price reclaims
    the head's own extreme first (``invalidated``).
    """

    completed = _completed_bars(bars)
    if len(completed) < _HEAD_SHOULDERS_MIN_WINDOW:
        return _unavailable(
            "head_and_shoulders",
            _HEAD_SHOULDERS_MIN_WINDOW,
            len(completed),
            f"完整K线不足 {_HEAD_SHOULDERS_MIN_WINDOW} 根，暂无法识别头肩形态",
        )
    signals: list[PatternShapeSignal] = []
    signals.extend(
        _scan_head_and_shoulders(
            completed,
            use_high=True,
            kind=PatternShapeKind.HEAD_SHOULDERS_TOP,
            shoulder_tolerance=shoulder_tolerance,
            head_clearance=head_clearance,
        )
    )
    signals.extend(
        _scan_head_and_shoulders(
            completed,
            use_high=False,
            kind=PatternShapeKind.HEAD_SHOULDERS_BOTTOM,
            shoulder_tolerance=shoulder_tolerance,
            head_clearance=head_clearance,
        )
    )
    return PatternShapeDetection(
        detector="head_and_shoulders",
        minimum_window=_HEAD_SHOULDERS_MIN_WINDOW,
        sample_size=len(completed),
        quality_status="live",
        missing_reason=None,
        signals=tuple(signals),
    )


def _scan_head_and_shoulders(
    bars: Sequence[OHLCVBar],
    *,
    use_high: bool,
    kind: PatternShapeKind,
    shoulder_tolerance: float,
    head_clearance: float,
) -> list[PatternShapeSignal]:
    """Each shoulder/head/shoulder triple resolves independently -- see
    ``_scan_double_pattern`` for why no scan may share a cursor: a triple's
    late resolution must never erase another triple's already-resolved
    episode from a longer replay."""

    peaks = _local_extrema(bars, use_high=use_high)
    signals: list[PatternShapeSignal] = []
    forming_candidate: tuple[int, int, int, float, float] | None = None
    for index in range(len(peaks) - 2):
        left, head, right = peaks[index], peaks[index + 1], peaks[index + 2]
        if left + 1 >= head or head + 1 >= right:
            continue
        left_extreme = getattr(bars[left], "high" if use_high else "low")
        head_extreme = getattr(bars[head], "high" if use_high else "low")
        right_extreme = getattr(bars[right], "high" if use_high else "low")
        shoulders_close = (
            abs(left_extreme - right_extreme) / min(left_extreme, right_extreme)
            <= shoulder_tolerance
        )
        head_clear = (
            head_extreme >= max(left_extreme, right_extreme) * head_clearance
            if use_high
            else head_extreme <= min(left_extreme, right_extreme) / head_clearance
        )
        if not (shoulders_close and head_clear):
            continue
        if use_high:
            left_trough = min(row.low for row in bars[left + 1 : head])
            right_trough = min(row.low for row in bars[head + 1 : right])
            neckline = (left_trough + right_trough) / 2.0
        else:
            left_peak = max(row.high for row in bars[left + 1 : head])
            right_peak = max(row.high for row in bars[head + 1 : right])
            neckline = (left_peak + right_peak) / 2.0
        resolution = _resolve_forward(bars, right, neckline, head_extreme, use_high=use_high)
        if resolution is not None:
            status, event_index = resolution
            signals.append(
                _build_hs_signal(
                    bars, kind, left, head, right, neckline, status, event_index, head_extreme
                )
            )
            continue
        forming_candidate = (left, head, right, neckline, head_extreme)
    if forming_candidate is not None:
        left, head, right, neckline, head_extreme = forming_candidate
        signals.append(
            _build_hs_signal(
                bars,
                kind,
                left,
                head,
                right,
                neckline,
                PatternShapeStatus.FORMING,
                len(bars) - 1,
                head_extreme,
            )
        )
    return signals


def _build_hs_signal(
    bars: Sequence[OHLCVBar],
    kind: PatternShapeKind,
    left: int,
    head: int,
    right: int,
    neckline: float,
    status: PatternShapeStatus,
    event_index: int,
    head_extreme: float,
) -> PatternShapeSignal:
    is_top = kind is PatternShapeKind.HEAD_SHOULDERS_TOP
    direction = Direction.BEARISH if is_top else Direction.BULLISH
    if status is PatternShapeStatus.FORMING:
        invalidation = (
            f"确认前收盘升破头部高点 {head_extreme:.2f} 视为形态失败"
            if is_top
            else f"确认前收盘跌破头部低点 {head_extreme:.2f} 视为形态失败"
        )
    elif status is PatternShapeStatus.CONFIRMED:
        invalidation = (
            f"收盘升破颈线 {neckline:.2f}" if is_top else f"收盘跌破颈线 {neckline:.2f}"
        )
    else:
        invalidation = (
            f"确认前收盘升破头部高点 {head_extreme:.2f}，形态未能成立"
            if is_top
            else f"确认前收盘跌破头部低点 {head_extreme:.2f}，形态未能成立"
        )
    explanation = (
        f"左肩、头部、右肩分别在第 {left}、{head}、{right} 根K线附近；颈线 {neckline:.2f}。"
    )
    summary, detail = _reading_copy(kind, status)
    bars_ref = (
        _bar_ref(bars, left),
        _bar_ref(bars, head),
        _bar_ref(bars, right),
        _bar_ref(bars, event_index),
    )
    if bars_ref[3].index == bars_ref[2].index:
        bars_ref = bars_ref[:3]
    if status is PatternShapeStatus.FORMING:
        invalidation_level: float | None = head_extreme
    elif status is PatternShapeStatus.CONFIRMED:
        invalidation_level = neckline
    else:
        invalidation_level = None
    return PatternShapeSignal(
        kind=kind,
        name=_KIND_NAME_ZH[kind],
        status=status,
        direction=direction,
        bars=bars_ref,
        anchor=_bar_ref(bars, head),
        event_index=event_index,
        invalidation=invalidation,
        explanation=explanation,
        reading_summary=summary,
        reading_detail=detail,
        invalidation_level=invalidation_level,
    )


# ---------------------------------------------------------------------------
# 回踩五日线企稳（回眸一笑）
# ---------------------------------------------------------------------------


def detect_ma5_pullback_pattern(
    bars: Sequence[OHLCVBar],
    *,
    near_tolerance: float = 0.015,
    break_tolerance: float = 0.02,
) -> PatternShapeDetection:
    """回踩五日线企稳（回眸一笑）-- see the module docstring for the exact rule."""

    completed = _completed_bars(bars)
    if len(completed) < _MA5_PULLBACK_MIN_WINDOW:
        return _unavailable(
            "ma5_pullback",
            _MA5_PULLBACK_MIN_WINDOW,
            len(completed),
            f"完整K线不足 {_MA5_PULLBACK_MIN_WINDOW} 根，暂无法识别回踩五日线形态",
        )
    closes = [row.close for row in completed]
    ma5 = moving_average_series(closes, 5)

    # Episodic scan: the first qualifying touch opens an episode; the episode
    # then resolves forward on its own (confirm or invalidation), and once
    # resolved it is emitted immutably -- a later qualifying touch starts a
    # NEW episode instead of re-anchoring (and thereby erasing) the resolved
    # one, which is what keeps every replay consistent with history. While an
    # episode is still open, a further qualifying touch re-anchors that
    # still-provisional episode to the most recent touch (the v1 "most recent
    # qualifying touch" reading, now scoped to the open episode only). A touch
    # bar can never itself be a resolution bar: touching requires a down close
    # near the average, confirming requires an up close, and invalidating
    # requires a close far below it.
    signals: list[PatternShapeSignal] = []
    open_touch: int | None = None
    for index in range(3, len(completed)):
        if ma5[index] is None:
            continue
        if open_touch is not None:
            bounced = closes[index] > closes[index - 1]
            holding_above = closes[index] >= ma5[index]  # type: ignore[operator]
            rising_now = (
                ma5[index - 3] is not None and ma5[index] > ma5[index - 3]  # type: ignore[operator]
            )
            if bounced and holding_above and rising_now:
                signals.append(
                    _build_ma5_signal(
                        completed,
                        ma5,
                        open_touch,
                        PatternShapeStatus.CONFIRMED,
                        index,
                        break_tolerance,
                    )
                )
                open_touch = None
                continue
            if closes[index] < ma5[index] * (1 - break_tolerance):  # type: ignore[operator]
                signals.append(
                    _build_ma5_signal(
                        completed,
                        ma5,
                        open_touch,
                        PatternShapeStatus.INVALIDATED,
                        index,
                        break_tolerance,
                    )
                )
                open_touch = None
                continue
        if ma5[index - 3] is None or ma5[index] <= ma5[index - 3]:  # type: ignore[operator]
            continue
        close = closes[index]
        near = abs(close - ma5[index]) / ma5[index] <= near_tolerance  # type: ignore[operator]
        pulling_back = close < closes[index - 1]
        if near and pulling_back:
            open_touch = index
    if open_touch is not None:
        signals.append(
            _build_ma5_signal(
                completed,
                ma5,
                open_touch,
                PatternShapeStatus.FORMING,
                len(completed) - 1,
                break_tolerance,
            )
        )

    return PatternShapeDetection(
        detector="ma5_pullback",
        minimum_window=_MA5_PULLBACK_MIN_WINDOW,
        sample_size=len(completed),
        quality_status="live",
        missing_reason=None,
        signals=tuple(signals),
    )


def _build_ma5_signal(
    completed: Sequence[OHLCVBar],
    ma5: Sequence[float | None],
    touch_index: int,
    status: PatternShapeStatus,
    event_index: int,
    break_tolerance: float,
) -> PatternShapeSignal:
    if status is PatternShapeStatus.FORMING:
        invalidation = (
            f"收盘跌破五日线 {ma5[touch_index] * (1 - break_tolerance):.2f}"  # type: ignore[operator]
            f"（跌破容忍度 {break_tolerance:.0%}）视为企稳失败"
        )
    elif status is PatternShapeStatus.CONFIRMED:
        confirm_ma5 = ma5[event_index]
        assert confirm_ma5 is not None
        invalidation = f"收盘再次跌破五日线 {confirm_ma5:.2f}，或五日线转跌"
    else:
        break_ma5 = ma5[event_index]
        assert break_ma5 is not None
        invalidation = f"收盘跌破五日线 {break_ma5 * (1 - break_tolerance):.2f}（已发生，企稳失败）"

    explanation = (
        f"五日均线在第 {touch_index} 根K线保持上升，收盘价回踩到均线附近后，"
        "观察后续能否收盘走高并守住均线。"
    )
    summary, detail = _reading_copy(PatternShapeKind.MA5_PULLBACK, status)
    bars_ref_indices = sorted({touch_index, event_index})
    bars_ref = tuple(_bar_ref(completed, index) for index in bars_ref_indices)
    return PatternShapeSignal(
        kind=PatternShapeKind.MA5_PULLBACK,
        name=_KIND_NAME_ZH[PatternShapeKind.MA5_PULLBACK],
        status=status,
        direction=Direction.BULLISH,
        bars=bars_ref,
        anchor=_bar_ref(completed, touch_index),
        event_index=event_index,
        invalidation=invalidation,
        explanation=explanation,
        reading_summary=summary,
        reading_detail=detail,
    )


# ---------------------------------------------------------------------------
# Aggregate entry point
# ---------------------------------------------------------------------------


def detect_pattern_shapes(bars: Sequence[OHLCVBar]) -> tuple[PatternShapeDetection, ...]:
    """Run every shape detector over the same completed-bars-only input."""

    return (
        detect_fractal_patterns(bars),
        detect_double_extreme_patterns(bars),
        detect_head_and_shoulders_patterns(bars),
        detect_ma5_pullback_pattern(bars),
    )
