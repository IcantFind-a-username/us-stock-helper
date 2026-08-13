from __future__ import annotations

import unittest

from adviser_llm import Citation, Conclusion, FabricatedFactError, trace_conclusion

from tests.fakes import evidence_item, sample_packet


class QuoteGroundingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1",
                headline="Nvidia 上调数据中心指引",
                body="公司称本季数据中心收入指引上调 12%。",
            )
        )

    def test_a_quote_absent_from_the_cited_item_is_a_fabrication(self) -> None:
        conclusion = Conclusion(
            statement="指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="CEO 宣布回购 50 亿美元")],
        )
        with self.assertRaises(FabricatedFactError):
            trace_conclusion(conclusion, self.packet)

    def test_a_quote_lifted_from_a_different_item_is_a_fabrication(self) -> None:
        packet = sample_packet(
            evidence_item(item_id="ev-1", body="公司称本季数据中心收入指引上调 12%。"),
            evidence_item(
                item_id="ev-2",
                headline="监管调查",
                body="监管机构就出口许可展开调查。",
                url="https://example.com/probe",
            ),
        )
        conclusion = Conclusion(
            statement="指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="监管机构就出口许可展开调查")],
        )
        with self.assertRaises(FabricatedFactError):
            trace_conclusion(conclusion, packet)

    def test_whitespace_differences_do_not_count_as_fabrication(self) -> None:
        conclusion = Conclusion(
            statement="指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="  指引上调   12%  ")],
        )
        traced = trace_conclusion(conclusion, self.packet)
        self.assertEqual(traced.citations[0].evidence_id, "ev-1")


class StatementGroundingTest(unittest.TestCase):
    """Facts outside the packet must not survive into a shown conclusion."""

    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1",
                headline="Nvidia 上调数据中心指引",
                body="公司称本季数据中心收入指引上调 12%。",
                symbols=("NVDA",),
            )
        )

    def test_a_number_that_appears_nowhere_in_the_evidence_is_caught(self) -> None:
        conclusion = Conclusion(
            # 45% appears in no supplied evidence item.
            statement="数据中心收入指引上调 45%，显著强于同业",
            confidence="high",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        with self.assertRaises(FabricatedFactError):
            trace_conclusion(conclusion, self.packet)

    def test_a_ticker_that_appears_nowhere_in_the_evidence_is_caught(self) -> None:
        conclusion = Conclusion(
            statement="AMD 会因此承压",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        with self.assertRaises(FabricatedFactError):
            trace_conclusion(conclusion, self.packet)

    def test_numbers_present_in_the_evidence_pass(self) -> None:
        conclusion = Conclusion(
            statement="数据中心收入指引上调 12%",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        traced = trace_conclusion(conclusion, self.packet)
        self.assertEqual(traced.statement, conclusion.statement)

    def test_the_packet_symbol_itself_is_not_treated_as_fabricated(self) -> None:
        conclusion = Conclusion(
            statement="NVDA 的指引上调",
            confidence="medium",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        traced = trace_conclusion(conclusion, self.packet)
        self.assertEqual(traced.statement, conclusion.statement)

    def test_a_qualitative_claim_without_new_facts_passes(self) -> None:
        conclusion = Conclusion(
            statement="指引上调对短线情绪偏正面",
            confidence="low",
            citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
        )
        traced = trace_conclusion(conclusion, self.packet)
        self.assertTrue(traced.citations)


if __name__ == "__main__":
    unittest.main()
