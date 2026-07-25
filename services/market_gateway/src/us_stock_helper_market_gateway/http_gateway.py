from __future__ import annotations

import hmac
import ipaddress
import json
import os
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from .errors import ErrorCode, GatewayError
from .service import MarketGatewayService
from .time_utils import iso_z, require_utc, utc_now


_PATHS = {
    "/health",
    "/watchlist",
    "/quotes",
    "/candles",
    "/stock-snapshot",
    "/capital-flow",
    "/capital-distribution",
    "/institutional-holdings",
}
_STATUS_BY_ERROR = {
    ErrorCode.INVALID_ARGUMENT.value: 400,
    ErrorCode.AUTH_REQUIRED.value: 401,
    ErrorCode.CLIENT_NOT_ALLOWED.value: 403,
    ErrorCode.ORIGIN_NOT_ALLOWED.value: 403,
    ErrorCode.PERMISSION_DENIED.value: 403,
    ErrorCode.PATH_NOT_ALLOWED.value: 404,
    ErrorCode.METHOD_NOT_ALLOWED.value: 405,
    ErrorCode.QUOTA_EXCEEDED.value: 429,
    ErrorCode.SDK_UNAVAILABLE.value: 503,
    ErrorCode.OPEND_OFFLINE.value: 503,
    ErrorCode.LOGIN_REQUIRED.value: 503,
    ErrorCode.STALE_DATA.value: 503,
    ErrorCode.MALFORMED_PROVIDER_DATA.value: 502,
    ErrorCode.PROVIDER_ERROR.value: 502,
    ErrorCode.UNSUPPORTED_CAPABILITY.value: 501,
}


@dataclass(frozen=True)
class GatewayServerConfig:
    host: str
    port: int
    allow_lan: bool
    token: str | None
    allowed_client_networks: tuple[str, ...]
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "GatewayServerConfig":
        env = os.environ if environment is None else environment
        allow_lan = env.get("MOOMOO_GATEWAY_ALLOW_LAN", "").lower() in {
            "1",
            "true",
            "yes",
        }
        host = env.get("MOOMOO_GATEWAY_HOST", "127.0.0.1")
        try:
            port = int(env.get("MOOMOO_GATEWAY_PORT", "8765"))
        except ValueError as exc:
            raise ValueError("MOOMOO_GATEWAY_PORT must be numeric") from exc
        if not 1 <= port <= 65535:
            raise ValueError("MOOMOO_GATEWAY_PORT must be between 1 and 65535")

        token = env.get("MOOMOO_GATEWAY_TOKEN")
        clients = tuple(
            part.strip()
            for part in env.get("MOOMOO_GATEWAY_ALLOWED_CLIENTS", "").split(",")
            if part.strip()
        )
        origins = tuple(
            part.strip()
            for part in env.get("MOOMOO_GATEWAY_ALLOWED_ORIGINS", "").split(",")
            if part.strip()
        )
        loopback_host = _is_loopback_host(host)

        if allow_lan:
            if not token or len(token) < 16 or not clients:
                raise ValueError(
                    "LAN mode requires a 16+ character token and explicit client CIDRs"
                )
            for network in clients:
                ipaddress.ip_network(network, strict=False)
        else:
            if not loopback_host:
                raise ValueError(
                    "Non-loopback binding requires MOOMOO_GATEWAY_ALLOW_LAN=1"
                )
            clients = ("127.0.0.0/8", "::1/128")
            token = None

        return cls(
            host=host,
            port=port,
            allow_lan=allow_lan,
            token=token,
            allowed_client_networks=clients,
            allowed_origins=origins,
        )


class GatewayApplication:
    def __init__(
        self,
        service: MarketGatewayService,
        config: GatewayServerConfig,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._service = service
        self._config = config
        self._clock = clock
        self._networks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in config.allowed_client_networks
        )

    def handle(
        self,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
        headers: Mapping[str, str],
        client_ip: str,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        response_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        origin = normalized_headers.get("origin")
        try:
            if path not in _PATHS:
                raise GatewayError(
                    ErrorCode.PATH_NOT_ALLOWED,
                    "Path is not exposed by this read-only gateway",
                )
            if method not in {"GET", "OPTIONS"}:
                response_headers["Allow"] = "GET, OPTIONS"
                raise GatewayError(
                    ErrorCode.METHOD_NOT_ALLOWED,
                    "Only read-only GET requests are supported",
                )
            if not self._client_allowed(client_ip):
                raise GatewayError(
                    ErrorCode.CLIENT_NOT_ALLOWED,
                    "Client network is not allowed",
                )
            if origin:
                if not self._origin_allowed(origin):
                    raise GatewayError(
                        ErrorCode.ORIGIN_NOT_ALLOWED,
                        "Browser origin is not allowed",
                    )
                response_headers["Access-Control-Allow-Origin"] = origin
                response_headers["Vary"] = "Origin"
            if method == "OPTIONS":
                response_headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
                response_headers["Access-Control-Allow-Headers"] = (
                    "Accept, Authorization"
                )
                return 204, response_headers, {}
            if self._config.allow_lan:
                self._require_token(normalized_headers.get("authorization"))

            payload = self._route(path, query)
            status = _STATUS_BY_ERROR.get(
                payload.get("error", {}).get("code"),
                200,
            )
            return status, response_headers, payload
        except GatewayError as error:
            return (
                _STATUS_BY_ERROR[error.code.value],
                response_headers,
                self._error_payload(error),
            )

    def _route(
        self,
        path: str,
        query: Mapping[str, list[str]],
    ) -> dict[str, Any]:
        if path == "/health":
            return self._service.health()
        if path == "/watchlist":
            return self._service.watchlist(self._one(query, "group", required=False))
        if path == "/quotes":
            raw = self._one(query, "symbols")
            assert raw is not None
            symbols = [value.strip() for value in raw.split(",") if value.strip()]
            if not symbols:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "symbols query parameter is required",
                )
            return self._service.quotes(symbols)
        if path in {
            "/capital-flow",
            "/capital-distribution",
            "/institutional-holdings",
        }:
            symbol = self._one(query, "symbol")
            assert symbol is not None
            if path == "/capital-flow":
                return self._service.capital_flow(symbol)
            if path == "/capital-distribution":
                return self._service.capital_distribution(symbol)
            return self._service.institutional_holdings(symbol)
        symbol = self._one(query, "symbol")
        assert symbol is not None
        interval = self._one(query, "timeframe", required=False) or self._one(
            query,
            "interval",
            required=False,
        ) or "5m"
        count_raw = self._one(query, "count", required=False) or "200"
        try:
            count = int(count_raw)
        except ValueError as exc:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                "count must be numeric",
            ) from exc
        if not 1 <= count <= 1000:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                "count must be between 1 and 1000",
            )
        if interval not in {"1m", "5m", "15m", "30m", "60m", "day", "week"}:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                "Unsupported candle interval",
            )
        if path == "/stock-snapshot":
            return self._service.stock_snapshot(symbol, interval, count)
        return self._service.candles(symbol, interval, count)

    def _one(
        self,
        query: Mapping[str, list[str]],
        key: str,
        *,
        required: bool = True,
    ) -> str | None:
        values = query.get(key, [])
        if len(values) > 1:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                f"{key} must appear only once",
            )
        value = values[0].strip() if values else ""
        if required and not value:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                f"{key} query parameter is required",
            )
        return value or None

    def _client_allowed(self, client_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(address in network for network in self._networks)

    def _origin_allowed(self, origin: str) -> bool:
        if self._config.allowed_origins:
            return origin in self._config.allowed_origins
        if self._config.allow_lan:
            return False
        parsed = urlparse(origin)
        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and _is_loopback_host(parsed.hostname)
        )

    def _require_token(self, authorization: str | None) -> None:
        prefix = "Bearer "
        supplied = (
            authorization[len(prefix) :]
            if authorization and authorization.startswith(prefix)
            else ""
        )
        expected = self._config.token or ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise GatewayError(
                ErrorCode.AUTH_REQUIRED,
                "Gateway authorization is required",
            )

    def _error_payload(self, error: GatewayError) -> dict[str, Any]:
        now = require_utc(self._clock(), "clock")
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": error.session,
            "asOf": iso_z(now),
            "availableAt": iso_z(now),
            "items": [],
            "error": error.public_dict(),
        }


def build_server(
    service: MarketGatewayService,
    config: GatewayServerConfig | None = None,
) -> ThreadingHTTPServer:
    resolved = config or GatewayServerConfig.from_environment()
    application = GatewayApplication(service, resolved)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._dispatch()

        def do_OPTIONS(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def do_PUT(self) -> None:
            self._dispatch()

        def do_PATCH(self) -> None:
            self._dispatch()

        def do_DELETE(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            parsed = urlparse(self.path)
            status, headers, body = application.handle(
                self.command,
                parsed.path,
                parse_qs(parsed.query, keep_blank_values=True),
                dict(self.headers.items()),
                self.client_address[0],
            )
            encoded = _encode_response_body(self.command, status, body)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if encoded:
                self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return None

    return ThreadingHTTPServer((resolved.host, resolved.port), Handler)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _encode_response_body(
    method: str,
    status: int,
    body: dict[str, Any],
) -> bytes:
    if method == "OPTIONS" or status == 204:
        return b""
    return json.dumps(
        body,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
