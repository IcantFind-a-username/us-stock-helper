"""The Dashboard's real-mode market hero, built from pieces a decision already trusts.

`GET /market-brief` composes only what a decision already composes for one
symbol — `EvidencePacketBuilder`, `MarketSentiment`, the request-scoped
evidence-gap accounting, citation freshness — over an empty focus instead of
one symbol's. No symbol score, no forecast, no risk plan, no adviser content
and no model call reach this route: those all require a symbol and a horizon
this route never takes.

The nine driver categories the Dashboard's market hero is designed to show
(`apps/mobile/src/domain/models.ts` `MarketDriverCategory`) are named here
whether or not this composition can source them. Two are sourced today —
`breadth` and `sector`, from `us_stock_helper_core`'s `breadth-v1` and
`sector-rs-v1` engines over a configurable daily-bar universe read from the
market gateway — and the remaining seven say why they are not, instead of
inventing a number for them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from information_layer import EvidencePacketBuilder, MarketSentiment
from information_layer.feeds import EvidenceUnavailable
from us_stock_helper_core import (
    OHLCVBar,
    percent_above_moving_average,
    relative_strength_ranking,
)

from .market_universe_cache import CacheOutcome, MarketUniverseCache
from .service import AnalysisProvider, AnalysisService, _citation, _iso


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
    "volatility-options": "波动率与期权持仓数据源尚未接入。",
    "rates-dollar": "利率与美元指数数据源尚未接入。",
    "macro-credit-energy": "信用利差与能源价格数据源尚未接入。",
    "liquidity-correlation": "流动性与相关性压力数据源尚未接入。",
    "broad-market-trend": "大盘趋势判定数据源尚未接入。",
    "geopolitics": "地缘政治的独立驱动判定尚未接入，相关报道已计入整体新闻情绪。",
}

_NOTHING_READABLE_REASON = "本次没有可读取的情报源，无法给出该驱动的结论。"

# The entry-level twin of sentiment.uncertainty's "情绪未测量": a reader who
# only looks at driverCoverage (never the top-level sentiment block) must
# still be told this driver was not actually sourced this round, rather than
# reading available:true next to a 中性/0.0 that was never measured.
_SENTIMENT_UNMEASURED_REASON = "情绪未测量（该时段无可读事件）"

_BREADTH_INTERVAL = "day"
_BREADTH_MA_PERIOD = 50
# Bounds "the universe size" the task discipline requires: a watchlist far
# larger than this is truncated (disclosed via a note), never fetched whole.
_BREADTH_MAX_UNIVERSE = 60
_SECTOR_MAX_UNIVERSE = 30
# The shortest of relative_strength.py's own DEFAULT_LOOKBACKS (~1 trading
# month) — the single headline reading this driver slot serves; the fuller
# multi-lookback table is a richer surface for a later task, not this one.
_SECTOR_LOOKBACK_DAYS = 21

_BREADTH_NOT_CONFIGURED_REASON = (
    "自选广度尚未配置（未设置自选股清单），且本次无法从行情网关读取观察列表，"
    "暂无法给出结论。"
)
_SECTOR_NOT_CONFIGURED_REASON = "板块强弱尚未配置板块 ETF 与基准品种，暂无法给出结论。"


@dataclass(frozen=True, slots=True)
class MarketBriefUniverseConfig:
    """Configures the breadth/sector-RS universes; every field optional.

    An unset ``breadth_symbols`` does not mean breadth stays unavailable — it
    means the operator's own watchlist (read live from the gateway, never
    configured here) is tried instead. Sector RS has no such default: an
    unset ``sector_symbols``/``sector_benchmark`` pair leaves that driver
    unavailable until an operator configures both.
    """

    breadth_symbols: tuple[str, ...] | None = None
    sector_symbols: tuple[str, ...] = ()
    sector_benchmark: str | None = None

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "MarketBriefUniverseConfig":
        env = os.environ if environment is None else environment
        breadth = _env_symbol_list(env, "ANALYSIS_API_BREADTH_UNIVERSE")
        if breadth is not None and len(breadth) > _BREADTH_MAX_UNIVERSE:
            raise ValueError(
                "ANALYSIS_API_BREADTH_UNIVERSE must list at most "
                f"{_BREADTH_MAX_UNIVERSE} symbols"
            )
        sector = _env_symbol_list(env, "ANALYSIS_API_SECTOR_RS_SYMBOLS") or ()
        if len(sector) > _SECTOR_MAX_UNIVERSE:
            raise ValueError(
                "ANALYSIS_API_SECTOR_RS_SYMBOLS must list at most "
                f"{_SECTOR_MAX_UNIVERSE} symbols"
            )
        benchmark_raw = (env.get("ANALYSIS_API_SECTOR_RS_BENCHMARK") or "").strip()
        benchmark = benchmark_raw.upper() or None
        if sector and benchmark is None:
            raise ValueError(
                "ANALYSIS_API_SECTOR_RS_BENCHMARK is required when "
                "ANALYSIS_API_SECTOR_RS_SYMBOLS is set"
            )
        if benchmark is not None and not sector:
            raise ValueError(
                "ANALYSIS_API_SECTOR_RS_SYMBOLS is required when "
                "ANALYSIS_API_SECTOR_RS_BENCHMARK is set"
            )
        return cls(
            breadth_symbols=breadth,
            sector_symbols=sector,
            sector_benchmark=benchmark,
        )


def _env_symbol_list(env: Mapping[str, str], name: str) -> tuple[str, ...] | None:
    raw = env.get(name)
    if raw is None:
        return None
    symbols = tuple(
        dict.fromkeys(part.strip().upper() for part in raw.split(",") if part.strip())
    )
    if not symbols:
        raise ValueError(f"{name} must not be blank when set")
    return symbols


@dataclass(frozen=True, slots=True)
class MarketBriefUniverse:
    """The breadth/sector-RS configuration and its shared, in-process cache.

    Built once — `build_server` reads `MarketBriefUniverseConfig` from the
    environment at startup, mirroring `AnalysisServerConfig` — and threaded
    through every request's `MarketBriefService`. The cache, unlike
    `MarketBriefService` itself (recreated per request, same as `/decision`),
    survives across the requests it exists to throttle: it lives here, one
    level up, exactly where the evidence collector's own poll coordinator
    lives relative to the same per-request service wrapper.
    """

    config: MarketBriefUniverseConfig = field(default_factory=MarketBriefUniverseConfig)
    cache: MarketUniverseCache = field(default_factory=MarketUniverseCache)


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
    universe: MarketBriefUniverse = field(default_factory=MarketBriefUniverse)

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
        # The point-in-time invariant may exclude an event stamped after even
        # this honestly-taken cutoff (an embargo, a skewed publisher clock).
        # The exclusion is legitimate; hiding it is not — mirrors /decision's
        # own disclosure of output.evidence_packet.excluded_future_event_ids.
        notes: list[str] = []
        excluded = packet.excluded_future_event_ids
        if excluded:
            notes.append(
                f"有 {len(excluded)} 条证据在决策截点之后才可用，"
                "未纳入本次结论：" + "、".join(excluded)
            )

        breadth_entry, breadth_notes = self._cached_entry(
            "breadth", as_of, self._compute_breadth
        )
        sector_entry, sector_notes = self._cached_entry(
            "sector", as_of, self._compute_sector
        )
        notes.extend(breadth_notes)
        notes.extend(sector_notes)

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "available",
            "reason": None,
            "decisionCutoff": _iso(as_of),
            "marketSession": _market_session(as_of),
            # breadth/RS becoming available never feeds back into this: it is
            # derived solely from sentiment/gap/citation accounting, so a
            # sourced driver can never mask an unmeasured sentiment reading.
            "dataHealth": _data_health(sentiment, gaps, citations),
            "sentiment": {
                "conclusion": sentiment.conclusion,
                "actionScore": sentiment.action_score,
                "uncertainty": list(sentiment.uncertainty),
            },
            "driverCoverage": _driver_coverage(sentiment, breadth_entry, sector_entry),
            "citations": citations,
            "sourceGaps": list(gaps),
            "notes": notes,
        }

    def _cached_entry(
        self,
        name: str,
        as_of: datetime,
        compute: Callable[
            [datetime], CacheOutcome[tuple[dict[str, Any], tuple[str, ...]]]
        ],
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        trading_date = _trading_date(as_of)
        value, _hit = self.universe.cache.get_or_compute(
            name, trading_date, lambda: compute(as_of)
        )
        return value

    def _compute_breadth(
        self, as_of: datetime
    ) -> CacheOutcome[tuple[dict[str, Any], tuple[str, ...]]]:
        entry, notes, healthy = _breadth_driver_entry(
            self.service.provider, self.universe.config, as_of
        )
        return CacheOutcome(value=(entry, notes), healthy=healthy)

    def _compute_sector(
        self, as_of: datetime
    ) -> CacheOutcome[tuple[dict[str, Any], tuple[str, ...]]]:
        entry, notes, healthy = _sector_driver_entry(
            self.service.provider, self.universe.config, as_of
        )
        return CacheOutcome(value=(entry, notes), healthy=healthy)

    def _unavailable(self, error: EvidenceUnavailable) -> dict[str, Any]:
        # Every configured source failed and nothing was already held for any
        # symbol, so there is nothing honest to compose a sentiment or a
        # driver value from — the whole brief is refused, naming the sources,
        # rather than answering with a quiet market this outage only looks
        # like. Breadth/sector-RS are candle-derived, not evidence-derived,
        # but this path stays unconditional: the documented "unavailable"
        # contract is that every one of the nine categories reports the same
        # shared reason, with nothing invented.
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
                    "computedAt": None,
                }
                for category in _DRIVER_CATEGORIES
            ],
            "citations": [],
            "sourceGaps": gaps,
            "notes": [],
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


def _trading_date(as_of: datetime) -> date:
    """The calendar date whose close the freshest daily bar should reflect.

    No exchange calendar is consulted here either (the same simplification
    `_market_session` already discloses): before the 16:00 ET close the
    freshest completed daily bar is still yesterday's, so the cache key rolls
    back a day until then. This only controls how often the universe gets
    refetched — never what a fetch itself returns — and the served entry's
    own `computedAt` is the honest record of when a value was actually
    computed, cache hit or not.
    """

    local = as_of.astimezone(_EASTERN)
    session_date = local.date()
    if local.hour < 16:
        session_date -= timedelta(days=1)
    return session_date


def _data_health(
    sentiment: MarketSentiment,
    gaps: tuple[str, ...],
    citations: list[dict[str, Any]],
) -> str:
    """The four-state read a reader needs before trusting `sentiment` at all.

    Ordered most-severe-first: no measured reading at all outranks a reading
    built from conflicting sources, which outranks a reading that is merely
    behind (an unreachable source this round, or evidence older than the
    freshness window) but otherwise clean. Deliberately blind to
    breadth/sector-RS: those are sourced from candles, not from the evidence
    sweep this reading describes, so their availability must never soften an
    unmeasured or conflicted sentiment reading into a healthier-looking state.
    """

    if not sentiment.action_score_measured:
        return "insufficient"
    if "来源冲突" in sentiment.uncertainty:
        return "conflict"
    if gaps or any(item["stale"] for item in citations):
        return "stale"
    return "fresh"


def _driver_coverage(
    sentiment: MarketSentiment,
    breadth_entry: dict[str, Any],
    sector_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for category in _DRIVER_CATEGORIES:
        if category == "news-sentiment":
            if sentiment.action_score_measured:
                coverage.append(
                    {
                        "category": category,
                        "available": True,
                        "conclusion": sentiment.conclusion,
                        "actionScore": sentiment.action_score,
                        "missingReason": None,
                        "computedAt": None,
                    }
                )
            else:
                # Mirrors the top-level sentiment.action_score_measured
                # discipline at the entry level: unmeasured never presents
                # as a measured 中性/0.0, even to a consumer reading only
                # this entry and not sentiment.uncertainty.
                coverage.append(
                    {
                        "category": category,
                        "available": False,
                        "conclusion": None,
                        "actionScore": None,
                        "missingReason": _SENTIMENT_UNMEASURED_REASON,
                        "computedAt": None,
                    }
                )
        elif category == "breadth":
            coverage.append(breadth_entry)
        elif category == "sector":
            coverage.append(sector_entry)
        else:
            coverage.append(
                {
                    "category": category,
                    "available": False,
                    "conclusion": None,
                    "actionScore": None,
                    "missingReason": _UNSOURCED_REASON[category],
                    "computedAt": None,
                }
            )
    return coverage


# ---------------------------------------------------------------------------
# Breadth: percent of a daily-bar universe closing above its own 50-day
# moving average (breadth-v1), over the operator's watchlist by default.
# ---------------------------------------------------------------------------


def _unavailable_entry(
    category: str, reason: str, *, computed_at: str | None = None
) -> dict[str, Any]:
    return {
        "category": category,
        "available": False,
        "conclusion": None,
        "actionScore": None,
        "missingReason": reason,
        "computedAt": computed_at,
    }


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _resolve_breadth_symbols(
    provider: AnalysisProvider, config: MarketBriefUniverseConfig
) -> tuple[tuple[str, ...] | None, str | None]:
    """The breadth universe: explicit configuration first, the operator's
    watchlist otherwise. Returns ``(symbols, truncation_note)``; ``symbols``
    is ``None`` when neither source could name a universe at all.
    """

    if config.breadth_symbols is not None:
        return config.breadth_symbols, None
    read = getattr(provider, "watchlist_symbols", None)
    if not callable(read):
        return None, None
    try:
        symbols = tuple(read())
    except Exception:  # noqa: BLE001 - the watchlist is an optional default;
        # a failure to read it just means no default universe, not a reason
        # to fail the whole brief.
        return None, None
    normalized = tuple(
        dict.fromkeys(
            symbol.strip().upper() for symbol in symbols if symbol.strip()
        )
    )
    if not normalized:
        return None, None
    if len(normalized) > _BREADTH_MAX_UNIVERSE:
        note = (
            f"自选广度：观察列表共 {len(normalized)} 只，已按上限使用前 "
            f"{_BREADTH_MAX_UNIVERSE} 只计算。"
        )
        return normalized[:_BREADTH_MAX_UNIVERSE], note
    return normalized, None


def _fetch_universe(
    provider: AnalysisProvider, symbols: Sequence[str], interval: str
) -> tuple[dict[str, tuple[OHLCVBar, ...]], tuple[str, ...]]:
    """Sequential, one symbol at a time — connection-reuse restraint over the
    loopback gateway rather than a fetch fanned out per symbol. A symbol the
    gateway could not answer for is named as a gap; it never aborts the rest
    of the universe.
    """

    universe: dict[str, tuple[OHLCVBar, ...]] = {}
    failed: list[str] = []
    for symbol in symbols:
        try:
            bars = provider.bars_for(symbol, interval)
        except Exception:  # noqa: BLE001 - degradation boundary; one bad
            # symbol must not take the whole universe fetch down.
            failed.append(symbol)
            continue
        if bars:
            universe[symbol] = bars
        else:
            failed.append(symbol)
    return universe, tuple(failed)


def _breadth_label(percent_above: float) -> str:
    if percent_above >= 55.0:
        return "多数走强"
    if percent_above <= 45.0:
        return "多数走弱"
    return "涨跌互现"


def _breadth_driver_entry(
    provider: AnalysisProvider,
    config: MarketBriefUniverseConfig,
    as_of: datetime,
) -> tuple[dict[str, Any], tuple[str, ...], bool]:
    symbols, truncation_note = _resolve_breadth_symbols(provider, config)
    if not symbols:
        return _unavailable_entry("breadth", _BREADTH_NOT_CONFIGURED_REASON), (), False

    universe, failed = _fetch_universe(provider, symbols, _BREADTH_INTERVAL)
    notes: tuple[str, ...] = (truncation_note,) if truncation_note else ()
    if not universe:
        return (
            _unavailable_entry(
                "breadth",
                f"自选广度（{len(symbols)} 只）于 {_iso(as_of)} 尝试获取日K线均未"
                "成功，暂无法给出结论。",
                computed_at=_iso(as_of),
            ),
            notes,
            False,
        )
    if failed:
        notes += (
            f"自选广度：{len(failed)} 只未能获取日K线（{'、'.join(failed)}），"
            f"已用其余 {len(universe)} 只计算。",
        )

    result = percent_above_moving_average(universe, as_of, period=_BREADTH_MA_PERIOD)
    if result.quality_status != "live":
        return (
            _unavailable_entry(
                "breadth",
                f"自选广度（{len(symbols)} 只）历史数据不足以计算"
                f"{_BREADTH_MA_PERIOD}日均线（满足条件的仅 {result.eligible_symbols} "
                "只），暂无法给出结论。",
            ),
            notes,
            False,
        )

    assert result.percent_above is not None
    conclusion = (
        f"自选广度（{len(symbols)} 只）· {_breadth_label(result.percent_above)} · "
        f"{result.percent_above:.0f}% 收于{_BREADTH_MA_PERIOD}日均线上方"
    )
    entry = {
        "category": "breadth",
        "available": True,
        "conclusion": conclusion,
        "actionScore": round(_clamp((result.percent_above - 50.0) / 50.0), 6),
        "missingReason": None,
        "computedAt": _iso(as_of),
    }
    # A fully-answered universe earns the whole trading date's cache; any
    # failure along the way earns only the short retry TTL, so a transient
    # gateway restart heals inside the same session (F6).
    healthy = not failed
    return entry, notes, healthy


# ---------------------------------------------------------------------------
# Sector strength: EMA-anchored relative strength of a sector-ETF universe
# against a benchmark (sector-rs-v1), both explicitly configured.
# ---------------------------------------------------------------------------


def _sector_driver_entry(
    provider: AnalysisProvider,
    config: MarketBriefUniverseConfig,
    as_of: datetime,
) -> tuple[dict[str, Any], tuple[str, ...], bool]:
    if not config.sector_symbols or config.sector_benchmark is None:
        return _unavailable_entry("sector", _SECTOR_NOT_CONFIGURED_REASON), (), False

    benchmark_universe, benchmark_failed = _fetch_universe(
        provider, (config.sector_benchmark,), _BREADTH_INTERVAL
    )
    sectors_universe, sector_failed = _fetch_universe(
        provider, config.sector_symbols, _BREADTH_INTERVAL
    )

    if benchmark_failed or not sectors_universe:
        failed = tuple(benchmark_failed) + sector_failed
        return (
            _unavailable_entry(
                "sector",
                f"板块强弱所需品种于 {_iso(as_of)} 尝试获取日K线未能成功（"
                + "、".join(failed)
                + "），暂无法给出结论。",
                computed_at=_iso(as_of),
            ),
            (),
            False,
        )

    notes: tuple[str, ...] = (
        (
            f"板块强弱：{len(sector_failed)} 只 ETF 未能获取日K线（"
            f"{'、'.join(sector_failed)}），已用其余 {len(sectors_universe)} "
            "只计算。",
        )
        if sector_failed
        else ()
    )

    ranking = relative_strength_ranking(
        sectors_universe,
        benchmark_universe[config.sector_benchmark],
        as_of,
        lookbacks=(_SECTOR_LOOKBACK_DAYS,),
    )
    live_results = [item for item in ranking.results if item.quality_status == "live"]
    if not live_results:
        return (
            _unavailable_entry(
                "sector",
                f"板块强弱（{len(sectors_universe)} 只 ETF 对比 "
                f"{config.sector_benchmark}）样本不足，暂无法给出结论。",
            ),
            notes,
            False,
        )

    leader = min(
        live_results, key=lambda item: item.rank if item.rank is not None else 1 << 30
    )
    assert leader.excess_return is not None
    entry = {
        "category": "sector",
        "available": True,
        "conclusion": (
            f"板块强弱（{_SECTOR_LOOKBACK_DAYS}日，对比 {config.sector_benchmark}）· "
            f"领涨 {leader.symbol} 超额收益 {leader.excess_return * 100:+.1f}%"
        ),
        "actionScore": round(_clamp(leader.excess_return), 6),
        "missingReason": None,
        "computedAt": _iso(as_of),
    }
    # Same F6 retention split as breadth: only a fetch nothing failed earns
    # the whole trading date.
    healthy = not sector_failed
    return entry, notes, healthy
