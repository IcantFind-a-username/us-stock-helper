"""Outbound-only LLM adviser layer.

The model is asked for exactly three things: cross-source reading,
counterargument, and natural-language advice. Sentiment scoring, clustering
and CIK attribution stay in deterministic, backtestable code elsewhere.
"""

from .client import (
    RETRYABLE_ERRORS,
    AdviserLlmConfig,
    build_client,
    call_with_retry,
)
from .errors import (
    AdviserLlmError,
    FabricatedFactError,
    LlmUnavailableError,
    MissingCredentialError,
    TraceabilityError,
)
from .evidence import (
    HORIZONS,
    PACKET_SCHEMA,
    EvidenceItem,
    EvidencePacket,
    build_packet,
)
from .frameworks import (
    ADVISORY_NOTE,
    ANALYSIS_FRAMEWORKS,
    AnalysisFramework,
    framework_by_id,
    select_frameworks,
)
from .gating import CouncilVerdict, apply_hard_gate
from .prompts import (
    EVIDENCE_ONLY_SYSTEM_PROMPT,
    build_council_system_prompt,
    build_council_user_message,
    build_news_user_message,
)
from .schemas import (
    Citation,
    Conclusion,
    CouncilBrief,
    FrameworkOpinion,
    NewsInterpretation,
)
from .service import AdviserLlm, AdviserOutcome
from .traceability import (
    ResolvedCitation,
    TracedBrief,
    TracedConclusion,
    TracedInterpretation,
    TracedOpinion,
    trace_brief,
    trace_conclusion,
    trace_interpretation,
)

__all__ = [
    "ADVISORY_NOTE",
    "ANALYSIS_FRAMEWORKS",
    "AdviserLlm",
    "AdviserLlmConfig",
    "AdviserLlmError",
    "AdviserOutcome",
    "AnalysisFramework",
    "Citation",
    "Conclusion",
    "CouncilBrief",
    "CouncilVerdict",
    "EVIDENCE_ONLY_SYSTEM_PROMPT",
    "EvidenceItem",
    "EvidencePacket",
    "FabricatedFactError",
    "FrameworkOpinion",
    "HORIZONS",
    "LlmUnavailableError",
    "MissingCredentialError",
    "NewsInterpretation",
    "PACKET_SCHEMA",
    "RETRYABLE_ERRORS",
    "ResolvedCitation",
    "TraceabilityError",
    "TracedBrief",
    "TracedConclusion",
    "TracedInterpretation",
    "TracedOpinion",
    "apply_hard_gate",
    "build_client",
    "build_council_system_prompt",
    "build_council_user_message",
    "build_news_user_message",
    "build_packet",
    "call_with_retry",
    "framework_by_id",
    "select_frameworks",
    "trace_brief",
    "trace_conclusion",
    "trace_interpretation",
]
