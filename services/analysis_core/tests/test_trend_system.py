from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.indicators import ema_series, warmup_ema_series, wilder_atr
from us_stock_helper_core.models import Direction, OHLCVBar
from us_stock_helper_core.patterns import magic_nine, td_setup
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
        # A series that only ever rises was never anything but bullish once it
        # became measurable, so there is no regime change to report.
        self.assertEqual(result.signals, ())

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
        # A downtrend that turns up, so the transition lands on a known bar and
        # the volume on that exact bar decides confirmation.
        closes = [200.0 - index for index in range(90)] + [
            111.0 + index * 4.0 for index in range(60)
        ]

        def build(turn_volume: float, turn_index: int) -> tuple[OHLCVBar, ...]:
            return tuple(
                bar(
                    index,
                    close,
                    volume=turn_volume if index == turn_index else 1_000.0,
                )
                for index, close in enumerate(closes)
            )

        quiet = dragon_trend(build(1_000.0, -1))
        turn_index = next(
            signal.confirmed_at_index
            for signal in quiet.signals
            if signal.direction is Direction.BULLISH
        )
        loud = dragon_trend(build(50_000.0, turn_index))
        quiet_turn = [
            signal
            for signal in quiet.signals
            if signal.direction is Direction.BULLISH
        ]
        loud_turn = [
            signal for signal in loud.signals if signal.direction is Direction.BULLISH
        ]

        self.assertTrue(quiet_turn)
        self.assertTrue(loud_turn)
        self.assertFalse(quiet_turn[-1].volume_confirmed)
        self.assertTrue(loud_turn[-1].volume_confirmed)
        assert loud_turn[-1].relative_volume is not None
        self.assertGreater(loud_turn[-1].relative_volume, 1.2)

    def test_relative_volume_compares_against_prior_bars_only(self) -> None:
        # The bar's own volume must not sit in its own baseline: an exponential
        # average that has already absorbed a fifty-fold spike reports it as
        # roughly nine-fold, understating exactly the event being measured.
        closes = [200.0 - index for index in range(90)] + [
            111.0 + index * 4.0 for index in range(60)
        ]

        def build(turn_volume: float, turn_index: int) -> tuple[OHLCVBar, ...]:
            return tuple(
                bar(index, close, volume=turn_volume if index == turn_index else 1_000.0)
                for index, close in enumerate(closes)
            )

        turn_index = next(
            signal.confirmed_at_index
            for signal in dragon_trend(build(1_000.0, -1)).signals
            if signal.direction is Direction.BULLISH
        )
        signal = next(
            item
            for item in dragon_trend(build(50_000.0, turn_index)).signals
            if item.confirmed_at_index == turn_index
        )

        assert signal.relative_volume is not None
        self.assertAlmostEqual(signal.relative_volume, 50.0, places=6)

    def test_the_first_measurable_bar_is_not_reported_as_a_transition(self) -> None:
        # A transition means the regime changed. At the first bar where a
        # regime can be computed at all there is no earlier regime to change
        # from, so calling it a transition invents information — and makes the
        # reported position depend on how many bars the caller happened to pass.
        bars = rising_bars(150)

        full = dragon_trend(bars)
        trimmed = dragon_trend(bars[30:])

        self.assertEqual(
            [signal.confirmed_at_index for signal in full.signals],
            [signal.confirmed_at_index + 30 for signal in trimmed.signals],
        )
        first_measurable = next(
            index
            for index, state in enumerate(full.states)
            if state is not TrendState.WARMING_UP
        )
        self.assertNotIn(
            first_measurable,
            [signal.confirmed_at_index for signal in full.signals],
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

    def test_magic_nine_does_not_contradict_td_setup_on_perfection(self) -> None:
        # Both describe the same rule; a close-only summary cannot see highs
        # and lows, so it must not claim a perfection verdict either way.
        def falling(low_offsets: dict[int, float]) -> tuple[OHLCVBar, ...]:
            return tuple(
                bar(index, 120.0 - index, low=120.0 - index - low_offsets.get(index, 1.0))
                for index in range(13)
            )

        bars = falling({9: 5.0, 10: 5.0, 11: 9.0, 12: 9.0})
        setup = td_setup(bars)
        summary = magic_nine([row.close for row in bars])

        self.assertTrue(setup.signals[0].perfected)
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.count, setup.signals[0].count)
        self.assertEqual(summary.direction, setup.signals[0].direction)
        self.assertIsNone(summary.perfected)

    def test_td_setup_reports_perfection_only_where_it_checked(self) -> None:
        bars = rising_bars(13)

        # A non-standard setup length has no defined bar 6/7 vs 8/9 comparison,
        # so publishing False would present "not checked" as "checked and not
        # perfected".
        short_setup = td_setup(bars, setup_length=5)

        self.assertTrue(short_setup.signals)
        for signal in short_setup.signals:
            self.assertIsNone(signal.perfected)

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


class MethodologyDocumentationTests(unittest.TestCase):
    def test_the_published_volume_baseline_matches_the_code(self) -> None:
        from pathlib import Path

        doc = (
            Path(__file__).resolve().parents[3] / "docs/indicator-methodology.md"
        ).read_text(encoding="utf-8")

        # The document is the project's public algorithm spec; a claim it makes
        # about the baseline has to be the baseline the code actually uses.
        self.assertIn("simple\n  average of the twenty bars *before* it", doc)
        self.assertNotIn("Relative volume against SMA 20", doc)
