from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from information_layer import ClaimStatus
from information_layer.cik_registry import CikTickerRegistry
from information_layer.feeds import (
    CacheValidators,
    FeedAccessError,
    FeedConfig,
    GenericFeedAdapter,
    HttpRequest,
    HttpResponse,
    KeywordMapping,
    PollingCoordinator,
    ResponseTooLargeError,
    SecCurrentFilingsAdapter,
    UrllibHttpsTransport,
    build_sec_current_filings_adapters,
)


UTC = timezone.utc
NOW = datetime(2026, 7, 25, 14, 0, tzinfo=UTC)


ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example feed</title>
  <entry>
    <id>tag:example.test,2026:item-1</id>
    <title>NVIDIA supplier raises shipment forecast</title>
    <summary type="html">&lt;p&gt;NVDA demand improved. Full article text must not be stored. More details follow here.&lt;/p&gt;</summary>
    <link rel="alternate" href="https://news.example.test/item-1"/>
    <published>2026-07-25T13:55:00Z</published>
    <updated>2026-07-25T13:56:00Z</updated>
  </entry>
</feed>
"""

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example RSS</title>
    <item>
      <guid>rss-item-1</guid>
      <title>Microsoft cloud demand accelerates</title>
      <description><![CDATA[<p>MSFT Azure demand improved. This is deliberately longer than the configured summary limit.</p>]]></description>
      <link>https://news.example.test/rss-item-1</link>
      <pubDate>Sat, 25 Jul 2026 13:50:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

SEC_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000081</id>
    <title>8-K - Apple Inc. (0000320193)</title>
    <summary>Filed 8-K current report.</summary>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/filing-index.htm"/>
    <updated>2026-07-25T13:58:00Z</updated>
  </entry>
</feed>
"""


class FakeTransport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = list(responses)
        self.requests: list[HttpRequest] = []

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("no fake response queued")
        return self.responses.pop(0)


def response(
    body: bytes = ATOM,
    *,
    status: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
    retrieved_at: datetime = NOW,
) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        headers=headers,
        body=body,
        retrieved_at=retrieved_at,
    )


def config(**overrides: object) -> FeedConfig:
    values: dict[str, object] = {
        "adapter_id": "example-atom",
        "feed_url": "https://feeds.example.test/atom.xml",
        "allowed_hosts": ("feeds.example.test",),
        "publisher_id": "example-news",
        "publisher_name": "Example News",
        "source_type": "news",
        "reliability": 0.75,
        "user_agent": "USStockHelper/0.1 contact@example.test",
        "timeout_seconds": 7.0,
        "max_response_bytes": 2048,
        "summary_max_chars": 64,
        "robots_allowed": True,
        "symbol_mappings": (
            KeywordMapping("NVDA", ("nvidia", "nvda"), 0.95),
        ),
        "entity_mappings": (
            KeywordMapping("NVIDIA", ("nvidia",), 0.9),
        ),
        "macro_mappings": (
            KeywordMapping("SEMICONDUCTOR_CYCLE", ("shipment",), 0.8),
        ),
        "geopolitical_mappings": (
            KeywordMapping("US_CHINA_TECH", ("supplier",), 0.8),
        ),
    }
    values.update(overrides)
    return FeedConfig(**values)  # type: ignore[arg-type]


class SecurityAndHttpMetadataTests(unittest.TestCase):
    def test_https_host_allowlist_and_public_access_are_mandatory(self) -> None:
        with self.assertRaises(FeedAccessError):
            config(feed_url="http://feeds.example.test/feed")
        with self.assertRaises(FeedAccessError):
            config(feed_url="https://evil.example/feed")
        with self.assertRaises(FeedAccessError):
            config(robots_allowed=False)
        with self.assertRaises(FeedAccessError):
            config(requires_auth=True)
        with self.assertRaises(FeedAccessError):
            config(paywalled=True)

    def test_request_has_limits_user_agent_and_conditional_headers(self) -> None:
        transport = FakeTransport(response(headers=(("ETag", '"next"'),)))
        adapter = GenericFeedAdapter(config(), transport)

        batch = adapter.poll(
            since=NOW - timedelta(hours=1),
            until=NOW,
            validators=CacheValidators(
                etag='"prior"',
                last_modified="Sat, 25 Jul 2026 13:00:00 GMT",
            ),
        )

        request = transport.requests[0]
        self.assertEqual(request.timeout_seconds, 7.0)
        self.assertEqual(request.max_response_bytes, 2048)
        self.assertEqual(request.header("User-Agent"), "USStockHelper/0.1 contact@example.test")
        self.assertEqual(request.header("If-None-Match"), '"prior"')
        self.assertEqual(
            request.header("If-Modified-Since"),
            "Sat, 25 Jul 2026 13:00:00 GMT",
        )
        self.assertEqual(batch.metadata.etag, '"next"')

    def test_retry_after_and_exponential_backoff_are_reported_not_slept(self) -> None:
        transport = FakeTransport(
            response(
                b"",
                status=429,
                headers=(("Retry-After", "120"),),
            )
        )
        adapter = GenericFeedAdapter(
            config(base_backoff_seconds=10.0, max_backoff_seconds=300.0),
            transport,
        )

        batch = adapter.poll(
            since=NOW - timedelta(hours=1),
            until=NOW,
            consecutive_failures=2,
        )

        self.assertEqual(batch.events, ())
        self.assertEqual(batch.metadata.retry_after_seconds, 120.0)
        self.assertEqual(batch.metadata.recommended_delay_seconds, 120.0)

    def test_successful_poll_reports_configured_minimum_interval(self) -> None:
        adapter = GenericFeedAdapter(
            config(minimum_poll_interval_seconds=45.0),
            FakeTransport(response()),
        )
        batch = adapter.poll(since=NOW - timedelta(hours=1), until=NOW)
        self.assertEqual(batch.metadata.recommended_delay_seconds, 45.0)

    def test_response_limit_is_enforced_even_with_injected_transport(self) -> None:
        transport = FakeTransport(response(b"x" * 65))
        adapter = GenericFeedAdapter(config(max_response_bytes=64), transport)
        with self.assertRaises(ResponseTooLargeError):
            adapter.poll(since=NOW - timedelta(hours=1), until=NOW)

    def test_stdlib_transport_rejects_insecure_or_credentialed_request_before_io(self) -> None:
        transport = UrllibHttpsTransport()
        with self.assertRaises(FeedAccessError):
            transport.request(
                HttpRequest(
                    url="http://feeds.example.test/feed",
                    allowed_hosts=("feeds.example.test",),
                    headers=(("User-Agent", "declared-agent"),),
                    timeout_seconds=1.0,
                    max_response_bytes=100,
                )
            )
        with self.assertRaises(FeedAccessError):
            transport.request(
                HttpRequest(
                    url="https://feeds.example.test/feed",
                    allowed_hosts=("feeds.example.test",),
                    headers=(
                        ("User-Agent", "declared-agent"),
                        ("Authorization", "secret"),
                    ),
                    timeout_seconds=1.0,
                    max_response_bytes=100,
                )
            )


class FeedParsingTests(unittest.TestCase):
    def test_empty_keyword_is_rejected_and_short_ticker_uses_word_boundary(self) -> None:
        with self.assertRaises(ValueError):
            KeywordMapping("AI", ("",), 0.9)
        adapter = GenericFeedAdapter(
            config(
                symbol_mappings=(KeywordMapping("AI", ("ai",), 0.9),),
            ),
            FakeTransport(response()),
        )
        item = adapter.poll(
            since=NOW - timedelta(hours=1),
            until=NOW,
        ).events[0]
        self.assertEqual(item.symbol_relevance, ())

    def test_atom_stores_short_summary_link_hash_and_keyword_relevance(self) -> None:
        adapter = GenericFeedAdapter(config(), FakeTransport(response()))
        batch = adapter.poll(since=NOW - timedelta(hours=1), until=NOW)

        self.assertEqual(len(batch.events), 1)
        item = batch.events[0]
        self.assertLessEqual(len(item.summary), 64)
        self.assertNotIn("<p>", item.summary)
        self.assertEqual(
            item.provenance.canonical_url,
            "https://news.example.test/item-1",
        )
        self.assertEqual(item.symbol_relevance, (("NVDA", 0.95),))
        self.assertEqual(item.entity_relevance, (("NVIDIA", 0.9),))
        self.assertEqual(item.macro_tags, ("SEMICONDUCTOR_CYCLE",))
        self.assertEqual(item.geopolitical_tags, ("US_CHINA_TECH",))
        self.assertEqual(len(item.content_hash), 64)
        self.assertEqual(item.claim_status, ClaimStatus.REPORTED)
        for timestamp in (
            item.event_time,
            item.published_at,
            item.first_seen_at,
            item.available_at,
            item.retrieved_at,
        ):
            self.assertIsNotNone(timestamp.utcoffset())
            self.assertLessEqual(timestamp, NOW)

    def test_rss_is_supported_without_storing_full_description(self) -> None:
        adapter = GenericFeedAdapter(
            config(
                adapter_id="example-rss",
                symbol_mappings=(
                    KeywordMapping("MSFT", ("microsoft", "msft"), 0.9),
                ),
            ),
            FakeTransport(response(RSS)),
        )
        item = adapter.poll(
            since=NOW - timedelta(hours=1),
            until=NOW,
        ).events[0]
        self.assertEqual(item.symbol_relevance, (("MSFT", 0.9),))
        self.assertLessEqual(len(item.summary), 64)
        self.assertNotIn("<p>", item.summary)

    def test_future_dated_entry_is_not_emitted(self) -> None:
        future_atom = ATOM.replace(
            b"2026-07-25T13:55:00Z",
            b"2026-07-25T14:00:01Z",
        )
        adapter = GenericFeedAdapter(
            config(),
            FakeTransport(response(future_atom)),
        )
        batch = adapter.poll(since=NOW - timedelta(hours=1), until=NOW)
        self.assertEqual(batch.events, ())
        self.assertEqual(batch.metadata.future_entries_rejected, 1)


class SecAndCoordinatorTests(unittest.TestCase):
    def test_sec_atom_preserves_accession_form_and_canonical_url(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
        )

        item = adapter.poll(
            since=NOW - timedelta(hours=1),
            until=NOW,
        ).events[0]

        self.assertIn(("accession", "0000320193-26-000081"), item.attributes)
        self.assertIn(("form_type", "8-K"), item.attributes)
        self.assertEqual(
            item.provenance.canonical_url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/filing-index.htm",
        )
        self.assertEqual(item.claim_status, ClaimStatus.VERIFIED)

    def test_sec_factory_builds_separate_8k_and_form4_feeds(self) -> None:
        adapters = build_sec_current_filings_adapters(
            transport=FakeTransport(),
            user_agent="USStockHelper/0.1 research@example.test",
            forms=("8-K", "4"),
        )
        self.assertEqual(tuple(adapter.form_type for adapter in adapters), ("8-K", "4"))
        self.assertTrue(all("output=atom" in adapter.config.feed_url for adapter in adapters))
        self.assertTrue(all(adapter.config.allowed_hosts == ("www.sec.gov",) for adapter in adapters))

    def test_coordinator_uses_validators_and_does_not_republish_unchanged_content(self) -> None:
        transport = FakeTransport(
            response(headers=(("ETag", '"v1"'),)),
            response(b"", status=304, headers=(("ETag", '"v1"'),)),
        )
        adapter = GenericFeedAdapter(config(), transport)
        # A clock that steps past the poll interval: these tests are about
        # cache validators and revisions, not about throttling.
        ticks = iter([NOW + timedelta(minutes=5 * step) for step in range(10)])
        coordinator = PollingCoordinator(clock=lambda: next(ticks))

        first = coordinator.poll(
            adapter,
            since=NOW - timedelta(hours=1),
            until=NOW,
        )
        second = coordinator.poll(
            adapter,
            since=NOW - timedelta(hours=1),
            until=NOW,
        )

        self.assertEqual(len(first.events), 1)
        self.assertEqual(second.events, ())
        self.assertEqual(transport.requests[1].header("If-None-Match"), '"v1"')
        self.assertTrue(second.metadata.not_modified)

    def test_changed_entry_is_published_as_revision_once(self) -> None:
        changed = ATOM.replace(
            b"NVDA demand improved.",
            b"NVDA demand was revised lower.",
        )
        transport = FakeTransport(response(), response(changed), response(changed))
        adapter = GenericFeedAdapter(config(), transport)
        # A clock that steps past the poll interval: these tests are about
        # cache validators and revisions, not about throttling.
        ticks = iter([NOW + timedelta(minutes=5 * step) for step in range(10)])
        coordinator = PollingCoordinator(clock=lambda: next(ticks))

        first = coordinator.poll(
            adapter,
            since=NOW - timedelta(hours=1),
            until=NOW,
        )
        revised = coordinator.poll(
            adapter,
            since=NOW - timedelta(hours=1),
            until=NOW,
        )
        unchanged = coordinator.poll(
            adapter,
            since=NOW - timedelta(hours=1),
            until=NOW,
        )

        self.assertEqual(len(revised.events), 1)
        self.assertEqual(revised.events[0].revision_of, first.events[0].event_id)
        self.assertEqual(revised.events[0].revision_number, 1)
        self.assertEqual(revised.events[0].revised_at, NOW)
        self.assertEqual(unchanged.events, ())


if __name__ == "__main__":
    unittest.main()


class FeedSentimentTests(unittest.TestCase):
    def test_a_feed_event_carries_a_real_reading_not_a_hardcoded_zero(
        self,
    ) -> None:
        from information_layer.event_sentiment import score_event_sentiment

        upbeat = score_event_sentiment("Quarterly profit surged, guidance raised")
        grim = score_event_sentiment("Company warned of a widening loss")

        assert upbeat.score is not None and grim.score is not None
        self.assertGreater(upbeat.score, 0.0)
        self.assertLess(grim.score, 0.0)

    def test_generic_adapter_no_longer_hardcodes_neutral(self) -> None:
        import inspect

        from information_layer.feeds import generic

        source = inspect.getsource(generic)
        # Every real event used to be born neutral, which made the whole
        # sentiment pipeline produce "中性" no matter what the news said.
        self.assertNotIn("sentiment=0.0", source)
        self.assertIn("score_event_sentiment", source)


SEC_TICKERS = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }
)


class SecSymbolAttributionTests(unittest.TestCase):
    def test_a_filing_is_attributed_by_cik_not_by_reading_the_name(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
            cik_registry=CikTickerRegistry.from_sec_payload(SEC_TICKERS),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertIn(("AAPL", 1.0), item.symbol_relevance)
        self.assertIn(("cik", "0000320193"), item.attributes)

    def test_a_filer_outside_the_registry_gets_no_invented_symbol(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
            cik_registry=CikTickerRegistry.from_sec_payload(
                json.dumps(
                    {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "N"}}
                )
            ),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, ())
        self.assertIn(("cik", "0000320193"), item.attributes)

    def test_without_a_registry_the_adapter_still_works(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, ())


SEC_FORM4_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000099</id>
    <title>4 - Cook Timothy D (0001214128) (Reporting)</title>
    <summary>Statement of changes in beneficial ownership.</summary>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000099/filing-index.htm"/>
    <updated>2026-07-25T13:58:00Z</updated>
  </entry>
</feed>
"""


class InsiderFilingAttributionTests(unittest.TestCase):
    def test_a_form_4_reaches_the_issuer_not_the_reporting_person(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="4",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_FORM4_ATOM)),
            cik_registry=CikTickerRegistry.from_sec_payload(SEC_TICKERS),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        # Insider transactions are one of the highest-value signals in this
        # product; attributing them to a natural person loses them entirely.
        self.assertEqual(item.symbol_relevance, (("AAPL", 1.0),))
        self.assertIn(("cik", "0000320193"), item.attributes)


class SecKeywordFallbackTests(unittest.TestCase):
    def test_configured_symbol_keywords_still_apply_without_a_registry(
        self,
    ) -> None:
        # The CIK override silently ignored symbol_mappings, so a caller that
        # configured keyword attribution got nothing and no error.
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
            symbol_mappings=(
                KeywordMapping(key="AAPL", keywords=("Apple",), relevance=0.7),
            ),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        # A keyword guess keeps its configured relevance; only a CIK match is
        # allowed to claim 1.0.
        self.assertEqual(item.symbol_relevance, (("AAPL", 0.7),))

    def test_a_registry_match_outranks_a_keyword_guess(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
            cik_registry=CikTickerRegistry.from_sec_payload(SEC_TICKERS),
            symbol_mappings=(
                KeywordMapping(key="TSLA", keywords=("Apple",), relevance=0.7),
            ),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, (("AAPL", 1.0),))


class FilingMetadataSentimentTests(unittest.TestCase):
    def test_a_filing_title_is_metadata_and_carries_no_sentiment(self) -> None:
        """An EDGAR title is a form type, a legal name, a CIK and a role.

        Words like "strong", "growth" and "record" appear in company names, so
        scoring the title as prose gave every filing from such an issuer a
        measured bullish vote — and CIK attribution then delivered it
        precisely to that ticker.
        """

        atom = SEC_ATOM.replace(
            b"8-K - Apple Inc. (0000320193)",
            b"8-K - STRONG GLOBAL ENTERTAINMENT, INC. (0000320193)",
        )
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(atom)),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertFalse(item.sentiment_measured)
        self.assertEqual(item.sentiment, 0.0)

    def test_an_ordinary_news_feed_still_gets_scored(self) -> None:
        adapter = GenericFeedAdapter(config(), FakeTransport(response()))

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertTrue(item.sentiment_measured)
