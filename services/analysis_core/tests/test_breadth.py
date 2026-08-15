from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.models import OHLCVBar
from us_stock_helper_core.breadth import (
    BREADTH_VERSION,
    AdvanceDeclineResult,
    NewHighLowResult,
    PercentAboveMAResult,
    advance_decline_line,
    new_high_low_differential,
    percent_above_moving_average,
)


BASE_DAY = datetime(2026, 7, 20, 21, tzinfo=UTC)  # NYSE close, UTC
ONE_DAY = timedelta(days=1)


def day(index: int) -> datetime:
    return BASE_DAY + ONE_DAY * index


def daily_bar(
    symbol: str,
    index: int,
    close: float,
    *,
    high: float | None = None,
    low: float | None = None,
    complete: bool = True,
    available_at: datetime | None = None,
) -> OHLCVBar:
    closed_at = day(index)
    opened_at = closed_at - ONE_DAY
    resolved_high = high if high is not None else close * 1.01
    resolved_low = low if low is not None else close * 0.99
    return OHLCVBar(
        symbol=symbol,
        interval="day",
        opened_at=opened_at,
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=close,
        high=max(resolved_high, close),
        low=min(resolved_low, close),
        close=close,
        volume=1_000.0,
        complete=complete,
    )


def series(
    symbol: str,
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> tuple[OHLCVBar, ...]:
    highs = highs or [None] * len(closes)  # type: ignore[list-item]
    lows = lows or [None] * len(closes)  # type: ignore[list-item]
    return tuple(
        daily_bar(symbol, index, close, high=highs[index], low=lows[index])
        for index, close in enumerate(closes)
    )


# --- Hand-computed advance/decline fixture -----------------------------
#
# Day1: A=10 B=10 C=10 D=10 E=10 (baseline, no prior day to compare)
# Day2: A=11(up) B=9(down) C=10(flat) D=12(up) E=8(down)
#   -> advancers=2 decliners=2 unchanged=1 net=0 cumulative=0
# Day3: A=12(up) B=9(flat) C=11(up) D=11(down) E=9(up)
#   -> advancers=3 decliners=1 unchanged=1 net=2 cumulative=2
# Day4: A=11(down) B=10(up) C=11(flat) D=10(down) E=10(up)
#   -> advancers=2 decliners=2 unchanged=1 net=0 cumulative=2
_AD_UNIVERSE = {
    "A": series("A", [10, 11, 12, 11]),
    "B": series("B", [10, 9, 9, 10]),
    "C": series("C", [10, 10, 11, 11]),
    "D": series("D", [10, 12, 11, 10]),
    "E": series("E", [10, 8, 9, 10]),
}


class AdvanceDeclineLineTests(unittest.TestCase):
    def test_hand_computed_advance_decline_line(self) -> None:
        cutoff = day(3)

        result = advance_decline_line(_AD_UNIVERSE, cutoff)

        self.assertIsInstance(result, AdvanceDeclineResult)
        self.assertEqual(result.quality_status, "live")
        self.assertIsNone(result.missing_reason)
        self.assertEqual(result.universe_size, 5)
        self.assertEqual(result.method_version, BREADTH_VERSION)
        self.assertEqual(len(result.points), 3)

        day2, day3, day4 = result.points
        self.assertEqual((day2.advancers, day2.decliners, day2.unchanged), (2, 2, 1))
        self.assertEqual((day2.net, day2.cumulative), (0, 0))

        self.assertEqual((day3.advancers, day3.decliners, day3.unchanged), (3, 1, 1))
        self.assertEqual((day3.net, day3.cumulative), (2, 2))

        self.assertEqual((day4.advancers, day4.decliners, day4.unchanged), (2, 2, 1))
        self.assertEqual((day4.net, day4.cumulative), (0, 2))

    def test_sub_minimum_universe_is_typed_unavailable_not_zero(self) -> None:
        small_universe = {k: _AD_UNIVERSE[k] for k in ("A", "B", "C", "D")}

        result = advance_decline_line(small_universe, day(3), minimum_universe=5)

        self.assertEqual(result.quality_status, "unavailable")
        self.assertEqual(result.points, ())
        self.assertIsNotNone(result.missing_reason)
        self.assertIn("universe", result.missing_reason or "")
        self.assertEqual(result.universe_size, 4)
        # Explicitly not a silent zero: no points to be mistaken for "flat".
        self.assertNotEqual(result.quality_status, "live")

    def test_a_bar_added_after_the_cutoff_cannot_change_yesterdays_breadth(
        self,
    ) -> None:
        cutoff = day(3)
        baseline = advance_decline_line(_AD_UNIVERSE, cutoff)

        future_universe = {
            symbol: bars + (daily_bar(symbol, 4, 999.0),)
            for symbol, bars in _AD_UNIVERSE.items()
        }
        with_future_bar = advance_decline_line(future_universe, cutoff)

        self.assertEqual(with_future_bar.points, baseline.points)
        self.assertEqual(with_future_bar.quality_status, baseline.quality_status)

    def test_a_bar_available_after_the_cutoff_cannot_change_earlier_points(
        self,
    ) -> None:
        cutoff = day(3)
        baseline = advance_decline_line(_AD_UNIVERSE, cutoff)

        # Symbol A's day-4 close is revised/late-reported after the cutoff, so
        # it is invisible to a decision made at the cutoff. It may change (or
        # even remove) the day-4 point once the universe falls below the
        # per-day minimum, but it must never reach backward and change what
        # was already published for day-2 or day-3.
        late_bars = _AD_UNIVERSE["A"][:3] + (
            daily_bar("A", 3, 500.0, available_at=day(3) + timedelta(days=2)),
        )
        late_universe = {**_AD_UNIVERSE, "A": late_bars}

        result = advance_decline_line(late_universe, cutoff)

        self.assertEqual(result.points[:2], baseline.points[:2])


# --- Hand-computed percent-above-MA fixture (period=3) ------------------
#
# A: 10,10,13 -> MA=11.0, close=13 > 11 -> above
# B: 10,10,7  -> MA=9.0,  close=7  < 9  -> below
# C: 10,10,10 -> MA=10.0, close=10 == 10 -> not above
# D: 10,10,16 -> MA=12.0, close=16 > 12 -> above
# E: 10,10,4  -> MA=8.0,  close=4  < 8  -> below
# above = {A, D} -> 2 of 5 eligible -> 40.0%
_MA_UNIVERSE = {
    "A": series("A", [10, 10, 13]),
    "B": series("B", [10, 10, 7]),
    "C": series("C", [10, 10, 10]),
    "D": series("D", [10, 10, 16]),
    "E": series("E", [10, 10, 4]),
}


class PercentAboveMovingAverageTests(unittest.TestCase):
    def test_hand_computed_percent_above_ma(self) -> None:
        cutoff = day(2)

        result = percent_above_moving_average(_MA_UNIVERSE, cutoff, period=3)

        self.assertIsInstance(result, PercentAboveMAResult)
        self.assertEqual(result.quality_status, "live")
        self.assertEqual(result.period, 3)
        self.assertEqual(result.universe_size, 5)
        self.assertEqual(result.eligible_symbols, 5)
        assert result.percent_above is not None
        self.assertAlmostEqual(result.percent_above, 40.0, places=6)
        self.assertEqual(result.method_version, BREADTH_VERSION)

    def test_sub_minimum_universe_is_typed_unavailable(self) -> None:
        small = {k: _MA_UNIVERSE[k] for k in ("A", "B", "C", "D")}

        result = percent_above_moving_average(
            small, day(2), period=3, minimum_universe=5
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.percent_above)
        self.assertIsNotNone(result.missing_reason)

    def test_insufficient_per_symbol_history_is_typed_unavailable(self) -> None:
        # Universe size is nominally 5, but symbol E only has two bars (< period),
        # dropping eligible symbols below the minimum even though the raw
        # universe count would otherwise pass.
        short_history = {**_MA_UNIVERSE, "E": _MA_UNIVERSE["E"][:2]}

        result = percent_above_moving_average(
            short_history, day(2), period=3, minimum_universe=5
        )

        self.assertEqual(result.universe_size, 5)
        self.assertEqual(result.eligible_symbols, 4)
        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.percent_above)

    def test_a_bar_added_after_the_cutoff_cannot_change_yesterdays_breadth(
        self,
    ) -> None:
        cutoff = day(2)
        baseline = percent_above_moving_average(_MA_UNIVERSE, cutoff, period=3)

        future_universe = {
            symbol: bars + (daily_bar(symbol, 3, 1.0),)
            for symbol, bars in _MA_UNIVERSE.items()
        }
        result = percent_above_moving_average(future_universe, cutoff, period=3)

        self.assertEqual(result.percent_above, baseline.percent_above)
        self.assertEqual(result.eligible_symbols, baseline.eligible_symbols)


# --- Hand-computed new-high/new-low fixture (lookback=3) -----------------
#
# A highs [10,11,12] -> latest=12=max -> new high; lows [8,8.5,9] -> latest=9, min=8 -> not new low
# B highs [12,11,9]  -> latest=9, max=12 -> not new high; lows [10,9,7] -> latest=7=min -> new low
# C highs [9,10,9.5] -> latest=9.5, max=10 -> not new high; lows [7,6,6.5] -> latest=6.5, min=6 -> not new low
# D highs [9,9,10]   -> latest=10=max -> new high; lows [8,8,7] -> latest=7=min -> new low
# E highs [10,9,8]   -> latest=8, max=10 -> not new high; lows [5,6,7] -> latest=7, min=5 -> not new low
# new_highs = {A, D} = 2 ; new_lows = {B, D} = 2 ; differential = 0
def _hl_series(symbol: str, highs: list[float], lows: list[float]) -> tuple[OHLCVBar, ...]:
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    return series(symbol, closes, highs=highs, lows=lows)


_HL_UNIVERSE = {
    "A": _hl_series("A", [10, 11, 12], [8, 8.5, 9]),
    "B": _hl_series("B", [12, 11, 9], [10, 9, 7]),
    "C": _hl_series("C", [9, 10, 9.5], [7, 6, 6.5]),
    "D": _hl_series("D", [9, 9, 10], [8, 8, 7]),
    "E": _hl_series("E", [10, 9, 8], [5, 6, 7]),
}


class NewHighLowDifferentialTests(unittest.TestCase):
    def test_hand_computed_new_high_low_differential(self) -> None:
        cutoff = day(2)

        result = new_high_low_differential(_HL_UNIVERSE, cutoff, lookback=3)

        self.assertIsInstance(result, NewHighLowResult)
        self.assertEqual(result.quality_status, "live")
        self.assertEqual(result.lookback, 3)
        self.assertEqual(result.universe_size, 5)
        self.assertEqual(result.eligible_symbols, 5)
        self.assertEqual(result.new_highs, 2)
        self.assertEqual(result.new_lows, 2)
        self.assertEqual(result.differential, 0)
        self.assertEqual(result.method_version, BREADTH_VERSION)

    def test_sub_minimum_universe_is_typed_unavailable(self) -> None:
        small = {k: _HL_UNIVERSE[k] for k in ("A", "B", "C", "D")}

        result = new_high_low_differential(
            small, day(2), lookback=3, minimum_universe=5
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.new_highs)
        self.assertIsNone(result.new_lows)
        self.assertIsNone(result.differential)
        self.assertIsNotNone(result.missing_reason)

    def test_insufficient_per_symbol_history_is_typed_unavailable(self) -> None:
        short_history = {**_HL_UNIVERSE, "E": _HL_UNIVERSE["E"][:2]}

        result = new_high_low_differential(
            short_history, day(2), lookback=3, minimum_universe=5
        )

        self.assertEqual(result.eligible_symbols, 4)
        self.assertEqual(result.quality_status, "unavailable")

    def test_a_bar_added_after_the_cutoff_cannot_change_yesterdays_breadth(
        self,
    ) -> None:
        cutoff = day(2)
        baseline = new_high_low_differential(_HL_UNIVERSE, cutoff, lookback=3)

        future_universe = {
            symbol: bars + (daily_bar(symbol, 3, 1_000.0, high=1_001.0, low=999.0),)
            for symbol, bars in _HL_UNIVERSE.items()
        }
        result = new_high_low_differential(future_universe, cutoff, lookback=3)

        self.assertEqual(result.new_highs, baseline.new_highs)
        self.assertEqual(result.new_lows, baseline.new_lows)
        self.assertEqual(result.differential, baseline.differential)


def _intraday_bar(symbol: str, index: int, close: float) -> OHLCVBar:
    closed_at = day(index)
    return OHLCVBar(
        symbol=symbol,
        interval="5m",
        opened_at=closed_at - timedelta(minutes=5),
        closed_at=closed_at,
        available_at=closed_at,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1_000.0,
    )


class BreadthValidationTests(unittest.TestCase):
    def test_daily_bars_are_required(self) -> None:
        bad_universe = {
            "A": series("A", [10.0] * 5),
            "B": tuple(_intraday_bar("B", index, 10.0) for index in range(5)),
        }
        with self.assertRaisesRegex(ValueError, "daily"):
            advance_decline_line(bad_universe, day(4))

    def test_empty_universe_is_typed_unavailable_not_an_error(self) -> None:
        result = advance_decline_line({}, day(4))

        self.assertEqual(result.quality_status, "unavailable")
        self.assertEqual(result.universe_size, 0)
        self.assertEqual(result.points, ())


if __name__ == "__main__":
    unittest.main()
