from __future__ import annotations

import json
import threading
import unittest
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from typing import Any, Iterator
from urllib.error import HTTPError

from us_stock_helper_analysis_api.http_app import (
    PAIRING_PATH,
    AnalysisApplication,
    AnalysisServerConfig,
    build_server,
)

from test_analysis_service import AS_OF, Provider, service


def app() -> AnalysisApplication:
    return AnalysisApplication(service(Provider()), clock=lambda: AS_OF)


class HttpBoundaryTests(unittest.TestCase):
    def test_a_decision_is_served_over_get(self) -> None:
        status, headers, body = app().handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["symbol"], "NVDA")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_write_methods_fail_closed(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, _, body = app().handle(
                    method, "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
                )

                self.assertEqual(status, 405)
                self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_paths_outside_the_allowlist_are_refused(self) -> None:
        for path in ("/orders", "/decision/../secrets", "/"):
            with self.subTest(path=path):
                status, _, body = app().handle("GET", path, {})

                self.assertEqual(status, 404)
                self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_the_read_application_alone_never_serves_the_pairing_path(self) -> None:
        """The application's own allowlist is the reads and nothing else.

        Routing settles the pairing path before this object sees it, so this
        is defence in depth rather than a live behaviour — which is exactly why
        it needs its own test. Widening the allowlist here would be invisible
        until the day a routing mistake let a POST reach the decision branch.
        """
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, _, body = app().handle(method, PAIRING_PATH, {})

                self.assertEqual(status, 404)
                self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_a_missing_or_repeated_parameter_is_a_client_error(self) -> None:
        for query in (
            {},
            {"symbol": ["NVDA"]},
            {"symbol": ["NVDA", "TSLA"], "horizon": ["short"]},
        ):
            with self.subTest(query=query):
                status, _, body = app().handle("GET", "/decision", query)

                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

    def test_an_unknown_horizon_is_a_client_error_not_a_crash(self) -> None:
        status, _, body = app().handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["forever"]}
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

    def test_an_internal_failure_does_not_leak_its_details(self) -> None:
        class Exploding:
            def bars_for(self, symbol: str, interval: str) -> tuple[()]:
                raise RuntimeError("account=123 token=secret")

            def evidence_for(self, symbol: str) -> tuple[()]:
                return ()

        from us_stock_helper_analysis_api.service import AnalysisService

        failing = AnalysisApplication(
            AnalysisService(Exploding(), clock=lambda: AS_OF),  # type: ignore[arg-type]
            clock=lambda: AS_OF,
        )

        status, _, body = failing.handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 500)
        self.assertNotIn("secret", repr(body))
        self.assertNotIn("account", repr(body))

    def test_a_data_failure_is_not_reported_as_a_client_argument_error(
        self,
    ) -> None:
        """JSONDecodeError is a ValueError.

        Catching ValueError ahead of the sanitizing branch meant an upstream
        HTML error page, or an internal invariant failure, came back as HTTP
        400 with the internal text attached — blaming the caller for a server
        problem and defeating the sanitizer for the commonest exception type.
        """

        import json as json_module

        class Broken:
            def bars_for(self, symbol: str, interval: str) -> tuple[()]:
                raise json_module.JSONDecodeError("Expecting delimiter", "{}", 1)

            def evidence_for(self, symbol: str) -> tuple[()]:
                return ()

        from us_stock_helper_analysis_api.service import AnalysisService

        broken = AnalysisApplication(
            AnalysisService(Broken(), clock=lambda: AS_OF),  # type: ignore[arg-type]
            clock=lambda: AS_OF,
        )

        status, _, body = broken.handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 500)
        self.assertNotIn("delimiter", repr(body))

    def test_an_unknown_horizon_is_still_a_client_error(self) -> None:
        status, _, body = app().handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["forever"]}
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

    def test_the_health_path_reports_readiness_without_data(self) -> None:
        status, _, body = app().handle("GET", "/health", {})

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ready")
        self.assertTrue(body["asOf"].endswith("Z"))


# The credential itself is device_auth's now, so everything about who may call
# this service — pairing, verification, revocation, the throttle — is asserted
# in test_device_pairing.py. What remains here is the binding: where the socket
# is, and which networks may reach it at all.
LAN_DATABASE = "/var/lib/us-stock-helper/device-auth.sqlite3"


class AnalysisServerConfigTests(unittest.TestCase):
    def test_default_configuration_is_loopback_only(self) -> None:
        config = AnalysisServerConfig.from_environment({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertFalse(config.allow_lan)
        self.assertIsNone(config.device_database)
        self.assertEqual(config.allowed_client_networks, ("127.0.0.0/8", "::1/128"))

    def test_non_loopback_binding_requires_explicit_opt_in(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisServerConfig.from_environment(
                {"ANALYSIS_API_HOST": "0.0.0.0"}
            )

        complete = {
            "ANALYSIS_API_ALLOW_LAN": "1",
            "ANALYSIS_API_HOST": "0.0.0.0",
            "DEVICE_AUTH_DATABASE": LAN_DATABASE,
            "ANALYSIS_API_ALLOWED_CLIENTS": "192.168.50.0/24",
        }
        config = AnalysisServerConfig.from_environment(complete)
        self.assertTrue(config.allow_lan)
        self.assertEqual(config.allowed_client_networks, ("192.168.50.0/24",))

    def test_lan_mode_rejects_an_empty_or_world_wide_client_list(self) -> None:
        base = {
            "ANALYSIS_API_ALLOW_LAN": "1",
            "ANALYSIS_API_HOST": "0.0.0.0",
            "DEVICE_AUTH_DATABASE": LAN_DATABASE,
            "ANALYSIS_API_ALLOWED_CLIENTS": "192.168.50.0/24",
        }
        with self.assertRaisesRegex(ValueError, "CIDR"):
            AnalysisServerConfig.from_environment(
                {**base, "ANALYSIS_API_ALLOWED_CLIENTS": ""}
            )
        for cidr in ("0.0.0.0/0", "::/0"):
            with self.subTest(cidr=cidr):
                with self.assertRaisesRegex(ValueError, "broad"):
                    AnalysisServerConfig.from_environment(
                        {**base, "ANALYSIS_API_ALLOWED_CLIENTS": cidr}
                    )

    def test_the_port_must_be_a_number_inside_the_valid_range(self) -> None:
        for port in ("http", "0", "65536", "-1"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    AnalysisServerConfig.from_environment(
                        {"ANALYSIS_API_PORT": port}
                    )

    def test_only_the_configured_client_networks_are_admitted(self) -> None:
        loopback = AnalysisServerConfig.from_environment({})

        self.assertTrue(loopback.allows_client("127.0.0.1"))
        self.assertTrue(loopback.allows_client("::1"))
        self.assertFalse(loopback.allows_client("192.168.50.8"))
        self.assertFalse(loopback.allows_client("not-an-address"))

        lan = AnalysisServerConfig.from_environment(
            {
                "ANALYSIS_API_ALLOW_LAN": "1",
                "ANALYSIS_API_HOST": "0.0.0.0",
                "DEVICE_AUTH_DATABASE": LAN_DATABASE,
                "ANALYSIS_API_ALLOWED_CLIENTS": "192.168.50.0/24",
            }
        )
        self.assertTrue(lan.allows_client("192.168.50.8"))
        self.assertFalse(lan.allows_client("192.168.51.8"))


def loopback_config(**overrides: Any) -> AnalysisServerConfig:
    defaults: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 0,
        "allow_lan": False,
        "trust_proxy": False,
        "device_database": None,
        "allowed_client_networks": ("127.0.0.0/8", "::1/128"),
    }
    return AnalysisServerConfig(**{**defaults, **overrides})


@contextmanager
def running(config: AnalysisServerConfig) -> Iterator[str]:
    server = build_server(service(Provider()), config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def call(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    request = urllib.request.Request(url, method=method)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return (
                response.status,
                dict(response.headers.items()),
                json.loads(response.read()),
            )
    except HTTPError as error:
        return error.code, dict(error.headers.items()), json.loads(error.read())


class ServerBindingTests(unittest.TestCase):
    def test_the_server_binds_loopback_and_serves_a_decision(self) -> None:
        with running(loopback_config()) as base:
            status, headers, body = call(f"{base}/health")
            self.assertEqual(status, 200)
            self.assertEqual(body["status"], "ready")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

            status, _, body = call(f"{base}/decision?symbol=NVDA&horizon=short")
            self.assertEqual(status, 200)
            self.assertEqual(body["symbol"], "NVDA")

    def test_the_server_is_threading_and_stays_silent(self) -> None:
        server = build_server(service(Provider()), loopback_config())
        try:
            self.assertIsInstance(server, ThreadingHTTPServer)
            self.assertEqual(server.server_address[0], "127.0.0.1")
            handler = server.RequestHandlerClass
            self.assertIsNone(handler.log_message(None, "%s", "noise"))
        finally:
            server.server_close()

    def test_write_methods_fail_closed_over_the_wire(self) -> None:
        with running(loopback_config()) as base:
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(method=method):
                    status, headers, body = call(
                        f"{base}/decision?symbol=NVDA&horizon=short",
                        method=method,
                    )

                    self.assertEqual(status, 405)
                    self.assertEqual(headers["Allow"], "GET")
                    self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_paths_outside_the_allowlist_are_refused_over_the_wire(self) -> None:
        with running(loopback_config()) as base:
            status, _, body = call(f"{base}/orders?symbol=NVDA")

            self.assertEqual(status, 404)
            self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_an_unconfigured_loopback_deployment_answers_without_a_credential(
        self,
    ) -> None:
        # A developer running this on their own machine with nothing in front
        # of it is the one case where loopback really does mean trusted, and
        # the one shape in which no credential database exists to consult.
        # Every configuration that is reachable from anywhere else demands a
        # device token; test_device_pairing.py asserts that over the wire.
        with running(loopback_config()) as base:
            self.assertEqual(call(f"{base}/health")[0], 200)

    def test_a_client_outside_the_allowlist_is_refused_before_any_analysis(
        self,
    ) -> None:
        config = loopback_config(allowed_client_networks=("192.168.50.0/24",))
        with running(config) as base:
            status, _, body = call(f"{base}/health")

            self.assertEqual(status, 403)
            self.assertEqual(body["error"]["code"], "CLIENT_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()


class FailClosedTests(unittest.TestCase):
    """A gate that cannot open must stop the service, not wave everyone through.

    `_admit` skips authorisation entirely when there is no gate, so swallowing
    the failure to open the credential database does not degrade one feature —
    it publishes every read path. The comment above the call says a database
    this service cannot read stops the deployment; nothing was holding that.
    """

    def test_an_unopenable_credential_database_refuses_to_build_a_server(
        self,
    ) -> None:
        config = AnalysisServerConfig.from_environment(
            {
                "ANALYSIS_API_TRUST_PROXY": "1",
                "DEVICE_AUTH_DATABASE": "/proc/nonexistent/devices.sqlite3",
            }
        )

        with self.assertRaises(Exception) as caught:
            build_server(service(Provider()), config)

        self.assertNotIsInstance(caught.exception, AssertionError)


class ForwardedForTests(unittest.TestCase):
    """Rate limiting is the only thing guarding the one write path.

    Its identity must come from the proxy, and a caller may send more than one
    X-Forwarded-For header. Reading only the first one lets the caller supply
    the line the limiter counts, which hands them an unlimited supply of
    pairing-code guesses.
    """

    def test_the_last_forwarded_header_line_decides_the_identity(self) -> None:
        from us_stock_helper_analysis_api.http_app import _forwarded_client

        class Headers:
            @staticmethod
            def get_all(name: str) -> list[str]:
                # A caller-supplied line first, the proxy's own line last.
                return ["8.8.8.8", "203.0.113.7"]

            @staticmethod
            def get(name: str, default: object = None) -> object:
                return "8.8.8.8"

        self.assertEqual(_forwarded_client(Headers()), "203.0.113.7")
