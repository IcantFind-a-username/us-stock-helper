from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from information_layer.feeds import (
    FRESHNESS_ATTRIBUTE,
    STALE_ATTRIBUTE,
    EvidenceUnavailable,
    SourceFailure,
)
from us_stock_helper_analysis_api.evidence_provider import (
    CompositeAnalysisProvider,
    FeedEvidenceProvider,
    evidence_provider_from_environment,
)
from us_stock_helper_core import OHLCVBar


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)
CONTACT = {"US_STOCK_HELPER_CONTACT_EMAIL": "ops@example.test"}


def event(event_id: str = "e1") -> EvidenceEvent:
    return EvidenceEvent.create(
        event_id=event_id,
        claim_key=f"claim-{event_id}",
        headline="NVIDIA lifts full-year outlook",
        summary="The company raised its guidance.",
        provenance=SourceProvenance(
            source_id="nvidia-newsroom",
            publisher_id="nvidia",
            publisher_name="NVIDIA Newsroom",
            canonical_url=f"https://nvidianews.nvidia.com/{event_id}",
            source_type="official_announcement",
            reliability=0.95,
        ),
        event_time=AS_OF - timedelta(minutes=30),
        published_at=AS_OF - timedelta(minutes=30),
        first_seen_at=AS_OF - timedelta(minutes=10),
        available_at=AS_OF - timedelta(minutes=10),
        retrieved_at=AS_OF - timedelta(minutes=10),
        claim_status=ClaimStatus.VERIFIED,
        sentiment=0.4,
        confidence=0.95,
        symbol_relevance=(("NVDA", 0.9),),
        attributes=((FRESHNESS_ATTRIBUTE, "600"), (STALE_ATTRIBUTE, "false")),
    )


class FakeCollector:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.raises = raises
        self.requests: list[tuple[str, ...]] = []

    def collect(self, *, symbols: tuple[str, ...] = ()) -> tuple[EvidenceEvent, ...]:
        self.requests.append(tuple(symbols))
        if self.raises is not None:
            raise self.raises
        return (event(),)


class FakeBars:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self.queries.append((symbol, interval))
        return ()


class EvidenceProviderTests(unittest.TestCase):
    def test_the_provider_scopes_the_collection_to_the_requested_symbol(
        self,
    ) -> None:
        collector = FakeCollector()

        events = FeedEvidenceProvider(collector).evidence_for("NVDA")

        self.assertEqual(collector.requests, [("NVDA",)])
        self.assertEqual([item.event_id for item in events], ["e1"])

    def test_an_unreadable_source_reaches_the_caller_instead_of_an_empty_answer(
        self,
    ) -> None:
        collector = FakeCollector(
            raises=EvidenceUnavailable((SourceFailure("sec-current-8-k", "HTTP 503"),))
        )

        with self.assertRaises(EvidenceUnavailable):
            FeedEvidenceProvider(collector).evidence_for("NVDA")


class CompositeProviderTests(unittest.TestCase):
    def test_candles_and_evidence_keep_their_own_sources(self) -> None:
        bars = FakeBars()
        collector = FakeCollector()
        provider = CompositeAnalysisProvider(
            bars=bars,
            evidence=FeedEvidenceProvider(collector),
        )

        provider.bars_for("NVDA", "5m")
        provider.evidence_for("NVDA")

        self.assertEqual(bars.queries, [("NVDA", "5m")])
        self.assertEqual(collector.requests, [("NVDA",)])


class ProviderConfigTests(unittest.TestCase):
    def test_a_deployment_without_a_contact_address_refuses_to_start(self) -> None:
        # EDGAR ships in the registry and demands a reachable contact, so an
        # unconfigured deployment must fail rather than poll it anonymously.
        with self.assertRaises(Exception) as failure:
            evidence_provider_from_environment({})

        self.assertIn("US_STOCK_HELPER_CONTACT_EMAIL", str(failure.exception))

    def test_the_shipped_sources_all_become_adapters(self) -> None:
        provider = evidence_provider_from_environment(dict(CONTACT))

        self.assertGreater(len(provider.collector.adapters), 1)

    def test_a_window_that_is_not_a_positive_number_is_refused(self) -> None:
        for value in ("", "0", "-1", "soon"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    evidence_provider_from_environment(
                        {
                            **CONTACT,
                            "ANALYSIS_API_EVIDENCE_STALE_AFTER_SECONDS": value,
                        }
                    )

    def test_the_configured_windows_reach_the_collector(self) -> None:
        provider = evidence_provider_from_environment(
            {
                **CONTACT,
                "ANALYSIS_API_EVIDENCE_LOOKBACK_SECONDS": "1800",
                "ANALYSIS_API_EVIDENCE_STALE_AFTER_SECONDS": "3600",
                "ANALYSIS_API_EVIDENCE_RETENTION_SECONDS": "86400",
            }
        )

        self.assertEqual(provider.collector.stale_after_seconds, 3600.0)
        self.assertEqual(provider.collector.retention_seconds, 86400.0)
        self.assertEqual(provider.collector.lookback_seconds, 1800.0)


if __name__ == "__main__":
    unittest.main()
