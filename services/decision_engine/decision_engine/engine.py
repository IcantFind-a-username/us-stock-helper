from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable

from adviser_layer.council import (
    AdviserOpinion,
    CouncilRequest,
    EvidenceFact,
    aggregate_opinions,
    validate_opinion,
)
from information_layer import (
    ClaimStatus,
    EvidenceEvent,
    EvidencePacket,
    EvidencePacketBuilder,
)
from us_stock_helper_core import (
    ADVISER_SCORE_CAP,
    CalibrationStatus,
    EvidenceKind,
    EvidenceRecord,
    HardGate,
    Horizon,
    MarketContext,
    OHLCVBar,
    RiskPlan,
    RiskPreference,
    ScenarioForecast,
    ScoreResult,
    ShortBorrowSnapshot,
    build_risk_plan,
    build_scenario_forecast,
    extract_horizon_features,
    score_horizon,
)
from us_stock_helper_core.models import require_unit_range, require_utc


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    symbol: str
    horizon: Horizon
    as_of: datetime
    bars: tuple[OHLCVBar, ...]
    evidence: tuple[EvidenceEvent, ...]
    current_price: float
    current_price_available_at: datetime
    annualized_volatility: float
    volatility_available_at: datetime
    macro: float
    geopolitics: float
    institutional_flow: float
    fundamentals: float
    risk_preference: RiskPreference
    invalidation_conditions: tuple[str, ...]
    hard_gates: tuple[HardGate, ...] = ()
    short_borrow: ShortBorrowSnapshot | None = None
    adviser_focus: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        require_utc(
            self.current_price_available_at,
            "current_price_available_at",
        )
        require_utc(
            self.volatility_available_at,
            "volatility_available_at",
        )
        if (
            self.current_price_available_at > self.as_of
            or self.volatility_available_at > self.as_of
        ):
            raise ValueError(
                "price and volatility availability cannot be after as_of"
            )
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        for name in (
            "macro",
            "geopolitics",
            "institutional_flow",
            "fundamentals",
        ):
            require_unit_range(getattr(self, name), name)
        if not self.invalidation_conditions:
            raise ValueError("invalidation_conditions are required")


@dataclass(frozen=True, slots=True)
class DecisionOutput:
    evidence_packet: EvidencePacket
    baseline_score: ScoreResult
    adjusted_score: ScoreResult
    adviser_adjustment: float
    forecast: ScenarioForecast
    risk_plan: RiskPlan


class DecisionEngine:
    """Pure point-in-time composition; model calls happen outside this class."""

    def evaluate(
        self,
        inputs: DecisionInputs,
        *,
        adviser_opinions: Iterable[AdviserOpinion] = (),
    ) -> DecisionOutput:
        symbol = inputs.symbol.strip().upper()
        packet = EvidencePacketBuilder().build(
            inputs.evidence,
            as_of=inputs.as_of,
            focus_symbols=(symbol,),
        )
        records = self._analysis_records(symbol, packet, inputs.evidence)
        context = MarketContext(
            as_of=inputs.as_of,
            market_sentiment=packet.sentiment.action_score,
            macro=inputs.macro,
            geopolitics=inputs.geopolitics,
            institutional_flow=inputs.institutional_flow,
            evidence_ids=packet.sentiment.evidence_cluster_ids,
        )
        features = extract_horizon_features(
            inputs.horizon,
            inputs.bars,
            records,
            context,
            fundamentals=inputs.fundamentals,
        )
        effective_gates = list(inputs.hard_gates)
        price_max_age = {
            Horizon.SHORT: timedelta(minutes=20),
            Horizon.SWING: timedelta(days=5),
            Horizon.LONG: timedelta(days=10),
        }[inputs.horizon]
        if (
            inputs.as_of - inputs.current_price_available_at
            > price_max_age
        ):
            effective_gates.append(HardGate.STALE_DATA)
        gates = tuple(dict.fromkeys(effective_gates))
        baseline = score_horizon(features, gates)
        adjustment = self._adviser_adjustment(
            symbol,
            inputs,
            packet,
            baseline,
            adviser_opinions,
        )
        adjusted = score_horizon(
            replace(
                features,
                adviser_factor=max(-1.0, min(1.0, adjustment / ADVISER_SCORE_CAP)),
            ),
            gates,
        )
        decision_event_ids = _actionable_event_ids(
            packet,
            inputs.evidence,
        )
        forecast = build_scenario_forecast(
            adjusted,
            current_price=inputs.current_price,
            annualized_volatility=inputs.annualized_volatility,
            calibration_status=CalibrationStatus.UNCALIBRATED,
            invalidation_conditions=inputs.invalidation_conditions,
            citation_ids=tuple(
                citation.citation_id
                for citation in packet.citations
                if citation.event_id in decision_event_ids
            ),
        )
        plan = build_risk_plan(
            adjusted,
            forecast,
            preference=inputs.risk_preference,
            short_borrow=inputs.short_borrow,
        )
        return DecisionOutput(
            evidence_packet=packet,
            baseline_score=baseline,
            adjusted_score=adjusted,
            adviser_adjustment=adjustment,
            forecast=forecast,
            risk_plan=plan,
        )

    @staticmethod
    def _analysis_records(
        symbol: str,
        packet: EvidencePacket,
        events: Iterable[EvidenceEvent],
    ) -> tuple[EvidenceRecord, ...]:
        materialized = tuple(events)
        actionable_ids = _actionable_event_ids(packet, materialized)
        by_id = {item.event_id: item for item in materialized}
        records: list[EvidenceRecord] = []
        for event_id in sorted(actionable_ids):
            item = by_id[event_id]
            scoped_symbols = {
                candidate
                for candidate, relevance in item.symbol_relevance
                if relevance > 0
            }
            records.append(
                EvidenceRecord(
                    evidence_id=item.event_id,
                    series_id=(
                        f"{item.provenance.publisher_id}:{item.claim_key}"
                    ),
                    symbol=symbol if symbol in scoped_symbols else None,
                    kind=_evidence_kind(item),
                    source_name=item.provenance.publisher_name,
                    source_url=item.provenance.canonical_url,
                    headline=item.headline,
                    event_time=item.event_time,
                    published_at=item.published_at,
                    first_seen_at=item.first_seen_at,
                    available_at=item.available_at,
                    revision=item.revision_number + 1,
                    sentiment=item.sentiment,
                    sentiment_measured=item.sentiment_measured,
                    confidence=(
                        item.confidence * item.provenance.reliability
                    ),
                    claim_key=item.claim_key,
                    tags=tuple(
                        sorted(
                            {
                                *item.macro_tags,
                                *item.geopolitical_tags,
                            }
                        )
                    ),
                )
            )
        return tuple(records)

    @staticmethod
    def _adviser_adjustment(
        symbol: str,
        inputs: DecisionInputs,
        packet: EvidencePacket,
        baseline: ScoreResult,
        adviser_opinions: Iterable[AdviserOpinion],
    ) -> float:
        opinions = tuple(adviser_opinions)
        if not opinions:
            return 0.0
        actionable = _actionable_event_ids(packet, inputs.evidence)
        facts = tuple(
            EvidenceFact(
                id=item.event_id,
                text=item.summary or item.headline,
                citation_url=item.provenance.canonical_url,
                available_at=item.available_at,
                credibility=item.confidence * item.provenance.reliability,
                is_counter_evidence=item.sentiment < -0.05,
                symbols=tuple(
                    candidate
                    for candidate, relevance in item.symbol_relevance
                    if relevance > 0
                ),
            )
            for item in inputs.evidence
            if item.event_id in actionable
        )
        request = CouncilRequest(
            symbol=symbol,
            horizon=inputs.horizon.value,
            as_of=inputs.as_of,
            baseline_score=baseline.objective_score,
            baseline_direction=baseline.direction.value,
            requested_focus=inputs.adviser_focus,
            facts=facts,
        )
        validated = tuple(
            validate_opinion(opinion, request) for opinion in opinions
        )
        result = aggregate_opinions(
            baseline_score=baseline.objective_score,
            baseline_direction=baseline.direction.value,
            opinions=validated,
            council_cap=ADVISER_SCORE_CAP,
            hard_gate_passed=baseline.actionable,
        )
        return result.adjustment


def _evidence_kind(item: EvidenceEvent) -> EvidenceKind:
    source_type = item.provenance.source_type.casefold()
    if "filing" in source_type or "regulatory" in source_type:
        return EvidenceKind.FILING
    if "macro" in source_type:
        return EvidenceKind.MACRO
    if "geopolit" in source_type:
        return EvidenceKind.GEOPOLITICAL
    if "institution" in source_type:
        return EvidenceKind.INSTITUTIONAL
    return EvidenceKind.NEWS


def _actionable_event_ids(
    packet: EvidencePacket,
    events: Iterable[EvidenceEvent],
) -> set[str]:
    non_rumor_ids = {
        item.event_id
        for item in events
        if item.claim_status is not ClaimStatus.RUMOR
    }
    return {
        event_id
        for cluster in packet.clusters
        if cluster.actionable
        for event_id in cluster.active_event_ids
        if event_id in non_rumor_ids
    }
