"""Time-of-day relative volume: today's pace against its own recent history.

RVOL answers "is more or less volume trading right now than usual at this
point in the session" — not against yesterday's total, which conflates two
different session lengths, but against the *same clock time* on prior
sessions. Comparing raw cumulative volume to a same-time-of-day baseline
avoids the trap of a naive intraday-vs-full-day average, which always reads
"low" in the morning and "high" by the close regardless of what is actually
happening.

This module has no notion of when a US session opens, when lunch goes
quiet, or when the close prints extra volume — none of that is hardcoded
here. Every bar is placed into a session and a time-of-day bucket by a
single injected ``session_bucket`` function, so the module stays exchange-
and calendar-agnostic and is trivially testable with synthetic clocks.

Two situations must never resolve to a padded ratio of 1.0x: too few
buckets have elapsed in the current session to trust a comparison ("early
session"), or there is not enough matching history to build the baseline
("missing history"). Both return a typed unavailable result instead.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Callable, Hashable, NamedTuple, Sequence

from .models import OHLCVBar, require_utc
from .temporal import select_bars_as_of


RVOL_VERSION = "rvol-tod-v1"

# A single bar cannot be compared to anything; it *is* the opening print.
# Two gives the ratio at least one interval's worth of accumulated trading
# beyond that print before it is trusted.
DEFAULT_MINIMUM_BUCKETS_ELAPSED = 2

# Twenty sessions is the conventional "recent history" window for volume
# baselines (about one trading month) — long enough to average over
# day-of-week effects, short enough to track a genuine regime change.
DEFAULT_LOOKBACK_SESSIONS = 20


class SessionBucket(NamedTuple):
    """Where one bar sits: which session, and which time-of-day slot.

    Both fields must be stable and comparable across sessions for the same
    clock time — e.g. ``session`` might be an exchange-calendar date and
    ``bucket`` an (hour, minute) pair in exchange time. This module never
    computes either itself; the caller supplies the single function that
    does, which is what keeps this module free of hardcoded session times.
    """

    session: Hashable
    bucket: Hashable


SessionBucketer = Callable[[OHLCVBar], SessionBucket]


@dataclass(frozen=True, slots=True)
class RelativeVolumeResult:
    """Current session's cumulative volume vs. the same-time-of-day mean.

    ``lookback_sessions`` is the disclosed N from the spec: the number of
    prior sessions the baseline is built from. A live result always used
    exactly that many — never fewer dressed up as complete. ``sessions_used``
    is retained on an unavailable result purely as a diagnostic (how far the
    search got), never as a substitute baseline.
    """

    symbol: str
    interval: str
    as_of: datetime
    session: str
    bucket: str
    buckets_elapsed: int
    minimum_buckets_elapsed: int
    lookback_sessions: int
    sessions_used: int
    current_cumulative_volume: float | None
    historical_mean_cumulative_volume: float | None
    ratio: float | None
    quality_status: str
    missing_reason: str | None
    method_version: str = RVOL_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if not self.symbol.strip() or not self.interval.strip():
            raise ValueError("symbol and interval are required")
        if self.buckets_elapsed < 0:
            raise ValueError("buckets_elapsed must be non-negative")
        if self.minimum_buckets_elapsed < 1:
            raise ValueError("minimum_buckets_elapsed must be at least one")
        if self.lookback_sessions < 1:
            raise ValueError("lookback_sessions must be at least one")
        if self.sessions_used < 0 or self.sessions_used > self.lookback_sessions:
            raise ValueError("sessions_used must be between 0 and lookback_sessions")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")

        if self.quality_status == "unavailable":
            values = (
                self.current_cumulative_volume,
                self.historical_mean_cumulative_volume,
                self.ratio,
            )
            if any(value is not None for value in values):
                raise ValueError("an unavailable result carries no volumes or ratio")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
            return

        if self.sessions_used != self.lookback_sessions:
            raise ValueError("a live result must use exactly lookback_sessions")
        if self.buckets_elapsed < self.minimum_buckets_elapsed:
            raise ValueError("a live result requires the minimum buckets elapsed")
        floats = (
            self.current_cumulative_volume,
            self.historical_mean_cumulative_volume,
            self.ratio,
        )
        if any(value is None or not isfinite(value) for value in floats):
            raise ValueError("a live result requires finite volumes and ratio")
        assert self.current_cumulative_volume is not None
        assert self.historical_mean_cumulative_volume is not None
        assert self.ratio is not None
        if self.current_cumulative_volume < 0:
            raise ValueError("current_cumulative_volume must be non-negative")
        if self.historical_mean_cumulative_volume <= 0:
            raise ValueError("historical_mean_cumulative_volume must be positive")
        if self.ratio != self.current_cumulative_volume / self.historical_mean_cumulative_volume:
            raise ValueError(
                "ratio must equal current volume divided by the historical mean"
            )
        if self.missing_reason is not None:
            raise ValueError("a live result cannot carry a missing reason")


def time_of_day_relative_volume(
    bars: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    session_bucket: SessionBucketer,
    lookback_sessions: int = DEFAULT_LOOKBACK_SESSIONS,
    minimum_buckets_elapsed: int = DEFAULT_MINIMUM_BUCKETS_ELAPSED,
) -> RelativeVolumeResult:
    """Current cumulative volume ÷ mean cumulative volume at the same bucket.

    ``bars`` must be completed candles from a single symbol and a single
    intraday interval. PIT selection (via ``select_bars_as_of``) drops
    anything not yet knowable as of ``decision_cutoff``. The current session
    is whichever session contains the latest knowable bar; the baseline is
    built from the ``lookback_sessions`` sessions immediately before it, each
    contributing its own cumulative volume through the bar matching the
    current session's latest time-of-day bucket. A prior session missing
    that exact bucket does not contribute a fallback value — no
    interpolation, no padding — it simply does not count toward the N.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if lookback_sessions < 1:
        raise ValueError("lookback_sessions must be at least one")
    if minimum_buckets_elapsed < 1:
        raise ValueError("minimum_buckets_elapsed must be at least one")

    rows = tuple(bars)
    if not rows:
        raise ValueError("rvol requires at least one bar")
    _validate_bars(rows)
    symbol = rows[0].symbol
    interval = rows[0].interval

    selected = select_bars_as_of(rows, decision_cutoff)
    if not selected:
        return _unavailable(
            symbol,
            interval,
            decision_cutoff,
            "",
            "",
            0,
            minimum_buckets_elapsed,
            lookback_sessions,
            0,
            "no completed bars are knowable as of the cutoff",
        )

    grouped: dict[Hashable, list[tuple[OHLCVBar, Hashable]]] = {}
    for row in selected:
        located = session_bucket(row)
        grouped.setdefault(located.session, []).append((row, located.bucket))

    ordered_sessions = sorted(
        grouped.items(),
        key=lambda item: min(entry[0].closed_at for entry in item[1]),
    )
    current_session_key, current_entries = ordered_sessions[-1]
    current_entries = sorted(current_entries, key=lambda entry: entry[0].closed_at)
    buckets_elapsed = len(current_entries)
    current_bucket = current_entries[-1][1]
    current_cumulative_volume = sum(row.volume for row, _ in current_entries)

    if buckets_elapsed < minimum_buckets_elapsed:
        return _unavailable(
            symbol,
            interval,
            decision_cutoff,
            str(current_session_key),
            str(current_bucket),
            buckets_elapsed,
            minimum_buckets_elapsed,
            lookback_sessions,
            0,
            f"early session: {buckets_elapsed} of {minimum_buckets_elapsed} "
            "minimum buckets elapsed",
        )

    prior_sessions = ordered_sessions[:-1][-lookback_sessions:]
    matched_cumulatives: list[float] = []
    for _, session_entries in prior_sessions:
        ordered_entries = sorted(session_entries, key=lambda entry: entry[0].closed_at)
        running = 0.0
        matched: float | None = None
        for row, bucket in ordered_entries:
            running += row.volume
            if bucket == current_bucket:
                matched = running
        if matched is not None:
            matched_cumulatives.append(matched)

    sessions_used = len(matched_cumulatives)
    if sessions_used < lookback_sessions:
        return _unavailable(
            symbol,
            interval,
            decision_cutoff,
            str(current_session_key),
            str(current_bucket),
            buckets_elapsed,
            minimum_buckets_elapsed,
            lookback_sessions,
            sessions_used,
            f"insufficient history: {sessions_used} of {lookback_sessions} prior "
            "sessions have this time-of-day bucket",
        )

    historical_mean = sum(matched_cumulatives) / sessions_used
    if historical_mean <= 0.0:
        return _unavailable(
            symbol,
            interval,
            decision_cutoff,
            str(current_session_key),
            str(current_bucket),
            buckets_elapsed,
            minimum_buckets_elapsed,
            lookback_sessions,
            sessions_used,
            "historical baseline has no volume at this bucket",
        )

    return RelativeVolumeResult(
        symbol=symbol,
        interval=interval,
        as_of=decision_cutoff,
        session=str(current_session_key),
        bucket=str(current_bucket),
        buckets_elapsed=buckets_elapsed,
        minimum_buckets_elapsed=minimum_buckets_elapsed,
        lookback_sessions=lookback_sessions,
        sessions_used=sessions_used,
        current_cumulative_volume=current_cumulative_volume,
        historical_mean_cumulative_volume=historical_mean,
        ratio=current_cumulative_volume / historical_mean,
        quality_status="live",
        missing_reason=None,
    )


def _validate_bars(rows: tuple[OHLCVBar, ...]) -> None:
    if any(not row.complete for row in rows):
        raise ValueError("rvol requires completed candles")
    symbols = {row.symbol.upper() for row in rows}
    if len(symbols) > 1:
        raise ValueError("rvol requires a single symbol")
    intervals = {row.interval for row in rows}
    if len(intervals) > 1:
        raise ValueError("rvol requires a single bar interval")
    interval = next(iter(intervals))
    if interval in {"day", "week"}:
        raise ValueError("rvol requires an intraday bar interval")


def _unavailable(
    symbol: str,
    interval: str,
    as_of: datetime,
    session: str,
    bucket: str,
    buckets_elapsed: int,
    minimum_buckets_elapsed: int,
    lookback_sessions: int,
    sessions_used: int,
    reason: str,
) -> RelativeVolumeResult:
    return RelativeVolumeResult(
        symbol=symbol,
        interval=interval,
        as_of=as_of,
        session=session,
        bucket=bucket,
        buckets_elapsed=buckets_elapsed,
        minimum_buckets_elapsed=minimum_buckets_elapsed,
        lookback_sessions=lookback_sessions,
        sessions_used=sessions_used,
        current_cumulative_volume=None,
        historical_mean_cumulative_volume=None,
        ratio=None,
        quality_status="unavailable",
        missing_reason=reason,
    )
