from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from us_stock_helper_market_gateway.errors import ErrorCode, GatewayError
from us_stock_helper_market_gateway.models import ProviderBatch, SessionHealth
from us_stock_helper_market_gateway.service import MarketGatewayService
from us_stock_helper_market_gateway.snapshot import assemble_stock_snapshot


NOW = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)


class SnapshotProvider:
    def __init__(self) -> None:
        self.health_calls = 0
        self.quote_result = ProviderBatch(
            source="moomoo",
            received_at=NOW,
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "change_percent": 2.7,
                    "available_at": "2026-07-25T03:59:00+00:00",
                }
            ],
        )
        self.candle_result = ProviderBatch(
            source="moomoo",
            received_at=NOW,
            items=self._candles(),
        )
        self.flow_result = ProviderBatch(
            source="moomoo",
            received_at=NOW,
            items=self._flow_rows(),
        )
        self.holding_result = ProviderBatch(
            source="moomoo",
            received_at=NOW,
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
        self.health_calls += 1
        return SessionHealth("healthy", NOW - timedelta(seconds=2), "moomoo")

    def quotes(self, codes: list[str]) -> ProviderBatch:
        return self.quote_result

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        return self.candle_result

    def capital_flow(self, code: str) -> ProviderBatch:
        return self.flow_result

    def institutional_holdings(self, code: str) -> ProviderBatch:
        return self.holding_result

    @staticmethod
    def _candles() -> list[dict[str, object]]:
        first_close = NOW - timedelta(minutes=95)
        items: list[dict[str, object]] = []
        for index in range(20):
            closed_at = first_close + timedelta(minutes=5 * index)
            close = float(index + 1)
            items.append(
                {
                    "code": "US.NVDA",
                    "timeframe": "5m",
                    "timestamp": closed_at.isoformat(),
                    "available_at": closed_at.isoformat(),
                    "complete": True,
                    "open": close - 0.25,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "volume": 1_000 + index,
                }
            )
        items.append(
            {
                "code": "US.NVDA",
                "timeframe": "5m",
                "timestamp": NOW.isoformat(),
                "available_at": NOW.isoformat(),
                "complete": False,
                "open": 20.0,
                "high": 21.0,
                "low": 19.0,
                "close": 20.5,
                "volume": 500,
            }
        )
        return items

    @staticmethod
    def _flow_rows() -> list[dict[str, object]]:
        first = NOW - timedelta(minutes=100)
        rows: list[dict[str, object]] = []
        for index in range(101):
            timestamp = first + timedelta(minutes=index)
            rows.append(
                {
                    "code": "US.NVDA",
                    "timestamp": timestamp.isoformat(),
                    "available_at": timestamp.isoformat(),
                    "session": "provider-session-1",
                    "total_net": float(index * 10),
                    "super_net": float(index * 4),
                    "big_net": float(index * 3),
                    "mid_net": float(index * 2),
                    "small_net": float(index),
                }
            )
        return rows


class StockSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = SnapshotProvider()
        self.service = MarketGatewayService(
            self.provider,
            clock=lambda: NOW,
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

    def test_snapshot_uses_one_cutoff_for_completed_market_data(self) -> None:
        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(self.provider.health_calls, 1)
        self.assertEqual(response["schemaVersion"], "2")
        self.assertEqual(response["sourceStatus"], "live")
        self.assertEqual(response["symbol"], "NVDA")
        self.assertEqual(response["interval"], "5m")
        self.assertEqual(len(response["completedCandles"]), 20)
        self.assertTrue(
            all(candle["complete"] for candle in response["completedCandles"])
        )
        self.assertTrue(
            all(
                child["availableAt"] <= response["decisionCutoff"]
                for child in [
                    response["quote"],
                    *response["completedCandles"],
                    *response["participationBars"],
                    *response["institutionalHoldings"],
                    *response["indicators"].values(),
                ]
            )
        )
        self.assertEqual(
            [bar["closedAt"] for bar in response["participationBars"]],
            [candle["timestamp"] for candle in response["completedCandles"]],
        )
        self.assertEqual(response["indicators"]["ma5"]["value"], 18.0)
        self.assertEqual(response["indicators"]["rsi"]["value"], 100.0)
        self.assertEqual(response["indicators"]["macd"]["qualityStatus"], "unavailable")
        self.assertEqual(response["indicators"]["magicNine"]["count"], 9)
        self.assertTrue(response["indicators"]["magicNine"]["completed"])
        self.assertEqual(
            response["institutionalHoldings"][0]["qualityStatus"], "delayed"
        )

    def test_later_flow_receipt_remains_usable_until_operation_completion(self) -> None:
        self.provider.quote_result = ProviderBatch(
            "moomoo", NOW + timedelta(seconds=1), self.provider.quote_result.items
        )
        self.provider.candle_result = ProviderBatch(
            "moomoo", NOW + timedelta(seconds=2), self.provider.candle_result.items
        )
        self.provider.flow_result = ProviderBatch(
            "moomoo",
            NOW + timedelta(seconds=3),
            [
                {**item, "available_at": (NOW + timedelta(seconds=3)).isoformat()}
                for item in self.provider.flow_result.items
            ],
        )
        self.provider.holding_result = ProviderBatch(
            "moomoo", NOW + timedelta(seconds=4), self.provider.holding_result.items
        )
        moments = iter([NOW, NOW, NOW + timedelta(seconds=5)])
        service = MarketGatewayService(self.provider, clock=lambda: next(moments))

        response = service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["decisionCutoff"], "2026-07-25T04:00:05Z")
        self.assertTrue(
            all(bar["qualityStatus"] == "live" for bar in response["participationBars"])
        )

    def test_day_and_week_vendor_labels_normalize_without_accepting_intraday(self) -> None:
        for vendor_label, interval in (("K_DAY", "day"), ("K_WEEK", "week")):
            with self.subTest(vendor_label=vendor_label):
                response = assemble_stock_snapshot(
                    symbol="NVDA",
                    interval=interval,
                    decision_cutoff=NOW,
                    quote_items=[
                        {
                            "code": "US.NVDA",
                            "price": 173.4,
                            "changePercent": 2.7,
                            "availableAt": NOW.isoformat(),
                        }
                    ],
                    candle_items=[
                        {
                            "code": "US.NVDA",
                            "timeframe": vendor_label,
                            "timestamp": NOW.isoformat(),
                            "availableAt": NOW.isoformat(),
                            "open": 172.0,
                            "high": 174.0,
                            "low": 171.5,
                            "close": 173.4,
                            "volume": 1_000.0,
                        }
                    ],
                    flow_items=[],
                    holding_items=[],
                )
                self.assertEqual(response["interval"], interval)
                self.assertEqual(len(response["completedCandles"]), 1)

        with self.assertRaisesRegex(ValueError, "interval"):
            assemble_stock_snapshot(
                symbol="NVDA",
                interval="day",
                decision_cutoff=NOW,
                quote_items=[
                    {
                        "code": "US.NVDA",
                        "price": 173.4,
                        "changePercent": 2.7,
                        "availableAt": NOW.isoformat(),
                    }
                ],
                candle_items=[
                    {
                        "code": "US.NVDA",
                        "timeframe": "5m",
                        "timestamp": NOW.isoformat(),
                        "availableAt": NOW.isoformat(),
                        "open": 172.0,
                        "high": 174.0,
                        "low": 171.5,
                        "close": 173.4,
                        "volume": 1_000.0,
                    }
                ],
                flow_items=[],
                holding_items=[],
            )

    def test_invalid_flow_makes_every_participation_bar_unavailable(self) -> None:
        cases = {
            "duplicate": lambda items: items.__setitem__(
                10,
                {**items[10], "timestamp": items[9]["timestamp"]},
            ),
            "out-of-order": lambda items: items.__setitem__(
                10,
                {**items[10], "timestamp": items[8]["timestamp"]},
            ),
            "future": lambda items: items.__setitem__(
                10,
                {
                    **items[10],
                    "available_at": (NOW + timedelta(minutes=1)).isoformat(),
                },
            ),
        }
        for name, invalidate in cases.items():
            with self.subTest(name=name):
                self.setUp()
                invalidate(self.provider.flow_result.items)

                response = self.service.stock_snapshot("NVDA", "5m", 200)

                self.assertEqual(response["sourceStatus"], "live")
                self.assertTrue(response["warnings"])
                self.assertTrue(
                    all(
                        bar["qualityStatus"] == "unavailable"
                        and bar["mainShare"] is None
                        and bar["retailShare"] is None
                        for bar in response["participationBars"]
                    )
                )
                self.assertNotIn(name, repr(response).lower())

    def test_mismatched_flow_symbol_rejects_the_entire_flow_batch(self) -> None:
        self.provider.flow_result.items[10]["code"] = "US.TSLA"

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["sourceStatus"], "live")
        self.assertTrue(response["warnings"])
        self.assertTrue(
            all(
                bar["qualityStatus"] == "unavailable"
                and bar["mainShare"] is None
                and bar["retailShare"] is None
                for bar in response["participationBars"]
            )
        )

    def test_provider_session_metadata_prevents_cross_session_differencing(self) -> None:
        self.provider.flow_result.items[10]["session"] = "provider-session-2"

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        affected = response["participationBars"][1]
        self.assertEqual(affected["qualityStatus"], "unavailable")
        self.assertIn("session", affected["missingReason"])

    def test_mid_operation_opend_offline_error_is_preserved(self) -> None:
        def fail(code: str, timeframe: str, count: int) -> ProviderBatch:
            raise GatewayError(
                ErrorCode.OPEND_OFFLINE,
                "moomoo OpenD is offline",
                retriable=True,
            )

        self.provider.candles = fail  # type: ignore[method-assign]

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["sourceStatus"], "unavailable")
        self.assertEqual(response["error"]["code"], "OPEND_OFFLINE")
        self.assertTrue(response["error"]["retriable"])

    def test_provider_failure_is_sanitized(self) -> None:
        def fail(code: str) -> ProviderBatch:
            raise RuntimeError("account=123 password=secret")

        self.provider.candles = fail  # type: ignore[method-assign]

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["sourceStatus"], "unavailable")
        self.assertEqual(response["error"]["code"], "PROVIDER_ERROR")
        self.assertNotIn("account=123", repr(response))
        self.assertNotIn("secret", repr(response))


if __name__ == "__main__":
    unittest.main()
