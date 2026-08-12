from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from us_stock_helper_core import (
    CapitalFlowPoint,
    OHLCVBar,
    build_participation_bars,
    macd,
    magic_nine,
    moving_average,
    rsi,
)

from .time_utils import iso_z, parse_aware, require_utc


_INTERVALS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "60m": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(days=7),
}


def assemble_stock_snapshot(
    *,
    symbol: str,
    interval: str,
    decision_cutoff: datetime,
    quote_items: list[dict[str, Any]],
    candle_items: list[dict[str, Any]],
    flow_items: list[dict[str, Any]],
    holding_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert normalized read-only batches into one cutoff-consistent contract."""

    cutoff = require_utc(decision_cutoff, "decision_cutoff")
    if interval not in _INTERVALS:
        raise ValueError("unsupported snapshot interval")
    quote = _quote(symbol, quote_items, cutoff)
    candles = _candles(symbol, interval, candle_items, cutoff)
    bars = _analysis_bars(symbol, interval, candles)
    participation, warnings = _participation(symbol, interval, bars, flow_items, cutoff)
    holdings = _holdings(holding_items, cutoff)
    indicators = _indicators(candles, cutoff)
    provenance = _provenance(quote, candles, participation, holdings, indicators)
    return {
        "schemaVersion": "2",
        "source": "moomoo",
        "sourceStatus": "live",
        "symbol": symbol,
        "interval": interval,
        "decisionCutoff": iso_z(cutoff),
        "quote": quote,
        "completedCandles": candles,
        "participationBars": participation,
        "indicators": indicators,
        "institutionalHoldings": holdings,
        "provenance": provenance,
        "warnings": warnings,
    }


def _quote(
    symbol: str, items: list[dict[str, Any]], cutoff: datetime
) -> dict[str, Any]:
    if len(items) != 1 or items[0].get("code") != f"US.{symbol}":
        raise ValueError("quote does not match requested symbol")
    item = items[0]
    available_at = _available_at(item, cutoff)
    return {
        "price": item["price"],
        "changePercent": item["changePercent"],
        "source": "moomoo",
        "asOf": iso_z(available_at),
        "availableAt": iso_z(available_at),
        "methodVersion": "provider-quote-v1",
        "qualityStatus": "live",
    }


def _candles(
    symbol: str,
    interval: str,
    items: list[dict[str, Any]],
    cutoff: datetime,
) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    previous: datetime | None = None
    for item in items:
        if item.get("code") != f"US.{symbol}":
            raise ValueError("candle does not match requested symbol")
        if _canonical_interval(item.get("timeframe")) != interval:
            raise ValueError("provider candle interval does not match request")
        closed_at = parse_aware(item["timestamp"], "candle timestamp")
        available_at = _available_at(item, cutoff)
        if previous is not None and closed_at <= previous:
            raise ValueError("candle timestamps are not strictly increasing")
        if closed_at > cutoff:
            raise ValueError("completed candle is after decision cutoff")
        previous = closed_at
        candles.append(
            {
                "timestamp": iso_z(closed_at),
                "complete": True,
                "open": item["open"],
                "high": item["high"],
                "low": item["low"],
                "close": item["close"],
                "volume": item["volume"],
                "source": "moomoo",
                "asOf": iso_z(closed_at),
                "availableAt": iso_z(available_at),
                "methodVersion": "provider-completed-candle-v1",
                "qualityStatus": "live",
            }
        )
    return candles


def _analysis_bars(
    symbol: str, interval: str, candles: list[dict[str, Any]]
) -> tuple[OHLCVBar, ...]:
    duration = _INTERVALS[interval]
    return tuple(
        OHLCVBar(
            symbol=symbol,
            interval=interval,
            opened_at=parse_aware(item["timestamp"], "candle timestamp") - duration,
            closed_at=parse_aware(item["timestamp"], "candle timestamp"),
            available_at=parse_aware(item["availableAt"], "candle availableAt"),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]),
        )
        for item in candles
    )


def _participation(
    symbol: str,
    interval: str,
    bars: tuple[OHLCVBar, ...],
    flow_items: list[dict[str, Any]],
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        points = tuple(_flow_points(symbol, flow_items, cutoff))
        result = build_participation_bars(points, bars, cutoff)
    except (KeyError, TypeError, ValueError):
        return _unavailable_participation(bars), [
            "Capital-flow participation is unavailable for this snapshot."
        ]
    return [_participation_item(item) for item in result], (
        []
        if points
        else ["Capital-flow participation is unavailable for this snapshot."]
    )


def _flow_points(
    symbol: str, items: list[dict[str, Any]], cutoff: datetime
) -> list[CapitalFlowPoint]:
    return [
        CapitalFlowPoint(
            symbol=symbol,
            timestamp=parse_aware(item["timestamp"], "flow timestamp"),
            available_at=_available_at(item, cutoff),
            total_net=float(item["totalNetFlow"]),
            super_net=float(item["extraLargeOrderNetFlow"]),
            big_net=float(item["largeOrderNetFlow"]),
            mid_net=float(item["mediumOrderNetFlow"]),
            small_net=float(item["smallOrderNetFlow"]),
            session=_flow_session(item),
        )
        for item in items
    ]


def _flow_session(item: dict[str, Any]) -> str:
    session = item["session"]
    if not isinstance(session, str) or not session.strip():
        raise ValueError("flow session metadata is malformed")
    return session


def _unavailable_participation(bars: tuple[OHLCVBar, ...]) -> list[dict[str, Any]]:
    return [
        {
            "closedAt": iso_z(bar.closed_at),
            "mainShare": None,
            "retailShare": None,
            "mainActivity": None,
            "retailActivity": None,
            "netFlow": None,
            "coverage": 0.0,
            "source": "moomoo",
            "asOf": iso_z(bar.closed_at),
            "availableAt": iso_z(bar.available_at),
            "methodVersion": "order-size-activity-share-v1",
            "qualityStatus": "unavailable",
            "missingReason": "capital flow unavailable",
        }
        for bar in bars
    ]


def _participation_item(item: Any) -> dict[str, Any]:
    return {
        "closedAt": iso_z(item.closed_at),
        "mainShare": item.main_share,
        "retailShare": item.retail_share,
        "mainActivity": item.main_activity,
        "retailActivity": item.retail_activity,
        "netFlow": item.net_flow,
        "coverage": item.coverage,
        "source": "moomoo",
        "asOf": iso_z(item.closed_at),
        "availableAt": iso_z(item.available_at),
        "methodVersion": item.method_version,
        "qualityStatus": item.quality_status,
        "missingReason": item.missing_reason,
    }


def _holdings(items: list[dict[str, Any]], cutoff: datetime) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        available_at = _available_at(item, cutoff)
        reported_at = parse_aware(item["reportedAt"], "holding reportedAt")
        result.append(
            {
                **item,
                "source": "moomoo-delayed-institutional-disclosure",
                "asOf": iso_z(reported_at),
                "availableAt": iso_z(available_at),
                "methodVersion": "reported-holdings-v1",
                "qualityStatus": "delayed",
            }
        )
    return result


def _indicators(candles: list[dict[str, Any]], cutoff: datetime) -> dict[str, dict[str, Any]]:
    closes = [float(item["close"]) for item in candles]
    as_of = (
        parse_aware(candles[-1]["timestamp"], "candle timestamp")
        if candles
        else cutoff
    )
    base = {
        "source": "analysis-core",
        "asOf": iso_z(as_of),
        "availableAt": iso_z(cutoff),
    }
    ma5 = moving_average(closes, 5)
    rsi14 = rsi(closes, 14)
    macd_value = macd(closes, 12, 26, 9)
    magic = magic_nine(closes)
    return {
        "ma5": {
            **base,
            "value": ma5,
            "methodVersion": "sma-5-v1",
            "qualityStatus": "live" if ma5 is not None else "unavailable",
        },
        "rsi": {
            **base,
            "value": rsi14,
            "methodVersion": "wilder-rsi-14-v1",
            "qualityStatus": "live" if rsi14 is not None else "unavailable",
        },
        "macd": {
            **base,
            "line": macd_value.line if macd_value else None,
            "signal": macd_value.signal if macd_value else None,
            "histogram": macd_value.histogram if macd_value else None,
            "methodVersion": "macd-12-26-9-v1",
            "qualityStatus": "live" if macd_value else "unavailable",
        },
        "magicNine": {
            **base,
            "direction": magic.direction.value if magic else None,
            "count": magic.count if magic else 0,
            "completed": magic.completed if magic else False,
            "confirmedAtIndex": magic.confirmed_at_index if magic else None,
            "methodVersion": magic.algorithm_version if magic else "sequential-close-4-v1",
            "qualityStatus": "live" if magic else "unavailable",
        },
    }


def _provenance(
    quote: dict[str, Any],
    candles: list[dict[str, Any]],
    participation: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    indicators: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    children = [quote, *candles, *participation, *holdings, *indicators.values()]
    return [
        {
            "source": child["source"],
            "asOf": child["asOf"],
            "availableAt": child["availableAt"],
            "methodVersion": child["methodVersion"],
            "qualityStatus": child["qualityStatus"],
        }
        for child in children
    ]


def _available_at(item: dict[str, Any], cutoff: datetime) -> datetime:
    available_at = parse_aware(item["availableAt"], "item availableAt")
    if available_at > cutoff:
        raise ValueError("item is after decision cutoff")
    return available_at


def _canonical_interval(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("provider candle interval is malformed")
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "d": "day",
        "day": "day",
        "k_day": "day",
        "w": "week",
        "week": "week",
        "k_week": "week",
    }
    return aliases.get(normalized, normalized)
