"""Probabilistic scenario forecasts without deterministic promises."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite, sqrt

from .models import Horizon, require_utc
from .scoring import ScoreResult


class CalibrationStatus(str, Enum):
    UNCALIBRATED = "uncalibrated"
    BACKTESTED = "backtested"
    LIVE_MONITORED = "live_monitored"


class ScenarioKind(str, Enum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


@dataclass(frozen=True, slots=True)
class ScenarioCase:
    kind: ScenarioKind
    probability: float
    price_low: float
    price_high: float
    explanation: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("scenario probability must be between 0 and 1")
        if (
            not isfinite(self.price_low)
            or not isfinite(self.price_high)
            or self.price_low <= 0
            or self.price_low > self.price_high
        ):
            raise ValueError("scenario price range must be positive and ordered")
        if not self.explanation.strip():
            raise ValueError("scenario explanation is required")


@dataclass(frozen=True, slots=True)
class ScenarioForecast:
    as_of: datetime
    horizon: Horizon
    current_price: float
    cases: tuple[ScenarioCase, ...]
    calibration_status: CalibrationStatus
    calibration_reference: str | None
    invalidation_conditions: tuple[str, ...]
    citation_ids: tuple[str, ...]
    method_version: str = "bounded-scenario-forecast-v1"
    disclaimer: str = "Scenarios are uncertain analytical ranges, not promised prices."

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        if len(self.cases) != 3:
            raise ValueError("forecast requires bear, base, and bull scenarios")
        if {case.kind for case in self.cases} != set(ScenarioKind):
            raise ValueError("forecast requires one scenario of each kind")
        if abs(sum(case.probability for case in self.cases) - 1.0) > 1e-9:
            raise ValueError("scenario probabilities must sum to 1")
        if not self.invalidation_conditions:
            raise ValueError("at least one invalidation condition is required")
        if (
            self.calibration_status != CalibrationStatus.UNCALIBRATED
            and (
                self.calibration_reference is None
                or not self.calibration_reference.strip()
            )
        ):
            raise ValueError(
                "calibration reference is required for a calibrated forecast"
            )


def build_scenario_forecast(
    score: ScoreResult,
    *,
    current_price: float,
    annualized_volatility: float,
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
    calibration_reference: str | None = None,
    invalidation_conditions: tuple[str, ...],
    citation_ids: tuple[str, ...] = (),
) -> ScenarioForecast:
    if not isfinite(current_price) or current_price <= 0:
        raise ValueError("current_price must be finite and positive")
    if not isfinite(annualized_volatility) or annualized_volatility <= 0:
        raise ValueError("annualized volatility must be finite and positive")
    if not invalidation_conditions or any(
        not condition.strip() for condition in invalidation_conditions
    ):
        raise ValueError("at least one non-empty invalidation condition is required")
    if (
        calibration_status != CalibrationStatus.UNCALIBRATED
        and (calibration_reference is None or not calibration_reference.strip())
    ):
        raise ValueError(
            "calibration reference is required for a calibrated forecast"
        )

    directional = max(-1.0, min(1.0, (score.objective_score - 50.0) / 50.0))
    probabilities = {
        ScenarioKind.BEAR: 0.30 - directional * 0.20,
        ScenarioKind.BASE: 0.40,
        ScenarioKind.BULL: 0.30 + directional * 0.20,
    }
    horizon_days = {
        Horizon.SHORT: 5,
        Horizon.SWING: 30,
        Horizon.LONG: 252,
    }[score.horizon]
    expected_move = min(
        annualized_volatility * sqrt(horizon_days / 252.0),
        0.95,
    )
    centers_and_widths = {
        ScenarioKind.BEAR: (-0.75 * expected_move, 0.35 * expected_move),
        ScenarioKind.BASE: (
            directional * 0.20 * expected_move,
            0.30 * expected_move,
        ),
        ScenarioKind.BULL: (0.75 * expected_move, 0.35 * expected_move),
    }
    # Investor-readable Chinese (2026-08-15 served-copy sweep), exact-pinned
    # by analysis_api's decision-fixture tests; these ride the wire verbatim
    # as `forecast.cases[].explanation`.
    explanations = {
        ScenarioKind.BEAR: ("按已实现波动率与当前证据评分推算的不利区间。"),
        ScenarioKind.BASE: "中性不确定区间；不是单一价格的预测。",
        ScenarioKind.BULL: ("按已实现波动率与当前证据评分推算的有利区间。"),
    }
    cases: list[ScenarioCase] = []
    for kind in ScenarioKind:
        center, width = centers_and_widths[kind]
        cases.append(
            ScenarioCase(
                kind=kind,
                probability=probabilities[kind],
                price_low=max(0.01, current_price * (1.0 + center - width)),
                price_high=max(0.01, current_price * (1.0 + center + width)),
                explanation=explanations[kind],
            )
        )
    return ScenarioForecast(
        as_of=score.as_of,
        horizon=score.horizon,
        current_price=current_price,
        cases=tuple(cases),
        calibration_status=calibration_status,
        calibration_reference=calibration_reference,
        invalidation_conditions=invalidation_conditions,
        citation_ids=citation_ids,
    )
