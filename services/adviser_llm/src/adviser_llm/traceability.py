"""Resolve model output back to frozen evidence, or refuse it outright."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .errors import FabricatedFactError, TraceabilityError
from .evidence import EvidencePacket
from .frameworks import framework_by_id
from .schemas import (
    Citation,
    Conclusion,
    CouncilBrief,
    FrameworkOpinion,
    NewsInterpretation,
)


_WHITESPACE = re.compile(r"\s+")
# Two digits or more: a lone digit is usually a count of items in the packet
# rather than an asserted measurement, and flagging it produces noise instead
# of catching fabrication.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_UPPERCASE_TOKEN = re.compile(r"\b[A-Z]{2,5}\b")


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


@dataclass(frozen=True, slots=True)
class ResolvedCitation:
    """A citation with the source link taken from our own record."""

    evidence_id: str
    quote: str
    url: str
    publisher: str
    available_at: datetime
    received_at: datetime
    is_counter_evidence: bool


@dataclass(frozen=True, slots=True)
class TracedConclusion:
    statement: str
    confidence: str
    citations: tuple[ResolvedCitation, ...]
    counter_evidence: tuple[ResolvedCitation, ...]


@dataclass(frozen=True, slots=True)
class TracedOpinion:
    framework_id: str
    display_name: str
    stance: str
    conclusions: tuple[TracedConclusion, ...]
    blind_spot_note: str


@dataclass(frozen=True, slots=True)
class TracedBrief:
    summary: str
    opinions: tuple[TracedOpinion, ...]


@dataclass(frozen=True, slots=True)
class TracedInterpretation:
    headline_summary: str
    cross_source_reading: str
    investment_impact: tuple[TracedConclusion, ...]
    unknowns: tuple[str, ...]


def _resolve_citation(
    citation: Citation, packet: EvidencePacket
) -> ResolvedCitation:
    item = packet.item(citation.evidence_id)
    if item is None:
        raise TraceabilityError(
            f"结论引用了证据包之外的条目: {citation.evidence_id}"
        )
    if _normalize(citation.quote) not in _normalize(item.text):
        raise FabricatedFactError(
            f"引文在证据 {citation.evidence_id} 的原文中不存在"
        )
    return ResolvedCitation(
        evidence_id=item.id,
        quote=citation.quote,
        url=item.url,
        publisher=item.publisher,
        available_at=item.available_at,
        received_at=item.received_at,
        is_counter_evidence=item.is_counter_evidence,
    )


def _grounded_tokens(packet: EvidencePacket) -> tuple[set[str], set[str]]:
    corpus = " ".join(
        [packet.symbol]
        + [
            f"{item.headline} {item.body} {item.publisher} {' '.join(item.symbols)}"
            for item in packet.items
        ]
    )
    numbers = {token for token in _NUMBER.findall(corpus) if len(token) >= 2}
    uppercase = set(_UPPERCASE_TOKEN.findall(corpus))
    return numbers, uppercase


def _reject_facts_outside_the_packet(
    statement: str, packet: EvidencePacket
) -> None:
    allowed_numbers, allowed_uppercase = _grounded_tokens(packet)
    for token in _NUMBER.findall(statement):
        if len(token) >= 2 and token not in allowed_numbers:
            raise FabricatedFactError(
                f"结论引入了证据中不存在的数字: {token}"
            )
    for token in _UPPERCASE_TOKEN.findall(statement):
        if token not in allowed_uppercase:
            raise FabricatedFactError(
                f"结论引入了证据中不存在的标的或缩写: {token}"
            )


def trace_conclusion(
    conclusion: Conclusion, packet: EvidencePacket
) -> TracedConclusion:
    if not conclusion.citations:
        raise TraceabilityError("结论没有任何引用，不予呈现")
    _reject_facts_outside_the_packet(conclusion.statement, packet)
    citations = tuple(
        _resolve_citation(citation, packet) for citation in conclusion.citations
    )
    counter = tuple(
        _resolve_citation(citation, packet)
        for citation in conclusion.counter_evidence
    )
    return TracedConclusion(
        statement=conclusion.statement,
        confidence=conclusion.confidence,
        citations=citations,
        counter_evidence=counter,
    )


def _trace_opinion(
    opinion: FrameworkOpinion, packet: EvidencePacket
) -> TracedOpinion:
    try:
        framework = framework_by_id(opinion.framework_id)
    except KeyError as exc:
        raise TraceabilityError(
            f"未知分析框架: {opinion.framework_id}"
        ) from exc
    return TracedOpinion(
        framework_id=framework.id,
        display_name=framework.display_name,
        stance=opinion.stance,
        conclusions=tuple(
            trace_conclusion(item, packet) for item in opinion.conclusions
        ),
        blind_spot_note=opinion.blind_spot_note,
    )


def trace_brief(brief: CouncilBrief, packet: EvidencePacket) -> TracedBrief:
    # Any single failure rejects the whole brief. Showing the sourced half
    # beside a dropped claim would leave the reader unable to tell that
    # something was removed.
    return TracedBrief(
        summary=brief.summary,
        opinions=tuple(
            _trace_opinion(opinion, packet) for opinion in brief.opinions
        ),
    )


def trace_interpretation(
    interpretation: NewsInterpretation, packet: EvidencePacket
) -> TracedInterpretation:
    return TracedInterpretation(
        headline_summary=interpretation.headline_summary,
        cross_source_reading=interpretation.cross_source_reading,
        investment_impact=tuple(
            trace_conclusion(item, packet)
            for item in interpretation.investment_impact
        ),
        unknowns=tuple(interpretation.unknowns),
    )
