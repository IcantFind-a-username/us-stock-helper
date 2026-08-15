from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.models import OHLCVBar
from us_stock_helper_core.rvol import (
    RVOL_VERSION,
    RelativeVolumeResult,
    SessionBucket,
    time_of_day_relative_volume,
)


def bar(
    day: int,
    hour: int,
    minute: int,
    volume: float,
    *,
    symbol: str = "NVDA",
    interval: str = "5m",
    complete: bool = True,
    available_at: datetime | None = None,
) -> OHLCVBar:
    closed_at = datetime(2026, 7, 20, tzinfo=UTC) + timedelta(days=day)
    closed_at = closed_at.replace(hour=hour, minute=minute)
    return OHLCVBar(
        symbol=symbol,
        interval=interval,
        opened_at=closed_at - timedelta(minutes=5),
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=volume,
        complete=complete,
    )


def bucketer(row: OHLCVBar) -> SessionBucket:
    return SessionBucket(
        session=row.closed_at.date(),
        bucket=(row.closed_at.hour, row.closed_at.minute),
    )


# Three historical sessions (day0..day2) with known cumulative volume curves
# through the 09:40 bucket: 100, 200, 300 -> mean 200. The current session
# (day3) is cut off exactly at its own 09:40 bar with cumulative volume 400,
# so the hand-computed ratio is 400 / 200 = 2.0 exactly.
def three_session_history() -> list[OHLCVBar]:
    return [
        bar(0, 9, 30, 40.0),
        bar(0, 9, 35, 30.0),
        bar(0, 9, 40, 30.0),  # session0 cumulative at 09:40 = 100
        bar(0, 9, 45, 50.0),
        bar(1, 9, 30, 80.0),
        bar(1, 9, 35, 60.0),
        bar(1, 9, 40, 60.0),  # session1 cumulative at 09:40 = 200
        bar(1, 9, 45, 100.0),
        bar(2, 9, 30, 120.0),
        bar(2, 9, 35, 90.0),
        bar(2, 9, 40, 90.0),  # session2 cumulative at 09:40 = 300
        bar(2, 9, 45, 150.0),
    ]


def current_session_at_boundary() -> list[OHLCVBar]:
    return [
        bar(3, 9, 30, 150.0),
        bar(3, 9, 35, 125.0),
        bar(3, 9, 40, 125.0),  # current cumulative at 09:40 = 400
    ]


CUTOFF_AT_BOUNDARY = datetime(2026, 7, 23, 9, 40, tzinfo=UTC)


class RelativeVolumeHandComputedTests(unittest.TestCase):
    def test_ratio_matches_the_hand_computed_value_at_a_bucket_boundary(self) -> None:
        bars = tuple(three_session_history() + current_session_at_boundary())

        result = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        self.assertIsInstance(result, RelativeVolumeResult)
        self.assertEqual(result.quality_status, "live")
        self.assertIsNone(result.missing_reason)
        self.assertEqual(result.current_cumulative_volume, 400.0)
        self.assertEqual(result.historical_mean_cumulative_volume, 200.0)
        self.assertEqual(result.ratio, 2.0)
        self.assertEqual(result.lookback_sessions, 3)
        self.assertEqual(result.sessions_used, 3)
        self.assertEqual(result.buckets_elapsed, 3)
        self.assertEqual(result.method_version, RVOL_VERSION)

    def test_disclosed_lookback_never_silently_shrinks_on_a_live_result(self) -> None:
        bars = tuple(three_session_history() + current_session_at_boundary())

        result = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        # A live ratio always used exactly the disclosed N — never fewer,
        # never a mix of some-sessions-found dressed up as complete.
        self.assertEqual(result.sessions_used, result.lookback_sessions)


class RelativeVolumeEarlySessionTests(unittest.TestCase):
    def test_early_session_is_unavailable_not_a_padded_ratio(self) -> None:
        bars = tuple(three_session_history() + [bar(3, 9, 30, 150.0)])
        cutoff = datetime(2026, 7, 23, 9, 30, tzinfo=UTC)

        result = time_of_day_relative_volume(
            bars,
            cutoff,
            session_bucket=bucketer,
            lookback_sessions=3,
            minimum_buckets_elapsed=2,
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.ratio)
        self.assertIsNone(result.current_cumulative_volume)
        self.assertIsNone(result.historical_mean_cumulative_volume)
        self.assertIn("early session", result.missing_reason or "")
        self.assertEqual(result.buckets_elapsed, 1)


class RelativeVolumeMissingHistoryTests(unittest.TestCase):
    def test_missing_history_is_unavailable_not_a_padded_ratio(self) -> None:
        # Only two prior sessions exist (day1, day2) but three are required.
        two_session_history = [row for row in three_session_history() if row.closed_at.day != 20]
        bars = tuple(two_session_history + current_session_at_boundary())

        result = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIsNone(result.ratio)
        self.assertIsNone(result.current_cumulative_volume)
        self.assertIsNone(result.historical_mean_cumulative_volume)
        self.assertIn("insufficient history", result.missing_reason or "")
        self.assertEqual(result.sessions_used, 2)
        self.assertEqual(result.lookback_sessions, 3)

    def test_a_session_missing_the_exact_bucket_does_not_count_toward_history(self) -> None:
        # session0's 09:40 bar is silently dropped -> only 2 of 3 sessions
        # actually carry the matching bucket, even though 3 sessions exist.
        history = [row for row in three_session_history() if not (row.closed_at.day == 20 and row.closed_at.hour == 9 and row.closed_at.minute == 40)]
        bars = tuple(history + current_session_at_boundary())

        result = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertEqual(result.sessions_used, 2)


class RelativeVolumePITTests(unittest.TestCase):
    def test_a_bar_available_after_the_cutoff_cannot_join_the_baseline(self) -> None:
        history = three_session_history()
        # session2's 09:40 bar becomes knowable only after the cutoff.
        history = [
            row
            if not (row.closed_at.day == 22 and row.closed_at.hour == 9 and row.closed_at.minute == 40)
            else bar(2, 9, 40, 90.0, available_at=row.closed_at + timedelta(days=2))
            for row in history
        ]
        bars = tuple(history + current_session_at_boundary())

        result = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        # Without the late-available bar, session2 no longer has a bucket
        # match, so only 2 of the 3 required sessions remain.
        self.assertEqual(result.quality_status, "unavailable")
        self.assertEqual(result.sessions_used, 2)

    def test_a_later_bar_added_after_the_fact_never_revises_an_earlier_result(self) -> None:
        bars = tuple(three_session_history() + current_session_at_boundary())
        baseline = time_of_day_relative_volume(
            bars,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        extended = bars + (bar(3, 9, 45, 999.0), bar(4, 9, 40, 1.0))
        revised = time_of_day_relative_volume(
            extended,
            CUTOFF_AT_BOUNDARY,
            session_bucket=bucketer,
            lookback_sessions=3,
        )

        self.assertEqual(baseline.ratio, revised.ratio)
        self.assertEqual(baseline.sessions_used, revised.sessions_used)


class RelativeVolumeDegenerateInputTests(unittest.TestCase):
    def test_empty_bars_are_rejected_rather_than_silently_computed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one bar"):
            time_of_day_relative_volume(
                (), CUTOFF_AT_BOUNDARY, session_bucket=bucketer, lookback_sessions=3
            )

    def test_no_bars_knowable_as_of_the_cutoff_is_unavailable(self) -> None:
        bars = tuple(three_session_history() + current_session_at_boundary())
        cutoff = datetime(2026, 7, 19, tzinfo=UTC)

        result = time_of_day_relative_volume(
            bars, cutoff, session_bucket=bucketer, lookback_sessions=3
        )

        self.assertEqual(result.quality_status, "unavailable")
        self.assertIn("no completed bars", result.missing_reason or "")

    def test_mixed_symbols_are_rejected(self) -> None:
        bars = tuple(three_session_history() + [bar(3, 9, 30, 1.0, symbol="AMD")])

        with self.assertRaisesRegex(ValueError, "single symbol"):
            time_of_day_relative_volume(
                bars, CUTOFF_AT_BOUNDARY, session_bucket=bucketer, lookback_sessions=3
            )

    def test_mixed_intervals_are_rejected(self) -> None:
        bars = tuple(three_session_history() + [bar(3, 9, 30, 1.0, interval="1m")])

        with self.assertRaisesRegex(ValueError, "single bar interval"):
            time_of_day_relative_volume(
                bars, CUTOFF_AT_BOUNDARY, session_bucket=bucketer, lookback_sessions=3
            )

    def test_daily_bars_are_rejected(self) -> None:
        # A uniformly daily series passes the single-interval check but must
        # still be rejected: "time of day" is meaningless for day bars.
        bars = tuple(bar(index, 9, 30, 100.0, interval="day") for index in range(4))

        with self.assertRaisesRegex(ValueError, "intraday"):
            time_of_day_relative_volume(
                bars, CUTOFF_AT_BOUNDARY, session_bucket=bucketer, lookback_sessions=3
            )

    def test_incomplete_bars_are_rejected(self) -> None:
        bars = tuple(
            three_session_history()
            + current_session_at_boundary()
            + [bar(3, 9, 45, 1.0, complete=False)]
        )

        with self.assertRaisesRegex(ValueError, "completed"):
            time_of_day_relative_volume(
                bars, CUTOFF_AT_BOUNDARY, session_bucket=bucketer, lookback_sessions=3
            )


if __name__ == "__main__":
    unittest.main()
