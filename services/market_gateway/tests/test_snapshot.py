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
                    "received_at": NOW.isoformat(),
                    "price_adjustment": "forward-adjusted",
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
                "received_at": NOW.isoformat(),
                "price_adjustment": "forward-adjusted",
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
        # Twenty rising closes complete one nine at index 12; counting then
        # restarts, so the current run is seven bars long.
        magic_nine = response["indicators"]["magicNine"]
        self.assertEqual(magic_nine["count"], 7)
        self.assertFalse(magic_nine["completed"])
        self.assertEqual(magic_nine["direction"], "bearish")
        self.assertEqual(magic_nine["methodVersion"], "td-setup-close-4-v2")
        self.assertEqual(
            magic_nine["lastCompleted"],
            {
                "direction": "bearish",
                "confirmedAtIndex": 12,
                "perfected": True,
                "barsSince": 7,
            },
        )
        self.assertEqual(
            response["institutionalHoldings"][0]["qualityStatus"], "delayed"
        )

    def test_snapshot_discloses_that_prices_are_rewritten_by_corporate_actions(
        self,
    ) -> None:
        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["priceAdjustment"], "forward-adjusted")
        self.assertTrue(
            any("复权" in warning or "adjust" in warning.lower() for warning in response["warnings"])
        )
        for candle in response["completedCandles"]:
            self.assertEqual(candle["priceAdjustment"], "forward-adjusted")

    def test_candles_carry_both_publication_and_receipt_times(self) -> None:
        response = self.service.stock_snapshot("NVDA", "5m", 200)

        for candle in response["completedCandles"]:
            self.assertLessEqual(candle["availableAt"], candle["receivedAt"])
            self.assertLessEqual(candle["receivedAt"], response["decisionCutoff"])

    def test_participation_names_the_reason_it_could_not_be_built(self) -> None:
        self.provider.flow_result = ProviderBatch(
            "moomoo", self.provider.flow_result.received_at, []
        )

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["sourceStatus"], "live")
        reasons = {bar["missingReason"] for bar in response["participationBars"]}
        self.assertEqual(reasons, {"capital flow unavailable"})

    def test_a_cutoff_violation_is_never_reported_as_missing_data(self) -> None:
        self.provider.flow_result.items[10]["available_at"] = (
            NOW + timedelta(hours=1)
        ).isoformat()

        response = self.service.stock_snapshot("NVDA", "5m", 200)

        # A flow row from the future is a temporal defect, not an absence: the
        # snapshot must fail loudly rather than quietly claim "no data".
        self.assertEqual(response["sourceStatus"], "unavailable")
        self.assertEqual(
            response["error"]["code"], ErrorCode.MALFORMED_PROVIDER_DATA.value
        )

    def test_magic_nine_reports_no_completed_setup_when_none_has_closed(self) -> None:
        self.provider.candle_result = ProviderBatch(
            "moomoo",
            self.provider.candle_result.received_at,
            self.provider.candle_result.items[:8],
        )

        magic_nine = self.service.stock_snapshot("NVDA", "5m", 200)["indicators"][
            "magicNine"
        ]

        self.assertIsNone(magic_nine["lastCompleted"])
        self.assertFalse(magic_nine["completed"])
        self.assertEqual(magic_nine["count"], 4)

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
        }
        # A row available after the cutoff is deliberately absent here: it is a
        # temporal violation, not a structural one, and
        # test_a_cutoff_violation_is_never_reported_as_missing_data requires it
        # to fail the whole snapshot instead of degrading this one section.
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
