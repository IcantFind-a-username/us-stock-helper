"""Realized volatility measured from completed bars only.

The scenario forecast needs a width, and the only honest source of one is what
the market has actually done. Every estimator here reports a number or says it
cannot — none ever falls back to a house default, because a fabricated width
would make every downstream range look equally trustworthy.

Three estimators live side by side, each producing the same
``VolatilityEstimate`` shape with its choice stamped explicitly in the
``estimator`` field (and a matching ``method_version``), so a consumer never
has to guess which formula produced a number:

``close_to_close`` (``VOLATILITY_VERSION``) uses only the sequence of closes —
the original estimator, unchanged.

``parkinson`` and ``garman_klass`` (both ``RANGE_VOLATILITY_VERSION``) use
each bar's own high/low (and, for Garman-Klass, open/close) range instead of
the gap between bars. They see intrabar movement close-to-close structurally
cannot, at the cost of assuming no drift and no jumps between bars. Because
``OHLCVBar`` already guarantees ``low <= min(open, close) <= max(open, close)
<= high``, every single-bar Garman-Klass term is provably non-negative, so a
degenerate (perfectly flat) window is the only way either range estimator's
aggregate variance reaches zero — handled the same way a flat close-to-close
window is: a typed unavailable result, never a manufactured zero.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, log, sqrt
from typing import Callable, Sequence

from .models import OHLCVBar, require_utc
from .temporal import select_bars_as_of


VOLATILITY_VERSION = "close-to-close-realized-v1"
RANGE_VOLATILITY_VERSION = "range-vol-v1"

_TRADING_DAYS_PER_YEAR = 252
# Regular US session bars per trading day. Extended hours are excluded because
# the gateway's candles follow the regular session.
_BARS_PER_DAY = {
    "1m": 390.0,
    "5m": 78.0,
    "15m": 26.0,
    "30m": 13.0,
    "60m": 6.5,
    "day": 1.0,
}
_MINIMUM_SAMPLE = 20

_LN2 = log(2.0)
# Garman & Klass (1980) open-close coefficient: 2*ln(2) - 1.
_GK_OPEN_CLOSE_COEFFICIENT = 2.0 * _LN2 - 1.0

_ESTIMATOR_VERSIONS = {
    "close_to_close": VOLATILITY_VERSION,
    "parkinson": RANGE_VOLATILITY_VERSION,
    "garman_klass": RANGE_VOLATILITY_VERSION,
}


@dataclass(frozen=True, slots=True)
class VolatilityEstimate:
    value: float | None
    sample_size: int
    interval: str
    as_of: datetime
    quality_status: str
    missing_reason: str | None
    estimator: str = "close_to_close"
    method_version: str = VOLATILITY_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if self.estimator not in _ESTIMATOR_VERSIONS:
            raise ValueError(
                "estimator must be close_to_close, parkinson, or garman_klass"
            )
        if self.method_version != _ESTIMATOR_VERSIONS[self.estimator]:
            raise ValueError("method_version does not match the estimator")
        if self.quality_status not in {"live", "unavailable"}:
            raise ValueError("quality_status must be live or unavailable")
        if self.quality_status == "live":
            if self.value is None or not isfinite(self.value) or self.value <= 0:
                raise ValueError("a live estimate requires a positive finite value")
            if self.missing_reason is not None:
                raise ValueError("a live estimate cannot carry a missing reason")
        else:
            if self.value is not None:
                raise ValueError("an unavailable estimate carries no value")
            if not (self.missing_reason or "").strip():
                raise ValueError("an unavailable estimate requires a reason")


def bars_per_year(interval: str) -> float:
    """Annualization factor for one bar of ``interval``."""

    if interval == "week":
        return 52.0
    per_day = _BARS_PER_DAY.get(interval)
    if per_day is None:
        raise ValueError(f"unsupported interval for volatility: {interval}")
    return per_day * _TRADING_DAYS_PER_YEAR


def estimate_annualized_volatility(
    bars: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    minimum_sample: int = _MINIMUM_SAMPLE,
) -> VolatilityEstimate:
    """Annualized close-to-close volatility from bars knowable at the cutoff."""

    require_utc(decision_cutoff, "decision_cutoff")
    cutoff = decision_cutoff
    rows, interval = _completed_single_interval_bars(bars)
    periods = bars_per_year(interval)
    if minimum_sample < 2:
        raise ValueError("minimum_sample must be at least two")

    selected = select_bars_as_of(rows, cutoff)
    returns = [
        log(selected[index].close / selected[index - 1].close)
        for index in range(1, len(selected))
    ]
    if len(returns) < minimum_sample:
        return _unavailable(
            len(returns),
            interval,
            cutoff,
            f"insufficient sample: {len(returns)} of {minimum_sample} returns",
            estimator="close_to_close",
        )

    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    annualized = sqrt(variance * periods)
    if not isfinite(annualized) or annualized <= 0.0:
        # A perfectly flat window is not zero risk; it is a window that cannot
        # tell us the risk. Saying zero would produce a forecast band of no
        # width at all, presented with the same confidence as a real one.
        return _unavailable(
            len(returns),
            interval,
            cutoff,
            "no price variation in the observed window",
            estimator="close_to_close",
        )
    return VolatilityEstimate(
        value=annualized,
        sample_size=len(returns),
        interval=interval,
        as_of=cutoff,
        quality_status="live",
        missing_reason=None,
        estimator="close_to_close",
    )


def estimate_parkinson_volatility(
    bars: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    minimum_sample: int = _MINIMUM_SAMPLE,
) -> VolatilityEstimate:
    """Annualized Parkinson (1980) high/low range volatility.

    Each completed bar contributes ``ln(high/low)^2 / (4 * ln 2)`` — no
    close-to-close differencing, so unlike
    :func:`estimate_annualized_volatility`, ``sample_size`` here counts
    *bars*, not returns: a single bar already carries a usable range
    observation.
    """

    return _range_volatility_estimate(
        bars,
        decision_cutoff,
        minimum_sample=minimum_sample,
        estimator="parkinson",
        per_bar_term=_parkinson_term,
    )


def estimate_garman_klass_volatility(
    bars: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    minimum_sample: int = _MINIMUM_SAMPLE,
) -> VolatilityEstimate:
    """Annualized Garman-Klass (1980) high/low/open/close range volatility.

    Each completed bar contributes
    ``0.5 * ln(high/low)^2 - (2*ln2 - 1) * ln(close/open)^2``. Given
    ``OHLCVBar``'s own invariant that ``high`` bounds both ``open`` and
    ``close`` from above and ``low`` bounds them from below, this per-bar
    term is always non-negative, so the aggregate can only reach zero on a
    perfectly flat window — handled as unavailable, the same as elsewhere in
    this module.
    """

    return _range_volatility_estimate(
        bars,
        decision_cutoff,
        minimum_sample=minimum_sample,
        estimator="garman_klass",
        per_bar_term=_garman_klass_term,
    )


def _range_volatility_estimate(
    bars: Sequence[OHLCVBar],
    decision_cutoff: datetime,
    *,
    minimum_sample: int,
    estimator: str,
    per_bar_term: Callable[[OHLCVBar], float],
) -> VolatilityEstimate:
    require_utc(decision_cutoff, "decision_cutoff")
    cutoff = decision_cutoff
    rows, interval = _completed_single_interval_bars(bars)
    periods = bars_per_year(interval)
    if minimum_sample < 1:
        raise ValueError("minimum_sample must be at least one")

    selected = select_bars_as_of(rows, cutoff)
    if len(selected) < minimum_sample:
        return _unavailable(
            len(selected),
            interval,
            cutoff,
            f"insufficient sample: {len(selected)} of {minimum_sample} bars",
            estimator=estimator,
        )

    terms = [per_bar_term(row) for row in selected]
    mean_variance = sum(terms) / len(terms)
    # per_bar_term is provably non-negative for every valid OHLCVBar, so
    # mean_variance can never be negative and sqrt is always safe here.
    annualized = sqrt(mean_variance * periods)
    if not isfinite(annualized) or annualized <= 0.0:
        # Every bar in the window had zero range (and, for Garman-Klass,
        # zero open-close move too) — a genuinely flat window, not a
        # measured zero. Same treatment as a flat close-to-close window.
        return _unavailable(
            len(selected),
            interval,
            cutoff,
            "no price variation in the observed window",
            estimator=estimator,
        )
    return VolatilityEstimate(
        value=annualized,
        sample_size=len(selected),
        interval=interval,
        as_of=cutoff,
        quality_status="live",
        missing_reason=None,
        estimator=estimator,
        method_version=_ESTIMATOR_VERSIONS[estimator],
    )


def _parkinson_term(bar: OHLCVBar) -> float:
    return (log(bar.high / bar.low) ** 2) / (4.0 * _LN2)


def _garman_klass_term(bar: OHLCVBar) -> float:
    return 0.5 * (log(bar.high / bar.low) ** 2) - _GK_OPEN_CLOSE_COEFFICIENT * (
        log(bar.close / bar.open) ** 2
    )


def _completed_single_interval_bars(
    bars: Sequence[OHLCVBar],
) -> tuple[tuple[OHLCVBar, ...], str]:
    rows = tuple(bars)
    if any(not row.complete for row in rows):
        raise ValueError("volatility requires completed candles")
    intervals = {row.interval for row in rows}
    if len(intervals) > 1:
        raise ValueError("volatility requires a single bar interval")
    interval = next(iter(intervals), "day")
    return rows, interval


def _unavailable(
    sample_size: int,
    interval: str,
    cutoff: datetime,
    reason: str,
    *,
    estimator: str = "close_to_close",
) -> VolatilityEstimate:
    return VolatilityEstimate(
        value=None,
        sample_size=sample_size,
        interval=interval,
        as_of=cutoff,
        quality_status="unavailable",
        missing_reason=reason,
        estimator=estimator,
        method_version=_ESTIMATOR_VERSIONS[estimator],
    )
