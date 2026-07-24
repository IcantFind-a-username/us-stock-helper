from __future__ import annotations

from .http_gateway import GatewayServerConfig, build_server
from .opend_adapter import MoomooOpenDProvider
from .service import MarketGatewayService


def main() -> None:
    config = GatewayServerConfig.from_environment()
    provider = MoomooOpenDProvider()
    service = MarketGatewayService(provider)
    server = build_server(service, config)
    print(f"Read-only moomoo gateway listening on {config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
