"""Lazily fetch SEC's company-ticker registry, once, for whichever caller asks first.

The registry is large (~10 MB) and network-backed. Two independent providers
need it — the fundamentals factor (a ticker -> CIK lookup) and the SEC evidence
feeds (a CIK -> ticker lookup, used to attribute an 8-K or Form 4 to a symbol).
Fetching it eagerly at construction time would mean a slow SEC response keeps
the whole process from starting even when the request that actually needs it
never arrives; fetching it once per caller would mean two network round trips
for one file that never changes within a process's lifetime. This wrapper
behaves like a CikTickerRegistry from the moment it is constructed: the fetch
happens lazily on first use and is cached for the life of the process.
"""

from __future__ import annotations

import threading

from information_layer import CikTickerRegistry
from information_layer.feeds import HttpRequest, HttpTransport


_TICKER_REGISTRY_URL = "https://www.sec.gov/files/company_tickers.json"


class LazySecTickerRegistry:
    """A CikTickerRegistry that fetches and caches itself on first use."""

    def __init__(self, transport: HttpTransport, user_agent: str) -> None:
        self._transport = transport
        self._user_agent = user_agent
        self._registry: CikTickerRegistry | None = None
        self._lock = threading.Lock()

    def cik_for(self, ticker: str) -> str | None:
        return self._get().cik_for(ticker)

    def tickers_for(self, cik: str | int) -> tuple[str, ...]:
        return self._get().tickers_for(cik)

    def symbol_relevance_for(self, cik: str | int) -> tuple[tuple[str, float], ...]:
        return self._get().symbol_relevance_for(cik)

    def resolve_first(
        self, candidates: tuple[str, ...]
    ) -> tuple[str | None, tuple[tuple[str, float], ...]]:
        return self._get().resolve_first(candidates)

    def _get(self) -> CikTickerRegistry:
        if self._registry is not None:
            return self._registry
        with self._lock:
            if self._registry is not None:
                return self._registry
            response = self._transport.request(
                HttpRequest(
                    url=_TICKER_REGISTRY_URL,
                    allowed_hosts=("www.sec.gov",),
                    headers=(
                        ("User-Agent", self._user_agent),
                        ("Accept", "application/json"),
                    ),
                    timeout_seconds=30.0,
                    max_response_bytes=8_000_000,
                )
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"SEC company ticker registry answered {response.status_code}"
                )
            loaded = CikTickerRegistry.from_sec_payload(response.body)
            self._registry = loaded
            return loaded
