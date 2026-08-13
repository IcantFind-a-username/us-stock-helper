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


if __name__ == "__main__":
    unittest.main()
