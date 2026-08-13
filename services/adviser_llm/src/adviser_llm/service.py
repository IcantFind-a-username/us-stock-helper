"""The two things this layer asks the model to do, and how it degrades."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, Mapping, Sequence, TypeVar

from pydantic import ValidationError
from us_stock_helper_core import HardGate

from .client import AdviserLlmConfig, build_client, call_with_retry
from .errors import AdviserLlmError, LlmUnavailableError, MissingCredentialError
from .evidence import EvidencePacket
from .frameworks import select_frameworks
from .gating import CouncilVerdict, apply_hard_gate
from .prompts import (
    EVIDENCE_ONLY_SYSTEM_PROMPT,
    build_council_system_prompt,
    build_council_user_message,
    build_news_user_message,
)
from .schemas import CouncilBrief, NewsInterpretation
from .traceability import (
    TracedInterpretation,
    trace_brief,
    trace_interpretation,
)


T = TypeVar("T")


@dataclass(frozen=True)
class AdviserOutcome(Generic[T]):
    """Either a result or a stated reason there is none — never a blank.

    A degraded call must not look like a neutral opinion: "the model was
    unreachable" and "the council looked and found nothing" are different
    claims, and only one of them was actually made.
    """

    value: T | None
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.unavailable_reason is None):
            raise ValueError("结果与不可用原因必须且只能有一个")

    @property
    def available(self) -> bool:
        return self.value is not None

    def require(self) -> T:
        if self.value is None:
            raise LlmUnavailableError(
                self.unavailable_reason or "顾问层不可用", attempts=0
            )
        return self.value


class AdviserLlm:
    """Cross-source reading and counterargument. Nothing deterministic."""

    def __init__(
        self,
        client: Any,
        config: AdviserLlmConfig | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._config = config or AdviserLlmConfig()
        self._sleep = sleep
        self._unavailable_reason: str | None = None

    @classmethod
    def from_environment(
        cls,
        config: AdviserLlmConfig | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> "AdviserLlm":
        resolved = config or AdviserLlmConfig()
        try:
            client = build_client(resolved, environ=environ)
        except MissingCredentialError as exc:
            # A missing key degrades the feature loudly instead of crashing the
            # caller's request path.
            service = cls(None, resolved, sleep=sleep)
            service._unavailable_reason = str(exc)
            return service
        return cls(client, resolved, sleep=sleep)

    @property
    def config(self) -> AdviserLlmConfig:
        return self._config

    def interpret_news(
        self, packet: EvidencePacket
    ) -> AdviserOutcome[TracedInterpretation]:
        return self._guarded(lambda: self._read_news(packet))

    def convene_council(
        self,
        packet: EvidencePacket,
        *,
        baseline_score: float,
        baseline_direction: str,
        hard_gates: Sequence[HardGate] = (),
    ) -> AdviserOutcome[CouncilVerdict]:
        return self._guarded(
            lambda: self._run_council(
                packet,
                baseline_score=baseline_score,
                baseline_direction=baseline_direction,
                hard_gates=hard_gates,
            )
        )

    def _read_news(self, packet: EvidencePacket) -> TracedInterpretation:
        config = self._config
        message = call_with_retry(
            lambda: self._client.messages.parse(
                model=config.model,
                max_tokens=config.news_max_output_tokens,
                system=EVIDENCE_ONLY_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": build_news_user_message(packet)}
                ],
                thinking={"type": "adaptive"},
                output_config={"effort": config.news_effort},
                output_format=NewsInterpretation,
                timeout=config.request_timeout_seconds,
            ),
            config=config,
            sleep=self._sleep,
            description="单条新闻解读",
        )
        return trace_interpretation(self._require_parsed(message), packet)

    def _run_council(
        self,
        packet: EvidencePacket,
        *,
        baseline_score: float,
        baseline_direction: str,
        hard_gates: Sequence[HardGate],
    ) -> CouncilVerdict:
        config = self._config
        frameworks = select_frameworks(
            horizon=packet.horizon, maximum=config.max_council_seats
        )
        system = build_council_system_prompt(frameworks)
        user_message = build_council_user_message(
            packet,
            baseline_score=baseline_score,
            baseline_direction=baseline_direction,
        )

        def operation() -> Any:
            # Streamed because a full council brief is long enough that a
            # single blocking response risks an HTTP timeout.
            with self._client.messages.stream(
                model=config.model,
                max_tokens=config.council_max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
                thinking={"type": "adaptive"},
                output_config={"effort": config.council_effort},
                output_format=CouncilBrief,
                timeout=config.council_timeout_seconds,
            ) as stream:
                return stream.get_final_message()

        message = call_with_retry(
            operation,
            config=config,
            sleep=self._sleep,
            description="顾问委员会",
        )
        brief = trace_brief(self._require_parsed(message), packet)
        return apply_hard_gate(
            brief,
            baseline_score=baseline_score,
            baseline_direction=baseline_direction,
            hard_gates=hard_gates,
        )

    @staticmethod
    def _require_parsed(message: Any) -> Any:
        stop_reason = getattr(message, "stop_reason", None)
        if stop_reason == "refusal":
            raise LlmUnavailableError(
                "模型拒绝作答（stop_reason=refusal）", attempts=1
            )
        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            raise LlmUnavailableError(
                "模型没有返回符合 schema 的结构化结果", attempts=1
            )
        return parsed

    def _guarded(self, operation: Callable[[], T]) -> AdviserOutcome[T]:
        if self._unavailable_reason is not None:
            return AdviserOutcome(
                value=None, unavailable_reason=self._unavailable_reason
            )
        try:
            return AdviserOutcome(value=operation(), unavailable_reason=None)
        except (AdviserLlmError, ValidationError) as exc:
            return AdviserOutcome(value=None, unavailable_reason=str(exc))
