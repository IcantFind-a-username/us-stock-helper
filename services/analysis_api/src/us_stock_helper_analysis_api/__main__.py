from __future__ import annotations

from .evidence_provider import (
    CompositeAnalysisProvider,
    evidence_provider_from_environment,
)
from .factor_provider import factor_provider_from_environment
from .gateway_provider import provider_from_environment
from .http_app import AnalysisServerConfig, build_server
from .institutional_flow_provider import GatewayInstitutionalFlowProvider
from .market_brief import MarketBriefUniverse, MarketBriefUniverseConfig
from .service import AnalysisService


def main() -> None:
    config = AnalysisServerConfig.from_environment()
    # Both providers validate their configuration here rather than at the
    # first request, so a deployment that cannot reach candles or cannot
    # lawfully poll its evidence sources fails before it starts answering.
    # The same gateway instance backs both candles and the institutional-flow
    # factor: they are two reads of one loopback HTTP client, not two.
    gateway = provider_from_environment()
    provider = CompositeAnalysisProvider(
        bars=gateway,
        evidence=evidence_provider_from_environment(),
        factors=factor_provider_from_environment(),
        institutional_flow=GatewayInstitutionalFlowProvider(gateway=gateway),
    )
    service = AnalysisService(provider)
    # Validated here too, alongside every other environment-driven provider,
    # so a misconfigured breadth/sector-RS universe fails the deployment at
    # startup instead of turning into a permanent 500 on the first brief.
    market_brief_universe = MarketBriefUniverse(
        config=MarketBriefUniverseConfig.from_environment()
    )
    server = build_server(service, config, market_brief_universe=market_brief_universe)
    print(f"Read-only analysis API listening on {config.host}:{config.port}")
    # Which of the two shapes this process is in, said once where the operator
    # will see it. "Open" is the developer's laptop; anything reachable from
    # elsewhere refuses to start without the database.
    print(
        "Reads require a paired device token"
        if config.device_database is not None
        else "No credential database is configured, so reads are open to any"
        " caller this socket admits"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
