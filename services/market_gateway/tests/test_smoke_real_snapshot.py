from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.request import Request


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPOSITORY_ROOT / "services/market_gateway/scripts/smoke_real_snapshot.py"
)
FIXTURE = (
    REPOSITORY_ROOT
    / "services/market_gateway/tests/fixtures/nvda_snapshot_redacted.json"
)
V3_FIXTURE = (
    REPOSITORY_ROOT
    / "services/market_gateway/tests/fixtures/snapshot_v3_anomalous_holdings.json"
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
        "priceAdjustment": "forward-adjusted",
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
                "receivedAt": "2026-07-25T03:55:01Z",
                "priceAdjustment": "forward-adjusted",
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
                "receivedAt": "2026-07-25T04:00:01Z",
                "priceAdjustment": "forward-adjusted",
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
            "volatility": {
                **metadata,
                "availableAt": cutoff,
                "value": 0.42,
                "sampleSize": 60,
                "missingReason": None,
                "methodVersion": "close-to-close-realized-v1",
            },
            "magicNine": {
                **metadata,
                "direction": "bullish",
                "count": 2,
                "completed": False,
                "confirmedAtIndex": None,
                "methodVersion": "td-setup-close-4-v2",
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

    def test_rejects_a_missing_or_incomplete_required_quote(self) -> None:
        payloads = []

        payload = valid_snapshot()
        payload["quote"] = None
        payloads.append(payload)

        for field in (
            "source",
            "asOf",
            "availableAt",
            "methodVersion",
            "qualityStatus",
        ):
            payload = valid_snapshot()
            payload["quote"].pop(field)
            payloads.append(payload)

        for field, value in (
            ("price", "172.8"),
            ("price", -1),
            ("changePercent", None),
        ):
            payload = valid_snapshot()
            payload["quote"][field] = value
            payloads.append(payload)

        for payload in payloads:
            with self.subTest(quote=payload["quote"]):
                self.assert_rejected(payload)

    def test_rejects_provenance_that_omits_required_contract_fields(self) -> None:
        payloads = []

        payload = valid_snapshot()
        payload["provenance"] = ["moomoo"]
        payloads.append(payload)

        for field in (
            "source",
            "asOf",
            "availableAt",
            "methodVersion",
            "qualityStatus",
        ):
            payload = valid_snapshot()
            payload["provenance"][0].pop(field)
            payloads.append(payload)

        for payload in payloads:
            with self.subTest(provenance=payload["provenance"]):
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

    def test_rejects_live_participation_without_positive_activity(self) -> None:
        payload = valid_snapshot()
        bar = payload["participationBars"][1]
        bar["mainShare"] = 0.5
        bar["retailShare"] = 0.5
        bar["mainActivity"] = 0.0
        bar["retailActivity"] = 0.0

        self.assert_rejected(payload)

    def test_rejects_live_participation_with_overflowing_activity_denominator(
        self,
    ) -> None:
        payload = valid_snapshot()
        bar = payload["participationBars"][1]
        bar["mainActivity"] = 1e308
        bar["retailActivity"] = 1e308
        bar["mainShare"] = 0.0
        bar["retailShare"] = 1.0

        self.assert_rejected(payload)

    def test_accepts_live_participation_with_large_finite_activity_denominator(
        self,
    ) -> None:
        payload = valid_snapshot()
        bar = payload["participationBars"][1]
        bar["mainActivity"] = 5e307
        bar["retailActivity"] = 5e307
        bar["mainShare"] = 0.5
        bar["retailShare"] = 0.5

        result = self.run_fixture(payload)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_live_participation_without_positive_coverage(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"][1]["coverage"] = 0.0

        self.assert_rejected(payload)

    def test_rejects_live_participation_without_exact_complete_coverage(self) -> None:
        payload = valid_snapshot()
        payload["participationBars"][1]["coverage"] = 0.9999999999999999

        self.assert_rejected(payload)

    def test_rejects_live_shares_not_derived_from_activity(self) -> None:
        payload = valid_snapshot()
        bar = payload["participationBars"][1]
        bar["mainShare"] = 0.5
        bar["retailShare"] = 0.5

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

    def test_rejects_prefixed_capabilities_and_nested_trade_paths(self) -> None:
        payloads = []
        for key, value in (
            ("canUseOpenSec" + "TradeContext", False),
            ("nested", {"endpoint": "/trade/orders/NVDA"}),
            ("nested", {"endpoint": "/api/v2/trade/orders/NVDA"}),
        ):
            payload = valid_snapshot()
            payload["quote"][key] = value
            payloads.append(payload)

        for warning in (
            "SDK symbol OpenSec" + "TradeContext is present",
            "call unlock_" + "trade before use",
            "call place_" + "order before use",
            "call modify_" + "order before use",
            "call cancel_" + "order before use",
        ):
            payload = valid_snapshot()
            payload["warnings"] = [warning]
            payloads.append(payload)

        for payload in payloads:
            with self.subTest(payload=payload):
                self.assert_rejected(payload)

    def test_allows_ordinary_read_only_explanatory_text(self) -> None:
        payload = valid_snapshot()
        payload["warnings"] = [
            "Analysis only; no trading or order submission is available."
        ]

        result = self.run_fixture(payload)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_does_not_treat_an_unknown_object_as_required_snapshot_metadata(
        self,
    ) -> None:
        payload = valid_snapshot()
        payload["diagnostic"] = {"source": "internal-note", "message": "read only"}

        result = self.run_fixture(payload)

        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_default_live_transport_refuses_redirects_before_forwarding_a_bearer(
        self,
    ) -> None:
        requests: list[tuple[str, str | None]] = []
        fixture = valid_snapshot()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                requests.append((self.path, self.headers.get("Authorization")))
                if self.path == "/health":
                    self.send_response(302)
                    self.send_header("Location", "/redirected-health")
                    self.end_headers()
                    return
                payload = (
                    {
                        "schemaVersion": "1",
                        "source": "moomoo",
                        "session": "healthy",
                        "items": [{"status": "healthy"}],
                    }
                    if self.path == "/redirected-health"
                    else fixture
                )
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(SMOKE.SmokeFailure):
                SMOKE.load_live_snapshot(
                    f"http://127.0.0.1:{server.server_port}",
                    symbol="NVDA",
                    interval="5m",
                    count=200,
                    authorization_token="redirect-bearer-canary",
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

        self.assertEqual(requests, [("/health", "Bearer redirect-bearer-canary")])


class SnapshotV3ValidationTests(unittest.TestCase):
    def fixture(self) -> dict[str, Any]:
        return json.loads(V3_FIXTURE.read_text(encoding="utf-8"))

    def validate(self, payload: dict[str, Any]) -> None:
        SMOKE.validate_snapshot_v3(
            payload,
            expected_symbol="AVGO",
            expected_interval="day",
            expected_count=250,
            now=SMOKE._timestamp(
                "2026-07-25T12:00:01Z",
                "now",
            ),
        )

    def test_anomalous_holdings_fixture_is_a_usable_partial_snapshot(self) -> None:
        payload = self.fixture()

        self.validate(payload)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(
            payload["sections"]["holdings"]["data"][0]["holdingPercent"],
            345.937,
        )

    def test_local_stale_invalid_null_section_is_a_precise_limitation(self) -> None:
        payload = self.fixture()
        payload["sections"]["currentSessionFlow"] = {
            "availabilityStatus": "stale",
            "qualityStatus": "invalid",
            "source": None,
            "asOf": None,
            "availableAt": None,
            "receivedAt": None,
            "data": None,
            "errorCode": "STALE_DATA",
            "reason": "当前交易时段资金流数据不可用",
            "warnings": [],
            "anomalies": [],
            "methodVersion": "unavailable-v1",
        }

        self.validate(payload)

    def test_unavailable_holdings_may_retain_only_batch_receipt_provenance(
        self,
    ) -> None:
        payload = self.fixture()
        payload["sections"]["holdings"] = {
            "availabilityStatus": "unavailable",
            "qualityStatus": "invalid",
            "source": "moomoo-delayed-institutional-disclosure",
            "asOf": None,
            "availableAt": None,
            "receivedAt": "2026-07-25T11:59:59Z",
            "data": [],
            "errorCode": "HOLDINGS_UNAVAILABLE",
            "reason": "机构持仓数据不可用",
            "warnings": [],
            "anomalies": [],
            "methodVersion": "reported-holdings-v2-anomaly-aware",
        }

        self.validate(payload)

    def test_stale_requires_null_times_and_live_requires_complete_times(self) -> None:
        mutations = []
        payload = self.fixture()
        payload["sections"]["currentSessionFlow"].update(
            {
                "availabilityStatus": "stale",
                "qualityStatus": "invalid",
                "source": None,
                "asOf": None,
                "availableAt": None,
                "receivedAt": "2026-07-25T11:59:59Z",
                "data": None,
                "errorCode": "STALE_DATA",
                "reason": "当前交易时段资金流数据不可用",
                "methodVersion": "unavailable-v1",
            }
        )
        mutations.append(("stale-with-receipt", payload))
        payload = self.fixture()
        payload["sections"]["quote"]["asOf"] = None
        mutations.append(("live-with-missing-as-of", payload))

        for case, payload in mutations:
            with self.subTest(case=case):
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_section_availability_states_match_the_mobile_contract(self) -> None:
        mutations: list[tuple[str, dict[str, Any]]] = []

        payload = self.fixture()
        payload["sections"]["quote"]["qualityStatus"] = "invalid"
        mutations.append(("live-invalid", payload))

        payload = self.fixture()
        payload["sections"]["holdings"]["source"] = None
        mutations.append(("delayed-without-source", payload))

        for field_name, value in (
            ("qualityStatus", "partial"),
            ("source", "moomoo"),
            ("data", {}),
            ("errorCode", None),
            ("reason", None),
        ):
            payload = self.fixture()
            payload["sections"]["currentSessionFlow"] = {
                "availabilityStatus": "stale",
                "qualityStatus": "invalid",
                "source": None,
                "asOf": None,
                "availableAt": None,
                "receivedAt": None,
                "data": None,
                "errorCode": "STALE_DATA",
                "reason": "provider-message-canary",
                "warnings": [],
                "anomalies": [],
                "methodVersion": "unavailable-v1",
            }
            payload["sections"]["currentSessionFlow"][field_name] = value
            mutations.append((f"stale-{field_name}", payload))

        for field_name, value in (
            ("qualityStatus", "partial"),
            ("data", {}),
            ("errorCode", None),
            ("reason", None),
        ):
            payload = self.fixture()
            payload["sections"]["holdings"] = {
                "availabilityStatus": "unavailable",
                "qualityStatus": "invalid",
                "source": "moomoo-delayed-institutional-disclosure",
                "asOf": None,
                "availableAt": None,
                "receivedAt": "2026-07-25T11:59:59Z",
                "data": [],
                "errorCode": "HOLDINGS_UNAVAILABLE",
                "reason": "provider-message-canary",
                "warnings": [],
                "anomalies": [],
                "methodVersion": "reported-holdings-v2-anomaly-aware",
            }
            payload["sections"]["holdings"][field_name] = value
            mutations.append((f"unavailable-{field_name}", payload))

        for case, payload in mutations:
            with self.subTest(case=case):
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_warning_strings_must_be_non_empty(self) -> None:
        for warning in ("", "   ", 1):
            with self.subTest(warning=warning):
                payload = self.fixture()
                payload["sections"]["technical"]["warnings"] = [warning]

                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_anomaly_shape_is_validated_in_every_section(self) -> None:
        anomalies: tuple[Any, ...] = (
            "not-an-object",
            {"code": "", "reason": "reason"},
            {"code": "CODE", "reason": ""},
            {"code": "CODE", "reason": "reason", "rowIndex": True},
            {"code": "CODE", "reason": "reason", "rowIndex": -1},
            {"code": "CODE", "reason": "reason", "rowIndex": 1.5},
        )
        for anomaly in anomalies:
            with self.subTest(anomaly=anomaly):
                payload = self.fixture()
                payload["sections"]["technical"]["anomalies"] = [anomaly]

                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_requires_exact_top_level_requested_sections_and_section_names(self) -> None:
        mutations = []
        payload = self.fixture()
        payload["extra"] = True
        mutations.append(payload)
        payload = self.fixture()
        payload["requestedSections"].reverse()
        mutations.append(payload)
        payload = self.fixture()
        payload["requestedSections"].append("quote")
        mutations.append(payload)
        payload = self.fixture()
        del payload["sections"]["news"]
        mutations.append(payload)
        payload = self.fixture()
        payload["sections"]["extra"] = deepcopy(payload["sections"]["news"])
        mutations.append(payload)

        for payload in mutations:
            with self.subTest(keys=tuple(payload)):
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_requires_exact_section_envelope_fields_and_supported_enums(self) -> None:
        mutations = []
        payload = self.fixture()
        del payload["sections"]["quote"]["receivedAt"]
        mutations.append(payload)
        payload = self.fixture()
        payload["sections"]["quote"]["extra"] = True
        mutations.append(payload)
        payload = self.fixture()
        payload["sections"]["quote"]["availabilityStatus"] = "demo"
        mutations.append(payload)
        payload = self.fixture()
        payload["sections"]["quote"]["qualityStatus"] = "live"
        mutations.append(payload)

        for payload in mutations:
            with self.subTest(envelope=payload["sections"]["quote"]):
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_rejects_future_or_misordered_section_timestamps(self) -> None:
        mutations = []
        payload = self.fixture()
        payload["sections"]["quote"]["receivedAt"] = "2026-07-25T12:00:01Z"
        mutations.append(payload)
        payload = self.fixture()
        payload["sections"]["quote"]["availableAt"] = "2026-07-25T11:59:57Z"
        mutations.append(payload)

        for payload in mutations:
            with self.subTest(envelope=payload["sections"]["quote"]):
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_requires_exact_unrequested_envelopes(self) -> None:
        for name in ("fundamentals", "marketContext", "news", "forecastDecision"):
            with self.subTest(name=name):
                payload = self.fixture()
                payload["sections"][name]["errorCode"] = "SECTION_UNAVAILABLE"
                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_rejects_neither_usable_quote_nor_non_empty_completed_candles(self) -> None:
        payload = self.fixture()
        for name in ("quote", "candles"):
            payload["sections"][name].update(
                {
                    "availabilityStatus": "unavailable",
                    "qualityStatus": "invalid",
                    "source": None,
                    "asOf": None,
                    "availableAt": None,
                    "receivedAt": None,
                    "data": None,
                    "errorCode": "SECTION_UNAVAILABLE",
                    "reason": "此数据切片不可用",
                    "warnings": [],
                    "anomalies": [],
                    "methodVersion": "unavailable-v1",
                }
            )
        payload["status"] = "unavailable"

        with self.assertRaisesRegex(
            SMOKE.SmokeFailure,
            "usable quote or completed candles",
        ):
            self.validate(payload)

    def test_live_validated_quote_must_be_semantically_usable(self) -> None:
        for price in (None, True, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(price=price):
                payload = self.fixture()
                payload["sections"]["quote"]["data"]["price"] = price

                with self.assertRaisesRegex(
                    SMOKE.SmokeFailure,
                    "validated quote is unusable",
                ):
                    self.validate(payload)

    def test_quote_contract_matches_the_mobile_decoder(self) -> None:
        mutations = (
            (("sections", "quote", "source"), "evil-provider"),
            (("sections", "quote", "methodVersion"), "wrong-method"),
            (("sections", "quote", "data", "source"), "evil-provider"),
            (("sections", "quote", "data", "methodVersion"), "wrong-method"),
            (("sections", "quote", "data", "institutionalIdentity"), True),
            (("sections", "quote", "data", "changePercent"), float("inf")),
            (("sections", "quote", "data", "asOf"), "2026-07-25T11:59:57Z"),
            (("sections", "quote", "data", "availableAt"), "2026-07-25T11:59:59Z"),
            (("sections", "quote", "data", "asOf"), "2099-01-01T00:00:00Z"),
            (("sections", "quote", "data", "availableAt"), "2099-01-01T00:00:00Z"),
            (("sections", "quote", "data", "qualityStatus"), "delayed"),
        )
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                payload = self.fixture()
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_candle_contract_matches_the_mobile_decoder(self) -> None:
        mutations = (
            (("sections", "candles", "source"), "evil-provider"),
            (("sections", "candles", "methodVersion"), "wrong-method"),
            (("sections", "candles", "data", "priceAdjustment"), "backward"),
            (("sections", "candles", "data", "candles", 0, "institutionalIdentity"), True),
            (("sections", "candles", "data", "candles", 0, "source"), "evil-provider"),
            (("sections", "candles", "data", "candles", 0, "asOf"), "2026-07-24T19:59:59Z"),
            (("sections", "candles", "data", "candles", 0, "availableAt"), "2026-07-24T20:00:02Z"),
            (("sections", "candles", "data", "candles", 0, "receivedAt"), "2026-07-24T20:00:03Z"),
            (("sections", "candles", "data", "candles", 0, "asOf"), "2099-01-01T00:00:00Z"),
            (("sections", "candles", "data", "candles", 0, "availableAt"), "2099-01-01T00:00:00Z"),
            (("sections", "candles", "data", "candles", 0, "receivedAt"), "2099-01-01T00:00:00Z"),
            (("sections", "candles", "data", "candles", 0, "qualityStatus"), "delayed"),
            (("sections", "candles", "data", "candles", 0, "methodVersion"), "wrong-method"),
            (("sections", "candles", "data", "candles", 0, "priceAdjustment"), "unadjusted"),
            (("sections", "candles", "data", "candles", 0, "complete"), False),
            (("sections", "candles", "data", "candles", 0, "open"), True),
            (("sections", "candles", "data", "candles", 0, "high"), float("nan")),
            (("sections", "candles", "data", "candles", 0, "low"), float("inf")),
            (("sections", "candles", "data", "candles", 0, "close"), 0.0),
            (("sections", "candles", "data", "candles", 0, "volume"), -1.0),
            (("sections", "candles", "data", "candles", 0, "high"), 183.0),
            (("sections", "candles", "data", "candles", 0, "low"), 181.0),
            (("sections", "candles", "data", "candles", 0, "high"), 179.0),
            (("sections", "candles", "asOf"), "2026-07-24T19:59:59Z"),
            (("sections", "candles", "availableAt"), "2026-07-24T20:00:02Z"),
        )
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                payload = self.fixture()
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

                with self.assertRaises(SMOKE.SmokeFailure):
                    self.validate(payload)

    def test_candle_section_available_at_is_the_maximum_row_availability(
        self,
    ) -> None:
        payload = self.fixture()
        candles = payload["sections"]["candles"]
        later_row = deepcopy(candles["data"]["candles"][0])
        earlier_row = deepcopy(later_row)
        earlier_row.update(
            {
                "timestamp": "2026-07-24T19:59:00Z",
                "asOf": "2026-07-24T19:59:00Z",
                "availableAt": "2026-07-24T20:00:02Z",
            }
        )
        candles["data"]["candles"] = [earlier_row, later_row]
        candles["availableAt"] = "2026-07-24T20:00:02Z"

        self.validate(payload)

    def test_empty_validated_candles_make_the_snapshot_partial(self) -> None:
        payload = self.fixture()
        payload["sections"]["candles"]["data"]["candles"] = []
        payload["sections"]["holdings"]["qualityStatus"] = "validated"
        payload["sections"]["holdings"]["anomalies"] = []
        payload["status"] = "live"

        with self.assertRaisesRegex(SMOKE.SmokeFailure, "status"):
            self.validate(payload)

        payload["status"] = "partial"
        self.validate(payload)

    def test_live_validated_holdings_must_be_non_empty(self) -> None:
        payload = self.fixture()
        payload["sections"]["holdings"].update(
            {"qualityStatus": "validated", "data": [], "anomalies": []}
        )
        payload["status"] = "live"

        with self.assertRaises(SMOKE.SmokeFailure):
            self.validate(payload)

    def test_v2_and_v3_validators_reject_the_other_schema(self) -> None:
        with self.assertRaises(SMOKE.SmokeFailure):
            SMOKE.validate_snapshot_v2(
                self.fixture(),
                expected_symbol="AVGO",
                expected_interval="day",
            )
        with self.assertRaises(SMOKE.SmokeFailure):
            self.validate(valid_snapshot())

    def test_v3_fixture_cli_passes_only_when_v3_is_selected(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--fixture",
                str(V3_FIXTURE),
                "--contract-version",
                "v3",
                "--symbol",
                "AVGO",
                "--interval",
                "day",
                "--count",
                "250",
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class ContractVersionDispatchTests(unittest.TestCase):
    def test_contract_version_defaults_to_v2(self) -> None:
        self.assertEqual(SMOKE._parser().parse_args([]).contract_version, "v2")

    def test_each_cli_version_dispatches_only_its_exact_validator(self) -> None:
        for version, expected in (("v2", "v2"), ("v3", "v3")):
            with self.subTest(version=version):
                called: list[str] = []
                with (
                    patch.object(SMOKE, "load_live_snapshot", return_value={}),
                    patch.object(
                        SMOKE,
                        "validate_snapshot_v2",
                        side_effect=lambda *args, **kwargs: called.append("v2"),
                    ),
                    patch.object(
                        SMOKE,
                        "validate_snapshot_v3",
                        side_effect=lambda *args, **kwargs: called.append("v3"),
                    ),
                    patch("builtins.print"),
                ):
                    self.assertEqual(
                        SMOKE.main(["--contract-version", version]),
                        0,
                    )
                self.assertEqual(called, [expected])

    def test_each_version_requests_only_its_exact_snapshot_route(self) -> None:
        health = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "items": [{"status": "healthy"}],
        }
        for version, path in (
            ("v2", "/stock-snapshot"),
            ("v3", "/v3/stock-snapshot"),
        ):
            with self.subTest(version=version):
                requests: list[str] = []

                def opener(request: Request, *, timeout: float) -> JsonResponse:
                    requests.append(request.full_url)
                    return JsonResponse(health if request.full_url.endswith("/health") else {})

                SMOKE.load_live_snapshot(
                    "http://gateway",
                    symbol="NVDA",
                    interval="day",
                    count=250,
                    contract_version=version,
                    opener=opener,
                )

                self.assertEqual(
                    requests,
                    [
                        "http://gateway/health",
                        f"http://gateway{path}?symbol=NVDA&interval=day&count=250",
                    ],
                )


if __name__ == "__main__":
    unittest.main()
