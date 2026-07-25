"""Point-in-time capital participation derived from cumulative flow buckets."""

from datetime import datetime, timedelta
from math import isclose, isfinite
from typing import Iterable

from .models import CapitalFlowPoint, OHLCVBar, ParticipationBar, require_utc


METHOD_VERSION = "order-size-activity-share-v1"
_MINUTE = timedelta(minutes=1)


def build_participation_bars(
    flow_points: Iterable[CapitalFlowPoint],
    completed_bars: Iterable[OHLCVBar],
    decision_cutoff: datetime,
    *,
    noise_floor: float = 1e-9,
    bucket_abs_tol: float = 1e-6,
    bucket_rel_tol: float = 1e-9,
) -> tuple[ParticipationBar, ...]:
    """Build one deterministic order-size activity bar for each completed candle.

    ``main`` and ``retail`` label order-size activity proxies only.  They do
    not identify market participants or account ownership.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    _validate_tolerances(noise_floor, bucket_abs_tol, bucket_rel_tol)
    points = tuple(flow_points)
    bars = tuple(completed_bars)
    _validate_flow_points(points, decision_cutoff, bucket_abs_tol, bucket_rel_tol)
    _validate_completed_bars(bars, decision_cutoff)

    if points and bars and any(point.symbol != bar.symbol for point in points for bar in bars):
        raise ValueError("flow points and completed bars must have equal symbol")

    by_timestamp = {point.timestamp: point for point in points}
    return tuple(
        _build_bar(bar, by_timestamp, noise_floor)
        for bar in bars
    )


def _validate_tolerances(
    noise_floor: float, bucket_abs_tol: float, bucket_rel_tol: float
) -> None:
    for value, name in (
        (noise_floor, "noise_floor"),
        (bucket_abs_tol, "bucket_abs_tol"),
        (bucket_rel_tol, "bucket_rel_tol"),
    ):
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")


def _validate_flow_points(
    points: tuple[CapitalFlowPoint, ...],
    decision_cutoff: datetime,
    bucket_abs_tol: float,
    bucket_rel_tol: float,
) -> None:
    previous: CapitalFlowPoint | None = None
    for point in points:
        if point.available_at > decision_cutoff:
            raise ValueError("flow point is after decision cutoff")
        if previous is not None and point.timestamp <= previous.timestamp:
            raise ValueError("flow point timestamps must be strictly increasing")
        buckets = point.super_net + point.big_net + point.mid_net + point.small_net
        if not isclose(
            point.total_net,
            buckets,
            abs_tol=bucket_abs_tol,
            rel_tol=bucket_rel_tol,
        ):
            raise ValueError("flow point total_net does not match bucket sum")
        previous = point


def _validate_completed_bars(
    bars: tuple[OHLCVBar, ...], decision_cutoff: datetime
) -> None:
    for bar in bars:
        if not bar.complete:
            raise ValueError("participation requires completed candles")
        if bar.closed_at > decision_cutoff or bar.available_at > decision_cutoff:
            raise ValueError("completed candle is after decision cutoff")


def _build_bar(
    bar: OHLCVBar,
    points: dict[datetime, CapitalFlowPoint],
    noise_floor: float,
) -> ParticipationBar:
    if bar.interval in {"day", "week"}:
        return _unavailable(bar, "unsupported interval in v1", 0.0, points)

    duration_seconds = (bar.closed_at - bar.opened_at).total_seconds()
    expected_delta_count = duration_seconds / _MINUTE.total_seconds()
    if expected_delta_count <= 0 or not expected_delta_count.is_integer():
        return _unavailable(bar, "unsupported intraday cadence", 0.0, points)

    observed_delta_count = 0
    mixed_session = len(
        {
            point.session
            for timestamp, point in points.items()
            if bar.opened_at <= timestamp <= bar.closed_at
        }
    ) > 1
    main_activity = 0.0
    retail_activity = 0.0
    net_flow = 0.0
    expected_time = bar.opened_at + _MINUTE
    while expected_time <= bar.closed_at:
        previous = points.get(expected_time - _MINUTE)
        current = points.get(expected_time)
        if previous is not None and current is not None:
            if previous.session != current.session:
                mixed_session = True
            else:
                observed_delta_count += 1
                main_activity += abs(current.super_net - previous.super_net)
                main_activity += abs(current.big_net - previous.big_net)
                retail_activity += abs(current.mid_net - previous.mid_net)
                retail_activity += abs(current.small_net - previous.small_net)
                net_flow += current.total_net - previous.total_net
        expected_time += _MINUTE

    coverage = observed_delta_count / expected_delta_count
    if mixed_session:
        return _unavailable(bar, "mixed session flow points", coverage, points)
    if observed_delta_count != expected_delta_count:
        return _unavailable(bar, "incomplete minute coverage", coverage, points)

    denominator = main_activity + retail_activity
    if denominator <= noise_floor:
        return _unavailable(bar, "zero activity denominator", coverage, points)
    main_share = main_activity / denominator
    return ParticipationBar(
        symbol=bar.symbol,
        interval=bar.interval,
        closed_at=bar.closed_at,
        available_at=_available_at(bar, points),
        main_share=main_share,
        retail_share=1.0 - main_share,
        main_activity=main_activity,
        retail_activity=retail_activity,
        net_flow=net_flow,
        coverage=coverage,
        quality_status="live",
        missing_reason=None,
        method_version=METHOD_VERSION,
    )


def _unavailable(
    bar: OHLCVBar,
    missing_reason: str,
    coverage: float,
    points: dict[datetime, CapitalFlowPoint],
) -> ParticipationBar:
    return ParticipationBar(
        symbol=bar.symbol,
        interval=bar.interval,
        closed_at=bar.closed_at,
        available_at=_available_at(bar, points),
        main_share=None,
        retail_share=None,
        main_activity=None,
        retail_activity=None,
        net_flow=None,
        coverage=coverage,
        quality_status="unavailable",
        missing_reason=missing_reason,
        method_version=METHOD_VERSION,
    )


def _available_at(
    bar: OHLCVBar, points: dict[datetime, CapitalFlowPoint]
) -> datetime:
    point_times = (
        point.available_at
        for timestamp, point in points.items()
        if bar.opened_at <= timestamp <= bar.closed_at
    )
    return max((bar.available_at, *point_times))
