from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from us_stock_helper_core.models import Horizon
from us_stock_helper_core.scoring import FeatureSet, score_horizon


AS_OF = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)

# What the information layer can now actually supply: a macro reading from the
# Treasury daily yield curve and a fundamentals reading from SEC XBRL company
# facts. Geopolitics and institutional flow have no free source whose
# timeliness or objectivity this system will stand behind, and abstain on
# purpose rather than for want of an afternoon's work.
SOURCED = ("macro", "fundamentals")
ABSTAINED = ("geopolitics", "institutional_flow")


def features(horizon: Horizon, **overrides: object) -> FeatureSet:
    values: dict[str, object] = {
        "as_of": AS_OF,
        "horizon": horizon,
        "technical_trend": 0.2,
        "momentum": 0.1,
        "pattern": 0.0,
        "market_sentiment": 0.3,
        "macro": None,
        "geopolitics": None,
        "institutional_flow": None,
        "fundamentals": None,
        "adviser_factor": 0.0,
        "evidence_confidence": 0.8,
        "latest_market_data_at": AS_OF - timedelta(minutes=5),
    }
    values.update(overrides)
    return FeatureSet(**values)  # type: ignore[arg-type]


class FactorCoverageTests(unittest.TestCase):
    """Pins what the two new sources are worth, per horizon.

    These are the numbers quoted when the product claims a coverage figure, so
    they are asserted rather than recomputed by hand each time the weights
    move. A weight change that alters them should fail here and be restated
    deliberately.
    """

    def test_without_the_new_sources_coverage_is_the_old_seventy_percent(
        self,
    ) -> None:
        result = score_horizon(features(Horizon.SHORT))

        self.assertAlmostEqual(result.factor_coverage, 0.70, places=6)
        self.assertEqual(
            result.unavailable_factors,
            ("fundamentals", "geopolitics", "institutional_flow", "macro"),
        )

    def test_macro_and_fundamentals_lift_every_horizon(self) -> None:
        expected = {
            Horizon.SHORT: 0.80,
            Horizon.SWING: 0.80,
            Horizon.LONG: 0.82,
        }
        for horizon, coverage in expected.items():
            with self.subTest(horizon=horizon.value):
                result = score_horizon(
                    features(horizon, macro=0.14, fundamentals=0.83)
                )

                self.assertAlmostEqual(
                    result.factor_coverage, coverage, places=6
                )
                self.assertEqual(result.unavailable_factors, ABSTAINED)

    def test_a_supplied_factor_actually_moves_the_score(self) -> None:
        # Coverage that does not change the number would be a cosmetic
        # improvement: the weight has to reach the score, not just the report.
        blind = score_horizon(features(Horizon.LONG))
        sourced = score_horizon(
            features(Horizon.LONG, macro=-0.8, fundamentals=-0.9)
        )

        self.assertLess(sourced.objective_score, blind.objective_score)
        contributions = {
            item.name: item for item in sourced.contributions
        }
        for name in SOURCED:
            self.assertIsNotNone(contributions[name].raw_value)
            self.assertGreater(contributions[name].weight, 0.0)

    def test_an_abstaining_factor_contributes_no_points_and_no_weight(
        self,
    ) -> None:
        result = score_horizon(
            features(Horizon.SHORT, macro=0.14, fundamentals=0.83)
        )
        contributions = {item.name: item for item in result.contributions}

        for name in ABSTAINED:
            with self.subTest(factor=name):
                self.assertIsNone(contributions[name].raw_value)
                self.assertEqual(contributions[name].points, 0.0)
                self.assertEqual(contributions[name].weight, 0.0)

    def test_one_new_source_alone_is_still_an_improvement(self) -> None:
        # Fundamentals is unavailable for a filer that has not reported, and
        # macro for a Treasury outage. Neither may drag the other down.
        macro_only = score_horizon(features(Horizon.SHORT, macro=0.14))
        fundamentals_only = score_horizon(
            features(Horizon.SHORT, fundamentals=0.83)
        )

        self.assertAlmostEqual(macro_only.factor_coverage, 0.75, places=6)
        self.assertAlmostEqual(
            fundamentals_only.factor_coverage, 0.75, places=6
        )


if __name__ == "__main__":
    unittest.main()
