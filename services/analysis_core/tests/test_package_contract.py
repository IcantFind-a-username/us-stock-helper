from __future__ import annotations

import importlib.util
import unittest

import us_stock_helper_core.models as models
import us_stock_helper_core.temporal as temporal
import us_stock_helper_core.indicators as indicators
import us_stock_helper_core.patterns as patterns
import us_stock_helper_core.scoring as scoring
import us_stock_helper_core.evidence as evidence_module
import us_stock_helper_core.forecasting as forecasting
import us_stock_helper_core.risk as risk
import us_stock_helper_core as package


class PackageContractTests(unittest.TestCase):
    def test_analysis_core_package_is_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core"))

    def test_temporal_model_modules_are_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core.models"))
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core.temporal"))

    def test_temporal_model_api_is_present(self) -> None:
        expected_models = (
            "Direction",
            "EvidenceKind",
            "EvidenceRecord",
            "Horizon",
            "MarketContext",
            "OHLCVBar",
            "RiskPreference",
        )
        expected_temporal = ("select_bars_as_of", "select_evidence_as_of")
        self.assertTrue(all(hasattr(models, name) for name in expected_models))
        self.assertTrue(all(hasattr(temporal, name) for name in expected_temporal))

    def test_technical_modules_are_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core.indicators"))
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core.patterns"))

    def test_technical_api_is_present(self) -> None:
        expected_indicators = ("ema_series", "macd", "moving_average", "rsi")
        expected_patterns = (
            "MagicNineSignal",
            "PatternKind",
            "PatternSignal",
            "detect_double_bottom",
            "detect_head_and_shoulders",
            "detect_ma5_pullback",
            "magic_nine",
            "three_bar_fractals",
        )
        self.assertTrue(
            all(hasattr(indicators, name) for name in expected_indicators)
        )
        self.assertTrue(all(hasattr(patterns, name) for name in expected_patterns))

    def test_scoring_module_is_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("us_stock_helper_core.scoring"))

    def test_scoring_api_is_present(self) -> None:
        expected = (
            "FactorContribution",
            "FeatureSet",
            "HardGate",
            "ScoreResult",
            "extract_horizon_features",
            "score_horizon",
        )
        self.assertTrue(all(hasattr(scoring, name) for name in expected))

    def test_decision_output_modules_are_importable(self) -> None:
        for module_name in ("evidence", "forecasting", "risk"):
            self.assertIsNotNone(
                importlib.util.find_spec(f"us_stock_helper_core.{module_name}")
            )

    def test_decision_output_api_is_present(self) -> None:
        expected = {
            evidence_module: ("EvidencePacket", "freeze_evidence_packet"),
            forecasting: (
                "CalibrationStatus",
                "ScenarioCase",
                "ScenarioForecast",
                "build_scenario_forecast",
            ),
            risk: ("AnalyticalAction", "RiskPlan", "build_risk_plan"),
        }
        for module, names in expected.items():
            self.assertTrue(all(hasattr(module, name) for name in names))

    def test_public_api_is_available_from_package_root(self) -> None:
        expected = (
            "EvidencePacket",
            "FeatureSet",
            "OHLCVBar",
            "RiskPlan",
            "ScenarioForecast",
            "build_risk_plan",
            "build_scenario_forecast",
            "extract_horizon_features",
            "freeze_evidence_packet",
            "score_horizon",
            "select_bars_as_of",
        )
        self.assertTrue(all(hasattr(package, name) for name in expected))


if __name__ == "__main__":
    unittest.main()
