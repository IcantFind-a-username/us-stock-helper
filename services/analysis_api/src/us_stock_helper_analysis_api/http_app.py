"""The HTTP surface for the decision chain.

Deliberately narrow: two GET paths, an explicit allowlist, and write methods
that fail closed. This service reads and explains; nothing here can act, and
the shape of the surface should make that obvious to anyone auditing it.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from .service import AnalysisService


_PATHS = {"/health", "/decision"}
_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


@dataclass(frozen=True, slots=True)
class AnalysisApplication:
    service: AnalysisService
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)

    def handle(
        self,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        headers = dict(_HEADERS)
        if path not in _PATHS:
            return 404, headers, _error(
                "PATH_NOT_ALLOWED", "Path is not exposed by this read-only service"
            )
        if method != "GET":
            headers["Allow"] = "GET"
            return 405, headers, _error(
                "METHOD_NOT_ALLOWED", "Only read-only GET requests are supported"
            )
        if path == "/health":
            return 200, headers, {
                "status": "ready",
                "asOf": _iso(self.clock()),
            }

        try:
            symbol = _one(query, "symbol")
            horizon = _one(query, "horizon")
        except ValueError as error:
            return 400, headers, _error("INVALID_ARGUMENT", str(error))

        try:
            payload = self.service.decision(symbol, horizon)
        except ValueError as error:
            return 400, headers, _error("INVALID_ARGUMENT", str(error))
        except Exception:
            # Provider failures can carry credentials in their text; replace
            # the message rather than forwarding it.
            return 500, headers, _error(
                "ANALYSIS_FAILED", "The decision chain could not be evaluated"
            )
        return 200, headers, payload


@dataclass(frozen=True, slots=True)
class AnalysisServerConfig:
    host: str
    port: int
    allow_lan: bool
    token: str | None
    allowed_client_networks: tuple[str, ...]

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "AnalysisServerConfig":
        env = os.environ if environment is None else environment
        allow_lan = env.get("ANALYSIS_API_ALLOW_LAN", "").lower() in {
            "1",
            "true",
            "yes",
        }
        host = env.get("ANALYSIS_API_HOST", "127.0.0.1")
        try:
            port = int(env.get("ANALYSIS_API_PORT", "8770"))
        except ValueError as exc:
            raise ValueError("ANALYSIS_API_PORT must be numeric") from exc
        if not 1 <= port <= 65535:
            raise ValueError("ANALYSIS_API_PORT must be between 1 and 65535")

        token = env.get("ANALYSIS_API_TOKEN")
        clients = tuple(
            part.strip()
            for part in env.get("ANALYSIS_API_ALLOWED_CLIENTS", "").split(",")
            if part.strip()
        )

        if allow_lan:
            if not token or len(token) < 32 or not clients:
                raise ValueError(
                    "LAN mode requires a 32+ character token and explicit client CIDRs"
                )
            for network in clients:
                if ipaddress.ip_network(network, strict=False).prefixlen == 0:
                    raise ValueError(
                        "Client CIDR allowlist is too broad; use specific networks"
                    )
        else:
            if not _is_loopback_host(host):
                raise ValueError(
                    "Non-loopback binding requires ANALYSIS_API_ALLOW_LAN=1"
                )
            # A token configured but never demanded reads as protection that
            # does not exist, so a loopback deployment drops it outright.
            clients = ("127.0.0.0/8", "::1/128")
            token = None

        return cls(
            host=host,
            port=port,
            allow_lan=allow_lan,
            token=token,
            allowed_client_networks=clients,
        )

    def allows_client(self, client_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(
            address in ipaddress.ip_network(network, strict=False)
            for network in self.allowed_client_networks
        )

    def authorizes(self, authorization: str | None) -> bool:
        if not self.allow_lan:
            return True
        prefix = "Bearer "
        supplied = (
            authorization[len(prefix) :]
            if authorization and authorization.startswith(prefix)
            else ""
        )
        expected = self.token or ""
        # Compare bytes: hmac.compare_digest raises TypeError on non-ASCII
        # strings, which would crash the handler thread before authentication
        # and print a stack trace with absolute paths in it.
        return bool(supplied) and hmac.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        )


def build_server(
    service: AnalysisService,
    config: AnalysisServerConfig | None = None,
) -> ThreadingHTTPServer:
    resolved = config or AnalysisServerConfig.from_environment()
    application = AnalysisApplication(service)

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
            status, headers, body = _admit(
                application,
                resolved,
                self.command,
                parsed.path,
                parse_qs(parsed.query, keep_blank_values=True),
                self.headers.get("Authorization"),
                self.client_address[0],
            )
            encoded = json.dumps(
                body,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return None

    return ThreadingHTTPServer((resolved.host, resolved.port), Handler)


def _admit(
    application: AnalysisApplication,
    config: AnalysisServerConfig,
    method: str,
    path: str,
    query: Mapping[str, list[str]],
    authorization: str | None,
    client_ip: str,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    # Address and token are settled before the path is even looked at, so an
    # unapproved caller cannot map the allowlist by reading 404s and 405s.
    if not config.allows_client(client_ip):
        return 403, dict(_HEADERS), _error(
            "CLIENT_NOT_ALLOWED", "Client network is not allowed"
        )
    if not config.authorizes(authorization):
        return 401, dict(_HEADERS), _error(
            "AUTH_REQUIRED", "Analysis API authorization is required"
        )
    return application.handle(method, path, query)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _one(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    if len(values) != 1 or not values[0].strip():
        raise ValueError(f"{key} must appear exactly once")
    return values[0].strip()


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
