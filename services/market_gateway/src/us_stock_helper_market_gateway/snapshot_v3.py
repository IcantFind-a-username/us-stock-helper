from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .errors import ErrorCode, GatewayError
from .symbols import from_moomoo_code, to_moomoo_code
from .time_utils import iso_z, parse_aware, require_utc


SECTION_NAMES = (
    "quote",
    "candles",
    "technical",
    "currentSessionFlow",
    "holdings",
    "fundamentals",
    "marketContext",
    "news",
    "forecastDecision",
)

REQUESTED_SECTIONS = (
    "quote",
    "candles",
    "technical",
    "currentSessionFlow",
    "holdings",
)

_UNREQUESTED_SECTIONS = SECTION_NAMES[len(REQUESTED_SECTIONS) :]
_INTERVALS = {"1m", "5m", "15m", "30m", "60m", "day", "week"}
_HOLDINGS_SOURCE = "moomoo-delayed-institutional-disclosure"
_HOLDINGS_PERIOD = re.compile(r"^\d{4}/Q[1-4]$")
_AGGREGATE_PERCENT_WARNING = (
    "供应商返回的聚合持仓比例超过 100%，不能按唯一股份占比直接解释"
)
_REQUIRED_HOLDING_FIELDS = (
    "period",
    "reported_at",
    "available_at",
    "institution_count",
    "institution_count_change",
    "shares_held",
    "shares_held_change",
    "holding_percent",
    "holding_percent_change",
    "source",
)
_HOLDING_ANOMALY_REASONS = {
    "MISSING_REQUIRED_FIELD": "机构持仓记录缺少必填字段",
    "INVALID_REPORTING_PERIOD": "机构持仓报告期格式无效",
    "INVALID_NUMERIC_VALUE": "机构持仓数值无效",
    "WRONG_HOLDINGS_SOURCE": "机构持仓来源无效",
    "FUTURE_HOLDINGS_ROW": "机构持仓记录晚于决策截止时间",
    "OUT_OF_ORDER_HOLDINGS_ROW": "机构持仓记录顺序无效",
}


@dataclass(frozen=True, slots=True)
class SnapshotSection:
    availability_status: Literal["live", "delayed", "stale", "unavailable"]
    quality_status: Literal["validated", "partial", "anomalous", "invalid"]
    source: str | None
    as_of: datetime | None
    available_at: datetime | None
    received_at: datetime | None
    data: Any
    error_code: str | None
    reason: str | None
    warnings: tuple[str, ...] = ()
    anomalies: tuple[dict[str, Any], ...] = ()
    method_version: str = "unavailable-v1"


def section_payload(section: SnapshotSection) -> dict[str, Any]:
    """Serialize one complete section envelope without provider side effects."""

    return {
        "availabilityStatus": section.availability_status,
        "qualityStatus": section.quality_status,
        "source": section.source,
        "asOf": _optional_iso_z(section.as_of),
        "availableAt": _optional_iso_z(section.available_at),
        "receivedAt": _optional_iso_z(section.received_at),
        "data": section.data,
        "errorCode": section.error_code,
        "reason": section.reason,
        "warnings": list(section.warnings),
        "anomalies": [dict(anomaly) for anomaly in section.anomalies],
        "methodVersion": section.method_version,
    }


def normalize_holdings_v3(
    items: list[dict[str, Any]],
    cutoff: datetime,
    received_at: datetime,
) -> SnapshotSection:
    """Normalize delayed holdings independently, retaining valid sibling rows."""

    normalized_cutoff = require_utc(cutoff, "decision_cutoff")
    normalized_received_at = require_utc(received_at, "holdings received_at")
    rows: list[dict[str, Any]] = []
    row_times: list[tuple[datetime, datetime]] = []
    anomalies: list[dict[str, Any]] = []
    warnings: list[str] = []
    previous_available_at: datetime | None = None

    for index, item in enumerate(items):
        if not isinstance(item, dict) or any(
            field not in item for field in _REQUIRED_HOLDING_FIELDS
        ):
            anomalies.append(_holding_anomaly(index, "MISSING_REQUIRED_FIELD"))
            continue

        period = item["period"]
        if not isinstance(period, str) or _HOLDINGS_PERIOD.fullmatch(period) is None:
            anomalies.append(_holding_anomaly(index, "INVALID_REPORTING_PERIOD"))
            continue

        if item["source"] != _HOLDINGS_SOURCE:
            anomalies.append(_holding_anomaly(index, "WRONG_HOLDINGS_SOURCE"))
            continue

        try:
            reported_at = parse_aware(item["reported_at"], "holding reported_at")
            available_at = parse_aware(item["available_at"], "holding available_at")
        except (GatewayError, TypeError, ValueError):
            anomalies.append(_holding_anomaly(index, "MISSING_REQUIRED_FIELD"))
            continue

        numbers = _holding_numbers(item)
        if numbers is None:
            anomalies.append(_holding_anomaly(index, "INVALID_NUMERIC_VALUE"))
            continue
        (
            institution_count,
            institution_count_change,
            shares_held,
            shares_held_change,
            holding_percent,
            holding_percent_change,
        ) = numbers

        if institution_count < 0 or shares_held < 0 or holding_percent < 0:
            anomalies.append(_holding_anomaly(index, "INVALID_NUMERIC_VALUE"))
            continue

        if (
            reported_at > normalized_cutoff
            or available_at > normalized_cutoff
            or normalized_received_at > normalized_cutoff
        ):
            anomalies.append(_holding_anomaly(index, "FUTURE_HOLDINGS_ROW"))
            continue

        if (
            reported_at > available_at
            or available_at > normalized_received_at
            or (
                previous_available_at is not None
                and available_at > previous_available_at
            )
        ):
            anomalies.append(_holding_anomaly(index, "OUT_OF_ORDER_HOLDINGS_ROW"))
            continue

        previous_available_at = available_at
        rows.append(
            {
                "period": period,
                "reportedAt": iso_z(reported_at),
                "reportedAtBasis": "reporting-period-end",
                "availableAt": iso_z(available_at),
                "source": _HOLDINGS_SOURCE,
                "institutionCount": int(institution_count),
                "institutionCountChange": int(institution_count_change),
                "sharesHeld": shares_held,
                "sharesHeldChange": shares_held_change,
                "holdingPercent": holding_percent,
                "holdingPercentChange": holding_percent_change,
            }
        )
        row_times.append((reported_at, available_at))

        if holding_percent > 100:
            if not warnings:
                warnings.append(_AGGREGATE_PERCENT_WARNING)
            anomalies.append(
                {
                    "rowIndex": index,
                    "code": "AGGREGATE_PERCENT_ABOVE_100",
                    "reason": _AGGREGATE_PERCENT_WARNING,
                }
            )

    if rows:
        return SnapshotSection(
            availability_status="delayed",
            quality_status="anomalous" if anomalies else "validated",
            source=_HOLDINGS_SOURCE,
            as_of=row_times[0][0],
            available_at=row_times[0][1],
            received_at=normalized_received_at,
            data=rows,
            error_code=None,
            reason=None,
            warnings=tuple(warnings),
            anomalies=tuple(anomalies),
            method_version="reported-holdings-v2-anomaly-aware",
        )

    error_code = anomalies[0]["code"] if anomalies else "HOLDINGS_UNAVAILABLE"
    reason = anomalies[0]["reason"] if anomalies else "机构持仓数据不可用"
    return SnapshotSection(
        availability_status="unavailable",
        quality_status="invalid",
        source=_HOLDINGS_SOURCE,
        as_of=None,
        available_at=None,
        received_at=normalized_received_at,
        data=[],
        error_code=error_code,
        reason=reason,
        warnings=tuple(warnings),
        anomalies=tuple(anomalies),
        method_version="reported-holdings-v2-anomaly-aware",
    )


def assemble_stock_snapshot_v3(
    symbol: str,
    interval: str,
    count: int,
    decision_cutoff: datetime,
    sections: Mapping[str, SnapshotSection],
) -> dict[str, Any]:
    """Assemble complete v3 envelopes from already-collected pure sections."""

    normalized_symbol = from_moomoo_code(to_moomoo_code(symbol))
    if interval not in _INTERVALS:
        raise GatewayError(ErrorCode.INVALID_ARGUMENT, "Unsupported candle interval")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 1000:
        raise GatewayError(
            ErrorCode.INVALID_ARGUMENT,
            "Candle count must be between 1 and 1000",
        )
    if not isinstance(decision_cutoff, datetime):
        raise GatewayError(
            ErrorCode.INVALID_ARGUMENT,
            "Decision cutoff must include timezone information",
        )
    try:
        cutoff = require_utc(decision_cutoff, "decision_cutoff")
    except GatewayError as error:
        raise GatewayError(
            ErrorCode.INVALID_ARGUMENT,
            "Decision cutoff must include timezone information",
        ) from error

    complete_sections: dict[str, SnapshotSection] = {}
    for name in SECTION_NAMES:
        if name in _UNREQUESTED_SECTIONS:
            complete_sections[name] = _unrequested_section()
            continue
        candidate = sections.get(name)
        if candidate is None:
            complete_sections[name] = _missing_section()
        elif not isinstance(candidate, SnapshotSection):
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                f"Snapshot section {name} has an invalid contract",
            )
        else:
            complete_sections[name] = candidate

    quote_usable = _quote_is_usable(complete_sections["quote"])
    candles_usable = _candles_are_usable(complete_sections["candles"])
    if not quote_usable and not candles_usable:
        status = "unavailable"
    elif all(
        complete_sections[name].availability_status in {"live", "delayed"}
        and complete_sections[name].quality_status == "validated"
        for name in REQUESTED_SECTIONS
    ):
        status = "live"
    else:
        status = "partial"

    return {
        "schemaVersion": "3",
        "status": status,
        "symbol": normalized_symbol,
        "interval": interval,
        "count": count,
        "decisionCutoff": iso_z(cutoff),
        "requestedSections": list(REQUESTED_SECTIONS),
        "sections": {
            name: section_payload(complete_sections[name]) for name in SECTION_NAMES
        },
    }


def _optional_iso_z(value: datetime | None) -> str | None:
    return iso_z(value) if value is not None else None


def _holding_anomaly(index: int, code: str) -> dict[str, Any]:
    return {
        "rowIndex": index,
        "code": code,
        "reason": _HOLDING_ANOMALY_REASONS[code],
    }


def _holding_numbers(item: dict[str, Any]) -> tuple[float, ...] | None:
    fields = (
        "institution_count",
        "institution_count_change",
        "shares_held",
        "shares_held_change",
        "holding_percent",
        "holding_percent_change",
    )
    values: list[float] = []
    for field in fields:
        value = item[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            number = float(value)
        except OverflowError:
            return None
        if not math.isfinite(number):
            return None
        values.append(number)
    return tuple(values)


def _missing_section() -> SnapshotSection:
    return SnapshotSection(
        availability_status="unavailable",
        quality_status="invalid",
        source=None,
        as_of=None,
        available_at=None,
        received_at=None,
        data=None,
        error_code="SECTION_UNAVAILABLE",
        reason="此数据切片不可用",
    )


def _unrequested_section() -> SnapshotSection:
    return SnapshotSection(
        availability_status="unavailable",
        quality_status="invalid",
        source=None,
        as_of=None,
        available_at=None,
        received_at=None,
        data=None,
        error_code="NOT_REQUESTED",
        reason="此切片未请求该数据",
    )


def _quote_is_usable(section: SnapshotSection) -> bool:
    if (
        section.availability_status not in {"live", "delayed"}
        or section.quality_status != "validated"
        or not isinstance(section.data, Mapping)
    ):
        return False
    price = section.data.get("price")
    return (
        not isinstance(price, bool)
        and isinstance(price, (int, float))
        and math.isfinite(float(price))
        and float(price) > 0
    )


def _candles_are_usable(section: SnapshotSection) -> bool:
    if (
        section.availability_status not in {"live", "delayed"}
        or section.quality_status != "validated"
        or not isinstance(section.data, Mapping)
    ):
        return False
    candles = section.data.get("candles")
    return isinstance(candles, list) and any(
        _completed_candle_is_valid(candle) for candle in candles
    )


def _completed_candle_is_valid(candle: object) -> bool:
    if not isinstance(candle, Mapping) or candle.get("complete") is not True:
        return False
    try:
        parse_aware(candle["timestamp"], "candle timestamp")
    except (KeyError, GatewayError):
        return False

    numbers: list[float] = []
    for field in ("open", "high", "low", "close", "volume"):
        value = candle.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            number = float(value)
        except OverflowError:
            return False
        if not math.isfinite(number):
            return False
        numbers.append(number)

    open_price, high, low, close, volume = numbers
    return (
        min(open_price, high, low, close) > 0
        and volume >= 0
        and high >= max(open_price, close)
        and low <= min(open_price, close)
        and high >= low
    )
