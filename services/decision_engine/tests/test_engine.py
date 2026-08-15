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


def daily_bars(*, newest_available_at: datetime) -> tuple[OHLCVBar, ...]:
    # Production feeds every horizon completed daily candles (see
    # analysis_api's AnalysisService.interval). A daily bar's available_at is
    # a session close, not the request instant, so this models the shape live
    # data actually takes instead of the always-zero-age fixture in bars().
    rows = []
    for index in range(40):
        closed_at = newest_available_at - timedelta(days=(39 - index))
        price = 100 + index * 0.5
        rows.append(
            OHLCVBar(
                symbol="NVDA",
                interval="day",
                opened_at=closed_at - timedelta(hours=6),
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
    sentiment_measured: bool = True,
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
        sentiment_measured=sentiment_measured,
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

    def test_a_daily_bar_from_yesterdays_close_does_not_stale_gate_short_horizon(
        self,
    ) -> None:
        # Reproduces the production shape: SHORT horizon fed daily candles,
        # queried mid-session so the newest completed bar is yesterday's
        # close, roughly 22 hours old. A 20-minute intraday budget applied to
        # this data stale-gates every SHORT decision outside a 20-minute
        # window after the close.
        filing = event("filing", status=ClaimStatus.VERIFIED)
        newest_close = AS_OF - timedelta(hours=22)

        output = DecisionEngine().evaluate(
            replace(
                inputs((filing,)),
                bars=daily_bars(newest_available_at=newest_close),
                current_price_available_at=newest_close,
            )
        )

        self.assertNotIn(HardGate.STALE_DATA, output.adjusted_score.blocked_by)

    def test_a_daily_bar_many_days_old_still_stale_gates_short_horizon(
        self,
    ) -> None:
        # Widening the budget for the daily cadence must not stop catching a
        # feed that has genuinely gone quiet.
        filing = event("filing", status=ClaimStatus.VERIFIED)
        newest_close = AS_OF - timedelta(days=10)

        output = DecisionEngine().evaluate(
            replace(
                inputs((filing,)),
                bars=daily_bars(newest_available_at=newest_close),
                current_price_available_at=newest_close,
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


class UnmeasuredSentimentBridgeTests(unittest.TestCase):
    def test_the_engine_carries_the_unmeasured_flag_across_the_boundary(
        self,
    ) -> None:
        import inspect

        from decision_engine import engine as engine_module

        source = inspect.getsource(engine_module)
        # Without this the flag stops at the information layer and unreadable
        # articles rejoin the score as neutral opinions.
        self.assertIn("sentiment_measured=item.sentiment_measured", source)


class LiveInputAvailabilityTests(unittest.TestCase):
    def test_the_engine_measures_volatility_when_none_is_supplied(self) -> None:
        # Callers on the live path have bars but no volatility service; making
        # them pass a number means making one up.
        import inspect

        from decision_engine import engine as engine_module

        source = inspect.getsource(engine_module)
        self.assertIn("estimate_annualized_volatility", source)

    def test_absent_factors_reach_scoring_as_unavailable(self) -> None:
        import inspect

        from decision_engine import engine as engine_module

        source = inspect.getsource(engine_module)
        # Passing zeros for macro, geopolitics and institutional flow would
        # state neutral judgements no source made.
        self.assertIn("float | None", source)


class UnmeasuredSentimentScoringTests(unittest.TestCase):
    """A news window nobody measured must not score as a measured neutral.

    market_sentiment used to enter the score as 0.0 at full (renormalized)
    weight whenever the packet was empty or nothing could read it — the
    factor's weight scaled UP exactly when the system was most blind. An
    unmeasured reading is factor-unavailable; a measured zero is a reading.
    """

    def contribution(self, output) -> object:
        return next(
            item
            for item in output.adjusted_score.contributions
            if item.name == "market_sentiment"
        )

    def test_an_empty_news_window_reports_the_sentiment_factor_unavailable(
        self,
    ) -> None:
        output = DecisionEngine().evaluate(inputs(()))

        score = output.adjusted_score
        self.assertIn("market_sentiment", score.unavailable_factors)
        self.assertIsNone(self.contribution(output).raw_value)
        self.assertEqual(self.contribution(output).weight, 0.0)
        # SHORT weights minus the 0.20 sentiment weight: the coverage must
        # say how blind the score was, not absorb the blindness.
        self.assertAlmostEqual(score.factor_coverage, 0.8)

    def test_a_window_nothing_could_read_is_unavailable_not_neutral(
        self,
    ) -> None:
        unread = (
            event(
                "filing-a",
                status=ClaimStatus.VERIFIED,
                sentiment=0.0,
                sentiment_measured=False,
            ),
            event(
                "filing-b",
                status=ClaimStatus.VERIFIED,
                sentiment=0.0,
                sentiment_measured=False,
            ),
        )

        output = DecisionEngine().evaluate(inputs(unread))

        # The information layer itself flags the window as unmeasured; the
        # score must agree with it rather than call the same window neutral.
        self.assertIn(
            "情绪未测量", output.evidence_packet.sentiment.uncertainty
        )
        self.assertIn(
            "market_sentiment", output.adjusted_score.unavailable_factors
        )
        self.assertIsNone(self.contribution(output).raw_value)

    def test_a_measured_neutral_still_scores_as_an_available_factor(
        self,
    ) -> None:
        # 测得中性 is a reading. It must keep its weight and its zero, or the
        # fix for unmeasured windows would erase genuinely neutral ones.
        neutral = event("filing", status=ClaimStatus.VERIFIED, sentiment=0.0)

        output = DecisionEngine().evaluate(inputs((neutral,)))

        self.assertNotIn(
            "market_sentiment", output.adjusted_score.unavailable_factors
        )
        self.assertEqual(self.contribution(output).raw_value, 0.0)
        self.assertGreater(self.contribution(output).weight, 0.0)


class LivePathEndToEndTests(unittest.TestCase):
    def test_the_engine_runs_on_market_data_and_news_alone(self) -> None:
        """The shape a live caller actually has today.

        Price and news reach the live path; macro, geopolitics, institutional
        flow and fundamentals have no feed, and nothing serves volatility.
        Before this the only way to call the engine was to invent all five.
        """

        from us_stock_helper_core import Horizon, RiskPreference

        rows = bars()
        inputs = DecisionInputs(
            symbol="NVDA",
            horizon=Horizon.SHORT,
            as_of=AS_OF,
            bars=rows,
            evidence=(event("a", status=ClaimStatus.VERIFIED),),
            current_price=rows[-1].close,
            current_price_available_at=AS_OF,
            annualized_volatility=None,
            volatility_available_at=None,
            macro=None,
            geopolitics=None,
            institutional_flow=None,
            fundamentals=None,
            risk_preference=RiskPreference.BALANCED,
            invalidation_conditions=("Guidance is withdrawn.",),
        )

        output = DecisionEngine().evaluate(inputs)

        self.assertIsNotNone(output.forecast)
        self.assertIsNotNone(output.risk_plan)
        self.assertEqual(
            output.adjusted_score.unavailable_factors,
            ("fundamentals", "geopolitics", "institutional_flow", "macro"),
        )
        self.assertLess(output.adjusted_score.factor_coverage, 1.0)
        self.assertGreater(output.adjusted_score.factor_coverage, 0.0)

    def test_a_flat_market_yields_no_forecast_rather_than_a_zero_width_one(
        self,
    ) -> None:
        from us_stock_helper_core import Horizon, RiskPreference

        flat = tuple(
            replace(row, open=100.0, high=100.0, low=100.0, close=100.0)
            for row in bars()
        )
        inputs = DecisionInputs(
            symbol="NVDA",
            horizon=Horizon.SHORT,
            as_of=AS_OF,
            bars=flat,
            evidence=(event("a", status=ClaimStatus.VERIFIED),),
            current_price=flat[-1].close,
            current_price_available_at=AS_OF,
            annualized_volatility=None,
            volatility_available_at=None,
            macro=None,
            geopolitics=None,
            institutional_flow=None,
            fundamentals=None,
            risk_preference=RiskPreference.BALANCED,
            invalidation_conditions=("Guidance is withdrawn.",),
        )

        output = DecisionEngine().evaluate(inputs)

        # A band of no width presented with the same confidence as a measured
        # one is worse than saying nothing.
        self.assertIsNone(output.forecast)
        self.assertIsNone(output.risk_plan)
        self.assertIsNotNone(output.adjusted_score)
