from __future__ import annotations

from dataclasses import dataclass


UPSTREAM_PROJECT = "virattt/ai-hedge-fund"
UPSTREAM_COMMIT = "e7c784f118866c5dba8fc2c4ee545f08cc611c61"
UPSTREAM_LICENSE = "MIT"


@dataclass(frozen=True)
class AdviserProfile:
    id: str
    display_name: str
    focus: tuple[str, ...]
    suitable_horizons: tuple[str, ...]
    style_disclaimer: str


_DISCLAIMER = (
    "基于公开投资理念构造的分析视角，不代表、模仿或获其本人认可；"
    "只读冻结证据包，输出仅作为有上限软因子。"
)

ADVISER_PROFILES: tuple[AdviserProfile, ...] = (
    AdviserProfile("damodaran", "Damodaran 风格", ("valuation", "narrative"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("graham", "Graham 风格", ("valuation", "balance-sheet"), ("long",), _DISCLAIMER),
    AdviserProfile("ackman", "Ackman 风格", ("catalyst", "governance"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("wood", "Cathie Wood 风格", ("innovation", "growth"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("munger", "Munger 风格", ("quality", "moat"), ("long",), _DISCLAIMER),
    AdviserProfile("burry", "Burry 风格", ("contrarian", "valuation", "short"), ("short", "swing"), _DISCLAIMER),
    AdviserProfile("pabrai", "Pabrai 风格", ("asymmetry", "downside"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("taleb", "Taleb 风格", ("tail-risk", "convexity"), ("short", "swing", "long"), _DISCLAIMER),
    AdviserProfile("lynch", "Peter Lynch 风格", ("growth", "business"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("fisher", "Phil Fisher 风格", ("growth", "research"), ("long",), _DISCLAIMER),
    AdviserProfile("jhunjhunwala", "Jhunjhunwala 风格", ("growth", "cycle"), ("swing", "long"), _DISCLAIMER),
    AdviserProfile("druckenmiller", "Druckenmiller 风格", ("macro", "momentum", "liquidity"), ("short", "swing"), _DISCLAIMER),
    AdviserProfile("buffett", "Buffett 风格", ("quality", "valuation", "moat"), ("long",), _DISCLAIMER),
)
