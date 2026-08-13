"""Feed the decision chain real evidence, or refuse to answer at all.

The chain treats thin evidence as a reason to hold back, so the one thing this
boundary must never do is let an unreadable source look like a quiet market.
Every failure the collector reports travels outward as an exception; only a
round of polling where every source answered can produce an empty tuple.

Read-only by construction: this reads public feeds over HTTPS, carries no
credential, and has no path to a broker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Protocol

from information_layer import EvidenceEvent
from information_layer.feeds import (
    DEFAULT_LOOKBACK_SECONDS,
    DEFAULT_RETENTION_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    EvidenceCollector,
    UrllibHttpsTransport,
    build_adapters,
    contact_email_from_environment,
)
from us_stock_helper_core import OHLCVBar


class BarSource(Protocol):
    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]: ...


class EvidenceSource(Protocol):
    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]: ...


class Collector(Protocol):
    def collect(
        self,
        *,
        symbols: tuple[str, ...] = (),
    ) -> tuple[EvidenceEvent, ...]: ...


@dataclass(frozen=True, slots=True)
class FeedEvidenceProvider:
    collector: Collector

    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
        return self.collector.collect(symbols=(symbol,))


@dataclass(frozen=True, slots=True)
class CompositeAnalysisProvider:
    """Candles and evidence come from different systems and fail differently."""

    bars: BarSource
    evidence: EvidenceSource

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        return self.bars.bars_for(symbol, interval)

    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
        return self.evidence.evidence_for(symbol)


def evidence_provider_from_environment(
    environment: Mapping[str, str] | None = None,
) -> FeedEvidenceProvider:
    env = os.environ if environment is None else environment
    # Raises when no contact address is configured. EDGAR ships in the
    # registry and serves only clients it can reach, so an anonymous
    # deployment has no evidence path at all and must say so at startup
    # rather than report an empty market at request time.
    contact_email = contact_email_from_environment(env)
    lookback = _seconds(
        env,
        "ANALYSIS_API_EVIDENCE_LOOKBACK_SECONDS",
        DEFAULT_LOOKBACK_SECONDS,
    )
    stale_after = _seconds(
        env,
        "ANALYSIS_API_EVIDENCE_STALE_AFTER_SECONDS",
        DEFAULT_STALE_AFTER_SECONDS,
    )
    retention = _seconds(
        env,
        "ANALYSIS_API_EVIDENCE_RETENTION_SECONDS",
        DEFAULT_RETENTION_SECONDS,
    )
    return FeedEvidenceProvider(
        EvidenceCollector(
            build_adapters(
                transport=UrllibHttpsTransport(),
                contact_email=contact_email,
            ),
            lookback_seconds=lookback,
            stale_after_seconds=stale_after,
            retention_seconds=retention,
        )
    )


def _seconds(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number of seconds") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive number of seconds")
    return value
