from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import math
import unittest

from us_stock_helper_core.models import (
    CapitalFlowPoint,
    OHLCVBar,
    ParticipationBar,
)
from us_stock_helper_core.participation import build_participation_bars


CUTOFF = datetime(2026, 7, 24, 16, tzinfo=UTC)
ONE_MINUTE = timedelta(minutes=1)
ONE_SECOND = timedelta(seconds=1)


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 24, hour, minute, tzinfo=UTC)


def flow(
    hour: int,
    minute: int,
    *,
    super_net: float = 10.0,
    big_net: float = 20.0,
    mid_net: float = 30.0,
    small_net: float = 40.0,
    symbol: str = "NVDA",
    session: str = "regular",
    available_at: datetime | None = None,
) -> CapitalFlowPoint:
    timestamp = at(hour, minute)
    return CapitalFlowPoint(
        symbol=symbol,
        timestamp=timestamp,
        available_at=available_at or timestamp,
        total_net=super_net + big_net + mid_net + small_net,
        super_net=super_net,
        big_net=big_net,
        mid_net=mid_net,
        small_net=small_net,
        session=session,
    )


def candle(
    opened_at: datetime,
    closed_at: datetime,
    *,
    interval: str = "5m",
    symbol: str = "NVDA",
    complete: bool = True,
    available_at: datetime | None = None,
) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        interval=interval,
        opened_at=opened_at,
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000.0,
        complete=complete,
    )


class CapitalFlowValidationTests(unittest.TestCase):
    def test_models_require_utc_finite_values_and_consistent_availability(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            flow(9, 30, available_at=datetime(2026, 7, 24, 9, 30))
        with self.assertRaisesRegex(ValueError, "finite"):
            flow(9, 30, super_net=math.nan)
        with self.assertRaisesRegex(ValueError, "available_at"):
            flow(9, 30, available_at=at(9, 29))

    def test_rejects_future_duplicate_and_inconsistent_flow_rows(self) -> None:
        point0 = flow(9, 30)
        point1 = flow(9, 31, super_net=13.0, big_net=18.0, mid_net=34.0, small_net=42.0)
        bars = (candle(at(9, 30), at(9, 32), interval="2m"),)

        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            build_participation_bars((point0, point0), bars, CUTOFF)
        with self.assertRaisesRegex(ValueError, "decision cutoff"):
            build_participation_bars(
                (replace(point1, available_at=CUTOFF + ONE_SECOND),), bars, CUTOFF
            )
        with self.assertRaisesRegex(ValueError, "bucket sum"):
            build_participation_bars((replace(point1, total_net=999.0),), bars, CUTOFF)

    def test_rejects_cross_symbol_and_noncompleted_candle_inputs(self) -> None:
        point = flow(9, 30)
        with self.assertRaisesRegex(ValueError, "symbol"):
            build_participation_bars(
                (point,), (candle(at(9, 29), at(9, 30), symbol="TSLA"),), CUTOFF
            )
        with self.assertRaisesRegex(ValueError, "completed"):
            build_participation_bars(
                (point,), (candle(at(9, 29), at(9, 30), complete=False),), CUTOFF
            )

    def test_participation_bar_enforces_available_or_unavailable_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "unavailable"):
            ParticipationBar(
                symbol="NVDA",
                interval="5m",
                closed_at=at(9, 35),
                available_at=at(9, 35),
                main_share=0.5,
                retail_share=0.5,
                main_activity=2.0,
                retail_activity=2.0,
                net_flow=0.0,
                coverage=1.0,
                quality_status="unavailable",
                missing_reason=None,
                method_version="order-size-activity-share-v1",
            )
        with self.assertRaisesRegex(ValueError, "sum"):
            ParticipationBar(
                symbol="NVDA",
                interval="5m",
                closed_at=at(9, 35),
                available_at=at(9, 35),
                main_share=0.6,
                retail_share=0.5,
                main_activity=2.0,
                retail_activity=2.0,
                net_flow=0.0,
                coverage=1.0,
                quality_status="live",
                missing_reason=None,
                method_version="order-size-activity-share-v1",
            )


class ParticipationAggregationTests(unittest.TestCase):
    def test_aggregates_cumulative_order_size_activity_within_one_session(self) -> None:
        points = (
            flow(9, 30, super_net=10.0, big_net=20.0, mid_net=30.0, small_net=40.0),
            flow(9, 31, super_net=13.0, big_net=18.0, mid_net=34.0, small_net=42.0),
            flow(9, 32, super_net=17.0, big_net=24.0, mid_net=32.0, small_net=47.0),
        )

        result = build_participation_bars(
            points, (candle(at(9, 30), at(9, 32), interval="2m"),), CUTOFF
        )

        self.assertEqual(len(result), 1)
        bar = result[0]
        self.assertEqual(bar.quality_status, "live")
        self.assertAlmostEqual(bar.main_activity, 15.0)
        self.assertAlmostEqual(bar.retail_activity, 13.0)
        self.assertAlmostEqual(bar.main_share, 15.0 / 28.0)
        self.assertAlmostEqual(bar.retail_share, 13.0 / 28.0)
        self.assertAlmostEqual((bar.main_share or 0.0) + (bar.retail_share or 0.0), 1.0)
        self.assertAlmostEqual(bar.net_flow, 20.0)
        self.assertEqual(bar.coverage, 1.0)
        self.assertEqual(bar.method_version, "order-size-activity-share-v1")

    def test_first_cumulative_point_cannot_create_a_bar(self) -> None:
        result = build_participation_bars(
            (flow(9, 30),), (candle(at(9, 29), at(9, 30), interval="1m"),), CUTOFF
        )

        self.assertEqual(result[0].quality_status, "unavailable")
        self.assertIsNone(result[0].main_share)
        self.assertIn("coverage", result[0].missing_reason or "")
        self.assertEqual(result[0].coverage, 0.0)

    def test_zero_activity_denominator_is_unavailable(self) -> None:
        result = build_participation_bars(
            (flow(9, 30), flow(9, 31)),
            (candle(at(9, 30), at(9, 31), interval="1m"),),
            CUTOFF,
        )

        self.assertEqual(result[0].quality_status, "unavailable")
        self.assertIn("zero", result[0].missing_reason or "")
        self.assertEqual(result[0].coverage, 1.0)

    def test_missing_expected_minute_makes_bar_unavailable_without_interpolation(self) -> None:
        result = build_participation_bars(
            (flow(9, 30), flow(9, 31), flow(9, 33)),
            (candle(at(9, 30), at(9, 33), interval="3m"),),
            CUTOFF,
        )

        self.assertEqual(result[0].quality_status, "unavailable")
        self.assertIn("coverage", result[0].missing_reason or "")
        self.assertAlmostEqual(result[0].coverage, 1.0 / 3.0)

    def test_session_change_never_creates_a_cross_session_delta(self) -> None:
        result = build_participation_bars(
            (flow(9, 30), flow(9, 31), flow(9, 32, session="after-hours")),
            (candle(at(9, 30), at(9, 32), interval="2m"),),
            CUTOFF,
        )

        self.assertEqual(result[0].quality_status, "unavailable")
        self.assertIn("session", result[0].missing_reason or "")
        self.assertEqual(result[0].coverage, 0.5)

    def test_day_and_week_bars_are_explicitly_unavailable_in_v1(self) -> None:
        points = (flow(9, 30), flow(9, 31, super_net=11.0))
        bars = (
            candle(at(9, 30), at(9, 31), interval="day"),
            candle(at(9, 30), at(9, 31), interval="week"),
        )

        result = build_participation_bars(points, bars, CUTOFF)

        self.assertEqual([bar.quality_status for bar in result], ["unavailable", "unavailable"])
        self.assertTrue(all("unsupported" in (bar.missing_reason or "") for bar in result))


if __name__ == "__main__":
    unittest.main()
