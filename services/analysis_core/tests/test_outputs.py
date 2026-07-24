from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
import random
import unittest

from us_stock_helper_core.evidence import freeze_evidence_packet
from us_stock_helper_core.forecasting import (
    CalibrationStatus,
    ScenarioKind,
    build_scenario_forecast,
)
from us_stock_helper_core.models import (
    Direction,
    EvidenceKind,
    EvidenceRecord,
    Horizon,
    RiskPreference,
)
from us_stock_helper_core.risk import (
    AnalyticalAction,
    ShortBorrowSnapshot,
    build_risk_plan,
)
from us_stock_helper_core.scoring import FeatureSet, HardGate, score_horizon


AS_OF = datetime(2026, 7, 24, 20, tzinfo=UTC)


def record(
    evidence_id: str,
    *,
    series_id: str | None = None,
    symbol: str = "NVDA",
    kind: EvidenceKind = EvidenceKind.NEWS,
    available_at: datetime = AS_OF - timedelta(minutes=10),
    revision: int = 1,
    sentiment: float = 0.2,
    claim_key: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        series_id=series_id or evidence_id,
        symbol=symbol,
        kind=kind,
        source_name="Primary source",
        source_url=f"https://example.com/{evidence_id}",
        headline=f"Evidence {evidence_id}",
        event_time=AS_OF - timedelta(hours=2),
        published_at=AS_OF - timedelta(hours=1),
        first_seen_at=AS_OF - timedelta(hours=1) + timedelta(seconds=5),
        available_at=available_at,
        revision=revision,
        sentiment=sentiment,
        confidence=0.9,
        claim_key=claim_key,
    )


def score(sign: float = 1.0, *, gates: tuple[HardGate, ...] = ()):
    features = FeatureSet(
        as_of=AS_OF,
        horizon=Horizon.SHORT,
        technical_trend=0.8 * sign,
        momentum=0.8 * sign,
        pattern=0.7 * sign,
        market_sentiment=0.7 * sign,
        macro=0.4 * sign,
        geopolitics=0.2 * sign,
        institutional_flow=0.6 * sign,
        fundamentals=0.5 * sign,
        adviser_factor=0.0,
        evidence_confidence=0.9,
        latest_market_data_at=AS_OF,
    )
    return score_horizon(features, gates)


def forecast_for(sign: float = 1.0, *, gates: tuple[HardGate, ...] = ()):
    return build_scenario_forecast(
        score(sign, gates=gates),
        current_price=100.0,
        annualized_volatility=0.4,
        invalidation_conditions=("Price closes through the evidence-defined invalidation level.",),
        citation_ids=("quote", "news"),
    )


class EvidencePacketTests(unittest.TestCase):
    def test_packet_freezes_only_information_available_at_cutoff(self) -> None:
        original = record(
            "guidance-v1", series_id="guidance", sentiment=0.5
        )
        correction = record(
            "guidance-v2",
            series_id="guidance",
            revision=2,
            sentiment=-0.3,
            available_at=AS_OF + timedelta(minutes=1),
        )
        other_symbol = record("tsla", symbol="TSLA")

        packet = freeze_evidence_packet(
            "NVDA",
            AS_OF,
            (correction, other_symbol, original),
            required_kinds=(EvidenceKind.NEWS, EvidenceKind.FILING),
        )

        self.assertEqual(
            [citation.evidence_id for citation in packet.citations],
            ["guidance-v1"],
        )
        self.assertEqual(packet.missing_kinds, (EvidenceKind.FILING,))
        with self.assertRaises(FrozenInstanceError):
            packet.symbol = "TSLA"  # type: ignore[misc]

    def test_packet_hash_is_reproducible_despite_input_order(self) -> None:
        records = [
            record("a", kind=EvidenceKind.NEWS),
            record("b", kind=EvidenceKind.FILING),
            record("c", kind=EvidenceKind.MACRO),
        ]
        expected = freeze_evidence_packet("NVDA", AS_OF, records)
        random.Random(4).shuffle(records)
        actual = freeze_evidence_packet("NVDA", AS_OF, records)

        self.assertEqual(actual, expected)
        self.assertEqual(len(actual.content_hash), 64)
        self.assertTrue(actual.packet_id.startswith("NVDA-"))

    def test_same_vendor_series_name_for_another_symbol_cannot_hide_citation(self) -> None:
        nvidia = record("nvda", series_id="guidance", symbol="NVDA")
        tesla = record(
            "tsla-revision",
            series_id="guidance",
            symbol="TSLA",
            revision=2,
        )

        packet = freeze_evidence_packet("NVDA", AS_OF, (nvidia, tesla))

        self.assertEqual(
            [citation.evidence_id for citation in packet.citations], ["nvda"]
        )

    def test_conflicting_cited_claims_are_explicit(self) -> None:
        packet = freeze_evidence_packet(
            "NVDA",
            AS_OF,
            (
                record("claim-positive", sentiment=0.7, claim_key="demand"),
                record(
                    "claim-negative",
                    kind=EvidenceKind.FILING,
                    sentiment=-0.6,
                    claim_key="demand",
                ),
            ),
        )

        self.assertEqual(len(packet.conflicts), 1)
        self.assertIn("demand", packet.conflicts[0])


class ScenarioForecastTests(unittest.TestCase):
    def test_forecast_is_three_probabilistic_ranges_not_a_promised_price(self) -> None:
        result = forecast_for()

        self.assertEqual(
            {case.kind for case in result.cases},
            {ScenarioKind.BEAR, ScenarioKind.BASE, ScenarioKind.BULL},
        )
        self.assertAlmostEqual(sum(case.probability for case in result.cases), 1.0)
        self.assertTrue(
            all(
                0.0 <= case.probability <= 1.0
                and 0.0 < case.price_low <= case.price_high
                for case in result.cases
            )
        )
        self.assertFalse(hasattr(result, "target_price"))
        self.assertIn("not promised", result.disclaimer)

    def test_directional_score_shifts_scenario_probability_without_certainty(self) -> None:
        bullish = forecast_for(1.0)
        bearish = forecast_for(-1.0)
        bull_probability = {
            case.kind: case.probability for case in bullish.cases
        }
        bear_probability = {
            case.kind: case.probability for case in bearish.cases
        }

        self.assertGreater(
            bull_probability[ScenarioKind.BULL],
            bull_probability[ScenarioKind.BEAR],
        )
        self.assertGreater(
            bear_probability[ScenarioKind.BEAR],
            bear_probability[ScenarioKind.BULL],
        )
        self.assertLess(max(bull_probability.values()), 0.8)

    def test_forecast_requires_invalidation_and_valid_market_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalidation"):
            build_scenario_forecast(
                score(),
                current_price=100.0,
                annualized_volatility=0.4,
                invalidation_conditions=(),
            )
        with self.assertRaisesRegex(ValueError, "volatility"):
            build_scenario_forecast(
                score(),
                current_price=100.0,
                annualized_volatility=-0.1,
                invalidation_conditions=("Invalidated",),
            )

    def test_calibration_status_is_never_inferred_or_overstated(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibration reference"):
            build_scenario_forecast(
                score(),
                current_price=100.0,
                annualized_volatility=0.4,
                calibration_status=CalibrationStatus.BACKTESTED,
                invalidation_conditions=("Invalidated",),
            )
        result = build_scenario_forecast(
            score(),
            current_price=100.0,
            annualized_volatility=0.4,
            calibration_status=CalibrationStatus.BACKTESTED,
            calibration_reference="walk-forward/NVDA-short-v3",
            invalidation_conditions=("Invalidated",),
        )
        default = forecast_for()
        self.assertEqual(result.calibration_status, CalibrationStatus.BACKTESTED)
        self.assertEqual(
            result.calibration_reference,
            "walk-forward/NVDA-short-v3",
        )
        self.assertEqual(default.calibration_status, CalibrationStatus.UNCALIBRATED)


class RiskPlanTests(unittest.TestCase):
    def test_risk_preference_changes_sizing_not_objective_analysis(self) -> None:
        objective = score()
        forecast = forecast_for()
        plans = [
            build_risk_plan(objective, forecast, preference=preference)
            for preference in RiskPreference
        ]

        self.assertEqual(
            {(plan.objective_score, plan.direction, plan.action) for plan in plans},
            {(objective.objective_score, objective.direction, AnalyticalAction.LONG)},
        )
        self.assertEqual(
            [plan.max_position_percent for plan in plans],
            [5.0, 10.0, 15.0],
        )
        self.assertEqual([plan.leverage for plan in plans], [1.0, 1.1, 1.5])

    def test_short_plan_fails_closed_without_current_borrow_availability(self) -> None:
        objective = score(-1.0)
        forecast = forecast_for(-1.0)

        unavailable = build_risk_plan(
            objective,
            forecast,
            preference=RiskPreference.AGGRESSIVE,
        )
        available = build_risk_plan(
            objective,
            forecast,
            preference=RiskPreference.AGGRESSIVE,
            short_borrow=ShortBorrowSnapshot(
                checked_at=AS_OF - timedelta(minutes=2),
                available=True,
                estimated_fee_percent=0.4,
                crowding="low",
                source="moomoo",
            ),
        )

        self.assertEqual(unavailable.action, AnalyticalAction.AVOID)
        self.assertIn(HardGate.BORROW_UNAVAILABLE, unavailable.blocked_by)
        self.assertIsNone(unavailable.entry_range)
        self.assertEqual(available.action, AnalyticalAction.SHORT)

    def test_short_plan_rejects_future_or_stale_borrow_checks(self) -> None:
        objective = score(-1.0)
        forecast = forecast_for(-1.0)
        for checked_at in (
            AS_OF + timedelta(seconds=1),
            AS_OF - timedelta(minutes=16),
        ):
            plan = build_risk_plan(
                objective,
                forecast,
                preference=RiskPreference.BALANCED,
                short_borrow=ShortBorrowSnapshot(
                    checked_at=checked_at,
                    available=True,
                    estimated_fee_percent=0.4,
                    crowding="low",
                    source="moomoo",
                ),
            )
            self.assertEqual(plan.action, AnalyticalAction.AVOID)
            self.assertIn(HardGate.BORROW_DATA_STALE, plan.blocked_by)

    def test_any_hard_gate_disables_action_and_leverage(self) -> None:
        objective = score(gates=(HardGate.STALE_DATA,))
        plan = build_risk_plan(
            objective,
            forecast_for(gates=(HardGate.STALE_DATA,)),
            preference=RiskPreference.AGGRESSIVE,
        )

        self.assertEqual(plan.action, AnalyticalAction.AVOID)
        self.assertEqual(plan.leverage, 1.0)
        self.assertEqual(plan.max_position_percent, 0.0)
        self.assertIsNone(plan.entry_range)

    def test_risk_plan_is_analysis_only_and_traceable(self) -> None:
        plan = build_risk_plan(
            score(),
            forecast_for(),
            preference=RiskPreference.BALANCED,
        )
        field_names = set(plan.__dataclass_fields__)

        self.assertFalse({"broker", "order_id", "submit_order"} & field_names)
        self.assertEqual(plan.citation_ids, ("quote", "news"))
        self.assertTrue(plan.warnings)


if __name__ == "__main__":
    unittest.main()
