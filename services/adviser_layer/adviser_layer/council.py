from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence
from urllib.parse import urlparse

from us_stock_helper_core import ADVISER_SCORE_CAP

from .registry import ADVISER_PROFILES, AdviserProfile


Direction = Literal["bullish", "neutral", "bearish"]
Horizon = Literal["short", "swing", "long"]


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


@dataclass(frozen=True)
class EvidenceFact:
    id: str
    text: str
    citation_url: str
    available_at: datetime
    credibility: float
    is_counter_evidence: bool
    symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.available_at, "available_at")
        if not self.id or not self.text or not self.citation_url:
            raise ValueError("evidence fact fields cannot be empty")
        parsed_url = urlparse(self.citation_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError("citation_url must be a credential-free HTTP(S) URL")
        if not 0 <= self.credibility <= 1:
            raise ValueError("credibility must be within 0..1")
        normalized_symbols = tuple(
            sorted({symbol.strip().upper() for symbol in self.symbols})
        )
        if any(not symbol for symbol in normalized_symbols):
            raise ValueError("fact symbols cannot be empty")
        object.__setattr__(self, "symbols", normalized_symbols)


@dataclass(frozen=True)
class CouncilRequest:
    symbol: str
    horizon: Horizon
    as_of: datetime
    baseline_score: float
    baseline_direction: Direction
    requested_focus: tuple[str, ...]
    facts: tuple[EvidenceFact, ...]

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if self.horizon not in {"short", "swing", "long"}:
            raise ValueError("horizon must be short, swing, or long")
        if self.baseline_direction not in {"bullish", "neutral", "bearish"}:
            raise ValueError(
                "baseline_direction must be bullish, neutral, or bearish"
            )
        if not 0 <= self.baseline_score <= 100:
            raise ValueError("baseline_score must be within 0..100")


@dataclass(frozen=True)
class AdviserOpinion:
    adviser_id: str
    direction: Direction
    confidence: float
    score_adjustment: float
    thesis: str
    counterargument: str
    citation_ids: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    abstained: bool


@dataclass(frozen=True)
class CouncilResult:
    baseline_score: float
    adjusted_score: float
    adjustment: float
    objective_direction: Direction
    action_eligible: bool
    active_opinions: int
    abstentions: int


class InvalidAdviserOutput(ValueError):
    """Raised when an untrusted model response violates the council contract."""


def select_advisers(
    request: CouncilRequest,
    *,
    maximum: int = 4,
) -> tuple[AdviserProfile, ...]:
    if maximum < 1:
        raise ValueError("maximum must be positive")
    requested = set(request.requested_focus)

    def relevance(profile: AdviserProfile) -> tuple[int, int, str]:
        focus_matches = len(requested.intersection(profile.focus))
        horizon_match = int(request.horizon in profile.suitable_horizons)
        return (-focus_matches, -horizon_match, profile.id)

    ranked = sorted(ADVISER_PROFILES, key=relevance)
    selected = [
        profile
        for profile in ranked
        if requested.intersection(profile.focus)
        or request.horizon in profile.suitable_horizons
    ]
    return tuple(selected[:maximum])


def build_compact_packet(
    request: CouncilRequest,
    *,
    max_characters: int = 4_000,
) -> str:
    if max_characters < 400:
        raise ValueError("max_characters is too small for an auditable packet")
    visible = sorted(
        _visible_facts(request).values(),
        key=lambda fact: (fact.available_at, fact.id),
    )
    if not visible:
        raise ValueError("no point-in-time evidence available")

    facts = [
        {
            "id": item.id,
            "text": item.text[:280],
            "url": item.citation_url,
            "available_at": item.available_at.isoformat(),
            "credibility": round(item.credibility, 3),
            "counter": item.is_counter_evidence,
            "symbols": item.symbols,
        }
        for item in visible
    ]
    payload = {
        "schema": "adviser-evidence-packet/v1",
        "symbol": request.symbol.upper(),
        "horizon": request.horizon,
        "as_of": request.as_of.isoformat(),
        "baseline": {
            "score": request.baseline_score,
            "direction": request.baseline_direction,
        },
        "instruction": (
            "只依据本包；列出反证和缺失证据；证据不足必须弃权；"
            "不得输出下单动作、数量或保证性收益。"
        ),
        "facts": facts,
    }

    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    while len(encoded) > max_characters and facts:
        longest = max(facts, key=lambda item: len(str(item["text"])))
        text = str(longest["text"])
        if len(text) > 72:
            longest["text"] = text[: max(72, len(text) // 2)]
        elif len(facts) > 1:
            facts.pop()
        else:
            break
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(encoded) > max_characters:
        raise ValueError("evidence packet cannot fit the requested token budget")
    return encoded


def validate_opinion(
    opinion: AdviserOpinion,
    request: CouncilRequest,
    *,
    per_adviser_cap: float = ADVISER_SCORE_CAP,
    minimum_reliable_facts: int = 1,
    minimum_credibility: float = 0.5,
) -> AdviserOpinion:
    _validate_opinion_shape(opinion, per_adviser_cap=per_adviser_cap)
    visible = _visible_facts(request)
    if not set(opinion.citation_ids).issubset(visible):
        raise InvalidAdviserOutput("opinion cites evidence outside the frozen packet")
    reliable_count = sum(
        item.credibility >= minimum_credibility for item in visible.values()
    )
    if reliable_count < minimum_reliable_facts and not opinion.abstained:
        raise InvalidAdviserOutput("insufficient reliable evidence requires abstention")
    if not opinion.abstained and not opinion.citation_ids:
        raise InvalidAdviserOutput("a non-abstaining opinion must cite evidence")
    if opinion.abstained and (
        opinion.direction != "neutral" or opinion.score_adjustment != 0
    ):
        raise InvalidAdviserOutput("abstention must be neutral with zero adjustment")
    if not opinion.thesis.strip() or not opinion.counterargument.strip():
        raise InvalidAdviserOutput("thesis and counterargument are required")
    return opinion


def aggregate_opinions(
    *,
    baseline_score: float,
    baseline_direction: Direction,
    opinions: Sequence[AdviserOpinion],
    council_cap: float = ADVISER_SCORE_CAP,
    per_adviser_cap: float = ADVISER_SCORE_CAP,
    hard_gate_passed: bool,
) -> CouncilResult:
    if not 0 <= baseline_score <= 100:
        raise ValueError("baseline_score must be within 0..100")
    if council_cap < 0:
        raise ValueError("council_cap cannot be negative")
    if baseline_direction not in {"bullish", "neutral", "bearish"}:
        raise ValueError(
            "baseline_direction must be bullish, neutral, or bearish"
        )
    for opinion in opinions:
        _validate_opinion_shape(
            opinion,
            per_adviser_cap=per_adviser_cap,
        )
    abstentions = sum(opinion.abstained for opinion in opinions)
    active = [opinion for opinion in opinions if not opinion.abstained]
    raw_adjustment = sum(
        opinion.score_adjustment * opinion.confidence for opinion in active
    )
    adjustment = (
        max(-council_cap, min(council_cap, raw_adjustment))
        if hard_gate_passed
        else 0.0
    )
    adjusted_score = max(0.0, min(100.0, baseline_score + adjustment))
    return CouncilResult(
        baseline_score=baseline_score,
        adjusted_score=adjusted_score,
        adjustment=adjustment,
        objective_direction=baseline_direction,
        action_eligible=hard_gate_passed,
        active_opinions=len(active),
        abstentions=abstentions,
    )


def _visible_facts(request: CouncilRequest) -> dict[str, EvidenceFact]:
    symbol = request.symbol.strip().upper()
    visible: dict[str, EvidenceFact] = {}
    for item in request.facts:
        if item.available_at > request.as_of:
            continue
        if item.symbols and symbol not in item.symbols:
            continue
        prior = visible.get(item.id)
        if prior is not None and prior != item:
            raise ValueError(f"conflicting evidence fact id: {item.id}")
        visible[item.id] = item
    return visible


def _validate_opinion_shape(
    opinion: AdviserOpinion,
    *,
    per_adviser_cap: float,
) -> None:
    known_profiles = {profile.id for profile in ADVISER_PROFILES}
    if opinion.adviser_id not in known_profiles:
        raise InvalidAdviserOutput("unknown adviser")
    if opinion.direction not in {"bullish", "neutral", "bearish"}:
        raise InvalidAdviserOutput("unknown adviser direction")
    if not math.isfinite(opinion.confidence) or not 0 <= opinion.confidence <= 1:
        raise InvalidAdviserOutput("confidence must be within 0..1")
    if (
        not math.isfinite(opinion.score_adjustment)
        or abs(opinion.score_adjustment) > per_adviser_cap
    ):
        raise InvalidAdviserOutput("score adjustment exceeds the soft-factor cap")
    if not opinion.thesis.strip() or not opinion.counterargument.strip():
        raise InvalidAdviserOutput("thesis and counterargument are required")
