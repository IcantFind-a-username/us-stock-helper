from __future__ import annotations

import unittest

from adviser_llm import (
    AdviserLlm,
    AdviserLlmConfig,
    Citation,
    Conclusion,
    CouncilBrief,
    EVIDENCE_ONLY_SYSTEM_PROMPT,
    FrameworkOpinion,
    NewsInterpretation,
)

from tests.fakes import FakeClient, FakeMessage, evidence_item, sample_packet


def _interpretation() -> NewsInterpretation:
    return NewsInterpretation(
        headline_summary="指引上调",
        cross_source_reading="仅一家信源",
        investment_impact=[
            Conclusion(
                statement="短线情绪偏正面",
                confidence="low",
                citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
            )
        ],
        unknowns=["缺少同业对照"],
    )


def _brief() -> CouncilBrief:
    return CouncilBrief(
        summary="综述",
        opinions=[
            FrameworkOpinion(
                framework_id="value",
                stance="neutral",
                conclusions=[
                    Conclusion(
                        statement="估值信息不足",
                        confidence="low",
                        citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
                    )
                ],
                blind_spot_note="不覆盖短期价格路径",
            )
        ],
    )


class NewsRequestShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1", body="公司称本季数据中心收入指引上调 12%。"
            )
        )
        self.client = FakeClient.returning(
            parse=[FakeMessage(parsed_output=_interpretation())]
        )
        self.config = AdviserLlmConfig()
        AdviserLlm(self.client, self.config).interpret_news(self.packet)
        self.call = self.client.messages.parse_calls[0]

    def test_the_pinned_model_is_used(self) -> None:
        self.assertEqual(self.call["model"], "claude-opus-4-8")

    def test_adaptive_thinking_is_requested(self) -> None:
        self.assertEqual(self.call["thinking"], {"type": "adaptive"})

    def test_a_single_news_reading_runs_at_low_effort(self) -> None:
        self.assertEqual(self.call["output_config"], {"effort": "low"})

    def test_the_schema_is_enforced_by_the_sdk_parser(self) -> None:
        self.assertIs(self.call["output_format"], NewsInterpretation)

    def test_the_request_carries_a_finite_deadline(self) -> None:
        self.assertEqual(
            self.call["timeout"], self.config.request_timeout_seconds
        )

    def test_the_system_prompt_forbids_facts_outside_the_evidence(self) -> None:
        system = self.call["system"]
        self.assertIn("只能基于给定证据", system)
        self.assertIn("不知道", system)

    def test_the_frozen_packet_is_the_only_material_sent(self) -> None:
        content = self.call["messages"][0]["content"]
        self.assertIn("ev-1", content)
        self.assertIn(self.packet.items[0].url, content)

    def test_no_tools_are_offered_to_the_model(self) -> None:
        self.assertNotIn("tools", self.call)


class CouncilRequestShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1", body="公司称本季数据中心收入指引上调 12%。"
            )
        )
        self.client = FakeClient.returning(
            stream=[FakeMessage(parsed_output=_brief())]
        )
        self.config = AdviserLlmConfig()
        AdviserLlm(self.client, self.config).convene_council(
            self.packet, baseline_score=60.0, baseline_direction="bullish"
        )
        self.call = self.client.messages.stream_calls[0]

    def test_the_long_council_answer_is_streamed(self) -> None:
        self.assertEqual(len(self.client.messages.stream_calls), 1)
        self.assertEqual(self.client.messages.parse_calls, [])

    def test_the_council_runs_at_high_effort(self) -> None:
        self.assertEqual(self.call["output_config"], {"effort": "high"})

    def test_the_council_uses_the_longer_deadline(self) -> None:
        self.assertEqual(
            self.call["timeout"], self.config.council_timeout_seconds
        )

    def test_every_framework_and_its_blind_spot_reaches_the_prompt(self) -> None:
        system = self.call["system"]
        self.assertIn("盲区", system)
        self.assertIn("value", system)

    def test_the_prompt_never_asks_for_an_order(self) -> None:
        blob = (self.call["system"] + self.call["messages"][0]["content"]).lower()
        for banned in ("下单", "买入数量", "broker", "order", "position size"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, blob)


class SystemPromptTest(unittest.TestCase):
    def test_the_shared_prompt_states_the_evidence_only_rule(self) -> None:
        self.assertIn("只能基于给定证据", EVIDENCE_ONLY_SYSTEM_PROMPT)

    def test_the_shared_prompt_requires_admitting_ignorance(self) -> None:
        self.assertIn("不知道", EVIDENCE_ONLY_SYSTEM_PROMPT)

    def test_the_shared_prompt_requires_a_citation_per_conclusion(self) -> None:
        self.assertIn("citations", EVIDENCE_ONLY_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
