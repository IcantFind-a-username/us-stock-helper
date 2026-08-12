from __future__ import annotations

import unittest
from datetime import datetime, timezone

from us_stock_helper_market_gateway.http_gateway import (
    GatewayApplication,
    GatewayServerConfig,
    _encode_response_body,
)
from us_stock_helper_market_gateway.errors import ErrorCode, GatewayError
from us_stock_helper_market_gateway.models import SessionHealth
from us_stock_helper_market_gateway.service import MarketGatewayService


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

    def stock_snapshot(self, symbol: str, timeframe: str, count: int) -> dict:
        return {
            "schemaVersion": "2",
            "source": "moomoo",
            "sourceStatus": "live",
            "symbol": symbol,
            "interval": timeframe,
            "decisionCutoff": "2026-07-25T04:00:00Z",
            "quote": {},
            "completedCandles": [],
            "participationBars": [],
            "indicators": {},
            "institutionalHoldings": [],
            "provenance": [],
            "warnings": [],
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
            "MOOMOO_GATEWAY_TOKEN": "0123456789abcdef0123456789abcdef",
            "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.168.50.0/24",
            "MOOMOO_GATEWAY_ALLOWED_ORIGINS": "http://192.168.50.20:8081",
        }
        config = GatewayServerConfig.from_environment(complete)
        self.assertTrue(config.allow_lan)
        self.assertEqual(config.allowed_client_networks, ("192.168.50.0/24",))

    def test_lan_configuration_rejects_weak_tokens_and_world_cidrs(self) -> None:
        base = {
            "MOOMOO_GATEWAY_ALLOW_LAN": "1",
            "MOOMOO_GATEWAY_HOST": "0.0.0.0",
            "MOOMOO_GATEWAY_TOKEN": "0123456789abcdef0123456789abcdef",
            "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.168.50.0/24",
        }
        with self.assertRaisesRegex(ValueError, "32"):
            GatewayServerConfig.from_environment(
                {**base, "MOOMOO_GATEWAY_TOKEN": "x" * 31}
            )
        for cidr in ("0.0.0.0/0", "::/0"):
            with self.subTest(cidr=cidr):
                with self.assertRaisesRegex(ValueError, "broad"):
                    GatewayServerConfig.from_environment(
                        {**base, "MOOMOO_GATEWAY_ALLOWED_CLIENTS": cidr}
                    )


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
            "/stock-snapshot",
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
        token = "0123456789abcdef0123456789abcdef"
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
                "MOOMOO_GATEWAY_TOKEN": "0123456789abcdef0123456789abcdef",
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

    def test_stock_snapshot_uses_candle_query_constraints(self) -> None:
        status, _, body = self.app.handle(
            "GET",
            "/stock-snapshot",
            {"symbol": ["NVDA"], "interval": ["5m"], "count": ["200"]},
            {},
            "127.0.0.1",
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["schemaVersion"], "2")
        self.assertEqual(body["symbol"], "NVDA")
        self.assertEqual(body["interval"], "5m")

    def test_mid_operation_opend_offline_maps_to_retryable_http_503(self) -> None:
        class OfflineDuringCandlesProvider:
            def health(self) -> SessionHealth:
                return SessionHealth(
                    "healthy",
                    datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc),
                    "moomoo",
                )

            def quotes(self, codes: list[str]) -> object:
                raise GatewayError(
                    ErrorCode.OPEND_OFFLINE,
                    "moomoo OpenD is offline",
                    retriable=True,
                )

        service = MarketGatewayService(
            OfflineDuringCandlesProvider(),  # type: ignore[arg-type]
            clock=lambda: datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc),
        )
        app = GatewayApplication(service, self.config)

        status, _, body = app.handle(
            "GET",
            "/stock-snapshot",
            {"symbol": ["NVDA"], "interval": ["5m"], "count": ["200"]},
            {},
            "127.0.0.1",
        )

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "OPEND_OFFLINE")
        self.assertTrue(body["error"]["retriable"])

    def test_preflight_uses_zero_length_body(self) -> None:
        self.assertEqual(_encode_response_body("OPTIONS", 204, {}), b"")
        self.assertEqual(
            _encode_response_body("GET", 200, {"items": []}),
            b'{"items":[]}',
        )


if __name__ == "__main__":
    unittest.main()
