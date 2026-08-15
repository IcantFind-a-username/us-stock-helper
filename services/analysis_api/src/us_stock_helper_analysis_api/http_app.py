"""The HTTP surface for the decision chain.

Deliberately narrow: two GET paths that read, one POST that pairs a phone, an
explicit allowlist, and write methods that fail closed everywhere else. This
service reads and explains; nothing here can act, and the shape of the surface
should make that obvious to anyone auditing it.

The pairing route is the exception that proves the rule, and it is written to
be read as one. It changes state, so it is a single fixed path, a single
method, a body this file caps before it is read, and a rate limit that lives in
the credential database rather than in this process. It answers without a
credential because it is where a credential comes from; everything else demands
a device token that the operator can revoke.
"""

from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from .device_gate import MAX_PAIRING_BODY_BYTES, DeviceGate, rate_limit_identity
from .market_brief import MarketBriefService, MarketBriefUniverse
from .service import AnalysisService, InvalidRequest


PAIRING_PATH = "/v1/device-pairings"
MARKET_BRIEF_PATH = "/market-brief"
_READ_PATHS = {"/health", "/decision", MARKET_BRIEF_PATH}
# What the deployment must expose, read and write together. The edge allowlist
# is tied to this set by a test in deploy/tests.
_PATHS = _READ_PATHS | {PAIRING_PATH}
_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


@dataclass(frozen=True, slots=True)
class AnalysisApplication:
    service: AnalysisService
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)
    # Built with the inert, "nothing configured" default so every existing
    # caller that never mentions this keeps deterministic behaviour (breadth
    # and sector-RS both report "not configured" rather than reading real
    # process environment). Production wires a real one in explicitly via
    # `build_server`'s own default, which does read the environment, exactly
    # once, at startup.
    market_brief_universe: MarketBriefUniverse = field(default_factory=MarketBriefUniverse)

    def handle(
        self,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        headers = dict(_HEADERS)
        # The pairing path is deliberately absent from this allowlist. It is
        # routed before anything reaches here, and leaving it out means a
        # mistake in that routing surfaces as a 404 rather than as the decision
        # branch answering a POST.
        if path not in _READ_PATHS:
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
        if path == MARKET_BRIEF_PATH:
            # Reads through the same AnalysisService a decision uses, and
            # therefore the same shared evidence provider and collector — a
            # repeated brief request never stands up a second collector for
            # the poll coordinator to throttle separately from a decision's.
            try:
                return 200, headers, MarketBriefService(
                    self.service, self.market_brief_universe
                ).market_brief()
            except Exception:
                # Provider failures can carry credentials in their text;
                # replace the message rather than forwarding it, exactly as
                # the decision branch below does.
                return 500, headers, _error(
                    "ANALYSIS_FAILED", "The market brief could not be composed"
                )

        try:
            symbol = _one(query, "symbol")
            horizon = _one(query, "horizon")
            adviser = _flag(query, "adviser")
        except ValueError as error:
            return 400, headers, _error("INVALID_ARGUMENT", str(error))

        try:
            payload = self.service.decision(symbol, horizon, adviser=adviser)
        except InvalidRequest as error:
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
    trust_proxy: bool
    device_database: str | None
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
        trust_proxy = env.get("ANALYSIS_API_TRUST_PROXY", "").lower() in {
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

        # A deployment that still carries the retired static token is stopped
        # rather than started with it ignored. The variable used to be the only
        # thing standing between the decision chain and the internet, so an
        # operator who set it believes it is being checked; coming up anyway
        # would leave them holding a credential nothing consults while the door
        # answers to one they have never seen.
        if "ANALYSIS_API_TOKEN" in env:
            raise ValueError(
                "ANALYSIS_API_TOKEN is no longer honoured; pair the phone with"
                " device_auth and remove the variable"
            )

        database = (env.get("DEVICE_AUTH_DATABASE") or "").strip() or None
        clients = tuple(
            part.strip()
            for part in env.get("ANALYSIS_API_ALLOWED_CLIENTS", "").split(",")
            if part.strip()
        )

        if allow_lan:
            if not clients:
                raise ValueError("LAN mode requires explicit client CIDRs")
            _require_database(database, "LAN mode")
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
            clients = ("127.0.0.0/8", "::1/128")
            # Loopback stops being evidence of trust the moment a reverse proxy
            # fronts it: every public request then arrives from 127.0.0.1. The
            # cloud deployment is exactly that shape, so a proxied service must
            # demand a credential, and a database the operator configured is
            # never discarded — believing you are protected when you are not is
            # worse than knowing you are open.
            if trust_proxy:
                _require_database(database, "ANALYSIS_API_TRUST_PROXY=1")

        return cls(
            host=host,
            port=port,
            allow_lan=allow_lan,
            trust_proxy=trust_proxy,
            device_database=database,
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


def build_server(
    service: AnalysisService,
    config: AnalysisServerConfig | None = None,
    *,
    gate: DeviceGate | None = None,
    market_brief_universe: MarketBriefUniverse | None = None,
) -> ThreadingHTTPServer:
    resolved = config or AnalysisServerConfig.from_environment()
    # Defaults to the same inert "nothing configured" instance
    # `AnalysisApplication` itself defaults to — this call site never reads
    # the environment on its own. A deployment that wants breadth/sector-RS
    # sourced from real configuration passes one explicitly (see
    # `__main__.py`, which builds it from `MarketBriefUniverseConfig.
    # from_environment()` alongside every other environment-driven provider).
    application = AnalysisApplication(
        service, market_brief_universe=market_brief_universe or MarketBriefUniverse()
    )
    # Opened once, at startup, so a database this service cannot read stops the
    # deployment instead of surfacing as a refusal on the first phone's first
    # request. Every call afterwards opens its own connection, which is what
    # lets the operator's terminal revoke a device this process is already
    # serving.
    if gate is None and resolved.device_database is not None:
        gate = DeviceGate.open(resolved.device_database)

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
                gate,
                self.command,
                parsed.path,
                parse_qs(parsed.query, keep_blank_values=True),
                self.headers.get("Authorization"),
                self.client_address[0],
                _forwarded_client(self.headers),
                self._pairing_body,
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

        def _pairing_body(self) -> bytes | None:
            """The declared body, or None when it is longer than this will read.

            Read only for the pairing route and only up to the declared length.
            An absent Content-Length is an empty body rather than a stream to
            drain: nothing on this surface accepts a chunked upload, and
            reading until the client stops sending would let one socket hold a
            handler thread for as long as it liked.
            """
            declared = self.headers.get("Content-Length")
            if declared is None:
                return b""
            try:
                length = int(declared)
            except ValueError:
                return None
            if not 0 <= length <= MAX_PAIRING_BODY_BYTES:
                return None
            return self.rfile.read(length)

        def log_message(self, format: str, *args: object) -> None:
            return None

    return ThreadingHTTPServer((resolved.host, resolved.port), Handler)


def _admit(
    application: AnalysisApplication,
    config: AnalysisServerConfig,
    gate: DeviceGate | None,
    method: str,
    path: str,
    query: Mapping[str, list[str]],
    authorization: str | None,
    client_ip: str,
    forwarded_for: str | None,
    read_body: Callable[[], bytes | None],
) -> tuple[int, dict[str, str], dict[str, Any]]:
    # The network allowlist is settled before anything else, pairing included:
    # it is the boundary of who may speak to this socket at all.
    if not config.allows_client(client_ip):
        return _answer(403, {}, _error(
            "CLIENT_NOT_ALLOWED", "Client network is not allowed"
        ))

    if path == PAIRING_PATH:
        # The whole write surface, in one branch. A deployment with no
        # credential database does not serve it at all, because the throttle
        # that protects it lives in that database.
        if gate is None:
            return _answer(404, {}, _error(
                "PATH_NOT_ALLOWED", "Path is not exposed by this read-only service"
            ))
        if method != "POST":
            return _answer(405, {"Allow": "POST"}, _error(
                "METHOD_NOT_ALLOWED", "Pairing accepts only POST"
            ))
        body = read_body()
        if body is None:
            return _answer(413, {}, _error(
                "PAYLOAD_TOO_LARGE", "The pairing request body is too large to read"
            ))
        return _answer(*gate.redeem(
            body,
            client_id=rate_limit_identity(
                forwarded_for, client_ip, trust_proxy=config.trust_proxy
            ),
        ))

    # Everywhere else the credential is settled before the path is looked at,
    # so an unapproved caller cannot map the allowlist by reading 404s and
    # 405s. The pairing path above is the one thing they can confirm exists,
    # and it is published in the app anyway.
    if gate is not None:
        refused = gate.refusal(authorization)
        if refused is not None:
            return _answer(*refused)
    return application.handle(method, path, query)


def _answer(
    status: int, headers: Mapping[str, str], body: dict[str, Any]
) -> tuple[int, dict[str, str], dict[str, Any]]:
    return status, {**_HEADERS, **headers}, body


def _require_database(database: str | None, subject: str) -> None:
    if database is None:
        raise ValueError(
            f"{subject} requires DEVICE_AUTH_DATABASE so a device token can be"
            " verified and revoked"
        )


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _forwarded_client(headers: Any) -> str | None:
    """Take the identity from the last forwarded header line, not the first.

    A caller may send more than one X-Forwarded-For header; a proxy appends
    its own line rather than replacing what arrived. Reading only the first
    lets the caller choose the value the rate limiter counts, which turns the
    one guarded write path into an unlimited supply of pairing-code guesses.
    """

    lines = headers.get_all("X-Forwarded-For") or []
    for line in reversed(lines):
        if line and line.strip():
            return line
    return None


def _one(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    if len(values) != 1 or not values[0].strip():
        raise ValueError(f"{key} must appear exactly once")
    return values[0].strip()


_TRUE = {"1", "true", "yes"}
_FALSE = {"0", "false", "no", ""}


def _flag(query: Mapping[str, list[str]], key: str) -> bool | str:
    """An absent switch is off; an unreadable one is refused.

    Guessing here is not a neutral act. Read as on, a typo spends the reader's
    money; read as off, it silently withholds what they asked for. Neither is
    a defensible default, so the request is rejected instead.
    """

    values = query.get(key, [])
    if not values:
        return False
    if len(values) != 1:
        raise ValueError(f"{key} must appear at most once")
    raw = values[0].strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    if raw == "news":
        return "news"
    raise ValueError(f"{key} must be one of 1, 0, true, false, yes, no, news")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
