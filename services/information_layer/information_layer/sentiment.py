from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Sequence

from .models import (
    EvidenceCluster,
    InvestigationRequest,
    MarketSentiment,
)


def assess_sentiment(
    clusters: Sequence[EvidenceCluster],
) -> MarketSentiment:
    evidence_ids = tuple(
        cluster.cluster_id
        for cluster in clusters
        if cluster.sentiment > 0.05 or cluster.has_conflict
    )
    counter_ids = tuple(
        cluster.cluster_id
        for cluster in clusters
        if cluster.sentiment < -0.05 or cluster.has_conflict
    )
    actionable = tuple(cluster for cluster in clusters if cluster.actionable)
    action_score = _weighted_score(actionable, action_only=True)
    observed_score = _weighted_score(clusters, action_only=False)
    uncertainty: list[str] = []
    if any(cluster.has_conflict for cluster in clusters):
        uncertainty.append("来源冲突")
    if any(cluster.contains_rumor for cluster in clusters):
        uncertainty.append("含未证实传闻")
    if any(
        cluster.action_independent_source_count < 2 for cluster in actionable
    ):
        uncertainty.append("独立来源不足")

    confidence = (
        sum(
            cluster.action_confidence
            * cluster.action_trust_score
            * (0.6 if cluster.action_has_conflict else 1.0)
            for cluster in actionable
        )
        / len(actionable)
        if actionable
        else 0.0
    )
    conclusion, signal = _conclusion(action_score)
    if not actionable and any(cluster.contains_rumor for cluster in clusters):
        signal = "observe_only"

    return MarketSentiment(
        conclusion=conclusion,
        action_score=round(action_score, 6),
        observed_score=round(observed_score, 6),
        confidence=round(max(0.0, min(confidence, 1.0)), 6),
        decision_signal=signal,
        evidence_cluster_ids=evidence_ids,
        counterevidence_cluster_ids=counter_ids,
        uncertainty=tuple(uncertainty),
    )


def make_investigation_requests(
    clusters: Sequence[EvidenceCluster],
    as_of: datetime,
) -> tuple[InvestigationRequest, ...]:
    requests: list[InvestigationRequest] = []
    for cluster in clusters:
        if cluster.contains_rumor:
            requests.append(
                _request(
                    cluster,
                    as_of,
                    reason="传闻仅供观察，需权威来源确认",
                    priority="high",
                    questions=("查找原始声明", "核验公司/监管/交易所披露"),
                )
            )
        elif cluster.has_conflict:
            requests.append(
                _request(
                    cluster,
                    as_of,
                    reason="来源冲突，需补充独立调查",
                    priority="high",
                    questions=("比较原始材料", "解释口径与时间差异"),
                )
            )
        elif (
            cluster.action_independent_source_count > 0
            and not cluster.actionable
        ):
            requests.append(
                _request(
                    cluster,
                    as_of,
                    reason="独立来源不足",
                    priority="medium",
                    questions=("寻找第二个独立来源",),
                )
            )
    return tuple(requests)


def _weighted_score(
    clusters: Sequence[EvidenceCluster],
    *,
    action_only: bool,
) -> float:
    weighted: list[tuple[float, float]] = []
    for cluster in clusters:
        if action_only:
            values = (
                cluster.action_sentiment,
                cluster.action_confidence,
                cluster.action_trust_score,
                cluster.action_freshness_score,
                cluster.action_has_conflict,
            )
        else:
            values = (
                cluster.sentiment,
                cluster.confidence,
                cluster.trust_score,
                cluster.freshness_score,
                cluster.has_conflict,
            )
        sentiment, confidence, trust, freshness, has_conflict = values
        weight = (
            confidence
            * trust
            * freshness
            * (0.5 if has_conflict else 1.0)
        )
        weighted.append((sentiment, weight))
    denominator = sum(weight for _, weight in weighted)
    if denominator == 0:
        return 0.0
    return sum(score * weight for score, weight in weighted) / denominator


def _conclusion(score: float) -> tuple[str, str]:
    if score >= 0.2:
        return "偏多", "long_bias"
    if score <= -0.2:
        return "偏空", "short_bias"
    return "中性", "neutral"


def _request(
    cluster: EvidenceCluster,
    as_of: datetime,
    *,
    reason: str,
    priority: str,
    questions: tuple[str, ...],
) -> InvestigationRequest:
    payload = f"{cluster.cluster_id}|{reason}|{as_of.isoformat()}"
    return InvestigationRequest(
        request_id=(
            f"investigation-{hashlib.sha256(payload.encode()).hexdigest()[:12]}"
        ),
        reason=reason,
        priority=priority,
        requested_at=as_of,
        related_cluster_ids=(cluster.cluster_id,),
        questions=questions,
    )
