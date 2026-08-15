"""Feed the decision chain real evidence, or refuse to answer at all.

The chain treats thin evidence as a reason to hold back, so the one thing this
boundary must never do is let an unreadable source look like a quiet market.
A round where some sources answered is served, because refusing everything
over one slow publisher took every symbol offline at once — but never
silently: the sources behind the gap travel with the read itself, inside the
`EvidenceRead` each call returns, for the decision to name. A round where
nothing could be read is still refused, since an empty tuple with no evidence
behind it reads as a quiet market.

Read-only by construction: this reads public feeds over HTTPS, carries no
credential, and has no path to a broker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from information_layer import EvidenceEvent
from information_layer.factors import FactorSnapshot
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
    def read_evidence(self, symbol: str) -> "EvidenceRead": ...


class FactorSource(Protocol):
    def snapshot(self, *, symbol: str, as_of: datetime) -> FactorSnapshot: ...


class Collector(Protocol):
    def collect_with_failures(
        self,
        *,
        symbols: tuple[str, ...] = (),
    ) -> tuple[tuple[EvidenceEvent, ...], tuple[Any, ...]]: ...


@dataclass(frozen=True, slots=True)
class EvidenceRead:
    """One request's evidence sweep and the sources it could not reach.

    The gaps belong to the sweep, not to the provider: the provider is one
    shared instance behind a threading server, and gaps parked on it were
    erased (or misattributed) by whichever request swept next, so a partial
    read could be served as a complete one. A value returned with the call
    cannot be overwritten by a neighbour.
    """

    events: tuple[EvidenceEvent, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeedEvidenceProvider:
    """Reads evidence, and names which sources this read could not reach.

    A single slow publisher used to refuse the request outright, which showed
    up in the app as every symbol failing at once. The thinner answer is taken
    instead, but the sources behind the gap travel with it so the decision can
    say what it was missing rather than presenting a partial read as full.
    """

    collector: Collector

    def read_evidence(self, symbol: str) -> EvidenceRead:
        events, failures = self.collector.collect_with_failures(symbols=(symbol,))
        return EvidenceRead(
            events=tuple(events),
            gaps=tuple(
                f"{failure.source_id}（{failure.reason}）" for failure in failures
            ),
        )


@dataclass(frozen=True, slots=True)
class CompositeAnalysisProvider:
    """Candles and evidence come from different systems and fail differently."""

    bars: BarSource
    evidence: EvidenceSource
    factors: FactorSource

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        return self.bars.bars_for(symbol, interval)

    def read_evidence(self, symbol: str) -> EvidenceRead:
        return self.evidence.read_evidence(symbol)

    def factors_for(self, symbol: str, as_of: datetime) -> FactorSnapshot:
        return self.factors.snapshot(symbol=symbol, as_of=as_of)


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
