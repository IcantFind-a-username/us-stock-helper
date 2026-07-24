from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.indicators import ema_series, macd, moving_average, rsi
from us_stock_helper_core.models import Direction, OHLCVBar
from us_stock_helper_core.patterns import (
    PatternKind,
    detect_double_bottom,
    detect_head_and_shoulders,
    detect_ma5_pullback,
    magic_nine,
    three_bar_fractals,
)


BASE_TIME = datetime(2026, 7, 24, 14, tzinfo=UTC)


def bars_from_closes(closes: list[float]) -> tuple[OHLCVBar, ...]:
    rows: list[OHLCVBar] = []
    for index, close in enumerate(closes):
        closed_at = BASE_TIME + timedelta(minutes=5 * index)
        rows.append(
            OHLCVBar(
                symbol="NVDA",
                interval="5m",
                opened_at=closed_at - timedelta(minutes=5),
                closed_at=closed_at,
                available_at=closed_at,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000.0 + index,
            )
        )
    return tuple(rows)


class IndicatorTests(unittest.TestCase):
    def test_moving_average_requires_a_complete_window(self) -> None:
        self.assertEqual(moving_average([1, 2, 3, 4, 5], 5), 3.0)
        self.assertIsNone(moving_average([1, 2, 3, 4], 5))
        with self.assertRaisesRegex(ValueError, "period"):
            moving_average([1, 2], 0)

    def test_ema_uses_only_the_supplied_sequence_in_order(self) -> None:
        self.assertEqual(ema_series([1, 2, 3], 3), (1.0, 1.5, 2.25))

    def test_rsi_handles_one_sided_and_flat_markets_without_division_errors(self) -> None:
        self.assertEqual(rsi(list(range(1, 16))), 100.0)
        self.assertEqual(rsi(list(range(15, 0, -1))), 0.0)
        self.assertEqual(rsi([10.0] * 15), 50.0)
        self.assertIsNone(rsi([1.0, 2.0], 14))

    def test_macd_reports_line_signal_and_histogram_consistently(self) -> None:
        result = macd([float(value) for value in range(1, 41)])
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result.line, 0.0)
        self.assertAlmostEqual(result.histogram, result.line - result.signal, places=12)


class PatternTests(unittest.TestCase):
    def test_magic_nine_is_an_original_close_versus_four_bars_sequence(self) -> None:
        rising = magic_nine([float(value) for value in range(10, 23)])
        falling = magic_nine([float(value) for value in range(23, 10, -1)])

        self.assertIsNotNone(rising)
        self.assertIsNotNone(falling)
        assert rising is not None and falling is not None
        self.assertEqual(
            (
                rising.count,
                rising.completed,
                rising.direction,
                rising.confirmed_at_index,
                rising.algorithm_version,
            ),
            (9, True, Direction.BEARISH, 12, "sequential-close-4-v1"),
        )
        self.assertEqual(falling.direction, Direction.BULLISH)

    def test_three_bar_fractal_waits_for_the_third_bar_to_confirm(self) -> None:
        top = list(bars_from_closes([100.0, 105.0, 101.0]))
        top[1] = OHLCVBar(
            **{
                **{field: getattr(top[1], field) for field in top[1].__dataclass_fields__},
                "high": 110.0,
            }
        )

        signals = three_bar_fractals(top)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].kind, PatternKind.FRACTAL_TOP)
        self.assertEqual(signals[0].confirmed_at_index, 2)

    def test_incomplete_bar_cannot_confirm_a_fractal(self) -> None:
        rows = list(bars_from_closes([100.0, 105.0, 101.0]))
        rows[-1] = OHLCVBar(
            **{
                **{field: getattr(rows[-1], field) for field in rows[-1].__dataclass_fields__},
                "complete": False,
            }
        )
        self.assertEqual(three_bar_fractals(rows), ())

    def test_detects_a_bullish_pullback_near_ma5_only_after_trend_evidence(self) -> None:
        signal = detect_ma5_pullback(
            bars_from_closes([100, 102, 104, 106, 108, 109, 110, 107])
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual((signal.kind, signal.direction), (PatternKind.MA5_PULLBACK, Direction.BULLISH))

    def test_double_bottom_requires_second_low_and_neckline_breakout(self) -> None:
        unconfirmed = detect_double_bottom(
            bars_from_closes([105, 100, 96, 100, 105, 101, 96.5, 100, 104])
        )
        confirmed = detect_double_bottom(
            bars_from_closes([105, 100, 96, 100, 105, 101, 96.5, 100, 108])
        )

        self.assertIsNone(unconfirmed)
        self.assertIsNotNone(confirmed)
        assert confirmed is not None
        self.assertEqual((confirmed.kind, confirmed.direction), (PatternKind.DOUBLE_BOTTOM, Direction.BULLISH))

    def test_head_and_shoulders_requires_neckline_break_confirmation(self) -> None:
        signal = detect_head_and_shoulders(
            bars_from_closes([100, 105, 110, 104, 108, 116, 107, 103, 110, 105, 101, 98])
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(
            (signal.kind, signal.direction, signal.confirmed_at_index),
            (PatternKind.HEAD_AND_SHOULDERS, Direction.BEARISH, 11),
        )


if __name__ == "__main__":
    unittest.main()
