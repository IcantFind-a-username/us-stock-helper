from __future__ import annotations

import unittest

from adviser_llm import (
    Citation,
    Conclusion,
    CouncilBrief,
    FrameworkOpinion,
    TraceabilityError,
    trace_brief,
    trace_conclusion,
)

from tests.fakes import evidence_item, sample_packet


def _conclusion(*citations: Citation, statement: str = "数据中心指引上调") -> Conclusion:
    return Conclusion(
        statement=statement,
        confidence="medium",
        citations=list(citations),
    )


class TraceConclusionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1",
                headline="Nvidia 上调数据中心指引",
                body="公司称本季数据中心收入指引上调 12%。",
                url="https://example.com/nvda-guidance",
            )
        )

    def test_citation_to_an_unknown_evidence_id_is_rejected(self) -> None:
        conclusion = _conclusion(Citation(evidence_id="ev-999", quote="指引上调"))
        with self.assertRaises(TraceabilityError):
            trace_conclusion(conclusion, self.packet)

    def test_resolved_citation_carries_the_original_link_from_our_record(self) -> None:
        conclusion = _conclusion(Citation(evidence_id="ev-1", quote="指引上调 12%"))
        traced = trace_conclusion(conclusion, self.packet)
        self.assertEqual(len(traced.citations), 1)
        resolved = traced.citations[0]
        self.assertEqual(resolved.evidence_id, "ev-1")
        self.assertEqual(resolved.url, "https://example.com/nvda-guidance")
        self.assertEqual(resolved.publisher, "Example Wire")
        self.assertEqual(
            resolved.available_at, self.packet.items[0].available_at
        )
        self.assertEqual(resolved.received_at, self.packet.items[0].received_at)

    def test_traced_conclusion_never_loses_its_citations(self) -> None:
        conclusion = _conclusion(Citation(evidence_id="ev-1", quote="指引上调 12%"))
        traced = trace_conclusion(conclusion, self.packet)
        self.assertTrue(traced.citations)
        self.assertEqual(traced.statement, conclusion.statement)

    def test_one_bad_citation_rejects_the_whole_conclusion(self) -> None:
        conclusion = _conclusion(
            Citation(evidence_id="ev-1", quote="指引上调 12%"),
            Citation(evidence_id="ev-missing", quote="指引上调 12%"),
        )
        with self.assertRaises(TraceabilityError):
            trace_conclusion(conclusion, self.packet)


class TraceBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1",
                headline="Nvidia 上调数据中心指引",
                body="公司称本季数据中心收入指引上调 12%。",
            )
        )
        self.good = Conclusion(
            statement="数据中心指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        self.bad = Conclusion(
            statement="数据中心指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-nope", quote="指引上调 12%")],
        )

    def _brief(self, *conclusions: Conclusion) -> CouncilBrief:
        return CouncilBrief(
            summary="综述",
            opinions=[
                FrameworkOpinion(
                    framework_id="value",
                    stance="bullish",
                    conclusions=list(conclusions),
                    blind_spot_note="不擅长短期价格路径",
                )
            ],
        )

    def test_a_single_untraceable_conclusion_rejects_the_entire_brief(self) -> None:
        # Partial display would let an unsourced claim reach the screen next to
        # sourced ones, which is exactly the failure the citation rule exists
        # to prevent.
        with self.assertRaises(TraceabilityError):
            trace_brief(self._brief(self.good, self.bad), self.packet)

    def test_a_fully_sourced_brief_is_accepted(self) -> None:
        traced = trace_brief(self._brief(self.good), self.packet)
        self.assertEqual(len(traced.opinions), 1)
        self.assertEqual(len(traced.opinions[0].conclusions), 1)
        self.assertEqual(
            traced.opinions[0].conclusions[0].citations[0].url,
            self.packet.items[0].url,
        )

    def test_an_unknown_framework_id_is_rejected(self) -> None:
        brief = CouncilBrief(
            summary="综述",
            opinions=[
                FrameworkOpinion(
                    framework_id="astrology",
                    stance="bullish",
                    conclusions=[self.good],
                    blind_spot_note="无",
                )
            ],
        )
        with self.assertRaises(TraceabilityError):
            trace_brief(brief, self.packet)


if __name__ == "__main__":
    unittest.main()
