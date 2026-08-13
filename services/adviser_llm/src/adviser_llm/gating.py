"""Turn a traced brief into a bounded, gate-subordinate soft factor.

The numeric mapping lives here rather than in the model: a score the model
wrote could not be reproduced, and the hard gate has to be able to veto it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from us_stock_helper_core import ADVISER_SCORE_CAP, HardGate

from .traceability import TracedBrief, TracedOpinion


DISCLAIMER = (
    "顾问观点是分析建议，不是操作指令；其影响有上限，且任一硬门未通过时一律作废。"
)

_STANCE_SIGN = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
_CONFIDENCE_WEIGHT = {"low": 0.25, "medium": 0.5, "high": 1.0}
_DIRECTIONS = frozenset(_STANCE_SIGN)


@dataclass(frozen=True, slots=True)
class CouncilVerdict:
    baseline_score: float
    adjusted_score: float
    score_adjustment: float
    objective_direction: str
    actionable: bool
    blocked_by: tuple[HardGate, ...]
    brief: TracedBrief
    disclaimer: str = DISCLAIMER


def _opinion_weight(opinion: TracedOpinion) -> float:
    # An opinion is only as strong as its most confident supported conclusion;
    # averaging would let a pile of throwaway remarks dilute a real finding.
    confidence = max(
        _CONFIDENCE_WEIGHT[conclusion.confidence]
        for conclusion in opinion.conclusions
    )
    return _STANCE_SIGN[opinion.stance] * confidence


def apply_hard_gate(
    brief: TracedBrief,
    *,
    baseline_score: float,
    baseline_direction: str,
    hard_gates: Sequence[HardGate] = (),
) -> CouncilVerdict:
    if not 0 <= baseline_score <= 100:
        raise ValueError("baseline_score 必须在 0..100 之间")
    if baseline_direction not in _DIRECTIONS:
        raise ValueError("baseline_direction 必须是多头、中性或空头之一")
    if not brief.opinions:
        raise ValueError("空的顾问简报无法定量")

    blocked_by = tuple(hard_gates)
    net = sum(_opinion_weight(opinion) for opinion in brief.opinions) / len(
        brief.opinions
    )
    proposed = max(
        -ADVISER_SCORE_CAP, min(ADVISER_SCORE_CAP, net * ADVISER_SCORE_CAP)
    )
    adjustment = 0.0 if blocked_by else proposed
    adjusted = max(0.0, min(100.0, baseline_score + adjustment))
    return CouncilVerdict(
        baseline_score=baseline_score,
        adjusted_score=adjusted,
        score_adjustment=adjustment,
        # The council never overrides the objective direction; it only nudges
        # the score inside the cap.
        objective_direction=baseline_direction,
        actionable=not blocked_by,
        blocked_by=blocked_by,
        brief=brief,
    )
