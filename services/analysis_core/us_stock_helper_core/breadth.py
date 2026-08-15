"""Market breadth measured from a universe of daily bar series.

Breadth answers a question no single symbol can: how many names are actually
participating in today's move, not just how the index closed. Every function
here takes a ``universe`` — a mapping of symbol to that symbol's own daily
bar history — and reports a metric computed only from bars knowable as of the
supplied cutoff.

This module never labels its own scope. A universe built from a five-name
watchlist and one built from the full exchange produce the same shaped
result; the caller is responsible for choosing the honest label (自选广度 vs
市场广度) based on how the universe was assembled. That is why every result
carries ``universe_size`` — so a consumer can decide, and disclose, what the
number actually covers.

Every metric is independently gated by a minimum sample on two axes: the
number of symbols in the universe, and — separately — the number of symbols
with enough of their *own* history to compute that particular metric (its
"eligible" count). Falling short on either axis returns a typed unavailable
result, never a zero or a partial number dressed up as complete.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Mapping, Sequence

from .indicators import moving_average
from .models import OHLCVBar, require_utc
from .temporal import select_bars_as_of


BREADTH_VERSION = "breadth-v1"

# Five names is the smallest group for which "most of the universe advanced"
# is a meaningful sentence rather than a description of one or two stocks.
DEFAULT_MINIMUM_UNIVERSE = 5

MA50_PERIOD = 50
MA200_PERIOD = 200

# A 52-week (trading-day) lookback is the conventional new-high/new-low
# window; callers with shorter history (or who want a faster-moving reading)
# may pass a smaller value explicitly.
DEFAULT_NEW_HIGH_LOW_LOOKBACK = 252


@dataclass(frozen=True, slots=True)
class BreadthPoint:
    """One day's advance/decline reading, and the running cumulative line."""

    as_of: datetime
    advancers: int
    decliners: int
    unchanged: int
    net: int
    cumulative: int

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        for name in ("advancers", "decliners", "unchanged"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.net != self.advancers - self.decliners:
            raise ValueError("net must equal advancers minus decliners")


@dataclass(frozen=True, slots=True)
class AdvanceDeclineResult:
    """The advance/decline line over the days each symbol could report.

    Each point aggregates only symbols that had both a current and a prior
    completed bar as of the point's date (via each symbol's own history, not
    a shared calendar assumption), and only publishes a point when at least
    ``minimum_universe`` symbols contributed that day — an early date with a
    handful of newly listed symbols is excluded rather than shown as if it
    described the whole universe.
    """

    universe_size: int
    minimum_universe: int
    points: tuple[BreadthPoint, ...]
    quality_status: str
    missing_reason: str | None
    method_version: str = BREADTH_VERSION

    def __post_init__(self) -> None:
        if self.universe_size < 0 or self.minimum_universe < 1:
            raise ValueError("universe_size and minimum_universe must be non-negative")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "unavailable":
            if self.points:
                raise ValueError("an unavailable result carries no points")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
        else:
            if not self.points:
                raise ValueError("a live result requires at least one point")
            if self.missing_reason is not None:
                raise ValueError("a live result cannot carry a missing reason")


@dataclass(frozen=True, slots=True)
class PercentAboveMAResult:
    """Percent of the universe closing above its own trailing moving average."""

    as_of: datetime
    universe_size: int
    minimum_universe: int
    period: int
    eligible_symbols: int
    percent_above: float | None
    quality_status: str
    missing_reason: str | None
    method_version: str = BREADTH_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.universe_size < 0 or self.minimum_universe < 1:
            raise ValueError("universe_size and minimum_universe must be non-negative")
        if self.eligible_symbols < 0 or self.eligible_symbols > self.universe_size:
            raise ValueError("eligible_symbols must be between 0 and universe_size")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "unavailable":
            if self.percent_above is not None:
                raise ValueError("an unavailable result carries no percentage")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
        else:
            if self.percent_above is None or not isfinite(self.percent_above):
                raise ValueError("a live result requires a finite percentage")
            if not 0.0 <= self.percent_above <= 100.0:
                raise ValueError("percent_above must be between 0 and 100")
            if self.missing_reason is not None:
                raise ValueError("a live result cannot carry a missing reason")


@dataclass(frozen=True, slots=True)
class NewHighLowResult:
    """New highs minus new lows over a trailing lookback of intraday extremes."""

    as_of: datetime
    universe_size: int
    minimum_universe: int
    lookback: int
    eligible_symbols: int
    new_highs: int | None
    new_lows: int | None
    differential: int | None
    quality_status: str
    missing_reason: str | None
    method_version: str = BREADTH_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if self.universe_size < 0 or self.minimum_universe < 1:
            raise ValueError("universe_size and minimum_universe must be non-negative")
        if self.eligible_symbols < 0 or self.eligible_symbols > self.universe_size:
            raise ValueError("eligible_symbols must be between 0 and universe_size")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "unavailable":
            if (
                self.new_highs is not None
                or self.new_lows is not None
                or self.differential is not None
            ):
                raise ValueError("an unavailable result carries no counts")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable result requires a reason")
        else:
            if self.new_highs is None or self.new_lows is None:
                raise ValueError("a live result requires both counts")
            if self.new_highs < 0 or self.new_lows < 0:
                raise ValueError("counts must be non-negative")
            if self.differential != self.new_highs - self.new_lows:
                raise ValueError("differential must equal new_highs minus new_lows")
            if self.missing_reason is not None:
                raise ValueError("a live result cannot carry a missing reason")


def advance_decline_line(
    universe: Mapping[str, Sequence[OHLCVBar]],
    decision_cutoff: datetime,
    *,
    minimum_universe: int = DEFAULT_MINIMUM_UNIVERSE,
) -> AdvanceDeclineResult:
    """Advance/decline line: net advancers-minus-decliners, accumulated.

    Every symbol's own bar history is walked independently: for each pair of
    consecutive completed bars knowable as of ``decision_cutoff``, that
    symbol contributes one advance, decline, or unchanged event dated by the
    later bar's ``closed_at``. Events are then grouped by date; a date's
    point is only published when at least ``minimum_universe`` symbols
    contributed that day.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if minimum_universe < 1:
        raise ValueError("minimum_universe must be at least one")
    _validate_universe(universe)

    universe_size = len(universe)
    if universe_size < minimum_universe:
        return AdvanceDeclineResult(
            universe_size=universe_size,
            minimum_universe=minimum_universe,
            points=(),
            quality_status="unavailable",
            missing_reason=(
                f"universe too small: {universe_size} of {minimum_universe} symbols"
            ),
        )

    events_by_date: dict[datetime, list[str]] = {}
    for bars in universe.values():
        pit_bars = select_bars_as_of(bars, decision_cutoff)
        for index in range(1, len(pit_bars)):
            previous_close = pit_bars[index - 1].close
            current = pit_bars[index]
            if current.close > previous_close:
                direction = "up"
            elif current.close < previous_close:
                direction = "down"
            else:
                direction = "flat"
            events_by_date.setdefault(current.closed_at, []).append(direction)

    points: list[BreadthPoint] = []
    cumulative = 0
    for as_of in sorted(events_by_date):
        directions = events_by_date[as_of]
        if len(directions) < minimum_universe:
            continue
        advancers = sum(1 for value in directions if value == "up")
        decliners = sum(1 for value in directions if value == "down")
        unchanged = sum(1 for value in directions if value == "flat")
        net = advancers - decliners
        cumulative += net
        points.append(
            BreadthPoint(
                as_of=as_of,
                advancers=advancers,
                decliners=decliners,
                unchanged=unchanged,
                net=net,
                cumulative=cumulative,
            )
        )

    if not points:
        return AdvanceDeclineResult(
            universe_size=universe_size,
            minimum_universe=minimum_universe,
            points=(),
            quality_status="unavailable",
            missing_reason="no date has enough symbols reporting a completed pair of bars",
        )

    return AdvanceDeclineResult(
        universe_size=universe_size,
        minimum_universe=minimum_universe,
        points=tuple(points),
        quality_status="live",
        missing_reason=None,
    )


def percent_above_moving_average(
    universe: Mapping[str, Sequence[OHLCVBar]],
    decision_cutoff: datetime,
    *,
    period: int,
    minimum_universe: int = DEFAULT_MINIMUM_UNIVERSE,
) -> PercentAboveMAResult:
    """Percent of the universe whose latest close sits above its own MA(period).

    A symbol is "eligible" once it has at least ``period`` completed bars
    knowable as of the cutoff — the same threshold ``moving_average`` needs
    to publish a value. "Above" requires a strictly greater close; an exact
    tie counts toward neither above nor below.
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if period <= 0:
        raise ValueError("period must be positive")
    if minimum_universe < 1:
        raise ValueError("minimum_universe must be at least one")
    _validate_universe(universe)

    universe_size = len(universe)
    above_count = 0
    eligible_symbols = 0
    for bars in universe.values():
        pit_bars = select_bars_as_of(bars, decision_cutoff)
        closes = [row.close for row in pit_bars]
        ma_value = moving_average(closes, period)
        if ma_value is None:
            continue
        eligible_symbols += 1
        if closes[-1] > ma_value:
            above_count += 1

    if universe_size < minimum_universe or eligible_symbols < minimum_universe:
        return PercentAboveMAResult(
            as_of=decision_cutoff,
            universe_size=universe_size,
            minimum_universe=minimum_universe,
            period=period,
            eligible_symbols=eligible_symbols,
            percent_above=None,
            quality_status="unavailable",
            missing_reason=(
                f"insufficient eligible symbols: {eligible_symbols} of "
                f"{minimum_universe} have {period}+ bars (universe {universe_size})"
            ),
        )

    return PercentAboveMAResult(
        as_of=decision_cutoff,
        universe_size=universe_size,
        minimum_universe=minimum_universe,
        period=period,
        eligible_symbols=eligible_symbols,
        percent_above=100.0 * above_count / eligible_symbols,
        quality_status="live",
        missing_reason=None,
    )


def new_high_low_differential(
    universe: Mapping[str, Sequence[OHLCVBar]],
    decision_cutoff: datetime,
    *,
    lookback: int = DEFAULT_NEW_HIGH_LOW_LOOKBACK,
    minimum_universe: int = DEFAULT_MINIMUM_UNIVERSE,
) -> NewHighLowResult:
    """New-high count minus new-low count over a trailing ``lookback`` window.

    A symbol makes a new high when its latest bar's ``high`` is at least the
    maximum ``high`` across the trailing ``lookback`` completed bars
    (inclusive), and a new low symmetrically on ``low``. A symbol is
    "eligible" once it has at least ``lookback`` bars knowable as of the
    cutoff; a single bar may count toward both tallies (an outside bar that
    is simultaneously the window's highest high and lowest low).
    """

    require_utc(decision_cutoff, "decision_cutoff")
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if minimum_universe < 1:
        raise ValueError("minimum_universe must be at least one")
    _validate_universe(universe)

    universe_size = len(universe)
    new_highs = 0
    new_lows = 0
    eligible_symbols = 0
    for bars in universe.values():
        pit_bars = select_bars_as_of(bars, decision_cutoff)
        if len(pit_bars) < lookback:
            continue
        eligible_symbols += 1
        window = pit_bars[-lookback:]
        highest_high = max(row.high for row in window)
        lowest_low = min(row.low for row in window)
        if window[-1].high >= highest_high:
            new_highs += 1
        if window[-1].low <= lowest_low:
            new_lows += 1

    if universe_size < minimum_universe or eligible_symbols < minimum_universe:
        return NewHighLowResult(
            as_of=decision_cutoff,
            universe_size=universe_size,
            minimum_universe=minimum_universe,
            lookback=lookback,
            eligible_symbols=eligible_symbols,
            new_highs=None,
            new_lows=None,
            differential=None,
            quality_status="unavailable",
            missing_reason=(
                f"insufficient eligible symbols: {eligible_symbols} of "
                f"{minimum_universe} have {lookback}+ bars (universe {universe_size})"
            ),
        )

    return NewHighLowResult(
        as_of=decision_cutoff,
        universe_size=universe_size,
        minimum_universe=minimum_universe,
        lookback=lookback,
        eligible_symbols=eligible_symbols,
        new_highs=new_highs,
        new_lows=new_lows,
        differential=new_highs - new_lows,
        quality_status="live",
        missing_reason=None,
    )


def _validate_universe(universe: Mapping[str, Sequence[OHLCVBar]]) -> None:
    for symbol, bars in universe.items():
        if not symbol.strip():
            raise ValueError("universe symbols must be non-empty")
        for row in bars:
            if row.symbol.upper() != symbol.upper():
                raise ValueError(f"bar symbol does not match universe key: {symbol}")
            if row.interval != "day":
                raise ValueError("breadth requires daily bars")
            if not row.complete:
                raise ValueError("breadth requires completed candles")
