"""Strongly typed domain models."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from math import isfinite


def require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")


def require_unit_range(value: float, field_name: str) -> None:
    if not isfinite(value) or not -1.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between -1 and 1")


class Horizon(str, Enum):
    SHORT = "short"
    SWING = "swing"
    LONG = "long"


class Direction(str, Enum):
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"


class EvidenceKind(str, Enum):
    NEWS = "news"
    FILING = "filing"
    QUOTE = "quote"
    MACRO = "macro"
    GEOPOLITICAL = "geopolitical"
    INSTITUTIONAL = "institutional"
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"


class RiskPreference(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    symbol: str
    interval: str
    opened_at: datetime
    closed_at: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool = True
    revision: int = 1

    def __post_init__(self) -> None:
        for name in ("opened_at", "closed_at", "available_at"):
            require_utc(getattr(self, name), name)
        if self.opened_at >= self.closed_at:
            raise ValueError("opened_at must be before closed_at")
        if self.available_at < self.closed_at:
            raise ValueError("available_at must not precede closed_at")
        prices = (self.open, self.high, self.low, self.close)
        if not all(isfinite(value) and value > 0 for value in prices):
            raise ValueError("OHLC prices must be finite and positive")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must be the greatest OHLC value")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must be the smallest OHLC value")
        if not isfinite(self.volume) or self.volume < 0:
            raise ValueError("volume must be finite and non-negative")
        if self.revision < 1:
            raise ValueError("revision must be at least 1")
        if not self.symbol.strip() or not self.interval.strip():
            raise ValueError("symbol and interval are required")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    series_id: str
    symbol: str | None
    kind: EvidenceKind
    source_name: str
    source_url: str
    headline: str
    event_time: datetime
    published_at: datetime
    first_seen_at: datetime
    available_at: datetime
    revision: int = 1
    sentiment: float = 0.0
    confidence: float = 1.0
    claim_key: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in (
            "event_time",
            "published_at",
            "first_seen_at",
            "available_at",
        ):
            require_utc(getattr(self, name), name)
        if self.published_at > self.first_seen_at:
            raise ValueError("published_at must not be after first_seen_at")
        if self.first_seen_at > self.available_at:
            raise ValueError("first_seen_at must not be after available_at")
        if self.revision < 1:
            raise ValueError("revision must be at least 1")
        require_unit_range(self.sentiment, "sentiment")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        required = (
            self.evidence_id,
            self.series_id,
            self.source_name,
            self.source_url,
            self.headline,
        )
        if any(not value.strip() for value in required):
            raise ValueError("evidence identifiers, source, URL, and headline are required")


@dataclass(frozen=True, slots=True)
class MarketContext:
    as_of: datetime
    market_sentiment: float
    macro: float
    geopolitics: float
    institutional_flow: float
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        require_unit_range(self.market_sentiment, "market_sentiment")
        require_unit_range(self.macro, "macro")
        require_unit_range(self.geopolitics, "geopolitics")
        require_unit_range(self.institutional_flow, "institutional_flow")
