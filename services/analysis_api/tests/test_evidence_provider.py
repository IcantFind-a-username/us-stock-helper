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
    def __init__(
        self,
        *,
        raises: Exception | None = None,
        failures: tuple[SourceFailure, ...] = (),
    ) -> None:
        self.raises = raises
        self.failures = failures
        self.requests: list[tuple[str, ...]] = []

    def collect_with_failures(
        self, *, symbols: tuple[str, ...] = ()
    ) -> tuple[tuple[EvidenceEvent, ...], tuple[SourceFailure, ...]]:
        self.requests.append(tuple(symbols))
        if self.raises is not None:
            raise self.raises
        return (event(),), self.failures


class FakeBars:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self.queries.append((symbol, interval))
        return ()


class ServedBars:
    """Enough completed daily candles for a decision to be served."""

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        rows = []
        for index in range(40):
            closed_at = AS_OF - timedelta(days=39 - index)
            price = 100.0 + index * 0.5
            rows.append(
                OHLCVBar(
                    symbol=symbol,
                    interval=interval,
                    opened_at=closed_at - timedelta(days=1),
                    closed_at=closed_at,
                    available_at=closed_at,
                    open=price,
                    high=price + 0.5,
                    low=price - 0.5,
                    close=price,
                    volume=1_000_000.0,
                )
            )
        return tuple(rows)


class FakeFactors:
    def __init__(self) -> None:
        self.queries: list[tuple[str, datetime]] = []
        self.answer = object()

    def snapshot(self, *, symbol: str, as_of: datetime) -> object:
        self.queries.append((symbol, as_of))
        return self.answer


class EvidenceProviderTests(unittest.TestCase):
    def test_the_provider_scopes_the_collection_to_the_requested_symbol(
        self,
    ) -> None:
        collector = FakeCollector()

        result = FeedEvidenceProvider(collector).read_evidence("NVDA")

        self.assertEqual(collector.requests, [("NVDA",)])
        self.assertEqual([item.event_id for item in result.events], ["e1"])
        self.assertEqual(result.gaps, ())

    def test_an_unreadable_source_reaches_the_caller_instead_of_an_empty_answer(
        self,
    ) -> None:
        collector = FakeCollector(
            raises=EvidenceUnavailable((SourceFailure("sec-current-8-k", "HTTP 503"),))
        )

        with self.assertRaises(EvidenceUnavailable):
            FeedEvidenceProvider(collector).read_evidence("NVDA")


class CompositeProviderTests(unittest.TestCase):
    def test_candles_and_evidence_keep_their_own_sources(self) -> None:
        bars = FakeBars()
        collector = FakeCollector()
        factors = FakeFactors()
        provider = CompositeAnalysisProvider(
            bars=bars,
            evidence=FeedEvidenceProvider(collector),
            factors=factors,
        )

        provider.bars_for("NVDA", "5m")
        provider.read_evidence("NVDA")
        answer = provider.factors_for("NVDA", AS_OF)

        self.assertEqual(bars.queries, [("NVDA", "5m")])
        self.assertEqual(collector.requests, [("NVDA",)])
        self.assertIs(answer, factors.answer)
        self.assertEqual(factors.queries, [("NVDA", AS_OF)])


class RequestScopedGapTests(unittest.TestCase):
    """A request's gap disclosure must survive a concurrent clean sweep.

    The provider is one shared instance behind a threading server. A request
    whose sweep was partial spends real time in factor reads and engine
    evaluation before its notes are assembled; when the gaps lived on the
    provider, a clean sweep for another symbol landing in that window erased
    them, and the partial read was served as a complete one — the exact
    mistake the gap notes exist to prevent.
    """

    @staticmethod
    def sweep(provider: object, symbol: str) -> object:
        # Mirrors the service's own bridging: prefer the request-scoped read,
        # fall back to the legacy provider-state shape.
        read = getattr(provider, "read_evidence", None)
        if callable(read):
            return read(symbol)
        return provider.evidence_for(symbol)

    def test_a_concurrent_clean_sweep_cannot_erase_a_gap_disclosure(
        self,
    ) -> None:
        from us_stock_helper_analysis_api.service import AnalysisService

        flaky = FakeCollector(
            failures=(SourceFailure("sec-current-8-k", "unreachable"),)
        )
        shared = FeedEvidenceProvider(flaky)
        run_sweep = self.sweep

        class ConcurrentSweepFactors:
            def snapshot(self, *, symbol: str, as_of: datetime) -> object:
                # Request B lands while request A is inside its factor read;
                # the source has recovered by then, so B's sweep is clean.
                flaky.failures = ()
                run_sweep(shared, "TSLA")
                raise RuntimeError("factors are not what this test reads")

        provider = CompositeAnalysisProvider(
            bars=ServedBars(),
            evidence=shared,
            factors=ConcurrentSweepFactors(),
        )

        payload = AnalysisService(provider, clock=lambda: AS_OF).decision(
            "NVDA", "short"
        )

        self.assertTrue(
            any("sec-current-8-k" in note for note in payload["notes"]),
            "request A's partial sweep was served as a complete one: "
            f"{payload['notes']}",
        )

    def test_the_gaps_travel_with_the_read_not_with_the_provider(self) -> None:
        collector = FakeCollector(
            failures=(SourceFailure("sec-current-8-k", "HTTP 503"),)
        )
        provider = FeedEvidenceProvider(collector)

        partial = provider.read_evidence("NVDA")
        collector.failures = ()
        clean = provider.read_evidence("NVDA")

        self.assertEqual(partial.gaps, ("sec-current-8-k（HTTP 503）",))
        self.assertEqual(clean.gaps, ())
        self.assertEqual([item.event_id for item in partial.events], ["e1"])


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
