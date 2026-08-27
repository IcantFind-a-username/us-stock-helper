from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class SessionHealth:
    state: str
    checked_at: datetime
    source: str
    error_code: Any | None = None


@dataclass(frozen=True)
class ProviderBatch:
    source: str
    received_at: datetime
    items: list[dict[str, Any]]


class QuoteProvider(Protocol):
    def health(self) -> SessionHealth:
        ...

    def watchlist(self, group: str | None = None) -> ProviderBatch:
        ...

    def quotes(self, codes: list[str]) -> ProviderBatch:
        ...

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        ...

    def capital_flow(self, code: str) -> ProviderBatch:
        ...

    def capital_distribution(self, code: str) -> ProviderBatch:
        ...

    def institutional_holdings(self, code: str) -> ProviderBatch:
        ...


class OptionsFlowProvider(Protocol):
    """Narrow protocol for read-only per-contract options data.

    Deliberately separate from QuoteProvider: not every provider needs to
    implement options, and this must never grow trade-context methods.
    """

    def options_flow(self, code: str) -> ProviderBatch:
        ...
