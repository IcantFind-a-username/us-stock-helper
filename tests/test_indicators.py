import unittest

from us_stock_helper.indicators import (
    CandleSeries,
    get_indicator,
    list_indicators,
    open_dragon_trend,
    td_nine_count,
)


def candles_from_close(close):
    return CandleSeries(
        close=close,
        high=[value + 0.5 for value in close],
        low=[value - 0.5 for value in close],
        volume=[1000 + index * 10 for index, _ in enumerate(close)],
    )


class TdNineCountTests(unittest.TestCase):
    def test_counts_nine_consecutive_higher_comparisons(self):
        candles = candles_from_close(list(range(1, 15)))
        result = td_nine_count(candles)

        self.assertEqual(result.values["bearish_count"][4], 1)
        self.assertEqual(result.values["bearish_count"][12], 9)
        self.assertEqual(len(result.signals), 1)
        self.assertEqual(result.signals[0].index, 12)
        self.assertEqual(result.signals[0].direction, "bearish")

    def test_counts_nine_consecutive_lower_comparisons(self):
        candles = candles_from_close(list(range(20, 5, -1)))
        result = td_nine_count(candles)

        self.assertEqual(result.values["bullish_count"][4], 1)
        self.assertEqual(result.values["bullish_count"][12], 9)
        self.assertEqual(result.signals[0].direction, "bullish")

    def test_equal_close_resets_both_counts(self):
        candles = candles_from_close([10] * 20)
        result = td_nine_count(candles)

        self.assertFalse(any(result.values["bullish_count"]))
        self.assertFalse(any(result.values["bearish_count"]))
        self.assertEqual(result.signals, ())


class NoLookaheadTests(unittest.TestCase):
    def test_td_history_does_not_change_when_future_is_appended(self):
        original = candles_from_close(list(range(1, 15)))
        extended = candles_from_close(list(range(1, 15)) + [1000, -1000])

        original_result = td_nine_count(original)
        extended_result = td_nine_count(extended)

        for key in original_result.values:
            self.assertEqual(
                original_result.values[key],
                extended_result.values[key][: len(original)],
            )

    def test_dragon_history_does_not_change_when_future_is_appended(self):
        close = [100 + index * 0.25 for index in range(90)]
        original = candles_from_close(close)
        extended = candles_from_close(close + [200, 50])

        original_result = open_dragon_trend(original)
        extended_result = open_dragon_trend(extended)

        for key in original_result.values:
            self.assertEqual(
                original_result.values[key],
                extended_result.values[key][: len(original)],
            )


class RegistryAndValidationTests(unittest.TestCase):
    def test_registry_exposes_both_indicators(self):
        self.assertIn("td_nine_count", list_indicators())
        self.assertIn("open_dragon_trend", list_indicators())
        self.assertIs(get_indicator("td_nine_count"), td_nine_count)

    def test_open_dragon_is_not_claimed_as_proprietary_equivalent(self):
        result = open_dragon_trend(
            candles_from_close([100 + index for index in range(80)])
        )
        self.assertFalse(result.metadata.proprietary_equivalent)
        self.assertTrue(result.metadata.sources)

    def test_candle_lengths_must_match(self):
        with self.assertRaises(ValueError):
            CandleSeries(close=[1], high=[2], low=[0], volume=[])


if __name__ == "__main__":
    unittest.main()

