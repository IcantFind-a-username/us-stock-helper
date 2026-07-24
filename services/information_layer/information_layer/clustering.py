from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Sequence

from .models import ClaimStatus, EvidenceCluster, EvidenceEvent


def build_clusters(
    events: Sequence[EvidenceEvent],
    as_of: datetime,
) -> tuple[EvidenceCluster, ...]:
    groups = _cluster_events(events)
    return tuple(
        sorted(
            (_summarize_cluster(group, as_of) for group in groups),
            key=lambda cluster: cluster.cluster_id,
        )
    )


def _cluster_events(
    events: Sequence[EvidenceEvent],
) -> tuple[tuple[EvidenceEvent, ...], ...]:
    if not events:
        return ()
    parents = list(range(len(events)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    claim_owner: dict[str, int] = {}
    hash_owner: dict[str, int] = {}
    id_owner = {item.event_id: index for index, item in enumerate(events)}
    for index, item in enumerate(events):
        for key, owners in (
            (item.claim_key, claim_owner),
            (item.content_hash, hash_owner),
        ):
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index
        if item.revision_of in id_owner:
            union(index, id_owner[item.revision_of])

    groups: dict[int, list[EvidenceEvent]] = defaultdict(list)
    for index, item in enumerate(events):
        groups[find(index)].append(item)
    return tuple(
        tuple(sorted(group, key=lambda item: item.event_id))
        for group in groups.values()
    )


def _summarize_cluster(
    events: Sequence[EvidenceEvent],
    as_of: datetime,
) -> EvidenceCluster:
    superseded = {item.revision_of for item in events if item.revision_of}
    active = tuple(item for item in events if item.event_id not in superseded)
    if not active:
        active = (max(events, key=_revision_sort_key),)
    active = tuple(sorted(active, key=lambda item: item.event_id))
    representative = max(active, key=_representative_sort_key)
    action_active = tuple(
        item for item in active if item.claim_status is not ClaimStatus.RUMOR
    )
    observed_metrics = _aggregate_events(active, as_of)
    action_metrics = _aggregate_events(action_active, as_of)
    has_conflict = _has_conflict(active)
    action_has_conflict = _has_conflict(action_active)
    has_authoritative_verification = any(
        item.claim_status is ClaimStatus.VERIFIED
        and item.provenance.reliability >= 0.8
        for item in action_active
    )
    passes_confirmation_gate = (
        has_authoritative_verification
        or action_metrics[0] >= 2
    )
    actionable = bool(action_active) and passes_confirmation_gate and action_metrics[3] >= 0.65
    claim_key = min(item.claim_key for item in events)
    content_hashes = {item.content_hash for item in events}
    cluster_seed = (
        f"content:{next(iter(content_hashes))}"
        if len(content_hashes) == 1
        else f"claim:{claim_key}"
    )

    return EvidenceCluster(
        cluster_id=(
            f"cluster-{hashlib.sha256(cluster_seed.encode()).hexdigest()[:12]}"
        ),
        claim_key=claim_key,
        event_ids=tuple(item.event_id for item in events),
        active_event_ids=tuple(item.event_id for item in active),
        active_event_id=representative.event_id,
        revision_chain=_revision_lineage(events, representative),
        independent_source_count=observed_metrics[0],
        sentiment=round(observed_metrics[1], 6),
        confidence=round(observed_metrics[2], 6),
        trust_score=round(observed_metrics[3], 6),
        freshness_score=round(observed_metrics[4], 6),
        action_independent_source_count=action_metrics[0],
        action_sentiment=round(action_metrics[1], 6),
        action_confidence=round(action_metrics[2], 6),
        action_trust_score=round(action_metrics[3], 6),
        action_freshness_score=round(action_metrics[4], 6),
        has_conflict=has_conflict,
        action_has_conflict=action_has_conflict,
        contains_rumor=any(
            item.claim_status is ClaimStatus.RUMOR for item in active
        ),
        actionable=actionable,
        headline=representative.headline,
        symbol_relevance=_merge_relevance(active, "symbol_relevance"),
        entity_relevance=_merge_relevance(active, "entity_relevance"),
        geopolitical_tags=tuple(
            sorted({tag for item in active for tag in item.geopolitical_tags})
        ),
        macro_tags=tuple(
            sorted({tag for item in active for tag in item.macro_tags})
        ),
    )


def _has_conflict(events: Sequence[EvidenceEvent]) -> bool:
    return (
        any(item.sentiment > 0.15 for item in events)
        and any(item.sentiment < -0.15 for item in events)
    )


def _revision_sort_key(item: EvidenceEvent) -> tuple[int, datetime, str]:
    return (
        item.revision_number,
        item.revised_at or item.available_at,
        item.event_id,
    )


def _representative_sort_key(
    item: EvidenceEvent,
) -> tuple[int, int, float, float, datetime, str]:
    status_rank = {
        ClaimStatus.RUMOR: 0,
        ClaimStatus.REPORTED: 1,
        ClaimStatus.VERIFIED: 2,
    }
    return (
        status_rank[item.claim_status],
        item.revision_number,
        item.provenance.reliability,
        item.confidence,
        item.revised_at or item.available_at,
        item.event_id,
    )


def _revision_lineage(
    events: Sequence[EvidenceEvent],
    representative: EvidenceEvent,
) -> tuple[str, ...]:
    by_id = {item.event_id: item for item in events}
    lineage = [representative.event_id]
    current = representative
    visited = {representative.event_id}
    while current.revision_of in by_id and current.revision_of not in visited:
        parent_id = current.revision_of
        if parent_id is None:
            break
        visited.add(parent_id)
        lineage.append(parent_id)
        current = by_id[parent_id]
    return tuple(reversed(lineage))


def _independence_key(
    item: EvidenceEvent,
    owner_by_publisher: dict[str, str],
) -> str:
    origin = item.provenance.syndication_origin_id
    if origin:
        return owner_by_publisher.get(origin, origin)
    return item.provenance.ownership_group_id or item.provenance.publisher_id


def _aggregate_events(
    events: Sequence[EvidenceEvent],
    as_of: datetime,
) -> tuple[int, float, float, float, float]:
    if not events:
        return (0, 0.0, 0.0, 0.0, 0.0)
    owner_by_publisher = {
        item.provenance.publisher_id: (
            item.provenance.ownership_group_id or item.provenance.publisher_id
        )
        for item in events
    }
    identities = {
        _independence_key(item, owner_by_publisher) for item in events
    }
    weights = tuple(_event_weight(item, as_of) for item in events)
    weight_sum = sum(weights)
    sentiment = sum(
        item.sentiment * weight for item, weight in zip(events, weights)
    ) / weight_sum
    confidence = sum(
        item.confidence * weight for item, weight in zip(events, weights)
    ) / weight_sum

    reliability_by_identity: dict[str, float] = {}
    for item in events:
        identity = _independence_key(item, owner_by_publisher)
        reliability_by_identity[identity] = max(
            item.provenance.reliability,
            reliability_by_identity.get(identity, 0.0),
        )
    trust_complement = 1.0
    for reliability in reliability_by_identity.values():
        trust_complement *= 1.0 - reliability

    return (
        len(identities),
        sentiment,
        confidence,
        1.0 - trust_complement,
        max(_freshness(item, as_of) for item in events),
    )


def _freshness(item: EvidenceEvent, as_of: datetime) -> float:
    age_seconds = max(0.0, (as_of - item.available_at).total_seconds())
    return max(0.0, 1.0 - age_seconds / (72 * 60 * 60))


def _event_weight(item: EvidenceEvent, as_of: datetime) -> float:
    return (
        max(item.provenance.reliability, 0.05)
        * max(item.confidence, 0.05)
        * max(_freshness(item, as_of), 0.05)
    )


def _merge_relevance(
    events: Sequence[EvidenceEvent],
    attribute: str,
) -> tuple[tuple[str, float], ...]:
    merged: dict[str, float] = {}
    for item in events:
        for key, score in getattr(item, attribute):
            merged[key] = max(score, merged.get(key, 0.0))
    return tuple(sorted(merged.items()))
