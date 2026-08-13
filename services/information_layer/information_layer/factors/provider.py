"""Answer for all four soft factors at once, without letting any of them fail loudly.

The decision chain asks for a snapshot and gets four readings back, always.
A source being down changes what the readings say, never whether they arrive:
a macro outage must not cost the caller its fundamentals, and neither may
raise into the scoring path, because the scorer's job is to redistribute
weight across what it could see and it cannot do that if it never runs.

The provider deliberately owns no HTTP itself. It resolves a ticker to a
filer, delegates, and converts anything unexpected into a stated reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .base import (
    FACTOR_FUNDAMENTALS,
    FACTOR_MACRO,
    FactorReading,
    FactorUnavailable,
)
from .fundamentals import SEC_FUNDAMENTALS_METHOD_VERSION
from .macro import TREASURY_MACRO_METHOD_VERSION
from .unsupported import geopolitics_reading, institutional_flow_reading


class FundamentalsSource(Protocol):
    def reading(self, *, cik: str, as_of: datetime) -> FactorReading:
        ...


class MacroSource(Protocol):
    def reading(self, *, as_of: datetime) -> FactorReading:
        ...


class CikLookup(Protocol):
    def cik_for(self, ticker: str) -> str | None:
        ...


@dataclass(frozen=True, slots=True)
class FactorSnapshot:
    symbol: str
    as_of: datetime
    macro: FactorReading
    geopolitics: FactorReading
    institutional_flow: FactorReading
    fundamentals: FactorReading

    def readings(self) -> tuple[FactorReading, ...]:
        return (
            self.macro,
            self.geopolitics,
            self.institutional_flow,
            self.fundamentals,
        )

    def unavailable_reasons(self) -> tuple[tuple[str, FactorUnavailable], ...]:
        """Which factors produced nothing, and why, for the caller to surface.

        The scorer already reports *that* a factor was missing. Without the
        reason travelling alongside it, a reader cannot tell a company that
        has not filed yet from a source that has been broken for a week.
        """

        return tuple(
            (reading.factor, reading.unavailable_reason)
            for reading in self.readings()
            if reading.unavailable_reason is not None
        )


class PublicFactorProvider:
    def __init__(
        self,
        *,
        fundamentals: FundamentalsSource,
        macro: MacroSource,
        cik_registry: CikLookup,
    ) -> None:
        self._fundamentals = fundamentals
        self._macro = macro
        self._cik_registry = cik_registry

    def snapshot(self, *, symbol: str, as_of: datetime) -> FactorSnapshot:
        normalized = symbol.strip().upper()
        return FactorSnapshot(
            symbol=normalized,
            as_of=as_of,
            macro=self._macro_reading(as_of),
            geopolitics=geopolitics_reading(as_of=as_of),
            institutional_flow=institutional_flow_reading(as_of=as_of),
            fundamentals=self._fundamentals_reading(normalized, as_of),
        )

    def _macro_reading(self, as_of: datetime) -> FactorReading:
        try:
            return self._macro.reading(as_of=as_of)
        except Exception as error:  # noqa: BLE001 - see _guarded below
            return _guarded(FACTOR_MACRO, TREASURY_MACRO_METHOD_VERSION, as_of, error)

    def _fundamentals_reading(
        self, symbol: str, as_of: datetime
    ) -> FactorReading:
        try:
            cik = self._cik_registry.cik_for(symbol)
        except Exception as error:  # noqa: BLE001 - one source degrades alone
            return _guarded(
                FACTOR_FUNDAMENTALS,
                SEC_FUNDAMENTALS_METHOD_VERSION,
                as_of,
                error,
            )
        if cik is None:
            # Without a filer there is nothing to look up. This is a property
            # of the symbol, not a fault, so it must not be reported as an
            # outage an operator would go hunting for.
            return FactorReading.unavailable(
                factor=FACTOR_FUNDAMENTALS,
                method_version=SEC_FUNDAMENTALS_METHOD_VERSION,
                as_of=as_of,
                reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
                detail=(
                    f"{symbol} maps to no single SEC filer in the company "
                    "ticker registry, so no XBRL financials can be attributed "
                    "to it."
                ),
            )
        try:
            return self._fundamentals.reading(cik=cik, as_of=as_of)
        except Exception as error:  # noqa: BLE001 - see _guarded below
            return _guarded(
                FACTOR_FUNDAMENTALS, SEC_FUNDAMENTALS_METHOD_VERSION, as_of, error
            )


def _guarded(
    factor: str, method_version: str, as_of: datetime, error: Exception
) -> FactorReading:
    """Turn any unhandled adapter fault into a stated reason.

    Catching everything is normally a smell, and here it is the point: this
    boundary exists so that a bug in one factor cannot take down a decision
    that three other factors could still have supported. The exception type
    and message survive into the detail, so nothing is swallowed silently.
    """

    return FactorReading.unavailable(
        factor=factor,
        method_version=method_version,
        as_of=as_of,
        reason=FactorUnavailable.SOURCE_UNREACHABLE,
        detail=(
            f"The {factor} source raised {type(error).__name__}: "
            f"{error or 'no message'}."
        ),
    )
