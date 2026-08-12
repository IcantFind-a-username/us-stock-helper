from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from us_stock_helper_market_gateway.errors import ErrorCode, GatewayError
from us_stock_helper_market_gateway.models import ProviderBatch, SessionHealth
from us_stock_helper_market_gateway.service import MarketGatewayService
from us_stock_helper_market_gateway.symbols import from_moomoo_code, to_moomoo_code


NOW = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self) -> None:
        self.health_result = SessionHealth(
            state="healthy",
            checked_at=NOW - timedelta(seconds=2),
            source="moomoo",
        )
        self.watchlist_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "name": "NVIDIA",
                    "price": 173.40,
                    "change_percent": 2.7,
                    "available_at": "2026-07-25T03:59:58+00:00",
                }
            ],
        )
        self.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.40,
                    "change_percent": 2.7,
                    "available_at": "2026-07-25T03:59:58+00:00",
                }
            ],
        )
        self.candles_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "timeframe": "5m",
                    "timestamp": "2026-07-25T03:50:00+00:00",
                    "available_at": "2026-07-25T03:55:00+00:00",
                    "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": True,
                    "open": 172.0,
                    "high": 174.0,
                    "low": 171.5,
                    "close": 173.4,
                    "volume": 1000,
                },
                {
                    "code": "US.NVDA",
                    "timeframe": "5m",
                    "timestamp": "2026-07-25T03:55:00+00:00",
                    "available_at": "2026-07-25T04:00:01+00:00",
                    "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": False,
                    "open": 173.4,
                    "high": 174.2,
                    "low": 173.0,
                    "close": 174.0,
                    "volume": 200,
                },
            ],
        )
        self.capital_flow_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "timestamp": "2026-07-25T03:58:00+00:00",
                    "available_at": "2026-07-25T03:59:00+00:00",
                    "session": "2026-07-24",
                    "total_net": 12_000.0,
                    "super_net": 5_000.0,
                    "big_net": 4_000.0,
                    "mid_net": 2_000.0,
                    "small_net": 1_000.0,
                }
            ],
        )
        self.capital_distribution_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "available_at": "2026-07-25T03:59:00+00:00",
                    "super_in": 10_000.0,
                    "super_out": 4_000.0,
                    "big_in": 8_000.0,
                    "big_out": 3_000.0,
                    "mid_in": 5_000.0,
                    "mid_out": 4_000.0,
                    "small_in": 2_000.0,
                    "small_out": 3_000.0,
                }
            ],
        )
        self.institutional_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "period": "2026/Q1",
                    "reported_at": "2026-03-31T20:00:00+00:00",
                    "available_at": "2026-05-16T14:00:00+00:00",
                    "institution_count": 863,
                    "institution_count_change": 12,
                    "shares_held": 4_192_178_205,
                    "shares_held_change": -3_105_448,
                    "holding_percent": 46.474,
                    "holding_percent_change": 0.03,
                    "source": "moomoo-delayed-institutional-disclosure",
                }
            ],
        )

    def health(self) -> SessionHealth:
        return self.health_result

    def watchlist(self, group: str | None = None) -> ProviderBatch:
        return self.watchlist_result

    def quotes(self, codes: list[str]) -> ProviderBatch:
        return self.quotes_result

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        return self.candles_result

    def capital_flow(self, code: str) -> ProviderBatch:
        return self.capital_flow_result

    def capital_distribution(self, code: str) -> ProviderBatch:
        return self.capital_distribution_result

    def institutional_holdings(self, code: str) -> ProviderBatch:
        return self.institutional_result


class SymbolNormalizationTests(unittest.TestCase):
    def test_us_symbol_round_trips_without_accepting_other_markets(self) -> None:
        self.assertEqual(to_moomoo_code(" nvda "), "US.NVDA")
        self.assertEqual(to_moomoo_code("US.NVDA"), "US.NVDA")
        self.assertEqual(from_moomoo_code("US.NVDA"), "NVDA")

        for bad in ("HK.00700", "NVDA/USD", "", "US."):
            with self.subTest(bad=bad):
                with self.assertRaises(GatewayError) as raised:
                    to_moomoo_code(bad)
                self.assertEqual(raised.exception.code, ErrorCode.INVALID_ARGUMENT)


class MarketGatewayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FakeProvider()
        self.service = MarketGatewayService(
            self.provider,
            clock=lambda: NOW,
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

    def test_health_reports_offline_without_claiming_live(self) -> None:
        self.provider.health_result = SessionHealth(
            state="offline",
            checked_at=NOW,
            source="moomoo",
            error_code=ErrorCode.OPEND_OFFLINE,
        )

        response = self.service.health()

        self.assertEqual(response["session"], "offline")
        self.assertEqual(response["items"][0]["status"], "offline")
        self.assertEqual(response["source"], "moomoo")

    def test_health_rejects_any_future_provider_check(self) -> None:
        self.provider.health_result = SessionHealth(
            state="healthy",
            checked_at=NOW + timedelta(milliseconds=1),
            source="moomoo",
        )

        response = self.service.health()

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_healthy_fresh_watchlist_is_normalized_and_live(self) -> None:
        response = self.service.watchlist("Technology")

        self.assertEqual(response["schemaVersion"], "1")
        self.assertEqual(response["source"], "moomoo")
        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["items"][0]["code"], "US.NVDA")
        self.assertEqual(response["items"][0]["price"], 173.40)
        self.assertEqual(response["items"][0]["changePercent"], 2.7)
        self.assertEqual(
            response["items"][0]["availableAt"],
            "2026-07-25T03:59:58Z",
        )
        self.assertLessEqual(response["asOf"], response["availableAt"])

    def test_sensitive_provider_fields_never_reach_response(self) -> None:
        self.provider.watchlist_result.items[0].update(
            {
                "password": "do-not-return",
                "token": "do-not-return",
                "cookie": "do-not-return",
            }
        )

        serialized = repr(self.service.watchlist()).lower()

        self.assertNotIn("do-not-return", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("cookie", serialized)

    def test_quotes_require_healthy_session(self) -> None:
        expected = {
            "offline": ErrorCode.OPEND_OFFLINE,
            "login_required": ErrorCode.LOGIN_REQUIRED,
            "permission_denied": ErrorCode.PERMISSION_DENIED,
            "quota_exceeded": ErrorCode.QUOTA_EXCEEDED,
            "sdk_unavailable": ErrorCode.SDK_UNAVAILABLE,
            "malformed": ErrorCode.MALFORMED_PROVIDER_DATA,
        }

        for state, code in expected.items():
            with self.subTest(state=state):
                self.provider.health_result = SessionHealth(
                    state=state,
                    checked_at=NOW,
                    source="moomoo",
                    error_code=code,
                )
                response = self.service.quotes(["NVDA"])
                self.assertEqual(response["session"], state.replace("_", "-"))
                self.assertEqual(response["error"]["code"], code.value)
                self.assertEqual(response["items"], [])

    def test_stale_or_non_moomoo_response_never_claims_live(self) -> None:
        cases = [
            ProviderBatch(
                source="moomoo",
                received_at=NOW - timedelta(minutes=1),
                items=self.provider.quotes_result.items,
            ),
            ProviderBatch(
                source="unknown",
                received_at=NOW,
                items=self.provider.quotes_result.items,
            ),
        ]

        for batch in cases:
            with self.subTest(source=batch.source, received_at=batch.received_at):
                self.provider.quotes_result = batch
                response = self.service.quotes(["NVDA"])
                self.assertNotEqual(response["session"], "healthy")
                self.assertIn(
                    response["error"]["code"],
                    {
                        ErrorCode.STALE_DATA.value,
                        ErrorCode.MALFORMED_PROVIDER_DATA.value,
                    },
                )

    def test_response_received_during_call_is_validated_against_completion_time(self) -> None:
        moments = iter(
            [
                NOW,
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=5),
            ]
        )
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(seconds=4),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "change_percent": 2.7,
                    "available_at": (NOW + timedelta(seconds=3)).isoformat(),
                }
            ],
        )
        service = MarketGatewayService(
            self.provider,
            clock=lambda: next(moments),
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

        response = service.quotes(["NVDA"])

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["availableAt"], "2026-07-25T04:00:04Z")

    def test_item_available_after_provider_receipt_is_rejected(self) -> None:
        moments = iter(
            [
                NOW,
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=5),
            ]
        )
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(seconds=2),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "change_percent": 2.7,
                    "available_at": (NOW + timedelta(seconds=3)).isoformat(),
                }
            ],
        )
        service = MarketGatewayService(
            self.provider,
            clock=lambda: next(moments),
        )

        response = service.quotes(["NVDA"])

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_rejects_future_provider_receipt_without_tolerance(self) -> None:
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(milliseconds=1),
            items=self.provider.quotes_result.items,
        )

        response = self.service.quotes(["NVDA"])

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_future_completed_candle_rejects_the_entire_batch(self) -> None:
        self.provider.candles_result.items.append(
            {
                "code": "US.NVDA",
                "timeframe": "5m",
                "timestamp": (NOW + timedelta(minutes=5)).isoformat(),
                "available_at": (NOW + timedelta(milliseconds=1)).isoformat(),
                "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": True,
                "open": 174.0,
                "high": 175.0,
                "low": 173.5,
                "close": 174.5,
                "volume": 100,
            }
        )

        response = self.service.candles("NVDA", "5m", 200)

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(response["items"], [])

    def test_malformed_quote_is_structured_error(self) -> None:
        self.provider.quotes_result.items[0]["available_at"] = "not-a-time"

        response = self.service.quotes(["NVDA"])

        self.assertNotEqual(response["session"], "healthy")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )
        self.assertNotIn("not-a-time", repr(response))

    def test_candles_return_only_completed_point_in_time_bars(self) -> None:
        response = self.service.candles("NVDA", "5m", 200)

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["symbol"], "NVDA")
        self.assertEqual(response["interval"], "5m")
        self.assertEqual(len(response["items"]), 1)
        candle = response["items"][0]
        self.assertTrue(candle["complete"])
        self.assertLessEqual(candle["availableAt"], response["asOf"])

    def test_snapshot_cutoff_is_the_completed_operation_time(self) -> None:
        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["decisionCutoff"], "2026-07-25T04:00:00Z")

    def test_provider_quota_failure_is_sanitized(self) -> None:
        def fail(codes: list[str]) -> ProviderBatch:
            raise GatewayError(
                ErrorCode.QUOTA_EXCEEDED,
                "Provider quota exceeded",
                retriable=True,
                details={"password": "secret", "raw": "account=123"},
            )

        self.provider.quotes = fail  # type: ignore[method-assign]
        response = self.service.quotes(["NVDA"])

        self.assertEqual(response["session"], "quota-exceeded")
        self.assertEqual(
            response["error"],
            {
                "code": "QUOTA_EXCEEDED",
                "message": "Provider quota exceeded",
                "retriable": True,
            },
        )
        self.assertNotIn("secret", repr(response))

    def test_capital_flow_is_large_order_proxy_not_institution_identity(self) -> None:
        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["symbol"], "NVDA")
        self.assertEqual(response["semantics"], "large-order-flow-proxy")
        self.assertFalse(response["institutionalIdentity"])
        self.assertEqual(response["items"][0]["largeOrderProxyNetFlow"], 9000.0)
        self.assertFalse(response["items"][0]["institutionalIdentity"])
        self.assertEqual(response["items"][0]["session"], "2026-07-24")

    def test_capital_flow_rejects_a_provider_symbol_mismatch_atomically(self) -> None:
        self.provider.capital_flow_result.items[0]["code"] = "US.TSLA"

        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(response["items"], [])

    def test_capital_distribution_keeps_order_size_buckets_explicit(self) -> None:
        response = self.service.capital_distribution("NVDA")

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["semantics"], "order-size-distribution-proxy")
        self.assertEqual(response["items"][0]["extraLargeOrderNetFlow"], 6000.0)
        self.assertEqual(response["items"][0]["largeOrderNetFlow"], 5000.0)
        self.assertFalse(response["institutionalIdentity"])

    def test_institutional_holdings_are_delayed_and_point_in_time(self) -> None:
        response = self.service.institutional_holdings("NVDA")

        item = response["items"][0]
        self.assertEqual(response["semantics"], "delayed-reported-holdings")
        self.assertEqual(item["reportedAt"], "2026-03-31T20:00:00Z")
        self.assertEqual(item["reportedAtBasis"], "reporting-period-end")
        self.assertEqual(item["availableAt"], "2026-05-16T14:00:00Z")
        self.assertEqual(item["source"], "moomoo-delayed-institutional-disclosure")
        self.assertLess(item["reportedAt"], item["availableAt"])

    def test_unsupported_provider_capability_is_explicit(self) -> None:
        def unsupported(code: str) -> ProviderBatch:
            raise GatewayError(
                ErrorCode.UNSUPPORTED_CAPABILITY,
                "OpenD SDK does not expose this quote capability",
            )

        self.provider.capital_flow = unsupported  # type: ignore[method-assign]

        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "unsupported-capability")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.UNSUPPORTED_CAPABILITY.value,
        )
        self.assertEqual(response["items"], [])


if __name__ == "__main__":
    unittest.main()
