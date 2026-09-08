from __future__ import annotations

import unittest

import anthropic

try:
    import httpx  # anthropic < 1.0 depends on httpx for its transport
except ModuleNotFoundError:  # anthropic >= 1.0 renamed the dependency to httpx2
    import httpx2 as httpx  # type: ignore[import-not-found,no-redef]

from adviser_llm import (
    AdviserLlm,
    AdviserLlmConfig,
    AdviserOutcome,
    Citation,
    Conclusion,
    CouncilBrief,
    FrameworkOpinion,
    LlmUnavailableError,
    NewsInterpretation,
)

from tests.fakes import FakeClient, FakeMessage, evidence_item, sample_packet


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _timeout() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=_request())


def _brief() -> CouncilBrief:
    return CouncilBrief(
        summary="综述",
        opinions=[
            FrameworkOpinion(
                framework_id="value",
                stance="bullish",
                conclusions=[
                    Conclusion(
                        statement="指引上调",
                        confidence="medium",
                        citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
                    )
                ],
                blind_spot_note="不覆盖短期价格路径",
            )
        ],
    )


class OutcomeContractTest(unittest.TestCase):
    def test_an_outcome_cannot_be_both_available_and_degraded(self) -> None:
        with self.assertRaises(ValueError):
            AdviserOutcome(value="x", unavailable_reason="down")

    def test_an_outcome_must_be_one_or_the_other(self) -> None:
        with self.assertRaises(ValueError):
            AdviserOutcome(value=None, unavailable_reason=None)

    def test_a_degraded_outcome_refuses_to_hand_over_a_value(self) -> None:
        outcome = AdviserOutcome(value=None, unavailable_reason="模型不可用")
        self.assertFalse(outcome.available)
        with self.assertRaises(LlmUnavailableError):
            outcome.require()


class DegradationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AdviserLlmConfig(max_attempts=2, retry_backoff_seconds=0.0)
        self.packet = sample_packet(
            evidence_item(
                item_id="ev-1", body="公司称本季数据中心收入指引上调 12%。"
            )
        )

    def _service(self, client: FakeClient) -> AdviserLlm:
        return AdviserLlm(client, self.config, sleep=lambda _seconds: None)

    def test_news_reading_degrades_explicitly_rather_than_returning_neutral(
        self,
    ) -> None:
        client = FakeClient.returning(parse=[_timeout(), _timeout()])
        outcome = self._service(client).interpret_news(self.packet)
        self.assertFalse(outcome.available)
        self.assertIsNone(outcome.value)
        self.assertTrue(outcome.unavailable_reason)

    def test_a_model_outage_is_never_reported_as_having_no_view(self) -> None:
        client = FakeClient.returning(stream=[_timeout(), _timeout()])
        outcome = self._service(client).convene_council(
            self.packet, baseline_score=60.0, baseline_direction="bullish"
        )
        self.assertFalse(outcome.available)
        self.assertIsNone(outcome.value)
        # A neutral verdict would be indistinguishable from "the council looked
        # and found nothing", which is a different and much stronger claim.
        self.assertNotIsInstance(outcome.value, CouncilBrief)

    def test_a_missing_credential_degrades_the_whole_feature(self) -> None:
        service = AdviserLlm.from_environment(self.config, environ={})
        outcome = service.interpret_news(self.packet)
        self.assertFalse(outcome.available)
        self.assertIn(self.config.api_key_env, outcome.unavailable_reason or "")

    def test_a_refusal_stop_reason_degrades_instead_of_inventing_content(
        self,
    ) -> None:
        client = FakeClient.returning(
            parse=[FakeMessage(parsed_output=None, stop_reason="refusal")]
        )
        outcome = self._service(client).interpret_news(self.packet)
        self.assertFalse(outcome.available)
        self.assertIn("refusal", (outcome.unavailable_reason or "").lower())

    def test_an_untraceable_answer_degrades_rather_than_being_shown(self) -> None:
        brief = CouncilBrief(
            summary="综述",
            opinions=[
                FrameworkOpinion(
                    framework_id="value",
                    stance="bullish",
                    conclusions=[
                        Conclusion(
                            statement="指引上调",
                            confidence="medium",
                            citations=[
                                Citation(evidence_id="ev-unknown", quote="指引上调 12%")
                            ],
                        )
                    ],
                    blind_spot_note="不覆盖短期价格路径",
                )
            ],
        )
        client = FakeClient.returning(stream=[FakeMessage(parsed_output=brief)])
        outcome = self._service(client).convene_council(
            self.packet, baseline_score=60.0, baseline_direction="bullish"
        )
        self.assertFalse(outcome.available)
        self.assertIsNone(outcome.value)

    def test_a_healthy_council_call_produces_a_verdict(self) -> None:
        client = FakeClient.returning(stream=[FakeMessage(parsed_output=_brief())])
        outcome = self._service(client).convene_council(
            self.packet, baseline_score=60.0, baseline_direction="bullish"
        )
        self.assertTrue(outcome.available)
        verdict = outcome.require()
        self.assertEqual(verdict.baseline_score, 60.0)

    def test_a_healthy_news_call_produces_a_traced_reading(self) -> None:
        interpretation = NewsInterpretation(
            headline_summary="指引上调",
            cross_source_reading="仅一家信源报道",
            investment_impact=[
                Conclusion(
                    statement="对短线情绪偏正面",
                    confidence="low",
                    citations=[Citation(evidence_id="ev-1", quote="指引上调 12%")],
                )
            ],
            unknowns=["缺少同业对照"],
        )
        client = FakeClient.returning(
            parse=[FakeMessage(parsed_output=interpretation)]
        )
        outcome = self._service(client).interpret_news(self.packet)
        self.assertTrue(outcome.available)
        traced = outcome.require()
        self.assertEqual(
            traced.investment_impact[0].citations[0].url, self.packet.items[0].url
        )


if __name__ == "__main__":
    unittest.main()
