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
