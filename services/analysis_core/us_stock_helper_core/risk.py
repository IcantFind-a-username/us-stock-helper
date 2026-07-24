"""Pure analytical risk plans. This module cannot place orders."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from math import isfinite

from .forecasting import ScenarioForecast, ScenarioKind
from .models import Direction, Horizon, RiskPreference, require_utc
from .scoring import HardGate, ScoreResult


class AnalyticalAction(str, Enum):
    LONG = "long"
    SHORT = "short"
    WATCH = "watch"
    AVOID = "avoid"


@dataclass(frozen=True, slots=True)
class ShortBorrowSnapshot:
    checked_at: datetime
    available: bool
    estimated_fee_percent: float
    crowding: str
    source: str

    def __post_init__(self) -> None:
        require_utc(self.checked_at, "checked_at")
        if (
            not isfinite(self.estimated_fee_percent)
            or self.estimated_fee_percent < 0
        ):
            raise ValueError(
                "estimated_fee_percent must be finite and non-negative"
            )
        if self.crowding not in {"low", "medium", "high", "unknown"}:
            raise ValueError(
                "crowding must be low, medium, high, or unknown"
            )
        if not self.source.strip():
            raise ValueError("borrow source is required")


@dataclass(frozen=True, slots=True)
class RiskPlan:
    as_of: datetime
    horizon: Horizon
    action: AnalyticalAction
    direction: Direction
    objective_score: float
    entry_range: tuple[float, float] | None
    invalidation_price: float | None
    target_range: tuple[float, float] | None
    max_position_percent: float
    leverage: float
    citation_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    blocked_by: tuple[HardGate, ...]
    method_version: str = "analysis-only-risk-plan-v1"


def build_risk_plan(
    score: ScoreResult,
    forecast: ScenarioForecast,
    *,
    preference: RiskPreference,
    short_borrow: ShortBorrowSnapshot | None = None,
    borrow_max_age: timedelta = timedelta(minutes=15),
) -> RiskPlan:
    if score.as_of != forecast.as_of or score.horizon != forecast.horizon:
        raise ValueError("score and forecast must share the same as_of and horizon")

    gates = list(score.blocked_by)
    if not score.actionable or gates:
        action = AnalyticalAction.AVOID
    elif score.direction == Direction.BULLISH:
        action = AnalyticalAction.LONG
    elif score.direction == Direction.BEARISH:
        if short_borrow is None or not short_borrow.available:
            action = AnalyticalAction.AVOID
            gates.append(HardGate.BORROW_UNAVAILABLE)
        elif (
            short_borrow.checked_at > score.as_of
            or score.as_of - short_borrow.checked_at > borrow_max_age
        ):
            action = AnalyticalAction.AVOID
            gates.append(HardGate.BORROW_DATA_STALE)
        else:
            action = AnalyticalAction.SHORT
    else:
        action = AnalyticalAction.WATCH

    max_position, leverage = {
        RiskPreference.CONSERVATIVE: (5.0, 1.0),
        RiskPreference.BALANCED: (10.0, 1.1),
        RiskPreference.AGGRESSIVE: (15.0, 1.5),
    }[preference]
    current_price = forecast.current_price
    cases = {case.kind: case for case in forecast.cases}
    if action == AnalyticalAction.LONG:
        entry_range = (current_price * 0.99, current_price * 1.005)
        invalidation_price = min(
            current_price * 0.96, cases[ScenarioKind.BEAR].price_high
        )
        target_range = (
            cases[ScenarioKind.BULL].price_low,
            cases[ScenarioKind.BULL].price_high,
        )
    elif action == AnalyticalAction.SHORT:
        entry_range = (current_price * 0.995, current_price * 1.01)
        invalidation_price = max(
            current_price * 1.04, cases[ScenarioKind.BULL].price_low
        )
        target_range = (
            cases[ScenarioKind.BEAR].price_low,
            cases[ScenarioKind.BEAR].price_high,
        )
    else:
        entry_range = None
        invalidation_price = None
        target_range = None
        max_position = 0.0
        leverage = 1.0

    warnings = [
        "Analysis only: this plan cannot submit, route, or execute an order.",
        "Scenario ranges are uncertain and require independent confirmation before any decision.",
    ]
    if forecast.calibration_status.value == "uncalibrated":
        warnings.append("Forecast calibration status is uncalibrated.")
    if gates:
        warnings.append(
            "Hard gate active: " + ", ".join(gate.value for gate in gates)
        )
    actionable = action in (AnalyticalAction.LONG, AnalyticalAction.SHORT)
    return RiskPlan(
        as_of=score.as_of,
        horizon=score.horizon,
        action=action,
        direction=score.direction,
        objective_score=score.objective_score,
        entry_range=entry_range,
        invalidation_price=invalidation_price,
        target_range=target_range,
        max_position_percent=max_position if actionable else 0.0,
        leverage=leverage if actionable else 1.0,
        citation_ids=forecast.citation_ids,
        warnings=tuple(warnings),
        blocked_by=tuple(dict.fromkeys(gates)),
    )
