"""The adviser layer as seen from /decision.

Two things are being pinned here at once. The first is money: a council brief
costs about ten cents, so the request has to ask for it and the answer has to
say what it spent. The second is honesty: a model that could not be reached
must not read as a model with no opinion, and an opinion the hard gate vetoed
must not arrive as a higher score.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any
from unittest import mock

from us_stock_helper_analysis_api.adviser_provider import (
    AdviserBriefing,
    LlmAdviserProvider,
)
from us_stock_helper_analysis_api.service import AnalysisService
from us_stock_helper_core import OHLCVBar

from test_analysis_service import AS_OF, Provider, bars


# ---------------------------------------------------------------------------
# Fakes. Nothing in this file may reach the network.
# ---------------------------------------------------------------------------


class ExplodingAdviser:
    """Any call at all is the failure being tested."""

    def brief(self, **kwargs: Any) -> AdviserBriefing:
        raise AssertionError("the model must not be called unless asked for")


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class FakeMessage:
    parsed_output: Any
    stop_reason: str = "end_turn"
    usage: Any = None


class _FakeStream:
    def __init__(self, message: Any) -> None:
        self._message = message

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def get_final_message(self) -> Any:
        return self._message


@dataclass
class FakeMessages:
    parse_results: list[Any] = field(default_factory=list)
    stream_results: list[Any] = field(default_factory=list)
    parse_calls: list[dict[str, Any]] = field(default_factory=list)
    stream_calls: list[dict[str, Any]] = field(default_factory=list)

    def parse(self, **kwargs: Any) -> Any:
        self.parse_calls.append(kwargs)
        return self._next(self.parse_results, "parse")

    def stream(self, **kwargs: Any) -> Any:
        self.stream_calls.append(kwargs)
        return _FakeStream(self._next(self.stream_results, "stream"))

    @staticmethod
    def _next(queue: list[Any], label: str) -> Any:
        if not queue:
            raise AssertionError(f"unexpected extra {label} call")
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)


def stale_bars() -> tuple[OHLCVBar, ...]:
    """Candles that stopped arriving long enough ago to trip the stale gate.

    These are daily bars, so the gate is budgeted against a daily-bar
    cadence (a session close can be a holiday weekend away, not just
    intraday-tight): the lag has to clear that wider, honest budget, not the
    45 minutes that only tripped the gate back when it was mistakenly
    budgeted for intraday data.
    """

    lag = timedelta(days=10)
    return tuple(
        replace(
            row,
            opened_at=row.opened_at - lag,
            closed_at=row.closed_at - lag,
            available_at=row.available_at - lag,
        )
        for row in bars()
    )


# The quotes below are copied verbatim out of the evidence the fake provider
# serves, because the traceability layer resolves a citation by finding its
# quote in the frozen source text and refuses anything it cannot find.
HEADLINE_QUOTE = "raises full-year revenue guidance"
BODY_QUOTE = "The chipmaker lifted its outlook."


def news_answer(*, evidence_id: str = "a", quote: str = HEADLINE_QUOTE) -> Any:
    from adviser_llm import Citation, Conclusion, NewsInterpretation

    return NewsInterpretation(
        headline_summary="两家通讯社都报道了指引上调。",
        cross_source_reading="两条报道指向同一件事，来源相互独立。",
        investment_impact=[
            Conclusion(
                statement="指引上调支持偏多的解读。",
                confidence="medium",
                citations=[Citation(evidence_id=evidence_id, quote=quote)],
            )
        ],
        unknowns=["证据没有说明毛利率如何变化。"],
    )


def council_answer(*, stance: str = "bullish") -> Any:
    from adviser_llm import Citation, Conclusion, CouncilBrief, FrameworkOpinion

    return CouncilBrief(
        summary="各框架都读到同一条指引上调。",
        opinions=[
            FrameworkOpinion(
                framework_id="technical",
                stance=stance,
                conclusions=[
                    Conclusion(
                        statement="指引上调与当前价格结构一致。",
                        confidence="high",
                        citations=[Citation(evidence_id="a", quote=HEADLINE_QUOTE)],
                    )
                ],
                blind_spot_note="对基本面突变无感。",
            )
        ],
    )


def provider_with(
    *,
    parse: list[Any] | None = None,
    stream: list[Any] | None = None,
) -> LlmAdviserProvider:
    from adviser_llm import AdviserLlmConfig

    return LlmAdviserProvider(
        client=FakeClient(
            messages=FakeMessages(
                parse_results=list(parse or []),
                stream_results=list(stream or []),
            )
        ),
        config=AdviserLlmConfig(max_attempts=1, retry_backoff_seconds=0.0),
        sleep=lambda _seconds: None,
    )


def service(
    adviser: Any = None,
    *,
    rows: tuple[OHLCVBar, ...] | None = None,
) -> AnalysisService:
    return AnalysisService(
        Provider(rows=rows),
        clock=lambda: AS_OF,
        adviser_factory=lambda: adviser if adviser is not None else ExplodingAdviser(),
    )


# ---------------------------------------------------------------------------


class CostControlTests(unittest.TestCase):
    def test_a_plain_decision_never_reaches_the_model(self) -> None:
        # ExplodingAdviser turns any call into a failure, so this asserts the
        # absence of a request rather than the shape of its answer.
        result = service().decision("NVDA", "short")

        self.assertEqual(result["newsInterpretation"]["status"], "not-requested")
        self.assertEqual(result["adviserCouncil"]["status"], "not-requested")
        self.assertIsNone(result["newsInterpretation"]["value"])
        self.assertIsNone(result["adviserCouncil"]["value"])
        self.assertIsNone(result["adviserUsage"])

    def test_the_not_requested_state_says_so_rather_than_going_blank(self) -> None:
        result = service().decision("NVDA", "short")

        for key in ("newsInterpretation", "adviserCouncil"):
            with self.subTest(key=key):
                self.assertTrue(result[key]["reason"])

    def test_not_requested_and_unavailable_are_different_answers(self) -> None:
        """A silent null cannot tell the reader which of the two happened."""

        quiet = service().decision("NVDA", "short")
        asked = service(
            LlmAdviserProvider(environ={}, sleep=lambda _seconds: None)
        ).decision("NVDA", "short", adviser=True)

        self.assertEqual(quiet["newsInterpretation"]["status"], "not-requested")
        self.assertEqual(asked["newsInterpretation"]["status"], "unavailable")
        self.assertNotEqual(
            quiet["newsInterpretation"]["reason"],
            asked["newsInterpretation"]["reason"],
        )

    def test_an_explicit_request_reaches_the_model_and_comes_back_traceable(
        self,
    ) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer())],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        news = result["newsInterpretation"]
        self.assertEqual(news["status"], "available")
        self.assertTrue(news["value"]["crossSourceReading"])
        conclusions = news["value"]["investmentImpact"]
        self.assertTrue(conclusions)
        for conclusion in conclusions:
            self.assertTrue(conclusion["citations"])
            for citation in conclusion["citations"]:
                self.assertTrue(citation["evidenceId"])
                self.assertTrue(citation["quote"])
                self.assertTrue(citation["url"].startswith("https://"))
                self.assertTrue(citation["publisher"])
                self.assertTrue(citation["availableAt"].endswith("Z"))

        council = result["adviserCouncil"]
        self.assertEqual(council["status"], "available")
        self.assertTrue(council["value"]["summary"])
        opinion = council["value"]["opinions"][0]
        self.assertEqual(opinion["frameworkId"], "technical")
        self.assertIn(opinion["stance"], {"bullish", "neutral", "bearish"})
        self.assertTrue(opinion["blindSpot"])
        self.assertTrue(council["value"]["disclaimer"])

    def test_a_news_only_request_spends_on_one_model_call_not_the_council(self) -> None:
        adviser = provider_with(
            parse=[
                FakeMessage(
                    news_answer(),
                    usage=FakeUsage(input_tokens=4000, output_tokens=900),
                )
            ],
            # An empty stream queue makes any accidental council call fail the
            # test instead of merely producing an answer we forget to assert.
            stream=[],
        )

        result = service(adviser).decision("NVDA", "short", adviser="news")

        self.assertEqual(result["newsInterpretation"]["status"], "available")
        self.assertEqual(result["adviserCouncil"]["status"], "not-requested")
        self.assertIn("仅请求新闻解读", result["adviserCouncil"]["reason"])
        self.assertEqual(result["adviserUsage"]["inputTokens"], 4000)
        self.assertEqual(result["adviserUsage"]["outputTokens"], 900)

    def test_the_measured_usage_and_its_cost_travel_with_the_answer(self) -> None:
        from adviser_llm.client import TokenUsage

        adviser = provider_with(
            parse=[
                FakeMessage(
                    news_answer(),
                    usage=FakeUsage(input_tokens=4000, output_tokens=900),
                )
            ],
            stream=[
                FakeMessage(
                    council_answer(),
                    usage=FakeUsage(
                        input_tokens=9000,
                        output_tokens=3000,
                        cache_read_input_tokens=2000,
                    ),
                )
            ],
        )

        usage = service(adviser).decision("NVDA", "short", adviser=True)[
            "adviserUsage"
        ]

        self.assertEqual(usage["inputTokens"], 13_000)
        self.assertEqual(usage["outputTokens"], 3_900)
        self.assertEqual(usage["cacheReadInputTokens"], 2_000)
        expected = TokenUsage(
            input_tokens=13_000,
            output_tokens=3_900,
            cache_read_input_tokens=2_000,
        ).cost_usd()
        self.assertAlmostEqual(usage["costUsd"], expected, places=6)
        self.assertGreater(usage["costUsd"], 0.0)


class DegradationTests(unittest.TestCase):
    def test_no_citable_evidence_degrades_into_a_chinese_reason(self) -> None:
        # Investor-readable Chinese (2026-08-15 served-copy sweep): a decision
        # was reached (bars exist), but nothing in the evidence feed could be
        # quoted, so the model was never asked. Both the prose this service
        # writes and the packet-builder's own ValueError it appends are
        # Chinese, so the whole reason reaches the AdvisersScreen readable.
        class NoEvidenceProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[Any, ...]:
                return ()

        # service() always builds a plain Provider(); this case needs the
        # empty-evidence provider instead, so the service is built directly.
        result = AnalysisService(
            NoEvidenceProvider(),
            clock=lambda: AS_OF,
            adviser_factory=lambda: provider_with(
                parse=[FakeMessage(news_answer())],
                stream=[FakeMessage(council_answer())],
            ),
        ).decision("NVDA", "short", adviser=True)

        reason = result["newsInterpretation"]["reason"]
        self.assertTrue(
            reason.startswith("决策截止时点没有可引用的证据，因此没有请求模型做任何解读："),
            msg=reason,
        )
        self.assertNotRegex(reason, r"[a-z]{3,}")

    def test_a_missing_key_is_stated_rather_than_read_as_no_opinion(self) -> None:
        result = service(
            LlmAdviserProvider(environ={}, sleep=lambda _seconds: None)
        ).decision("NVDA", "short", adviser=True)

        for key in ("newsInterpretation", "adviserCouncil"):
            with self.subTest(key=key):
                self.assertEqual(result[key]["status"], "unavailable")
                self.assertIsNone(result[key]["value"])
                self.assertIn("ANTHROPIC_API_KEY", result[key]["reason"])

    def test_a_refused_answer_degrades_instead_of_rendering_half_of_it(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer(), stop_reason="refusal")],
            stream=[FakeMessage(council_answer(), stop_reason="refusal")],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        for key in ("newsInterpretation", "adviserCouncil"):
            with self.subTest(key=key):
                self.assertEqual(result[key]["status"], "unavailable")
                self.assertIsNone(result[key]["value"])
                self.assertTrue(result[key]["reason"])

    def test_a_timeout_degrades_explicitly(self) -> None:
        import anthropic
        import httpx

        def timeout() -> anthropic.APITimeoutError:
            return anthropic.APITimeoutError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )

        adviser = provider_with(parse=[timeout()], stream=[timeout()])

        result = service(adviser).decision("NVDA", "short", adviser=True)

        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")
        self.assertEqual(result["adviserCouncil"]["status"], "unavailable")

    def test_a_conclusion_with_no_citation_is_refused_rather_than_shown(self) -> None:
        """The schema makes this unrepresentable; the boundary refuses it anyway.

        `Conclusion` requires a non-empty citation list, so a well-formed model
        answer cannot reach here without one. That is exactly why the check
        below matters: it is the guard for the day the schema is bypassed, and
        an unguarded path would put an unsourced sentence on the screen.
        """

        @dataclass
        class UncitedConclusion:
            statement: str = "指引上调支持偏多的解读。"
            confidence: str = "medium"
            citations: tuple[Any, ...] = ()
            counter_evidence: tuple[Any, ...] = ()

        @dataclass
        class UncitedInterpretation:
            headline_summary: str = "两家通讯社都报道了指引上调。"
            cross_source_reading: str = "两条报道指向同一件事。"
            investment_impact: tuple[Any, ...] = (UncitedConclusion(),)
            unknowns: tuple[str, ...] = ()

        adviser = provider_with(
            parse=[FakeMessage(UncitedInterpretation())],
            stream=[FakeMessage(council_answer())],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")
        self.assertIsNone(result["newsInterpretation"]["value"])

    def test_a_quote_absent_from_the_source_is_refused(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer(quote="cuts its full-year outlook"))],
            stream=[FakeMessage(council_answer())],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")
        self.assertIsNone(result["newsInterpretation"]["value"])

    def test_a_citation_outside_the_evidence_packet_is_refused(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer(evidence_id="never-collected"))],
            stream=[FakeMessage(council_answer())],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")

    def test_a_chain_with_no_decision_does_not_spend_money_on_advice(self) -> None:
        result = service(ExplodingAdviser(), rows=()).decision(
            "NVDA", "short", adviser=True
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")
        # Investor-readable Chinese (2026-08-15 served-copy sweep): this
        # reason reaches the AdvisersScreen and the stock page's model-
        # interpretation card verbatim, with no client-side translation.
        self.assertEqual(
            result["newsInterpretation"]["reason"],
            "决策链没有得出结论，因此没有召开顾问委员会，也没有产生任何花费。",
        )
        self.assertIsNone(result["adviserUsage"])


class EvidencePacketTests(unittest.TestCase):
    def test_evidence_the_model_cannot_quote_is_counted_rather_than_dropped(
        self,
    ) -> None:
        """An event with nothing quotable cannot go into the packet.

        Patching one up would hand the model a sentence nobody published, so it
        is left out — and left out silently is how a thin packet comes to look
        like a quiet news window. The count travels with the answer.
        """

        from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance

        good, _ = Provider().evidence_for("NVDA")
        unquotable = EvidenceEvent.create(
            event_id="no-body",
            claim_key="claim-no-body",
            headline="Headline with no summary behind it",
            summary="",
            provenance=SourceProvenance(
                source_id="feed:wire",
                publisher_id="wire",
                publisher_name="Wire",
                canonical_url="https://wire.example/no-body",
                source_type="wire",
                reliability=0.9,
            ),
            event_time=AS_OF - timedelta(minutes=40),
            published_at=AS_OF - timedelta(minutes=30),
            first_seen_at=AS_OF - timedelta(minutes=20),
            available_at=AS_OF - timedelta(minutes=19),
            retrieved_at=AS_OF - timedelta(minutes=18),
            claim_status=ClaimStatus.VERIFIED,
            sentiment=0.7,
            confidence=0.9,
            symbol_relevance=(("NVDA", 0.95),),
        )

        class ThinProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[Any, ...]:
                return (good, unquotable)

        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer())],
        )
        service = AnalysisService(
            ThinProvider(), clock=lambda: AS_OF, adviser_factory=lambda: adviser
        )

        result = service.decision("NVDA", "short", adviser=True)

        self.assertEqual(result["newsInterpretation"]["status"], "available")
        # Investor-readable Chinese (2026-08-15 served-copy sweep): pinned
        # exactly, consistent with the served-vocabulary conventions this
        # note now follows.
        self.assertIn(
            "有 1 条证据没有可引用文本或没有可用链接，未纳入本次顾问材料包。",
            result["notes"],
        )


class HardGateTests(unittest.TestCase):
    def test_the_council_cannot_lift_a_score_the_hard_gate_blocked(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer(stance="bullish"))],
        )

        result = service(adviser, rows=stale_bars()).decision(
            "NVDA", "short", adviser=True
        )

        self.assertTrue(result["score"]["blockedBy"])
        council = result["adviserCouncil"]["value"]
        self.assertEqual(council["scoreAdjustment"], 0.0)
        self.assertEqual(council["adjustedScore"], council["baselineScore"])
        self.assertFalse(council["actionable"])
        self.assertTrue(council["blockedBy"])
        # A gated council still ran, so its (zeroed) adjustment folds through
        # as a measured 0.0 -- not null, and not some stale value left over
        # from a council that never spoke.
        self.assertEqual(result["adviserAdjustment"], 0.0)
        self.assertEqual(result["score"]["value"], result["baselineScore"]["value"])

    def test_an_ungated_council_stays_inside_the_published_cap(self) -> None:
        from us_stock_helper_core import ADVISER_SCORE_CAP

        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer(stance="bullish"))],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        council = result["adviserCouncil"]["value"]
        self.assertFalse(result["score"]["blockedBy"])
        self.assertGreater(council["scoreAdjustment"], 0.0)
        self.assertLessEqual(abs(council["scoreAdjustment"]), ADVISER_SCORE_CAP)
        # The council nudges the score; it never rewrites the objective call.
        self.assertEqual(
            council["objectiveDirection"], result["score"]["direction"]
        )


class AdviserAdjustmentContractTests(unittest.TestCase):
    """The top-level adviserAdjustment is the one adjustment authority.

    It must never be a fake measured 0.0 for a council that never ran, and it
    must never silently disagree with the council block sitting right next to
    it in the same response.
    """

    def test_council_off_reports_null_not_a_fake_zero(self) -> None:
        result = service().decision("NVDA", "short")

        self.assertIsNone(result["adviserCouncil"]["value"])
        self.assertIsNone(result["adviserAdjustment"])
        # Pinned in Chinese, consistent with the served-vocabulary
        # conventions and the note.py section of the adviser-adjustment
        # contract: this note reaches a Chinese UI on every default-mode
        # response, so English boilerplate here diluted the notes channel.
        self.assertIn(
            "本次没有召开顾问委员会，顾问调整为空，而非测得的零。",
            result["notes"],
        )

    def test_council_unavailable_reports_null_not_a_fake_zero(self) -> None:
        from us_stock_helper_analysis_api.adviser_provider import LlmAdviserProvider

        result = service(
            LlmAdviserProvider(environ={}, sleep=lambda _seconds: None)
        ).decision("NVDA", "short", adviser=True)

        self.assertEqual(result["adviserCouncil"]["status"], "unavailable")
        self.assertIsNone(result["adviserCouncil"]["value"])
        self.assertIsNone(result["adviserAdjustment"])

    def test_news_only_mode_never_convenes_a_council_and_reports_null(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[],
        )

        result = service(adviser).decision("NVDA", "short", adviser="news")

        self.assertEqual(result["adviserCouncil"]["status"], "not-requested")
        self.assertIsNone(result["adviserAdjustment"])

    def test_an_available_council_is_the_sole_adjustment_authority(self) -> None:
        from us_stock_helper_core import ADVISER_SCORE_CAP

        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer(stance="bullish"))],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        council = result["adviserCouncil"]["value"]
        # One bullish, high-confidence opinion pushes the full published cap.
        self.assertEqual(council["scoreAdjustment"], ADVISER_SCORE_CAP)
        self.assertIsNotNone(result["adviserAdjustment"])
        self.assertLessEqual(abs(result["adviserAdjustment"]), ADVISER_SCORE_CAP)
        # Exactly one adjustment authority: the top-level fields describe the
        # same computation the council block does, not a second, disagreeing
        # one.
        self.assertEqual(result["adviserAdjustment"], council["scoreAdjustment"])
        self.assertEqual(result["score"]["value"], council["adjustedScore"])
        self.assertEqual(
            result["score"]["value"],
            result["baselineScore"]["value"] + result["adviserAdjustment"],
        )
        self.assertNotEqual(result["score"]["value"], result["baselineScore"]["value"])


class HttpSwitchTests(unittest.TestCase):
    """The switch that decides whether this request spends ten cents."""

    @staticmethod
    def _app(adviser: Any) -> Any:
        from us_stock_helper_analysis_api.http_app import AnalysisApplication

        return AnalysisApplication(service(adviser), clock=lambda: AS_OF)

    def test_a_bare_decision_request_does_not_convene_the_council(self) -> None:
        status, _, body = self._app(ExplodingAdviser()).handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["adviserCouncil"]["status"], "not-requested")

    def test_the_adviser_flag_turns_the_model_on(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[FakeMessage(council_answer())],
        )

        status, _, body = self._app(adviser).handle(
            "GET",
            "/decision",
            {"symbol": ["NVDA"], "horizon": ["short"], "adviser": ["1"]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["adviserCouncil"]["status"], "available")
        self.assertEqual(body["newsInterpretation"]["status"], "available")

    def test_news_mode_calls_only_the_small_interpretation(self) -> None:
        adviser = provider_with(
            parse=[FakeMessage(news_answer())],
            stream=[],
        )

        status, _, body = self._app(adviser).handle(
            "GET",
            "/decision",
            {"symbol": ["NVDA"], "horizon": ["short"], "adviser": ["news"]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["newsInterpretation"]["status"], "available")
        self.assertEqual(body["adviserCouncil"]["status"], "not-requested")

    def test_an_explicit_zero_keeps_the_model_out_of_it(self) -> None:
        status, _, body = self._app(ExplodingAdviser()).handle(
            "GET",
            "/decision",
            {"symbol": ["NVDA"], "horizon": ["short"], "adviser": ["0"]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["newsInterpretation"]["status"], "not-requested")

    def test_an_unreadable_flag_is_refused_rather_than_guessed(self) -> None:
        # Guessing costs the reader money on a typo, or silently withholds the
        # thing they asked for. Neither is a defensible default.
        for value in (["maybe"], ["1", "0"]):
            with self.subTest(value=value):
                status, _, body = self._app(ExplodingAdviser()).handle(
                    "GET",
                    "/decision",
                    {"symbol": ["NVDA"], "horizon": ["short"], "adviser": value},
                )

                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")


SECRET = "sk-ant-test-do-not-log-0123456789"


class LeakyMessages:
    """An SDK failure whose text carries the credential back out.

    Not a hypothetical: HTTP client libraries routinely put request headers in
    the exception they raise, and this boundary forwards a failure reason all
    the way to the phone.
    """

    def parse(self, **kwargs: Any) -> Any:
        raise RuntimeError(f"401 unauthorized (x-api-key={SECRET})")

    def stream(self, **kwargs: Any) -> Any:
        raise RuntimeError(f"401 unauthorized (x-api-key={SECRET})")


class CredentialTests(unittest.TestCase):
    def test_the_api_key_never_appears_in_the_answer(self) -> None:
        from adviser_llm import AdviserLlmConfig

        adviser = LlmAdviserProvider(
            client=FakeClient(messages=LeakyMessages()),  # type: ignore[arg-type]
            config=AdviserLlmConfig(max_attempts=1, retry_backoff_seconds=0.0),
            environ={"ANTHROPIC_API_KEY": SECRET},
            sleep=lambda _seconds: None,
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("sk-ant", repr(result))
        # Redacting must not turn into silence: the reader still has to learn
        # the model was asked and could not answer.
        self.assertEqual(result["newsInterpretation"]["status"], "unavailable")
        # Investor-readable Chinese (2026-08-15 served-copy sweep): reaches
        # the AdvisersScreen and the model-interpretation card verbatim.
        self.assertEqual(
            result["newsInterpretation"]["reason"],
            "顾问层出现了本服务不会原样转述的失败，因为这类信息可能带有外发凭据。"
            "没有产生解读。",
        )

    def test_a_credential_shaped_reason_is_withheld_rather_than_forwarded(
        self,
    ) -> None:
        """A degradation reason is not text this service wrote.

        The adviser layer builds several of its refusals out of model output —
        an unresolvable evidence id is quoted back verbatim — and model output
        is untrusted. A reason that has come to contain something shaped like a
        credential is replaced rather than published.
        """

        adviser = provider_with(
            parse=[FakeMessage(news_answer(evidence_id=SECRET))],
            stream=[FakeMessage(council_answer())],
        )

        result = service(adviser).decision("NVDA", "short", adviser=True)

        news = result["newsInterpretation"]
        self.assertEqual(news["status"], "unavailable")
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn("sk-ant", repr(result))
        self.assertTrue(news["reason"])


class LazyImportTests(unittest.TestCase):
    @staticmethod
    def _without_sdk() -> Any:
        # Blank out the SDK and every adviser_llm module that already imported
        # it, so a fresh import inside the request path fails the way it would
        # on a deployment that never installed anthropic.
        modules: dict[str, Any] = {
            name: None
            for name in list(sys.modules)
            if name == "anthropic"
            or name.startswith("anthropic.")
            or name == "adviser_llm"
            or name.startswith("adviser_llm.")
        }
        modules["anthropic"] = None
        modules["adviser_llm"] = None
        return mock.patch.dict(sys.modules, modules)

    def test_a_deployment_without_the_sdk_reports_the_adviser_unavailable(
        self,
    ) -> None:
        with self._without_sdk():
            result = service(
                LlmAdviserProvider(environ={}, sleep=lambda _seconds: None)
            ).decision("NVDA", "short", adviser=True)

        for key in ("newsInterpretation", "adviserCouncil"):
            with self.subTest(key=key):
                self.assertEqual(result[key]["status"], "unavailable")
                self.assertIsNone(result[key]["value"])
                # Investor-readable Chinese (2026-08-15 served-copy sweep):
                # reaches the AdvisersScreen and the model-interpretation card
                # verbatim, with no client-side translation.
                self.assertEqual(
                    result[key]["reason"],
                    "本次部署没有安装顾问层（无法导入模型 SDK），因此没有产生解读。",
                )

    def test_the_service_starts_and_answers_with_no_sdk_installed(self) -> None:
        """A top-level import of an optional dependency is how a whole product
        stops opening. Asserted in a fresh interpreter, because this process
        has the SDK and cannot un-import it honestly."""

        completed = subprocess.run(
            [sys.executable, "-c", NO_SDK_STARTUP_SCRIPT],
            capture_output=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")},
            text=True,
            timeout=120,
        )

        self.assertEqual(
            completed.returncode, 0, msg=completed.stdout + completed.stderr
        )
        self.assertIn("served-without-sdk", completed.stdout)


NO_SDK_STARTUP_SCRIPT = """
import sys


class NoAnthropic:
    def find_spec(self, name, path=None, target=None):
        if name == "anthropic" or name.startswith("anthropic."):
            raise ImportError("anthropic is not installed on this deployment")
        return None


for name in [n for n in list(sys.modules) if n.split(".")[0] == "anthropic"]:
    del sys.modules[name]
sys.meta_path.insert(0, NoAnthropic())

try:
    import anthropic
except ImportError:
    pass
else:
    raise SystemExit("the SDK was importable; this proved nothing")

from us_stock_helper_analysis_api.http_app import (
    AnalysisApplication,
    AnalysisServerConfig,
    build_server,
)
from us_stock_helper_analysis_api.service import AnalysisService

sys.path.insert(0, "tests")
from test_analysis_service import AS_OF, Provider

service = AnalysisService(Provider(), clock=lambda: AS_OF)
config = AnalysisServerConfig.from_environment({})
server = build_server(service, config)
server.server_close()

status, _, body = AnalysisApplication(service, clock=lambda: AS_OF).handle(
    "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
)
assert status == 200, status
assert body["status"] == "live", body["status"]
assert body["newsInterpretation"]["status"] == "not-requested"

status, _, body = AnalysisApplication(service, clock=lambda: AS_OF).handle(
    "GET",
    "/decision",
    {"symbol": ["NVDA"], "horizon": ["short"], "adviser": ["1"]},
)
assert status == 200, status
assert body["newsInterpretation"]["status"] == "unavailable", body[
    "newsInterpretation"
]
assert body["newsInterpretation"]["reason"], "a degraded adviser must say why"
print("served-without-sdk")
"""


if __name__ == "__main__":
    unittest.main()
