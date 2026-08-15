from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from us_stock_helper_core import (
    macd_series,
    moving_average_series,
    rsi_series,
)
from us_stock_helper_market_gateway.snapshot import assemble_stock_snapshot


NOW = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)

# Every series the chart draws, mapped to the indicator entry that owns it.
# The gateway is the only place these may be produced: the app is forbidden
# from deriving indicator paths from its own closes, so a missing entry here
# means an undrawable chart, not a client-side fallback.
SERIES_KEYS: dict[str, tuple[str, ...]] = {
    "ma5": ("series",),
    "ma10": ("series",),
    "ma20": ("series",),
    "ma60": ("series",),
    "rsi": ("series",),
    "macd": ("lineSeries", "signalSeries", "histogramSeries"),
}

METHOD_VERSIONS = {
    "ma5": "sma-5-v1",
    "ma10": "sma-10-v1",
    "ma20": "sma-20-v1",
    "ma60": "sma-60-v1",
    "rsi": "wilder-rsi-14-v1",
    "macd": "macd-12-26-9-v1",
}


def _closes(count: int) -> list[float]:
    """Deterministic and non-monotonic: a rising ramp pins RSI at 100."""

    return [
        100.0 + ((index * 7) % 11) - 5.0 + index * 0.1 for index in range(count)
    ]


def _candle_items(count: int) -> list[dict[str, Any]]:
    first = NOW - timedelta(minutes=5 * (count - 1))
    items: list[dict[str, Any]] = []
    for index, close in enumerate(_closes(count)):
        closed_at = first + timedelta(minutes=5 * index)
        items.append(
            {
                "code": "US.NVDA",
                "timeframe": "5m",
                "timestamp": closed_at.isoformat(),
                "availableAt": closed_at.isoformat(),
                "receivedAt": NOW.isoformat(),
                "priceAdjustment": "forward-adjusted",
                "open": close - 0.25,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1_000.0 + index,
            }
        )
    return items


def _snapshot(count: int) -> dict[str, Any]:
    return assemble_stock_snapshot(
        symbol="NVDA",
        interval="5m",
        decision_cutoff=NOW,
        quote_items=[
            {
                "code": "US.NVDA",
                "price": 173.4,
                "changePercent": 2.7,
                "availableAt": NOW.isoformat(),
            }
        ],
        candle_items=_candle_items(count),
        flow_items=[],
        holding_items=[],
    )


class IndicatorSeriesAlignmentTests(unittest.TestCase):
    def test_every_drawable_series_is_index_aligned_with_completed_candles(
        self,
    ) -> None:
        response = _snapshot(80)
        expected = len(response["completedCandles"])

        self.assertEqual(expected, 80)
        for name, keys in SERIES_KEYS.items():
            entry = response["indicators"][name]
            for key in keys:
                with self.subTest(indicator=name, series=key):
                    self.assertIsInstance(entry[key], list)
                    self.assertEqual(len(entry[key]), expected)
            with self.subTest(indicator=name):
                # The app must not have to infer what the index means.
                self.assertEqual(entry["seriesAlignedTo"], "completedCandles")

    def test_warmup_positions_are_null_rather_than_zero(self) -> None:
        # A zero-filled warm-up draws a false line along the bottom of the
        # chart, which reads as a real value rather than as "not yet defined".
        response = _snapshot(80)
        warmups = {
            ("ma5", "series"): 4,
            ("ma10", "series"): 9,
            ("ma20", "series"): 19,
            ("ma60", "series"): 59,
            ("rsi", "series"): 14,
            ("macd", "lineSeries"): 25,
            ("macd", "signalSeries"): 25,
            ("macd", "histogramSeries"): 25,
        }
        for (name, key), warmup in warmups.items():
            series = response["indicators"][name][key]
            with self.subTest(indicator=name, series=key):
                self.assertEqual(series[:warmup], [None] * warmup)
                self.assertIsNotNone(series[warmup])

    def test_every_series_carrying_indicator_declares_a_method_version(self) -> None:
        response = _snapshot(80)

        for name, method in METHOD_VERSIONS.items():
            with self.subTest(indicator=name):
                self.assertEqual(response["indicators"][name]["methodVersion"], method)

    def test_the_last_series_value_is_the_published_single_value(self) -> None:
        response = _snapshot(80)
        indicators = response["indicators"]

        self.assertEqual(indicators["ma5"]["series"][-1], indicators["ma5"]["value"])
        self.assertEqual(indicators["rsi"]["series"][-1], indicators["rsi"]["value"])
        self.assertEqual(indicators["macd"]["lineSeries"][-1], indicators["macd"]["line"])
        self.assertEqual(
            indicators["macd"]["signalSeries"][-1], indicators["macd"]["signal"]
        )
        self.assertEqual(
            indicators["macd"]["histogramSeries"][-1], indicators["macd"]["histogram"]
        )

    def test_series_match_the_shared_analysis_core_computation(self) -> None:
        # Pins the values to the one implementation the rest of the system
        # scores on; a second copy inside the gateway would drift silently.
        closes = _closes(80)
        indicators = _snapshot(80)["indicators"]
        macd_expected = macd_series(closes, 12, 26, 9)

        for period in (5, 10, 20, 60):
            with self.subTest(period=period):
                self.assertEqual(
                    indicators[f"ma{period}"]["series"],
                    list(moving_average_series(closes, period)),
                )
        self.assertEqual(indicators["rsi"]["series"], list(rsi_series(closes, 14)))
        self.assertEqual(indicators["macd"]["lineSeries"], list(macd_expected.line))
        self.assertEqual(indicators["macd"]["signalSeries"], list(macd_expected.signal))
        self.assertEqual(
            indicators["macd"]["histogramSeries"], list(macd_expected.histogram)
        )

    def test_an_uncomputable_indicator_still_returns_an_aligned_null_series(
        self,
    ) -> None:
        # Twenty closes are short of MACD's 26 and MA60's 60. Dropping the key
        # or shortening the list would make the app guess at the alignment.
        response = _snapshot(20)
        indicators = response["indicators"]

        self.assertEqual(indicators["macd"]["qualityStatus"], "unavailable")
        self.assertEqual(indicators["ma60"]["qualityStatus"], "unavailable")
        self.assertIsNone(indicators["ma60"]["value"])
        for name, keys in SERIES_KEYS.items():
            for key in keys:
                with self.subTest(indicator=name, series=key):
                    self.assertEqual(len(indicators[name][key]), 20)
        self.assertEqual(indicators["macd"]["lineSeries"], [None] * 20)
        self.assertEqual(indicators["ma60"]["series"], [None] * 20)

    def test_a_snapshot_without_candles_carries_empty_aligned_series(self) -> None:
        response = assemble_stock_snapshot(
            symbol="NVDA",
            interval="5m",
            decision_cutoff=NOW,
            quote_items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "changePercent": 2.7,
                    "availableAt": NOW.isoformat(),
                }
            ],
            candle_items=[],
            flow_items=[],
            holding_items=[],
        )

        for name, keys in SERIES_KEYS.items():
            for key in keys:
                with self.subTest(indicator=name, series=key):
                    self.assertEqual(response["indicators"][name][key], [])

    def test_the_added_moving_averages_are_provenance_tracked_like_the_rest(
        self,
    ) -> None:
        response = _snapshot(80)

        methods = [entry["methodVersion"] for entry in response["provenance"]]
        for period in (5, 10, 20, 60):
            with self.subTest(period=period):
                self.assertIn(f"sma-{period}-v1", methods)

    def test_macd_and_rsi_match_an_independently_computed_reference(self) -> None:
        # Values below were produced by a from-scratch EMA/Wilder-RSI loop
        # (not by calling analysis_core) over `_closes(30)`, so this catches a
        # bug shared by both the gateway and analysis_core's own engine — the
        # thing `test_series_match_the_shared_analysis_core_computation` above
        # cannot catch because it compares against that same engine.
        response = _snapshot(30)
        indicators = response["indicators"]

        # MACD's slow EMA needs 26 closes, so index 25 is the first published
        # value; every published index below is pinned to five decimal places.
        expected_macd = {
            25: (1.33237, 1.20766, 0.12472),
            26: (1.34647, 1.23542, 0.11105),
            27: (1.03106, 1.19455, -0.16349),
            28: (1.33857, 1.22335, 0.11522),
            29: (1.25314, 1.22931, 0.02383),
        }
        for index, (line, signal, histogram) in expected_macd.items():
            with self.subTest(index=index):
                self.assertAlmostEqual(
                    indicators["macd"]["lineSeries"][index], line, places=5
                )
                self.assertAlmostEqual(
                    indicators["macd"]["signalSeries"][index], signal, places=5
                )
                self.assertAlmostEqual(
                    indicators["macd"]["histogramSeries"][index], histogram, places=5
                )

        # Wilder's RSI needs period + 1 = 15 closes, so index 14 is first.
        expected_rsi = {
            14: 57.72358,
            15: 54.61538,
            16: 51.62192,
            17: 56.31609,
            18: 53.25910,
            19: 50.31761,
            29: 51.91221,
        }
        for index, value in expected_rsi.items():
            with self.subTest(index=index):
                self.assertAlmostEqual(
                    indicators["rsi"]["series"][index], value, places=5
                )

    def test_a_bar_added_after_the_cutoff_does_not_change_earlier_values(
        self,
    ) -> None:
        # PIT: MACD and RSI are computed from completed bars only, so a bar
        # that closes after every prior bar must never rewrite what the chart
        # already drew for those prior bars. `_candle_items` anchors its last
        # bar at the fixed `NOW`, so raising its count only prepends an
        # earlier bar; a real append needs its own explicit timestamps.
        start = NOW - timedelta(minutes=5 * 30)

        def candles_from(count: int, cutoff: datetime) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            for index, close in enumerate(_closes(count)):
                closed_at = start + timedelta(minutes=5 * index)
                items.append(
                    {
                        "code": "US.NVDA",
                        "timeframe": "5m",
                        "timestamp": closed_at.isoformat(),
                        "availableAt": closed_at.isoformat(),
                        "receivedAt": cutoff.isoformat(),
                        "priceAdjustment": "forward-adjusted",
                        "open": close - 0.25,
                        "high": close + 0.5,
                        "low": close - 0.5,
                        "close": close,
                        "volume": 1_000.0 + index,
                    }
                )
            return items

        def snapshot_with(count: int, cutoff: datetime) -> dict[str, Any]:
            return assemble_stock_snapshot(
                symbol="NVDA",
                interval="5m",
                decision_cutoff=cutoff,
                quote_items=[
                    {
                        "code": "US.NVDA",
                        "price": 173.4,
                        "changePercent": 2.7,
                        "availableAt": cutoff.isoformat(),
                    }
                ],
                candle_items=candles_from(count, cutoff),
                flow_items=[],
                holding_items=[],
            )

        cutoff_30 = start + timedelta(minutes=5 * 29)
        cutoff_31 = start + timedelta(minutes=5 * 30)
        before = snapshot_with(30, cutoff_30)
        after = snapshot_with(31, cutoff_31)

        # The append is a true suffix: bars 0..29 keep the same timestamps.
        self.assertEqual(
            [c["timestamp"] for c in before["completedCandles"]],
            [c["timestamp"] for c in after["completedCandles"][:30]],
        )

        before_macd = before["indicators"]["macd"]
        after_macd = after["indicators"]["macd"]
        before_rsi = before["indicators"]["rsi"]
        after_rsi = after["indicators"]["rsi"]

        self.assertEqual(
            after_macd["lineSeries"][:30], before_macd["lineSeries"]
        )
        self.assertEqual(
            after_macd["signalSeries"][:30], before_macd["signalSeries"]
        )
        self.assertEqual(
            after_macd["histogramSeries"][:30], before_macd["histogramSeries"]
        )
        self.assertEqual(after_rsi["series"][:30], before_rsi["series"])
        # The new bar itself is a genuinely new, defined position.
        self.assertIsNotNone(after_macd["lineSeries"][30])
        self.assertIsNotNone(after_rsi["series"][30])


if __name__ == "__main__":
    unittest.main()
