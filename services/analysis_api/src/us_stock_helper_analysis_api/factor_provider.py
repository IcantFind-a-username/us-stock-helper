"""Build the deterministic public-factor path used by live decisions.

The SEC ticker registry is large and network-backed, so it is loaded on the
first fundamentals request and cached thereafter. Failure remains one missing
factor: the macro reading and the rest of the decision still run.
"""

from __future__ import annotations

from typing import Mapping

from information_layer.factors import (
    PublicFactorProvider,
    SecXbrlFundamentalsFactor,
    TreasuryYieldCurveMacroFactor,
)
from information_layer.feeds import (
    HttpTransport,
    UrllibHttpsTransport,
    contact_email_from_environment,
    user_agent_for,
)

from .cik_registry_provider import LazySecTickerRegistry


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
