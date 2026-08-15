from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from us_stock_helper_market_gateway.snapshot import assemble_stock_snapshot


NOW = datetime(2026, 7, 30, 21, 0, tzinfo=timezone.utc)

# Same shape (and same hand-verified numbers) as the analysis_core fixture:
# a first trough near 96, a bounce to a 104 neckline, a second trough near
# 96.5, then a close that breaks back above the neckline -- a confirmed W底.
_ROWS = [
    (105.0, 106.0, 104.0, 105.0),
    (98.0, 99.0, 96.0, 97.0),
    (98.0, 101.0, 97.0, 100.0),
    (100.0, 104.0, 99.0, 103.0),
    (102.0, 103.0, 98.0, 99.0),
    (97.0, 98.0, 96.5, 97.0),
    (98.0, 101.0, 98.0, 100.0),
    (100.0, 109.0, 99.0, 108.0),
]


def _quote_items() -> list[dict[str, object]]:
    return [
        {
            "code": "US.NVDA",
            "price": 108.0,
            "changePercent": 1.0,
            "availableAt": NOW.isoformat(),
        }
    ]


def _candle_items(rows: list[tuple[float, float, float, float]]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    base = NOW - timedelta(days=len(rows))
    for index, (open_, high, low, close) in enumerate(rows):
        closed_at = base + timedelta(days=index + 1)
        items.append(
            {
                "code": "US.NVDA",
                "timeframe": "day",
                "timestamp": closed_at.isoformat(),
                "availableAt": closed_at.isoformat(),
                "receivedAt": closed_at.isoformat(),
                "priceAdjustment": "forward-adjusted",
                "complete": True,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000.0 + index,
            }
        )
    return items


def _snapshot(rows: list[tuple[float, float, float, float]]) -> dict[str, object]:
    return assemble_stock_snapshot(
        symbol="NVDA",
        interval="day",
        decision_cutoff=NOW,
        quote_items=_quote_items(),
        candle_items=_candle_items(rows),
        flow_items=[],
        holding_items=[],
    )


class PatternShapesSnapshotTests(unittest.TestCase):
    def test_below_every_detector_window_reports_typed_unavailable_detections(self) -> None:
        response = _snapshot(_ROWS[:2])

        entry = response["indicators"]["patternShapes"]
        self.assertEqual(entry["source"], "analysis-core")
        self.assertEqual(entry["methodVersion"], "patterns-shapes-v1")
        # Some completed bars exist, so the entry itself is live -- the
        # per-detector honesty lives inside each detection, not the envelope.
        self.assertEqual(entry["qualityStatus"], "live")
        detectors = {d["detector"] for d in entry["detections"]}
        self.assertEqual(
            detectors, {"fractal", "double_extreme", "head_and_shoulders", "ma5_pullback"}
        )
        for detection in entry["detections"]:
            self.assertEqual(detection["qualityStatus"], "unavailable")
            self.assertEqual(detection["signals"], [])
            self.assertTrue(detection["missingReason"])

    def test_no_candles_reports_the_envelope_itself_as_unavailable(self) -> None:
        response = _snapshot([])

        entry = response["indicators"]["patternShapes"]
        self.assertEqual(entry["qualityStatus"], "unavailable")
        self.assertEqual(entry["detections"], [])

    def test_a_confirmed_double_bottom_is_served_with_its_full_explained_hint(self) -> None:
        response = _snapshot(_ROWS)

        entry = response["indicators"]["patternShapes"]
        self.assertEqual(entry["qualityStatus"], "live")
        double_extreme = next(
            d for d in entry["detections"] if d["detector"] == "double_extreme"
        )
        self.assertEqual(double_extreme["qualityStatus"], "live")
        bottoms = [s for s in double_extreme["signals"] if s["kind"] == "double_bottom"]
        self.assertEqual(len(bottoms), 1)
        signal = bottoms[0]

        self.assertEqual(signal["name"], "W底")
        self.assertEqual(signal["status"], "confirmed")
        self.assertEqual(signal["direction"], "bullish")
        self.assertEqual(signal["invalidation"], "收盘跌破颈线 104.00")
        self.assertEqual(signal["methodVersion"], "patterns-shapes-v1")
        self.assertEqual(signal["eventIndex"], 7)
        self.assertEqual(
            [bar["index"] for bar in signal["bars"]],
            [1, 5, 7],
        )
        self.assertEqual(
            signal["bars"][-1]["closedAt"],
            response["completedCandles"][7]["timestamp"],
        )
        self.assertEqual(signal["reading"]["honesty"], "历史胜率待回测")
        self.assertTrue(signal["reading"]["summary"])
        self.assertTrue(signal["reading"]["detail"])

    def test_pattern_shapes_respect_the_common_decision_cutoff(self) -> None:
        response = _snapshot(_ROWS)

        entry = response["indicators"]["patternShapes"]
        self.assertLessEqual(entry["availableAt"], response["decisionCutoff"])

    def test_pattern_shapes_appear_in_provenance(self) -> None:
        response = _snapshot(_ROWS)

        sources = {child["source"] for child in response["provenance"]}
        self.assertIn("analysis-core", sources)
        pattern_children = [
            child
            for child in response["provenance"]
            if child["methodVersion"] == "patterns-shapes-v1"
        ]
        self.assertEqual(len(pattern_children), 1)


if __name__ == "__main__":
    unittest.main()
