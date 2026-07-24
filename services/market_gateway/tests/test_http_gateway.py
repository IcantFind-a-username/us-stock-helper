from __future__ import annotations

import unittest
from datetime import datetime, timezone

from us_stock_helper_market_gateway.http_gateway import (
    GatewayApplication,
    GatewayServerConfig,
    _encode_response_body,
)


class StubService:
    def health(self) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "items": [{"status": "healthy"}],
        }

    def watchlist(self, group: str | None = None) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "items": [],
        }

    def quotes(self, symbols: list[str]) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "items": [],
        }

    def candles(self, symbol: str, timeframe: str, count: int) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "symbol": symbol,
            "interval": timeframe,
            "items": [],
        }

    def capital_flow(self, symbol: str) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "symbol": symbol,
            "semantics": "large-order-flow-proxy",
            "institutionalIdentity": False,
            "items": [],
        }

    def capital_distribution(self, symbol: str) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "symbol": symbol,
            "semantics": "order-size-distribution-proxy",
            "institutionalIdentity": False,
            "items": [],
        }

    def institutional_holdings(self, symbol: str) -> dict:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "healthy",
            "asOf": "2026-07-25T04:00:00Z",
            "availableAt": "2026-07-25T04:00:00Z",
            "symbol": symbol,
            "semantics": "delayed-reported-holdings",
            "items": [],
        }


class GatewayServerConfigTests(unittest.TestCase):
    def test_default_configuration_is_loopback_only(self) -> None:
        config = GatewayServerConfig.from_environment({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertFalse(config.allow_lan)
        self.assertEqual(config.allowed_client_networks, ("127.0.0.0/8", "::1/128"))

    def test_non_loopback_binding_requires_explicit_hardened_lan_config(self) -> None:
        incomplete = {
            "MOOMOO_GATEWAY_ALLOW_LAN": "1",
            "MOOMOO_GATEWAY_HOST": "0.0.0.0",
        }
        with self.assertRaises(ValueError):
            GatewayServerConfig.from_environment(incomplete)

        complete = {
            **incomplete,
            "MOOMOO_GATEWAY_TOKEN": "long-random-runtime-secret",
            "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.168.50.0/24",
            "MOOMOO_GATEWAY_ALLOWED_ORIGINS": "http://192.168.50.20:8081",
        }
        config = GatewayServerConfig.from_environment(complete)
        self.assertTrue(config.allow_lan)
        self.assertEqual(config.allowed_client_networks, ("192.168.50.0/24",))


class GatewayApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = GatewayServerConfig.from_environment({})
        self.app = GatewayApplication(
            StubService(),  # type: ignore[arg-type]
            self.config,
            clock=lambda: datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc),
        )

    def test_only_allowlisted_read_paths_are_exposed(self) -> None:
        for path in (
            "/health",
            "/watchlist",
            "/quotes",
            "/candles",
            "/capital-flow",
            "/capital-distribution",
            "/institutional-holdings",
        ):
            with self.subTest(path=path):
                query = (
                    {}
                    if path in {"/health", "/watchlist"}
                    else {"symbols": ["NVDA"]}
                    if path == "/quotes"
                    else {"symbol": ["NVDA"]}
                )
                status, _, body = self.app.handle(
                    "GET", path, query, {}, "127.0.0.1"
                )
                self.assertNotEqual(status, 404)
                self.assertNotEqual(
                    body.get("error", {}).get("code"), "PATH_NOT_ALLOWED"
                )

        status, _, body = self.app.handle(
            "GET", "/trade/orders", {}, {}, "127.0.0.1"
        )
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_write_methods_are_rejected(self) -> None:
        status, headers, body = self.app.handle(
            "POST", "/quotes", {}, {}, "127.0.0.1"
        )

        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET, OPTIONS")
        self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_default_rejects_non_loopback_client_and_unapproved_origin(self) -> None:
        status, _, body = self.app.handle(
            "GET", "/health", {}, {}, "192.168.1.8"
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "CLIENT_NOT_ALLOWED")

        status, headers, body = self.app.handle(
            "GET",
            "/health",
            {},
            {"Origin": "https://attacker.example"},
            "127.0.0.1",
        )
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(body["error"]["code"], "ORIGIN_NOT_ALLOWED")

    def test_lan_mode_requires_bearer_token_without_echoing_it(self) -> None:
        token = "long-random-runtime-secret"
        config = GatewayServerConfig.from_environment(
            {
                "MOOMOO_GATEWAY_ALLOW_LAN": "1",
                "MOOMOO_GATEWAY_HOST": "0.0.0.0",
                "MOOMOO_GATEWAY_TOKEN": token,
                "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.168.50.0/24",
            }
        )
        app = GatewayApplication(StubService(), config)  # type: ignore[arg-type]

        status, _, body = app.handle(
            "GET", "/health", {}, {}, "192.168.50.8"
        )
        self.assertEqual(status, 401)
        self.assertNotIn(token, repr(body))

        status, _, body = app.handle(
            "GET",
            "/health",
            {},
            {"Authorization": f"Bearer {token}"},
            "192.168.50.8",
        )
        self.assertEqual(status, 200)
        self.assertNotIn(token, repr(body))

    def test_lan_browser_preflight_is_allowed_but_get_remains_authenticated(self) -> None:
        origin = "http://192.168.50.20:8081"
        config = GatewayServerConfig.from_environment(
            {
                "MOOMOO_GATEWAY_ALLOW_LAN": "1",
                "MOOMOO_GATEWAY_HOST": "0.0.0.0",
                "MOOMOO_GATEWAY_TOKEN": "long-random-runtime-secret",
                "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.168.50.0/24",
                "MOOMOO_GATEWAY_ALLOWED_ORIGINS": origin,
            }
        )
        app = GatewayApplication(StubService(), config)  # type: ignore[arg-type]

        status, headers, body = app.handle(
            "OPTIONS",
            "/health",
            {},
            {"Origin": origin},
            "192.168.50.8",
        )

        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
        self.assertEqual(body, {})

    def test_query_validation_returns_structured_errors(self) -> None:
        cases = [
            ("/quotes", {}, "INVALID_ARGUMENT"),
            ("/candles", {"symbol": ["NVDA"], "count": ["1001"]}, "INVALID_ARGUMENT"),
            ("/candles", {"symbol": ["NVDA"], "timeframe": ["tick"]}, "INVALID_ARGUMENT"),
        ]

        for path, query, expected in cases:
            with self.subTest(path=path, query=query):
                status, _, body = self.app.handle(
                    "GET", path, query, {}, "127.0.0.1"
                )
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], expected)

    def test_preflight_uses_zero_length_body(self) -> None:
        self.assertEqual(_encode_response_body("OPTIONS", 204, {}), b"")
        self.assertEqual(
            _encode_response_body("GET", 200, {"items": []}),
            b'{"items":[]}',
        )


if __name__ == "__main__":
    unittest.main()
