"""Tests for the live smoke gate.

The gate exists because a green unit suite once certified a `/decision` route
that had never answered a real phone. So these tests are written against the
gate's own failure behaviour: every case below is a way the live chain can be
broken while every in-process test stays green, and each one asserts that the
gate says so out loud, names the stage, and refuses to exit zero.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/smoke_live.py"
V3_FIXTURE = (
    REPOSITORY_ROOT
    / "services/market_gateway/tests/fixtures/snapshot_v3_anomalous_holdings.json"
)
SPEC = importlib.util.spec_from_file_location("smoke_live", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
# Registered before execution because the module defines slotted dataclasses,
# and dataclasses resolves their annotations through sys.modules.
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)


BASE = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def candles(count: int) -> list[dict[str, Any]]:
    result = []
    for index in range(count):
        closed_at = BASE + timedelta(minutes=5 * (index + 1))
        close = 100.0 + index
        result.append(
            {
                "timestamp": iso(closed_at),
                "asOf": iso(closed_at),
                "availableAt": iso(closed_at),
                "receivedAt": iso(closed_at),
                "complete": True,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0 + index,
                "priceAdjustment": "forward-adjusted",
                "source": "moomoo",
                "methodVersion": "provider-completed-candle-v1",
                "qualityStatus": "live",
            }
        )
    return result


def series(count: int, blanks: int) -> list[float | None]:
    """A candle-aligned series whose leading warm-up is unmeasured."""
    blanks = min(blanks, count)
    return [None] * blanks + [1.0 + index for index in range(count - blanks)]


def snapshot_payload(count: int = 80) -> dict[str, Any]:
    rows = candles(count)
    cutoff = iso(BASE + timedelta(minutes=5 * count + 1))

    def entry(extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "analysis-core",
            "asOf": rows[-1]["timestamp"],
            "availableAt": cutoff,
            "seriesAlignedTo": "completedCandles",
            "qualityStatus": "live",
            **extra,
        }

    return {
        "schemaVersion": "2",
        "source": "moomoo",
        "sourceStatus": "live",
        "symbol": "NVDA",
        "interval": "5m",
        "decisionCutoff": cutoff,
        "priceAdjustment": "forward-adjusted",
        "completedCandles": rows,
        "indicators": {
            "ma5": entry({"value": 1.0, "series": series(count, 4),
                          "methodVersion": "sma-5-v1"}),
            "ma10": entry({"value": 1.0, "series": series(count, 9),
                           "methodVersion": "sma-10-v1"}),
            "ma20": entry({"value": 1.0, "series": series(count, 19),
                           "methodVersion": "sma-20-v1"}),
            "ma60": entry({"value": 1.0, "series": series(count, 59),
                           "methodVersion": "sma-60-v1"}),
            "rsi": entry({"value": 55.0, "series": series(count, 14),
                          "methodVersion": "wilder-rsi-14-v1"}),
            "macd": entry(
                {
                    "line": 1.0,
                    "signal": 0.5,
                    "histogram": 0.5,
                    "lineSeries": series(count, 25),
                    "signalSeries": series(count, 33),
                    "histogramSeries": series(count, 33),
                    "methodVersion": "macd-12-26-9-v1",
                }
            ),
        },
    }


def score_block() -> dict[str, Any]:
    return {
        "value": 62.5,
        "direction": "bullish",
        "actionable": True,
        "methodVersion": "objective-score-v3",
        "factorCoverage": 0.75,
        "unavailableFactors": ["macro"],
        "blockedBy": [],
        "contributions": [
            {
                "name": "trend",
                "rawValue": 1.0,
                "weight": 0.3,
                "points": 30.0,
                "explanation": "close above the twenty period mean",
            }
        ],
    }


def decision_payload(count: int = 80) -> dict[str, Any]:
    last_close = 100.0 + (count - 1)
    return {
        "schemaVersion": "1",
        "status": "live",
        "symbol": "NVDA",
        "horizon": "short",
        "interval": "day",
        "decisionCutoff": iso(BASE + timedelta(minutes=5 * count + 1)),
        "score": score_block(),
        "baselineScore": score_block(),
        "adviserAdjustment": 0.0,
        "forecast": {
            "currentPrice": last_close,
            "methodVersion": "scenario-forecast-v1",
            "calibrationStatus": "uncalibrated",
            "calibrationReference": None,
            "invalidationConditions": ["evidence withdrawn"],
            "disclaimer": "not advice",
            "cases": [
                {
                    "kind": "base",
                    "probability": 0.6,
                    "priceLow": last_close * 0.98,
                    "priceHigh": last_close * 1.02,
                    "explanation": "range",
                }
            ],
        },
        "riskPlan": {"action": "watch", "direction": "bullish"},
        "sentiment": {"conclusion": "mixed", "actionScore": 0.1},
        "citations": [],
        "notes": [],
    }


class FakeTransport:
    """Answers the four live calls the gate makes, and records what it was sent."""

    def __init__(self, answers: dict[tuple[str, str], Any]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        stage: str,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> Any:
        self.calls.append(
            {"stage": stage, "method": method, "url": url, "token": token, "body": body}
        )
        path = url.split("?", 1)[0]
        answer = self.answers[(method, path)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def call_for(self, stage: str) -> dict[str, Any]:
        for call in self.calls:
            if call["stage"] == stage:
                return call
        raise AssertionError(f"no call was made for stage {stage}")


def transport(overrides: dict[tuple[str, str], Any] | None = None) -> FakeTransport:
    answers: dict[tuple[str, str], Any] = {
        ("GET", "http://gateway/health"): {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "items": [{"status": "healthy"}],
        },
        ("GET", "http://gateway/stock-snapshot"): snapshot_payload(),
        ("POST", "http://analysis/v1/device-pairings"): {
            "deviceId": "dev-1",
            "deviceToken": "dev-1.secret-token-value",
            "expiresAt": None,
        },
        ("GET", "http://analysis/health"): {"status": "ready", "asOf": iso(BASE)},
        ("GET", "http://analysis/decision"): decision_payload(),
    }
    answers.update(overrides or {})
    return FakeTransport(answers)


class Operator:
    """Stands in for the device_auth terminal commands."""

    def __init__(self, code: str = "ABCD-EFGH", revoke_error: Exception | None = None):
        self.code = code
        self.revoke_error = revoke_error
        self.issued_labels: list[str] = []
        self.revoked: list[str] = []

    def issue(self, label: str) -> str:
        self.issued_labels.append(label)
        return self.code

    def revoke(self, device_id: str) -> None:
        self.revoked.append(device_id)
        if self.revoke_error is not None:
            raise self.revoke_error


def run(transport_: FakeTransport, operator: Operator | None = None):
    operator = operator or Operator()
    lines: list[str] = []
    SMOKE.run_smoke(
        SMOKE.SmokeConfig(
            gateway_url="http://gateway",
            analysis_url="http://analysis",
            interval="5m",
        ),
        request=transport_,
        issue_pairing_code=operator.issue,
        revoke_device=operator.revoke,
        log=lines.append,
    )
    return lines, operator


class SnapshotValidationTests(unittest.TestCase):
    def test_accepts_a_snapshot_whose_series_are_candle_aligned(self) -> None:
        facts = SMOKE.validate_snapshot(
            snapshot_payload(), expected_symbol="NVDA", expected_interval="5m"
        )
        self.assertEqual(facts.candle_count, 80)
        self.assertEqual(facts.last_close, 179.0)

    def test_rejects_an_indicator_series_shorter_than_the_candles(self) -> None:
        payload = snapshot_payload()
        payload["indicators"]["rsi"]["series"] = payload["indicators"]["rsi"]["series"][:-1]
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("rsi", caught.exception.detail)
        self.assertIn("79", caught.exception.detail)
        self.assertIn("80", caught.exception.detail)

    def test_rejects_a_series_that_was_never_measured(self) -> None:
        payload = snapshot_payload()
        payload["indicators"]["ma5"]["series"] = [None] * 80
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("ma5", caught.exception.detail)

    def test_reports_but_accepts_a_series_below_its_warm_up_length(self) -> None:
        payload = snapshot_payload(count=30)
        payload["indicators"]["ma60"]["series"] = [None] * 30
        payload["indicators"]["ma60"]["value"] = None
        payload["indicators"]["ma60"]["qualityStatus"] = "unavailable"
        facts = SMOKE.validate_snapshot(
            payload, expected_symbol="NVDA", expected_interval="5m"
        )
        self.assertIn("ma60", " ".join(facts.notes))

    def test_rejects_a_series_that_does_not_declare_its_axis(self) -> None:
        payload = snapshot_payload()
        del payload["indicators"]["macd"]["seriesAlignedTo"]
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("seriesAlignedTo", caught.exception.detail)

    def test_rejects_a_missing_indicator(self) -> None:
        payload = snapshot_payload()
        del payload["indicators"]["ma20"]
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        detail = caught.exception.detail
        self.assertIn("ma20", detail)
        # An indicator that is absent has to read as absent. "not an object" is
        # what a reader would chase into a serializer that is working fine.
        self.assertIn("absent", detail)

    def test_rejects_an_empty_candle_series(self) -> None:
        payload = snapshot_payload()
        payload["completedCandles"] = []
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("completedCandles", caught.exception.detail)

    def test_rejects_candles_that_are_out_of_order(self) -> None:
        payload = snapshot_payload()
        payload["completedCandles"][3], payload["completedCandles"][4] = (
            payload["completedCandles"][4],
            payload["completedCandles"][3],
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("order", caught.exception.detail)

    def test_rejects_an_incomplete_candle(self) -> None:
        payload = snapshot_payload()
        payload["completedCandles"][-1]["complete"] = False
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("complete", caught.exception.detail)

    def test_rejects_a_snapshot_for_another_symbol(self) -> None:
        payload = snapshot_payload()
        payload["symbol"] = "AAPL"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("AAPL", caught.exception.detail)


class DecisionValidationTests(unittest.TestCase):
    def validate(self, payload: dict[str, Any]):
        return SMOKE.validate_decision(
            payload, expected_symbol="NVDA", expected_horizon="short"
        )

    def test_accepts_a_scored_decision(self) -> None:
        facts = self.validate(decision_payload())
        self.assertEqual(facts.score, 62.5)
        self.assertEqual(facts.direction, "bullish")
        self.assertEqual(facts.factor_coverage, 0.75)
        self.assertEqual(facts.current_price, 179.0)

    def test_rejects_an_unavailable_decision_and_quotes_its_reason(self) -> None:
        payload = decision_payload()
        payload["status"] = "unavailable"
        payload["score"] = None
        payload["notes"] = ["No completed candles were available at the cutoff."]
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("unavailable", caught.exception.detail)
        self.assertNotIn("No completed candles", caught.exception.render())

    def test_rejects_a_null_score(self) -> None:
        payload = decision_payload()
        payload["score"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("score", caught.exception.detail)

    def test_rejects_a_score_with_no_value(self) -> None:
        payload = decision_payload()
        payload["score"]["value"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("score.value", caught.exception.detail)

    def test_rejects_an_unknown_direction(self) -> None:
        payload = decision_payload()
        payload["score"]["direction"] = "sideways"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("sideways", caught.exception.detail)

    def test_rejects_a_coverage_of_zero(self) -> None:
        payload = decision_payload()
        payload["score"]["factorCoverage"] = 0.0
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("factorCoverage", caught.exception.detail)

    def test_rejects_an_unmeasured_coverage(self) -> None:
        payload = decision_payload()
        payload["score"]["factorCoverage"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        detail = caught.exception.detail
        self.assertIn("factorCoverage", detail)
        # Coverage that was never measured is a different fact from coverage
        # that came out at zero, and the report has to say which one it is.
        self.assertIn("not measured", detail)

    def test_rejects_an_empty_contribution_list(self) -> None:
        payload = decision_payload()
        payload["score"]["contributions"] = []
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("contributions", caught.exception.detail)

    def test_rejects_an_answer_for_another_symbol(self) -> None:
        payload = decision_payload()
        payload["symbol"] = "AAPL"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("AAPL", caught.exception.detail)

    def test_reports_an_absent_forecast_as_unmeasured_rather_than_zero(self) -> None:
        payload = decision_payload()
        payload["forecast"] = None
        facts = self.validate(payload)
        self.assertIsNone(facts.current_price)


class PriceCrossCheckTests(unittest.TestCase):
    def facts(self):
        snapshot = SMOKE.validate_snapshot(
            snapshot_payload(), expected_symbol="NVDA", expected_interval="5m"
        )
        decision = SMOKE.validate_decision(
            decision_payload(), expected_symbol="NVDA", expected_horizon="short"
        )
        return decision, snapshot

    def test_accepts_a_price_taken_from_a_recent_candle(self) -> None:
        decision, snapshot = self.facts()
        self.assertIn("179", SMOKE.cross_check_price(decision, snapshot))

    def test_accepts_a_price_one_candle_behind_the_snapshot(self) -> None:
        # The snapshot is read after the decision, so a bar that closed between
        # the two calls leaves the decision one candle behind. That is the
        # ordinary race, not a broken chain.
        decision, snapshot = self.facts()
        behind = SMOKE.DecisionFacts(
            score=decision.score,
            direction=decision.direction,
            factor_coverage=decision.factor_coverage,
            current_price=178.0,
            cutoff=decision.cutoff,
        )
        SMOKE.cross_check_price(behind, snapshot)

    def test_rejects_a_price_that_matches_no_candle(self) -> None:
        decision, snapshot = self.facts()
        detached = SMOKE.DecisionFacts(
            score=decision.score,
            direction=decision.direction,
            factor_coverage=decision.factor_coverage,
            current_price=1.23,
            cutoff=decision.cutoff,
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.cross_check_price(detached, snapshot)
        self.assertIn("1.23", caught.exception.detail)

    def test_states_plainly_when_there_was_no_price_to_check(self) -> None:
        decision, snapshot = self.facts()
        unmeasured = SMOKE.DecisionFacts(
            score=decision.score,
            direction=decision.direction,
            factor_coverage=decision.factor_coverage,
            current_price=None,
            cutoff=decision.cutoff,
        )
        message = SMOKE.cross_check_price(unmeasured, snapshot)
        self.assertIn("not measured", message)


class StageFailureRenderingTests(unittest.TestCase):
    def test_names_only_the_stage_fixed_classification_and_http_status(self) -> None:
        canary = "raw-provider-canary"
        failure = SMOKE.StageFailure(
            "decision",
            canary,
            url=f"http://analysis/decision?secret={canary}",
            http_status=500,
            server_code=canary,
            server_message=canary,
            cause=ValueError(canary),
            classification="http-error",
        )
        rendered = failure.render()
        self.assertIn("stage=decision", rendered)
        self.assertIn("http_status: 500", rendered)
        self.assertIn("classification: http-error", rendered)
        self.assertNotIn(canary, rendered)
        self.assertNotIn("server_message", rendered)
        self.assertNotIn("local_exception", rendered)
        self.assertNotIn("url:", rendered)

    def test_distinguishes_a_field_that_does_not_apply_from_one_left_blank(self) -> None:
        rendered = SMOKE.StageFailure("issue_pairing_code", "the terminal failed").render()
        self.assertIn("http_status: none", rendered)
        self.assertIn("classification:", rendered)


class RunSmokeTests(unittest.TestCase):
    def test_walks_the_whole_live_path_and_reports_a_pass(self) -> None:
        sent = transport()
        lines, operator = run(sent)
        stages = [call["stage"] for call in sent.calls]
        self.assertEqual(
            stages,
            [
                "gateway_health",
                "redeem_pairing_code",
                "analysis_health",
                "decision",
                "gateway_snapshot",
            ],
        )
        self.assertEqual(operator.revoked, ["dev-1"])
        self.assertTrue(any("PASS" in line for line in lines))

    def test_redeems_with_the_field_name_the_service_reads(self) -> None:
        sent = transport()
        run(sent)
        body = sent.call_for("redeem_pairing_code")["body"]
        self.assertEqual(body, {"pairingCode": "ABCD-EFGH"})

    def test_carries_the_device_token_on_every_authenticated_call(self) -> None:
        sent = transport()
        run(sent)
        for stage in ("analysis_health", "decision"):
            self.assertEqual(
                sent.call_for(stage)["token"], "dev-1.secret-token-value"
            )
        self.assertIsNone(sent.call_for("redeem_pairing_code")["token"])

    def test_never_prints_the_device_token(self) -> None:
        sent = transport()
        lines, _ = run(sent)
        self.assertNotIn("dev-1.secret-token-value", "\n".join(lines))

    def test_asks_the_decision_route_for_the_symbol_and_horizon(self) -> None:
        sent = transport()
        run(sent)
        url = sent.call_for("decision")["url"]
        self.assertIn("symbol=NVDA", url)
        self.assertIn("horizon=short", url)

    def test_revokes_the_smoke_device_even_when_the_decision_fails(self) -> None:
        sent = transport(
            {
                ("GET", "http://analysis/decision"): SMOKE.StageFailure(
                    "decision",
                    "refused",
                    http_status=500,
                    server_code="ANALYSIS_FAILED",
                )
            }
        )
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent, operator)
        self.assertEqual(caught.exception.stage, "decision")
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_still_reads_the_gateway_when_the_decision_fails(self) -> None:
        # Which side broke is the first question after a failed decision, so
        # the candles are read anyway and the answer is put in the report.
        sent = transport(
            {
                ("GET", "http://analysis/decision"): SMOKE.StageFailure(
                    "decision", "refused", http_status=500, server_code="ANALYSIS_FAILED"
                )
            }
        )
        lines: list[str] = []
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.run_smoke(
                SMOKE.SmokeConfig(
                    gateway_url="http://gateway",
                    analysis_url="http://analysis",
                    interval="5m",
                ),
                request=sent,
                issue_pairing_code=operator.issue,
                revoke_device=operator.revoke,
                log=lines.append,
            )
        self.assertIn("gateway_snapshot", [call["stage"] for call in sent.calls])
        self.assertTrue(any("80" in line for line in lines))

    def test_reports_the_original_failure_when_cleanup_also_fails(self) -> None:
        sent = transport(
            {
                ("GET", "http://analysis/decision"): SMOKE.StageFailure(
                    "decision", "refused", http_status=500, server_code="ANALYSIS_FAILED"
                )
            }
        )
        operator = Operator(revoke_error=RuntimeError("sqlite is locked"))
        lines: list[str] = []
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.run_smoke(
                SMOKE.SmokeConfig(
                    gateway_url="http://gateway",
                    analysis_url="http://analysis",
                    interval="5m",
                ),
                request=sent,
                issue_pairing_code=operator.issue,
                revoke_device=operator.revoke,
                log=lines.append,
            )
        self.assertEqual(caught.exception.stage, "decision")
        self.assertNotIn("sqlite is locked", "\n".join(lines))

    def test_a_failed_revocation_alone_still_fails_the_gate(self) -> None:
        sent = transport()
        operator = Operator(revoke_error=RuntimeError("sqlite is locked"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent, operator)
        self.assertEqual(caught.exception.stage, "revoke_smoke_device")

    def test_refuses_an_unhealthy_gateway_before_it_pairs_anything(self) -> None:
        sent = transport(
            {
                ("GET", "http://gateway/health"): {
                    "schemaVersion": "1",
                    "source": "moomoo",
                    "session": "degraded",
                    "items": [{"status": "healthy"}],
                }
            }
        )
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent, operator)
        self.assertEqual(caught.exception.stage, "gateway_health")
        self.assertIn("degraded", caught.exception.detail)
        # Nothing was paired, so a gateway that cannot serve candles does not
        # leave a credential behind on the way out.
        self.assertEqual(operator.issued_labels, [])
        self.assertEqual(operator.revoked, [])

    def test_refuses_a_gateway_whose_connection_is_unhealthy(self) -> None:
        sent = transport(
            {
                ("GET", "http://gateway/health"): {
                    "schemaVersion": "1",
                    "source": "moomoo",
                    "session": "healthy",
                    "items": [{"status": "unhealthy"}],
                }
            }
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent)
        self.assertEqual(caught.exception.stage, "gateway_health")
        self.assertIn("unhealthy", caught.exception.detail)

    def test_refuses_an_analysis_service_that_is_not_ready(self) -> None:
        sent = transport(
            {("GET", "http://analysis/health"): {"status": "starting"}}
        )
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent, operator)
        self.assertEqual(caught.exception.stage, "analysis_health")
        self.assertIn("starting", caught.exception.detail)
        # It got as far as pairing, so the credential is still cleaned up.
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_refuses_a_pairing_reply_without_a_token(self) -> None:
        sent = transport(
            {
                ("POST", "http://analysis/v1/device-pairings"): {
                    "deviceId": "dev-1",
                    "expiresAt": None,
                }
            }
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent)
        self.assertEqual(caught.exception.stage, "redeem_pairing_code")
        self.assertIn("deviceToken", caught.exception.detail)


class PhoneGatewayTests(unittest.TestCase):
    """The app reads candles from a socket the analysis service never touches."""

    def phone_transport(self, snapshot: Any = None) -> FakeTransport:
        sent = transport()
        sent.answers[("GET", "http://phone-gateway/health")] = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "items": [{"status": "healthy"}],
        }
        sent.answers[("GET", "http://phone-gateway/stock-snapshot")] = (
            snapshot if snapshot is not None else snapshot_payload()
        )
        return sent

    def run_with_phone(self, sent: FakeTransport, operator: Operator | None = None):
        operator = operator or Operator()
        lines: list[str] = []
        SMOKE.run_smoke(
            SMOKE.SmokeConfig(
                gateway_url="http://gateway",
                analysis_url="http://analysis",
                interval="5m",
                phone_gateway_url="http://phone-gateway",
                phone_gateway_token="gateway-token",
            ),
            request=sent,
            issue_pairing_code=operator.issue,
            revoke_device=operator.revoke,
            log=lines.append,
        )
        return lines

    def test_says_out_loud_when_the_app_origin_was_not_checked(self) -> None:
        # An unchecked leg reported as nothing is exactly how a chart ends up
        # empty on a phone while every stage above it says PASS.
        sent = transport()
        lines, _ = run(sent)
        self.assertTrue(any("NOT CHECKED" in line for line in lines))
        self.assertNotIn(
            "phone_gateway_health", [call["stage"] for call in sent.calls]
        )

    def test_reads_the_app_origin_with_its_own_token(self) -> None:
        sent = self.phone_transport()
        self.run_with_phone(sent)
        for stage in ("phone_gateway_health", "phone_gateway_snapshot"):
            self.assertEqual(sent.call_for(stage)["token"], "gateway-token")

    def test_fails_the_gate_when_the_app_origin_serves_no_candles(self) -> None:
        broken = snapshot_payload()
        broken["completedCandles"] = []
        sent = self.phone_transport(broken)
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.run_with_phone(sent, operator)
        self.assertEqual(caught.exception.stage, "phone_gateway_snapshot")
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_keeps_the_decision_failure_ahead_of_the_app_origin_failure(self) -> None:
        sent = self.phone_transport()
        sent.answers[("GET", "http://analysis/decision")] = SMOKE.StageFailure(
            "decision", "refused", http_status=500, server_code="ANALYSIS_FAILED"
        )
        sent.answers[("GET", "http://phone-gateway/health")] = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "auth-required",
            "items": [],
        }
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.run_with_phone(sent)
        self.assertEqual(caught.exception.stage, "decision")

    def watchlist_of(self, sent: FakeTransport, *codes: str) -> None:
        sent.answers[("GET", "http://gateway/watchlist")] = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "items": [{"code": code} for code in codes],
        }

    def test_all_watchlist_without_a_phone_gateway_still_says_not_checked(self) -> None:
        # --all-watchlist must not make the unchecked leg quieter: this is the
        # exact "NOT CHECKED" disclosure the single-symbol path already prints,
        # and every batch run loses it the same way if it is gated off.
        sent = transport()
        self.watchlist_of(sent, "US.NVDA")
        lines: list[str] = []
        operator = Operator()
        SMOKE.run_smoke(
            SMOKE.SmokeConfig(
                gateway_url="http://gateway",
                analysis_url="http://analysis",
                interval="5m",
                all_watchlist=True,
            ),
            request=sent,
            issue_pairing_code=operator.issue,
            revoke_device=operator.revoke,
            log=lines.append,
        )
        self.assertTrue(any("NOT CHECKED" in line for line in lines))

    def test_all_watchlist_with_an_explicit_phone_gateway_still_checks_it(self) -> None:
        # An operator who explicitly passes --phone-gateway-url alongside
        # --all-watchlist must get that leg checked, not silently ignored.
        sent = self.phone_transport()
        self.watchlist_of(sent, "US.NVDA")
        operator = Operator()
        SMOKE.run_smoke(
            SMOKE.SmokeConfig(
                gateway_url="http://gateway",
                analysis_url="http://analysis",
                interval="5m",
                all_watchlist=True,
                phone_gateway_url="http://phone-gateway",
                phone_gateway_token="gateway-token",
            ),
            request=sent,
            issue_pairing_code=operator.issue,
            revoke_device=operator.revoke,
            log=lambda line: None,
        )
        self.assertIn(
            "phone_gateway_health", [call["stage"] for call in sent.calls]
        )


class CompoundFailureTests(unittest.TestCase):
    """When several stages fail at once, the cause has to outrank the symptom."""

    def both_failing(self) -> FakeTransport:
        # What a provider quota looks like from outside: the gateway refuses to
        # serve candles, and the decision that reads it turns that into its own
        # sanitized 500. Blaming the 500 sends the reader to the wrong service.
        return transport(
            {
                ("GET", "http://analysis/decision"): SMOKE.StageFailure(
                    "decision",
                    "the service refused this GET request",
                    http_status=500,
                    server_code="ANALYSIS_FAILED",
                ),
                ("GET", "http://gateway/stock-snapshot"): SMOKE.StageFailure(
                    "gateway_snapshot",
                    "the service refused this GET request",
                    http_status=429,
                    server_code="QUOTA_EXCEEDED",
                ),
            }
        )

    def test_blames_the_dependency_rather_than_the_route_that_reads_it(self) -> None:
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(self.both_failing())
        self.assertEqual(caught.exception.stage, "gateway_snapshot")
        self.assertEqual(caught.exception.server_code, "QUOTA_EXCEEDED")

    def test_names_every_other_stage_with_only_safe_status_metadata(self) -> None:
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(self.both_failing())
        rendered = caught.exception.render()
        self.assertIn("also_failed", rendered)
        self.assertIn("decision", rendered)
        self.assertNotIn("ANALYSIS_FAILED", rendered)
        self.assertIn("500", rendered)

    def test_prints_each_failure_with_safe_multiline_fields(self) -> None:
        # A one-line summary drops the fixed classification and numeric status.
        # Both failures retain those safe fields without forwarding server text.
        printed: list[str] = []
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.run_smoke(
                SMOKE.SmokeConfig(
                    gateway_url="http://gateway", analysis_url="http://analysis"
                ),
                request=self.both_failing(),
                issue_pairing_code=operator.issue,
                revoke_device=operator.revoke,
                log=printed.append,
            )
        joined = "\n".join(printed)
        self.assertNotIn("ANALYSIS_FAILED", joined)
        self.assertIn("http_status: 500", joined)
        self.assertNotIn("QUOTA_EXCEEDED", joined)
        self.assertIn("classification: provider-quota", joined)
        self.assertIn("http_status: 429", joined)

    def test_a_lone_failure_names_no_others(self) -> None:
        sent = transport(
            {
                ("GET", "http://analysis/decision"): SMOKE.StageFailure(
                    "decision", "refused", http_status=500, server_code="ANALYSIS_FAILED"
                )
            }
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent)
        self.assertNotIn("also_failed", caught.exception.render())

    def test_a_quota_refusal_explains_itself(self) -> None:
        failure = SMOKE.StageFailure(
            "gateway_snapshot", "refused", http_status=429, server_code="QUOTA_EXCEEDED"
        )
        self.assertIn("quota", failure.render().lower())


class PairingCodeParsingTests(unittest.TestCase):
    def test_reads_the_code_the_operator_terminal_printed(self) -> None:
        printed = (
            "pairing-code: 7QF4-2KDA\n"
            "label: smoke\n"
            "expires-utc: 2026-08-14T01:40:00Z\n"
            "note: single use, one phone, and typed into the phone by hand\n"
        )
        self.assertEqual(SMOKE.parse_pairing_code(printed), "7QF4-2KDA")

    def test_refuses_output_that_carries_no_code(self) -> None:
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.parse_pairing_code("DATABASE_UNREADABLE: the file is not readable\n")
        rendered = caught.exception.render()
        self.assertEqual(caught.exception.stage, "issue_pairing_code")
        self.assertNotIn("DATABASE_UNREADABLE", rendered)


class OperatorTerminalTests(unittest.TestCase):
    """The pairing code exists only on the operator's terminal, so it is run."""

    def terminal(self, *results: Any):
        import subprocess

        recorded: list[list[str]] = []
        answers = list(results)

        def run(command, **kwargs: Any):
            recorded.append(list(command))
            returncode, stdout, stderr = answers.pop(0)
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)

        issue, revoke = SMOKE.operator_terminal(
            database=Path("/tmp/devices.sqlite3"), run=run
        )
        return issue, revoke, recorded

    def test_runs_the_pair_command_against_the_named_database(self) -> None:
        issue, _, recorded = self.terminal((0, "pairing-code: 7QF4-2KDA\nlabel: x\n", ""))
        self.assertEqual(issue("smoke"), "7QF4-2KDA")
        command = recorded[0]
        self.assertIn("pair", command)
        self.assertIn("--database", command)
        self.assertIn("/tmp/devices.sqlite3", command)
        self.assertIn("smoke", command)

    def test_sanitizes_the_terminal_when_the_pair_command_fails(self) -> None:
        issue, _, _ = self.terminal((2, "", "DATABASE_UNREADABLE: refusing a shared file"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            issue("smoke")
        rendered = caught.exception.render()
        self.assertEqual(caught.exception.stage, "issue_pairing_code")
        self.assertNotIn("DATABASE_UNREADABLE", rendered)

    def test_revocation_failure_names_its_own_stage(self) -> None:
        _, revoke, _ = self.terminal((1, "", "unknown-device: dev-9"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            revoke("dev-9")
        self.assertEqual(caught.exception.stage, "revoke_smoke_device")
        self.assertNotIn("unknown-device", caught.exception.render())


class RecordingStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


class ExitCodeTests(unittest.TestCase):
    def test_flushes_each_line_so_the_trail_and_the_verdict_stay_in_order(self) -> None:
        # The stages go to stdout and the failure goes to stderr. Buffered, a
        # redirected run prints the verdict above the stages that produced it.
        out, err = RecordingStream(), RecordingStream()

        def failing(config: Any, **kwargs: Any) -> None:
            kwargs["log"]("stage=decision")
            raise SMOKE.StageFailure("decision", "refused", http_status=500)

        self.assertEqual(SMOKE.main([], runner=failing, stdout=out, stderr=err), 1)
        self.assertGreater(out.flushes, 0)
        self.assertGreater(err.flushes, 0)

    def test_exits_zero_when_the_live_path_answers(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        code = SMOKE.main(
            ["--gateway-url", "http://gateway"],
            runner=lambda *args, **kwargs: None,
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 0)

    def test_exits_non_zero_and_prints_the_true_cause(self) -> None:
        def broken(*args: Any, **kwargs: Any) -> None:
            raise SMOKE.StageFailure(
                "decision",
                "the analysis service refused the decision request",
                http_status=500,
                server_code="ANALYSIS_FAILED",
                cause=RuntimeError("HTTP Error 500"),
            )

        out, err = io.StringIO(), io.StringIO()
        code = SMOKE.main([], runner=broken, stdout=out, stderr=err)
        self.assertEqual(code, 1)
        printed = err.getvalue()
        self.assertIn("stage=decision", printed)
        self.assertNotIn("ANALYSIS_FAILED", printed)
        self.assertIn("500", printed)

    def test_exits_non_zero_when_a_service_cannot_be_reached_at_all(self) -> None:
        def offline(*args: Any, **kwargs: Any) -> None:
            raise SMOKE.StageFailure(
                "gateway_health",
                "the market gateway could not be reached",
                cause=OSError("Connection refused"),
            )

        out, err = io.StringIO(), io.StringIO()
        code = SMOKE.main([], runner=offline, stdout=out, stderr=err)
        self.assertEqual(code, 1)
        self.assertNotIn("Connection refused", err.getvalue())


class HttpFailureTranslationTests(unittest.TestCase):
    """The transport has to turn a live refusal into a locatable cause."""

    def test_reads_the_service_error_code_out_of_an_http_error_body(self) -> None:
        from urllib.error import HTTPError

        body = json.dumps(
            {"error": {"code": "AUTH_REQUIRED", "message": "A paired device token is required"}}
        ).encode("utf-8")
        error = HTTPError(
            "http://analysis/decision", 401, "Unauthorized", {}, io.BytesIO(body)
        )
        request = SMOKE.http_transport(timeout=1.0, opener=_raiser(error))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            request("decision", "GET", "http://analysis/decision")
        rendered = caught.exception.render()
        self.assertIn("http_status: 401", rendered)
        self.assertNotIn("AUTH_REQUIRED", rendered)
        self.assertNotIn("A paired device token is required", rendered)

    def test_states_the_local_exception_when_nothing_answered(self) -> None:
        request = SMOKE.http_transport(
            timeout=1.0, opener=_raiser(OSError("Connection refused"))
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            request("gateway_health", "GET", "http://gateway/health")
        rendered = caught.exception.render()
        self.assertNotIn("Connection refused", rendered)
        self.assertIn("http_status: none", rendered)

    def test_names_the_stage_when_a_service_answers_with_something_else(self) -> None:
        request = SMOKE.http_transport(timeout=1.0, opener=_answering(b"<html>hi</html>"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            request("analysis_health", "GET", "http://analysis/health")
        self.assertEqual(caught.exception.stage, "analysis_health")
        self.assertIn("JSON", caught.exception.detail)

    def test_default_transport_refuses_redirects_before_forwarding_a_bearer(
        self,
    ) -> None:
        requests: list[tuple[str, str | None]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                requests.append((self.path, self.headers.get("Authorization")))
                if self.path == "/source":
                    self.send_response(302)
                    self.send_header("Location", "/sink")
                    self.end_headers()
                    return
                body = b"{}"
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
            request = SMOKE.http_transport(timeout=1.0)
            with self.assertRaises(SMOKE.StageFailure) as caught:
                request(
                    "gateway_health",
                    "GET",
                    f"http://127.0.0.1:{server.server_port}/source",
                    token="redirect-bearer-canary",
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

        self.assertEqual(caught.exception.http_status, 302)
        self.assertEqual(requests, [("/source", "Bearer redirect-bearer-canary")])


def _raiser(error: BaseException):
    def opener(request: Any, timeout: float) -> Any:
        raise error

    return opener


def _answering(body: bytes):
    class Response:
        status = 200

        def read(self, *args: Any) -> bytes:
            return body

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    def opener(request: Any, timeout: float) -> Any:
        return Response()

    return opener


def snapshot_v3_payload(
    symbol: str = "NVDA",
    *,
    interval: str = "day",
    count: int = 250,
) -> dict[str, Any]:
    payload = json.loads(V3_FIXTURE.read_text(encoding="utf-8"))
    payload["symbol"] = symbol
    payload["interval"] = interval
    payload["count"] = count
    return payload


class BatchTransport:
    def __init__(
        self,
        codes: list[str],
        *,
        fail_stage: str | None = None,
        failure: BaseException | None = None,
        stale_flow: bool = False,
        decision_interval: str = "day",
        token: str = "device-token-canary",
        section_error_code: str | None = None,
        anomaly_code: str | None = None,
    ) -> None:
        self.codes = codes
        self.fail_stage = fail_stage
        self.failure = failure
        self.stale_flow = stale_flow
        self.decision_interval = decision_interval
        self.token = token
        self.section_error_code = section_error_code
        self.anomaly_code = anomaly_code
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        stage: str,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> Any:
        self.calls.append(
            {"stage": stage, "method": method, "url": url, "token": token, "body": body}
        )
        if stage == self.fail_stage:
            assert self.failure is not None
            raise self.failure
        split = urlsplit(url)
        query = parse_qs(split.query)
        if split.path == "/health" and split.netloc == "gateway":
            return {
                "schemaVersion": "1",
                "source": "moomoo",
                "session": "healthy",
                "items": [{"status": "healthy"}],
            }
        if split.path == "/watchlist":
            return {
                "schemaVersion": "1",
                "source": "moomoo",
                "session": "healthy",
                "items": [{"code": code} for code in self.codes],
            }
        if split.path == "/v1/device-pairings":
            return {"deviceId": "dev-1", "deviceToken": self.token}
        if split.path == "/health" and split.netloc == "analysis":
            return {"status": "ready"}
        if split.path == "/decision":
            symbol = query["symbol"][0]
            payload = decision_payload()
            payload["symbol"] = symbol
            payload["interval"] = self.decision_interval
            payload["forecast"]["currentPrice"] = 184.0
            return payload
        if split.path == "/v3/stock-snapshot":
            symbol = query["symbol"][0]
            payload = snapshot_v3_payload(
                symbol,
                interval=query["interval"][0],
                count=int(query["count"][0]),
            )
            if self.stale_flow:
                payload["sections"]["currentSessionFlow"] = {
                    "availabilityStatus": "stale",
                    "qualityStatus": "invalid",
                    "source": None,
                    "asOf": None,
                    "availableAt": None,
                    "receivedAt": None,
                    "data": None,
                    "errorCode": self.section_error_code or "STALE_DATA",
                    "reason": "provider-message-canary",
                    "warnings": ["warning-canary"],
                    "anomalies": [],
                    "methodVersion": "unavailable-v1",
                }
            if self.anomaly_code is not None:
                payload["sections"]["holdings"]["anomalies"][0]["code"] = (
                    self.anomaly_code
                )
            return payload
        raise AssertionError(f"unexpected request: {method} {url}")


def batch_config(**overrides: Any) -> Any:
    values = {
        "gateway_url": "http://gateway",
        "analysis_url": "http://analysis",
        "interval": "day",
        "count": 250,
        "all_watchlist": True,
        "snapshot_version": "v3",
    }
    values.update(overrides)
    return SMOKE.SmokeConfig(**values)


class BatchParserAndWatchlistTests(unittest.TestCase):
    def test_parser_supports_batch_v3_report_and_defaults_to_daily(self) -> None:
        arguments = SMOKE.build_parser().parse_args(
            [
                "--all-watchlist",
                "--snapshot-version",
                "v3",
                "--report",
                "/tmp/smoke-report.json",
            ]
        )

        self.assertTrue(arguments.all_watchlist)
        self.assertEqual(arguments.snapshot_version, "v3")
        self.assertEqual(arguments.interval, "day")
        self.assertEqual(arguments.report, "/tmp/smoke-report.json")

    def test_watchlist_codes_are_canonicalized_in_source_order(self) -> None:
        payload = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "items": [{"code": "US.NVDA"}, {"code": "US.BRK.B"}],
        }

        self.assertEqual(SMOKE.validate_watchlist(payload), ("NVDA", "BRK.B"))

    def test_watchlist_rejects_empty_or_duplicate_canonical_symbols(self) -> None:
        for items in (
            [],
            [{"code": "US.NVDA"}, {"code": "US.NVDA"}],
            [{"code": "NVDA"}],
            [{"code": "US."}],
        ):
            with self.subTest(items=items):
                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_watchlist(
                        {
                            "schemaVersion": "1",
                            "source": "moomoo",
                            "session": "healthy",
                            "items": items,
                        }
                    )

    def test_single_symbol_v2_never_reads_watchlist(self) -> None:
        sent = transport()
        operator = Operator()

        SMOKE.run_smoke(
            SMOKE.SmokeConfig(
                gateway_url="http://gateway",
                analysis_url="http://analysis",
                symbol="NVDA",
                interval="5m",
                snapshot_version="v2",
            ),
            request=sent,
            issue_pairing_code=operator.issue,
            revoke_device=operator.revoke,
            log=lambda line: None,
        )

        self.assertNotIn("watchlist", [call["stage"] for call in sent.calls])
        self.assertEqual(
            [call["url"].split("?", 1)[0] for call in sent.calls if call["stage"] == "gateway_snapshot"],
            ["http://gateway/stock-snapshot"],
        )

    def test_v3_unavailable_holdings_may_keep_only_received_at(self) -> None:
        payload = snapshot_v3_payload("AVGO")
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

        facts = SMOKE.validate_snapshot_v3(
            payload,
            expected_symbol="AVGO",
            expected_interval="day",
            expected_count=250,
        )

        self.assertEqual(facts.snapshot_status, "partial")

    def test_v3_stale_requires_null_times_and_live_requires_complete_times(self) -> None:
        mutations = []
        payload = snapshot_v3_payload("AVGO")
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
                "methodVersion": "unavailable-v1",
            }
        )
        mutations.append(("stale-with-receipt", payload))
        payload = snapshot_v3_payload("AVGO")
        payload["sections"]["quote"]["asOf"] = None
        mutations.append(("live-with-missing-as-of", payload))

        for case, payload in mutations:
            with self.subTest(case=case):
                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_rejects_a_future_decision_cutoff(self) -> None:
        payload = snapshot_v3_payload("AVGO")
        payload["decisionCutoff"] = "2026-07-25T12:00:01Z"

        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.validate_snapshot_v3(
                payload,
                expected_symbol="AVGO",
                expected_interval="day",
                expected_count=250,
                now=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
            )

    def test_v3_rejects_an_extra_top_level_field(self) -> None:
        payload = snapshot_v3_payload("AVGO")
        payload["extra"] = True

        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.validate_snapshot_v3(
                payload,
                expected_symbol="AVGO",
                expected_interval="day",
                expected_count=250,
            )

    def test_v3_validated_sections_require_provenance_data_and_method(self) -> None:
        for field_name, value in (
            ("source", None),
            ("data", None),
            ("methodVersion", ""),
        ):
            with self.subTest(field=field_name):
                payload = snapshot_v3_payload("AVGO")
                holdings = payload["sections"]["holdings"]
                holdings.update(
                    {
                        "availabilityStatus": "delayed",
                        "qualityStatus": "validated",
                        "errorCode": None,
                        "reason": None,
                        "warnings": [],
                        "anomalies": [],
                    }
                )
                holdings[field_name] = value
                payload["status"] = "live"

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_section_availability_states_enforce_the_mobile_contract(self) -> None:
        mutations: list[tuple[str, dict[str, Any]]] = []

        payload = snapshot_v3_payload("AVGO")
        payload["sections"]["quote"]["qualityStatus"] = "invalid"
        mutations.append(("live-invalid", payload))

        payload = snapshot_v3_payload("AVGO")
        payload["sections"]["holdings"]["source"] = None
        mutations.append(("delayed-without-source", payload))

        for field_name, value in (
            ("qualityStatus", "partial"),
            ("source", "moomoo"),
            ("data", {}),
            ("errorCode", None),
            ("reason", None),
        ):
            payload = snapshot_v3_payload("AVGO")
            payload["sections"]["currentSessionFlow"].update(
                {
                    "availabilityStatus": "stale",
                    "qualityStatus": "invalid",
                    "source": None,
                    "asOf": None,
                    "availableAt": None,
                    "receivedAt": None,
                    "data": None,
                    "errorCode": "STALE_DATA",
                    "reason": "provider-message-canary",
                    "methodVersion": "unavailable-v1",
                }
            )
            payload["sections"]["currentSessionFlow"][field_name] = value
            mutations.append((f"stale-{field_name}", payload))

        for field_name, value in (
            ("qualityStatus", "partial"),
            ("data", {}),
            ("errorCode", None),
            ("reason", None),
        ):
            payload = snapshot_v3_payload("AVGO")
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
                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_warning_strings_must_be_non_empty(self) -> None:
        for warning in ("", "   ", 1):
            with self.subTest(warning=warning):
                payload = snapshot_v3_payload("AVGO")
                payload["sections"]["technical"]["warnings"] = [warning]

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_anomaly_shape_is_validated_in_every_section(self) -> None:
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
                payload = snapshot_v3_payload("AVGO")
                payload["sections"]["technical"]["anomalies"] = [anomaly]

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_validated_quote_must_be_semantically_usable(self) -> None:
        for price in (None, True, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(price=price):
                payload = snapshot_v3_payload("AVGO")
                payload["sections"]["quote"]["data"]["price"] = price

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_quote_contract_matches_the_mobile_decoder(self) -> None:
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
                payload = snapshot_v3_payload("AVGO")
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_candle_contract_matches_the_mobile_decoder(self) -> None:
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
                payload = snapshot_v3_payload("AVGO")
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

                with self.assertRaises(SMOKE.StageFailure):
                    SMOKE.validate_snapshot_v3(
                        payload,
                        expected_symbol="AVGO",
                        expected_interval="day",
                        expected_count=250,
                    )

    def test_v3_candle_section_available_at_is_the_maximum_row_availability(
        self,
    ) -> None:
        payload = snapshot_v3_payload("AVGO")
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

        SMOKE.validate_snapshot_v3(
            payload,
            expected_symbol="AVGO",
            expected_interval="day",
            expected_count=250,
        )

    def test_v3_empty_validated_candles_make_the_snapshot_partial(self) -> None:
        payload = snapshot_v3_payload("AVGO")
        payload["sections"]["candles"]["data"]["candles"] = []
        payload["sections"]["holdings"]["qualityStatus"] = "validated"
        payload["sections"]["holdings"]["anomalies"] = []
        payload["status"] = "live"

        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.validate_snapshot_v3(
                payload,
                expected_symbol="AVGO",
                expected_interval="day",
                expected_count=250,
            )

        payload["status"] = "partial"
        facts = SMOKE.validate_snapshot_v3(
            payload,
            expected_symbol="AVGO",
            expected_interval="day",
            expected_count=250,
        )
        self.assertEqual(facts.snapshot_status, "partial")

    def test_v3_live_validated_holdings_must_be_non_empty(self) -> None:
        payload = snapshot_v3_payload("AVGO")
        payload["sections"]["holdings"].update(
            {"qualityStatus": "validated", "data": [], "anomalies": []}
        )
        payload["status"] = "live"

        with self.assertRaises(SMOKE.StageFailure):
            SMOKE.validate_snapshot_v3(
                payload,
                expected_symbol="AVGO",
                expected_interval="day",
                expected_count=250,
            )


class BatchLifecycleAndReportTests(unittest.TestCase):
    def run_batch(
        self,
        sent: BatchTransport,
        *,
        config: Any | None = None,
        operator: Operator | None = None,
    ) -> tuple[list[str], Operator]:
        lines: list[str] = []
        operator = operator or Operator(code="pairing-code-canary")
        SMOKE.run_smoke(
            config or batch_config(),
            request=sent,
            issue_pairing_code=operator.issue,
            revoke_device=operator.revoke,
            log=lines.append,
        )
        return lines, operator

    def test_46_sources_issue_and_redeem_once_then_run_46_pairs(self) -> None:
        codes = [f"US.S{index}" for index in range(46)]
        sent = BatchTransport(codes)

        _, operator = self.run_batch(sent)

        stages = [call["stage"] for call in sent.calls]
        self.assertEqual(len(operator.issued_labels), 1)
        self.assertEqual(stages.count("redeem_pairing_code"), 1)
        self.assertEqual(stages.count("gateway_snapshot"), 46)
        self.assertEqual(stages.count("decision"), 46)
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_anomalous_holdings_and_stale_optional_flow_do_not_block_price(self) -> None:
        sent = BatchTransport(["US.AVGO"], stale_flow=True)

        lines, _ = self.run_batch(sent)

        self.assertTrue(any(line.startswith("PASS") for line in lines))

    def test_decision_interval_mismatch_fails_and_revokes(self) -> None:
        sent = BatchTransport(["US.NVDA"], decision_interval="5m")
        operator = Operator()

        with self.assertRaises(SMOKE.StageFailure):
            self.run_batch(sent, operator=operator)

        self.assertEqual(operator.revoked, ["dev-1"])

    def test_runtime_failure_and_interrupt_each_revoke_exactly_once(self) -> None:
        for failure in (RuntimeError("runtime-canary"), KeyboardInterrupt("interrupt-canary")):
            with self.subTest(failure=type(failure).__name__):
                sent = BatchTransport(
                    ["US.NVDA"],
                    fail_stage="analysis_health",
                    failure=failure,
                )
                operator = Operator()
                with self.assertRaises(type(failure)):
                    self.run_batch(sent, operator=operator)
                self.assertEqual(operator.revoked, ["dev-1"])

    def test_cleanup_revokes_when_the_log_sink_itself_fails(self) -> None:
        for failure in (RuntimeError("log-canary"), KeyboardInterrupt("log-canary")):
            with self.subTest(failure=type(failure).__name__):
                sent = BatchTransport(["US.NVDA"])
                operator = Operator()

                def log(line: str) -> None:
                    if line == "stage=revoke_smoke_device":
                        raise failure

                with self.assertRaises(type(failure)):
                    SMOKE.run_smoke(
                        batch_config(),
                        request=sent,
                        issue_pairing_code=operator.issue,
                        revoke_device=operator.revoke,
                        log=log,
                    )

                self.assertEqual(operator.revoked, ["dev-1"])

    def test_report_write_failure_still_revokes_exactly_once(self) -> None:
        sent = BatchTransport(["US.NVDA"])
        operator = Operator()
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            report_directory = Path(directory) / "report-target"
            report_directory.mkdir()
            with self.assertRaises(SMOKE.StageFailure):
                self.run_batch(
                    sent,
                    config=batch_config(report_path=report_directory),
                    operator=operator,
                )

        self.assertEqual(operator.revoked, ["dev-1"])

    def test_a_report_write_failure_does_not_bury_a_real_stage_failure(self) -> None:
        # A report the caller cannot write must not outrank the reason the
        # run actually failed: the operator has to be pointed at the quota
        # exhaustion _blame exists to surface, not sent chasing a
        # report_write red herring while it travels along in also_failed.
        sent = BatchTransport(
            ["US.NVDA"],
            fail_stage="decision",
            failure=SMOKE.StageFailure(
                "decision", "refused", http_status=429, server_code="QUOTA_EXCEEDED"
            ),
        )
        operator = Operator()
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            report_directory = Path(directory) / "report-target"
            report_directory.mkdir()
            with self.assertRaises(SMOKE.StageFailure) as caught:
                self.run_batch(
                    sent,
                    config=batch_config(report_path=report_directory),
                    operator=operator,
                )

        self.assertEqual(caught.exception.stage, "decision")
        self.assertEqual(caught.exception.server_code, "QUOTA_EXCEEDED")
        self.assertIn("report_write", caught.exception.render())
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_report_is_private_ordered_and_contains_only_allowlisted_facts(self) -> None:
        sent = BatchTransport(["US.AVGO", "US.NVDA"], stale_flow=True)
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            report_path = Path(directory) / "report.json"
            lines, operator = self.run_batch(
                sent,
                config=batch_config(
                    report_path=report_path,
                    gateway_token="gateway-token-canary",
                ),
                operator=Operator(code="pairing-code-canary"),
            )
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)

            self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)
            self.assertEqual([item["symbol"] for item in report["items"]], ["AVGO", "NVDA"])
            self.assertEqual(len(report["items"]), 2)
            self.assertEqual(report["snapshotVersion"], "v3")
            self.assertEqual(report["interval"], "day")
            self.assertEqual(report["items"][0]["decision"]["interval"], "day")
            self.assertEqual(
                report["items"][0]["snapshot"]["sections"]["currentSessionFlow"],
                {
                    "availabilityStatus": "stale",
                    "qualityStatus": "invalid",
                    "errorCode": "STALE_DATA",
                },
            )
            joined = "\n".join(lines) + report_text
            for canary in (
                "pairing-code-canary",
                "device-token-canary",
                "gateway-token-canary",
                "provider-message-canary",
                "warning-canary",
                "Authorization",
            ):
                self.assertNotIn(canary, joined)
            self.assertEqual(operator.revoked, ["dev-1"])

    def test_report_path_outside_tmp_is_rejected_before_pairing(self) -> None:
        sent = BatchTransport(["US.NVDA"])
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure):
            self.run_batch(
                sent,
                config=batch_config(report_path=REPOSITORY_ROOT / "report.json"),
                operator=operator,
            )
        self.assertEqual(operator.issued_labels, [])
        self.assertEqual(operator.revoked, [])

    def test_unknown_section_and_anomaly_codes_never_enter_failure_report(self) -> None:
        canaries = ("section-error-canary", "anomaly-code-canary")
        sent = BatchTransport(
            ["US.AVGO"],
            stale_flow=True,
            section_error_code=canaries[0],
            anomaly_code=canaries[1],
        )
        operator = Operator()
        lines: list[str] = []
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            report_path = Path(directory) / "report.json"
            with self.assertRaises(SMOKE.StageFailure):
                SMOKE.run_smoke(
                    batch_config(report_path=report_path),
                    request=sent,
                    issue_pairing_code=operator.issue,
                    revoke_device=operator.revoke,
                    log=lines.append,
                )
            serialized = "\n".join(lines) + report_path.read_text(encoding="utf-8")

        for canary in canaries:
            self.assertNotIn(canary, serialized)
        self.assertEqual(operator.revoked, ["dev-1"])

    def test_success_output_never_names_environment_keys(self) -> None:
        sent = transport()
        lines, _ = run(sent)

        self.assertNotIn("MOOMOO_GATEWAY_TOKEN", "\n".join(lines))

    def test_help_output_never_names_environment_keys(self) -> None:
        help_text = SMOKE.build_parser().format_help()
        for environment_key in (
            "MOOMOO_GATEWAY_TOKEN",
            "ANALYSIS_API_CANDLE_COUNT",
        ):
            self.assertNotIn(environment_key, help_text)

    def test_all_origins_reject_secret_bearing_urls_before_any_side_effect(
        self,
    ) -> None:
        secret = "origin-secret-canary"
        bad_urls = (
            f"http://user:{secret}@service",
            f"http://service?token={secret}",
            f"http://service#{secret}",
            f"http://service/path/{secret}",
            f"http://service\n{secret}",
            f"http://service {secret}",
            f"http://service\t{secret}",
            f"http://service\x00{secret}",
        )
        for field_name in (
            "gateway_url",
            "analysis_url",
            "phone_gateway_url",
        ):
            for shape_index, bad_url in enumerate(bad_urls):
                with self.subTest(field=field_name, shape=shape_index):
                    lines: list[str] = []
                    calls: list[str] = []
                    operator = Operator()

                    def no_network(*args: Any, **kwargs: Any) -> Any:
                        calls.append("called")
                        raise AssertionError("network must not run")

                    try:
                        with self.assertRaises(SMOKE.StageFailure):
                            SMOKE.run_smoke(
                                batch_config(**{field_name: bad_url}),
                                request=no_network,
                                issue_pairing_code=operator.issue,
                                revoke_device=operator.revoke,
                                log=lines.append,
                            )
                    finally:
                        self.assertNotIn(secret, "\n".join(lines))
                        self.assertEqual(calls, [])
                        self.assertEqual(operator.issued_labels, [])
                        self.assertEqual(operator.revoked, [])


class CanaryFailureSurfaceTests(unittest.TestCase):
    def test_main_sanitizes_stage_runtime_and_interrupt_failures(self) -> None:
        canary = "failure-surface-canary"
        failures: tuple[BaseException, ...] = (
            SMOKE.StageFailure(
                "decision",
                canary,
                server_message=canary,
                cause=RuntimeError(canary),
            ),
            RuntimeError(canary),
            KeyboardInterrupt(canary),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                out, err = io.StringIO(), io.StringIO()

                def broken(*args: Any, **kwargs: Any) -> None:
                    raise failure

                self.assertEqual(
                    SMOKE.main([], runner=broken, stdout=out, stderr=err),
                    1,
                )
                self.assertNotIn(canary, out.getvalue() + err.getvalue())

    def test_environment_canary_is_not_printed(self) -> None:
        canary = "environment-value-canary"
        previous = os.environ.get("MOOMOO_GATEWAY_TOKEN")
        os.environ["MOOMOO_GATEWAY_TOKEN"] = canary
        try:
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(
                SMOKE.main(
                    [],
                    runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                        RuntimeError(canary)
                    ),
                    stdout=out,
                    stderr=err,
                ),
                1,
            )
            self.assertNotIn(canary, out.getvalue() + err.getvalue())
        finally:
            if previous is None:
                os.environ.pop("MOOMOO_GATEWAY_TOKEN", None)
            else:
                os.environ["MOOMOO_GATEWAY_TOKEN"] = previous


if __name__ == "__main__":
    unittest.main()
