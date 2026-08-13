"""The frozen, point-in-time material the model is allowed to reason over."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal
from urllib.parse import urlparse


Horizon = Literal["short", "swing", "long"]

HORIZONS: tuple[str, ...] = ("short", "swing", "long")

PACKET_SCHEMA = "adviser-llm-evidence-packet/v1"


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} 必须带时区")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One citable entry.

    ``available_at`` is when the world could first know the fact and
    ``received_at`` is when this system actually took delivery of it. Both are
    required and neither may be inferred from the wall clock: a guessed
    timestamp would silently reorder the evidence a conclusion rests on.
    """

    id: str
    headline: str
    body: str
    url: str
    publisher: str
    available_at: datetime
    received_at: datetime
    symbols: tuple[str, ...] = ()
    is_counter_evidence: bool = False

    def __post_init__(self) -> None:
        _require_aware(self.available_at, "available_at")
        _require_aware(self.received_at, "received_at")
        if self.received_at < self.available_at:
            raise ValueError("received_at 不能早于 available_at")
        for name in ("id", "headline", "body", "url", "publisher"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"证据字段 {name} 不能为空")
        parsed = urlparse(self.url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("url 必须是不含凭据的 HTTP(S) 链接")
        normalized = tuple(sorted({symbol.strip().upper() for symbol in self.symbols}))
        if any(not symbol for symbol in normalized):
            raise ValueError("证据标的不能为空字符串")
        object.__setattr__(self, "symbols", normalized)

    @property
    def text(self) -> str:
        """Everything a citation may legitimately quote from."""
        return f"{self.headline}\n{self.body}"


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    symbol: str
    horizon: str
    as_of: datetime
    items: tuple[EvidenceItem, ...]

    def item(self, evidence_id: str) -> EvidenceItem | None:
        for candidate in self.items:
            if candidate.id == evidence_id:
                return candidate
        return None

    @property
    def latest_available_at(self) -> datetime:
        return max(item.available_at for item in self.items)

    @property
    def latest_received_at(self) -> datetime:
        return max(item.received_at for item in self.items)

    def render(self, *, max_body_characters: int = 600) -> str:
        if max_body_characters < 80:
            raise ValueError("max_body_characters 过小，会毁掉可引用的原文")
        lines = [
            f"schema={PACKET_SCHEMA}",
            f"symbol={self.symbol}",
            f"horizon={self.horizon}",
            f"as_of={self.as_of.isoformat()}",
            "",
        ]
        for item in self.items:
            lines.extend(
                (
                    f"[{item.id}]",
                    f"标题: {item.headline}",
                    f"正文: {item.body[:max_body_characters]}",
                    f"来源: {item.publisher}",
                    f"链接: {item.url}",
                    f"发布时刻 available_at: {item.available_at.isoformat()}",
                    f"接收时刻 received_at: {item.received_at.isoformat()}",
                    f"标的: {'、'.join(item.symbols) or '未标注'}",
                    f"是否反证: {'是' if item.is_counter_evidence else '否'}",
                    "",
                )
            )
        return "\n".join(lines)


def build_packet(
    *,
    symbol: str,
    horizon: str,
    as_of: datetime,
    items: Iterable[EvidenceItem],
) -> EvidencePacket:
    _require_aware(as_of, "as_of")
    clean_symbol = symbol.strip().upper()
    if not clean_symbol:
        raise ValueError("symbol 不能为空")
    if horizon not in HORIZONS:
        raise ValueError(f"horizon 必须是 {HORIZONS} 之一")

    visible: dict[str, EvidenceItem] = {}
    for item in items:
        if item.available_at > as_of:
            continue
        if item.symbols and clean_symbol not in item.symbols:
            continue
        if item.id in visible:
            raise ValueError(f"证据 id 重复: {item.id}")
        visible[item.id] = item

    if not visible:
        # Refusing beats shipping an empty packet: a model handed nothing will
        # answer from memory, and that answer cannot be traced to anything.
        raise ValueError("截至 as_of 没有任何可用证据")

    ordered = tuple(
        sorted(visible.values(), key=lambda item: (item.available_at, item.id))
    )
    return EvidencePacket(
        symbol=clean_symbol,
        horizon=horizon,
        as_of=as_of,
        items=ordered,
    )
