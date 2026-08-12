from __future__ import annotations

from .gateway_provider import provider_from_environment
from .http_app import AnalysisServerConfig, build_server
from .service import AnalysisService


def main() -> None:
    config = AnalysisServerConfig.from_environment()
    provider = provider_from_environment()
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
