"""Mock Anthropic clients. No test in this package may reach the network."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from adviser_llm import EvidenceItem, build_packet


UTC = timezone.utc


class ExplodingClient:
    """Fails loudly if any deterministic code path touches the model."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"deterministic code must not call the model: {name}")


@dataclass
class FakeMessage:
    parsed_output: Any
    stop_reason: str = "end_turn"
    stop_details: Any = None


class _FakeStreamManager:
    def __init__(self, message: FakeMessage) -> None:
        self._message = message
        self.closed = False

    def __enter__(self) -> "_FakeStreamManager":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.closed = True

    def get_final_message(self) -> FakeMessage:
        return self._message


@dataclass
class FakeMessages:
    parse_results: list[Any] = field(default_factory=list)
    stream_results: list[Any] = field(default_factory=list)
    parse_calls: list[dict[str, Any]] = field(default_factory=list)
    stream_calls: list[dict[str, Any]] = field(default_factory=list)

    def parse(self, **kwargs: Any) -> Any:
        self.parse_calls.append(kwargs)
        return self._next(self.parse_results, "parse")

    def stream(self, **kwargs: Any) -> Any:
        self.stream_calls.append(kwargs)
        outcome = self._next(self.stream_results, "stream")
        return _FakeStreamManager(outcome)

    @staticmethod
    def _next(queue: list[Any], label: str) -> Any:
        if not queue:
            raise AssertionError(f"unexpected extra {label} call")
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)

    @classmethod
    def returning(
        cls,
        *,
        parse: list[Any] | None = None,
        stream: list[Any] | None = None,
    ) -> "FakeClient":
        return cls(
            messages=FakeMessages(
                parse_results=list(parse or []),
                stream_results=list(stream or []),
            )
        )


AS_OF = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def evidence_item(
    *,
    item_id: str = "ev-1",
    headline: str = "Nvidia 上调数据中心指引",
    body: str = "公司称本季数据中心收入指引上调 12%。",
    url: str = "https://example.com/nvda-guidance",
    publisher: str = "Example Wire",
    available_at: datetime | None = None,
    received_at: datetime | None = None,
    symbols: tuple[str, ...] = ("NVDA",),
    is_counter_evidence: bool = False,
) -> EvidenceItem:
    published = available_at or datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    return EvidenceItem(
        id=item_id,
        headline=headline,
        body=body,
        url=url,
        publisher=publisher,
        available_at=published,
        received_at=received_at or published,
        symbols=symbols,
        is_counter_evidence=is_counter_evidence,
    )


def sample_packet(*items: EvidenceItem, as_of: datetime = AS_OF):
    return build_packet(
        symbol="NVDA",
        horizon="swing",
        as_of=as_of,
        items=items or (evidence_item(),),
    )
