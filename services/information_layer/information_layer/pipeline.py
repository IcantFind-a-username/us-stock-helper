from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Iterable, Sequence

from .clustering import build_clusters
from .models import (
    Citation,
    EvidenceEvent,
    EvidencePacket,
    InvestigationRequest,
    _require_aware,
)
from .sentiment import assess_sentiment, make_investigation_requests


def prioritize_events(
    events: Iterable[EvidenceEvent],
    watchlist_symbols: Iterable[str],
) -> tuple[EvidenceEvent, ...]:
    """Move relevant items first without creating or modifying evidence."""

    watchlist = {symbol.upper() for symbol in watchlist_symbols}

    def priority(item: EvidenceEvent) -> tuple[int, datetime, str]:
        relevant = any(
            symbol in watchlist for symbol, _ in item.symbol_relevance
        )
        return (0 if relevant else 1, item.first_seen_at, item.event_id)

    return tuple(sorted(events, key=priority))


class EvidencePacketBuilder:
    def build(
        self,
        events: Iterable[EvidenceEvent],
        *,
        as_of: datetime,
        focus_symbols: Iterable[str] = (),
    ) -> EvidencePacket:
        _require_aware(as_of, "as_of")
        focus = tuple(sorted({symbol.upper() for symbol in focus_symbols}))
        visible: list[EvidenceEvent] = []
        future: list[EvidenceEvent] = []

        for item in self._unique_events(events):
            if not item.is_visible_at(as_of):
                future.append(item)
            elif not focus or self._is_relevant(item, focus):
                visible.append(item)

        visible.sort(key=lambda item: item.event_id)
        clusters = build_clusters(visible, as_of)
        citations = self._make_citations(visible)
        sentiment = assess_sentiment(clusters)
        return EvidencePacket(
            version_id=self._version_id(as_of, focus, visible),
            as_of=as_of,
            focus_symbols=focus,
            clusters=clusters,
            citations=citations,
            sentiment=sentiment,
            actionable_cluster_ids=tuple(
                cluster.cluster_id
                for cluster in clusters
                if cluster.actionable
            ),
            observational_cluster_ids=tuple(
                cluster.cluster_id
                for cluster in clusters
                if not cluster.actionable
            ),
            investigation_requests=make_investigation_requests(
                clusters,
                as_of,
            ),
            included_event_ids=tuple(item.event_id for item in visible),
            excluded_future_event_ids=tuple(
                sorted(item.event_id for item in future)
            ),
        )

    def request_supplementary_investigation(
        self,
        packet: EvidencePacket,
        *,
        reason: str,
        questions: Iterable[str],
        priority: str = "medium",
        related_cluster_ids: Iterable[str] = (),
    ) -> InvestigationRequest:
        clean_questions = tuple(
            question.strip() for question in questions if question.strip()
        )
        if not reason.strip() or not clean_questions:
            raise ValueError("reason and at least one question are required")
        related = tuple(sorted(set(related_cluster_ids)))
        payload = "|".join(
            (packet.version_id, reason, *clean_questions, *related)
        )
        return InvestigationRequest(
            request_id=(
                "investigation-"
                + hashlib.sha256(payload.encode()).hexdigest()[:12]
            ),
            reason=reason.strip(),
            priority=priority,
            requested_at=packet.as_of,
            related_cluster_ids=related,
            questions=clean_questions,
        )

    @staticmethod
    def _unique_events(events: Iterable[EvidenceEvent]) -> list[EvidenceEvent]:
        by_id: dict[str, EvidenceEvent] = {}
        for item in events:
            prior = by_id.get(item.event_id)
            if prior is not None and prior != item:
                raise ValueError(
                    f"conflicting payloads for event_id {item.event_id}"
                )
            by_id[item.event_id] = item
        return list(by_id.values())

    @staticmethod
    def _is_relevant(
        item: EvidenceEvent,
        focus: Sequence[str],
    ) -> bool:
        symbol_match = any(
            symbol in focus and score > 0
            for symbol, score in item.symbol_relevance
        )
        global_market_context = bool(
            item.macro_tags or item.geopolitical_tags
        )
        return symbol_match or global_market_context

    @staticmethod
    def _make_citations(
        events: Sequence[EvidenceEvent],
    ) -> tuple[Citation, ...]:
        return tuple(
            Citation(
                citation_id=f"C{index}",
                event_id=item.event_id,
                source_id=item.provenance.source_id,
                publisher_id=item.provenance.publisher_id,
                publisher_name=item.provenance.publisher_name,
                source_type=item.provenance.source_type,
                canonical_url=item.provenance.canonical_url,
                headline=item.headline,
                event_time=item.event_time,
                published_at=item.published_at,
                first_seen_at=item.first_seen_at,
                available_at=item.available_at,
                retrieved_at=item.retrieved_at,
                revised_at=item.revised_at,
                revision_of=item.revision_of,
                revision_number=item.revision_number,
                claim_status=item.claim_status,
                attributes=item.attributes,
                content_hash=item.content_hash,
            )
            for index, item in enumerate(events, start=1)
        )

    @staticmethod
    def _version_id(
        as_of: datetime,
        focus: tuple[str, ...],
        events: Sequence[EvidenceEvent],
    ) -> str:
        payload = {
            "as_of": as_of.isoformat(),
            "focus": focus,
            "events": tuple(
                (
                    item.event_id,
                    item.content_hash,
                    item.revision_number,
                    item.available_at.isoformat(),
                )
                for item in events
            ),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"packet-{hashlib.sha256(encoded).hexdigest()[:16]}"
