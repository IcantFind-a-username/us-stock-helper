from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import random
import unittest

from us_stock_helper_core.models import (
    Direction,
    EvidenceKind,
    EvidenceRecord,
    Horizon,
    MarketContext,
    OHLCVBar,
)
from us_stock_helper_core.scoring import (
    FeatureSet,
    HardGate,
    extract_horizon_features,
    score_horizon,
)


AS_OF = datetime(2026, 7, 24, 20, tzinfo=UTC)


def make_bars(closes: list[float]) -> tuple[OHLCVBar, ...]:
    start = AS_OF - timedelta(days=len(closes))
    result: list[OHLCVBar] = []
    for index, close in enumerate(closes):
        closed_at = start + timedelta(days=index + 1)
        result.append(
            OHLCVBar(
                symbol="NVDA",
                interval="1d",
                opened_at=closed_at - timedelta(hours=6),
                closed_at=closed_at,
                available_at=closed_at,
                open=close - 0.2,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=5_000_000,
            )
        )
    return tuple(result)


def make_evidence(
    evidence_id: str,
    kind: EvidenceKind,
    sentiment: float,
    confidence: float,
    sentiment_measured: bool = True,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        series_id=evidence_id,
        symbol="NVDA",
        kind=kind,
        source_name="Primary source",
        source_url=f"https://example.com/{evidence_id}",
        headline=f"Evidence {evidence_id}",
        event_time=AS_OF - timedelta(hours=3),
        published_at=AS_OF - timedelta(hours=2),
        first_seen_at=AS_OF - timedelta(hours=2) + timedelta(seconds=5),
        available_at=AS_OF - timedelta(hours=2) + timedelta(seconds=10),
        sentiment=sentiment,
        sentiment_measured=sentiment_measured,
        confidence=confidence,
    )


def context() -> MarketContext:
    return MarketContext(
        as_of=AS_OF,
        market_sentiment=0.4,
        macro=-0.2,
        geopolitics=-0.5,
        institutional_flow=0.3,
        evidence_ids=("market", "macro", "geo"),
    )


def manual_features(
    *,
    horizon: Horizon = Horizon.SHORT,
    adviser_factor: float = 0.0,
    sign: float = 1.0,
) -> FeatureSet:
    return FeatureSet(
        as_of=AS_OF,
        horizon=horizon,
        technical_trend=0.8 * sign,
        momentum=0.6 * sign,
        pattern=0.4 * sign,
        market_sentiment=0.7 * sign,
        macro=0.3 * sign,
        geopolitics=0.2 * sign,
        institutional_flow=0.5 * sign,
        fundamentals=0.6 * sign,
        adviser_factor=adviser_factor,
        evidence_confidence=0.9,
        latest_market_data_at=AS_OF,
    )


class FeatureExtractionTests(unittest.TestCase):
    def test_three_horizons_use_distinct_lookbacks_and_keep_context_explainable(self) -> None:
        closes = [100.0 + index * 0.05 for index in range(60)]
        closes += [103.0 + index for index in range(25)]
        closes += [127.0, 124.0, 122.0, 120.0, 118.0]
        bars = make_bars(closes)
        evidence = (
            make_evidence("news", EvidenceKind.NEWS, 0.8, 0.9),
            make_evidence("filing", EvidenceKind.FILING, 0.2, 0.7),
        )

        short = extract_horizon_features(Horizon.SHORT, bars, evidence, context())
        swing = extract_horizon_features(Horizon.SWING, bars, evidence, context())
        long = extract_horizon_features(Horizon.LONG, bars, evidence, context())

        self.assertLess(short.technical_trend, 0.0)
        self.assertGreater(swing.technical_trend, 0.0)
        self.assertGreater(long.technical_trend, 0.0)
        self.assertEqual((short.macro, short.geopolitics), (-0.2, -0.5))
        self.assertGreater(short.market_sentiment, context().market_sentiment)
        self.assertNotEqual(
            (short.technical_trend, short.momentum),
            (swing.technical_trend, swing.momentum),
        )

    def test_future_and_incomplete_bars_cannot_change_features(self) -> None:
        historical = make_bars([100.0 + index for index in range(35)])
        future_close = AS_OF + timedelta(days=1)
        future = OHLCVBar(
            symbol="NVDA",
            interval="1d",
            opened_at=future_close - timedelta(hours=6),
            closed_at=future_close,
            available_at=future_close,
            open=999.0,
            high=1_001.0,
            low=998.0,
            close=1_000.0,
            volume=9_000_000,
        )
        incomplete = replace(historical[-1], close=500.0, high=501.0, complete=False)
        expected = extract_horizon_features(
            Horizon.SWING, historical, (), context()
        )
        injected = extract_horizon_features(
            Horizon.SWING, (*historical, future, incomplete), (), context()
        )

        self.assertEqual(injected, expected)

    def test_same_cutoff_is_reproducible_despite_input_order(self) -> None:
        bars = list(make_bars([100.0 + index * 0.2 for index in range(65)]))
        evidence = [
            make_evidence("a", EvidenceKind.NEWS, 0.4, 0.8),
            make_evidence("b", EvidenceKind.FILING, -0.1, 0.9),
        ]
        expected = extract_horizon_features(
            Horizon.LONG, bars, evidence, context(), adviser_factor=0.5
        )
        random.Random(7).shuffle(bars)
        random.Random(9).shuffle(evidence)

        actual = extract_horizon_features(
            Horizon.LONG, bars, evidence, context(), adviser_factor=0.5
        )

        self.assertEqual(actual, expected)

    def test_feature_extraction_rejects_mixed_price_series(self) -> None:
        bars = list(make_bars([100.0 + index for index in range(35)]))
        foreign = replace(bars[-1], symbol="TSLA")

        with self.assertRaisesRegex(ValueError, "single symbol and interval"):
            extract_horizon_features(
                Horizon.SHORT, (*bars, foreign), (), context()
            )

    def test_evidence_for_another_symbol_cannot_change_features(self) -> None:
        bars = make_bars([100.0 + index for index in range(35)])
        expected = extract_horizon_features(
            Horizon.SHORT, bars, (), context()
        )
        foreign = make_evidence("foreign", EvidenceKind.NEWS, 1.0, 1.0)
        foreign = replace(foreign, symbol="TSLA")

        actual = extract_horizon_features(
            Horizon.SHORT, bars, (foreign,), context()
        )

        self.assertEqual(actual, expected)


class ExplainableScoreTests(unittest.TestCase):
    def test_missing_evidence_and_stale_market_data_fail_closed_by_default(self) -> None:
        no_evidence = score_horizon(
            replace(manual_features(), evidence_confidence=0.0)
        )
        stale = score_horizon(
            replace(
                manual_features(),
                latest_market_data_at=AS_OF - timedelta(hours=1),
            )
        )

        self.assertFalse(no_evidence.actionable)
        self.assertIn(HardGate.INSUFFICIENT_EVIDENCE, no_evidence.blocked_by)
        self.assertFalse(stale.actionable)
        self.assertIn(HardGate.STALE_DATA, stale.blocked_by)

    def test_adviser_is_bounded_to_three_points_and_does_not_replace_facts(self) -> None:
        negative_adviser = score_horizon(
            manual_features(adviser_factor=-1.0)
        )
        positive_adviser = score_horizon(
            manual_features(adviser_factor=1.0)
        )
        adviser_contribution = next(
            item
            for item in positive_adviser.contributions
            if item.name == "adviser"
        )

        self.assertAlmostEqual(
            positive_adviser.objective_score
            - negative_adviser.objective_score,
            6.0,
        )
        self.assertEqual(adviser_contribution.points, 3.0)
        self.assertEqual(positive_adviser.direction, Direction.BULLISH)

    def test_market_macro_and_geopolitical_factors_are_visible_in_explanation(self) -> None:
        result = score_horizon(manual_features())
        names = {item.name for item in result.contributions}
        self.assertTrue({"market_sentiment", "macro", "geopolitics"} <= names)
        self.assertTrue(all(item.explanation for item in result.contributions))

    def test_hard_gate_blocks_action_even_with_maximum_adviser_support(self) -> None:
        result = score_horizon(
            manual_features(adviser_factor=1.0),
            hard_gates=(HardGate.STALE_DATA,),
        )

        self.assertFalse(result.actionable)
        self.assertEqual(result.blocked_by, (HardGate.STALE_DATA,))

    def test_horizon_weights_make_the_same_facts_horizon_specific(self) -> None:
        short = score_horizon(manual_features(horizon=Horizon.SHORT))
        long = score_horizon(manual_features(horizon=Horizon.LONG))
        self.assertNotEqual(short.objective_score, long.objective_score)

    def test_out_of_range_feature_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "technical_trend"):
            replace(manual_features(), technical_trend=1.1)


if __name__ == "__main__":
    unittest.main()


class AdviserCapContractTests(unittest.TestCase):
    def test_the_adviser_cap_is_a_single_published_constant(self) -> None:
        from us_stock_helper_core.scoring import ADVISER_SCORE_CAP

        self.assertEqual(ADVISER_SCORE_CAP, 3.0)

    def test_no_adviser_factor_can_move_the_score_beyond_the_cap(self) -> None:
        from us_stock_helper_core.scoring import ADVISER_SCORE_CAP

        # Two defences: the feature model refuses an out-of-range factor, and
        # scoring caps whatever survives.
        for factor in (5.0, -5.0):
            with self.subTest(factor=factor):
                with self.assertRaisesRegex(ValueError, "adviser_factor"):
                    manual_features(adviser_factor=factor)
        for factor in (1.0, -1.0, 0.5):
            with self.subTest(factor=factor):
                result = score_horizon(manual_features(adviser_factor=factor))
                adviser = next(
                    item for item in result.contributions if item.name == "adviser"
                )
                self.assertLessEqual(abs(adviser.points), ADVISER_SCORE_CAP)


class UnmeasuredEvidenceTests(unittest.TestCase):
    def test_unread_evidence_does_not_dilute_the_sentiment_it_carries_none_of(
        self,
    ) -> None:
        # An article no scorer could read is not a neutral opinion. Averaging
        # it in as 0.0 pulls a real signal toward the middle, which is the
        # missing-data-as-judgement failure the project forbids.
        bars = make_bars([100.0 + i * 0.5 for i in range(60)])
        loud = (make_evidence("a", EvidenceKind.NEWS, 0.8, 0.9),)
        loud_plus_silent = loud + (
            make_evidence(
                "b", EvidenceKind.NEWS, 0.0, 0.9, sentiment_measured=False
            ),
        )

        only = extract_horizon_features(Horizon.SHORT, bars, loud, context())
        both = extract_horizon_features(
            Horizon.SHORT, bars, loud_plus_silent, context()
        )

        self.assertEqual(only.market_sentiment, both.market_sentiment)

    def test_unread_evidence_still_counts_toward_evidence_confidence(
        self,
    ) -> None:
        bars = make_bars([100.0 + i * 0.5 for i in range(60)])
        records = (
            make_evidence("a", EvidenceKind.NEWS, 0.8, 0.9),
            make_evidence(
                "b", EvidenceKind.NEWS, 0.0, 0.9, sentiment_measured=False
            ),
        )

        features = extract_horizon_features(
            Horizon.SHORT, bars, records, context()
        )

        # It carries no opinion, but it is still a cited, corroborating source.
        self.assertGreater(features.evidence_confidence, 0.0)

    def test_a_record_cannot_claim_a_reading_it_never_took(self) -> None:
        with self.assertRaisesRegex(ValueError, "sentiment_measured"):
            make_evidence(
                "bad", EvidenceKind.NEWS, 0.5, 0.9, sentiment_measured=False
            )


class UnavailableFactorTests(unittest.TestCase):
    def test_a_missing_factor_is_not_scored_as_neutral(self) -> None:
        # Filling an absent factor with 0.0 states a neutral judgement nobody
        # made, and it drags the score toward 50 in proportion to how much
        # data is missing — the more blind the system is, the more confident
        # it looks.
        complete = manual_features(sign=1.0)
        partial = replace(complete, macro=None, geopolitics=None)

        zero_filled = score_horizon(
            replace(complete, macro=0.0, geopolitics=0.0)
        ).objective_score
        renormalized = score_horizon(partial).objective_score
        full = score_horizon(complete).objective_score

        # Zero-filling pulls the score toward the middle; renormalizing keeps
        # it where the evidence that does exist puts it.
        self.assertLess(zero_filled, full)
        self.assertGreaterEqual(renormalized, full)
        self.assertGreater(renormalized, zero_filled)

    def test_the_result_names_the_factors_it_could_not_use(self) -> None:
        features = replace(
            manual_features(), macro=None, geopolitics=None, fundamentals=None
        )

        result = score_horizon(features)

        self.assertEqual(
            result.unavailable_factors, ("fundamentals", "geopolitics", "macro")
        )
        self.assertLess(result.factor_coverage, 1.0)
        self.assertGreater(result.factor_coverage, 0.0)

    def test_full_coverage_is_reported_when_everything_is_present(self) -> None:
        result = score_horizon(manual_features())

        self.assertEqual(result.unavailable_factors, ())
        self.assertEqual(result.factor_coverage, 1.0)

    def test_an_unavailable_factor_contributes_no_points(self) -> None:
        result = score_horizon(replace(manual_features(), macro=None))

        macro = next(
            item for item in result.contributions if item.name == "macro"
        )
        self.assertIsNone(macro.raw_value)
        self.assertEqual(macro.points, 0.0)
        self.assertIn("unavailable", macro.explanation.lower())

    def test_a_score_with_no_usable_factor_is_not_actionable(self) -> None:
        blind = replace(
            manual_features(),
            technical_trend=None,
            momentum=None,
            pattern=None,
            market_sentiment=None,
            macro=None,
            geopolitics=None,
            institutional_flow=None,
            fundamentals=None,
        )

        result = score_horizon(blind)

        self.assertEqual(result.factor_coverage, 0.0)
        self.assertFalse(result.actionable)
        self.assertEqual(result.objective_score, 50.0)


class ContextAvailabilityTests(unittest.TestCase):
    def test_a_context_may_declare_a_factor_it_has_no_source_for(self) -> None:
        # Today only price and news reach the live path; macro, geopolitics
        # and institutional flow have no feed. Requiring a number forces the
        # caller to invent one.
        context = MarketContext(
            as_of=AS_OF,
            market_sentiment=0.4,
            macro=None,
            geopolitics=None,
            institutional_flow=None,
        )
        bars = make_bars([100.0 + index * 0.5 for index in range(60)])

        features = extract_horizon_features(Horizon.SHORT, bars, (), context)

        self.assertIsNone(features.macro)
        self.assertIsNone(features.geopolitics)
        self.assertIsNone(features.institutional_flow)
        self.assertIsNotNone(features.market_sentiment)

    def test_a_score_from_a_partial_context_reports_its_coverage(self) -> None:
        context = MarketContext(
            as_of=AS_OF,
            market_sentiment=0.4,
            macro=None,
            geopolitics=None,
            institutional_flow=None,
        )
        bars = make_bars([100.0 + index * 0.5 for index in range(60)])

        result = score_horizon(
            extract_horizon_features(Horizon.SHORT, bars, (), context)
        )

        self.assertIn("macro", result.unavailable_factors)
        self.assertIn("institutional_flow", result.unavailable_factors)
        # Fundamentals has no feed either and now says so, rather than
        # counting itself as a measured neutral.
        self.assertEqual(result.factor_coverage, 0.70)
        # Partial coverage is reported, not punished: actionability stays a
        # matter for the hard gates, which here fire on the absent evidence.
        self.assertNotIn("coverage", " ".join(gate.value for gate in result.blocked_by))


class UncomputableFactorTests(unittest.TestCase):
    def test_too_few_bars_leaves_the_technical_factors_unmeasured(self) -> None:
        """The extractor promised None and delivered zero.

        FeatureSet documents that None means no source could supply a factor
        and that filling absence with zero states a judgement nobody made.
        The extractor honoured that only for the context factors: technical
        trend, momentum and pattern silently became 0.0 whenever there were
        too few bars to compute them, so coverage was overstated and the
        score was pulled toward the middle exactly when least was known.
        """

        bars = make_bars([100.0, 100.5, 101.0])

        features = extract_horizon_features(Horizon.SHORT, bars, (), context())

        self.assertIsNone(features.technical_trend)
        self.assertIsNone(features.momentum)

    def test_an_uncomputable_factor_lowers_the_reported_coverage(self) -> None:
        short_series = extract_horizon_features(
            Horizon.SHORT, make_bars([100.0, 100.5, 101.0]), (), context()
        )
        long_series = extract_horizon_features(
            Horizon.SHORT,
            make_bars([100.0 + index * 0.5 for index in range(60)]),
            (),
            context(),
        )

        self.assertLess(
            score_horizon(short_series).factor_coverage,
            score_horizon(long_series).factor_coverage,
        )

    def test_fundamentals_defaults_to_unavailable_not_neutral(self) -> None:
        import inspect

        signature = inspect.signature(extract_horizon_features)

        # A default of 0.0 hands every caller that omits the argument a
        # measured neutral for a factor that has no feed at all.
        self.assertIsNone(signature.parameters["fundamentals"].default)
