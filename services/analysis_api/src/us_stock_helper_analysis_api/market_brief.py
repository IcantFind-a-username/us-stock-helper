"""The Dashboard's real-mode market hero, built from pieces a decision already trusts.

`GET /market-brief` composes only what a decision already composes for one
symbol — `EvidencePacketBuilder`, `MarketSentiment`, the request-scoped
evidence-gap accounting, citation freshness — over an empty focus instead of
one symbol's. No symbol score, no forecast, no risk plan, no adviser content
and no model call reach this route: those all require a symbol and a horizon
this route never takes.

The nine driver categories the Dashboard's market hero is designed to show
(`apps/mobile/src/domain/models.ts` `MarketDriverCategory`) are named here
whether or not this composition can source them. Today it sources exactly
one — the aggregate news/evidence sentiment — and says so about the other
eight instead of inventing a number for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from information_layer import EvidencePacketBuilder, MarketSentiment
from information_layer.feeds import EvidenceUnavailable

from .service import AnalysisService, _citation, _iso


SCHEMA_VERSION = "1"

_EASTERN = ZoneInfo("America/New_York")

# Mirrors apps/mobile/src/domain/models.ts's MarketDriverCategory so a later
# task can map this disclosure onto the Dashboard's driver chips one for one.
_DRIVER_CATEGORIES: tuple[str, ...] = (
    "news-sentiment",
    "breadth",
    "volatility-options",
    "sector",
    "rates-dollar",
    "macro-credit-energy",
    "liquidity-correlation",
    "broad-market-trend",
    "geopolitics",
)

_UNSOURCED_REASON: dict[str, str] = {
    "breadth": "大盘涨跌家数、新高新低等广度数据源尚未接入。",
    "volatility-options": "波动率与期权持仓数据源尚未接入。",
    "sector": "板块轮动强弱数据源尚未接入。",
    "rates-dollar": "利率与美元指数数据源尚未接入。",
    "macro-credit-energy": "信用利差与能源价格数据源尚未接入。",
    "liquidity-correlation": "流动性与相关性压力数据源尚未接入。",
    "broad-market-trend": "大盘趋势判定数据源尚未接入。",
    "geopolitics": "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。",
}

_NOTHING_READABLE_REASON = "本次没有可读取的情报源，无法给出该驱动的结论。"


@dataclass(frozen=True, slots=True)
class MarketBriefService:
    """Wraps an `AnalysisService` rather than owning a provider of its own.

    The evidence provider, and the collector and poll coordinator behind it,
    are built once at startup and shared by every `/decision` request; this
    wrapper reads through the exact same `AnalysisService` instance so a
    burst of brief requests shares that collector too, instead of standing up
    a second one this route would have to throttle on its own.
    """

    service: AnalysisService

    def market_brief(self) -> dict[str, Any]:
        try:
            events, gaps = self.service.read_market_evidence()
        except EvidenceUnavailable as error:
            return self._unavailable(error)

        # Sampled after the evidence fetch returns, for the same reason a
        # decision's cutoff is taken after its own fetch: a live collector
        # stamps available_at at the moment of the fetch, so sampling the
        # clock any earlier would file whatever this request's own fetch just
        # retrieved as being from the future, and silently drop it.
        as_of = self.service.clock()
        packet = EvidencePacketBuilder().build(events, as_of=as_of, focus_symbols=())
        sentiment = packet.sentiment
        citations = [
            _citation(item)
            for item in packet.citations
            # This surface promises https-only citations; every shipped feed
            # adapter already speaks https, but the check is made here rather
            # than trusted, since a citation is a URL this app will open.
            if item.canonical_url.startswith("https://")
        ]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "available",
            "reason": None,
            "decisionCutoff": _iso(as_of),
            "marketSession": _market_session(as_of),
            "dataHealth": _data_health(sentiment, gaps, citations),
            "sentiment": {
                "conclusion": sentiment.conclusion,
                "actionScore": sentiment.action_score,
                "uncertainty": list(sentiment.uncertainty),
            },
            "driverCoverage": _driver_coverage(sentiment),
            "citations": citations,
            "sourceGaps": list(gaps),
        }

    def _unavailable(self, error: EvidenceUnavailable) -> dict[str, Any]:
        # Every configured source failed and nothing was already held for any
        # symbol, so there is nothing honest to compose a sentiment or a
        # driver value from — the whole brief is refused, naming the sources,
        # rather than answering with a quiet market this outage only looks
        # like.
        as_of = self.service.clock()
        gaps = [
            f"{failure.source_id}（{failure.reason}）" for failure in error.failures
        ]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "本次未能读取任何情报源：" + "、".join(gaps),
            "decisionCutoff": _iso(as_of),
            "marketSession": _market_session(as_of),
            "dataHealth": None,
            "sentiment": None,
            "driverCoverage": [
                {
                    "category": category,
                    "available": False,
                    "conclusion": None,
                    "actionScore": None,
                    "missingReason": _NOTHING_READABLE_REASON,
                }
                for category in _DRIVER_CATEGORIES
            ],
            "citations": [],
            "sourceGaps": gaps,
        }


def _market_session(as_of: datetime) -> str:
    """A best-effort NYSE session label from the wall clock alone.

    No exchange calendar is consulted, so a holiday reads as a plain weekday
    session; that is a known simplification of this composition, not a claim
    the response makes about itself, and callers only ever see the four
    coarse labels below.
    """

    local = as_of.astimezone(_EASTERN)
    if local.weekday() >= 5:
        return "closed"
    minutes = local.hour * 60 + local.minute
    if minutes < 4 * 60 or minutes >= 20 * 60:
        return "closed"
    if minutes < 9 * 60 + 30:
        return "premarket"
    if minutes < 16 * 60:
        return "regular"
    return "afterhours"


def _data_health(
    sentiment: MarketSentiment,
    gaps: tuple[str, ...],
    citations: list[dict[str, Any]],
) -> str:
    """The four-state read a reader needs before trusting `sentiment` at all.

    Ordered most-severe-first: no measured reading at all outranks a reading
    built from conflicting sources, which outranks a reading that is merely
    behind (an unreachable source this round, or evidence older than the
    freshness window) but otherwise clean.
    """

    if not sentiment.action_score_measured:
        return "insufficient"
    if "来源冲突" in sentiment.uncertainty:
        return "conflict"
    if gaps or any(item["stale"] for item in citations):
        return "stale"
    return "fresh"


def _driver_coverage(sentiment: MarketSentiment) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for category in _DRIVER_CATEGORIES:
        if category == "news-sentiment":
            coverage.append(
                {
                    "category": category,
                    "available": True,
                    "conclusion": sentiment.conclusion,
                    "actionScore": sentiment.action_score,
                    "missingReason": None,
                }
            )
        else:
            coverage.append(
                {
                    "category": category,
                    "available": False,
                    "conclusion": None,
                    "actionScore": None,
                    "missingReason": _UNSOURCED_REASON[category],
                }
            )
    return coverage
