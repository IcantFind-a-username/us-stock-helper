"""Structured-output schemas that make an untraceable answer unrepresentable.

``citations`` is required and non-empty at the schema level, so a conclusion
without a source cannot even be constructed — the rejection happens before any
of it can reach a screen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Confidence = Literal["low", "medium", "high"]
Stance = Literal["bullish", "neutral", "bearish"]


def _require_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空白")
    return stripped


class _StrictModel(BaseModel):
    # Unmodelled fields are refused rather than ignored: a field we did not ask
    # for is a claim nobody validated.
    model_config = ConfigDict(extra="forbid")


class Citation(_StrictModel):
    evidence_id: str = Field(
        min_length=1, description="必须是证据包里出现过的条目 id"
    )
    quote: str = Field(
        min_length=1, description="从该条目原文逐字复制的片段，不得改写"
    )

    # The original link is deliberately absent: it is resolved from the frozen
    # packet, because a fabricated URL is indistinguishable from a real one.

    @field_validator("evidence_id", "quote")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return _require_text(value)


class Conclusion(_StrictModel):
    statement: str = Field(min_length=1)
    confidence: Confidence
    citations: list[Citation] = Field(min_length=1)
    counter_evidence: list[Citation] = Field(default_factory=list)

    @field_validator("statement")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return _require_text(value)


class FrameworkOpinion(_StrictModel):
    framework_id: str = Field(min_length=1)
    stance: Stance
    conclusions: list[Conclusion] = Field(min_length=1)
    blind_spot_note: str = Field(
        min_length=1, description="本框架在这次判断上的已知盲区"
    )

    @field_validator("framework_id", "blind_spot_note")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return _require_text(value)


class CouncilBrief(_StrictModel):
    summary: str = Field(min_length=1)
    opinions: list[FrameworkOpinion] = Field(min_length=1)

    @field_validator("summary")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return _require_text(value)


class NewsInterpretation(_StrictModel):
    headline_summary: str = Field(min_length=1)
    cross_source_reading: str = Field(min_length=1)
    investment_impact: list[Conclusion] = Field(min_length=1)
    unknowns: list[str] = Field(
        default_factory=list, description="证据无法回答的问题，直说不知道"
    )

    @field_validator("headline_summary", "cross_source_reading")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        return _require_text(value)
