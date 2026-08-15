from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.models import Direction, OHLCVBar
from us_stock_helper_core.patterns_shapes import (
    PATTERN_SHAPE_READING_COPY,
    PATTERNS_SHAPES_VERSION,
    REACHABLE_PATTERN_SHAPE_STATES,
    PatternShapeKind,
    PatternShapeStatus,
    detect_double_extreme_patterns,
    detect_fractal_patterns,
    detect_head_and_shoulders_patterns,
    detect_ma5_pullback_pattern,
    detect_pattern_shapes,
)


BASE_DAY = datetime(2026, 7, 1, tzinfo=UTC)

_BANNED_VERBS = ("买入", "卖出", "加仓", "抄底", "梭哈")


def bars_from_ohlc(
    rows: list[tuple[float, float, float, float]],
    *,
    symbol: str = "NVDA",
    interval: str = "day",
) -> tuple[OHLCVBar, ...]:
    """rows: list of (open, high, low, close). Index i -> BASE_DAY + i days."""

    result: list[OHLCVBar] = []
    for index, (open_, high, low, close) in enumerate(rows):
        closed_at = BASE_DAY + timedelta(days=index)
        result.append(
            OHLCVBar(
                symbol=symbol,
                interval=interval,
                opened_at=closed_at - timedelta(days=1),
                closed_at=closed_at,
                available_at=closed_at,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1_000.0 + index,
            )
        )
    return tuple(result)


def bars_from_closes(closes: list[float]) -> tuple[OHLCVBar, ...]:
    return bars_from_ohlc([(c, c + 1.0, c - 1.0, c) for c in closes])


# ---------------------------------------------------------------------------
# 顶分型 / 底分型 (three-bar fractals)
# ---------------------------------------------------------------------------


class FractalTests(unittest.TestCase):
    def test_below_minimum_window_is_typed_unavailable(self) -> None:
        detection = detect_fractal_patterns(bars_from_closes([100.0, 101.0]))

        self.assertEqual(detection.quality_status, "unavailable")
        self.assertEqual(detection.signals, ())
        self.assertIsNotNone(detection.missing_reason)
        self.assertEqual(detection.minimum_window, 3)
        self.assertEqual(detection.algorithm_version, PATTERNS_SHAPES_VERSION)

    def test_fractal_top_confirms_on_the_third_bar(self) -> None:
        bars = bars_from_ohlc(
            [
                (100.0, 101.0, 99.0, 100.0),
                (100.0, 110.0, 99.0, 104.0),  # middle bar: highest high
                (104.0, 105.0, 100.0, 101.0),
            ]
        )

        detection = detect_fractal_patterns(bars)

        self.assertEqual(detection.quality_status, "live")
        self.assertEqual(len(detection.signals), 1)
        signal = detection.signals[0]
        self.assertEqual(signal.kind, PatternShapeKind.FRACTAL_TOP)
        self.assertEqual(signal.name, "顶分型")
        self.assertEqual(signal.status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(signal.direction, Direction.BEARISH)
        self.assertEqual(signal.anchor.index, 1)
        self.assertEqual(signal.event_index, 2)
        self.assertEqual([b.index for b in signal.bars], [0, 1, 2])
        self.assertEqual(signal.invalidation, "收盘价升破分型高点 110.00")
        self.assertEqual(signal.algorithm_version, PATTERNS_SHAPES_VERSION)
        self.assertEqual(signal.reading_honesty, "历史胜率待回测")
        self.assertTrue(signal.reading_summary)
        self.assertTrue(signal.reading_detail)

    def test_fractal_bottom_confirms_on_the_third_bar(self) -> None:
        bars = bars_from_ohlc(
            [
                (100.0, 101.0, 99.0, 100.0),
                (100.0, 102.0, 90.0, 96.0),  # middle bar: lowest low
                (96.0, 103.0, 95.0, 101.0),
            ]
        )

        detection = detect_fractal_patterns(bars)

        self.assertEqual(len(detection.signals), 1)
        signal = detection.signals[0]
        self.assertEqual(signal.kind, PatternShapeKind.FRACTAL_BOTTOM)
        self.assertEqual(signal.name, "底分型")
        self.assertEqual(signal.status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(signal.direction, Direction.BULLISH)
        self.assertEqual(signal.anchor.index, 1)
        self.assertEqual(signal.invalidation, "收盘价跌破分型低点 90.00")

    def test_incomplete_bar_is_rejected(self) -> None:
        rows = list(
            bars_from_ohlc(
                [
                    (100.0, 101.0, 99.0, 100.0),
                    (100.0, 110.0, 99.0, 104.0),
                    (104.0, 105.0, 100.0, 101.0),
                ]
            )
        )
        fields = {f: getattr(rows[-1], f) for f in rows[-1].__dataclass_fields__}
        fields["complete"] = False
        rows[-1] = OHLCVBar(**fields)

        with self.assertRaises(ValueError):
            detect_fractal_patterns(tuple(rows))


# ---------------------------------------------------------------------------
# W底 / 双头 (double bottom / double top with neckline)
# ---------------------------------------------------------------------------

_DOUBLE_BOTTOM_PREFIX = [
    (105.0, 106.0, 104.0, 105.0),
    (98.0, 99.0, 96.0, 97.0),  # first trough (low 96)
    (98.0, 101.0, 97.0, 100.0),
    (100.0, 104.0, 99.0, 103.0),  # neckline candidate high 104
    (102.0, 103.0, 98.0, 99.0),
    (97.0, 98.0, 96.5, 97.0),  # second trough (low 96.5)
    (98.0, 101.0, 98.0, 100.0),
]


class DoubleBottomTests(unittest.TestCase):
    def test_below_minimum_window_is_typed_unavailable(self) -> None:
        detection = detect_double_extreme_patterns(bars_from_closes([100.0] * 3))

        self.assertEqual(detection.quality_status, "unavailable")
        self.assertEqual(detection.minimum_window, 7)

    def test_forming_before_neckline_or_support_resolves(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX)

        detection = detect_double_extreme_patterns(bars)

        bottoms = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_BOTTOM]
        self.assertEqual(len(bottoms), 1)
        signal = bottoms[0]
        self.assertEqual(signal.status, PatternShapeStatus.FORMING)
        self.assertEqual(signal.direction, Direction.BULLISH)
        self.assertEqual(signal.name, "W底")
        self.assertEqual(signal.anchor.index, 5)
        self.assertIn("96.50", signal.invalidation)

    def test_confirms_on_close_above_the_neckline(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(100.0, 109.0, 99.0, 108.0)])

        detection = detect_double_extreme_patterns(bars)

        bottoms = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_BOTTOM]
        self.assertEqual(len(bottoms), 1)
        signal = bottoms[0]
        self.assertEqual(signal.status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(signal.event_index, 7)
        self.assertEqual(signal.invalidation, "收盘跌破颈线 104.00")

    def test_invalidated_when_support_breaks_before_the_neckline(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(99.0, 100.0, 93.0, 94.0)])

        detection = detect_double_extreme_patterns(bars)

        bottoms = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_BOTTOM]
        self.assertEqual(len(bottoms), 1)
        signal = bottoms[0]
        self.assertEqual(signal.status, PatternShapeStatus.INVALIDATED)
        self.assertEqual(signal.event_index, 7)

    def test_boundary_close_exactly_on_the_neckline_does_not_confirm(self) -> None:
        # Mutation-check target: flipping the confirm comparison from strictly
        # greater-than to greater-or-equal would flip this assertion.
        bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(100.0, 104.0, 99.0, 104.0)])

        detection = detect_double_extreme_patterns(bars)

        bottoms = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_BOTTOM]
        self.assertEqual(len(bottoms), 1)
        self.assertEqual(bottoms[0].status, PatternShapeStatus.FORMING)

    def test_pit_appending_a_future_bar_never_changes_the_confirmed_signal(self) -> None:
        confirmed_bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(100.0, 109.0, 99.0, 108.0)])
        extended_bars = bars_from_ohlc(
            _DOUBLE_BOTTOM_PREFIX
            + [(100.0, 109.0, 99.0, 108.0), (108.0, 110.0, 106.0, 109.0)]
        )

        before = detect_double_extreme_patterns(confirmed_bars)
        after = detect_double_extreme_patterns(extended_bars)

        before_confirmed = [
            s
            for s in before.signals
            if s.kind is PatternShapeKind.DOUBLE_BOTTOM and s.status == PatternShapeStatus.CONFIRMED
        ]
        after_confirmed = [
            s
            for s in after.signals
            if s.kind is PatternShapeKind.DOUBLE_BOTTOM and s.status == PatternShapeStatus.CONFIRMED
        ]
        self.assertEqual(len(before_confirmed), 1)
        self.assertEqual(len(after_confirmed), 1)
        self.assertEqual(before_confirmed[0], after_confirmed[0])


_DOUBLE_TOP_PREFIX = [
    (95.0, 96.0, 94.0, 95.0),
    (97.0, 104.0, 96.0, 103.0),  # first peak (high 104)
    (102.0, 103.0, 97.0, 98.0),
    (97.0, 98.0, 93.0, 95.0),  # neckline candidate low 93
    (96.0, 97.0, 95.0, 96.0),
    (97.0, 103.5, 96.0, 99.0),  # second peak (high 103.5)
    (98.0, 99.0, 95.0, 97.0),
]


class DoubleTopTests(unittest.TestCase):
    def test_forming_before_neckline_or_resistance_resolves(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_TOP_PREFIX)

        detection = detect_double_extreme_patterns(bars)

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_TOP]
        self.assertEqual(len(tops), 1)
        signal = tops[0]
        self.assertEqual(signal.status, PatternShapeStatus.FORMING)
        self.assertEqual(signal.direction, Direction.BEARISH)
        self.assertEqual(signal.name, "双头")

    def test_confirms_on_close_below_the_neckline(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_TOP_PREFIX + [(96.0, 97.0, 88.0, 90.0)])

        detection = detect_double_extreme_patterns(bars)

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(tops[0].invalidation, "收盘升破颈线 93.00")

    def test_invalidated_when_resistance_breaks_before_the_neckline(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_TOP_PREFIX + [(99.0, 106.0, 98.0, 105.0)])

        detection = detect_double_extreme_patterns(bars)

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.DOUBLE_TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].status, PatternShapeStatus.INVALIDATED)


# ---------------------------------------------------------------------------
# 头肩顶 / 头肩底
# ---------------------------------------------------------------------------

_HS_TOP_FORMING = [100.0, 105.0, 110.0, 104.0, 108.0, 116.0, 107.0, 103.0, 110.0, 105.0]
_HS_TOP_CONFIRMED = _HS_TOP_FORMING + [101.0]
_HS_TOP_INVALIDATED = _HS_TOP_FORMING + [120.0]


class HeadAndShouldersTests(unittest.TestCase):
    def test_below_minimum_window_is_typed_unavailable(self) -> None:
        detection = detect_head_and_shoulders_patterns(bars_from_closes([100.0] * 4))

        self.assertEqual(detection.quality_status, "unavailable")
        self.assertEqual(detection.minimum_window, 8)

    def test_top_is_forming_before_neckline_or_head_breaks(self) -> None:
        detection = detect_head_and_shoulders_patterns(bars_from_closes(_HS_TOP_FORMING))

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.HEAD_SHOULDERS_TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].status, PatternShapeStatus.FORMING)
        self.assertEqual(tops[0].direction, Direction.BEARISH)
        self.assertEqual(tops[0].name, "头肩顶")

    def test_top_confirms_on_close_below_the_neckline(self) -> None:
        detection = detect_head_and_shoulders_patterns(bars_from_closes(_HS_TOP_CONFIRMED))

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.HEAD_SHOULDERS_TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(tops[0].invalidation, "收盘升破颈线 102.50")

    def test_top_invalidated_when_price_reclaims_the_head(self) -> None:
        detection = detect_head_and_shoulders_patterns(bars_from_closes(_HS_TOP_INVALIDATED))

        tops = [s for s in detection.signals if s.kind is PatternShapeKind.HEAD_SHOULDERS_TOP]
        self.assertEqual(len(tops), 1)
        self.assertEqual(tops[0].status, PatternShapeStatus.INVALIDATED)

    def test_bottom_confirms_on_close_above_the_neckline(self) -> None:
        closes = [100.0 - (c - 100.0) for c in _HS_TOP_CONFIRMED]
        detection = detect_head_and_shoulders_patterns(bars_from_closes(closes))

        bottoms = [
            s for s in detection.signals if s.kind is PatternShapeKind.HEAD_SHOULDERS_BOTTOM
        ]
        self.assertEqual(len(bottoms), 1)
        self.assertEqual(bottoms[0].status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(bottoms[0].direction, Direction.BULLISH)
        self.assertEqual(bottoms[0].name, "头肩底")


# ---------------------------------------------------------------------------
# 回踩五日线企稳 (回眸一笑)
# ---------------------------------------------------------------------------

_MA5_PREFIX = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 109.0]


class Ma5PullbackTests(unittest.TestCase):
    def test_below_minimum_window_is_typed_unavailable(self) -> None:
        detection = detect_ma5_pullback_pattern(bars_from_closes([100.0] * 5))

        self.assertEqual(detection.quality_status, "unavailable")
        self.assertEqual(detection.minimum_window, 8)

    def test_forming_when_touch_has_not_yet_resolved(self) -> None:
        detection = detect_ma5_pullback_pattern(bars_from_closes(_MA5_PREFIX))

        self.assertEqual(len(detection.signals), 1)
        signal = detection.signals[0]
        self.assertEqual(signal.kind, PatternShapeKind.MA5_PULLBACK)
        self.assertEqual(signal.status, PatternShapeStatus.FORMING)
        self.assertEqual(signal.direction, Direction.BULLISH)
        self.assertEqual(signal.anchor.index, 7)

    def test_confirms_on_a_close_back_above_a_rising_ma5(self) -> None:
        detection = detect_ma5_pullback_pattern(bars_from_closes(_MA5_PREFIX + [113.0]))

        self.assertEqual(len(detection.signals), 1)
        signal = detection.signals[0]
        self.assertEqual(signal.status, PatternShapeStatus.CONFIRMED)
        self.assertEqual(signal.event_index, 8)

    def test_invalidated_on_a_clean_breakdown_through_ma5(self) -> None:
        detection = detect_ma5_pullback_pattern(bars_from_closes(_MA5_PREFIX + [100.0]))

        self.assertEqual(len(detection.signals), 1)
        signal = detection.signals[0]
        self.assertEqual(signal.status, PatternShapeStatus.INVALIDATED)
        self.assertEqual(signal.event_index, 8)


# ---------------------------------------------------------------------------
# Aggregate entry point, PIT, and plain-language reading copy
# ---------------------------------------------------------------------------


class DetectPatternShapesTests(unittest.TestCase):
    def test_runs_every_detector_and_tags_the_shared_version(self) -> None:
        detections = detect_pattern_shapes(bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX))

        detectors = {d.detector for d in detections}
        self.assertEqual(
            detectors, {"fractal", "double_extreme", "head_and_shoulders", "ma5_pullback"}
        )
        for detection in detections:
            self.assertEqual(detection.algorithm_version, PATTERNS_SHAPES_VERSION)

    def test_pit_no_lookahead_prefix_matches_a_truncated_recompute(self) -> None:
        full_bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(100.0, 109.0, 99.0, 108.0)])
        prefix_bars = full_bars[:7]

        prefix_result = detect_double_extreme_patterns(prefix_bars)
        full_result = detect_double_extreme_patterns(full_bars)

        prefix_forming = [
            s
            for s in prefix_result.signals
            if s.kind is PatternShapeKind.DOUBLE_BOTTOM
        ]
        full_confirmed = [
            s
            for s in full_result.signals
            if s.kind is PatternShapeKind.DOUBLE_BOTTOM
            and s.status == PatternShapeStatus.CONFIRMED
        ]
        # Truncated at bar 7 (before the neckline break is knowable), the read
        # is honestly "forming" -- it must not have leaked the future close.
        self.assertEqual(prefix_forming[0].status, PatternShapeStatus.FORMING)
        self.assertEqual(len(full_confirmed), 1)


class ReadingCopyCompletenessTests(unittest.TestCase):
    def test_every_reachable_state_has_reading_copy(self) -> None:
        for state in REACHABLE_PATTERN_SHAPE_STATES:
            self.assertIn(state, PATTERN_SHAPE_READING_COPY)

    def test_no_reading_copy_uses_a_banned_action_verb(self) -> None:
        for (kind, status), (summary, detail) in PATTERN_SHAPE_READING_COPY.items():
            for verb in _BANNED_VERBS:
                self.assertNotIn(
                    verb, summary, f"{kind}/{status} summary used banned verb {verb}"
                )
                self.assertNotIn(
                    verb, detail, f"{kind}/{status} detail used banned verb {verb}"
                )

    def test_every_reading_carries_the_backtest_honesty_line(self) -> None:
        bars = bars_from_ohlc(_DOUBLE_BOTTOM_PREFIX + [(100.0, 109.0, 99.0, 108.0)])
        detection = detect_double_extreme_patterns(bars)
        for signal in detection.signals:
            self.assertEqual(signal.reading_honesty, "历史胜率待回测")


if __name__ == "__main__":
    unittest.main()
