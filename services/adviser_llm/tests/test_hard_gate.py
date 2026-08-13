from __future__ import annotations

import unittest

from us_stock_helper_core import ADVISER_SCORE_CAP, HardGate

from adviser_llm import (
    ANALYSIS_FRAMEWORKS,
    Citation,
    Conclusion,
    CouncilBrief,
    FrameworkOpinion,
    apply_hard_gate,
    trace_brief,
)

from tests.fakes import evidence_item, sample_packet


class HardGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1", body="公司称本季数据中心收入指引上调 12%。"
            )
        )

    def _brief(self, stance: str, confidence: str) -> object:
        opinions = [
            FrameworkOpinion(
                framework_id=framework.id,
                stance=stance,
                conclusions=[
                    Conclusion(
                        statement="指引上调",
                        confidence=confidence,
                        citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
                    )
                ],
                blind_spot_note=framework.blind_spots[0],
            )
            for framework in ANALYSIS_FRAMEWORKS
        ]
        return trace_brief(
            CouncilBrief(summary="综述", opinions=opinions), self.packet
        )

    def test_a_unanimous_bullish_council_cannot_pass_a_failed_hard_gate(
        self,
    ) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
            hard_gates=(HardGate.INSUFFICIENT_EVIDENCE,),
        )
        self.assertFalse(verdict.actionable)
        self.assertEqual(verdict.score_adjustment, 0.0)
        self.assertEqual(verdict.adjusted_score, 60.0)
        self.assertEqual(verdict.blocked_by, (HardGate.INSUFFICIENT_EVIDENCE,))

    def test_the_council_never_flips_the_objective_direction(self) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=40.0,
            baseline_direction="bearish",
        )
        self.assertEqual(verdict.objective_direction, "bearish")

    def test_the_adjustment_is_capped_by_the_shared_soft_factor_ceiling(
        self,
    ) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
        )
        self.assertEqual(verdict.score_adjustment, ADVISER_SCORE_CAP)
        self.assertEqual(verdict.adjusted_score, 60.0 + ADVISER_SCORE_CAP)

    def test_a_bearish_council_is_capped_symmetrically(self) -> None:
        verdict = apply_hard_gate(
            self._brief("bearish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
        )
        self.assertEqual(verdict.score_adjustment, -ADVISER_SCORE_CAP)

    def test_low_confidence_moves_the_score_less_than_high_confidence(self) -> None:
        low = apply_hard_gate(
            self._brief("bullish", "low"),
            baseline_score=60.0,
            baseline_direction="bullish",
        )
        high = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
        )
        self.assertLess(low.score_adjustment, high.score_adjustment)
        self.assertGreater(low.score_adjustment, 0.0)

    def test_multiple_gates_are_all_reported(self) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
            hard_gates=(HardGate.STALE_DATA, HardGate.LOW_LIQUIDITY),
        )
        self.assertEqual(
            set(verdict.blocked_by), {HardGate.STALE_DATA, HardGate.LOW_LIQUIDITY}
        )
        self.assertFalse(verdict.actionable)

    def test_the_verdict_states_that_opinions_are_advice_not_instruction(
        self,
    ) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=60.0,
            baseline_direction="bullish",
        )
        self.assertIn("建议", verdict.disclaimer)
        self.assertNotEqual(verdict.disclaimer.strip(), "")

    def test_the_adjusted_score_stays_inside_the_score_range(self) -> None:
        verdict = apply_hard_gate(
            self._brief("bullish", "high"),
            baseline_score=99.0,
            baseline_direction="bullish",
        )
        self.assertLessEqual(verdict.adjusted_score, 100.0)


if __name__ == "__main__":
    unittest.main()
