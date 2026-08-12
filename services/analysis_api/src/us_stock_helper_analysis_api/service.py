"""Turn the decision chain into one JSON answer the app can render.

Everything the chain refuses to state — an unmeasurable forecast width, a
factor with no feed — has to survive the trip to the screen. A serializer that
quietly drops those is how a partial picture arrives looking complete, so each
absence is carried as an explicit null plus a note saying why.

Read-only by construction: this exposes analysis, never an order path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from decision_engine import DecisionEngine, DecisionInputs
from information_layer import EvidenceEvent
from us_stock_helper_core import (
    Horizon,
    OHLCVBar,
    RiskPreference,
    RiskPlan,
    ScenarioForecast,
    ScoreResult,
)


SCHEMA_VERSION = "1"


class InvalidRequest(ValueError):
    """A caller supplied an argument this service cannot honour.

    Kept apart from every other ValueError because json.JSONDecodeError and
    the decision chain's own invariant failures are ValueErrors too: catching
    the base class blamed the caller for server-side problems and forwarded
    internal text that the sanitizer exists to withhold.
    """

_HORIZONS = {horizon.value: horizon for horizon in Horizon}
_PREFERENCES = {value.value: value for value in RiskPreference}


class AnalysisProvider(Protocol):
    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]: ...

    def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]: ...


@dataclass(frozen=True, slots=True)
class AnalysisService:
    provider: AnalysisProvider
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)
    interval: str = "5m"

    def decision(
        self,
        symbol: str,
        horizon: str,
        *,
        risk_preference: str = "balanced",
    ) -> dict[str, Any]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise InvalidRequest("symbol is required")
        if horizon not in _HORIZONS:
            raise InvalidRequest(f"unsupported horizon: {horizon}")
        if risk_preference not in _PREFERENCES:
            raise InvalidRequest(f"unsupported risk preference: {risk_preference}")

        # Take the cutoff after the data is in hand. Sampling it first made
        # any bar published during the round trip newer than the cutoff, and
        # the chain's own point-in-time invariant then rejected the request.
        bars = self.provider.bars_for(normalized, self.interval)
        as_of = self.clock()
        if not bars:
            return self._unavailable(
                normalized,
                horizon,
                as_of,
                "No completed candles were available at the decision cutoff.",
            )

        output = DecisionEngine().evaluate(
            DecisionInputs(
                symbol=normalized,
                horizon=_HORIZONS[horizon],
                as_of=as_of,
                bars=bars,
                evidence=self.provider.evidence_for(normalized),
                current_price=bars[-1].close,
                current_price_available_at=bars[-1].available_at,
                annualized_volatility=None,
                volatility_available_at=None,
                macro=None,
                geopolitics=None,
                institutional_flow=None,
                fundamentals=None,
                risk_preference=_PREFERENCES[risk_preference],
                invalidation_conditions=(
                    "The cited evidence is withdrawn or contradicted.",
                ),
            )
        )

        notes: list[str] = []
        if output.forecast is None:
            notes.append(
                "Realized volatility could not be measured, so no scenario "
                "range is offered."
            )
        if output.adjusted_score.unavailable_factors:
            notes.append(
                "Scored on "
                f"{output.adjusted_score.factor_coverage:.0%} of the factor "
                "weight; the rest has no source yet."
            )

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "live",
            "symbol": normalized,
            "horizon": horizon,
            "decisionCutoff": _iso(as_of),
            "score": _score(output.adjusted_score),
            "baselineScore": _score(output.baseline_score),
            "adviserAdjustment": output.adviser_adjustment,
            "forecast": _forecast(output.forecast),
            "riskPlan": _risk_plan(output.risk_plan),
            "sentiment": {
                "conclusion": output.evidence_packet.sentiment.conclusion,
                "actionScore": output.evidence_packet.sentiment.action_score,
                "decisionSignal": output.evidence_packet.sentiment.decision_signal,
                "uncertainty": list(output.evidence_packet.sentiment.uncertainty),
            },
            "citations": [
                {
                    "id": citation.citation_id,
                    "headline": citation.headline,
                    "publisher": citation.publisher_name,
                    "url": citation.canonical_url,
                    "availableAt": _iso(citation.available_at),
                }
                for citation in output.evidence_packet.citations
            ],
            "notes": notes,
        }

    def _unavailable(
        self, symbol: str, horizon: str, as_of: datetime, reason: str
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "unavailable",
            "symbol": symbol,
            "horizon": horizon,
            "decisionCutoff": _iso(as_of),
            "score": None,
            "baselineScore": None,
            "adviserAdjustment": 0.0,
            "forecast": None,
            "riskPlan": None,
            "sentiment": None,
            "citations": [],
            "notes": [reason],
        }


def _score(score: ScoreResult) -> dict[str, Any]:
    return {
        "value": score.objective_score,
        "direction": score.direction.value,
        "actionable": score.actionable,
        "methodVersion": score.method_version,
        "factorCoverage": score.factor_coverage,
        "unavailableFactors": list(score.unavailable_factors),
        "blockedBy": [gate.value for gate in score.blocked_by],
        "contributions": [
            {
                "name": item.name,
                "rawValue": item.raw_value,
                "weight": item.weight,
                "points": item.points,
                "explanation": item.explanation,
            }
            for item in score.contributions
        ],
    }


def _forecast(forecast: ScenarioForecast | None) -> dict[str, Any] | None:
    if forecast is None:
        return None
    return {
        "currentPrice": forecast.current_price,
        "methodVersion": forecast.method_version,
        "calibrationStatus": forecast.calibration_status.value,
        "calibrationReference": forecast.calibration_reference,
        "invalidationConditions": list(forecast.invalidation_conditions),
        "disclaimer": forecast.disclaimer,
        "cases": [
            {
                "kind": case.kind.value,
                "probability": case.probability,
                "priceLow": case.price_low,
                "priceHigh": case.price_high,
                "explanation": case.explanation,
            }
            for case in forecast.cases
        ],
    }


def _risk_plan(plan: RiskPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "action": plan.action.value,
        "direction": plan.direction.value,
        "entryRange": list(plan.entry_range) if plan.entry_range else None,
        "invalidationPrice": plan.invalidation_price,
        "targetRange": list(plan.target_range) if plan.target_range else None,
        "maxPositionPercent": plan.max_position_percent,
        "leverage": plan.leverage,
        "warnings": list(plan.warnings),
        "blockedBy": [gate.value for gate in plan.blocked_by],
        "methodVersion": plan.method_version,
    }


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
