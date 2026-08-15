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
from .patterns import magic_nine
from .patterns_shapes import PatternShapeKind, PatternShapeStatus, detect_pattern_shapes
from .temporal import select_bars_as_of, select_evidence_as_of


# The single authority for how far the adviser panel may move a score. Every
# layer that caps, normalizes or displays an adviser adjustment must read this
# rather than repeating the number, or the layers drift apart silently.
ADVISER_SCORE_CAP = 3.0

# The smallest window any pattern detector can read: three-bar fractals need
# three completed bars (magic nine needs five closes, everything else more).
# Below this no detector ran at all, and "the detectors found nothing" would
# be a claim about a reading nobody took.
_SMALLEST_PATTERN_WINDOW = 3

# Score magnitude per confirmed shape kind (sign follows the signal's own
# direction) -- mirrors patterns_shapes.py's own confirmed/invalidated
# distinction: only a confirmed shape votes, matching the "只计入收盘确认的
# 形态证据" explanation below.
_PATTERN_SHAPE_MAGNITUDE: dict[PatternShapeKind, float] = {
    PatternShapeKind.FRACTAL_TOP: 0.3,
    PatternShapeKind.FRACTAL_BOTTOM: 0.3,
    PatternShapeKind.DOUBLE_TOP: 0.9,
    PatternShapeKind.DOUBLE_BOTTOM: 0.9,
    PatternShapeKind.HEAD_SHOULDERS_TOP: 0.9,
    PatternShapeKind.HEAD_SHOULDERS_BOTTOM: 0.9,
    PatternShapeKind.MA5_PULLBACK: 0.6,
}

# How long a completed bar remains "the current picture" before a decision
# must refuse to act on it. Budgeted against the interval the bars were
# actually sampled on, not the horizon asking about them: a horizon is a
# claim about the future, not about how often the exchange publishes a new
# candle. An intraday bar goes stale within a small multiple of its own
# length; a daily bar is only replaced once a session, and the previous
# session can be a weekend or a short holiday run away, so its budget has to
# span that gap rather than the bar's own 24-hour length.
_INTRADAY_BAR_DURATIONS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "60m": timedelta(hours=1),
}
_INTRADAY_STALE_MULTIPLE = 3
# Covers a holiday-extended weekend (Friday close to Tuesday reopen) with
# margin, without disguising a feed that has genuinely stopped reporting.
_DAILY_STALE_BUDGET = timedelta(days=5)
# A weekly bar is only replaced once a week, so its age legitimately climbs
# toward -- but stays under -- 7 days for most of the cycle; sharing the
# 5-day daily budget stale-gated every request made in the back half of the
# week. Budgeted past a full 7-day cycle with margin for a holiday-shifted
# close, while staying well short of a feed that has genuinely stopped.
_WEEKLY_STALE_BUDGET = timedelta(days=9)
# No interval could be attributed to the bars at all: fail toward the
# tightest budget rather than assume a cadence nobody confirmed.
_UNKNOWN_INTERVAL_STALE_BUDGET = timedelta(minutes=20)


def data_freshness_budget(interval: str | None) -> timedelta:
    """How old the freshest bar of ``interval`` may be before it is stale."""
    duration = _INTRADAY_BAR_DURATIONS.get(interval) if interval else None
    if duration is not None:
        return duration * _INTRADAY_STALE_MULTIPLE
    if interval == "week":
        return _WEEKLY_STALE_BUDGET
    if interval == "day":
        return _DAILY_STALE_BUDGET
    return _UNKNOWN_INTERVAL_STALE_BUDGET


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
    # None means no source could supply this factor. Distinct from 0.0, which
    # is a measured neutral: filling absence with zero states a judgement
    # nobody made and drags the score toward the middle in proportion to how
    # blind the system is.
    technical_trend: float | None
    momentum: float | None
    pattern: float | None
    market_sentiment: float | None
    macro: float | None
    geopolitics: float | None
    institutional_flow: float | None
    fundamentals: float | None
    adviser_factor: float
    evidence_confidence: float
    latest_market_data_at: datetime | None
    # The interval the bars behind latest_market_data_at were sampled on
    # ("day", "5m", ...). The staleness gate budgets freshness against this,
    # not against the horizon: a horizon is a question about the future, not
    # a claim about how often the exchange publishes a new candle. None means
    # no bars could be attributed to a single known interval.
    data_interval: str | None = None

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
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_unit_range(value, field_name)
        require_unit_range(self.adviser_factor, "adviser_factor")
        if not 0.0 <= self.evidence_confidence <= 1.0:
            raise ValueError("evidence_confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FactorContribution:
    name: str
    # None when no source could supply the factor, as opposed to a measured 0.
    raw_value: float | None
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
    unavailable_factors: tuple[str, ...] = ()
    factor_coverage: float = 1.0
    method_version: str = "explainable-horizon-score-v1"


def extract_horizon_features(
    horizon: Horizon,
    bars: Sequence[OHLCVBar],
    evidence: Iterable[EvidenceRecord],
    context: MarketContext,
    *,
    adviser_factor: float = 0.0,
    fundamentals: float | None = None,
) -> FeatureSet:
    selected_bars = select_bars_as_of(bars, context.as_of)
    series = {
        (row.symbol.upper(), row.interval)
        for row in selected_bars
    }
    if len(series) > 1:
        raise ValueError("feature extraction requires a single symbol and interval")
    symbol = next(iter(series))[0] if series else None
    data_interval = next(iter(series))[1] if series else None
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
        # Too short to measure a return over this horizon. Zero would claim a
        # flat market where there is simply no observation.
        technical_trend = None

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
        sum(momentum_parts) / len(momentum_parts) if momentum_parts else None
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
    # detect_pattern_shapes runs 顶分型/底分型/W底/双头/头肩顶/头肩底/回踩五日线
    # over the same completed bars the chart-hint card serves; only a
    # confirmed shape votes here, so the score and the served hint can never
    # disagree about what "confirmed" means.
    for detection in detect_pattern_shapes(selected_bars):
        for signal in detection.signals:
            if signal.status is not PatternShapeStatus.CONFIRMED:
                continue
            sign = 1.0 if signal.direction == Direction.BULLISH else -1.0
            pattern_values.append(sign * _PATTERN_SHAPE_MAGNITUDE[signal.kind])
    if len(selected_bars) < _SMALLEST_PATTERN_WINDOW:
        # Too few bars for any detector to have looked. Claiming a measured
        # zero here would report "looked and found nothing" for a window that
        # was never looked at.
        pattern = None
    else:
        # No confirmed pattern is a genuine reading of zero: the detectors ran
        # and found nothing. It stays 0.0, unlike a factor nothing could read.
        pattern = max(pattern_values, key=abs) if pattern_values else 0.0

    confidence_total = sum(record.confidence for record in selected_evidence)
    # Only sources something actually read contribute an opinion. Unread ones
    # still count as corroborating evidence below; averaging them in as 0.0
    # would let silence pull a real signal toward the middle.
    scored_evidence = tuple(
        record for record in selected_evidence if record.sentiment_measured
    )
    scored_confidence = sum(record.confidence for record in scored_evidence)
    if scored_confidence:
        evidence_sentiment = (
            sum(
                record.sentiment * record.confidence
                for record in scored_evidence
            )
            / scored_confidence
        )
        market_sentiment = (
            _clamp(context.market_sentiment * 0.6 + evidence_sentiment * 0.4)
            if context.market_sentiment is not None
            # No market-wide reading, but the cited evidence is a reading.
            else _clamp(evidence_sentiment)
        )
    else:
        market_sentiment = context.market_sentiment
    evidence_confidence = (
        confidence_total / len(selected_evidence) if selected_evidence else 0.0
    )
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
        data_interval=data_interval,
    )


def score_horizon(
    features: FeatureSet, hard_gates: Iterable[HardGate] = ()
) -> ScoreResult:
    weights = _WEIGHTS[features.horizon]
    # Investor-readable Chinese, exact-pinned by tests/test_scoring.py. These
    # strings ride the wire verbatim as `contributions[].explanation` — the
    # analysis_api layer does no translation of its own — so this is the one
    # place they are written, not a template a downstream layer fills in.
    explanations = {
        "technical_trend": "按周期对应的回看窗口，用已收盘K线计算涨跌幅。",
        "momentum": "RSI 与 MACD 动量，只用已收盘K线计算。",
        "pattern": "只计入收盘确认的形态证据；未确认的形态贡献为零。",
        "market_sentiment": "按当时可见的市场情绪，结合引用的新闻证据。",
        "macro": "按当时可见的宏观经济背景，作为软因子处理。",
        "geopolitics": "按当时可见的地缘政治背景，作为软因子处理。",
        "institutional_flow": (
            "融合日内大单资金净流入占比的估算代理与机构持仓变动趋势"
            "（按披露日期计入），不声称掌握隐藏订单信息。"
        ),
        "fundamentals": "按当时可见的公司财务状况。",
    }
    contributions: list[FactorContribution] = []
    unavailable = tuple(
        sorted(name for name in weights if getattr(features, name) is None)
    )
    available_weight = sum(
        weight for name, weight in weights.items() if getattr(features, name) is not None
    )
    total_weight = sum(weights.values())
    # Redistribute the missing weight across what is left rather than letting
    # absent factors vote zero. The score then means "given what we could see",
    # and factor_coverage says how much that was.
    scale = total_weight / available_weight if available_weight else 0.0
    for name, weight in weights.items():
        raw_value = getattr(features, name)
        if raw_value is None:
            contributions.append(
                FactorContribution(
                    name=name,
                    raw_value=None,
                    weight=0.0,
                    points=0.0,
                    explanation=f"{explanations[name]}本次快照不可用。",
                )
            )
            continue
        contributions.append(
            FactorContribution(
                name=name,
                raw_value=raw_value,
                weight=weight * scale,
                points=raw_value * weight * scale * 50.0,
                explanation=explanations[name],
            )
        )
    adviser_points = _clamp(features.adviser_factor) * ADVISER_SCORE_CAP
    contributions.append(
        FactorContribution(
            name="adviser",
            raw_value=features.adviser_factor,
            weight=0.0,
            points=adviser_points,
            explanation=(
                f"顾问软因子设有上限：最多影响 ±{ADVISER_SCORE_CAP:g} 分，"
                "且不能绕过任何硬性拦截。"
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
    maximum_age = data_freshness_budget(features.data_interval)
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
        # A score built on nothing is not a weak opinion, it is no opinion.
        actionable=not unique_gates and available_weight > 0.0,
        contributions=tuple(contributions),
        blocked_by=unique_gates,
        unavailable_factors=unavailable,
        factor_coverage=(
            available_weight / total_weight if total_weight else 0.0
        ),
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
