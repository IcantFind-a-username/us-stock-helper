from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.indicators import ema_series, warmup_ema_series, wilder_atr
from us_stock_helper_core.models import Direction, OHLCVBar
from us_stock_helper_core.patterns import td_setup
from us_stock_helper_core.trend import DRAGON_TREND_VERSION, TrendState, dragon_trend


BASE_TIME = datetime(2026, 7, 24, 14, tzinfo=UTC)


def bar(
    index: int,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1_000.0,
    complete: bool = True,
) -> OHLCVBar:
    closed_at = BASE_TIME + timedelta(minutes=5 * index)
    return OHLCVBar(
        symbol="NVDA",
        interval="5m",
        opened_at=closed_at - timedelta(minutes=5),
        closed_at=closed_at,
        available_at=closed_at,
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=volume,
        complete=complete,
    )


def rising_bars(count: int, *, start: float = 100.0, step: float = 1.0) -> tuple[OHLCVBar, ...]:
    return tuple(bar(index, start + step * index) for index in range(count))


class WarmupEmaTests(unittest.TestCase):
    def test_warmup_ema_publishes_nothing_before_a_complete_window(self) -> None:
        values = [float(value) for value in range(1, 11)]

        series = warmup_ema_series(values, 5)

        self.assertEqual(len(series), len(values))
        self.assertEqual(series[:4], (None,) * 4)
        self.assertEqual(series[4], 3.0)
        for value in series[4:]:
            self.assertIsNotNone(value)

    def test_warmup_ema_is_seeded_by_the_simple_average_not_the_first_value(self) -> None:
        values = [100.0, 1.0, 1.0, 1.0, 1.0]

        self.assertEqual(warmup_ema_series(values, 5)[4], 20.8)
        self.assertNotEqual(warmup_ema_series(values, 5)[4], ema_series(values, 5)[4])

    def test_warmup_ema_never_revises_a_published_value(self) -> None:
        values = [float(value) for value in range(1, 21)]

        prefix = warmup_ema_series(values[:15], 5)
        full = warmup_ema_series(values, 5)

        self.assertEqual(prefix, full[:15])

    def test_warmup_ema_rejects_short_series_and_invalid_periods(self) -> None:
        self.assertEqual(warmup_ema_series([1.0, 2.0], 5), (None, None))
        with self.assertRaisesRegex(ValueError, "period"):
            warmup_ema_series([1.0], 0)
        with self.assertRaisesRegex(ValueError, "finite"):
            warmup_ema_series([1.0, float("inf")], 2)


class WilderAtrTests(unittest.TestCase):
    def test_atr_publishes_nothing_before_its_first_complete_window(self) -> None:
        bars = rising_bars(20)

        series = wilder_atr(bars, 14)

        self.assertEqual(len(series), 20)
        self.assertEqual(series[:13], (None,) * 13)
        for value in series[13:]:
            self.assertIsNotNone(value)
            assert value is not None
            self.assertGreater(value, 0.0)

    def test_atr_never_revises_a_published_value(self) -> None:
        bars = rising_bars(30)

        self.assertEqual(wilder_atr(bars[:20], 14), wilder_atr(bars, 14)[:20])

    def test_atr_uses_the_previous_close_for_gaps(self) -> None:
        bars = (
            bar(0, 100.0, high=101.0, low=99.0),
            bar(1, 120.0, high=121.0, low=119.0),
        )

        series = wilder_atr(bars, 2)

        self.assertIsNone(series[0])
        # The gap up makes |high - previous close| the true range, not high-low.
        self.assertEqual(series[1], (2.0 + 21.0) / 2)


class DragonTrendTests(unittest.TestCase):
    def test_dragon_trend_stays_warming_up_until_every_input_is_published(self) -> None:
        bars = rising_bars(30)

        result = dragon_trend(bars)

        self.assertEqual(result.algorithm_version, DRAGON_TREND_VERSION)
        self.assertEqual(len(result.states), 30)
        for index in range(54):
            if index < len(result.states):
                self.assertEqual(result.states[index], TrendState.WARMING_UP)
                self.assertIsNone(result.strength[index])
        self.assertEqual(result.signals, ())

    def test_dragon_trend_reports_a_bullish_regime_after_warm_up(self) -> None:
        bars = rising_bars(90)

        result = dragon_trend(bars)

        self.assertEqual(result.states[-1], TrendState.BULLISH)
        self.assertIsNotNone(result.strength[-1])
        assert result.strength[-1] is not None
        self.assertGreater(result.strength[-1], 0.0)
        self.assertLessEqual(result.strength[-1], 3.0)
        self.assertTrue(result.signals)
        self.assertEqual(result.signals[0].direction, Direction.BULLISH)
        self.assertEqual(result.signals[0].algorithm_version, DRAGON_TREND_VERSION)

    def test_dragon_trend_marks_a_falling_market_bearish(self) -> None:
        bars = tuple(bar(index, 300.0 - index) for index in range(90))

        result = dragon_trend(bars)

        self.assertEqual(result.states[-1], TrendState.BEARISH)
        assert result.strength[-1] is not None
        self.assertLess(result.strength[-1], 0.0)
        self.assertGreaterEqual(result.strength[-1], -3.0)

    def test_dragon_trend_is_unavailable_when_the_risk_channel_collapses(self) -> None:
        bars = tuple(bar(index, 100.0, high=100.0, low=100.0) for index in range(90))

        result = dragon_trend(bars)

        self.assertEqual(result.states[-1], TrendState.UNAVAILABLE)
        self.assertIsNone(result.strength[-1])
        self.assertIsNone(result.upper_channel[-1])
        self.assertIsNone(result.lower_channel[-1])

    def test_dragon_trend_never_revises_history_when_new_bars_arrive(self) -> None:
        bars = rising_bars(120)

        prefix = dragon_trend(bars[:90])
        full = dragon_trend(bars)

        self.assertEqual(prefix.states, full.states[:90])
        self.assertEqual(prefix.strength, full.strength[:90])
        self.assertEqual(prefix.upper_channel, full.upper_channel[:90])
        self.assertEqual(
            prefix.signals,
            tuple(signal for signal in full.signals if signal.confirmed_at_index < 90),
        )

    def test_dragon_trend_confirms_transitions_with_relative_volume(self) -> None:
        quiet = tuple(bar(index, 100.0 + index, volume=1_000.0) for index in range(90))
        loud = quiet[:-1] + (
            bar(89, 100.0 + 89, volume=50_000.0),
        )

        quiet_signal = dragon_trend(quiet).signals[-1]
        loud_result = dragon_trend(loud)

        self.assertFalse(quiet_signal.volume_confirmed)
        self.assertTrue(
            all(
                signal.relative_volume is None or signal.relative_volume >= 0.0
                for signal in loud_result.signals
            )
        )

    def test_dragon_trend_rejects_incomplete_bars_and_bad_parameters(self) -> None:
        bars = rising_bars(90)
        with self.assertRaisesRegex(ValueError, "completed"):
            dragon_trend(bars[:-1] + (bar(89, 200.0, complete=False),))
        with self.assertRaisesRegex(ValueError, "fast"):
            dragon_trend(bars, fast_period=55, medium_period=21, slow_period=8)
        with self.assertRaisesRegex(ValueError, "positive"):
            dragon_trend(bars, atr_multiplier=0.0)

    def test_dragon_trend_rejects_mixed_symbols_or_intervals(self) -> None:
        bars = rising_bars(90)
        other_symbol = bars[:-1] + (
            OHLCVBar(
                **{
                    **{
                        name: getattr(bars[-1], name)
                        for name in bars[-1].__dataclass_fields__
                    },
                    "symbol": "TSLA",
                }
            ),
        )

        with self.assertRaisesRegex(ValueError, "symbol"):
            dragon_trend(other_symbol)


class TdSetupTests(unittest.TestCase):
    def test_td_setup_counts_every_bar_and_flags_completion(self) -> None:
        bars = rising_bars(13)

        result = td_setup(bars)

        self.assertEqual(result.bearish_counts[:4], (0, 0, 0, 0))
        self.assertEqual(result.bearish_counts[4:], tuple(range(1, 10)))
        self.assertEqual(result.bullish_counts, (0,) * 13)
        self.assertEqual(len(result.signals), 1)
        self.assertEqual(result.signals[0].confirmed_at_index, 12)
        self.assertTrue(result.signals[0].completed)
        self.assertEqual(result.signals[0].direction, Direction.BEARISH)

    def test_td_setup_reports_the_latest_state_not_the_first_completed_run(self) -> None:
        closes = [100.0 + index for index in range(13)] + [112.5, 111.0, 110.0]
        bars = tuple(bar(index, close) for index, close in enumerate(closes))

        result = td_setup(bars)

        self.assertEqual(len(result.signals), 1)
        self.assertEqual(result.signals[0].confirmed_at_index, 12)
        self.assertIsNotNone(result.latest)
        assert result.latest is not None
        self.assertEqual(result.latest.confirmed_at_index, len(bars) - 1)
        self.assertFalse(result.latest.completed)
        self.assertEqual(result.latest.direction, Direction.BULLISH)

    def test_td_setup_judges_bar_eight_and_nine_perfection(self) -> None:
        def falling(low_offsets: dict[int, float]) -> tuple[OHLCVBar, ...]:
            return tuple(
                bar(
                    index,
                    120.0 - index,
                    low=120.0 - index - low_offsets.get(index, 1.0),
                )
                for index in range(13)
            )

        # The setup runs over indices 4..12, so bars 6 and 7 are indices 9 and
        # 10 and bars 8 and 9 are indices 11 and 12.
        perfected = falling({9: 5.0, 10: 5.0, 11: 9.0, 12: 9.0})
        blunted = falling({9: 5.0, 10: 5.0, 11: 0.5, 12: 0.5})

        self.assertTrue(td_setup(perfected).signals[0].perfected)
        self.assertFalse(td_setup(blunted).signals[0].perfected)

    def test_td_setup_restarts_counting_after_a_completed_run(self) -> None:
        bars = rising_bars(22)

        result = td_setup(bars)

        self.assertEqual(result.bearish_counts[12], 9)
        self.assertEqual(result.bearish_counts[13], 1)
        self.assertEqual(len(result.signals), 2)
        self.assertEqual(
            [signal.confirmed_at_index for signal in result.signals], [12, 21]
        )

    def test_td_setup_never_revises_history_when_new_bars_arrive(self) -> None:
        bars = rising_bars(30)

        prefix = td_setup(bars[:20])
        full = td_setup(bars)

        self.assertEqual(prefix.bearish_counts, full.bearish_counts[:20])
        self.assertEqual(prefix.bullish_counts, full.bullish_counts[:20])
        self.assertEqual(
            prefix.signals,
            tuple(signal for signal in full.signals if signal.confirmed_at_index < 20),
        )

    def test_td_setup_rejects_incomplete_bars_and_invalid_parameters(self) -> None:
        bars = rising_bars(13)
        with self.assertRaisesRegex(ValueError, "completed"):
            td_setup(bars[:-1] + (bar(12, 200.0, complete=False),))
        with self.assertRaisesRegex(ValueError, "lookback"):
            td_setup(bars, lookback=0)
        with self.assertRaisesRegex(ValueError, "setup_length"):
            td_setup(bars, setup_length=1)


if __name__ == "__main__":
    unittest.main()
