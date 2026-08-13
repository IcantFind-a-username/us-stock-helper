from __future__ import annotations

from .evidence_provider import (
    CompositeAnalysisProvider,
    evidence_provider_from_environment,
)
from .gateway_provider import provider_from_environment
from .http_app import AnalysisServerConfig, build_server
from .service import AnalysisService


def main() -> None:
    config = AnalysisServerConfig.from_environment()
    # Both providers validate their configuration here rather than at the
    # first request, so a deployment that cannot reach candles or cannot
    # lawfully poll its evidence sources fails before it starts answering.
    provider = CompositeAnalysisProvider(
        bars=provider_from_environment(),
        evidence=evidence_provider_from_environment(),
    )
    service = AnalysisService(provider)
    server = build_server(service, config)
    print(f"Read-only analysis API listening on {config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
