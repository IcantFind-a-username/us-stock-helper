"""Blend the market gateway's two institutional-capital ingredients, or say
plainly that neither was available.

The decision score used to list institutional_flow as permanently
unavailable (information_layer.factors.unsupported used to abstain on it
outright: no free source was timely enough). That stopped being true once
the market gateway started serving, for the symbols it covers:

* An intraday order-size participation proxy (main-vs-retail lot-size split
  and net capital flow, from the gateway's currentSessionFlow section, built
  via us_stock_helper_core.participation.build_participation_bars). This is
  explicitly an *estimate* — the gateway itself stamps every row
  ``institutionalIdentity: false`` — so it never contributes at full
  strength. Its share of the blend is capped at ``PROXY_CONFIDENCE``
  regardless of how strong its own raw reading is.
* A dated institutional-holdings disclosure trend (from the gateway's
  holdings section). This is an actual filed disclosure rather than an
  estimate, so it is never discounted the way the proxy is; its own age is
  what already limits it, via the point-in-time filter that keeps a row out
  of ``InstitutionalFlowInputs.holdings`` in the first place
  (``gateway_provider.MarketGatewayProvider._holdings``) — nothing here ever
  reads a disclosure before its own ``available_at``.

Neither ingredient is invented when missing: a symbol with no live intraday
flow and no qualifying holdings disclosure gets an honest
``unavailable_reason``, never a neutral-looking 0.0 — the same rule every
other soft factor in this system follows (see
information_layer.factors.base.FactorReading's own doctrine, which this
module deliberately mirrors without adopting: institutional flow is not a
citable public HTTPS source the way macro/fundamentals are, so it is not
built on FactorReading/FactorInput itself).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from information_layer.factors.base import FactorUnavailable

from .gateway_provider import (
    HoldingsDisclosure,
    InstitutionalFlowInputs,
    MarketGatewayUnavailable,
)


METHOD_VERSION = "institutional-flow-participation-holdings-v1"

# The intraday proxy never claims more conviction than half of what a real
# disclosure would for the same raw reading: it is order-size activity, not
# a verified institutional trade. Versioned here rather than left as a bare
# literal because it is the one number that decides how far a guess is
# allowed to move the score.
PROXY_CONFIDENCE = 0.5
# An actual filed disclosure is not a guess, so it is never discounted for
# being an estimate — only for age, and that is already enforced by the PIT
# filter that keeps a stale row out of `holdings` before this module ever
# sees it.
DISCLOSURE_CONFIDENCE = 1.0
# A five-percentage-point swing in aggregate institutional ownership between
# consecutive disclosures reads as a full-strength signal; larger moves
# clamp rather than overshoot [-1, 1].
DISCLOSURE_TREND_SCALE_POINTS = 5.0


@dataclass(frozen=True, slots=True)
class InstitutionalFlowReading:
    """Exactly one of ``value``/``unavailable_reason`` is set, never both.

    Mirrors information_layer.factors.base.FactorReading's own invariant on
    purpose — same rule, same reason — without inheriting from it: this
    reading is not built from FactorInput citations, so it does not carry
    that class's HTTPS-source requirement.
    """

    value: float | None
    unavailable_reason: FactorUnavailable | None
    detail: str
    method_version: str = METHOD_VERSION

    def __post_init__(self) -> None:
        if (self.value is None) == (self.unavailable_reason is None):
            raise ValueError(
                "a reading is either a measured value or a stated reason, "
                "never both"
            )


class InstitutionalFlowGateway(Protocol):
    def institutional_flow_inputs_for(
        self, symbol: str, as_of: datetime
    ) -> InstitutionalFlowInputs: ...


@dataclass(frozen=True, slots=True)
class GatewayInstitutionalFlowProvider:
    """Adapts the market gateway's snapshot into the institutional-flow factor."""

    gateway: InstitutionalFlowGateway

    def reading(self, *, symbol: str, as_of: datetime) -> InstitutionalFlowReading:
        try:
            inputs = self.gateway.institutional_flow_inputs_for(symbol, as_of)
        except MarketGatewayUnavailable as error:
            return InstitutionalFlowReading(
                value=None,
                unavailable_reason=FactorUnavailable.SOURCE_UNREACHABLE,
                detail=(
                    "The market gateway could not supply institutional-flow "
                    f"inputs: {error}."
                ),
            )
        return blend(symbol, inputs)


def blend(symbol: str, inputs: InstitutionalFlowInputs) -> InstitutionalFlowReading:
    proxy_bar = _latest_live_bar(inputs.participation_bars)
    disclosure_row = inputs.holdings[0] if inputs.holdings else None

    proxy_component = _proxy_component(proxy_bar) if proxy_bar is not None else None
    disclosure_component = (
        _disclosure_component(disclosure_row) if disclosure_row is not None else None
    )

    if proxy_component is None and disclosure_component is None:
        failures = [
            (label, failure)
            for label, failure in (
                ("current-session order-size flow", inputs.flow_section_failure),
                ("institutional holdings disclosure", inputs.holdings_section_failure),
            )
            if failure is not None
        ]
        if failures:
            # The gateway itself said a source failed here — a stronger,
            # more actionable claim than "the market was quiet" — so it gets
            # the same reason code every other source outage in this system
            # reports, not the softer no-data-this-day taxonomy.
            described = "; ".join(
                f"{label} ({failure.status}"
                + (f": {failure.reason}" if failure.reason else "")
                + ")"
                for label, failure in failures
            )
            return InstitutionalFlowReading(
                value=None,
                unavailable_reason=FactorUnavailable.SOURCE_UNREACHABLE,
                detail=(
                    "The market gateway declared "
                    f"{'a source' if len(failures) == 1 else 'sources'} "
                    f"unavailable for {symbol}: {described}."
                ),
            )
        return InstitutionalFlowReading(
            value=None,
            unavailable_reason=FactorUnavailable.NO_DATA_AT_CUTOFF,
            detail=(
                "Neither a live intraday order-size participation bar nor a "
                "point-in-time institutional holdings disclosure was "
                f"available for {symbol} at the cutoff."
            ),
        )

    if proxy_component is not None and disclosure_component is not None:
        value = _clamp(
            (proxy_component * PROXY_CONFIDENCE + disclosure_component * DISCLOSURE_CONFIDENCE)
            / (PROXY_CONFIDENCE + DISCLOSURE_CONFIDENCE)
        )
        detail = (
            "Blended from a live order-size participation proxy (estimate "
            f"only, no institutional identity claimed, confidence "
            f"{PROXY_CONFIDENCE:g}) and the institutional holdings "
            f"disclosure reported {disclosure_row.reported_at.isoformat()}, "  # type: ignore[union-attr]
            f"available {disclosure_row.available_at.isoformat()} "  # type: ignore[union-attr]
            f"(confidence {DISCLOSURE_CONFIDENCE:g})."
        )
    elif proxy_component is not None:
        value = _clamp(proxy_component * PROXY_CONFIDENCE)
        detail = (
            "From a live order-size participation proxy only (estimate "
            f"only, no institutional identity claimed, confidence "
            f"{PROXY_CONFIDENCE:g}); no qualifying holdings disclosure was "
            "available at the cutoff."
        )
    else:
        assert disclosure_row is not None
        value = _clamp(disclosure_component * DISCLOSURE_CONFIDENCE)  # type: ignore[operator]
        detail = (
            "From the institutional holdings disclosure reported "
            f"{disclosure_row.reported_at.isoformat()}, available "
            f"{disclosure_row.available_at.isoformat()} only; no live "
            "intraday order-size participation data was available at the "
            "cutoff."
        )

    return InstitutionalFlowReading(value=value, unavailable_reason=None, detail=detail)


def _latest_live_bar(bars):
    for bar in reversed(bars):
        if bar.quality_status == "live":
            return bar
    return None


def _proxy_component(bar) -> float:
    # Bounded in [-1, 1] by construction: net_flow is the sum of four signed
    # per-minute bucket deltas, and main_activity+retail_activity is the sum
    # of their absolute values, so |net_flow| <= denominator by the triangle
    # inequality. _clamp stays as a defensive floor, not the load-bearing
    # bound.
    denominator = bar.main_activity + bar.retail_activity
    return _clamp(bar.net_flow / denominator)


def _disclosure_component(row: HoldingsDisclosure) -> float:
    return _clamp(row.holding_percent_change / DISCLOSURE_TREND_SCALE_POINTS)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))
