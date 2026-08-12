from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from information_layer import (
    ClaimStatus,
    EvidenceEvent,
    EvidencePacketBuilder,
    SourceAdapter,
    SourceProvenance,
    compact_render,
    prioritize_events,
)
from information_layer.clustering import build_clusters


UTC = timezone.utc
AS_OF = datetime(2026, 7, 24, 16, 0, tzinfo=UTC)


def source(
    publisher_id: str,
    *,
    reliability: float = 0.8,
    ownership_group_id: str | None = None,
    syndication_origin_id: str | None = None,
) -> SourceProvenance:
    return SourceProvenance(
        source_id=f"feed:{publisher_id}",
        publisher_id=publisher_id,
        publisher_name=publisher_id.upper(),
        canonical_url=f"https://example.test/{publisher_id}",
        source_type="news",
        reliability=reliability,
        ownership_group_id=ownership_group_id,
        syndication_origin_id=syndication_origin_id,
    )


def event(
    event_id: str,
    *,
    publisher_id: str = "wire",
    claim_key: str = "nvda|supply|raised",
    headline: str = "NVDA supplier raises shipment forecast",
    summary: str = "Shipment guidance was raised.",
    sentiment: float = 0.6,
    sentiment_measured: bool = True,
    confidence: float = 0.8,
    status: ClaimStatus = ClaimStatus.REPORTED,
    first_seen_at: datetime = AS_OF - timedelta(minutes=15),
    available_at: datetime = AS_OF - timedelta(minutes=14),
    retrieved_at: datetime = AS_OF - timedelta(minutes=13),
    revised_at: datetime | None = None,
    revision_of: str | None = None,
    revision_number: int = 0,
    provenance: SourceProvenance | None = None,
) -> EvidenceEvent:
    return EvidenceEvent.create(
        event_id=event_id,
        claim_key=claim_key,
        headline=headline,
        summary=summary,
        provenance=provenance or source(publisher_id),
        event_time=AS_OF - timedelta(minutes=30),
        published_at=AS_OF - timedelta(minutes=20),
        first_seen_at=first_seen_at,
        available_at=available_at,
        retrieved_at=retrieved_at,
        revised_at=revised_at,
        revision_of=revision_of,
        revision_number=revision_number,
        claim_status=status,
        sentiment=sentiment,
        sentiment_measured=sentiment_measured,
        confidence=confidence,
        symbol_relevance=(("NVDA", 0.95),),
        entity_relevance=(("NVIDIA", 0.9),),
        geopolitical_tags=("US_CHINA_TECH",),
        macro_tags=("SEMICONDUCTOR_CYCLE",),
    )


class FakeAdapter:
    adapter_id = "fake"

    def fetch(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> tuple[EvidenceEvent, ...]:
        return ()


class PointInTimeTests(unittest.TestCase):
    def test_future_first_seen_available_and_revision_are_excluded(self) -> None:
        original = event("e-original")
        future_seen = event(
            "e-future-seen",
            claim_key="nvda|order|future",
            first_seen_at=AS_OF + timedelta(seconds=1),
            available_at=AS_OF + timedelta(seconds=2),
            retrieved_at=AS_OF + timedelta(seconds=3),
        )
        future_available = event(
            "e-future-available",
            claim_key="nvda|margin|future",
            available_at=AS_OF + timedelta(seconds=1),
            retrieved_at=AS_OF + timedelta(seconds=2),
        )
        future_revision = event(
            "e-revision",
            revision_of=original.event_id,
            revision_number=1,
            revised_at=AS_OF + timedelta(seconds=1),
            available_at=AS_OF + timedelta(seconds=1),
            retrieved_at=AS_OF + timedelta(seconds=2),
        )

        packet = EvidencePacketBuilder().build(
            (original, future_seen, future_available, future_revision),
            as_of=AS_OF,
            focus_symbols=("NVDA",),
        )

        self.assertEqual(packet.included_event_ids, ("e-original",))
        self.assertEqual(packet.excluded_future_event_ids, (
            "e-future-available",
            "e-future-seen",
            "e-revision",
        ))
        self.assertTrue(all(citation.available_at <= AS_OF for citation in packet.citations))

    def test_retrieval_after_cutoff_is_not_point_in_time_available(self) -> None:
        late_retrieval = event(
            "e-late-retrieval",
            retrieved_at=AS_OF + timedelta(microseconds=1),
        )
        packet = EvidencePacketBuilder().build((late_retrieval,), as_of=AS_OF)
        self.assertEqual(packet.included_event_ids, ())
        self.assertEqual(packet.excluded_future_event_ids, ("e-late-retrieval",))

    def test_symbol_packet_keeps_global_macro_and_geopolitical_context(self) -> None:
        global_context = replace(
            event("global-context"),
            symbol_relevance=(),
            macro_tags=("FED_POLICY",),
            geopolitical_tags=("US_CHINA_TECH",),
        )

        packet = EvidencePacketBuilder().build(
            (global_context,),
            as_of=AS_OF,
            focus_symbols=("NVDA",),
        )

        self.assertEqual(packet.included_event_ids, ("global-context",))


class ProvenanceAndClusteringTests(unittest.TestCase):
    def test_citation_keeps_source_and_complete_temporal_provenance(self) -> None:
        revised_at = AS_OF - timedelta(minutes=3)
        item = event(
            "audited",
            revised_at=revised_at,
            revision_of="prior",
            revision_number=1,
            available_at=revised_at,
            retrieved_at=AS_OF - timedelta(minutes=2),
        )

        citation = EvidencePacketBuilder().build((item,), as_of=AS_OF).citations[0]

        self.assertEqual(citation.source_id, item.provenance.source_id)
        self.assertEqual(citation.publisher_id, item.provenance.publisher_id)
        self.assertEqual(citation.event_time, item.event_time)
        self.assertEqual(citation.revised_at, revised_at)
        self.assertEqual(citation.revision_of, "prior")
        self.assertEqual(citation.claim_status, ClaimStatus.REPORTED)

    def test_reposts_do_not_inflate_independent_source_count(self) -> None:
        original = event(
            "wire-original",
            provenance=source("wire", ownership_group_id="wire-group"),
        )
        repost = event(
            "portal-repost",
            provenance=source(
                "portal",
                ownership_group_id="portal-group",
                syndication_origin_id="wire",
            ),
        )
        independent = event(
            "exchange-confirmation",
            provenance=source("exchange", reliability=0.95),
        )

        packet = EvidencePacketBuilder().build(
            (original, repost, independent),
            as_of=AS_OF,
        )

        self.assertEqual(len(packet.clusters), 1)
        cluster = packet.clusters[0]
        self.assertEqual(cluster.independent_source_count, 2)
        self.assertEqual(cluster.event_ids, (
            "exchange-confirmation",
            "portal-repost",
            "wire-original",
        ))

    def test_identical_content_clusters_even_if_adapter_claim_keys_differ(self) -> None:
        first = event("first", claim_key="adapter-a|shipment")
        second = event("second", claim_key="adapter-b|guidance")

        packet = EvidencePacketBuilder().build((first, second), as_of=AS_OF)

        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(len(packet.clusters), 1)

    def test_revision_chain_uses_latest_visible_revision_and_keeps_history(self) -> None:
        original = event("filing-v0", sentiment=0.7)
        revision = event(
            "filing-v1",
            sentiment=-0.4,
            headline="NVDA supplier corrects shipment forecast",
            summary="The earlier increase was withdrawn.",
            revision_of="filing-v0",
            revision_number=1,
            revised_at=AS_OF - timedelta(minutes=3),
            available_at=AS_OF - timedelta(minutes=3),
            retrieved_at=AS_OF - timedelta(minutes=2),
        )

        packet = EvidencePacketBuilder().build((original, revision), as_of=AS_OF)
        cluster = packet.clusters[0]

        self.assertEqual(cluster.active_event_id, "filing-v1")
        self.assertEqual(cluster.revision_chain, ("filing-v0", "filing-v1"))
        self.assertEqual(cluster.sentiment, -0.4)
        self.assertNotEqual(original.content_hash, revision.content_hash)

    def test_revision_chain_does_not_mislabel_independent_sources_as_revisions(self) -> None:
        first = event("publisher-a", publisher_id="a")
        second = event("publisher-b", publisher_id="b")

        packet = EvidencePacketBuilder().build((first, second), as_of=AS_OF)

        self.assertEqual(len(packet.clusters[0].revision_chain), 1)
        self.assertIn(
            packet.clusters[0].revision_chain[0],
            packet.clusters[0].active_event_ids,
        )

    def test_conflicting_sources_are_preserved_with_counterevidence(self) -> None:
        positive = event("company", publisher_id="company", sentiment=0.8)
        negative = event(
            "regulator",
            publisher_id="regulator",
            headline="Regulator disputes shipment characterization",
            summary="The regulator says the increase is not confirmed.",
            sentiment=-0.8,
        )

        packet = EvidencePacketBuilder().build((positive, negative), as_of=AS_OF)

        self.assertEqual(packet.clusters[0].event_ids, ("company", "regulator"))
        self.assertTrue(packet.clusters[0].has_conflict)
        self.assertIn(packet.clusters[0].cluster_id, packet.sentiment.evidence_cluster_ids)
        self.assertIn(packet.clusters[0].cluster_id, packet.sentiment.counterevidence_cluster_ids)
        self.assertIn("来源冲突", packet.sentiment.uncertainty)

    def test_market_and_entity_tags_survive_normalization(self) -> None:
        packet = EvidencePacketBuilder().build((event("tagged"),), as_of=AS_OF)
        active = packet.clusters[0]
        self.assertEqual(active.symbol_relevance, (("NVDA", 0.95),))
        self.assertEqual(active.entity_relevance, (("NVIDIA", 0.9),))
        self.assertEqual(active.geopolitical_tags, ("US_CHINA_TECH",))
        self.assertEqual(active.macro_tags, ("SEMICONDUCTOR_CYCLE",))


class SafetyAndRenderingTests(unittest.TestCase):
    def test_evidence_rejects_published_after_first_seen(self) -> None:
        item = event("bad-published-order")
        with self.assertRaises(ValueError):
            replace(
                item,
                published_at=item.first_seen_at + timedelta(seconds=1),
            )

    def test_evidence_rejects_first_seen_after_available(self) -> None:
        item = event("bad-first-seen-order")
        with self.assertRaises(ValueError):
            replace(
                item,
                first_seen_at=item.available_at + timedelta(seconds=1),
            )

    def test_evidence_rejects_available_after_retrieved(self) -> None:
        item = event("bad-available-order")
        with self.assertRaises(ValueError):
            replace(
                item,
                available_at=item.retrieved_at + timedelta(seconds=1),
            )

    def test_evidence_rejects_revision_after_availability_or_retrieval(self) -> None:
        item = event(
            "bad-revision-order",
            revision_of="prior",
            revision_number=1,
        )
        with self.assertRaises(ValueError):
            replace(
                item,
                revised_at=item.available_at + timedelta(seconds=1),
            )
        with self.assertRaises(ValueError):
            replace(
                item,
                revised_at=item.retrieved_at + timedelta(seconds=1),
            )

    def test_scheduled_future_event_time_is_allowed_after_public_announcement(self) -> None:
        item = event("scheduled")
        scheduled = replace(item, event_time=AS_OF + timedelta(days=1))
        self.assertGreater(scheduled.event_time, scheduled.retrieved_at)

    def test_untyped_claim_status_cannot_bypass_rumor_gate(self) -> None:
        with self.assertRaises(TypeError):
            EvidenceEvent.create(
                event_id="bad-status",
                claim_key="nvda|rumor",
                headline="Unverified message",
                summary="A social post made an unsupported claim.",
                provenance=source("social"),
                event_time=AS_OF - timedelta(minutes=20),
                published_at=AS_OF - timedelta(minutes=15),
                first_seen_at=AS_OF - timedelta(minutes=14),
                available_at=AS_OF - timedelta(minutes=13),
                retrieved_at=AS_OF - timedelta(minutes=12),
                claim_status="rumor",  # type: ignore[arg-type]
                sentiment=1.0,
                confidence=1.0,
            )

        with self.assertRaises(TypeError):
            replace(
                event("valid-before-replace"),
                claim_status="rumor",  # type: ignore[arg-type]
            )

    def test_rumor_is_observational_and_cannot_create_action_signal(self) -> None:
        rumor = event(
            "social-rumor",
            publisher_id="social",
            status=ClaimStatus.RUMOR,
            sentiment=1.0,
            confidence=1.0,
        )

        packet = EvidencePacketBuilder().build((rumor,), as_of=AS_OF)

        self.assertEqual(packet.actionable_cluster_ids, ())
        self.assertEqual(len(packet.observational_cluster_ids), 1)
        self.assertEqual(packet.sentiment.action_score, 0.0)
        self.assertEqual(packet.sentiment.decision_signal, "observe_only")
        self.assertTrue(packet.investigation_requests)
        self.assertIn("传闻", packet.investigation_requests[0].reason)

    def test_one_unverified_report_cannot_cross_the_action_gate(self) -> None:
        single_report = event(
            "single-news-report",
            status=ClaimStatus.REPORTED,
            sentiment=1.0,
            confidence=1.0,
            provenance=source("news", reliability=0.9),
        )

        packet = EvidencePacketBuilder().build((single_report,), as_of=AS_OF)

        self.assertEqual(packet.actionable_cluster_ids, ())
        self.assertEqual(packet.sentiment.action_score, 0.0)
        self.assertEqual(packet.sentiment.decision_signal, "neutral")
        self.assertIn("独立来源不足", packet.investigation_requests[0].reason)

    def test_one_authoritative_verified_source_may_enter_the_action_score(self) -> None:
        filing = event(
            "sec-filing",
            status=ClaimStatus.VERIFIED,
            sentiment=0.7,
            confidence=0.95,
            provenance=source("sec", reliability=0.98),
        )

        packet = EvidencePacketBuilder().build((filing,), as_of=AS_OF)

        self.assertEqual(len(packet.actionable_cluster_ids), 1)
        self.assertGreater(packet.sentiment.action_score, 0)

    def test_rumor_cannot_move_action_score_inside_mixed_cluster(self) -> None:
        reported = event(
            "reported",
            publisher_id="filing",
            sentiment=-0.5,
            confidence=1.0,
            status=ClaimStatus.VERIFIED,
            provenance=source("filing", reliability=1.0),
        )
        rumor = event(
            "rumor",
            publisher_id="social",
            sentiment=1.0,
            confidence=1.0,
            status=ClaimStatus.RUMOR,
            provenance=source("social", reliability=1.0),
        )

        packet = EvidencePacketBuilder().build((reported, rumor), as_of=AS_OF)

        self.assertEqual(packet.sentiment.action_score, -0.5)
        self.assertGreater(packet.sentiment.observed_score, -0.5)
        self.assertEqual(packet.sentiment.decision_signal, "short_bias")

    def test_watchlist_priority_never_changes_sentiment_evidence(self) -> None:
        nvda = event("nvda")
        unrelated = EvidenceEvent.create(
            event_id="msft",
            claim_key="msft|cloud|growth",
            headline="MSFT cloud growth accelerates",
            summary="Reported cloud growth accelerated.",
            provenance=source("msft-wire"),
            event_time=AS_OF - timedelta(minutes=20),
            published_at=AS_OF - timedelta(minutes=15),
            first_seen_at=AS_OF - timedelta(minutes=14),
            available_at=AS_OF - timedelta(minutes=13),
            retrieved_at=AS_OF - timedelta(minutes=12),
            claim_status=ClaimStatus.REPORTED,
            sentiment=-0.3,
            confidence=0.7,
            symbol_relevance=(("MSFT", 0.9),),
        )
        reordered = prioritize_events((unrelated, nvda), ("NVDA",))

        baseline = EvidencePacketBuilder().build((unrelated, nvda), as_of=AS_OF)
        prioritized = EvidencePacketBuilder().build(reordered, as_of=AS_OF)

        self.assertEqual(reordered[0].event_id, "nvda")
        self.assertEqual(baseline.sentiment, prioritized.sentiment)
        self.assertEqual(baseline.included_event_ids, prioritized.included_event_ids)
        self.assertEqual(baseline.version_id, prioritized.version_id)

    def test_packet_is_immutable_and_version_is_deterministic(self) -> None:
        builder = EvidencePacketBuilder()
        first = builder.build((event("stable"),), as_of=AS_OF)
        second = builder.build((event("stable"),), as_of=AS_OF)
        self.assertEqual(first.version_id, second.version_id)
        with self.assertRaises(FrozenInstanceError):
            first.version_id = "mutated"  # type: ignore[misc]

    def test_compact_render_respects_budget_and_keeps_a_citation(self) -> None:
        events = tuple(
            event(
                f"event-{index}",
                claim_key=f"nvda|claim|{index}",
                headline=f"NVDA evidence headline {index}",
                summary="A deliberately verbose evidence summary for compact rendering.",
                sentiment=0.5 if index % 2 == 0 else -0.2,
            )
            for index in range(8)
        )
        packet = EvidencePacketBuilder().build(events, as_of=AS_OF)

        rendered = compact_render(packet, max_tokens=80)

        self.assertLessEqual(rendered.estimated_tokens, 80)
        self.assertIn("结论", rendered.text)
        self.assertRegex(rendered.text, r"\[C\d+\]")
        self.assertTrue(rendered.truncated)

    def test_source_adapter_protocol_is_runtime_checkable(self) -> None:
        self.assertIsInstance(FakeAdapter(), SourceAdapter)


if __name__ == "__main__":
    unittest.main()


class UnmeasuredSentimentTests(unittest.TestCase):
    def test_an_unmeasured_event_does_not_drag_the_cluster_toward_neutral(
        self,
    ) -> None:
        # A headline the lexicon cannot read is not a neutral opinion. Counting
        # it as 0.0 is exactly the "missing data disguised as a judgement" the
        # project forbids.
        measured_only = build_clusters((event("a", sentiment=0.8),), AS_OF)
        with_silent = build_clusters(
            (
                event("a", sentiment=0.8),
                event(
                    "b",
                    publisher_id="other",
                    sentiment=0.0,
                    sentiment_measured=False,
                ),
            ),
            AS_OF,
        )

        self.assertEqual(
            measured_only[0].sentiment, with_silent[0].sentiment
        )

    def test_an_unmeasured_event_still_counts_as_an_independent_source(
        self,
    ) -> None:
        clusters = build_clusters(
            (
                event("a", sentiment=0.8),
                event(
                    "b",
                    publisher_id="other",
                    sentiment=0.0,
                    sentiment_measured=False,
                ),
            ),
            AS_OF,
        )

        # It carries no opinion, but it is still a second outlet reporting the
        # same claim, which is what the corroboration rule counts.
        self.assertEqual(clusters[0].independent_source_count, 2)

    def test_a_cluster_of_only_unmeasured_events_reports_zero_not_a_verdict(
        self,
    ) -> None:
        clusters = build_clusters(
            (
                event("a", sentiment=0.0, sentiment_measured=False),
                event(
                    "b",
                    publisher_id="other",
                    sentiment=0.0,
                    sentiment_measured=False,
                ),
            ),
            AS_OF,
        )

        self.assertEqual(clusters[0].sentiment, 0.0)

    def test_an_event_cannot_claim_a_score_it_did_not_measure(self) -> None:
        with self.assertRaisesRegex(ValueError, "sentiment_measured"):
            event("bad", sentiment=0.7, sentiment_measured=False)
