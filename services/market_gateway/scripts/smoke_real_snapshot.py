#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SmokeFailure(ValueError):
    pass


_TRADING_CAPABILITY_IDENTIFIERS = {
    "opensectradecontext",
    "unlocktrade",
    "placeorder",
    "modifyorder",
    "cancelorder",
}
_TRADING_STRUCTURE_KEYS = {
    "orders",
    "tradeorders",
    "tradecontext",
    "tradeendpoint",
    "tradingcapability",
}
_SNAPSHOT_STATUSES = {"live", "delayed", "stale", "unavailable", "demo"}
_PROVENANCE_SOURCES = {
    "moomoo",
    "analysis-core",
    "moomoo-delayed-institutional-disclosure",
}
_V3_TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "status",
    "symbol",
    "interval",
    "count",
    "decisionCutoff",
    "requestedSections",
    "sections",
}
_V3_SECTION_NAMES = (
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
_V3_REQUESTED_SECTIONS = _V3_SECTION_NAMES[:5]
_V3_UNREQUESTED_SECTIONS = _V3_SECTION_NAMES[5:]
_V3_ENVELOPE_FIELDS = {
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
}
_V3_AVAILABILITY_STATUSES = {"live", "delayed", "stale", "unavailable"}
_V3_QUALITY_STATUSES = {"validated", "partial", "anomalous", "invalid"}
_V3_TOP_LEVEL_STATUSES = {"live", "partial", "unavailable"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the read-only real-market snapshot contract.",
    )
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument(
        "--contract-version",
        choices=("v2", "v3"),
        default="v2",
    )
    return parser


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SmokeFailure(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(
            f"{value[:-1]}+00:00" if value.endswith("Z") else value
        )
    except ValueError as exc:
        raise SmokeFailure(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SmokeFailure(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _record(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SmokeFailure(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SmokeFailure(f"{label} must be an array")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SmokeFailure(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SmokeFailure(f"{label} must be finite")
    return result


def _non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SmokeFailure(f"{label} must be non-empty")
    return value


def _normalized_identifier(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _has_trade_order_path(value: str) -> bool:
    segments = [
        _normalized_identifier(segment)
        for segment in re.split(r"[/?#]+", value)
        if segment
    ]
    return any(
        left == "trade" and right == "orders"
        for left, right in zip(segments, segments[1:])
    )


def _has_trading_capability(value: object, *, is_key: bool) -> bool:
    normalized = _normalized_identifier(value)
    if any(
        capability in normalized
        for capability in _TRADING_CAPABILITY_IDENTIFIERS
    ):
        return True
    if is_key and normalized in _TRADING_STRUCTURE_KEYS:
        return True
    return isinstance(value, str) and _has_trade_order_path(value)


def _reject_trading_surface(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _has_trading_capability(key, is_key=True):
                raise SmokeFailure(f"trading capability found at {path}.{key}")
            _reject_trading_surface(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_trading_surface(child, f"{path}[{index}]")
    elif isinstance(value, str) and _has_trading_capability(value, is_key=False):
        raise SmokeFailure(f"trading capability found at {path}")


def _validate_metadata(
    value: object,
    label: str,
    cutoff: datetime,
) -> tuple[dict[str, Any], str, datetime, datetime, str, str]:
    record = _record(value, label)
    source = _non_empty_string(record.get("source"), f"{label}.source")
    as_of = _timestamp(record.get("asOf"), f"{label}.asOf")
    available_at = _timestamp(record.get("availableAt"), f"{label}.availableAt")
    method = _non_empty_string(
        record.get("methodVersion"),
        f"{label}.methodVersion",
    )
    status = _non_empty_string(
        record.get("qualityStatus"),
        f"{label}.qualityStatus",
    )
    if status not in _SNAPSHOT_STATUSES:
        raise SmokeFailure(f"{label}.qualityStatus is unsupported")
    if as_of > cutoff or available_at > cutoff:
        raise SmokeFailure(f"{label} is after the decision cutoff")
    if as_of > available_at:
        raise SmokeFailure(f"{label}.asOf follows availableAt")
    return record, source, as_of, available_at, method, status


def _validate_quote(payload: dict[str, Any], cutoff: datetime) -> None:
    quote, source, _, _, method, status = _validate_metadata(
        payload.get("quote"),
        "quote",
        cutoff,
    )
    if source != "moomoo":
        raise SmokeFailure("quote has an unexpected source")
    if method != "provider-quote-v1":
        raise SmokeFailure("quote has an unexpected method")
    if status != "live":
        raise SmokeFailure("quote is not live")
    if _number(quote.get("price"), "quote.price") <= 0:
        raise SmokeFailure("quote.price must be positive")
    _number(quote.get("changePercent"), "quote.changePercent")


def _validate_provenance(payload: dict[str, Any], cutoff: datetime) -> None:
    provenance = _array(payload.get("provenance"), "provenance")
    for index, raw in enumerate(provenance):
        label = f"provenance[{index}]"
        _, source, _, _, _, _ = _validate_metadata(raw, label, cutoff)
        if source not in _PROVENANCE_SOURCES:
            raise SmokeFailure(f"{label} has an unsupported source")


def _validate_holdings(payload: dict[str, Any], cutoff: datetime) -> None:
    holdings = _array(
        payload.get("institutionalHoldings"),
        "institutionalHoldings",
    )
    for index, raw in enumerate(holdings):
        label = f"institutionalHoldings[{index}]"
        _, source, _, _, method, status = _validate_metadata(raw, label, cutoff)
        if source != "moomoo-delayed-institutional-disclosure":
            raise SmokeFailure(f"{label} has an unexpected source")
        if method != "reported-holdings-v1":
            raise SmokeFailure(f"{label} has an unexpected method")
        if status != "delayed":
            raise SmokeFailure(f"{label} is not delayed")


def _validate_candles(payload: dict[str, Any], cutoff: datetime) -> list[datetime]:
    candles = _array(payload.get("completedCandles"), "completedCandles")
    if not candles:
        raise SmokeFailure("no completed candles")
    closes: list[datetime] = []
    previous: datetime | None = None
    for index, raw in enumerate(candles):
        label = f"completedCandles[{index}]"
        candle = _record(raw, label)
        if candle.get("complete") is not True:
            raise SmokeFailure(f"{label} is not complete")
        closed_at = _timestamp(candle.get("timestamp"), f"{label}.timestamp")
        as_of = _timestamp(candle.get("asOf"), f"{label}.asOf")
        available_at = _timestamp(
            candle.get("availableAt"),
            f"{label}.availableAt",
        )
        if previous is not None and closed_at <= previous:
            raise SmokeFailure("completed candles are out of order or duplicated")
        received_at = _timestamp(
            candle.get("receivedAt"),
            f"{label}.receivedAt",
        )
        if closed_at > cutoff or available_at > cutoff or received_at > cutoff:
            raise SmokeFailure(f"{label} is after the decision cutoff")
        if closed_at != as_of or closed_at > available_at:
            raise SmokeFailure(f"{label} timestamps are misaligned")
        if received_at < available_at:
            raise SmokeFailure(f"{label} was received before it was published")
        if candle.get("priceAdjustment") != payload.get("priceAdjustment"):
            raise SmokeFailure(f"{label} disagrees with the snapshot adjustment basis")
        if candle.get("source") != "moomoo":
            raise SmokeFailure(f"{label} has an unexpected source")
        if candle.get("methodVersion") != "provider-completed-candle-v1":
            raise SmokeFailure(f"{label} has an unexpected method")
        if candle.get("qualityStatus") != "live":
            raise SmokeFailure(f"{label} is not live")
        open_price = _number(candle.get("open"), f"{label}.open")
        high = _number(candle.get("high"), f"{label}.high")
        low = _number(candle.get("low"), f"{label}.low")
        close = _number(candle.get("close"), f"{label}.close")
        volume = _number(candle.get("volume"), f"{label}.volume")
        if (
            min(open_price, high, low, close) <= 0
            or volume < 0
            or high < max(open_price, close)
            or low > min(open_price, close)
        ):
            raise SmokeFailure(f"{label} has invalid OHLCV values")
        closes.append(closed_at)
        previous = closed_at
    return closes


def _validate_participation(
    payload: dict[str, Any],
    closes: list[datetime],
    cutoff: datetime,
) -> int:
    bars = _array(payload.get("participationBars"), "participationBars")
    if len(bars) != len(closes):
        raise SmokeFailure("participation bars are not one-to-one with candles")
    valid_count = 0
    for index, (raw, candle_close) in enumerate(zip(bars, closes, strict=True)):
        label = f"participationBars[{index}]"
        bar = _record(raw, label)
        closed_at = _timestamp(bar.get("closedAt"), f"{label}.closedAt")
        as_of = _timestamp(bar.get("asOf"), f"{label}.asOf")
        available_at = _timestamp(
            bar.get("availableAt"),
            f"{label}.availableAt",
        )
        if closed_at != candle_close or as_of != candle_close:
            raise SmokeFailure(f"{label} is misaligned with its candle")
        if available_at < closed_at or available_at > cutoff:
            raise SmokeFailure(f"{label} availability is invalid")
        if bar.get("source") != "moomoo":
            raise SmokeFailure(f"{label} has an unexpected source")
        if bar.get("methodVersion") != "order-size-activity-share-v1":
            raise SmokeFailure(f"{label} has an unexpected method")
        coverage = _number(bar.get("coverage"), f"{label}.coverage")
        if not 0 <= coverage <= 1:
            raise SmokeFailure(f"{label}.coverage is outside [0, 1]")

        status = bar.get("qualityStatus")
        metrics = (
            "mainShare",
            "retailShare",
            "mainActivity",
            "retailActivity",
            "netFlow",
        )
        if status == "live":
            values = {
                name: _number(bar.get(name), f"{label}.{name}") for name in metrics
            }
            main_share = values["mainShare"]
            retail_share = values["retailShare"]
            main_activity = values["mainActivity"]
            retail_activity = values["retailActivity"]
            activity_denominator = main_activity + retail_activity
            if (
                not 0 <= main_share <= 1
                or not 0 <= retail_share <= 1
                or main_share + retail_share != 1.0
            ):
                raise SmokeFailure(
                    f"{label} shares must exactly sum to one within [0, 1]"
                )
            if main_activity < 0 or retail_activity < 0:
                raise SmokeFailure(f"{label} activity must be non-negative")
            if coverage != 1.0:
                raise SmokeFailure(f"{label} live coverage must equal 1.0 exactly")
            if not math.isfinite(activity_denominator) or activity_denominator <= 0:
                raise SmokeFailure(
                    f"{label} live activity denominator must be finite and positive"
                )
            expected_main_share = main_activity / activity_denominator
            if (
                main_share != expected_main_share
                or retail_share != 1.0 - expected_main_share
            ):
                raise SmokeFailure(
                    f"{label} shares are inconsistent with activity"
                )
            if bar.get("missingReason") is not None:
                raise SmokeFailure(f"{label} live data cannot have a missing reason")
            valid_count += 1
        elif status == "unavailable":
            if any(bar.get(name) is not None for name in metrics):
                raise SmokeFailure(f"{label} unavailable metrics must all be null")
            reason = bar.get("missingReason")
            if not isinstance(reason, str) or not reason.strip():
                raise SmokeFailure(f"{label} requires a missing reason")
        else:
            raise SmokeFailure(f"{label} has an invalid quality status")
    if valid_count == 0:
        raise SmokeFailure("no valid participation bars")
    return valid_count


def _validate_indicators(payload: dict[str, Any], cutoff: datetime) -> None:
    indicators = _record(payload.get("indicators"), "indicators")
    expected = {
        "ma5": "sma-5-v1",
        "rsi": "wilder-rsi-14-v1",
        "macd": "macd-12-26-9-v1",
        "magicNine": "td-setup-close-4-v2",
        "volatility": "close-to-close-realized-v1",
    }
    for name, method in expected.items():
        label = f"indicators.{name}"
        _, source, _, available_at, actual_method, status = (
            _validate_metadata(indicators.get(name), label, cutoff)
        )
        if source != "analysis-core":
            raise SmokeFailure(f"indicators.{name} has an unexpected source")
        if actual_method != method:
            raise SmokeFailure(f"indicators.{name} has an unexpected method")
        if status not in {"live", "unavailable"}:
            raise SmokeFailure(f"indicators.{name} has an invalid quality status")
        if available_at != cutoff:
            raise SmokeFailure(
                f"indicators.{name} does not use the common decision cutoff"
            )


def validate_snapshot_v2(
    payload: object,
    *,
    expected_symbol: str,
    expected_interval: str,
    now: datetime | None = None,
) -> None:
    snapshot = _record(payload, "snapshot")
    _reject_trading_surface(snapshot)
    if snapshot.get("schemaVersion") != "2":
        raise SmokeFailure("snapshot schemaVersion is not 2")
    if snapshot.get("source") != "moomoo":
        raise SmokeFailure("snapshot source is not moomoo")
    if snapshot.get("sourceStatus") != "live":
        raise SmokeFailure("snapshot is not live")
    if snapshot.get("symbol") != expected_symbol.strip().upper():
        raise SmokeFailure("snapshot symbol does not match request")
    if snapshot.get("interval") != expected_interval:
        raise SmokeFailure("snapshot interval does not match request")
    cutoff = _timestamp(snapshot.get("decisionCutoff"), "decisionCutoff")
    if cutoff > (now or datetime.now(UTC)):
        raise SmokeFailure("decision cutoff is in the future")
    adjustment = snapshot.get("priceAdjustment")
    if adjustment not in {"forward-adjusted", "unadjusted"}:
        raise SmokeFailure("snapshot does not declare a known price adjustment basis")
    _validate_quote(snapshot, cutoff)
    closes = _validate_candles(snapshot, cutoff)
    _validate_participation(snapshot, closes, cutoff)
    _validate_indicators(snapshot, cutoff)
    _validate_holdings(snapshot, cutoff)
    _validate_provenance(snapshot, cutoff)
    warnings = _array(snapshot.get("warnings"), "warnings")
    if any(not isinstance(warning, str) for warning in warnings):
        raise SmokeFailure("warnings must contain only strings")


def validate_snapshot_v3(
    payload: object,
    *,
    expected_symbol: str,
    expected_interval: str,
    expected_count: int,
    now: datetime | None = None,
) -> None:
    snapshot = _record(payload, "snapshot")
    _reject_trading_surface(snapshot)
    if set(snapshot) != _V3_TOP_LEVEL_FIELDS:
        raise SmokeFailure("snapshot v3 top-level fields are not exact")
    if snapshot.get("schemaVersion") != "3":
        raise SmokeFailure("snapshot schemaVersion is not 3")
    status = snapshot.get("status")
    if status not in _V3_TOP_LEVEL_STATUSES:
        raise SmokeFailure("snapshot v3 status is unsupported")
    if snapshot.get("symbol") != expected_symbol.strip().upper():
        raise SmokeFailure("snapshot symbol does not match request")
    if snapshot.get("interval") != expected_interval:
        raise SmokeFailure("snapshot interval does not match request")
    count = snapshot.get("count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count != expected_count
        or not 1 <= count <= 1000
    ):
        raise SmokeFailure("snapshot count does not match request")
    cutoff = _timestamp(snapshot.get("decisionCutoff"), "decisionCutoff")
    if cutoff > (now or datetime.now(UTC)):
        raise SmokeFailure("decision cutoff is in the future")
    if snapshot.get("requestedSections") != list(_V3_REQUESTED_SECTIONS):
        raise SmokeFailure("snapshot requestedSections are not the fixed ordered set")

    sections = _record(snapshot.get("sections"), "sections")
    if set(sections) != set(_V3_SECTION_NAMES):
        raise SmokeFailure("snapshot v3 section names are not exact")
    envelopes = {
        name: _validate_v3_section(sections.get(name), name, cutoff)
        for name in _V3_SECTION_NAMES
    }
    for name in _V3_UNREQUESTED_SECTIONS:
        _validate_v3_unrequested_section(envelopes[name], name)

    quote = envelopes["quote"]
    quote_usable = _v3_quote_is_usable(quote)
    if (
        quote["availabilityStatus"] in {"live", "delayed"}
        and quote["qualityStatus"] == "validated"
        and not quote_usable
    ):
        raise SmokeFailure("snapshot validated quote is unusable")
    candles_usable = _v3_candles_are_usable(envelopes["candles"], cutoff)
    holdings = envelopes["holdings"]
    if (
        holdings["availabilityStatus"] in {"live", "delayed"}
        and holdings["qualityStatus"] == "validated"
        and (
            not isinstance(holdings["data"], list)
            or not holdings["data"]
        )
    ):
        raise SmokeFailure("snapshot validated holdings are unusable")
    if not quote_usable and not candles_usable:
        raise SmokeFailure("snapshot has no usable quote or completed candles")
    expected_status = (
        "live"
        if all(
            envelopes[name]["availabilityStatus"] in {"live", "delayed"}
            and envelopes[name]["qualityStatus"] == "validated"
            for name in _V3_REQUESTED_SECTIONS
        ) and candles_usable
        else "partial"
    )
    if status != expected_status:
        raise SmokeFailure("snapshot status is inconsistent with its requested sections")


def _validate_v3_section(
    value: object,
    name: str,
    cutoff: datetime,
) -> dict[str, Any]:
    label = f"sections.{name}"
    envelope = _record(value, label)
    if set(envelope) != _V3_ENVELOPE_FIELDS:
        raise SmokeFailure(f"{label} envelope fields are not exact")
    if envelope.get("availabilityStatus") not in _V3_AVAILABILITY_STATUSES:
        raise SmokeFailure(f"{label}.availabilityStatus is unsupported")
    if envelope.get("qualityStatus") not in _V3_QUALITY_STATUSES:
        raise SmokeFailure(f"{label}.qualityStatus is unsupported")
    source = envelope.get("source")
    if source is not None:
        _non_empty_string(source, f"{label}.source")
    method = _non_empty_string(envelope.get("methodVersion"), f"{label}.methodVersion")
    del method
    for field in ("errorCode", "reason"):
        field_value = envelope.get(field)
        if field_value is not None:
            _non_empty_string(field_value, f"{label}.{field}")
    warnings = _array(envelope.get("warnings"), f"{label}.warnings")
    if any(not isinstance(item, str) or not item.strip() for item in warnings):
        raise SmokeFailure(f"{label}.warnings must contain non-empty strings")
    anomalies = _array(envelope.get("anomalies"), f"{label}.anomalies")
    for index, anomaly in enumerate(anomalies):
        record = _record(anomaly, f"{label}.anomalies[{index}]")
        _non_empty_string(record.get("code"), f"{label}.anomalies[{index}].code")
        _non_empty_string(record.get("reason"), f"{label}.anomalies[{index}].reason")
        row_index = record.get("rowIndex")
        if "rowIndex" in record and (
            isinstance(row_index, bool)
            or not isinstance(row_index, (int, float))
            or not math.isfinite(float(row_index))
            or not float(row_index).is_integer()
            or row_index < 0
        ):
            raise SmokeFailure(f"{label}.anomalies[{index}].rowIndex is invalid")

    time_fields = ("asOf", "availableAt", "receivedAt")
    raw_times = {field: envelope.get(field) for field in time_fields}
    times = {
        field: _timestamp(value, f"{label}.{field}")
        for field, value in raw_times.items()
        if value is not None
    }
    if any(value > cutoff for value in times.values()):
        raise SmokeFailure(f"{label} timestamp is after cutoff")
    availability = envelope["availabilityStatus"]
    if availability == "stale" and times:
        raise SmokeFailure(f"{label} stale timestamps must be null")
    if availability in {"live", "delayed"} and len(times) != len(time_fields):
        raise SmokeFailure(f"{label} available timestamps must be complete")
    for earlier, later in zip(time_fields, time_fields[1:]):
        if earlier in times and later in times and times[earlier] > times[later]:
            raise SmokeFailure(f"{label} timestamps are out of order")

    quality = envelope["qualityStatus"]
    data = envelope.get("data")
    error_code = envelope.get("errorCode")
    reason = envelope.get("reason")
    state_invalid = False
    if availability in {"live", "delayed"}:
        state_invalid = (
            quality == "invalid"
            or source is None
            or len(times) != len(time_fields)
            or data is None
            or error_code is not None
            or reason is not None
        )
    elif availability == "stale":
        state_invalid = (
            quality != "invalid"
            or source is not None
            or bool(times)
            or data is not None
            or error_code is None
            or reason is None
        )
    else:
        state_invalid = (
            quality != "invalid"
            or (data is not None and data != [])
            or error_code is None
            or reason is None
        )
    if state_invalid:
        raise SmokeFailure(f"{label} availability state is invalid")
    return envelope


def _validate_v3_unrequested_section(
    envelope: dict[str, Any],
    name: str,
) -> None:
    expected = {
        "availabilityStatus": "unavailable",
        "qualityStatus": "invalid",
        "source": None,
        "asOf": None,
        "availableAt": None,
        "receivedAt": None,
        "data": None,
        "errorCode": "NOT_REQUESTED",
        "reason": "此切片未请求该数据",
        "warnings": [],
        "anomalies": [],
        "methodVersion": "unavailable-v1",
    }
    if envelope != expected:
        raise SmokeFailure(f"sections.{name} is not the fixed unrequested envelope")


def _v3_quote_is_usable(envelope: dict[str, Any]) -> bool:
    if envelope["availabilityStatus"] not in {"live", "delayed"}:
        return False
    data = envelope["data"]
    if (
        envelope["source"] != "moomoo"
        or envelope["methodVersion"] != "provider-quote-v1"
        or not isinstance(data, dict)
        or data.get("institutionalIdentity") is True
        or data.get("source") != "moomoo"
        or data.get("methodVersion") != "provider-quote-v1"
        or data.get("qualityStatus") != "live"
    ):
        raise SmokeFailure("snapshot quote source contract is invalid")
    data_as_of = _timestamp(data.get("asOf"), "sections.quote.data.asOf")
    data_available_at = _timestamp(
        data.get("availableAt"), "sections.quote.data.availableAt"
    )
    section_as_of = _timestamp(envelope["asOf"], "sections.quote.asOf")
    section_available_at = _timestamp(
        envelope["availableAt"], "sections.quote.availableAt"
    )
    if (
        data_as_of != section_as_of
        or data_available_at != section_available_at
        or data_as_of > data_available_at
    ):
        raise SmokeFailure("snapshot quote metadata contradicts its data")
    try:
        price = _number(data.get("price"), "sections.quote.data.price")
        _number(data.get("changePercent"), "sections.quote.data.changePercent")
    except SmokeFailure as error:
        message = (
            "snapshot validated quote is unusable"
            if envelope["qualityStatus"] == "validated"
            else "snapshot quote data is invalid"
        )
        raise SmokeFailure(message) from error
    if price <= 0:
        if envelope["qualityStatus"] == "validated":
            raise SmokeFailure("snapshot validated quote is unusable")
        raise SmokeFailure("snapshot quote price must be positive")
    return envelope["qualityStatus"] == "validated"


def _v3_candles_are_usable(
    envelope: dict[str, Any],
    cutoff: datetime,
) -> bool:
    if envelope["availabilityStatus"] not in {"live", "delayed"}:
        return False
    data = envelope["data"]
    if (
        envelope["source"] != "moomoo"
        or envelope["methodVersion"] != "provider-completed-candle-v1"
        or not isinstance(data, dict)
    ):
        raise SmokeFailure("snapshot candle source contract is invalid")
    price_adjustment = data.get("priceAdjustment")
    candles = data.get("candles")
    if (
        price_adjustment not in {"forward-adjusted", "unadjusted"}
        or not isinstance(candles, list)
    ):
        raise SmokeFailure("snapshot candle data contract is invalid")
    if not candles:
        return False
    section_as_of = _timestamp(envelope["asOf"], "sections.candles.asOf")
    section_available_at = _timestamp(
        envelope["availableAt"], "sections.candles.availableAt"
    )
    section_received_at = _timestamp(
        envelope["receivedAt"], "sections.candles.receivedAt"
    )
    previous: datetime | None = None
    row_available_times: list[datetime] = []
    for index, raw in enumerate(candles):
        candle = _record(raw, f"sections.candles.data.candles[{index}]")
        if (
            candle.get("institutionalIdentity") is True
            or candle.get("complete") is not True
            or candle.get("source") != "moomoo"
            or candle.get("priceAdjustment") != price_adjustment
            or candle.get("qualityStatus") != "live"
            or candle.get("methodVersion") != "provider-completed-candle-v1"
        ):
            raise SmokeFailure("snapshot candle row contract is invalid")
        closed_at = _timestamp(
            candle.get("timestamp"),
            f"sections.candles.data.candles[{index}].timestamp",
        )
        row_as_of = _timestamp(
            candle.get("asOf"),
            f"sections.candles.data.candles[{index}].asOf",
        )
        row_available_at = _timestamp(
            candle.get("availableAt"),
            f"sections.candles.data.candles[{index}].availableAt",
        )
        row_received_at = _timestamp(
            candle.get("receivedAt"),
            f"sections.candles.data.candles[{index}].receivedAt",
        )
        if (
            row_as_of != closed_at
            or closed_at > row_available_at
            or row_available_at > section_available_at
            or row_received_at < row_available_at
            or row_received_at > section_received_at
            or row_received_at > cutoff
            or (previous is not None and closed_at <= previous)
        ):
            raise SmokeFailure("snapshot candle row time is invalid")
        values = [
            _number(candle.get(field), f"sections.candles.data.candles[{index}].{field}")
            for field in ("open", "high", "low", "close", "volume")
        ]
        open_price, high, low, close, volume = values
        if (
            min(open_price, high, low, close) <= 0
            or volume < 0
            or high < max(open_price, close)
            or low > min(open_price, close)
            or high < low
        ):
            raise SmokeFailure("snapshot candle row values are invalid")
        previous = closed_at
        row_available_times.append(row_available_at)
    if section_as_of != previous or section_available_at != max(row_available_times):
        raise SmokeFailure("snapshot candle metadata contradicts its rows")
    return envelope["qualityStatus"] == "validated"


def _get_json(
    url: str,
    *,
    authorization_token: str | None,
    opener: Callable[..., Any],
) -> object:
    headers = {"Accept": "application/json"}
    if authorization_token:
        headers["Authorization"] = f"Bearer {authorization_token}"
    request = Request(
        url,
        headers=headers,
        method="GET",
    )
    with opener(request, timeout=10.0) as response:
        return json.loads(response.read())


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        del request, file_pointer, code, message, headers, new_url
        raise SmokeFailure("redirect refused")


def _strict_urlopen(request: Request, *, timeout: float) -> Any:
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def load_live_snapshot(
    base_url: str,
    *,
    symbol: str,
    interval: str,
    count: int,
    authorization_token: str | None = None,
    contract_version: str = "v2",
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not 1 <= count <= 1000:
        raise SmokeFailure("count must be between 1 and 1000")
    open_request = opener or _strict_urlopen
    root = base_url.rstrip("/")
    health = _record(
        _get_json(
            f"{root}/health",
            authorization_token=authorization_token,
            opener=open_request,
        ),
        "health",
    )
    _reject_trading_surface(health)
    healthy_items = health.get("items")
    if (
        health.get("schemaVersion") != "1"
        or health.get("source") != "moomoo"
        or health.get("session") != "healthy"
        or not isinstance(healthy_items, list)
        or not healthy_items
        or any(
            not isinstance(item, dict) or item.get("status") != "healthy"
            for item in healthy_items
        )
        or "error" in health
    ):
        raise SmokeFailure("OpenD is not healthy")
    query = urlencode(
        {
            "symbol": symbol.strip().upper(),
            "interval": interval,
            "count": count,
        }
    )
    route = {
        "v2": "/stock-snapshot",
        "v3": "/v3/stock-snapshot",
    }.get(contract_version)
    if route is None:
        raise SmokeFailure("contract version must be v2 or v3")
    return _record(
        _get_json(
            f"{root}{route}?{query}",
            authorization_token=authorization_token,
            opener=open_request,
        ),
        "snapshot",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = (
            json.loads(args.fixture.read_text(encoding="utf-8"))
            if args.fixture is not None
            else load_live_snapshot(
                args.base_url,
                symbol=args.symbol,
                interval=args.interval,
                count=args.count,
                authorization_token=os.environ.get("MOOMOO_GATEWAY_TOKEN"),
                contract_version=args.contract_version,
            )
        )
        if args.contract_version == "v2":
            validate_snapshot_v2(
                payload,
                expected_symbol=args.symbol,
                expected_interval=args.interval,
            )
            print(
                f"PASS snapshot={args.symbol.strip().upper()} "
                "candles>0 valid_participation>0 future_rows=0"
            )
        else:
            validate_snapshot_v3(
                payload,
                expected_symbol=args.symbol,
                expected_interval=args.interval,
                expected_count=args.count,
            )
            print(
                f"PASS snapshot={args.symbol.strip().upper()} "
                "contract=v3 usable_price>0"
            )
        return 0
    except (
        OSError,
        HTTPError,
        URLError,
        json.JSONDecodeError,
        SmokeFailure,
    ) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
