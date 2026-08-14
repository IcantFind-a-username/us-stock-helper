from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from us_stock_helper_market_gateway.errors import GatewayError
from us_stock_helper_market_gateway.snapshot_v3 import (
    REQUESTED_SECTIONS,
    SECTION_NAMES,
    SnapshotSection,
    assemble_stock_snapshot_v3,
    normalize_holdings_v3,
    section_payload,
)


CUTOFF = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
RECEIVED_AT = CUTOFF - timedelta(seconds=1)
HOLDINGS_SOURCE = "moomoo-delayed-institutional-disclosure"
AGGREGATE_WARNING = "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释"

ANOMALY_REASONS = {
    "MISSING_REQUIRED_FIELD": "机构持仓记录缺少必填字段",
    "INVALID_REPORTING_PERIOD": "机构持仓报告期格式无效",
    "INVALID_NUMERIC_VALUE": "机构持仓数值无效",
    "WRONG_HOLDINGS_SOURCE": "机构持仓来源无效",
    "FUTURE_HOLDINGS_ROW": "机构持仓记录晚于决策截止时间",
    "OUT_OF_ORDER_HOLDINGS_ROW": "机构持仓记录顺序无效",
}


def holding_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "period": "2026/Q1",
        "reported_at": "2026-03-31T20:00:00+00:00",
        "available_at": "2026-05-16T14:00:00+00:00",
        "institution_count": 863,
        "institution_count_change": 12,
        "shares_held": 4_192_178_205,
        "shares_held_change": -3_105_448,
        "holding_percent": 46.474,
        "holding_percent_change": 0.03,
        "source": HOLDINGS_SOURCE,
    }
    row.update(overrides)
    return row


def section(
    data: Any,
    *,
    availability: str = "live",
    quality: str = "validated",
    source: str = "moomoo",
) -> SnapshotSection:
    return SnapshotSection(
        availability_status=availability,  # type: ignore[arg-type]
        quality_status=quality,  # type: ignore[arg-type]
        source=source,
        as_of=CUTOFF - timedelta(minutes=1),
        available_at=CUTOFF - timedelta(seconds=2),
        received_at=RECEIVED_AT,
        data=data,
        error_code=None,
        reason=None,
        method_version="test-v1",
    )


def unavailable_section() -> SnapshotSection:
    return SnapshotSection(
        availability_status="unavailable",
        quality_status="invalid",
        source=None,
        as_of=None,
        available_at=None,
        received_at=None,
        data=None,
        error_code="TEST_UNAVAILABLE",
        reason="测试分区不可用",
    )


def completed_candles() -> dict[str, Any]:
    return {
        "candles": [
            {
                "timestamp": "2026-08-13T20:00:00Z",
                "complete": True,
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.0,
                "volume": 1_000.0,
                "qualityStatus": "live",
            }
        ],
        "priceAdjustment": "forward-adjusted",
    }


def validated_requested_sections() -> dict[str, SnapshotSection]:
    return {
        "quote": section({"price": 101.25}),
        "candles": section(completed_candles()),
        "technical": section({"indicators": {}}),
        "currentSessionFlow": section([]),
        "holdings": section([], availability="delayed"),
    }


class SnapshotSectionContractTests(unittest.TestCase):
    def test_section_payload_emits_every_envelope_field_and_utc_timestamps(
        self,
    ) -> None:
        value = SnapshotSection(
            availability_status="delayed",
            quality_status="anomalous",
            source=HOLDINGS_SOURCE,
            as_of=datetime(2026, 3, 31, 16, 0, tzinfo=timezone(timedelta(hours=-4))),
            available_at=datetime(
                2026, 5, 16, 22, 0, tzinfo=timezone(timedelta(hours=8))
            ),
            received_at=RECEIVED_AT,
            data=[{"holdingPercent": 345.937}],
            error_code=None,
            reason=None,
            warnings=(AGGREGATE_WARNING,),
            anomalies=(
                {
                    "rowIndex": 0,
                    "code": "AGGREGATE_PERCENT_ABOVE_100",
                    "reason": AGGREGATE_WARNING,
                },
            ),
            method_version="reported-holdings-v2-anomaly-aware",
        )

        payload = section_payload(value)

        self.assertEqual(
            set(payload),
            {
                "availabilityStatus",
                "qualityStatus",
                "source",
                "asOf",
                "availableAt",
                "receivedAt",
                "data",
                "errorCode",
                "reason",
                "warnings",
                "anomalies",
                "methodVersion",
            },
        )
        self.assertEqual(payload["asOf"], "2026-03-31T20:00:00Z")
        self.assertEqual(payload["availableAt"], "2026-05-16T14:00:00Z")
        self.assertEqual(payload["receivedAt"], "2026-08-14T11:59:59Z")
        self.assertEqual(payload["warnings"], [AGGREGATE_WARNING])
        self.assertEqual(payload["anomalies"][0]["code"], "AGGREGATE_PERCENT_ABOVE_100")

    def test_unavailable_section_still_emits_all_twelve_fields(self) -> None:
        payload = section_payload(unavailable_section())

        self.assertEqual(len(payload), 12)
        self.assertIsNone(payload["asOf"])
        self.assertIsNone(payload["availableAt"])
        self.assertIsNone(payload["receivedAt"])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["anomalies"], [])


class HoldingsV3Tests(unittest.TestCase):
    def test_aggregate_percentage_above_100_is_retained_and_anomalous(self) -> None:
        result = normalize_holdings_v3(
            [holding_row(holding_percent=345.937)], CUTOFF, RECEIVED_AT
        )

        self.assertEqual(result.availability_status, "delayed")
        self.assertEqual(result.quality_status, "anomalous")
        self.assertEqual(result.data[0]["holdingPercent"], 345.937)
        self.assertEqual(result.warnings, (AGGREGATE_WARNING,))
        self.assertEqual(
            result.anomalies,
            (
                {
                    "rowIndex": 0,
                    "code": "AGGREGATE_PERCENT_ABOVE_100",
                    "reason": AGGREGATE_WARNING,
                },
            ),
        )
        self.assertEqual(result.method_version, "reported-holdings-v2-anomaly-aware")

    def test_live_symbols_with_aggregate_percentages_above_100_are_retained(
        self,
    ) -> None:
        cases = {
            "CRCL": 126.431,
            "AVGO": 345.937,
            "GRRR": 118.775,
            "SMTC": 164.208,
            "LULU": 112.604,
            "PTON": 137.519,
            "ETSY": 144.882,
            "GPCR": 109.317,
        }

        for symbol, percentage in cases.items():
            with self.subTest(symbol=symbol):
                result = normalize_holdings_v3(
                    [holding_row(holding_percent=percentage)],
                    CUTOFF,
                    RECEIVED_AT,
                )

                self.assertEqual(result.data[0]["holdingPercent"], percentage)
                self.assertEqual(result.quality_status, "anomalous")
                self.assertEqual(result.warnings, (AGGREGATE_WARNING,))

    def test_valid_row_uses_the_v3_holding_shape(self) -> None:
        result = normalize_holdings_v3([holding_row()], CUTOFF, RECEIVED_AT)

        self.assertEqual(result.availability_status, "delayed")
        self.assertEqual(result.quality_status, "validated")
        self.assertEqual(result.source, HOLDINGS_SOURCE)
        self.assertEqual(
            result.as_of, datetime(2026, 3, 31, 20, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            result.available_at,
            datetime(2026, 5, 16, 14, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(result.received_at, RECEIVED_AT)
        self.assertEqual(
            result.data,
            [
                {
                    "period": "2026/Q1",
                    "reportedAt": "2026-03-31T20:00:00Z",
                    "reportedAtBasis": "reporting-period-end",
                    "availableAt": "2026-05-16T14:00:00Z",
                    "source": HOLDINGS_SOURCE,
                    "institutionCount": 863,
                    "institutionCountChange": 12,
                    "sharesHeld": 4_192_178_205.0,
                    "sharesHeldChange": -3_105_448.0,
                    "holdingPercent": 46.474,
                    "holdingPercentChange": 0.03,
                }
            ],
        )

    def test_invalid_rows_are_excluded_without_discarding_a_valid_sibling(
        self,
    ) -> None:
        missing = holding_row()
        del missing["shares_held"]
        cases: list[tuple[str, dict[str, Any], str]] = [
            ("missing", missing, "MISSING_REQUIRED_FIELD"),
            (
                "negative",
                holding_row(holding_percent=-0.01),
                "INVALID_NUMERIC_VALUE",
            ),
            (
                "nan",
                holding_row(shares_held=math.nan),
                "INVALID_NUMERIC_VALUE",
            ),
            (
                "infinite signed change",
                holding_row(holding_percent_change=math.inf),
                "INVALID_NUMERIC_VALUE",
            ),
            (
                "future",
                holding_row(available_at="2026-08-14T12:00:01+00:00"),
                "FUTURE_HOLDINGS_ROW",
            ),
            (
                "wrong source",
                holding_row(source="provider-error: permission denied"),
                "WRONG_HOLDINGS_SOURCE",
            ),
            (
                "malformed period",
                holding_row(period="2026 Q1"),
                "INVALID_REPORTING_PERIOD",
            ),
            (
                "out of order",
                holding_row(available_at="2026-06-16T14:00:00+00:00"),
                "OUT_OF_ORDER_HOLDINGS_ROW",
            ),
        ]

        for label, bad_row, code in cases:
            with self.subTest(label=label):
                result = normalize_holdings_v3(
                    [holding_row(), bad_row], CUTOFF, RECEIVED_AT
                )

                self.assertEqual(len(result.data), 1)
                self.assertEqual(result.data[0]["holdingPercent"], 46.474)
                self.assertEqual(result.availability_status, "delayed")
                self.assertEqual(result.quality_status, "anomalous")
                self.assertEqual(
                    result.anomalies,
                    (
                        {
                            "rowIndex": 1,
                            "code": code,
                            "reason": ANOMALY_REASONS[code],
                        },
                    ),
                )
                self.assertNotIn("permission denied", repr(result.anomalies))

    def test_period_grammar_accepts_only_four_digit_year_and_quarter(self) -> None:
        for period in ("", "Q1/2026", "2026/Q0", "2026/Q5", "26/Q1", "2026/Q1x"):
            with self.subTest(period=period):
                result = normalize_holdings_v3(
                    [holding_row(period=period)], CUTOFF, RECEIVED_AT
                )

                self.assertEqual(result.data, [])
                self.assertEqual(
                    result.anomalies[0]["code"], "INVALID_REPORTING_PERIOD"
                )

        valid = normalize_holdings_v3(
            [holding_row(period="2026/Q1")], CUTOFF, RECEIVED_AT
        )
        self.assertEqual(valid.data[0]["period"], "2026/Q1")

    def test_all_invalid_rows_make_holdings_unavailable_and_preserve_anomalies(
        self,
    ) -> None:
        result = normalize_holdings_v3(
            [holding_row(holding_percent=-1.0)], CUTOFF, RECEIVED_AT
        )

        self.assertEqual(result.data, [])
        self.assertEqual(result.availability_status, "unavailable")
        self.assertEqual(result.quality_status, "invalid")
        self.assertEqual(result.anomalies[0]["code"], "INVALID_NUMERIC_VALUE")

    def test_overflowing_numeric_row_is_excluded_without_losing_sibling(self) -> None:
        result = normalize_holdings_v3(
            [holding_row(), holding_row(shares_held=10**10000)],
            CUTOFF,
            RECEIVED_AT,
        )

        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.data[0]["holdingPercent"], 46.474)
        self.assertEqual(result.availability_status, "delayed")
        self.assertEqual(result.quality_status, "anomalous")
        self.assertEqual(
            result.anomalies,
            (
                {
                    "rowIndex": 1,
                    "code": "INVALID_NUMERIC_VALUE",
                    "reason": ANOMALY_REASONS["INVALID_NUMERIC_VALUE"],
                },
            ),
        )

    def test_batch_received_after_cutoff_excludes_each_row_as_future(self) -> None:
        result = normalize_holdings_v3(
            [holding_row()], CUTOFF, CUTOFF + timedelta(microseconds=1)
        )

        self.assertEqual(result.data, [])
        self.assertEqual(result.availability_status, "unavailable")
        self.assertEqual(result.quality_status, "invalid")
        self.assertEqual(result.anomalies[0]["code"], "FUTURE_HOLDINGS_ROW")


class StockSnapshotV3AssemblyTests(unittest.TestCase):
    def test_assembly_emits_exact_top_level_and_section_contract(self) -> None:
        payload = assemble_stock_snapshot_v3(
            symbol="AVGO",
            interval="day",
            count=200,
            decision_cutoff=CUTOFF,
            sections=validated_requested_sections(),
        )

        self.assertEqual(
            set(payload),
            {
                "schemaVersion",
                "status",
                "symbol",
                "interval",
                "count",
                "decisionCutoff",
                "requestedSections",
                "sections",
            },
        )
        self.assertEqual(payload["schemaVersion"], "3")
        self.assertEqual(payload["status"], "live")
        self.assertEqual(payload["symbol"], "AVGO")
        self.assertEqual(payload["interval"], "day")
        self.assertEqual(payload["count"], 200)
        self.assertEqual(payload["decisionCutoff"], "2026-08-14T12:00:00Z")
        self.assertEqual(payload["requestedSections"], list(REQUESTED_SECTIONS))
        self.assertEqual(tuple(payload["sections"]), SECTION_NAMES)
        self.assertTrue(
            all(len(envelope) == 12 for envelope in payload["sections"].values())
        )

    def test_unrequested_sections_are_explicit_and_do_not_prevent_live(self) -> None:
        payload = assemble_stock_snapshot_v3(
            "AVGO", "day", 200, CUTOFF, validated_requested_sections()
        )

        self.assertEqual(payload["status"], "live")
        for name in ("fundamentals", "marketContext", "news", "forecastDecision"):
            with self.subTest(name=name):
                envelope = payload["sections"][name]
                self.assertEqual(envelope["availabilityStatus"], "unavailable")
                self.assertEqual(envelope["qualityStatus"], "invalid")
                self.assertEqual(envelope["errorCode"], "NOT_REQUESTED")
                self.assertEqual(envelope["reason"], "此切片未请求该数据")

    def test_anomalous_holdings_make_snapshot_partial_without_losing_price(
        self,
    ) -> None:
        sections = validated_requested_sections()
        sections["holdings"] = normalize_holdings_v3(
            [holding_row(holding_percent=345.937)], CUTOFF, RECEIVED_AT
        )

        payload = assemble_stock_snapshot_v3("AVGO", "day", 200, CUTOFF, sections)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["sections"]["candles"]["qualityStatus"], "validated")
        self.assertEqual(payload["sections"]["holdings"]["qualityStatus"], "anomalous")
        self.assertEqual(
            payload["sections"]["holdings"]["data"][0]["holdingPercent"],
            345.937,
        )

    def test_quote_only_and_candles_only_snapshots_are_partial_and_usable(
        self,
    ) -> None:
        quote_only = validated_requested_sections()
        quote_only["candles"] = unavailable_section()
        candles_only = validated_requested_sections()
        candles_only["quote"] = unavailable_section()

        for label, sections in (("quote", quote_only), ("candles", candles_only)):
            with self.subTest(label=label):
                payload = assemble_stock_snapshot_v3(
                    "AVGO", "day", 200, CUTOFF, sections
                )

                self.assertEqual(payload["status"], "partial")

    def test_snapshot_is_unavailable_without_a_usable_price_section(self) -> None:
        sections = validated_requested_sections()
        sections["quote"] = unavailable_section()
        sections["candles"] = unavailable_section()

        payload = assemble_stock_snapshot_v3("AVGO", "day", 200, CUTOFF, sections)

        self.assertEqual(payload["status"], "unavailable")

    def test_empty_validated_candle_array_does_not_satisfy_price_minimum(
        self,
    ) -> None:
        sections = validated_requested_sections()
        sections["quote"] = unavailable_section()
        sections["candles"] = section(
            {"candles": [], "priceAdjustment": "forward-adjusted"}
        )

        payload = assemble_stock_snapshot_v3("AVGO", "day", 200, CUTOFF, sections)

        self.assertEqual(payload["status"], "unavailable")

    def test_incomplete_candle_shape_does_not_satisfy_price_minimum(self) -> None:
        sections = validated_requested_sections()
        sections["quote"] = unavailable_section()
        sections["candles"] = section(
            {
                "candles": [{"complete": True}],
                "priceAdjustment": "forward-adjusted",
            }
        )

        payload = assemble_stock_snapshot_v3("AVGO", "day", 200, CUTOFF, sections)

        self.assertEqual(payload["status"], "unavailable")

    def test_non_positive_or_non_finite_quote_is_not_usable(self) -> None:
        for price in (None, 0, -1, math.nan, math.inf):
            with self.subTest(price=price):
                sections = validated_requested_sections()
                sections["quote"] = section({"price": price})
                sections["candles"] = unavailable_section()

                payload = assemble_stock_snapshot_v3(
                    "AVGO", "day", 200, CUTOFF, sections
                )

                self.assertEqual(payload["status"], "unavailable")

    def test_missing_requested_sections_become_explicit_unavailable_envelopes(
        self,
    ) -> None:
        payload = assemble_stock_snapshot_v3(
            "AVGO", "day", 200, CUTOFF, {"quote": section({"price": 101.25})}
        )

        self.assertEqual(payload["status"], "partial")
        for name in ("candles", "technical", "currentSessionFlow", "holdings"):
            with self.subTest(name=name):
                envelope = payload["sections"][name]
                self.assertEqual(envelope["availabilityStatus"], "unavailable")
                self.assertEqual(envelope["qualityStatus"], "invalid")

    def test_invalid_count_is_rejected_before_assembly(self) -> None:
        for count in (True, 200.0, 0, -1, 1001):
            with self.subTest(count=count):
                with self.assertRaises(GatewayError):
                    assemble_stock_snapshot_v3(
                        "AVGO",
                        "day",
                        count,  # type: ignore[arg-type]
                        CUTOFF,
                        validated_requested_sections(),
                    )

    def test_invalid_identity_or_cutoff_is_rejected_before_assembly(self) -> None:
        cases = (
            ("", "day", CUTOFF),
            ("AVGO", "hour", CUTOFF),
            ("AVGO", "day", CUTOFF.replace(tzinfo=None)),
        )

        for symbol, interval, cutoff in cases:
            with self.subTest(symbol=symbol, interval=interval, cutoff=cutoff):
                with self.assertRaises(GatewayError):
                    assemble_stock_snapshot_v3(
                        symbol,
                        interval,
                        200,
                        cutoff,
                        validated_requested_sections(),
                    )

    def test_non_datetime_cutoff_raises_top_level_gateway_error(self) -> None:
        with self.assertRaises(GatewayError) as raised:
            assemble_stock_snapshot_v3(
                "AVGO",
                "day",
                200,
                "2026-08-14T12:00:00Z",  # type: ignore[arg-type]
                validated_requested_sections(),
            )

        self.assertEqual(raised.exception.code.value, "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
