from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import unittest

from adviser_layer.council import AdviserOpinion
from adviser_layer.council import InvalidAdviserOutput
from decision_engine import DecisionEngine, DecisionInputs
from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from us_stock_helper_core import (
    AnalyticalAction,
    HardGate,
    Horizon,
    OHLCVBar,
    RiskPreference,
)


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)


def bars() -> tuple[OHLCVBar, ...]:
    rows = []
    for index in range(40):
        closed_at = AS_OF - timedelta(minutes=(39 - index) * 5)
        price = 100 + index * 0.5
        rows.append(
            OHLCVBar(
                symbol="NVDA",
                interval="5m",
                opened_at=closed_at - timedelta(minutes=5),
                closed_at=closed_at,
                available_at=closed_at,
                open=price - 0.2,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=1_000_000,
            )
        )
    return tuple(rows)


def event(
    event_id: str,
    *,
    status: ClaimStatus,
    publisher: str = "sec",
    sentiment: float = 0.7,
    available_at: datetime = AS_OF - timedelta(minutes=2),
    symbols: tuple[tuple[str, float], ...] = (("NVDA", 0.9),),
) -> EvidenceEvent:
    return EvidenceEvent.create(
        event_id=event_id,
        claim_key=f"claim-{event_id}",
        headline=f"Evidence {event_id}",
        summary="Point-in-time evidence.",
        provenance=SourceProvenance(
            source_id=publisher,
            publisher_id=publisher,
            publisher_name=publisher.upper(),
            canonical_url=f"https://example.com/{event_id}",
            source_type="regulatory_filing" if publisher == "sec" else "news",
            reliability=0.98 if publisher == "sec" else 0.85,
        ),
        event_time=available_at - timedelta(minutes=3),
        published_at=available_at - timedelta(minutes=2),
        first_seen_at=available_at - timedelta(minutes=1),
        available_at=available_at,
        retrieved_at=available_at,
        claim_status=status,
        sentiment=sentiment,
        confidence=0.95,
        symbol_relevance=symbols,
    )


def inputs(
    evidence: tuple[EvidenceEvent, ...],
    *,
    preference: RiskPreference = RiskPreference.BALANCED,
) -> DecisionInputs:
    return DecisionInputs(
        symbol="NVDA",
        horizon=Horizon.SHORT,
        as_of=AS_OF,
        bars=bars(),
        evidence=evidence,
        current_price=119.5,
        current_price_available_at=AS_OF,
        annualized_volatility=0.45,
        volatility_available_at=AS_OF,
        macro=0.1,
        geopolitics=-0.2,
        institutional_flow=0.3,
        fundamentals=0.4,
        risk_preference=preference,
        invalidation_conditions=("Closed bar breaks the evidence-defined level.",),
        adviser_focus=("tail-risk",),
    )


class DecisionEngineTests(unittest.TestCase):
    def test_verified_point_in_time_evidence_flows_to_traceable_analysis(self) -> None:
        output = DecisionEngine().evaluate(
            inputs((event("filing", status=ClaimStatus.VERIFIED),))
        )

        self.assertTrue(output.baseline_score.actionable)
        self.assertEqual(output.forecast.calibration_status.value, "uncalibrated")
        self.assertTrue(output.forecast.citation_ids)
        self.assertIn(output.risk_plan.action, {
            AnalyticalAction.LONG,
            AnalyticalAction.WATCH,
        })

    def test_rumor_or_future_evidence_cannot_enable_an_action(self) -> None:
        rumor = event("rumor", status=ClaimStatus.RUMOR, publisher="social")
        future = event(
            "future",
            status=ClaimStatus.VERIFIED,
            available_at=AS_OF + timedelta(seconds=1),
        )

        output = DecisionEngine().evaluate(inputs((rumor, future)))

        self.assertFalse(output.adjusted_score.actionable)
        self.assertIn(
            HardGate.INSUFFICIENT_EVIDENCE,
            output.adjusted_score.blocked_by,
        )
        self.assertEqual(output.risk_plan.action, AnalyticalAction.AVOID)
        self.assertEqual(output.evidence_packet.excluded_future_event_ids, ("future",))

    def test_adviser_is_bounded_and_cannot_bypass_a_hard_gate(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED)
        opinion = AdviserOpinion(
            adviser_id="taleb",
            direction="bullish",
            confidence=1.0,
            score_adjustment=3.0,
            thesis="Evidence supports the bounded favorable case.",
            counterargument="Tail risk remains material.",
            citation_ids=("filing",),
            missing_evidence=("options skew",),
            abstained=False,
        )
        gated_inputs = replace(
            inputs((filing,)),
            hard_gates=(HardGate.LOW_LIQUIDITY,),
        )

        output = DecisionEngine().evaluate(
            gated_inputs,
            adviser_opinions=(opinion,),
        )

        self.assertEqual(output.adviser_adjustment, 0.0)
        self.assertFalse(output.adjusted_score.actionable)
        self.assertEqual(output.risk_plan.action, AnalyticalAction.AVOID)

    def test_rumor_inside_confirmed_cluster_cannot_move_the_analysis_score(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED, sentiment=-0.5)
        rumor = replace(
            event(
                "rumor",
                status=ClaimStatus.RUMOR,
                publisher="social",
                sentiment=1.0,
                available_at=AS_OF - timedelta(minutes=1),
            ),
            claim_key=filing.claim_key,
        )

        baseline = DecisionEngine().evaluate(inputs((filing,)))
        mixed = DecisionEngine().evaluate(inputs((filing, rumor)))

        self.assertEqual(
            mixed.baseline_score.objective_score,
            baseline.baseline_score.objective_score,
        )
        cited_events = {
            citation.event_id
            for citation in mixed.evidence_packet.citations
            if citation.citation_id in mixed.forecast.citation_ids
        }
        self.assertNotIn("rumor", cited_events)

    def test_adviser_cannot_cite_observational_rumor_as_decision_evidence(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED)
        rumor = replace(
            event(
                "rumor",
                status=ClaimStatus.RUMOR,
                publisher="social",
                available_at=AS_OF - timedelta(minutes=1),
            ),
            claim_key=filing.claim_key,
        )
        opinion = AdviserOpinion(
            adviser_id="taleb",
            direction="neutral",
            confidence=0.5,
            score_adjustment=0.0,
            thesis="The rumor is uncertain.",
            counterargument="The filing is authoritative.",
            citation_ids=("rumor",),
            missing_evidence=("independent confirmation",),
            abstained=False,
        )

        with self.assertRaises(InvalidAdviserOutput):
            DecisionEngine().evaluate(
                inputs((filing, rumor)),
                adviser_opinions=(opinion,),
            )

    def test_risk_preference_changes_sizing_not_objective_score(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED)
        conservative = DecisionEngine().evaluate(
            inputs((filing,), preference=RiskPreference.CONSERVATIVE)
        )
        aggressive = DecisionEngine().evaluate(
            inputs((filing,), preference=RiskPreference.AGGRESSIVE)
        )

        self.assertEqual(
            conservative.adjusted_score.objective_score,
            aggressive.adjusted_score.objective_score,
        )
        self.assertLess(
            conservative.risk_plan.max_position_percent,
            aggressive.risk_plan.max_position_percent,
        )

    def test_future_price_or_volatility_snapshot_is_rejected(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED)
        for field_name in (
            "current_price_available_at",
            "volatility_available_at",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, "after as_of"):
                    DecisionEngine().evaluate(
                        replace(
                            inputs((filing,)),
                            **{field_name: AS_OF + timedelta(microseconds=1)},
                        )
                    )

    def test_stale_short_horizon_price_snapshot_blocks_action(self) -> None:
        filing = event("filing", status=ClaimStatus.VERIFIED)

        output = DecisionEngine().evaluate(
            replace(
                inputs((filing,)),
                current_price_available_at=AS_OF - timedelta(minutes=21),
            )
        )

        self.assertIn(HardGate.STALE_DATA, output.adjusted_score.blocked_by)
        self.assertEqual(output.risk_plan.action, AnalyticalAction.AVOID)


if __name__ == "__main__":
    unittest.main()


class AdviserCapConsistencyTests(unittest.TestCase):
    def test_the_engine_uses_the_scoring_layer_adviser_cap(self) -> None:
        import inspect

        from us_stock_helper_core.scoring import ADVISER_SCORE_CAP
        from decision_engine import engine as engine_module

        source = inspect.getsource(engine_module)
        # The cap and the normalization divisor must both come from the shared
        # constant; a repeated literal is how the layers drifted apart before.
        self.assertIn("council_cap=ADVISER_SCORE_CAP", source)
        self.assertIn("ADVISER_SCORE_CAP", source)
        self.assertNotIn("council_cap=3.0", source)
        self.assertNotIn("/ 3.0", source)
        self.assertEqual(ADVISER_SCORE_CAP, 3.0)
