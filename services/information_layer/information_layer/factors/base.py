"""What a scoring factor is allowed to say, and what it must never say.

A factor answers one of two things: a number it measured, or the reason it
could not measure anything. There is deliberately no third state. Returning
0.0 when a source is unreachable is the failure mode this whole module exists
to make impossible — downstream, a measured neutral and a blind spot are
indistinguishable, and the score silently drifts to the middle in proportion
to how little the system can see.

A measured reading also has to prove it could have been known at the cutoff.
Every number it was computed from carries the moment its publisher made it
public, and a reading whose newest input postdates the cutoff is rejected at
construction rather than reviewed later. That is the only place in this
package where a future function can be stopped cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Iterable


FACTOR_MACRO = "macro"
FACTOR_GEOPOLITICS = "geopolitics"
FACTOR_INSTITUTIONAL_FLOW = "institutional_flow"
FACTOR_FUNDAMENTALS = "fundamentals"


class FactorUnavailable(str, Enum):
    """Why a factor produced no number.

    These are not error codes for operators alone. A reader deciding whether
    to trust a 78% coverage score needs to know whether the missing 22% is a
    broken fetch, a company that has not reported yet, or a factor this
    system has decided on purpose not to guess at.
    """

    SOURCE_UNREACHABLE = "source_unreachable"
    SOURCE_MALFORMED = "source_malformed"
    NO_DATA_AT_CUTOFF = "no_data_at_cutoff"
    INSUFFICIENT_HISTORY = "insufficient_history"
    STALE_BEYOND_WINDOW = "stale_beyond_window"
    NO_QUALIFIED_SOURCE = "no_qualified_source"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class FactorInput:
    """One published number a factor was computed from.

    ``observed_at`` is the period or observation date the number describes and
    ``available_at`` is when its publisher released it. Keeping them apart is
    what makes a lagged factor honest: a quarter that ended in June and was
    filed in July is two different facts, and only the second one bounds what
    a decision could have used.
    """

    name: str
    value: float
    observed_at: datetime
    available_at: datetime
    source_url: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a factor input needs a name")
        if not isfinite(self.value):
            raise ValueError(f"{self.name} must be a finite number")
        _require_aware(self.observed_at, "observed_at")
        _require_aware(self.available_at, "available_at")
        if self.available_at < self.observed_at:
            raise ValueError(
                f"{self.name} cannot be published before the period it describes"
            )
        if not self.source_url.startswith("https://"):
            raise ValueError("a factor input must cite an HTTPS source")


@dataclass(frozen=True, slots=True)
class FactorReading:
    factor: str
    method_version: str
    as_of: datetime
    # Exactly one of these two is set. Both set would let a caller publish
    # "0.0 because the source was down"; neither set says nothing at all.
    value: float | None
    unavailable_reason: FactorUnavailable | None
    detail: str
    inputs: tuple[FactorInput, ...] = ()
    available_at: datetime | None = None
    lag_seconds: float | None = None

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        if not self.factor.strip() or not self.method_version.strip():
            raise ValueError("a reading needs a factor name and a method version")
        if (self.value is None) == (self.unavailable_reason is None):
            raise ValueError(
                "a reading is either a measured value or a stated reason, never both"
            )
        if self.value is not None:
            if not isfinite(self.value) or not -1.0 <= self.value <= 1.0:
                raise ValueError("a measured factor must be within [-1, 1]")
            if not self.inputs:
                raise ValueError("a measured factor must cite what it measured")
        if not self.detail.strip():
            raise ValueError("a reading must explain itself in words")

    @property
    def measured_value(self) -> float | None:
        """Alias that reads correctly at call sites deciding what to score."""

        return self.value

    @classmethod
    def measured(
        cls,
        *,
        factor: str,
        method_version: str,
        as_of: datetime,
        value: float,
        detail: str,
        inputs: Iterable[FactorInput],
    ) -> "FactorReading":
        collected = tuple(inputs)
        if not collected:
            raise ValueError("a measured factor must cite what it measured")
        _require_aware(as_of, "as_of")
        newest = max(item.available_at for item in collected)
        if newest > as_of:
            raise ValueError(
                "a factor may not be measured from data published after its cutoff"
            )
        return cls(
            factor=factor,
            method_version=method_version,
            as_of=as_of,
            value=float(value),
            unavailable_reason=None,
            detail=detail,
            inputs=collected,
            available_at=newest,
            lag_seconds=(as_of - newest).total_seconds(),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        factor: str,
        method_version: str,
        as_of: datetime,
        reason: FactorUnavailable,
        detail: str,
        inputs: Iterable[FactorInput] = (),
    ) -> "FactorReading":
        return cls(
            factor=factor,
            method_version=method_version,
            as_of=as_of,
            value=None,
            unavailable_reason=reason,
            detail=detail,
            inputs=tuple(inputs),
            available_at=None,
            lag_seconds=None,
        )


def clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))
