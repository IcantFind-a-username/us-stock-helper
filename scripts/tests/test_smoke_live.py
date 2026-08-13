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
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/smoke_live.py"
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
        SMOKE.SmokeConfig(gateway_url="http://gateway", analysis_url="http://analysis"),
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
        rendered = caught.exception.render()
        self.assertIn("rsi", rendered)
        self.assertIn("79", rendered)
        self.assertIn("80", rendered)

    def test_rejects_a_series_that_was_never_measured(self) -> None:
        payload = snapshot_payload()
        payload["indicators"]["ma5"]["series"] = [None] * 80
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("ma5", caught.exception.render())

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
        self.assertIn("seriesAlignedTo", caught.exception.render())

    def test_rejects_a_missing_indicator(self) -> None:
        payload = snapshot_payload()
        del payload["indicators"]["ma20"]
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        rendered = caught.exception.render()
        self.assertIn("ma20", rendered)
        # An indicator that is absent has to read as absent. "not an object" is
        # what a reader would chase into a serializer that is working fine.
        self.assertIn("absent", rendered)

    def test_rejects_an_empty_candle_series(self) -> None:
        payload = snapshot_payload()
        payload["completedCandles"] = []
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("completedCandles", caught.exception.render())

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
        self.assertIn("order", caught.exception.render())

    def test_rejects_an_incomplete_candle(self) -> None:
        payload = snapshot_payload()
        payload["completedCandles"][-1]["complete"] = False
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("complete", caught.exception.render())

    def test_rejects_a_snapshot_for_another_symbol(self) -> None:
        payload = snapshot_payload()
        payload["symbol"] = "AAPL"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            SMOKE.validate_snapshot(
                payload, expected_symbol="NVDA", expected_interval="5m"
            )
        self.assertIn("AAPL", caught.exception.render())


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
        rendered = caught.exception.render()
        self.assertIn("unavailable", rendered)
        self.assertIn("No completed candles", rendered)

    def test_rejects_a_null_score(self) -> None:
        payload = decision_payload()
        payload["score"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("score", caught.exception.render())

    def test_rejects_a_score_with_no_value(self) -> None:
        payload = decision_payload()
        payload["score"]["value"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("score.value", caught.exception.render())

    def test_rejects_an_unknown_direction(self) -> None:
        payload = decision_payload()
        payload["score"]["direction"] = "sideways"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("sideways", caught.exception.render())

    def test_rejects_a_coverage_of_zero(self) -> None:
        payload = decision_payload()
        payload["score"]["factorCoverage"] = 0.0
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("factorCoverage", caught.exception.render())

    def test_rejects_an_unmeasured_coverage(self) -> None:
        payload = decision_payload()
        payload["score"]["factorCoverage"] = None
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        rendered = caught.exception.render()
        self.assertIn("factorCoverage", rendered)
        # Coverage that was never measured is a different fact from coverage
        # that came out at zero, and the report has to say which one it is.
        self.assertIn("not measured", rendered)

    def test_rejects_an_empty_contribution_list(self) -> None:
        payload = decision_payload()
        payload["score"]["contributions"] = []
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("contributions", caught.exception.render())

    def test_rejects_an_answer_for_another_symbol(self) -> None:
        payload = decision_payload()
        payload["symbol"] = "AAPL"
        with self.assertRaises(SMOKE.StageFailure) as caught:
            self.validate(payload)
        self.assertIn("AAPL", caught.exception.render())

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
        self.assertIn("1.23", caught.exception.render())

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
    def test_names_the_stage_the_status_the_server_code_and_the_local_error(self) -> None:
        cause = ValueError("connection reset")
        failure = SMOKE.StageFailure(
            "decision",
            "the analysis service refused the decision request",
            url="http://analysis/decision?symbol=NVDA",
            http_status=500,
            server_code="ANALYSIS_FAILED",
            server_message="The decision chain could not be evaluated",
            cause=cause,
        )
        rendered = failure.render()
        self.assertIn("stage=decision", rendered)
        self.assertIn("http_status: 500", rendered)
        self.assertIn("server_code: ANALYSIS_FAILED", rendered)
        self.assertIn("ValueError", rendered)
        self.assertIn("connection reset", rendered)
        self.assertIn("http://analysis/decision?symbol=NVDA", rendered)

    def test_distinguishes_a_field_that_does_not_apply_from_one_left_blank(self) -> None:
        rendered = SMOKE.StageFailure("issue_pairing_code", "the terminal failed").render()
        self.assertIn("http_status: none", rendered)
        self.assertIn("server_code: none", rendered)
        self.assertIn("local_exception: none", rendered)


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
                    gateway_url="http://gateway", analysis_url="http://analysis"
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
                    gateway_url="http://gateway", analysis_url="http://analysis"
                ),
                request=sent,
                issue_pairing_code=operator.issue,
                revoke_device=operator.revoke,
                log=lines.append,
            )
        self.assertEqual(caught.exception.stage, "decision")
        self.assertTrue(any("sqlite is locked" in line for line in lines))

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
        self.assertIn("degraded", caught.exception.render())
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
        self.assertIn("unhealthy", caught.exception.render())

    def test_refuses_an_analysis_service_that_is_not_ready(self) -> None:
        sent = transport(
            {("GET", "http://analysis/health"): {"status": "starting"}}
        )
        operator = Operator()
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(sent, operator)
        self.assertEqual(caught.exception.stage, "analysis_health")
        self.assertIn("starting", caught.exception.render())
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
        self.assertIn("deviceToken", caught.exception.render())


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

    def test_names_every_other_stage_that_failed_with_its_code(self) -> None:
        with self.assertRaises(SMOKE.StageFailure) as caught:
            run(self.both_failing())
        rendered = caught.exception.render()
        self.assertIn("also_failed", rendered)
        self.assertIn("decision", rendered)
        self.assertIn("ANALYSIS_FAILED", rendered)
        self.assertIn("500", rendered)

    def test_prints_every_failure_in_full_not_as_a_one_line_summary(self) -> None:
        # A one-line summary drops the status and the service's own code, which
        # is exactly what a reader needs from a stage that is not the one being
        # blamed. Both failures have to appear in full, whichever is raised.
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
        self.assertIn("ANALYSIS_FAILED", joined)
        self.assertIn("http_status: 500", joined)
        self.assertIn("QUOTA_EXCEEDED", joined)
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
        self.assertIn("DATABASE_UNREADABLE", rendered)


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

    def test_quotes_the_terminal_when_the_pair_command_fails(self) -> None:
        issue, _, _ = self.terminal((2, "", "DATABASE_UNREADABLE: refusing a shared file"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            issue("smoke")
        rendered = caught.exception.render()
        self.assertEqual(caught.exception.stage, "issue_pairing_code")
        self.assertIn("DATABASE_UNREADABLE", rendered)

    def test_revocation_failure_names_its_own_stage(self) -> None:
        _, revoke, _ = self.terminal((1, "", "unknown-device: dev-9"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            revoke("dev-9")
        self.assertEqual(caught.exception.stage, "revoke_smoke_device")
        self.assertIn("unknown-device", caught.exception.render())


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
        self.assertIn("ANALYSIS_FAILED", printed)
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
        self.assertIn("Connection refused", err.getvalue())


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
        self.assertIn("AUTH_REQUIRED", rendered)
        self.assertIn("A paired device token is required", rendered)

    def test_states_the_local_exception_when_nothing_answered(self) -> None:
        request = SMOKE.http_transport(
            timeout=1.0, opener=_raiser(OSError("Connection refused"))
        )
        with self.assertRaises(SMOKE.StageFailure) as caught:
            request("gateway_health", "GET", "http://gateway/health")
        rendered = caught.exception.render()
        self.assertIn("Connection refused", rendered)
        self.assertIn("http_status: none", rendered)

    def test_names_the_stage_when_a_service_answers_with_something_else(self) -> None:
        request = SMOKE.http_transport(timeout=1.0, opener=_answering(b"<html>hi</html>"))
        with self.assertRaises(SMOKE.StageFailure) as caught:
            request("analysis_health", "GET", "http://analysis/health")
        self.assertEqual(caught.exception.stage, "analysis_health")
        self.assertIn("JSON", caught.exception.render())


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


if __name__ == "__main__":
    unittest.main()
