from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.request import Request


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPOSITORY_ROOT / "services/market_gateway/scripts/smoke_real_snapshot.py"
)
FIXTURE = (
    REPOSITORY_ROOT
    / "services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json"
)
SPEC = importlib.util.spec_from_file_location("smoke_real_snapshot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


def valid_snapshot() -> dict[str, Any]:
    cutoff = "2026-07-25T04:00:05Z"
    first_close = "2026-07-25T03:55:00Z"
    second_close = "2026-07-25T04:00:00Z"
    metadata = {
        "source": "analysis-core",
        "asOf": second_close,
        "availableAt": cutoff,
        "qualityStatus": "live",
    }
    return {
        "schemaVersion": "2",
        "source": "moomoo",
        "sourceStatus": "live",
        "symbol": "NVDA",
        "interval": "5m",
        "decisionCutoff": cutoff,
        "quote": {
            "price": 172.8,
            "changePercent": 1.2,
            "source": "moomoo",
            "asOf": "2026-07-25T04:00:04Z",
            "availableAt": "2026-07-25T04:00:04Z",
            "methodVersion": "provider-quote-v1",
            "qualityStatus": "live",
        },
        "completedCandles": [
            {
                "timestamp": first_close,
                "complete": True,
                "open": 171.0,
                "high": 172.0,
                "low": 170.5,
                "close": 171.7,
                "volume": 1000.0,
                "source": "moomoo",
                "asOf": first_close,
                "availableAt": "2026-07-25T03:55:01Z",
                "methodVersion": "provider-completed-candle-v1",
                "qualityStatus": "live",
            },
            {
                "timestamp": second_close,
                "complete": True,
                "open": 171.7,
                "high": 173.0,
                "low": 171.5,
                "close": 172.8,
                "volume": 1200.0,
                "source": "moomoo",
                "asOf": second_close,
                "availableAt": "2026-07-25T04:00:01Z",
                "methodVersion": "provider-completed-candle-v1",
                "qualityStatus": "live",
            },
        ],
        "participationBars": [
            {
                "closedAt": first_close,
                "mainShare": None,
                "retailShare": None,
                "mainActivity": None,
                "retailActivity": None,
                "netFlow": None,
                "coverage": 0.0,
                "source": "moomoo",
                "asOf": first_close,
                "availableAt": "2026-07-25T03:55:01Z",
                "methodVersion": "order-size-activity-share-v1",
                "qualityStatus": "unavailable",
                "missingReason": "capital flow unavailable",
            },
            {
                "closedAt": second_close,
                "mainShare": 0.6,
                "retailShare": 0.4,
                "mainActivity": 60.0,
                "retailActivity": 40.0,
                "netFlow": 5.0,
                "coverage": 1.0,
                "source": "moomoo",
                "asOf": second_close,
                "availableAt": "2026-07-25T04:00:01Z",
                "methodVersion": "order-size-activity-share-v1",
                "qualityStatus": "live",
                "missingReason": None,
            },
        ],
        "indicators": {
            "ma5": {
                **metadata,
                "value": 171.5,
                "methodVersion": "sma-5-v1",
            },
            "rsi": {
                **metadata,
                "value": 55.0,
                "methodVersion": "wilder-rsi-14-v1",
            },
            "macd": {
                **metadata,
                "line": 0.3,
                "signal": 0.2,
                "histogram": 0.1,
                "methodVersion": "macd-12-26-9-v1",
            },
            "magicNine": {
                **metadata,
                "direction": "bullish",
                "count": 2,
                "completed": False,
                "confirmedAtIndex": None,
                "methodVersion": "sequential-close-4-v1",
            },
        },
        "institutionalHoldings": [],
        "provenance": [
            {
                "source": "moomoo",
                "asOf": second_close,
                "availableAt": "2026-07-25T04:00:01Z",
                "methodVersion": "provider-completed-candle-v1",
                "qualityStatus": "live",
            }
        ],
        "warnings": [],
    }


class JsonResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "JsonResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class SmokeRealSnapshotTests(unittest.TestCase):
    def run_fixture(self, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "snapshot.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--fixture", str(fixture)],
                cwd=REPOSITORY_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_accepts_a_strict_cutoff_consistent_replay(self) -> None:
        result = self.run_fixture(valid_snapshot())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "PASS snapshot=NVDA candles>0 valid_participation>0 future_rows=0",
        )

    def test_checked_in_redacted_replay_passes_offline(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--fixture", str(FIXTURE)],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "PASS snapshot=NVDA candles>0 valid_participation>0 future_rows=0",
        )

    def assert_rejected(self, payload: dict[str, Any]) -> None:
        result = self.run_fixture(payload)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stderr.startswith("FAIL "), result.stderr)

    def test_rejects_an_empty_completed_candle_series(self) -> None:
        payload = valid_snapshot()
        payload["completedCandles"] = []
        payload["participationBars"] = []

        self.assert_rejected(payload)

    def test_rejects_a_decision_cutoff_in_the_future(self) -> None:
        payload = valid_snapshot()
        payload["decisionCutoff"] = "2999-01-01T00:00:00Z"

        self.assert_rejected(payload)

    def test_rejects_any_source_child_after_the_common_cutoff(self) -> None:
        locations = [
            ("quote",),
            ("completedCandles", 0),
            ("participationBars", 0),
            ("indicators", "ma5"),
            ("provenance", 0),
        ]

        for location in locations:
            with self.subTest(location=location):
                payload = valid_snapshot()
                child: Any = payload
                for key in location:
                    child = child[key]
                child["availableAt"] = "2026-07-25T04:00:06Z"
                self.assert_rejected(payload)

    def test_rejects_out_of_order_or_duplicate_candles(self) -> None:
        payload = valid_snapshot()
        payload["completedCandles"].reverse()
        payload["participationBars"].reverse()
        self.assert_rejected(payload)

        payload = valid_snapshot()
        payload["completedCandles"][1]["timestamp"] = payload["completedCandles"][0][
            "timestamp"
        ]
        payload["completedCandles"][1]["asOf"] = payload["completedCandles"][0][
            "asOf"
        ]
        payload["participationBars"][1]["closedAt"] = payload["participationBars"][0][
            "closedAt"
        ]
        payload["participationBars"][1]["asOf"] = payload["participationBars"][0][
            "asOf"
        ]
        self.assert_rejected(payload)

    def test_rejects_misaligned_participation_without_reordering_or_repair(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"].reverse()

        self.assert_rejected(payload)

    def test_rejects_live_shares_without_any_numeric_tolerance(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"][1]["mainShare"] = 0.6000000001

        self.assert_rejected(payload)

    def test_rejects_out_of_range_or_non_finite_shares(self) -> None:
        for value in (-0.1, 1.1, float("nan")):
            with self.subTest(value=value):
                payload = valid_snapshot()
                payload["participationBars"][1]["mainShare"] = value
                self.assert_rejected(payload)

    def test_rejects_partial_repair_of_an_unavailable_participation_bar(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"][0]["mainShare"] = 0.5

        self.assert_rejected(payload)

    def test_requires_at_least_one_valid_participation_bar(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"][1] = deepcopy(payload["participationBars"][0])
        payload["participationBars"][1]["closedAt"] = payload["completedCandles"][1][
            "timestamp"
        ]
        payload["participationBars"][1]["asOf"] = payload["completedCandles"][1][
            "timestamp"
        ]

        self.assert_rejected(payload)

    def test_requires_all_indicators_to_use_the_common_decision_cutoff(self) -> None:
        payload = valid_snapshot()
        payload["indicators"]["rsi"]["availableAt"] = "2026-07-25T04:00:04Z"

        self.assert_rejected(payload)

    def test_rejects_an_accidental_trading_capability_anywhere_in_response(self) -> None:
        payloads = []
        for key, value in (
            ("placeOrder", True),
            ("orders", []),
            ("endpoint", "/trade/orders"),
        ):
            payload = valid_snapshot()
            payload["quote"][key] = value
            payloads.append(payload)

        for payload in payloads:
            with self.subTest(extra=payload["quote"]):
                self.assert_rejected(payload)

    def test_live_smoke_gets_health_then_the_read_only_snapshot(self) -> None:
        health = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:05Z",
            "availableAt": "2026-07-25T04:00:05Z",
            "items": [{"status": "healthy"}],
        }
        requests: list[tuple[str, str]] = []

        def opener(request: Request, *, timeout: float) -> JsonResponse:
            requests.append((request.get_method(), request.full_url))
            return JsonResponse(
                health if request.full_url.endswith("/health") else valid_snapshot()
            )

        snapshot = SMOKE.load_live_snapshot(
            "http://127.0.0.1:8765",
            symbol="NVDA",
            interval="5m",
            count=200,
            opener=opener,
        )

        self.assertEqual(snapshot["symbol"], "NVDA")
        self.assertEqual([method for method, _ in requests], ["GET", "GET"])
        self.assertEqual(requests[0][1], "http://127.0.0.1:8765/health")
        self.assertEqual(
            requests[1][1],
            "http://127.0.0.1:8765/"
            "stock-snapshot?symbol=NVDA&interval=5m&count=200",
        )

    def test_live_smoke_sends_a_runtime_token_only_in_authorization_headers(
        self,
    ) -> None:
        health = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:05Z",
            "availableAt": "2026-07-25T04:00:05Z",
            "items": [{"status": "healthy"}],
        }
        requests: list[Request] = []

        def opener(request: Request, *, timeout: float) -> JsonResponse:
            requests.append(request)
            return JsonResponse(
                health if request.full_url.endswith("/health") else valid_snapshot()
            )

        SMOKE.load_live_snapshot(
            "http://192.168.5.84:8765",
            symbol="NVDA",
            interval="5m",
            count=200,
            authorization_token="runtime-only-secret",
            opener=opener,
        )

        self.assertTrue(requests)
        for request in requests:
            self.assertEqual(
                request.get_header("Authorization"),
                "Bearer runtime-only-secret",
            )
            self.assertNotIn("runtime-only-secret", request.full_url)

    def test_live_smoke_stops_after_an_unhealthy_opend_response(self) -> None:
        health = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "offline",
            "asOf": "2026-07-25T04:00:05Z",
            "availableAt": "2026-07-25T04:00:05Z",
            "items": [{"status": "offline"}],
            "error": {"code": "OPEND_OFFLINE"},
        }
        requests: list[str] = []

        def opener(request: Request, *, timeout: float) -> JsonResponse:
            requests.append(request.full_url)
            return JsonResponse(health)

        with self.assertRaisesRegex(SMOKE.SmokeFailure, "OpenD is not healthy"):
            SMOKE.load_live_snapshot(
                "http://127.0.0.1:8765",
                symbol="NVDA",
                interval="5m",
                count=200,
                opener=opener,
            )

        self.assertEqual(requests, ["http://127.0.0.1:8765/health"])


if __name__ == "__main__":
    unittest.main()
