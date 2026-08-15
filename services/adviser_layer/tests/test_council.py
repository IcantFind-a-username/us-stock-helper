from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta

from adviser_layer.council import (
    AdviserOpinion,
    CouncilRequest,
    EvidenceFact,
    InvalidAdviserOutput,
    aggregate_opinions,
    build_compact_packet,
    select_advisers,
    validate_opinion,
)
from adviser_layer.registry import ADVISER_PROFILES


NOW = datetime(2026, 7, 25, 16, 0, tzinfo=UTC)


def fact(
    fact_id: str,
    *,
    available_at: datetime = NOW - timedelta(minutes=1),
    credibility: float = 0.9,
    text: str = "Revenue guidance was raised.",
    symbols: tuple[str, ...] = (),
) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        text=text,
        citation_url=f"https://example.com/{fact_id}",
        available_at=available_at,
        credibility=credibility,
        is_counter_evidence=False,
        symbols=symbols,
    )


class RegistryTests(unittest.TestCase):
    def test_registry_contains_the_thirteen_public_style_lenses(self) -> None:
        self.assertEqual(len(ADVISER_PROFILES), 13)
        self.assertEqual(len({profile.id for profile in ADVISER_PROFILES}), 13)
        self.assertTrue(all(profile.style_disclaimer for profile in ADVISER_PROFILES))
        self.assertFalse(any("portfolio_manager" in profile.id for profile in ADVISER_PROFILES))

    def test_selection_is_horizon_and_question_specific_but_bounded(self) -> None:
        request = CouncilRequest(
            symbol="NVDA",
            horizon="short",
            as_of=NOW,
            baseline_score=67,
            baseline_direction="bullish",
            requested_focus=("macro", "tail-risk", "momentum"),
            facts=(fact("f1"),),
        )
        selected = select_advisers(request, maximum=4)

        self.assertLessEqual(len(selected), 4)
        self.assertIn("druckenmiller", {profile.id for profile in selected})
        self.assertIn("taleb", {profile.id for profile in selected})


class CompactPacketTests(unittest.TestCase):
    def test_packet_is_point_in_time_citation_first_and_token_bounded(self) -> None:
        request = CouncilRequest(
            symbol="NVDA",
            horizon="short",
            as_of=NOW,
            baseline_score=67,
            baseline_direction="bullish",
            requested_focus=("momentum",),
            facts=(
                fact("known"),
                fact("future", available_at=NOW + timedelta(seconds=1)),
                fact("long", text="A" * 3000),
            ),
        )

        packet = build_compact_packet(request, max_characters=900)
        decoded = json.loads(packet)

        self.assertEqual(decoded["symbol"], "NVDA")
        self.assertEqual(decoded["as_of"], NOW.isoformat())
        self.assertEqual([item["id"] for item in decoded["facts"]], ["known", "long"])
        self.assertNotIn("future", packet)
        self.assertLessEqual(len(packet), 900)
        self.assertNotIn("quantity", packet)
        self.assertNotIn("order", packet.lower())

    def test_packet_raises_when_no_evidence_was_available_at_cutoff(self) -> None:
        request = CouncilRequest(
            symbol="NVDA",
            horizon="short",
            as_of=NOW,
            baseline_score=50,
            baseline_direction="neutral",
            requested_focus=(),
            facts=(fact("future", available_at=NOW + timedelta(seconds=1)),),
        )

        with self.assertRaises(ValueError):
            build_compact_packet(request)

    def test_packet_cannot_include_facts_scoped_to_another_symbol(self) -> None:
        request = CouncilRequest(
            symbol="NVDA",
            horizon="short",
            as_of=NOW,
            baseline_score=50,
            baseline_direction="neutral",
            requested_focus=(),
            facts=(
                fact("global"),
                fact("nvda", symbols=("NVDA",)),
                fact("tesla", symbols=("TSLA",)),
            ),
        )

        decoded = json.loads(build_compact_packet(request))

        self.assertEqual(
            [item["id"] for item in decoded["facts"]],
            ["global", "nvda"],
        )


class OutputSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = CouncilRequest(
            symbol="NVDA",
            horizon="short",
            as_of=NOW,
            baseline_score=67,
            baseline_direction="bullish",
            requested_focus=("tail-risk",),
            facts=(fact("f1"), fact("f2")),
        )

    def test_opinion_must_only_cite_frozen_packet_and_adjustment_is_capped(self) -> None:
        valid = AdviserOpinion(
            adviser_id="taleb",
            direction="bearish",
            confidence=0.7,
            score_adjustment=-2.5,
            thesis="Tail risk remains elevated.",
            counterargument="Primary evidence remains constructive.",
            citation_ids=("f1",),
            missing_evidence=("options skew",),
            abstained=False,
        )
        checked = validate_opinion(valid, self.request, per_adviser_cap=3.0)
        self.assertEqual(checked, valid)

        with self.assertRaises(InvalidAdviserOutput):
            validate_opinion(
                AdviserOpinion(
                    **{**valid.__dict__, "citation_ids": ("not-in-packet",)}
                ),
                self.request,
            )
        with self.assertRaises(InvalidAdviserOutput):
            validate_opinion(
                AdviserOpinion(**{**valid.__dict__, "score_adjustment": 8.0}),
                self.request,
            )

    def test_low_credibility_or_insufficient_evidence_forces_abstention(self) -> None:
        weak_request = CouncilRequest(
            **{
                **self.request.__dict__,
                "facts": (fact("weak", credibility=0.2),),
            }
        )
        non_abstaining = AdviserOpinion(
            adviser_id="taleb",
            direction="bullish",
            confidence=0.9,
            score_adjustment=2,
            thesis="Buy.",
            counterargument="None.",
            citation_ids=("weak",),
            missing_evidence=(),
            abstained=False,
        )

        with self.assertRaises(InvalidAdviserOutput):
            validate_opinion(non_abstaining, weak_request)

    def test_council_is_a_bounded_soft_factor_and_cannot_flip_hard_gates(self) -> None:
        opinions = (
            AdviserOpinion(
                adviser_id="taleb",
                direction="bearish",
                confidence=1,
                score_adjustment=-3,
                thesis="x",
                counterargument="y",
                citation_ids=("f1",),
                missing_evidence=(),
                abstained=False,
            ),
            AdviserOpinion(
                adviser_id="druckenmiller",
                direction="bearish",
                confidence=1,
                score_adjustment=-3,
                thesis="x",
                counterargument="y",
                citation_ids=("f2",),
                missing_evidence=(),
                abstained=False,
            ),
        )

        result = aggregate_opinions(
            baseline_score=67,
            baseline_direction="bullish",
            opinions=opinions,
            council_cap=4,
            hard_gate_passed=True,
        )
        self.assertEqual(result.adjustment, -4)
        self.assertEqual(result.adjusted_score, 63)
        self.assertEqual(result.objective_direction, "bullish")

        gated = aggregate_opinions(
            baseline_score=67,
            baseline_direction="bullish",
            opinions=opinions,
            council_cap=4,
            hard_gate_passed=False,
        )
        self.assertFalse(gated.action_eligible)
        self.assertEqual(gated.adjustment, 0)

    def test_runtime_contract_rejects_unknown_horizon_direction_and_raw_output(self) -> None:
        with self.assertRaises(ValueError):
            CouncilRequest(
                **{**self.request.__dict__, "horizon": "intraday"}  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            CouncilRequest(
                **{**self.request.__dict__, "baseline_direction": "up"}  # type: ignore[arg-type]
            )
        unvalidated = AdviserOpinion(
            adviser_id="taleb",
            direction="up",  # type: ignore[arg-type]
            confidence=2.0,
            score_adjustment=99,
            thesis="x",
            counterargument="y",
            citation_ids=("f1",),
            missing_evidence=(),
            abstained=False,
        )
        with self.assertRaises(InvalidAdviserOutput):
            aggregate_opinions(
                baseline_score=67,
                baseline_direction="bullish",
                opinions=(unvalidated,),
                hard_gate_passed=True,
            )


class AdviserCapAuthorityTests(unittest.TestCase):
    """council.py must not repeat the ADVISER_SCORE_CAP literal: commit
    71bfd8f made analysis_core the single authority for the engine and the
    app, but left this module's own defaults hardcoded and diverging."""

    def test_council_cap_default_matches_the_shared_authority(self) -> None:
        from us_stock_helper_core import ADVISER_SCORE_CAP

        opinions = (
            AdviserOpinion(
                adviser_id="taleb",
                direction="bearish",
                confidence=1,
                score_adjustment=-3,
                thesis="x",
                counterargument="y",
                citation_ids=("f1",),
                missing_evidence=(),
                abstained=False,
            ),
            AdviserOpinion(
                adviser_id="druckenmiller",
                direction="bearish",
                confidence=1,
                score_adjustment=-3,
                thesis="x",
                counterargument="y",
                citation_ids=("f2",),
                missing_evidence=(),
                abstained=False,
            ),
        )

        # Raw adjustment is -6; only the module's old stray default of 4.0
        # would clamp it to -4. The shared authority is 3.0.
        result = aggregate_opinions(
            baseline_score=67,
            baseline_direction="bullish",
            opinions=opinions,
            hard_gate_passed=True,
        )
        self.assertEqual(ADVISER_SCORE_CAP, 3.0)
        self.assertEqual(result.adjustment, -ADVISER_SCORE_CAP)
        self.assertEqual(result.adjusted_score, 67 - ADVISER_SCORE_CAP)

    def test_per_adviser_cap_defaults_are_sourced_from_the_shared_authority(
        self,
    ) -> None:
        import inspect

        from us_stock_helper_core import ADVISER_SCORE_CAP

        for func in (validate_opinion, aggregate_opinions):
            default = inspect.signature(func).parameters["per_adviser_cap"].default
            self.assertEqual(default, ADVISER_SCORE_CAP)


if __name__ == "__main__":
    unittest.main()
