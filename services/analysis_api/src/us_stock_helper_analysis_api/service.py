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
from typing import Any, Callable, Mapping, Protocol

from decision_engine import DecisionEngine, DecisionInputs
from information_layer import Citation, EvidenceEvent
from information_layer.factors import FactorSnapshot
from information_layer.feeds import FRESHNESS_ATTRIBUTE, STALE_ATTRIBUTE
from us_stock_helper_core import (
    ADVISER_SCORE_CAP,
    Horizon,
    OHLCVBar,
    RiskPreference,
    RiskPlan,
    ScenarioForecast,
    ScoreResult,
)

from .adviser_provider import (
    NO_DECISION_REASON,
    AdviserBriefing,
    AdviserSource,
    not_requested,
    provider_from_environment,
    unavailable_for_mode,
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
    """Candles are required; evidence arrives through one of two shapes.

    Preferred: read_evidence(symbol) returning an object carrying request-
    scoped .events and .gaps. Providers written before partial reads existed
    — including the fakes several test modules inject — expose
    evidence_for(symbol) instead, optionally with a provider-level
    evidence_gaps(); _read_evidence bridges both.
    """

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]: ...


@dataclass(frozen=True, slots=True)
class AnalysisService:
    provider: AnalysisProvider
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)
    # A composed investment decision defaults to completed daily bars. The
    # five-minute feed is useful for chart inspection, but making it the basis
    # of every horizon turned intraday noise into a swing or long-term verdict.
    interval: str = "day"
    # Built per request rather than at startup, because building it imports the
    # model SDK. A deployment without that SDK has to serve every deterministic
    # route exactly as before and report only the adviser as unavailable.
    adviser_factory: Callable[[], AdviserSource] = provider_from_environment

    def _read_evidence(
        self,
        symbol: str,
    ) -> tuple[tuple[EvidenceEvent, ...], tuple[str, ...]]:
        """One request's evidence, with the sources that read could not reach.

        The gaps travel with the call: the provider is one shared instance
        behind a threading server, and reading them back from provider state
        later let a concurrent clean sweep erase another request's disclosure.
        Providers written before partial reads existed — including the fakes
        several test modules inject — still answer through evidence_for, with
        anything their optional provider-level evidence_gaps() reports carried
        along as before.
        """

        read = getattr(self.provider, "read_evidence", None)
        if callable(read):
            result = read(symbol)
            return tuple(result.events), tuple(result.gaps)
        events = tuple(self.provider.evidence_for(symbol))
        report = getattr(self.provider, "evidence_gaps", None)
        return events, (tuple(report()) if callable(report) else ())

    def _factor_snapshot(
        self,
        symbol: str,
        as_of: datetime,
    ) -> tuple[FactorSnapshot | None, str | None]:
        """Read optional public factors without taking the base decision down.

        Providers deployed before the factor layer still produce the original
        partial score. A configured factor provider that fails as a whole is
        also a partial score, but the response says why instead of turning all
        symbols into HTTP 500s.
        """

        read = getattr(self.provider, "factors_for", None)
        if not callable(read):
            return None, None
        try:
            snapshot = read(symbol, as_of)
        except Exception:  # noqa: BLE001 - this is the degradation boundary
            return None, "Public factor sources could not be read for this decision."
        if not isinstance(snapshot, FactorSnapshot):
            return None, "Public factor sources returned an unsupported snapshot."
        return snapshot, None

    def decision(
        self,
        symbol: str,
        horizon: str,
        *,
        risk_preference: str = "balanced",
        adviser: bool | str = False,
    ) -> dict[str, Any]:
        normalized = symbol.strip().upper()
        if not normalized:
            raise InvalidRequest("symbol is required")
        if horizon not in _HORIZONS:
            raise InvalidRequest(f"unsupported horizon: {horizon}")
        if risk_preference not in _PREFERENCES:
            raise InvalidRequest(f"unsupported risk preference: {risk_preference}")
        adviser_mode = _adviser_mode(adviser)

        bars = self.provider.bars_for(normalized, self.interval)
        if not bars:
            return self._unavailable(
                normalized,
                horizon,
                self.clock(),
                "No completed candles were available at the decision cutoff.",
                # Nothing was scored, so there is no baseline for a council to
                # move and no reason to spend anything finding that out.
                briefing=(
                    unavailable_for_mode(adviser_mode, NO_DECISION_REASON)
                    if adviser_mode != "off"
                    else not_requested()
                ),
            )

        # Take the cutoff after ALL the data is in hand — evidence as well as
        # bars. Sampling it before the bar fetch made any bar published during
        # the round trip newer than the cutoff and failed the request; sampling
        # it before the evidence fetch was quieter and worse: a live collector
        # stamps available_at = retrieved_at, so every event first retrieved
        # during the request fell after the cutoff and was silently filed as
        # future — breaking news was invisible to precisely the request that
        # fetched it, served as a measured-looking neutral.
        evidence, gaps = self._read_evidence(normalized)
        as_of = self.clock()
        factors, factor_failure = self._factor_snapshot(normalized, as_of)
        output = DecisionEngine().evaluate(
            DecisionInputs(
                symbol=normalized,
                horizon=_HORIZONS[horizon],
                as_of=as_of,
                bars=bars,
                evidence=evidence,
                current_price=bars[-1].close,
                current_price_available_at=bars[-1].available_at,
                annualized_volatility=None,
                volatility_available_at=None,
                macro=factors.macro.measured_value if factors else None,
                geopolitics=(
                    factors.geopolitics.measured_value if factors else None
                ),
                institutional_flow=(
                    factors.institutional_flow.measured_value if factors else None
                ),
                fundamentals=(
                    factors.fundamentals.measured_value if factors else None
                ),
                risk_preference=_PREFERENCES[risk_preference],
                invalidation_conditions=(
                    "The cited evidence is withdrawn or contradicted.",
                ),
            )
        )

        citations = [
            _citation(item) for item in output.evidence_packet.citations
        ]
        notes: list[str] = []
        if factor_failure:
            notes.append(factor_failure)
        if factors:
            notes.extend(
                f"{name} unavailable ({reason.value})."
                for name, reason in factors.unavailable_reasons()
            )
        stale_count = sum(1 for item in citations if item["stale"] is True)
        if stale_count:
            # Age is stated, never used as a reason to hide the item: whether
            # an old filing still matters is the reader's call to make.
            notes.append(
                f"{stale_count} cited item(s) are older than the configured "
                "freshness window and are marked stale."
            )
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
        # The point-in-time invariant may still exclude an event stamped after
        # even this honestly-taken cutoff (an embargo, a skewed publisher
        # clock). The exclusion is legitimate; hiding it is not — an exclusion
        # the reader cannot see patches the record instead of protecting it.
        excluded = output.evidence_packet.excluded_future_event_ids
        if excluded:
            notes.append(
                f"有 {len(excluded)} 条证据在决策截点之后才可用，"
                "未纳入本次结论：" + "、".join(excluded)
            )
        # A source that could not be read is stated rather than absorbed. The
        # decision is still served — one slow publisher used to fail every
        # symbol at once — but a reader must never mistake a partial sweep of
        # the news for a complete one. The gaps were captured with the fetch
        # itself, so a neighbouring request's sweep cannot rewrite them.
        if gaps:
            notes.append(
                f"本次未能读取 {len(gaps)} 个情报源，证据可能不完整：" + "、".join(gaps)
            )

        # The council reads the objective score as its baseline and is handed
        # the same hard gates, so a gated decision cannot be talked back up:
        # the gate voids the adjustment inside apply_hard_gate rather than
        # anywhere in this file.
        briefing = (
            self.adviser_factory().brief(
                symbol=normalized,
                horizon=horizon,
                as_of=as_of,
                evidence=evidence,
                baseline_score=output.adjusted_score.objective_score,
                baseline_direction=output.adjusted_score.direction.value,
                hard_gates=output.adjusted_score.blocked_by,
                mode=adviser_mode,
            )
            if adviser_mode != "off"
            else not_requested()
        )
        notes.extend(briefing.notes)

        # One adjustment authority: engine.evaluate is never handed adviser
        # opinions (see the comment above), so output.adviser_adjustment is
        # always 0.0 and is not what moved anything. The council's own
        # verdict — already voided by any hard gate and clamped to
        # ±ADVISER_SCORE_CAP inside apply_hard_gate — is the real adjustment
        # when a council ran at all. A council that never ran (not
        # requested, unreachable, or convened only for news) has no
        # adjustment to report; 0.0 would be a measured neutral for a
        # judgement nobody made.
        served_score = _score(output.adjusted_score)
        council_value = briefing.council.get("value")
        if council_value is None:
            adviser_adjustment: float | None = None
            notes.append(
                "No adviser council ran for this response, so "
                "adviserAdjustment is null rather than a measured zero."
            )
        else:
            adviser_adjustment = council_value["scoreAdjustment"]
            assert abs(adviser_adjustment) <= ADVISER_SCORE_CAP, (
                "council scoreAdjustment exceeded the published cap"
            )
            served_score["value"] = council_value["adjustedScore"]

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "live",
            "symbol": normalized,
            "horizon": horizon,
            "interval": self.interval,
            "decisionCutoff": _iso(as_of),
            "score": served_score,
            "baselineScore": _score(output.baseline_score),
            "adviserAdjustment": adviser_adjustment,
            "forecast": _forecast(output.forecast),
            "riskPlan": _risk_plan(output.risk_plan),
            "sentiment": {
                "conclusion": output.evidence_packet.sentiment.conclusion,
                "actionScore": output.evidence_packet.sentiment.action_score,
                "decisionSignal": output.evidence_packet.sentiment.decision_signal,
                "uncertainty": list(output.evidence_packet.sentiment.uncertainty),
            },
            "citations": citations,
            # Null here would be a third way of saying nothing. Each block
            # states which of not-requested, available and unavailable it is,
            # and only an available one carries a value.
            "newsInterpretation": briefing.news,
            "adviserCouncil": briefing.council,
            "adviserUsage": briefing.usage,
            "notes": notes,
        }
    def _unavailable(
        self,
        symbol: str,
        horizon: str,
        as_of: datetime,
        reason: str,
        *,
        briefing: AdviserBriefing,
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "unavailable",
            "symbol": symbol,
            "horizon": horizon,
            "interval": self.interval,
            "decisionCutoff": _iso(as_of),
            "score": None,
            "baselineScore": None,
            # No decision was reached at all, so there is no council to have
            # run and no baseline for it to have moved.
            "adviserAdjustment": None,
            "forecast": None,
            "riskPlan": None,
            "sentiment": None,
            "citations": [],
            "newsInterpretation": briefing.news,
            "adviserCouncil": briefing.council,
            "adviserUsage": briefing.usage,
            "notes": [reason, *briefing.notes],
        }


def _adviser_mode(value: bool | str) -> str:
    if value is False:
        return "off"
    if value is True:
        return "full"
    if value in {"news", "full"}:
        return value
    raise InvalidRequest("adviser must be off, news, or full")


def _citation(citation: Citation) -> dict[str, Any]:
    attributes = dict(citation.attributes)
    return {
        "id": citation.citation_id,
        "headline": citation.headline,
        "publisher": citation.publisher_name,
        "url": citation.canonical_url,
        "availableAt": _iso(citation.available_at),
        "freshnessSeconds": _freshness(attributes),
        "stale": _stale(attributes),
    }


def _freshness(attributes: Mapping[str, str]) -> int | None:
    # Null means nobody measured the age. Zero would mean it was measured and
    # came out at this instant, which is a different claim entirely.
    raw = attributes.get(FRESHNESS_ATTRIBUTE)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _stale(attributes: Mapping[str, str]) -> bool | None:
    raw = attributes.get(STALE_ATTRIBUTE)
    if raw in {"true", "false"}:
        return raw == "true"
    return None


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
