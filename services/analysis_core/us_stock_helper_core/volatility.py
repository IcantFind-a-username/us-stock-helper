"""Realized volatility measured from completed bars only.

The scenario forecast needs a width, and the only honest source of one is what
the market has actually done. This estimator reports a number or says it cannot
— it never falls back to a house default, because a fabricated width would make
every downstream range look equally trustworthy.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, log, sqrt
from typing import Sequence

from .models import OHLCVBar, require_utc
from .temporal import select_bars_as_of


VOLATILITY_VERSION = "close-to-close-realized-v1"

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


@dataclass(frozen=True, slots=True)
class VolatilityEstimate:
    value: float | None
    sample_size: int
    interval: str
    as_of: datetime
    quality_status: str
    missing_reason: str | None
    method_version: str = VOLATILITY_VERSION

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
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
    rows = tuple(bars)
    if any(not row.complete for row in rows):
        raise ValueError("volatility requires completed candles")
    intervals = {row.interval for row in rows}
    if len(intervals) > 1:
        raise ValueError("volatility requires a single bar interval")
    interval = next(iter(intervals), "day")
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
        )
    return VolatilityEstimate(
        value=annualized,
        sample_size=len(returns),
        interval=interval,
        as_of=cutoff,
        quality_status="live",
        missing_reason=None,
    )


def _unavailable(
    sample_size: int, interval: str, cutoff: datetime, reason: str
) -> VolatilityEstimate:
    return VolatilityEstimate(
        value=None,
        sample_size=sample_size,
        interval=interval,
        as_of=cutoff,
        quality_status="unavailable",
        missing_reason=reason,
    )
