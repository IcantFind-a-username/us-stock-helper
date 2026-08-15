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
from us_stock_helper_analysis_api.market_brief import MarketBriefService
from us_stock_helper_analysis_api.service import AnalysisService
from us_stock_helper_device_auth import DeviceAuthService, DeviceStore

from test_analysis_service import AS_OF, Provider, _all_keys, evidence, service
from test_device_pairing import FAST_SCRYPT, START, call


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


if __name__ == "__main__":
    unittest.main()
