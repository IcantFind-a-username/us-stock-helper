from __future__ import annotations

import unittest

from us_stock_helper_core import (
    macd,
    macd_series,
    moving_average,
    moving_average_series,
    rsi,
    rsi_series,
)


def _closes(count: int) -> list[float]:
    """A deterministic non-monotonic series: RSI pinned at 100 hides errors."""

    return [
        100.0 + ((index * 7) % 11) - 5.0 + index * 0.1 for index in range(count)
    ]


class MovingAverageSeriesTests(unittest.TestCase):
    def test_series_is_index_aligned_with_its_input(self) -> None:
        values = _closes(30)

        series = moving_average_series(values, 5)

        self.assertEqual(len(series), len(values))

    def test_warmup_positions_are_absent_rather_than_zero(self) -> None:
        series = moving_average_series(_closes(30), 5)

        self.assertEqual(list(series[:4]), [None, None, None, None])
        self.assertIsNotNone(series[4])

    def test_every_position_equals_the_single_value_over_that_prefix(self) -> None:
        values = _closes(30)

        series = moving_average_series(values, 5)

        for index in range(len(values)):
            with self.subTest(index=index):
                self.assertEqual(series[index], moving_average(values[: index + 1], 5))

    def test_a_series_shorter_than_the_window_is_all_absent(self) -> None:
        series = moving_average_series(_closes(3), 5)

        self.assertEqual(list(series), [None, None, None])

    def test_a_non_positive_period_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "period"):
            moving_average_series(_closes(5), 0)

    def test_window_sum_is_not_left_to_right_rounding_noise(self) -> None:
        # sum() over this exact window order (105.3, 101.4, 97.5, 104.6,
        # 100.7) previously landed on 101.89999999999999 rather than the
        # mathematically exact 101.9 -- a plain left-to-right float
        # accumulation error, not a real cross-platform difference (every
        # summation order but this one already gave 101.9). It broke the
        # market_gateway contract fixture, which pins byte-exact JSON.
        series = moving_average_series(_closes(30), 5)

        self.assertEqual(series[7], 101.9)
        self.assertEqual(series[12], 100.0)


class RsiSeriesTests(unittest.TestCase):
    def test_series_is_index_aligned_with_its_input(self) -> None:
        values = _closes(40)

        self.assertEqual(len(rsi_series(values, 14)), len(values))

    def test_warmup_positions_are_absent_rather_than_zero(self) -> None:
        series = rsi_series(_closes(40), 14)

        # RSI needs period+1 closes for period deltas, so index 14 is first.
        self.assertEqual(list(series[:14]), [None] * 14)
        self.assertIsNotNone(series[14])

    def test_every_position_equals_the_single_value_over_that_prefix(self) -> None:
        values = _closes(40)

        series = rsi_series(values, 14)

        for index in range(len(values)):
            with self.subTest(index=index):
                self.assertEqual(series[index], rsi(values[: index + 1], 14))

    def test_flat_and_one_sided_markets_stay_defined(self) -> None:
        self.assertEqual(rsi_series([10.0] * 15, 14)[-1], 50.0)
        self.assertEqual(rsi_series(list(range(1, 16)), 14)[-1], 100.0)
        self.assertEqual(rsi_series(list(range(15, 0, -1)), 14)[-1], 0.0)


class MacdSeriesTests(unittest.TestCase):
    def test_all_three_lines_are_index_aligned_with_the_input(self) -> None:
        values = _closes(60)

        series = macd_series(values, 12, 26, 9)

        self.assertEqual(len(series.line), len(values))
        self.assertEqual(len(series.signal), len(values))
        self.assertEqual(len(series.histogram), len(values))

    def test_warmup_positions_are_absent_rather_than_zero(self) -> None:
        series = macd_series(_closes(60), 12, 26, 9)

        self.assertEqual(list(series.line[:25]), [None] * 25)
        self.assertEqual(list(series.signal[:25]), [None] * 25)
        self.assertEqual(list(series.histogram[:25]), [None] * 25)
        self.assertIsNotNone(series.line[25])
        self.assertIsNotNone(series.signal[25])
        self.assertIsNotNone(series.histogram[25])

    def test_every_position_equals_the_single_value_over_that_prefix(self) -> None:
        values = _closes(60)

        series = macd_series(values, 12, 26, 9)

        for index in range(len(values)):
            with self.subTest(index=index):
                expected = macd(values[: index + 1], 12, 26, 9)
                if expected is None:
                    self.assertIsNone(series.line[index])
                    self.assertIsNone(series.signal[index])
                    self.assertIsNone(series.histogram[index])
                    continue
                self.assertEqual(series.line[index], expected.line)
                self.assertEqual(series.signal[index], expected.signal)
                self.assertEqual(series.histogram[index], expected.histogram)

    def test_a_series_shorter_than_the_slow_window_is_all_absent(self) -> None:
        series = macd_series(_closes(20), 12, 26, 9)

        self.assertEqual(list(series.line), [None] * 20)
        self.assertEqual(list(series.signal), [None] * 20)
        self.assertEqual(list(series.histogram), [None] * 20)

    def test_an_inverted_period_pair_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "fast_period"):
            macd_series(_closes(60), 26, 12, 9)


if __name__ == "__main__":
    unittest.main()
