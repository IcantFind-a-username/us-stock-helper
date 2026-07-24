"""Point-in-time-safe analysis primitives for US Stock Helper."""

from .evidence import EvidencePacket, freeze_evidence_packet
from .forecasting import (
    CalibrationStatus,
    ScenarioCase,
    ScenarioForecast,
    ScenarioKind,
    build_scenario_forecast,
)
from .indicators import MACDValue, ema_series, macd, moving_average, rsi
from .models import (
    Direction,
    EvidenceKind,
    EvidenceRecord,
    Horizon,
    MarketContext,
    OHLCVBar,
    RiskPreference,
)
from .patterns import (
    MagicNineSignal,
    PatternKind,
    PatternSignal,
    detect_double_bottom,
    detect_head_and_shoulders,
    detect_ma5_pullback,
    magic_nine,
    three_bar_fractals,
)
from .risk import (
    AnalyticalAction,
    RiskPlan,
    ShortBorrowSnapshot,
    build_risk_plan,
)
from .scoring import (
    FactorContribution,
    FeatureSet,
    HardGate,
    ScoreResult,
    extract_horizon_features,
    score_horizon,
)
from .temporal import select_bars_as_of, select_evidence_as_of

__all__ = [
    "AnalyticalAction",
    "CalibrationStatus",
    "Direction",
    "EvidenceKind",
    "EvidencePacket",
    "EvidenceRecord",
    "FactorContribution",
    "FeatureSet",
    "HardGate",
    "Horizon",
    "MACDValue",
    "MagicNineSignal",
    "MarketContext",
    "OHLCVBar",
    "PatternKind",
    "PatternSignal",
    "RiskPlan",
    "RiskPreference",
    "ScenarioCase",
    "ScenarioForecast",
    "ScenarioKind",
    "ScoreResult",
    "ShortBorrowSnapshot",
    "build_risk_plan",
    "build_scenario_forecast",
    "detect_double_bottom",
    "detect_head_and_shoulders",
    "detect_ma5_pullback",
    "ema_series",
    "extract_horizon_features",
    "freeze_evidence_packet",
    "macd",
    "magic_nine",
    "moving_average",
    "rsi",
    "score_horizon",
    "select_bars_as_of",
    "select_evidence_as_of",
    "three_bar_fractals",
]
