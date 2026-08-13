"""Outbound client construction and the bounded retry policy.

This module dials out. It never listens: the adviser layer is a caller of the
Messages API, not a service of its own.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping, TypeVar

import anthropic

from .errors import LlmUnavailableError, MissingCredentialError


LOGGER = logging.getLogger("adviser_llm")

T = TypeVar("T")

_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# A transport failure may clear on its own; a rejected request will not, so
# retrying it only spends money and delays the honest "unavailable" answer.
RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


@dataclass(frozen=True)
class AdviserLlmConfig:
    model: str = "claude-opus-4-8"
    api_key_env: str = "ANTHROPIC_API_KEY"
    request_timeout_seconds: float = 60.0
    council_timeout_seconds: float = 300.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    news_effort: str = "low"
    council_effort: str = "high"
    news_max_output_tokens: int = 4_000
    council_max_output_tokens: int = 16_000
    max_council_seats: int = 13

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.api_key_env.strip():
            raise ValueError("model 与 api_key_env 不能为空")
        for name in ("request_timeout_seconds", "council_timeout_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} 必须是有限正数")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts 必须在 1..5 之间")
        if not math.isfinite(self.retry_backoff_seconds) or (
            self.retry_backoff_seconds < 0
        ):
            raise ValueError("retry_backoff_seconds 不能为负")
        for name in ("news_effort", "council_effort"):
            if getattr(self, name) not in _EFFORTS:
                raise ValueError(f"{name} 必须取自 {_EFFORTS}")
        for name in (
            "news_max_output_tokens",
            "council_max_output_tokens",
            "max_council_seats",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} 必须为正")


def build_client(
    config: AdviserLlmConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> anthropic.Anthropic:
    source = os.environ if environ is None else environ
    raw = source.get(config.api_key_env, "")
    if not raw.strip():
        raise MissingCredentialError(
            f"未配置环境变量 {config.api_key_env}；"
            f"请在运行环境中设置该变量后重试（不要写进仓库或日志）"
        )
    LOGGER.debug("为模型 %s 构造出站客户端", config.model)
    return anthropic.Anthropic(
        api_key=raw.strip(),
        # The SDK's own retry loop is switched off so this module's bounded
        # policy is the only one in force; two stacked loops would multiply
        # attempts and hide a real outage behind a long stall.
        max_retries=0,
        timeout=config.request_timeout_seconds,
    )


# Opus 4.8 list prices, USD per million tokens. A cache read is a tenth of a
# fresh read, which is the whole reason the framework prefix is held stable.
_PRICE_PER_MTOK = {
    "input": 5.00,
    "output": 25.00,
    "cache_write": 6.25,
    "cache_read": 0.50,
}


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What a call actually spent.

    Read from the response rather than estimated: an estimate cannot tell the
    operator whether the framework prefix is being cached, which is the
    difference between five cents and twenty-two.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @classmethod
    def from_response(cls, usage: object | None) -> "TokenUsage | None":
        # Nothing measured is not the same claim as nothing spent.
        if usage is None:
            return None
        return cls(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(
                usage, "cache_creation_input_tokens", 0
            )
            or 0,
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens
            + other.cache_read_input_tokens,
        )

    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1e6 * _PRICE_PER_MTOK["input"]
            + self.output_tokens / 1e6 * _PRICE_PER_MTOK["output"]
            + self.cache_creation_input_tokens / 1e6 * _PRICE_PER_MTOK["cache_write"]
            + self.cache_read_input_tokens / 1e6 * _PRICE_PER_MTOK["cache_read"]
        )


def call_with_retry(
    operation: Callable[[], T],
    *,
    config: AdviserLlmConfig,
    sleep: Callable[[float], None] = time.sleep,
    description: str = "模型调用",
) -> T:
    attempts = 0
    last_error: BaseException | None = None
    while attempts < config.max_attempts:
        attempts += 1
        try:
            return operation()
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            LOGGER.warning(
                "%s 第 %d/%d 次尝试失败: %s",
                description,
                attempts,
                config.max_attempts,
                type(exc).__name__,
            )
            if attempts >= config.max_attempts:
                break
            sleep(config.retry_backoff_seconds * (2 ** (attempts - 1)))
        except anthropic.APIError as exc:
            raise LlmUnavailableError(
                f"{description} 被拒绝且不可重试: {type(exc).__name__}",
                attempts=attempts,
            ) from exc
    raise LlmUnavailableError(
        f"{description} 重试耗尽: {type(last_error).__name__}",
        attempts=attempts,
    ) from last_error
