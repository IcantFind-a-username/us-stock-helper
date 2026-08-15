from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from us_stock_helper_core import (
    PATTERNS_SHAPES_VERSION,
    TD_SETUP_VERSION,
    CapitalFlowPoint,
    OHLCVBar,
    PatternShapeDetection,
    PatternShapeSignal,
    TDSetupResult,
    build_participation_bars,
    detect_pattern_shapes,
    estimate_annualized_volatility,
    macd_series,
    moving_average_series,
    rsi_series,
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


# The moving averages a candlestick chart is expected to carry. Five, ten and
# twenty are the short-term set the rest of the product reasons about; sixty
# is the slow backdrop that says whether those three are fighting the trend.
_MA_PERIODS = (5, 10, 20, 60)

# Names the axis a series index refers to, so the app never has to infer that
# position i belongs to completedCandles[i].
_SERIES_ALIGNMENT = {"seriesAlignedTo": "completedCandles"}


def _last(series: tuple[float | None, ...]) -> float | None:
    return series[-1] if series else None


def _moving_average_entry(
    base: dict[str, Any], closes: list[float], period: int
) -> dict[str, Any]:
    series = moving_average_series(closes, period)
    value = _last(series)
    return {
        **base,
        **_SERIES_ALIGNMENT,
        "value": value,
        "series": list(series),
        "methodVersion": f"sma-{period}-v1",
        "qualityStatus": "live" if value is not None else "unavailable",
    }


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
    # Every drawable series is emitted position-by-position against
    # completedCandles. The app is barred from deriving indicator paths from
    # its own closes, so an absent series means an undrawable chart rather
    # than a client-side fallback, and a shortened one would make the app
    # guess which bar an index belongs to.
    rsi14 = rsi_series(closes, 14)
    macd_lines = macd_series(closes, 12, 26, 9)
    setup = td_setup(bars) if bars else None
    magic = setup.latest if setup else None
    realized = estimate_annualized_volatility(bars, cutoff)
    return {
        **{
            f"ma{period}": _moving_average_entry(base, closes, period)
            for period in _MA_PERIODS
        },
        "rsi": {
            **base,
            **_SERIES_ALIGNMENT,
            "value": _last(rsi14),
            "series": list(rsi14),
            "methodVersion": "wilder-rsi-14-v1",
            "qualityStatus": "live" if _last(rsi14) is not None else "unavailable",
        },
        "macd": {
            **base,
            **_SERIES_ALIGNMENT,
            "line": _last(macd_lines.line),
            "signal": _last(macd_lines.signal),
            "histogram": _last(macd_lines.histogram),
            "lineSeries": list(macd_lines.line),
            "signalSeries": list(macd_lines.signal),
            "histogramSeries": list(macd_lines.histogram),
            "methodVersion": "macd-12-26-9-v1",
            "qualityStatus": (
                "live" if _last(macd_lines.line) is not None else "unavailable"
            ),
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
            **_SERIES_ALIGNMENT,
            "direction": magic.direction.value if magic else None,
            "count": magic.count if magic else 0,
            "series": _magic_nine_series(setup),
            "completed": magic.completed if magic else False,
            "perfected": magic.perfected if magic else None,
            "confirmedAtIndex": magic.confirmed_at_index if magic else None,
            "lastCompleted": _last_completed_setup(setup),
            "methodVersion": TD_SETUP_VERSION,
            # Availability describes whether the count could be computed at
            # all. A neutral bar ends the run, and "no run in progress" is a
            # computed answer of zero — reporting it as unavailable hid any
            # completed setup the series still carried.
            "qualityStatus": "live" if setup is not None else "unavailable",
        },
        "patternShapes": _pattern_shapes_entry(base, bars),
    }


def _pattern_shapes_entry(
    base: dict[str, Any], bars: tuple[OHLCVBar, ...]
) -> dict[str, Any]:
    """顶分型/底分型/W底/双头/头肩顶/头肩底/回踩五日线 -- see patterns_shapes.py.

    Each of the four detectors carries its own minimum-window honesty, so this
    entry is only "unavailable" when there are no completed bars to hand any
    detector at all; below that, every individual detector still reports its
    own typed-unavailable reason inside ``detections``.
    """

    if not bars:
        return {
            **base,
            "detections": [],
            "methodVersion": PATTERNS_SHAPES_VERSION,
            "qualityStatus": "unavailable",
        }
    detections = detect_pattern_shapes(bars)
    return {
        **base,
        "detections": [_detection_payload(detection) for detection in detections],
        "methodVersion": PATTERNS_SHAPES_VERSION,
        "qualityStatus": "live",
    }


def _detection_payload(detection: PatternShapeDetection) -> dict[str, Any]:
    return {
        "detector": detection.detector,
        "minimumWindow": detection.minimum_window,
        "sampleSize": detection.sample_size,
        "qualityStatus": detection.quality_status,
        "missingReason": detection.missing_reason,
        "methodVersion": detection.algorithm_version,
        "signals": [_signal_payload(signal) for signal in detection.signals],
    }


def _signal_payload(signal: PatternShapeSignal) -> dict[str, Any]:
    return {
        "kind": signal.kind.value,
        "name": signal.name,
        "status": signal.status.value,
        "direction": signal.direction.value,
        "bars": [
            {"index": bar.index, "closedAt": iso_z(bar.closed_at)} for bar in signal.bars
        ],
        "anchorIndex": signal.anchor.index,
        "eventIndex": signal.event_index,
        "invalidation": signal.invalidation,
        "explanation": signal.explanation,
        "reading": {
            "summary": signal.reading_summary,
            "detail": signal.reading_detail,
            "honesty": signal.reading_honesty,
        },
        "methodVersion": signal.algorithm_version,
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


def _magic_nine_series(
    setup: TDSetupResult | None,
) -> list[dict[str, Any] | None]:
    """Serialize every computed TD count against its completed candle.

    The domain keeps bullish and bearish counters separately because only one
    can be active on a bar. The wire combines them so the phone never has to
    infer a direction from a sign or reconstruct counts from closes.
    """

    if setup is None:
        return []
    result: list[dict[str, Any] | None] = []
    for bullish, bearish in zip(setup.bullish_counts, setup.bearish_counts):
        if bullish:
            result.append({"direction": "bullish", "count": bullish})
        elif bearish:
            result.append({"direction": "bearish", "count": bearish})
        else:
            result.append(None)
    return result


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
