"""Explainable three-horizon feature extraction and bounded scoring."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Sequence

from .indicators import macd, rsi
from .models import (
    Direction,
    EvidenceRecord,
    Horizon,
    MarketContext,
    OHLCVBar,
    require_unit_range,
    require_utc,
)
from .patterns import (
    detect_double_bottom,
    detect_head_and_shoulders,
    detect_ma5_pullback,
    magic_nine,
    three_bar_fractals,
)
from .temporal import select_bars_as_of, select_evidence_as_of


class HardGate(str, Enum):
    STALE_DATA = "stale_data"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LOW_LIQUIDITY = "low_liquidity"
    BORROW_UNAVAILABLE = "borrow_unavailable"
    BORROW_DATA_STALE = "borrow_data_stale"


@dataclass(frozen=True, slots=True)
class FeatureSet:
    as_of: datetime
    horizon: Horizon
    technical_trend: float
    momentum: float
    pattern: float
    market_sentiment: float
    macro: float
    geopolitics: float
    institutional_flow: float
    fundamentals: float
    adviser_factor: float
    evidence_confidence: float
    latest_market_data_at: datetime | None

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if self.latest_market_data_at is not None:
            require_utc(self.latest_market_data_at, "latest_market_data_at")
        for field_name in (
            "technical_trend",
            "momentum",
            "pattern",
            "market_sentiment",
            "macro",
            "geopolitics",
            "institutional_flow",
            "fundamentals",
            "adviser_factor",
        ):
            require_unit_range(getattr(self, field_name), field_name)
        if not 0.0 <= self.evidence_confidence <= 1.0:
            raise ValueError("evidence_confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FactorContribution:
    name: str
    raw_value: float
    weight: float
    points: float
    explanation: str


@dataclass(frozen=True, slots=True)
class ScoreResult:
    as_of: datetime
    horizon: Horizon
    objective_score: float
    direction: Direction
    actionable: bool
    contributions: tuple[FactorContribution, ...]
    blocked_by: tuple[HardGate, ...]
    method_version: str = "explainable-horizon-score-v1"


def extract_horizon_features(
    horizon: Horizon,
    bars: Sequence[OHLCVBar],
    evidence: Iterable[EvidenceRecord],
    context: MarketContext,
    *,
    adviser_factor: float = 0.0,
    fundamentals: float = 0.0,
) -> FeatureSet:
    selected_bars = select_bars_as_of(bars, context.as_of)
    series = {
        (row.symbol.upper(), row.interval)
        for row in selected_bars
    }
    if len(series) > 1:
        raise ValueError("feature extraction requires a single symbol and interval")
    symbol = next(iter(series))[0] if series else None
    selected_evidence = tuple(
        record
        for record in select_evidence_as_of(evidence, context.as_of)
        if symbol is None
        or record.symbol is None
        or record.symbol.upper() == symbol
    )
    closes = [row.close for row in selected_bars]
    lookback, return_scale = {
        Horizon.SHORT: (5, 0.03),
        Horizon.SWING: (20, 0.12),
        Horizon.LONG: (60, 0.30),
    }[horizon]
    if len(closes) > lookback:
        price_return = closes[-1] / closes[-lookback] - 1.0
        technical_trend = _clamp(price_return / return_scale)
    else:
        technical_trend = 0.0

    momentum_window = closes[-max(35, lookback + 1) :]
    rsi_value = rsi(momentum_window)
    macd_value = macd(momentum_window)
    momentum_parts: list[float] = []
    if rsi_value is not None:
        momentum_parts.append(_clamp((rsi_value - 50.0) / 50.0))
    if macd_value is not None and closes:
        momentum_parts.append(
            _clamp(macd_value.histogram / max(closes[-1] * 0.01, 0.01))
        )
    momentum = (
        sum(momentum_parts) / len(momentum_parts) if momentum_parts else 0.0
    )

    pattern_values: list[float] = []
    sequential = magic_nine(closes)
    if sequential is not None:
        pattern_values.append(
            (1.0 if sequential.direction == Direction.BULLISH else -1.0)
            * sequential.count
            / 9.0
            * 0.5
        )
    pullback = detect_ma5_pullback(selected_bars)
    double_bottom = detect_double_bottom(selected_bars)
    head_and_shoulders = detect_head_and_shoulders(selected_bars)
    if pullback is not None:
        pattern_values.append(
            0.6 if pullback.direction == Direction.BULLISH else -0.6
        )
    if double_bottom is not None:
        pattern_values.append(0.9)
    if head_and_shoulders is not None:
        pattern_values.append(-0.9)
    fractals = three_bar_fractals(selected_bars)
    if fractals:
        pattern_values.append(
            0.3 if fractals[-1].direction == Direction.BULLISH else -0.3
        )
    pattern = (
        max(pattern_values, key=abs) if pattern_values else 0.0
    )

    confidence_total = sum(record.confidence for record in selected_evidence)
    if confidence_total:
        evidence_sentiment = (
            sum(
                record.sentiment * record.confidence
                for record in selected_evidence
            )
            / confidence_total
        )
        market_sentiment = _clamp(
            context.market_sentiment * 0.6 + evidence_sentiment * 0.4
        )
        evidence_confidence = confidence_total / len(selected_evidence)
    else:
        market_sentiment = context.market_sentiment
        evidence_confidence = 0.0
    return FeatureSet(
        as_of=context.as_of,
        horizon=horizon,
        technical_trend=technical_trend,
        momentum=momentum,
        pattern=pattern,
        market_sentiment=market_sentiment,
        macro=context.macro,
        geopolitics=context.geopolitics,
        institutional_flow=context.institutional_flow,
        fundamentals=fundamentals,
        adviser_factor=adviser_factor,
        evidence_confidence=evidence_confidence,
        latest_market_data_at=max(
            (row.available_at for row in selected_bars),
            default=None,
        ),
    )


def score_horizon(
    features: FeatureSet, hard_gates: Iterable[HardGate] = ()
) -> ScoreResult:
    weights = _WEIGHTS[features.horizon]
    explanations = {
        "technical_trend": "Closed-bar return over the horizon-specific lookback.",
        "momentum": "RSI and MACD momentum calculated from closed bars only.",
        "pattern": "Confirmed close-only pattern evidence; unconfirmed shapes contribute zero.",
        "market_sentiment": "Point-in-time market mood blended with cited news evidence.",
        "macro": "As-of macroeconomic context, treated as a soft factor.",
        "geopolitics": "As-of geopolitical context, treated as a soft factor.",
        "institutional_flow": (
            "As-of institutional-flow estimate with no claim of hidden order knowledge."
        ),
        "fundamentals": "Point-in-time company financial health.",
    }
    contributions: list[FactorContribution] = []
    for name, weight in weights.items():
        raw_value = getattr(features, name)
        contributions.append(
            FactorContribution(
                name=name,
                raw_value=raw_value,
                weight=weight,
                points=raw_value * weight * 50.0,
                explanation=explanations[name],
            )
        )
    adviser_points = _clamp(features.adviser_factor) * 3.0
    contributions.append(
        FactorContribution(
            name="adviser",
            raw_value=features.adviser_factor,
            weight=0.0,
            points=adviser_points,
            explanation=(
                "Bounded style-adviser soft factor; capped at ±3 points and "
                "never bypasses a hard gate."
            ),
        )
    )
    objective_score = _clamp_score(
        50.0 + sum(item.points for item in contributions)
    )
    if objective_score >= 58.0:
        direction = Direction.BULLISH
    elif objective_score <= 42.0:
        direction = Direction.BEARISH
    else:
        direction = Direction.NEUTRAL
    gates = list(hard_gates)
    if features.evidence_confidence < 0.35:
        gates.append(HardGate.INSUFFICIENT_EVIDENCE)
    maximum_age = {
        Horizon.SHORT: timedelta(minutes=20),
        Horizon.SWING: timedelta(days=5),
        Horizon.LONG: timedelta(days=10),
    }[features.horizon]
    latest_market_data_at = features.latest_market_data_at
    if (
        latest_market_data_at is None
        or latest_market_data_at > features.as_of
        or features.as_of - latest_market_data_at > maximum_age
    ):
        gates.append(HardGate.STALE_DATA)
    unique_gates = tuple(dict.fromkeys(gates))
    return ScoreResult(
        as_of=features.as_of,
        horizon=features.horizon,
        objective_score=objective_score,
        direction=direction,
        actionable=not unique_gates,
        contributions=tuple(contributions),
        blocked_by=unique_gates,
    )


_WEIGHTS: dict[Horizon, dict[str, float]] = {
    Horizon.SHORT: {
        "technical_trend": 0.25,
        "momentum": 0.15,
        "pattern": 0.10,
        "market_sentiment": 0.20,
        "macro": 0.05,
        "geopolitics": 0.05,
        "institutional_flow": 0.15,
        "fundamentals": 0.05,
    },
    Horizon.SWING: {
        "technical_trend": 0.20,
        "momentum": 0.12,
        "pattern": 0.12,
        "market_sentiment": 0.14,
        "macro": 0.10,
        "geopolitics": 0.08,
        "institutional_flow": 0.12,
        "fundamentals": 0.12,
    },
    Horizon.LONG: {
        "technical_trend": 0.12,
        "momentum": 0.08,
        "pattern": 0.08,
        "market_sentiment": 0.10,
        "macro": 0.18,
        "geopolitics": 0.10,
        "institutional_flow": 0.08,
        "fundamentals": 0.26,
    },
}


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))
