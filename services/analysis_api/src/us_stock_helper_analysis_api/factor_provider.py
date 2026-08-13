"""Build the deterministic public-factor path used by live decisions.

The SEC ticker registry is large and network-backed, so it is loaded on the
first fundamentals request and cached thereafter. Failure remains one missing
factor: the macro reading and the rest of the decision still run.
"""

from __future__ import annotations

import threading
from typing import Mapping

from information_layer import CikTickerRegistry
from information_layer.factors import (
    PublicFactorProvider,
    SecXbrlFundamentalsFactor,
    TreasuryYieldCurveMacroFactor,
)
from information_layer.feeds import (
    HttpRequest,
    HttpTransport,
    UrllibHttpsTransport,
    contact_email_from_environment,
    user_agent_for,
)


_TICKER_REGISTRY_URL = "https://www.sec.gov/files/company_tickers.json"


class LazySecTickerRegistry:
    def __init__(self, transport: HttpTransport, user_agent: str) -> None:
        self._transport = transport
        self._user_agent = user_agent
        self._registry: CikTickerRegistry | None = None
        self._lock = threading.Lock()

    def cik_for(self, ticker: str) -> str | None:
        return self._get().cik_for(ticker)

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


def factor_provider_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    transport: HttpTransport | None = None,
) -> PublicFactorProvider:
    contact = contact_email_from_environment(environment)
    user_agent = user_agent_for(contact)
    resolved_transport = transport or UrllibHttpsTransport()
    return PublicFactorProvider(
        fundamentals=SecXbrlFundamentalsFactor(
            transport=resolved_transport,
            user_agent=user_agent,
        ),
        macro=TreasuryYieldCurveMacroFactor(
            transport=resolved_transport,
            user_agent=user_agent,
        ),
        cik_registry=LazySecTickerRegistry(resolved_transport, user_agent),
    )
