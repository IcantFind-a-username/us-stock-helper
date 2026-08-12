from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    REPORTED = "reported"
    RUMOR = "rumor"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _normalize_relevance(
    values: Iterable[tuple[str, float]],
    *,
    uppercase_key: bool,
) -> tuple[tuple[str, float], ...]:
    normalized: list[tuple[str, float]] = []
    for key, score in values:
        clean_key = key.strip().upper() if uppercase_key else key.strip()
        if not clean_key:
            raise ValueError("relevance key must not be empty")
        if not 0.0 <= score <= 1.0:
            raise ValueError("relevance score must be between 0 and 1")
        normalized.append((clean_key, float(score)))
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_id: str
    publisher_id: str
    publisher_name: str
    canonical_url: str
    source_type: str
    reliability: float
    ownership_group_id: str | None = None
    syndication_origin_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.publisher_id.strip():
            raise ValueError("source_id and publisher_id are required")
        if not self.canonical_url.startswith(("https://", "http://")):
            raise ValueError("canonical_url must be an HTTP(S) URL")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    event_id: str
    claim_key: str
    headline: str
    summary: str
    provenance: SourceProvenance
    event_time: datetime
    published_at: datetime
    first_seen_at: datetime
    available_at: datetime
    retrieved_at: datetime
    revised_at: datetime | None
    revision_of: str | None
    revision_number: int
    claim_status: ClaimStatus
    sentiment: float
    # False means no scorer could read this text. Kept apart from a measured
    # 0.0 because the aggregator must not average in an opinion nobody formed.
    sentiment_measured: bool
    confidence: float
    symbol_relevance: tuple[tuple[str, float], ...]
    entity_relevance: tuple[tuple[str, float], ...]
    geopolitical_tags: tuple[str, ...]
    macro_tags: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    content_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.claim_status, ClaimStatus):
            raise TypeError("claim_status must be a ClaimStatus")
        for field_name, value in (
            ("event_time", self.event_time),
            ("published_at", self.published_at),
            ("first_seen_at", self.first_seen_at),
            ("available_at", self.available_at),
            ("retrieved_at", self.retrieved_at),
        ):
            _require_aware(value, field_name)
        if self.revised_at is not None:
            _require_aware(self.revised_at, "revised_at")
        if not (
            self.published_at
            <= self.first_seen_at
            <= self.available_at
            <= self.retrieved_at
        ):
            raise ValueError(
                "evidence time order must be "
                "published_at <= first_seen_at <= available_at <= retrieved_at"
            )
        if self.revised_at is not None and self.revised_at > self.available_at:
            raise ValueError(
                "revised_at must be no later than available_at and retrieved_at"
            )
        if not self.event_id or not self.claim_key or not self.headline:
            raise ValueError("event_id, claim_key, and headline are required")
        if not -1.0 <= self.sentiment <= 1.0:
            raise ValueError("sentiment must be between -1 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.revision_number < 0:
            raise ValueError("revision_number cannot be negative")
        if self.revision_of is None and self.revision_number:
            raise ValueError("revision_number requires revision_of")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_hash):
            raise ValueError("content_hash must be a SHA-256 hex digest")

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        claim_key: str,
        headline: str,
        summary: str,
        provenance: SourceProvenance,
        event_time: datetime,
        published_at: datetime,
        first_seen_at: datetime,
        available_at: datetime,
        retrieved_at: datetime,
        claim_status: ClaimStatus,
        sentiment: float,
        confidence: float,
        sentiment_measured: bool = True,
        revised_at: datetime | None = None,
        revision_of: str | None = None,
        revision_number: int = 0,
        symbol_relevance: Iterable[tuple[str, float]] = (),
        entity_relevance: Iterable[tuple[str, float]] = (),
        geopolitical_tags: Iterable[str] = (),
        macro_tags: Iterable[str] = (),
        attributes: Iterable[tuple[str, str]] = (),
    ) -> "EvidenceEvent":
        for field_name, value in (
            ("event_time", event_time),
            ("published_at", published_at),
            ("first_seen_at", first_seen_at),
            ("available_at", available_at),
            ("retrieved_at", retrieved_at),
        ):
            _require_aware(value, field_name)
        if revised_at is not None:
            _require_aware(revised_at, "revised_at")
        if not event_id.strip() or not claim_key.strip():
            raise ValueError("event_id and claim_key are required")
        if not headline.strip():
            raise ValueError("headline is required")
        if not -1.0 <= sentiment <= 1.0:
            raise ValueError("sentiment must be between -1 and 1")
        if not sentiment_measured and sentiment != 0.0:
            raise ValueError(
                "sentiment_measured=False requires a sentiment of exactly 0"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(claim_status, ClaimStatus):
            raise TypeError("claim_status must be a ClaimStatus")
        if revision_number < 0:
            raise ValueError("revision_number cannot be negative")
        if revision_of is None and revision_number:
            raise ValueError("revision_number requires revision_of")

        digest_input = "\n".join(
            (
                _normalize_text(headline),
                _normalize_text(summary),
            )
        )
        content_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        return cls(
            event_id=event_id.strip(),
            claim_key=_normalize_text(claim_key),
            headline=re.sub(r"\s+", " ", headline).strip(),
            summary=re.sub(r"\s+", " ", summary).strip(),
            provenance=provenance,
            event_time=event_time,
            published_at=published_at,
            first_seen_at=first_seen_at,
            available_at=available_at,
            retrieved_at=retrieved_at,
            revised_at=revised_at,
            revision_of=revision_of,
            revision_number=revision_number,
            claim_status=claim_status,
            sentiment=float(sentiment),
            sentiment_measured=bool(sentiment_measured),
            confidence=float(confidence),
            symbol_relevance=_normalize_relevance(
                symbol_relevance,
                uppercase_key=True,
            ),
            entity_relevance=_normalize_relevance(
                entity_relevance,
                uppercase_key=False,
            ),
            geopolitical_tags=tuple(sorted(set(geopolitical_tags))),
            macro_tags=tuple(sorted(set(macro_tags))),
            attributes=tuple(
                sorted(
                    (key.strip(), value.strip())
                    for key, value in attributes
                    if key.strip() and value.strip()
                )
            ),
            content_hash=content_hash,
        )

    def is_visible_at(self, as_of: datetime) -> bool:
        _require_aware(as_of, "as_of")
        temporal_fields = [
            self.first_seen_at,
            self.available_at,
            self.retrieved_at,
        ]
        if self.revised_at is not None:
            temporal_fields.append(self.revised_at)
        return all(value <= as_of for value in temporal_fields)


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    event_id: str
    source_id: str
    publisher_id: str
    publisher_name: str
    source_type: str
    canonical_url: str
    headline: str
    event_time: datetime
    published_at: datetime
    first_seen_at: datetime
    available_at: datetime
    retrieved_at: datetime
    revised_at: datetime | None
    revision_of: str | None
    revision_number: int
    claim_status: ClaimStatus
    attributes: tuple[tuple[str, str], ...]
    content_hash: str


@dataclass(frozen=True, slots=True)
class EvidenceCluster:
    cluster_id: str
    claim_key: str
    event_ids: tuple[str, ...]
    active_event_ids: tuple[str, ...]
    active_event_id: str
    revision_chain: tuple[str, ...]
    independent_source_count: int
    sentiment: float
    # False when nothing in this cluster could be read. Without it the packet
    # layer treats the resulting 0.0 as a full-weight neutral vote.
    sentiment_measured: bool
    confidence: float
    trust_score: float
    freshness_score: float
    action_independent_source_count: int
    action_sentiment: float
    action_confidence: float
    action_trust_score: float
    action_freshness_score: float
    has_conflict: bool
    action_has_conflict: bool
    contains_rumor: bool
    actionable: bool
    headline: str
    symbol_relevance: tuple[tuple[str, float], ...]
    entity_relevance: tuple[tuple[str, float], ...]
    geopolitical_tags: tuple[str, ...]
    macro_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketSentiment:
    conclusion: str
    action_score: float
    observed_score: float
    confidence: float
    decision_signal: str
    evidence_cluster_ids: tuple[str, ...]
    counterevidence_cluster_ids: tuple[str, ...]
    uncertainty: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvestigationRequest:
    request_id: str
    reason: str
    priority: str
    requested_at: datetime
    related_cluster_ids: tuple[str, ...]
    questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    version_id: str
    as_of: datetime
    focus_symbols: tuple[str, ...]
    clusters: tuple[EvidenceCluster, ...]
    citations: tuple[Citation, ...]
    sentiment: MarketSentiment
    actionable_cluster_ids: tuple[str, ...]
    observational_cluster_ids: tuple[str, ...]
    investigation_requests: tuple[InvestigationRequest, ...]
    included_event_ids: tuple[str, ...]
    excluded_future_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompactRender:
    text: str
    estimated_tokens: int
    truncated: bool
