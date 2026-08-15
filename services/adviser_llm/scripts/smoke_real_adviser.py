"""Run the adviser layer once against the real API and report what it cost.

Every test in this service uses a fake client, which proves the wiring but
never the contract: whether the live API honours the non-empty citations
constraint, and whether a real model stays inside the evidence it was given,
are things only a real request answers. This sends two — one news reading, one
council — so both paths are exercised, and prints the token counts so the
per-call cost is a measurement rather than an estimate.

    ANTHROPIC_API_KEY=... python3 scripts/smoke_real_adviser.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

# Opus 4.8 list prices, USD per million tokens.
PRICE = {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50}


def _packet(as_of):
    from adviser_llm.evidence import EvidenceItem, build_packet

    return build_packet(
        symbol="NVDA",
        horizon="short",
        as_of=as_of,
        items=[
            EvidenceItem(
                id="smoke-1",
                headline="NVIDIA raises full-year revenue guidance",
                body=(
                    "The company lifted its full-year outlook, citing data-centre "
                    "demand. It did not disclose a per-customer breakdown, and gave "
                    "no gross-margin guidance for the coming quarter."
                ),
                url="https://example.invalid/smoke-1",
                publisher="Smoke Wire",
                available_at=as_of - timedelta(minutes=19),
                received_at=as_of - timedelta(minutes=18),
                symbols=("NVDA",),
            ),
            EvidenceItem(
                id="smoke-2",
                headline="Supplier reports tighter advanced-packaging capacity",
                body=(
                    "A packaging supplier said capacity remains constrained into "
                    "next quarter. The statement named no customer."
                ),
                url="https://example.invalid/smoke-2",
                publisher="Smoke Trade Press",
                available_at=as_of - timedelta(minutes=44),
                received_at=as_of - timedelta(minutes=43),
                symbols=("NVDA",),
                is_counter_evidence=True,
            ),
        ],
    )


_CACHE_NOT_ENABLED_NOTE = (
    "本服务未启用 prompt caching（council 系统前缀约 1059 token，低于 Opus 4.8 "
    "的 4096 token 最小可缓存长度）；再跑一次费用相同。"
)


def _cache_note(usage) -> str | None:
    """cache_read_input_tokens == 0 never means "the first call primed the
    cache": no request this service sends sets cache_control, so nothing is
    ever written to a cache in the first place. Commit 092be7a measured the
    council's stable prefix at 1059 tokens, below Opus 4.8's 4096-token
    minimum, and found enabling caching would not have helped either — a
    rerun costs exactly the same as the first call, every time.
    """
    if usage.cache_read_input_tokens == 0:
        return _CACHE_NOT_ENABLED_NOTE
    return None


def _price(usage) -> float:
    return (
        getattr(usage, "input_tokens", 0) / 1e6 * PRICE["input"]
        + getattr(usage, "output_tokens", 0) / 1e6 * PRICE["output"]
        + getattr(usage, "cache_creation_input_tokens", 0) / 1e6 * PRICE["cache_write"]
        + getattr(usage, "cache_read_input_tokens", 0) / 1e6 * PRICE["cache_read"]
    )


def _report(label: str, outcome) -> None:
    if not outcome.available:
        print(f"{label}: unavailable — {outcome.unavailable_reason}")
        return
    print(f"\n=== {label} ===")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; nothing was sent.", file=sys.stderr)
        return 2

    from adviser_llm import AdviserLlm

    as_of = datetime.now(tz=UTC)
    packet = _packet(as_of)
    service = AdviserLlm.from_environment()

    reading = service.interpret_news(packet)
    _report("news reading", reading)
    if reading.available:
        traced = reading.require()
        print(repr(traced)[:1200])

    council = service.convene_council(
        packet, baseline_score=61.0, baseline_direction="bullish"
    )
    _report("council", council)
    if council.available:
        print(repr(council.require())[:2000])

    usage = service.usage
    if usage is None:
        print("\nno usage was reported; nothing to price")
        return 0
    print(
        f"\n输入 {usage.input_tokens}  输出 {usage.output_tokens}  "
        f"缓存写入 {usage.cache_creation_input_tokens}  "
        f"缓存读取 {usage.cache_read_input_tokens}"
    )
    print(f"这两次调用实测花费 ${usage.cost_usd():.4f}")
    note = _cache_note(usage)
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
