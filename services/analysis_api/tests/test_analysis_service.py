from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from us_stock_helper_analysis_api.service import AnalysisService
from us_stock_helper_core import OHLCVBar


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)


def bars(count: int = 40, *, flat: bool = False) -> tuple[OHLCVBar, ...]:
    rows = []
    for index in range(count):
        closed_at = AS_OF - timedelta(minutes=(count - 1 - index) * 5)
        price = 100.0 if flat else 100.0 + index * 0.5
        rows.append(
            OHLCVBar(
                symbol="NVDA",
                interval="5m",
                opened_at=closed_at - timedelta(minutes=5),
                closed_at=closed_at,
                available_at=closed_at,
                open=price,
                high=price if flat else price + 0.5,
                low=price if flat else price - 0.5,
                close=price,
                volume=1_000_000.0,
            )
        )
    return tuple(rows)


def evidence() -> tuple[EvidenceEvent, ...]:
    return tuple(
        EvidenceEvent.create(
            event_id=event_id,
            claim_key=f"claim-{event_id}",
            headline="NVIDIA raises full-year revenue guidance",
            summary="The chipmaker lifted its outlook.",
            provenance=SourceProvenance(
                source_id=f"feed:{publisher}",
                publisher_id=publisher,
                publisher_name=publisher,
                canonical_url=f"https://{publisher}.example/{event_id}",
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
        for event_id, publisher in (("a", "reuters"), ("b", "bloomberg"))
    )


class Provider:
    def __init__(self, *, rows: tuple[OHLCVBar, ...] | None = None) -> None:
        self.rows = bars() if rows is None else rows
        self.queries: list[tuple[str, str]] = []

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self.queries.append((symbol, interval))
        return self.rows

    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
        return evidence()


def service(provider: Provider | None = None) -> AnalysisService:
    return AnalysisService(provider or Provider(), clock=lambda: AS_OF)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= _all_keys(item)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found |= _all_keys(item)
        return found
    return set()


class AnalysisContractTests(unittest.TestCase):
    def test_a_decision_reports_its_score_and_what_it_could_not_see(self) -> None:
        result = service().decision("NVDA", "short")

        self.assertEqual(result["schemaVersion"], "1")
        self.assertEqual(result["symbol"], "NVDA")
        self.assertEqual(result["horizon"], "short")
        self.assertEqual(result["decisionCutoff"], "2026-07-25T16:00:00Z")
        score = result["score"]
        self.assertGreaterEqual(score["value"], 0.0)
        self.assertLessEqual(score["value"], 100.0)
        # Macro, geopolitics, institutional flow and fundamentals have no feed
        # yet, and the response has to say so rather than imply a full picture.
        self.assertIn("macro", score["unavailableFactors"])
        self.assertLess(score["factorCoverage"], 1.0)
        self.assertGreater(score["factorCoverage"], 0.0)

    def test_every_factor_contribution_is_itemized(self) -> None:
        result = service().decision("NVDA", "short")

        names = {item["name"] for item in result["score"]["contributions"]}
        self.assertIn("technical_trend", names)
        unavailable = next(
            item
            for item in result["score"]["contributions"]
            if item["name"] == "macro"
        )
        self.assertIsNone(unavailable["rawValue"])
        self.assertEqual(unavailable["points"], 0.0)

    def test_the_forecast_carries_three_scenarios_and_its_disclaimer(self) -> None:
        forecast = service().decision("NVDA", "short")["forecast"]

        self.assertIsNotNone(forecast)
        kinds = [case["kind"] for case in forecast["cases"]]
        self.assertEqual(sorted(kinds), ["base", "bear", "bull"])
        self.assertAlmostEqual(
            sum(case["probability"] for case in forecast["cases"]), 1.0, places=9
        )
        self.assertTrue(forecast["disclaimer"])
        self.assertEqual(forecast["calibrationStatus"], "uncalibrated")
        self.assertTrue(forecast["invalidationConditions"])

    def test_an_unmeasurable_volatility_yields_no_forecast_and_says_why(
        self,
    ) -> None:
        result = service(Provider(rows=bars(flat=True))).decision("NVDA", "short")

        # A band of no width shown as confidently as a measured one is worse
        # than showing nothing.
        self.assertIsNone(result["forecast"])
        self.assertIsNone(result["riskPlan"])
        self.assertTrue(
            any("volatility" in note.lower() for note in result["notes"])
        )

    def test_the_plan_is_analysis_only_and_never_offers_to_trade(self) -> None:
        result = service().decision("NVDA", "short")

        plan = result["riskPlan"]
        self.assertIn(plan["action"], {"long", "short", "watch", "avoid"})
        self.assertLessEqual(plan["maxPositionPercent"], 100.0)
        self.assertGreaterEqual(plan["leverage"], 0.0)
        # The invariant is that nothing here can act, not that the word
        # "order" is absent — the plan's own warning says it cannot place one.
        self.assertTrue(
            any("cannot" in warning.lower() for warning in plan["warnings"])
        )
        forbidden_fields = {
            "orderId",
            "submitOrder",
            "quantity",
            "accountId",
            "brokerToken",
        }
        self.assertEqual(forbidden_fields & set(_all_keys(result)), set())

    def test_evidence_citations_travel_with_the_conclusion(self) -> None:
        result = service().decision("NVDA", "short")

        self.assertTrue(result["citations"])
        for citation in result["citations"]:
            self.assertTrue(citation["url"].startswith("https://"))
            self.assertTrue(citation["publisher"])
            self.assertTrue(citation["availableAt"])

    def test_an_unknown_horizon_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            service().decision("NVDA", "forever")

    def test_the_requested_symbol_reaches_the_provider_normalized(self) -> None:
        provider = Provider()

        service(provider).decision(" nvda ", "short")

        self.assertEqual(provider.queries[0][0], "NVDA")

    def test_no_bars_yields_an_explicit_unavailable_rather_than_a_guess(
        self,
    ) -> None:
        result = service(Provider(rows=())).decision("NVDA", "short")

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["score"])
        self.assertTrue(result["notes"])

    def test_a_live_decision_is_marked_live(self) -> None:
        self.assertEqual(service().decision("NVDA", "short")["status"], "live")


if __name__ == "__main__":
    unittest.main()
