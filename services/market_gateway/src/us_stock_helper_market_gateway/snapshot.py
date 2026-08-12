from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from us_stock_helper_core import (
    TD_SETUP_VERSION,
    CapitalFlowPoint,
    OHLCVBar,
    TDSetupResult,
    build_participation_bars,
    estimate_annualized_volatility,
    macd,
    moving_average,
    rsi,
    td_setup,
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
    indicators = _indicators(candles, cutoff, bars)
    provenance = _provenance(quote, candles, participation, holdings, indicators)
    price_adjustment = _price_adjustment(candles)
    if price_adjustment == "forward-adjusted":
        warnings = [
            "价格为前复权：除权除息会回溯改写这条历史序列，回测请以复权基准对齐。",
            *warnings,
        ]
    return {
        "schemaVersion": "2",
        "source": "moomoo",
        "sourceStatus": "live",
        "symbol": symbol,
        "interval": interval,
        "decisionCutoff": iso_z(cutoff),
        "priceAdjustment": price_adjustment,
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
        received_at = parse_aware(item["receivedAt"], "candle receivedAt")
        if received_at < available_at or received_at > cutoff:
            raise ValueError("candle receipt time is outside the decision cutoff")
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
                "receivedAt": iso_z(received_at),
                "priceAdjustment": _require_adjustment(item),
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
    # A missing or unusable feed is an absence and degrades to "unavailable".
    # A row that violates the decision cutoff is a temporal defect, and saying
    # "no data" about it would hide exactly the failure worth knowing.
    points = tuple(_flow_points(symbol, flow_items, cutoff))
    if not points:
        return _unavailable_participation(bars), [
            "Capital-flow participation is unavailable for this snapshot."
        ]
    # Check the cutoff here rather than reading it out of an upstream exception
    # message: a reworded message would silently disable the guard.
    for point in points:
        if point.available_at > cutoff:
            raise ValueError("flow point is after the decision cutoff")
    for bar in bars:
        if bar.closed_at > cutoff or bar.available_at > cutoff:
            raise ValueError("completed candle is after the decision cutoff")
    try:
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


def _indicators(
    candles: list[dict[str, Any]],
    cutoff: datetime,
    bars: tuple[OHLCVBar, ...] = (),
) -> dict[str, dict[str, Any]]:
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
    setup = td_setup(bars) if bars else None
    magic = setup.latest if setup else None
    realized = estimate_annualized_volatility(bars, cutoff)
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
        "volatility": {
            **base,
            "availableAt": iso_z(cutoff),
            "value": realized.value,
            "sampleSize": realized.sample_size,
            "missingReason": realized.missing_reason,
            "methodVersion": realized.method_version,
            "qualityStatus": realized.quality_status,
        },
        "magicNine": {
            **base,
            "direction": magic.direction.value if magic else None,
            "count": magic.count if magic else 0,
            "completed": magic.completed if magic else False,
            "perfected": magic.perfected if magic else False,
            "confirmedAtIndex": magic.confirmed_at_index if magic else None,
            "lastCompleted": _last_completed_setup(setup),
            "methodVersion": TD_SETUP_VERSION,
            "qualityStatus": "live" if magic else "unavailable",
        },
    }


_KNOWN_ADJUSTMENTS = {"forward-adjusted", "unadjusted"}


def _require_adjustment(item: dict[str, Any]) -> str:
    """The basis is a fact about the gateway's own request, never a guess."""

    basis = item.get("priceAdjustment")
    if basis not in _KNOWN_ADJUSTMENTS:
        raise ValueError("candle does not declare a known price adjustment basis")
    return basis


def _price_adjustment(candles: list[dict[str, Any]]) -> str:
    bases = {candle["priceAdjustment"] for candle in candles}
    if len(bases) > 1:
        raise ValueError("candles mix price adjustment bases")
    if not bases:
        # No completed candles yet is a normal state before the first bar of a
        # session closes. The basis of the series is still known — the gateway
        # always requests forward adjustment — and emitting "unknown" here made
        # the app reject an otherwise valid snapshot.
        return "forward-adjusted"
    basis = bases.pop()
    if basis not in _KNOWN_ADJUSTMENTS:
        raise ValueError(f"unsupported price adjustment basis: {basis}")
    return basis


def _last_completed_setup(setup: TDSetupResult | None) -> dict[str, Any] | None:
    """Keep a completed nine visible after counting restarts on the next bar."""

    if setup is None or not setup.signals:
        return None
    last = setup.signals[-1]
    return {
        "direction": last.direction.value,
        "confirmedAtIndex": last.confirmed_at_index,
        "perfected": last.perfected,
        "barsSince": len(setup.bullish_counts) - 1 - last.confirmed_at_index,
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
