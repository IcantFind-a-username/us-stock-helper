"""GET /market-brief: the Dashboard's real-mode market hero.

Composes only pieces a decision already trusts — EvidencePacketBuilder over
an empty focus, MarketSentiment, request-scoped evidence-gap accounting,
citation freshness — into a versioned envelope with no symbol, no forecast,
no risk plan, no adviser content and no model call. Tests are organised the
way the plan's Step 1 RED list is: the route's shape and its place in the
read-only boundary first, then the honesty of what it composes, then the
throttle guarantee that makes serving it on every dashboard load safe.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from information_layer.feeds import (
    EvidenceCollector,
    EvidenceUnavailable,
    FeedConfig,
    GenericFeedAdapter,
    HttpResponse,
    SourceFailure,
)
from us_stock_helper_analysis_api.device_gate import DeviceGate
from us_stock_helper_analysis_api.evidence_provider import FeedEvidenceProvider
from us_stock_helper_analysis_api.http_app import (
    MARKET_BRIEF_PATH,
    PAIRING_PATH,
    AnalysisApplication,
    AnalysisServerConfig,
    build_server,
)
from us_stock_helper_analysis_api.market_brief import (
    MarketBriefService,
    MarketBriefUniverse,
    MarketBriefUniverseConfig,
)
from us_stock_helper_analysis_api.market_universe_cache import MarketUniverseCache
from us_stock_helper_analysis_api.service import AnalysisService
from us_stock_helper_core import OHLCVBar
from us_stock_helper_core import relative_strength_ranking as core_relative_strength_ranking
from us_stock_helper_device_auth import DeviceAuthService, DeviceStore

from test_analysis_service import AS_OF, Provider, _all_keys, evidence, service
from test_device_pairing import FAST_SCRYPT, START, call
from test_market_universe_cache import FakeMonotonic


_ALL_CATEGORIES = {
    "news-sentiment",
    "breadth",
    "volatility-options",
    "sector",
    "rates-dollar",
    "macro-credit-energy",
    "liquidity-correlation",
    "broad-market-trend",
    "geopolitics",
}


def app(provider: Provider | None = None) -> AnalysisApplication:
    return AnalysisApplication(service(provider or Provider()), clock=lambda: AS_OF)


def brief(provider: Provider | None = None) -> MarketBriefService:
    return MarketBriefService(service(provider or Provider()))


# ---------------------------------------------------------------------------
# The route's place in the read-only boundary: GET-only, path space
# unchanged elsewhere, no order/credential field can ride along.
# ---------------------------------------------------------------------------


class HttpBoundaryTests(unittest.TestCase):
    def test_a_brief_is_served_over_get(self) -> None:
        status, headers, body = app().handle("GET", MARKET_BRIEF_PATH, {})

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "available")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_write_methods_fail_closed(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, _, body = app().handle(method, MARKET_BRIEF_PATH, {})

                self.assertEqual(status, 405)
                self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_paths_outside_the_allowlist_are_still_refused(self) -> None:
        for path in ("/orders", "/decision/../secrets", "/"):
            with self.subTest(path=path):
                status, _, body = app().handle("GET", path, {})

                self.assertEqual(status, 404)
                self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_the_read_application_alone_never_serves_the_pairing_path(self) -> None:
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                status, _, body = app().handle(method, PAIRING_PATH, {})

                self.assertEqual(status, 404)
                self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_the_response_names_no_symbol_forecast_or_adviser_content(self) -> None:
        body = app(Provider(stamped=True)).handle("GET", MARKET_BRIEF_PATH, {})[2]

        forbidden = {
            "symbol",
            "horizon",
            "interval",
            "score",
            "baselineScore",
            "forecast",
            "riskPlan",
            "adviserAdjustment",
            "adviserCouncil",
            "adviserUsage",
            "newsInterpretation",
        }
        self.assertEqual(forbidden & set(body), set())

    def test_the_response_carries_no_order_or_credential_field(self) -> None:
        body = app(Provider(stamped=True)).handle("GET", MARKET_BRIEF_PATH, {})[2]

        forbidden = {
            "orderId",
            "submitOrder",
            "quantity",
            "accountId",
            "brokerToken",
        }
        self.assertEqual(forbidden & _all_keys(body), set())


# ---------------------------------------------------------------------------
# Envelope shape: schemaVersion, cutoff, session, and every designed driver
# category named — sourced or not, but never invented.
# ---------------------------------------------------------------------------


class EnvelopeShapeTests(unittest.TestCase):
    def test_a_normal_read_reports_available_with_no_reason(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        self.assertEqual(result["schemaVersion"], "1")
        self.assertEqual(result["status"], "available")
        self.assertIsNone(result["reason"])
        self.assertEqual(result["decisionCutoff"], "2026-07-25T16:00:00Z")
        self.assertIn(
            result["marketSession"],
            {"premarket", "regular", "afterhours", "closed"},
        )

    def test_every_designed_driver_category_is_named(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        categories = {item["category"] for item in result["driverCoverage"]}
        self.assertEqual(categories, _ALL_CATEGORIES)

    def test_unsourced_categories_carry_available_false_and_a_reason(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        unsourced = [
            item for item in result["driverCoverage"] if item["category"] != "news-sentiment"
        ]
        self.assertEqual(len(unsourced), 8)
        for item in unsourced:
            with self.subTest(category=item["category"]):
                self.assertFalse(item["available"])
                self.assertTrue(item["missingReason"])
                self.assertIsNone(item["conclusion"])
                self.assertIsNone(item["actionScore"])

    def test_the_one_sourced_category_carries_the_measured_sentiment(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        sourced = next(
            item for item in result["driverCoverage"] if item["category"] == "news-sentiment"
        )
        self.assertTrue(sourced["available"])
        self.assertIsNone(sourced["missingReason"])
        self.assertEqual(sourced["conclusion"], result["sentiment"]["conclusion"])
        self.assertEqual(sourced["actionScore"], result["sentiment"]["actionScore"])

    def test_no_driver_category_is_invented_beyond_the_designed_nine(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        self.assertEqual(len(result["driverCoverage"]), 9)

    def test_news_sentiment_entry_is_not_available_when_unmeasured(self) -> None:
        # A packet with nothing readable this round leaves
        # action_score_measured False on the packet's own sentiment. The
        # entry-level driverCoverage disclosure must say so itself — a
        # reader who only looks at driverCoverage (not the top-level
        # sentiment.uncertainty list) must not be told this driver was
        # sourced when nothing was actually measured.
        class NoEvidenceProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return ()

        result = brief(NoEvidenceProvider()).market_brief()

        entry = next(
            item
            for item in result["driverCoverage"]
            if item["category"] == "news-sentiment"
        )
        self.assertFalse(entry["available"])
        self.assertIsNone(entry["conclusion"])
        self.assertIsNone(entry["actionScore"])
        self.assertTrue(entry["missingReason"])


# ---------------------------------------------------------------------------
# Point-in-time exclusions: an event stamped after the cutoff is legitimately
# excluded from the packet, but the exclusion itself must stay visible to the
# reader, exactly like /decision's notes already disclose it.
# ---------------------------------------------------------------------------


class ExcludedFutureEventTests(unittest.TestCase):
    def test_excluded_future_events_are_disclosed_in_notes(self) -> None:
        class FutureEventProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                future = EvidenceEvent.create(
                    event_id="future-1",
                    claim_key="claim-future-1",
                    headline="NVIDIA files late 8-K",
                    summary="Filed after this brief's decision cutoff.",
                    provenance=SourceProvenance(
                        source_id="feed:sec",
                        publisher_id="sec",
                        publisher_name="sec",
                        canonical_url="https://sec.example/future-1",
                        source_type="filing",
                        reliability=0.9,
                    ),
                    event_time=AS_OF - timedelta(minutes=5),
                    published_at=AS_OF - timedelta(minutes=4),
                    first_seen_at=AS_OF - timedelta(minutes=3),
                    available_at=AS_OF + timedelta(minutes=1),
                    retrieved_at=AS_OF + timedelta(minutes=1),
                    claim_status=ClaimStatus.VERIFIED,
                    sentiment=0.5,
                    confidence=0.9,
                    symbol_relevance=(("NVDA", 0.95),),
                )
                return evidence(stamped=True) + (future,)

        result = brief(FutureEventProvider()).market_brief()

        self.assertIn("notes", result)
        self.assertTrue(
            any("future-1" in note for note in result["notes"]),
            result["notes"],
        )
        self.assertTrue(
            any("未纳入本次结论" in note for note in result["notes"]),
            result["notes"],
        )

    def test_no_exclusions_leaves_notes_empty(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        self.assertEqual(result["notes"], [])


# ---------------------------------------------------------------------------
# Sentiment: built from EvidencePacketBuilder over an empty focus, the
# 情绪未测量 marker travels exactly like a decision's.
# ---------------------------------------------------------------------------


class SentimentTests(unittest.TestCase):
    def test_sentiment_is_composed_from_the_empty_focus_evidence_packet(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        sentiment = result["sentiment"]
        self.assertTrue(sentiment["conclusion"])
        self.assertIsInstance(sentiment["actionScore"], float)
        self.assertIsInstance(sentiment["uncertainty"], list)

    def test_zero_evidence_serves_an_unmeasured_sentiment_marker(self) -> None:
        class NoEvidenceProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return ()

        result = brief(NoEvidenceProvider()).market_brief()

        self.assertIn("情绪未测量", result["sentiment"]["uncertainty"])
        self.assertEqual(result["dataHealth"], "insufficient")


# ---------------------------------------------------------------------------
# Citations: https-only, freshness-tagged, exactly as a decision's.
# ---------------------------------------------------------------------------


class CitationTests(unittest.TestCase):
    def test_citations_are_freshness_tagged(self) -> None:
        result = brief(Provider(stamped=True)).market_brief()

        self.assertTrue(result["citations"])
        for citation in result["citations"]:
            self.assertTrue(citation["url"].startswith("https://"))
            self.assertEqual(citation["freshnessSeconds"], 1140)
            self.assertIs(citation["stale"], False)

    def test_a_non_https_citation_is_dropped_rather_than_served(self) -> None:
        class HttpProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return tuple(
                    replace(
                        item,
                        provenance=replace(
                            item.provenance,
                            canonical_url=item.provenance.canonical_url.replace(
                                "https://", "http://"
                            ),
                        ),
                    )
                    for item in evidence(stamped=True)
                )

        result = brief(HttpProvider()).market_brief()

        self.assertEqual(result["citations"], [])


# ---------------------------------------------------------------------------
# Data health: derived from evidence-gap and staleness accounting, worst
# condition wins.
# ---------------------------------------------------------------------------


def _conflicting_evidence() -> tuple[EvidenceEvent, ...]:
    return tuple(
        EvidenceEvent.create(
            event_id=event_id,
            claim_key="nvda-guidance-conflict",
            headline="NVIDIA guidance conflicting reports",
            summary="Outlets disagree on the guidance change.",
            provenance=SourceProvenance(
                source_id=f"feed:{publisher}",
                publisher_id=publisher,
                publisher_name=publisher,
                canonical_url=f"https://{publisher}.example/{event_id}",
                source_type="wire",
                reliability=0.9,
            ),
            event_time=AS_OF - timedelta(minutes=40),
            published_at=AS_OF - timedelta(minutes=30),
            first_seen_at=AS_OF - timedelta(minutes=20),
            available_at=AS_OF - timedelta(minutes=19),
            retrieved_at=AS_OF - timedelta(minutes=18),
            claim_status=ClaimStatus.VERIFIED,
            sentiment=sentiment,
            confidence=0.9,
            symbol_relevance=(("NVDA", 0.95),),
        )
        for event_id, publisher, sentiment in (
            ("c1", "reuters", 0.5),
            ("c2", "bloomberg", -0.5),
        )
    )


class DataHealthTests(unittest.TestCase):
    def test_a_clean_measured_read_is_fresh(self) -> None:
        result = brief(Provider()).market_brief()

        self.assertEqual(result["dataHealth"], "fresh")

    def test_a_stale_citation_marks_the_brief_stale(self) -> None:
        result = brief(Provider(stamped=True, stale=True)).market_brief()

        self.assertEqual(result["dataHealth"], "stale")

    def test_an_unread_source_marks_the_brief_stale(self) -> None:
        class PartiallyReadProvider(Provider):
            def evidence_gaps(self) -> tuple[str, ...]:
                return ("sec-current-8-k（unreachable）",)

        result = brief(PartiallyReadProvider()).market_brief()

        self.assertEqual(result["sourceGaps"], ["sec-current-8-k（unreachable）"])
        self.assertEqual(result["dataHealth"], "stale")

    def test_conflicting_sources_mark_the_brief_conflict(self) -> None:
        class ConflictingProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return _conflicting_evidence()

        result = brief(ConflictingProvider()).market_brief()

        self.assertIn("来源冲突", result["sentiment"]["uncertainty"])
        self.assertEqual(result["dataHealth"], "conflict")

    def test_no_evidence_at_all_is_insufficient_not_fresh(self) -> None:
        class NoEvidenceProvider(Provider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return ()

        result = brief(NoEvidenceProvider()).market_brief()

        self.assertEqual(result["dataHealth"], "insufficient")


# ---------------------------------------------------------------------------
# Fail-closed: nothing readable at all is refused, naming the sources — not
# served as a quiet market.
# ---------------------------------------------------------------------------


class UnavailableTests(unittest.TestCase):
    class BrokenProvider(Provider):
        def read_evidence(self, symbol: str) -> None:  # pragma: no cover - shape
            raise EvidenceUnavailable(
                (
                    SourceFailure("sec-current-8-k", "HTTP 503"),
                    SourceFailure("fred-releases", "unreachable"),
                )
            )

    def test_a_totally_unreadable_evidence_layer_is_reported_unavailable(self) -> None:
        result = brief(self.BrokenProvider()).market_brief()

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("sec-current-8-k", result["reason"])
        self.assertIn("fred-releases", result["reason"])
        self.assertIsNone(result["dataHealth"])
        self.assertIsNone(result["sentiment"])
        self.assertEqual(result["citations"], [])
        self.assertEqual(len(result["driverCoverage"]), 9)
        self.assertTrue(all(not item["available"] for item in result["driverCoverage"]))

    def test_the_unavailable_brief_still_serves_over_get_at_200(self) -> None:
        # Business-level unavailability lives in the JSON body, exactly as a
        # decision's "no completed candles" case does; the HTTP layer itself
        # answers normally.
        status, _, body = AnalysisApplication(
            service(self.BrokenProvider()), clock=lambda: AS_OF
        ).handle("GET", MARKET_BRIEF_PATH, {})

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "unavailable")


# ---------------------------------------------------------------------------
# Throttle: a burst of brief requests inside the coordinator's minimum poll
# interval must perform at most one feed sweep, because a normal dashboard
# load may hit this route on every open.
# ---------------------------------------------------------------------------


class RecordingTransport:
    def __init__(self, *answers: HttpResponse) -> None:
        self.answers = list(answers)
        self.requests: list[object] = []

    def request(self, request: object) -> HttpResponse:
        self.requests.append(request)
        if not self.answers:
            raise AssertionError("no fake feed answer queued")
        return self.answers.pop(0)


def _atom_entry(identity: bytes, title: bytes, published: bytes) -> bytes:
    return (
        b"<entry><id>" + identity + b"</id>"
        b"<title>" + title + b"</title>"
        b"<summary>Details follow.</summary>"
        b'<link rel="alternate" href="https://feeds.example.test/'
        + identity
        + b'"/>'
        b"<published>" + published + b"</published>"
        b"<updated>" + published + b"</updated></entry>"
    )


def _atom_feed(*entries: bytes) -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom">' + b"".join(entries) + b"</feed>"
    )


def _feed_config() -> FeedConfig:
    return FeedConfig(
        adapter_id="example-feed",
        feed_url="https://feeds.example.test/atom.xml",
        allowed_hosts=("feeds.example.test",),
        publisher_id="example-news",
        publisher_name="Example News",
        source_type="official_announcement",
        reliability=0.8,
        user_agent="us-stock-helper/0.1 (contact placeholder)",
        robots_allowed=True,
        minimum_poll_interval_seconds=60.0,
    )


def _feed_response(body: bytes, *, status: int = 200) -> HttpResponse:
    return HttpResponse(status_code=status, headers=(), body=body, retrieved_at=AS_OF)


class EvidenceOnlyProvider:
    """Everything a MarketBriefService needs, nothing a decision's bars do."""

    def __init__(self, feed_provider: FeedEvidenceProvider) -> None:
        self._feed = feed_provider

    def bars_for(self, symbol: str, interval: str) -> tuple[()]:
        return ()

    def read_evidence(self, symbol: str):
        return self._feed.read_evidence(symbol)


class ThrottleTests(unittest.TestCase):
    def test_a_burst_of_briefs_within_the_poll_interval_performs_one_sweep(
        self,
    ) -> None:
        entry = _atom_entry(
            b"item-1",
            b"NVIDIA supplier raises shipment forecast",
            b"2026-07-25T15:55:00Z",
        )
        transport = RecordingTransport(_feed_response(_atom_feed(entry)))
        adapter = GenericFeedAdapter(_feed_config(), transport)
        collector = EvidenceCollector((adapter,), clock=lambda: AS_OF)
        feed_provider = FeedEvidenceProvider(collector)
        market_brief = MarketBriefService(
            AnalysisService(EvidenceOnlyProvider(feed_provider), clock=lambda: AS_OF)
        )

        results = [market_brief.market_brief() for _ in range(5)]

        self.assertEqual(len(transport.requests), 1)
        for result in results:
            self.assertEqual(result["status"], "available")

    def test_repeated_briefs_through_the_http_application_share_the_sweep(
        self,
    ) -> None:
        # The application layer must not stand up a fresh MarketBriefService
        # that rebuilds the provider per request; it has to keep reading
        # through the same AnalysisService, and therefore the same collector.
        entry = _atom_entry(
            b"item-1",
            b"NVIDIA supplier raises shipment forecast",
            b"2026-07-25T15:55:00Z",
        )
        transport = RecordingTransport(_feed_response(_atom_feed(entry)))
        adapter = GenericFeedAdapter(_feed_config(), transport)
        collector = EvidenceCollector((adapter,), clock=lambda: AS_OF)
        feed_provider = FeedEvidenceProvider(collector)
        application = AnalysisApplication(
            AnalysisService(EvidenceOnlyProvider(feed_provider), clock=lambda: AS_OF),
            clock=lambda: AS_OF,
        )

        for _ in range(5):
            status, _, body = application.handle("GET", MARKET_BRIEF_PATH, {})
            self.assertEqual(status, 200)
            self.assertEqual(body["status"], "available")

        self.assertEqual(len(transport.requests), 1)


# ---------------------------------------------------------------------------
# Device-token gate ordering: unchanged by the new route.
# ---------------------------------------------------------------------------


class DeviceGateOrderingTests(unittest.TestCase):
    def test_the_brief_demands_the_same_device_token_a_decision_does(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="market-brief-gate-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        database = directory / "device-auth.sqlite3"
        auth = DeviceAuthService(
            store=DeviceStore(database), clock=lambda: START, scrypt=FAST_SCRYPT
        )
        code = auth.issue_pairing_code(label="test iPhone").code
        gate = DeviceGate(auth)
        config = AnalysisServerConfig(
            host="127.0.0.1",
            port=0,
            allow_lan=False,
            trust_proxy=False,
            device_database=str(database),
            allowed_client_networks=("127.0.0.0/8", "::1/128"),
        )
        server = build_server(service(Provider(stamped=True)), config, gate=gate)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://{server.server_address[0]}:{server.server_address[1]}"

            self.assertEqual(call(f"{base}{MARKET_BRIEF_PATH}")[0], 401)

            status, _, body = call(
                f"{base}{PAIRING_PATH}",
                method="POST",
                body=json.dumps({"pairingCode": code}).encode("utf-8"),
            )
            self.assertEqual(status, 200)
            token = body["deviceToken"]

            status, _, body = call(f"{base}{MARKET_BRIEF_PATH}", token=token)
            self.assertEqual(status, 200)
            self.assertEqual(body["status"], "available")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Breadth / sector-RS: driverCoverage['breadth'] and ['sector'] sourced from
# us_stock_helper_core's breadth-v1 and sector-rs-v1 engines over a
# configurable daily-bar universe read from the market gateway.
# ---------------------------------------------------------------------------


def _daily_bars(
    symbol: str, closes: list[float], *, end: datetime
) -> tuple[OHLCVBar, ...]:
    bars = []
    for index, price in enumerate(closes):
        closed_at = end - timedelta(days=len(closes) - 1 - index)
        bars.append(
            OHLCVBar(
                symbol=symbol,
                interval="day",
                opened_at=closed_at - timedelta(days=1),
                closed_at=closed_at,
                available_at=closed_at,
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=1_000_000.0,
            )
        )
    return tuple(bars)


def _breadth_bars(symbol: str, *, last_close: float) -> tuple[OHLCVBar, ...]:
    """49 flat bars at 100 then one final bar — a hand-checkable MA50 read.

    MA50 = (49 * 100 + last_close) / 50, so a last_close of 110 sits above it
    and one of 90 sits below it; nothing here depends on the breadth engine's
    own arithmetic being trusted blind, only on a single division anyone can
    redo by hand.
    """

    return _daily_bars(symbol, [100.0] * 49 + [last_close], end=AS_OF)


def _sector_bars(symbol: str, *, last_close: float) -> tuple[OHLCVBar, ...]:
    """21 flat bars at 100 then one final bar — the shortest EMA(21) warm-up."""

    return _daily_bars(symbol, [100.0] * 21 + [last_close], end=AS_OF)


class UniverseProvider(Provider):
    """A `Provider` that also answers `bars_for` for an arbitrary universe
    and optionally a watchlist — the two things `MarketBriefService` reads
    beyond the evidence path the base `Provider` already covers.

    `bars_for` never falls back to the base class's fixed NVDA rows: a symbol
    outside the configured `universe` answers with an honest empty series (or
    raises, for `raises`), exactly the two "unfetchable" shapes the gateway
    boundary itself can produce.
    """

    def __init__(
        self,
        universe: dict[str, tuple[OHLCVBar, ...]] | None = None,
        *,
        watchlist: tuple[str, ...] | None = None,
        watchlist_error: bool = False,
        raises: tuple[str, ...] = (),
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._universe = universe or {}
        self._watchlist = watchlist
        self._watchlist_error = watchlist_error
        self._raises = set(raises)
        self.universe_requests: list[str] = []

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self.universe_requests.append(symbol)
        if symbol in self._raises:
            raise RuntimeError(f"{symbol} gateway failure")
        return self._universe.get(symbol, ())

    def watchlist_symbols(self) -> tuple[str, ...]:
        if self._watchlist_error:
            raise RuntimeError("watchlist unreachable")
        if self._watchlist is None:
            raise AttributeError("watchlist not configured")
        return self._watchlist

    def recover(self) -> None:
        """Simulates a gateway restart: every symbol that used to raise now
        answers normally, without touching anything else about the fixture."""

        self._raises.clear()


def _brief_with_universe(
    provider: UniverseProvider, config: MarketBriefUniverseConfig
) -> dict:
    return MarketBriefService(
        service(provider), MarketBriefUniverse(config=config)
    ).market_brief()


def _driver(result: dict, category: str) -> dict:
    return next(item for item in result["driverCoverage"] if item["category"] == category)


class BreadthDriverTests(unittest.TestCase):
    def test_an_explicit_universe_serves_an_exact_hand_checked_reading(self) -> None:
        # 3 of 5 above their own MA50 -> 60%, self-checkable by hand: MA50 of
        # [100]*49 + [110] is 100.2 (< 110, "above"); of [100]*49 + [90] is
        # 99.8 (> 90, "below").
        universe = {
            "AAA": _breadth_bars("AAA", last_close=110.0),
            "BBB": _breadth_bars("BBB", last_close=110.0),
            "CCC": _breadth_bars("CCC", last_close=110.0),
            "DDD": _breadth_bars("DDD", last_close=90.0),
            "EEE": _breadth_bars("EEE", last_close=90.0),
        }
        config = MarketBriefUniverseConfig(
            breadth_symbols=("AAA", "BBB", "CCC", "DDD", "EEE")
        )
        provider = UniverseProvider(universe, stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "breadth")
        self.assertTrue(entry["available"])
        self.assertIsNone(entry["missingReason"])
        self.assertIn("自选广度（5 只）", entry["conclusion"])
        self.assertIn("60%", entry["conclusion"])
        self.assertAlmostEqual(entry["actionScore"], 0.2, places=6)

    def test_the_scope_label_is_pinned_to_watchlist_wording_never_market_wide(
        self,
    ) -> None:
        # The plan's own red line: watchlist/自选-scoped breadth may never be
        # labelled 市场广度 as if it covered the whole market.
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        result = _brief_with_universe(UniverseProvider(universe, stamped=True), config)

        entry = _driver(result, "breadth")
        self.assertTrue(entry["conclusion"].startswith("自选广度（"))
        self.assertNotIn("市场广度", entry["conclusion"])

    def test_no_configuration_and_no_watchlist_stays_unavailable(self) -> None:
        result = _brief_with_universe(
            UniverseProvider(stamped=True), MarketBriefUniverseConfig()
        )

        entry = _driver(result, "breadth")
        self.assertFalse(entry["available"])
        self.assertIsNone(entry["conclusion"])
        self.assertIsNone(entry["actionScore"])
        self.assertIn("自选广度尚未配置", entry["missingReason"])

    def test_the_watchlist_is_the_default_universe_when_nothing_is_configured(
        self,
    ) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        provider = UniverseProvider(universe, watchlist=tuple(universe), stamped=True)

        result = _brief_with_universe(provider, MarketBriefUniverseConfig())

        entry = _driver(result, "breadth")
        self.assertTrue(entry["available"])
        self.assertIn("自选广度（5 只）", entry["conclusion"])

    def test_a_watchlist_the_gateway_cannot_serve_leaves_breadth_unavailable(
        self,
    ) -> None:
        result = _brief_with_universe(
            UniverseProvider(watchlist_error=True, stamped=True),
            MarketBriefUniverseConfig(),
        )

        entry = _driver(result, "breadth")
        self.assertFalse(entry["available"])
        self.assertTrue(entry["missingReason"])

    def test_a_wholly_unfetchable_universe_is_typed_unavailable(self) -> None:
        config = MarketBriefUniverseConfig(
            breadth_symbols=("AAA", "BBB", "CCC", "DDD", "EEE")
        )
        provider = UniverseProvider(raises=("AAA", "BBB", "CCC", "DDD", "EEE"), stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "breadth")
        self.assertFalse(entry["available"])
        self.assertIsNone(entry["conclusion"])
        self.assertIsNone(entry["actionScore"])
        self.assertTrue(entry["missingReason"])

    def test_a_partially_fetched_universe_is_served_with_an_honest_note(
        self,
    ) -> None:
        # 6 configured, 1 unfetchable, 5 remain -- still enough to meet
        # breadth-v1's own 5-symbol minimum, so the reading is served with a
        # note naming exactly what was dropped rather than silently smaller.
        universe = {
            "AAA": _breadth_bars("AAA", last_close=110.0),
            "BBB": _breadth_bars("BBB", last_close=110.0),
            "CCC": _breadth_bars("CCC", last_close=110.0),
            "DDD": _breadth_bars("DDD", last_close=90.0),
            "EEE": _breadth_bars("EEE", last_close=90.0),
        }
        config = MarketBriefUniverseConfig(
            breadth_symbols=("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")
        )
        provider = UniverseProvider(universe, raises=("FFF",), stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "breadth")
        self.assertTrue(entry["available"])
        # The percentage was computed over the 5 symbols actually fetched,
        # not the 6 configured -- the conclusion must say so itself (F8),
        # rather than only the separate note disclosing the drop.
        self.assertIn("自选广度（有效 5/6 只）", entry["conclusion"])
        self.assertNotIn("自选广度（6 只）", entry["conclusion"])
        self.assertTrue(
            any("FFF" in note and "自选广度" in note for note in result["notes"]),
            result["notes"],
        )

    def test_the_conclusion_states_the_full_sample_plainly_when_nothing_failed(
        self,
    ) -> None:
        # The honest-sample wording only earns its keep when it says
        # something the configured count alone did not: a fully-answered
        # universe stays the plain "N 只" form, never a redundant "有效 N/N".
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        result = _brief_with_universe(UniverseProvider(universe, stamped=True), config)

        entry = _driver(result, "breadth")
        self.assertIn("自选广度（5 只）", entry["conclusion"])
        self.assertNotIn("有效", entry["conclusion"])

    def test_a_large_partial_sample_carries_its_effective_count_honestly(
        self,
    ) -> None:
        # The reviewer's own example: a 60-symbol watchlist with 3 gateway
        # failures must read 自选广度（有效 57/60 只）, not 自选广度（60 只）.
        configured = tuple(f"SYM{i}" for i in range(60))
        universe = {
            symbol: _breadth_bars(symbol, last_close=110.0) for symbol in configured[:57]
        }
        config = MarketBriefUniverseConfig(breadth_symbols=configured)
        provider = UniverseProvider(universe, raises=configured[57:], stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "breadth")
        self.assertTrue(entry["available"])
        self.assertIn("自选广度（有效 57/60 只）", entry["conclusion"])

    def test_computed_at_is_the_decision_cutoff_on_a_fresh_compute(self) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        result = _brief_with_universe(UniverseProvider(universe, stamped=True), config)

        entry = _driver(result, "breadth")
        self.assertEqual(entry["computedAt"], result["decisionCutoff"])


class SectorDriverTests(unittest.TestCase):
    def test_a_configured_universe_ranks_the_leading_sector(self) -> None:
        benchmark = _sector_bars("SPY", last_close=100.0)
        xlk = _sector_bars("XLK", last_close=110.0)
        xle = _sector_bars("XLE", last_close=95.0)
        sectors = {"SPY": benchmark, "XLK": xlk, "XLE": xle}
        config = MarketBriefUniverseConfig(
            sector_symbols=("XLK", "XLE"), sector_benchmark="SPY"
        )
        provider = UniverseProvider(sectors, stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "sector")
        self.assertTrue(entry["available"])
        self.assertIsNone(entry["missingReason"])
        self.assertIn("XLK", entry["conclusion"])
        self.assertIn("SPY", entry["conclusion"])

        # Cross-checked directly against the same core engine this service
        # wires through, rather than a hand-derived EMA value.
        expected = core_relative_strength_ranking(
            {"XLK": xlk, "XLE": xle}, benchmark, AS_OF, lookbacks=(21,)
        )
        leader = min(
            (item for item in expected.results if item.quality_status == "live"),
            key=lambda item: item.rank,
        )
        self.assertEqual(leader.symbol, "XLK")
        self.assertAlmostEqual(entry["actionScore"], leader.excess_return, places=6)

    def test_not_configured_stays_unavailable(self) -> None:
        result = _brief_with_universe(
            UniverseProvider(stamped=True), MarketBriefUniverseConfig()
        )

        entry = _driver(result, "sector")
        self.assertFalse(entry["available"])
        self.assertIn("尚未配置", entry["missingReason"])

    def test_an_unfetchable_benchmark_is_typed_unavailable_naming_it(self) -> None:
        sectors = {
            "XLK": _sector_bars("XLK", last_close=110.0),
            "XLE": _sector_bars("XLE", last_close=95.0),
        }
        config = MarketBriefUniverseConfig(
            sector_symbols=("XLK", "XLE"), sector_benchmark="SPY"
        )
        provider = UniverseProvider(sectors, raises=("SPY",), stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "sector")
        self.assertFalse(entry["available"])
        self.assertIsNone(entry["conclusion"])
        self.assertIn("SPY", entry["missingReason"])

    def test_a_partially_fetched_sector_universe_still_ranks_with_a_note(
        self,
    ) -> None:
        # 3 ETFs configured, 1 unfetchable, 2 remain -- still meets
        # sector-rs-v1's own 2-symbol minimum for a ranking.
        benchmark = _sector_bars("SPY", last_close=100.0)
        sectors = {
            "SPY": benchmark,
            "XLK": _sector_bars("XLK", last_close=110.0),
            "XLE": _sector_bars("XLE", last_close=95.0),
        }
        config = MarketBriefUniverseConfig(
            sector_symbols=("XLK", "XLE", "XLF"), sector_benchmark="SPY"
        )
        provider = UniverseProvider(sectors, raises=("XLF",), stamped=True)

        result = _brief_with_universe(provider, config)

        entry = _driver(result, "sector")
        self.assertTrue(entry["available"])
        self.assertTrue(
            any("XLF" in note and "板块强弱" in note for note in result["notes"]),
            result["notes"],
        )


class UniverseConfigEnvironmentTests(unittest.TestCase):
    def test_nothing_set_leaves_every_universe_unconfigured(self) -> None:
        config = MarketBriefUniverseConfig.from_environment({})

        self.assertIsNone(config.breadth_symbols)
        self.assertEqual(config.sector_symbols, ())
        self.assertIsNone(config.sector_benchmark)

    def test_a_comma_separated_breadth_universe_is_parsed_and_normalized(
        self,
    ) -> None:
        config = MarketBriefUniverseConfig.from_environment(
            {"ANALYSIS_API_BREADTH_UNIVERSE": " nvda, tsla,nvda ,aapl "}
        )

        self.assertEqual(config.breadth_symbols, ("NVDA", "TSLA", "AAPL"))

    def test_a_blank_breadth_universe_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_BREADTH_UNIVERSE": "  , , "}
            )

    def test_an_oversized_breadth_universe_is_refused(self) -> None:
        many = ",".join(f"SYM{i}" for i in range(61))
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_BREADTH_UNIVERSE": many}
            )

    def test_sector_symbols_and_benchmark_must_both_be_set_or_neither(self) -> None:
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_SECTOR_RS_SYMBOLS": "XLK,XLE"}
            )
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_SECTOR_RS_BENCHMARK": "SPY"}
            )

    def test_a_matched_sector_configuration_is_accepted(self) -> None:
        config = MarketBriefUniverseConfig.from_environment(
            {
                "ANALYSIS_API_SECTOR_RS_SYMBOLS": "xlk, xle",
                "ANALYSIS_API_SECTOR_RS_BENCHMARK": "spy",
            }
        )

        self.assertEqual(config.sector_symbols, ("XLK", "XLE"))
        self.assertEqual(config.sector_benchmark, "SPY")

    def test_the_fetch_deadline_defaults_when_unset(self) -> None:
        config = MarketBriefUniverseConfig.from_environment({})

        self.assertGreater(config.fetch_deadline_seconds, 0)

    def test_the_fetch_deadline_is_parsed_from_the_environment(self) -> None:
        config = MarketBriefUniverseConfig.from_environment(
            {"ANALYSIS_API_MARKET_BRIEF_FETCH_DEADLINE_SECONDS": "5"}
        )

        self.assertEqual(config.fetch_deadline_seconds, 5.0)

    def test_a_non_numeric_fetch_deadline_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_MARKET_BRIEF_FETCH_DEADLINE_SECONDS": "soon"}
            )

    def test_an_out_of_range_fetch_deadline_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_MARKET_BRIEF_FETCH_DEADLINE_SECONDS": "0"}
            )
        with self.assertRaises(ValueError):
            MarketBriefUniverseConfig.from_environment(
                {"ANALYSIS_API_MARKET_BRIEF_FETCH_DEADLINE_SECONDS": "301"}
            )


class UniverseCacheTests(unittest.TestCase):
    def test_two_briefs_the_same_trading_date_perform_one_universe_fetch(
        self,
    ) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        provider = UniverseProvider(universe, stamped=True)
        shared_service = service(provider)
        shared_universe = MarketBriefUniverse(config=config)

        first = MarketBriefService(shared_service, shared_universe).market_brief()
        second = MarketBriefService(shared_service, shared_universe).market_brief()

        self.assertEqual(len(provider.universe_requests), 5)
        self.assertEqual(
            _driver(first, "breadth")["computedAt"],
            _driver(second, "breadth")["computedAt"],
        )

    def test_a_cache_hit_still_carries_its_original_computed_at(self) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        provider = UniverseProvider(universe, stamped=True)
        shared_service = service(provider)
        shared_universe = MarketBriefUniverse(config=config)

        first = MarketBriefService(shared_service, shared_universe).market_brief()
        second = MarketBriefService(shared_service, shared_universe).market_brief()

        # Both requests share one clock (AS_OF), so this also proves the
        # second call never recomputed: a recompute would still equal the
        # first's computedAt only by coincidence of a frozen clock, but the
        # fetch-count assertion above is what actually pins "no refetch".
        self.assertEqual(_driver(first, "breadth")["computedAt"], first["decisionCutoff"])
        self.assertEqual(_driver(second, "breadth")["computedAt"], first["decisionCutoff"])


# ---------------------------------------------------------------------------
# Retry TTL: a failure or a partial universe must heal well inside a single
# trading session, not freeze until the 16:00 ET rollover -- the reviewer's
# own outage-then-recovery scenario.
# ---------------------------------------------------------------------------


class RetryAfterFailureTests(unittest.TestCase):
    def test_a_wholly_failed_universe_retries_live_once_the_ttl_elapses(
        self,
    ) -> None:
        # 3 of 5 above their own MA50 once the gateway recovers -- the same
        # hand-checkable split BreadthDriverTests already relies on.
        universe = {
            "AAA": _breadth_bars("AAA", last_close=110.0),
            "BBB": _breadth_bars("BBB", last_close=110.0),
            "CCC": _breadth_bars("CCC", last_close=110.0),
            "DDD": _breadth_bars("DDD", last_close=90.0),
            "EEE": _breadth_bars("EEE", last_close=90.0),
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        provider = UniverseProvider(universe, raises=tuple(universe), stamped=True)
        clock = FakeMonotonic()
        shared_universe = MarketBriefUniverse(
            config=config,
            cache=MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock),
        )
        shared_service = service(provider)

        # First request during the outage: every symbol fails, served
        # honestly unavailable.
        first = MarketBriefService(shared_service, shared_universe).market_brief()
        first_entry = _driver(first, "breadth")
        self.assertFalse(first_entry["available"])
        self.assertEqual(len(provider.universe_requests), 5)

        # A second request still inside the retry window is replayed from
        # cache, not refetched -- an outage must not be hammered every read.
        second = MarketBriefService(shared_service, shared_universe).market_brief()
        self.assertFalse(_driver(second, "breadth")["available"])
        self.assertEqual(len(provider.universe_requests), 5)

        # The gateway recovers, and the retry window elapses.
        provider.recover()
        clock.advance(61.0)

        # A request after the retry TTL performs a fresh fetch and serves
        # live values -- this must not wait for the 16:00 ET rollover.
        third = MarketBriefService(shared_service, shared_universe).market_brief()
        third_entry = _driver(third, "breadth")
        self.assertTrue(third_entry["available"])
        self.assertIn("60%", third_entry["conclusion"])
        self.assertEqual(len(provider.universe_requests), 10)

    def test_a_healthy_universe_still_survives_the_whole_trading_date(self) -> None:
        # Regression guard alongside the retry-TTL fix above: a result every
        # symbol answered must still be exempt from the short retry window.
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        provider = UniverseProvider(universe, stamped=True)
        clock = FakeMonotonic()
        shared_universe = MarketBriefUniverse(
            config=config,
            cache=MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock),
        )
        shared_service = service(provider)

        first = MarketBriefService(shared_service, shared_universe).market_brief()
        clock.advance(10_000.0)  # long past the short retry window
        second = MarketBriefService(shared_service, shared_universe).market_brief()

        self.assertTrue(_driver(first, "breadth")["available"])
        self.assertEqual(
            _driver(first, "breadth")["computedAt"], _driver(second, "breadth")["computedAt"]
        )
        self.assertEqual(len(provider.universe_requests), 5)

    def test_a_replayed_failure_never_claims_this_round_and_states_when_computed(
        self,
    ) -> None:
        # F6's wording half: a cached failure served on a later, unrelated
        # request must not say "本次" ("this round") as if the fetch just
        # happened -- it must instead state when the attempt was actually
        # made, via computedAt and the message itself.
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        provider = UniverseProvider(raises=tuple(universe), stamped=True)
        shared_universe = MarketBriefUniverse(
            config=config, cache=MarketUniverseCache(retry_after_seconds=60.0)
        )
        shared_service = service(provider)

        first = MarketBriefService(shared_service, shared_universe).market_brief()
        replayed = MarketBriefService(shared_service, shared_universe).market_brief()

        for result in (first, replayed):
            entry = _driver(result, "breadth")
            self.assertNotIn("本次", entry["missingReason"])
            self.assertEqual(entry["computedAt"], first["decisionCutoff"])


# ---------------------------------------------------------------------------
# Single-flight: a concurrent miss on the same cache slot must never queue a
# follower behind the leader's own network I/O (F7).
# ---------------------------------------------------------------------------


class BlockingUniverseProvider(UniverseProvider):
    """A `UniverseProvider` whose `bars_for` blocks on `released` the first
    time it is asked for `blocked_symbol`, signalling `entered` first --
    house-style hooks/events, never a sleep, for pinning a concurrent race."""

    def __init__(
        self,
        universe: dict[str, tuple[OHLCVBar, ...]],
        *,
        blocked_symbol: str,
        entered: threading.Event,
        released: threading.Event,
        **kwargs: object,
    ) -> None:
        super().__init__(universe, **kwargs)
        self._blocked_symbol = blocked_symbol
        self._entered = entered
        self._released = released

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        if symbol == self._blocked_symbol:
            self._entered.set()
            if not self._released.wait(timeout=5):
                raise AssertionError("leader was never released -- test bug")
        return super().bars_for(symbol, interval)


class SingleFlightTests(unittest.TestCase):
    def test_a_follower_returns_promptly_while_the_leader_computes(self) -> None:
        universe = {
            "AAA": _breadth_bars("AAA", last_close=110.0),
            "BBB": _breadth_bars("BBB", last_close=110.0),
            "CCC": _breadth_bars("CCC", last_close=110.0),
            "DDD": _breadth_bars("DDD", last_close=90.0),
            "EEE": _breadth_bars("EEE", last_close=90.0),
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))
        entered = threading.Event()
        released = threading.Event()
        provider = BlockingUniverseProvider(
            universe,
            blocked_symbol="AAA",
            entered=entered,
            released=released,
            stamped=True,
        )
        shared_service = service(provider)
        shared_universe = MarketBriefUniverse(config=config)

        leader_result: dict[str, dict] = {}
        follower_result: dict[str, dict] = {}

        def run_leader() -> None:
            leader_result["value"] = MarketBriefService(
                shared_service, shared_universe
            ).market_brief()

        leader_thread = threading.Thread(target=run_leader)
        leader_thread.start()
        self.assertTrue(entered.wait(timeout=5), "leader never reached the fetch")

        # The follower must answer without waiting for the leader's own
        # blocked fetch to unblock -- the whole point of not holding the
        # cache lock across compute().
        follower_result["value"] = MarketBriefService(
            shared_service, shared_universe
        ).market_brief()

        follower_entry = _driver(follower_result["value"], "breadth")
        self.assertFalse(follower_entry["available"])
        self.assertIn("计算中", follower_entry["missingReason"])

        released.set()
        leader_thread.join(timeout=5)
        self.assertFalse(leader_thread.is_alive(), "leader thread never finished")

        leader_entry = _driver(leader_result["value"], "breadth")
        self.assertTrue(leader_entry["available"])
        self.assertIn("60%", leader_entry["conclusion"])

        # Single-flight held: the follower never triggered a fetch of its
        # own -- only the leader's 5 symbol reads were ever made.
        self.assertEqual(len(provider.universe_requests), 5)


# ---------------------------------------------------------------------------
# Fetch deadline: bounds one universe fetch's total wall time so a leader's
# worst-case hold on this route stays far under 91 sequential timeouts (F7).
# ---------------------------------------------------------------------------


class SlowUniverseProvider(UniverseProvider):
    """A `UniverseProvider` whose `bars_for` advances a shared fake monotonic
    clock by a fixed amount per call, so a fetch-deadline bound can be pinned
    exactly -- no real sleep, no timing flakiness."""

    def __init__(
        self,
        universe: dict[str, tuple[OHLCVBar, ...]],
        *,
        clock: FakeMonotonic,
        seconds_per_call: float,
        **kwargs: object,
    ) -> None:
        super().__init__(universe, **kwargs)
        self._clock = clock
        self._seconds_per_call = seconds_per_call

    def bars_for(self, symbol: str, interval: str) -> tuple[OHLCVBar, ...]:
        self._clock.advance(self._seconds_per_call)
        return super().bars_for(symbol, interval)


class UniverseFetchDeadlineTests(unittest.TestCase):
    def test_a_universe_fetch_stops_attempting_symbols_once_the_deadline_elapses(
        self,
    ) -> None:
        # 7 symbols, each attempted fetch "takes" 2s, deadline 9s: symbols
        # 1-5 are attempted (elapsed checked before each: 0, 2, 4, 6, 8, all
        # < 9), leaving elapsed at 10; symbols 6-7 are then skipped before
        # ever calling bars_for, since 10 >= 9. 5 answers still meets
        # breadth-v1's own 5-symbol minimum for a live reading.
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG")
        }
        config = MarketBriefUniverseConfig(
            breadth_symbols=tuple(universe), fetch_deadline_seconds=9.0
        )
        clock = FakeMonotonic()
        provider = SlowUniverseProvider(
            universe, clock=clock, seconds_per_call=2.0, stamped=True
        )
        shared_universe = MarketBriefUniverse(
            config=config, cache=MarketUniverseCache(monotonic=clock)
        )

        result = MarketBriefService(service(provider), shared_universe).market_brief()

        entry = _driver(result, "breadth")
        self.assertTrue(entry["available"])
        self.assertEqual(len(provider.universe_requests), 5)
        self.assertTrue(
            any(
                "FFF" in note and "GGG" in note and "自选广度" in note
                for note in result["notes"]
            ),
            result["notes"],
        )


class DataHealthInterplayTests(unittest.TestCase):
    def test_breadth_and_sector_availability_never_soften_insufficient_data_health(
        self,
    ) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))

        class NoEvidenceProvider(UniverseProvider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return ()

        result = _brief_with_universe(NoEvidenceProvider(universe), config)

        self.assertEqual(result["dataHealth"], "insufficient")
        self.assertTrue(_driver(result, "breadth")["available"])

    def test_breadth_and_sector_availability_never_soften_conflict_data_health(
        self,
    ) -> None:
        universe = {
            name: _breadth_bars(name, last_close=110.0)
            for name in ("AAA", "BBB", "CCC", "DDD", "EEE")
        }
        config = MarketBriefUniverseConfig(breadth_symbols=tuple(universe))

        class ConflictingProvider(UniverseProvider):
            def evidence_for(self, symbol: str) -> tuple[EvidenceEvent, ...]:
                return _conflicting_evidence()

        result = _brief_with_universe(ConflictingProvider(universe), config)

        self.assertEqual(result["dataHealth"], "conflict")
        self.assertTrue(_driver(result, "breadth")["available"])


if __name__ == "__main__":
    unittest.main()
