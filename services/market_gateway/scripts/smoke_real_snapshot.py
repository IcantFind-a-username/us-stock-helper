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
from urllib.request import Request, urlopen


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the read-only real-market snapshot contract.",
    )
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--fixture", type=Path)
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
        if closed_at > cutoff or available_at > cutoff:
            raise SmokeFailure(f"{label} is after the decision cutoff")
        if closed_at != as_of or closed_at > available_at:
            raise SmokeFailure(f"{label} timestamps are misaligned")
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
            if coverage <= 0:
                raise SmokeFailure(f"{label} live coverage must be positive")
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
        "magicNine": "sequential-close-4-v1",
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


def validate_snapshot(
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
    _validate_quote(snapshot, cutoff)
    closes = _validate_candles(snapshot, cutoff)
    _validate_participation(snapshot, closes, cutoff)
    _validate_indicators(snapshot, cutoff)
    _validate_holdings(snapshot, cutoff)
    _validate_provenance(snapshot, cutoff)
    warnings = _array(snapshot.get("warnings"), "warnings")
    if any(not isinstance(warning, str) for warning in warnings):
        raise SmokeFailure("warnings must contain only strings")


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


def load_live_snapshot(
    base_url: str,
    *,
    symbol: str,
    interval: str,
    count: int,
    authorization_token: str | None = None,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    if not 1 <= count <= 1000:
        raise SmokeFailure("count must be between 1 and 1000")
    root = base_url.rstrip("/")
    health = _record(
        _get_json(
            f"{root}/health",
            authorization_token=authorization_token,
            opener=opener,
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
    return _record(
        _get_json(
            f"{root}/stock-snapshot?{query}",
            authorization_token=authorization_token,
            opener=opener,
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
            )
        )
        validate_snapshot(
            payload,
            expected_symbol=args.symbol,
            expected_interval=args.interval,
        )
        print(
            f"PASS snapshot={args.symbol.strip().upper()} "
            "candles>0 valid_participation>0 future_rows=0"
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
