from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from us_stock_helper_market_gateway.errors import ErrorCode, GatewayError
from us_stock_helper_market_gateway.opend_adapter import MoomooOpenDProvider


NOW = datetime(2026, 7, 25, 15, 56, tzinfo=timezone.utc)


class FakeFrame:
    def __init__(
        self,
        records: list[dict],
        *,
        attrs: dict | None = None,
    ) -> None:
        self.records = records
        self.attrs = attrs or {}

    def to_dict(self, orient: str) -> list[dict]:
        if orient != "records":
            raise AssertionError(f"Unexpected orient: {orient}")
        return self.records


class FakeQuoteContext:
    global_state = (0, {"qot_logined": True})
    watchlist = (
        0,
        FakeFrame(
            [
                {
                    "code": "US.NVDA",
                    "name": "NVIDIA",
                    "lot_size": 1,
                    "stock_type": "STOCK",
                }
            ]
        ),
    )
    snapshots = (
        0,
        FakeFrame(
            [
                {
                    "code": "US.NVDA",
                    "last_price": 173.4,
                    "prev_close_price": 168.84,
                    "open_price": 170.0,
                    "high_price": 174.0,
                    "low_price": 169.5,
                    "volume": 12_345,
                    "turnover": 2_000_000.0,
                    "update_time": "2026-07-25 11:55:58",
                }
            ]
        ),
    )
    history = (
        0,
        FakeFrame(
            [
                {
                    "code": "US.NVDA",
                    "time_key": "2026-07-25 11:50:00",
                    "open": 172.0,
                    "high": 174.0,
                    "low": 171.5,
                    "close": 173.4,
                    "volume": 1000,
                    "turnover": 1_000_000.0,
                },
                {
                    "code": "US.NVDA",
                    "time_key": "2026-07-25 11:55:00",
                    "open": 173.4,
                    "high": 174.2,
                    "low": 173.0,
                    "close": 174.0,
                    "volume": 100,
                    "turnover": 100_000.0,
                },
            ]
        ),
        None,
    )
    flow = (
        0,
        FakeFrame(
            [
                {
                    "code": "US.NVDA",
                    "in_flow": 12_000.0,
                    "super_in_flow": 5_000.0,
                    "big_in_flow": 4_000.0,
                    "mid_in_flow": 2_000.0,
                    "sml_in_flow": 1_000.0,
                    "capital_flow_item_time": "2026-07-25 11:54:00",
                    "last_valid_time": "2026-07-25 11:55:00",
                }
            ]
        ),
    )
    distribution = (
        0,
        FakeFrame(
            [
                {
                    "code": "US.NVDA",
                    "capital_in_super": 10_000.0,
                    "capital_out_super": 4_000.0,
                    "capital_in_big": 8_000.0,
                    "capital_out_big": 3_000.0,
                    "capital_in_mid": 5_000.0,
                    "capital_out_mid": 4_000.0,
                    "capital_in_small": 2_000.0,
                    "capital_out_small": 3_000.0,
                    "update_time": "2026-07-25 11:55:00",
                }
            ]
        ),
    )
    institutional = (
        0,
        FakeFrame(
            [
                {
                    "period_text": "2026/Q1",
                    "institution_quantity": 863,
                    "institution_quantity_change": 12,
                    "holder_quantity": 4_192_178_205,
                    "holder_quantity_change": -3_105_448,
                    "holder_pct": 46.474,
                    "holder_pct_change": 0.03,
                    "update_time_str": "2026-05-16 10:00:00",
                }
            ],
            attrs={"next_key": "-1"},
        ),
    )

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def get_global_state(self) -> tuple[int, object]:
        return self.global_state

    def get_user_security_group(
        self,
        group_type: str = "ALL",
    ) -> tuple[int, object]:
        return 0, FakeFrame([{"group_name": "All", "group_type": "SYSTEM"}])

    def get_user_security(self, group_name: str) -> tuple[int, object]:
        return self.watchlist

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        return self.snapshots

    def request_history_kline(
        self,
        code: str,
        ktype: str,
        max_count: int,
        **_: object,
    ) -> tuple[int, object, object]:
        return self.history

    def get_capital_flow(self, stock_code: str) -> tuple[int, object]:
        return self.flow

    def get_capital_distribution(self, stock_code: str) -> tuple[int, object]:
        return self.distribution

    def get_shareholders_institutional(
        self,
        code: str,
        next_key: str | None = None,
        num: int | None = None,
    ) -> tuple[int, object]:
        return self.institutional

    def close(self) -> None:
        return None


class PagedQuoteContext(FakeQuoteContext):
    def request_history_kline(
        self,
        code: str,
        ktype: str,
        max_count: int,
        page_req_key: bytes | None = None,
        **_: object,
    ) -> tuple[int, object, object]:
        if page_req_key is None:
            return (
                0,
                FakeFrame(
                    [
                        {
                            "code": code,
                            "time_key": "2026-07-25 11:40:00",
                            "open": 170.0,
                            "high": 171.0,
                            "low": 169.0,
                            "close": 170.5,
                            "volume": 900,
                        }
                    ]
                ),
                b"next",
            )
        return FakeQuoteContext.history


class LocalizedGroupQuoteContext(FakeQuoteContext):
    def get_user_security_group(
        self,
        group_type: str = "ALL",
    ) -> tuple[int, object]:
        return 0, FakeFrame([{"group_name": "全部", "group_type": "SYSTEM"}])

    def get_user_security(self, group_name: str) -> tuple[int, object]:
        if group_name != "全部":
            return -1, "未知自选股分组"
        return (
            0,
            FakeFrame(
                [
                    *self.watchlist[1].records,
                    {
                        "code": "HK.00700",
                        "name": "Tencent",
                        "lot_size": 100,
                        "stock_type": "STOCK",
                    },
                    {
                        "code": "US.PMRTY",
                        "name": "Unsupported OTC",
                        "lot_size": 1,
                        "stock_type": "STOCK",
                    },
                    {
                        "code": "US.OTC2",
                        "name": "Second Unsupported OTC",
                        "lot_size": 1,
                        "stock_type": "STOCK",
                    },
                ]
            ),
        )

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        if any(not code.startswith("US.") for code in codes):
            return -1, "unsupported quote market"
        if any(code in {"US.PMRTY", "US.OTC2"} for code in codes):
            return -1, "unsupported US OTC quote"
        return self.snapshots


class FutureValidTimeQuoteContext(FakeQuoteContext):
    flow = (
        0,
        FakeFrame(
            [
                {
                    **FakeQuoteContext.flow[1].records[0],
                    "last_valid_time": "2026-07-25 11:56:10",
                }
            ]
        ),
    )

class CrossUtcSessionQuoteContext(FakeQuoteContext):
    flow = (
        0,
        FakeFrame(
            [
                {
                    **FakeQuoteContext.flow[1].records[0],
                    "capital_flow_item_time": "2026-07-24 23:54:00",
                }
            ]
        ),
    )


class MismatchedFlowCodeQuoteContext(FakeQuoteContext):
    flow = (
        0,
        FakeFrame(
            [
                {
                    **FakeQuoteContext.flow[1].records[0],
                    "code": "US.TSLA",
                }
            ]
        ),
    )


class PagedInstitutionalContext(FakeQuoteContext):
    def get_shareholders_institutional(
        self,
        code: str,
        next_key: str | None = None,
        num: int | None = None,
    ) -> tuple[int, object]:
        if next_key is None:
            first = dict(FakeQuoteContext.institutional[1].records[0])
            first["next_key"] = "next"
            return 0, FakeFrame([first])
        second = dict(FakeQuoteContext.institutional[1].records[0])
        second.update(
            {
                "period_text": "2025/Q4",
                "next_key": "-1",
                "update_time_str": "2026-02-15 10:00:00",
            }
        )
        return 0, FakeFrame([second])


ADVANCING_CLOCK = {"now": NOW}
AFTER_RESPONSE = datetime(2026, 7, 25, 16, 0, 1, tzinfo=timezone.utc)


class AdvancingQuoteContext(FakeQuoteContext):
    @staticmethod
    def _advance() -> None:
        ADVANCING_CLOCK["now"] = AFTER_RESPONSE

    def get_global_state(self) -> tuple[int, object]:
        self._advance()
        return super().get_global_state()

    def get_user_security(self, group_name: str) -> tuple[int, object]:
        self._advance()
        return super().get_user_security(group_name)

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        self._advance()
        return super().get_market_snapshot(codes)

    def request_history_kline(
        self,
        code: str,
        ktype: str,
        max_count: int,
        **kwargs: object,
    ) -> tuple[int, object, object]:
        self._advance()
        return super().request_history_kline(
            code,
            ktype,
            max_count,
            **kwargs,
        )

    def get_capital_flow(self, stock_code: str) -> tuple[int, object]:
        self._advance()
        return super().get_capital_flow(stock_code)

    def get_capital_distribution(self, stock_code: str) -> tuple[int, object]:
        self._advance()
        return super().get_capital_distribution(stock_code)

    def get_shareholders_institutional(
        self,
        code: str,
        next_key: str | None = None,
        num: int | None = None,
    ) -> tuple[int, object]:
        self._advance()
        return super().get_shareholders_institutional(code, next_key, num)


def fake_sdk() -> object:
    return SimpleNamespace(
        RET_OK=0,
        KLType=SimpleNamespace(
            K_1M="K_1M",
            K_5M="K_5M",
            K_15M="K_15M",
            K_30M="K_30M",
            K_60M="K_60M",
            K_DAY="K_DAY",
            K_WEEK="K_WEEK",
        ),
        AuType=SimpleNamespace(QFQ="QFQ"),
        OpenQuoteContext=FakeQuoteContext,
    )


def paged_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = PagedQuoteContext
    return sdk


def localized_group_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = LocalizedGroupQuoteContext
    return sdk


def future_valid_time_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = FutureValidTimeQuoteContext
    return sdk

def cross_utc_session_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = CrossUtcSessionQuoteContext
    return sdk


def mismatched_flow_code_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = MismatchedFlowCodeQuoteContext
    return sdk


def paged_institutional_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = PagedInstitutionalContext
    return sdk


def advancing_sdk() -> object:
    sdk = fake_sdk()
    sdk.OpenQuoteContext = AdvancingQuoteContext
    return sdk


def no_op_probe(host: str, port: int, timeout: float) -> None:
    return None


class MoomooOpenDProviderTests(unittest.TestCase):
    def test_unreachable_port_fails_before_loading_sdk(self) -> None:
        loaded = {"value": False}

        def load_sdk() -> object:
            loaded["value"] = True
            return fake_sdk()

        def refuse(host: str, port: int, timeout: float) -> None:
            raise ConnectionRefusedError("raw socket detail")

        provider = MoomooOpenDProvider(
            sdk_loader=load_sdk,
            connectivity_probe=refuse,
            clock=lambda: NOW,
        )

        health = provider.health()

        self.assertFalse(loaded["value"])
        self.assertEqual(health.state, "offline")
        self.assertEqual(health.error_code, ErrorCode.OPEND_OFFLINE)

    def test_missing_sdk_is_safe_structured_degradation(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=lambda: (_ for _ in ()).throw(ModuleNotFoundError("moomoo")),
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        health = provider.health()

        self.assertEqual(health.state, "sdk_unavailable")
        self.assertEqual(health.error_code, ErrorCode.SDK_UNAVAILABLE)

    def test_health_detects_login_required(self) -> None:
        original = FakeQuoteContext.global_state
        FakeQuoteContext.global_state = (0, {"qot_logined": False})
        self.addCleanup(setattr, FakeQuoteContext, "global_state", original)
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        health = provider.health()

        self.assertEqual(health.state, "login_required")
        self.assertEqual(health.error_code, ErrorCode.LOGIN_REQUIRED)

    def test_health_classifies_connection_failure_as_offline(self) -> None:
        sdk = fake_sdk()

        def fail_context(*_: object, **__: object) -> object:
            raise ConnectionRefusedError("connection refused")

        sdk.OpenQuoteContext = fail_context
        provider = MoomooOpenDProvider(
            sdk_loader=lambda: sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        health = provider.health()

        self.assertEqual(health.state, "offline")
        self.assertEqual(health.error_code, ErrorCode.OPEND_OFFLINE)

    def test_health_classifies_connection_drop_during_probe_as_offline(self) -> None:
        class DroppedContext(FakeQuoteContext):
            def get_global_state(self) -> tuple[int, object]:
                raise ConnectionResetError("connection reset")

        sdk = fake_sdk()
        sdk.OpenQuoteContext = DroppedContext
        provider = MoomooOpenDProvider(
            sdk_loader=lambda: sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        health = provider.health()

        self.assertEqual(health.state, "offline")
        self.assertEqual(health.error_code, ErrorCode.OPEND_OFFLINE)

    def test_adapter_normalizes_watchlist_and_quotes_to_utc(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        watchlist = provider.watchlist()
        quotes = provider.quotes(["US.NVDA"])

        self.assertEqual(watchlist.source, "moomoo")
        self.assertEqual(watchlist.items[0]["code"], "US.NVDA")
        self.assertEqual(
            watchlist.items[0]["available_at"], "2026-07-25T15:55:58Z"
        )
        self.assertEqual(watchlist.items[0]["price"], 173.4)
        self.assertAlmostEqual(
            watchlist.items[0]["change_percent"], 2.7008, places=3
        )
        self.assertEqual(
            quotes.items[0]["available_at"], "2026-07-25T15:55:58Z"
        )
        self.assertAlmostEqual(quotes.items[0]["change_percent"], 2.7008, places=3)

    def test_watchlist_discovers_the_localized_all_group(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=localized_group_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        watchlist = provider.watchlist()

        self.assertEqual(watchlist.items[0]["code"], "US.NVDA")
        self.assertEqual(len(watchlist.items), 1)

    def test_capital_flow_uses_receipt_time_not_provider_valid_until(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=future_valid_time_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        flow = provider.capital_flow("US.NVDA")

        self.assertEqual(flow.items[0]["available_at"], "2026-07-25T15:56:00Z")

    def test_capital_flow_preserves_exchange_session_across_utc_midnight(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=cross_utc_session_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        flow = provider.capital_flow("US.NVDA")

        self.assertEqual(flow.items[0]["timestamp"], "2026-07-25T03:54:00Z")
        self.assertEqual(flow.items[0]["session"], "2026-07-24")

    def test_capital_flow_rejects_provider_row_code_mismatch(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=mismatched_flow_code_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        with self.assertRaises(GatewayError) as raised:
            provider.capital_flow("US.NVDA")

        self.assertEqual(
            raised.exception.code,
            ErrorCode.MALFORMED_PROVIDER_DATA,
        )

    def test_adapter_marks_only_closed_candles_complete(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        batch = provider.candles("US.NVDA", "5m", 200)

        self.assertEqual(len(batch.items), 2)
        self.assertTrue(batch.items[0]["complete"])
        self.assertEqual(
            batch.items[0]["timestamp"], "2026-07-25T15:55:00Z"
        )
        self.assertEqual(
            batch.items[0]["available_at"], "2026-07-25T15:55:00Z"
        )
        self.assertFalse(batch.items[1]["complete"])
        self.assertEqual(
            batch.items[1]["timestamp"], "2026-07-25T16:00:00Z"
        )
        self.assertEqual(
            batch.items[1]["available_at"], "2026-07-25T16:00:00Z"
        )

    def test_candle_count_returns_the_latest_rows(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        batch = provider.candles("US.NVDA", "5m", 1)

        self.assertEqual(len(batch.items), 1)
        self.assertEqual(
            batch.items[0]["timestamp"], "2026-07-25T16:00:00Z"
        )

    def test_candles_follow_pages_before_selecting_latest_rows(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=paged_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        batch = provider.candles("US.NVDA", "5m", 2)

        self.assertEqual(
            [item["timestamp"] for item in batch.items],
            ["2026-07-25T15:55:00Z", "2026-07-25T16:00:00Z"],
        )

    def test_provider_error_categories_are_stable_and_sanitized(self) -> None:
        cases = {
            "Please login OpenD first": ErrorCode.LOGIN_REQUIRED,
            "请先登录 OpenD": ErrorCode.LOGIN_REQUIRED,
            "No quote authority or permission": ErrorCode.PERMISSION_DENIED,
            "无行情权限": ErrorCode.PERMISSION_DENIED,
            "Request frequency quota exceeded": ErrorCode.QUOTA_EXCEEDED,
            "请求频率达到上限": ErrorCode.QUOTA_EXCEEDED,
            "Connection refused": ErrorCode.OPEND_OFFLINE,
            "连接超时": ErrorCode.OPEND_OFFLINE,
            "Unexpected upstream payload": ErrorCode.PROVIDER_ERROR,
        }

        for message, expected in cases.items():
            with self.subTest(message=message):
                FakeQuoteContext.snapshots = (-1, message)
                self.addCleanup(
                    setattr,
                    FakeQuoteContext,
                    "snapshots",
                    (
                        0,
                        FakeFrame(
                            [
                                {
                                    "code": "US.NVDA",
                                    "last_price": 173.4,
                                    "prev_close_price": 168.84,
                                    "open_price": 170.0,
                                    "high_price": 174.0,
                                    "low_price": 169.5,
                                    "volume": 12_345,
                                    "turnover": 2_000_000.0,
                                    "update_time": "2026-07-25 11:55:58",
                                }
                            ]
                        ),
                    ),
                )
                provider = MoomooOpenDProvider(
                    sdk_loader=fake_sdk,
                    connectivity_probe=no_op_probe,
                    clock=lambda: NOW,
                )
                with self.assertRaises(GatewayError) as raised:
                    provider.quotes(["US.NVDA"])
                self.assertEqual(raised.exception.code, expected)
                self.assertNotIn(message, raised.exception.public_dict())

    def test_health_and_batches_use_sdk_completion_time(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=advancing_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: ADVANCING_CLOCK["now"],
        )

        ADVANCING_CLOCK["now"] = NOW
        self.assertEqual(provider.health().checked_at, AFTER_RESPONSE)

        operations = [
            lambda: provider.watchlist(),
            lambda: provider.quotes(["US.NVDA"]),
            lambda: provider.candles("US.NVDA", "5m", 2),
            lambda: provider.capital_flow("US.NVDA"),
            lambda: provider.capital_distribution("US.NVDA"),
            lambda: provider.institutional_holdings("US.NVDA"),
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                ADVANCING_CLOCK["now"] = NOW
                batch = operation()
                self.assertEqual(batch.received_at, AFTER_RESPONSE)

    def test_capital_apis_are_explicit_non_identity_proxies(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        flow = provider.capital_flow("US.NVDA")
        distribution = provider.capital_distribution("US.NVDA")

        self.assertEqual(flow.items[0]["total_net"], 12_000.0)
        self.assertEqual(flow.items[0]["available_at"], "2026-07-25T15:56:00Z")
        self.assertNotIn("institution", repr(flow.items[0]).lower())
        self.assertEqual(distribution.items[0]["super_in"], 10_000.0)
        self.assertEqual(
            distribution.items[0]["available_at"],
            "2026-07-25T15:55:00Z",
        )

    def test_institutional_holdings_preserve_report_and_availability_times(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=fake_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        batch = provider.institutional_holdings("US.NVDA")

        item = batch.items[0]
        self.assertEqual(item["period"], "2026/Q1")
        self.assertEqual(item["reported_at"], "2026-03-31T20:00:00Z")
        self.assertEqual(item["available_at"], "2026-05-16T14:00:00Z")
        self.assertEqual(
            item["source"],
            "moomoo-delayed-institutional-disclosure",
        )

    def test_institutional_holdings_follow_dataframe_next_key(self) -> None:
        provider = MoomooOpenDProvider(
            sdk_loader=paged_institutional_sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        batch = provider.institutional_holdings("US.NVDA")

        self.assertEqual(
            [item["period"] for item in batch.items],
            ["2026/Q1", "2025/Q4"],
        )

    def test_missing_optional_quote_capability_is_not_fabricated(self) -> None:
        class MinimalContext:
            def __init__(self, **_: object) -> None:
                pass

            def close(self) -> None:
                pass

        sdk = fake_sdk()
        sdk.OpenQuoteContext = MinimalContext
        provider = MoomooOpenDProvider(
            sdk_loader=lambda: sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        with self.assertRaises(GatewayError) as raised:
            provider.capital_flow("US.NVDA")

        self.assertEqual(
            raised.exception.code,
            ErrorCode.UNSUPPORTED_CAPABILITY,
        )

    def test_incompatible_optional_quote_signature_is_explicitly_unsupported(self) -> None:
        class IncompatibleContext:
            def __init__(self, **_: object) -> None:
                pass

            def get_capital_flow(
                self,
                code: str,
                required_new_argument: object,
            ) -> tuple[int, object]:
                raise AssertionError("must not fabricate an argument")

            def close(self) -> None:
                pass

        sdk = fake_sdk()
        sdk.OpenQuoteContext = IncompatibleContext
        provider = MoomooOpenDProvider(
            sdk_loader=lambda: sdk,
            connectivity_probe=no_op_probe,
            clock=lambda: NOW,
        )

        with self.assertRaises(GatewayError) as raised:
            provider.capital_flow("US.NVDA")

        self.assertEqual(
            raised.exception.code,
            ErrorCode.UNSUPPORTED_CAPABILITY,
        )


if __name__ == "__main__":
    unittest.main()
