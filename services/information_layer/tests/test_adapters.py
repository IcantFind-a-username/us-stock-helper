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

# The same feed as RSS above, but stamped the way real publishers stamp it.
# Every source this project polls writes "GMT" rather than a numeric offset,
# and that difference alone decided whether the entry was read at all.
RSS_GMT = RSS.replace(
    b"<pubDate>Sat, 25 Jul 2026 13:50:00 +0000</pubDate>",
    b"<pubDate>Sat, 25 Jul 2026 13:50:00 GMT</pubDate>",
)

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

    def test_accept_offers_a_wildcard_fallback_so_a_strict_server_still_answers(
        self,
    ) -> None:
        # apps.bea.gov refuses with 406 unless the Accept header ends in a
        # wildcard, which took the whole macro source offline. Naming the feed
        # types first still expresses the preference; the fallback only stops a
        # server from refusing outright, and a reply that is not a feed is
        # rejected by the parser as it always was.
        transport = FakeTransport(response())
        adapter = GenericFeedAdapter(config(), transport)

        adapter.poll(since=NOW - timedelta(hours=1), until=NOW)

        accept = transport.requests[0].header("Accept")
        self.assertIn("application/atom+xml", accept)
        self.assertTrue(
            accept.rstrip().endswith("*/*;q=0.1"),
            f"Accept must fall back to a wildcard, got {accept!r}",
        )

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

    def test_rss_dated_in_gmt_is_read_rather_than_silently_dropped(self) -> None:
        # An RFC-822 stamp was routed to the ISO-8601 parser whenever it
        # contained a capital T, which "GMT" always does. Every entry from
        # every RSS source therefore failed to parse and was discarded without
        # a failure being recorded anywhere: four of this project's seven
        # sources looked healthy while delivering nothing.
        adapter = GenericFeedAdapter(
            config(
                adapter_id="example-rss",
                symbol_mappings=(
                    KeywordMapping("MSFT", ("microsoft", "msft"), 0.9),
                ),
            ),
            FakeTransport(response(RSS_GMT)),
        )

        batch = adapter.poll(since=NOW - timedelta(hours=1), until=NOW)

        self.assertEqual(len(batch.events), 1, "a GMT-stamped entry was dropped")
        self.assertEqual(
            batch.events[0].published_at,
            datetime(2026, 7, 25, 13, 50, tzinfo=timezone.utc),
        )

    def test_a_plain_http_entry_link_is_upgraded_not_dropped(self) -> None:
        # FDA's own press feed writes http:// links. The announcement is
        # real; only the link scheme is unacceptable, so the citation gets
        # the secure form of the same URL.
        insecure = ATOM.replace(
            b'href="https://news.example.test/item-1"',
            b'href="http://news.example.test/item-1"',
        )
        adapter = GenericFeedAdapter(config(), FakeTransport(response(insecure)))

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(
            item.provenance.canonical_url,
            "https://news.example.test/item-1",
        )

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
    def test_a_reporting_entry_claims_no_symbol_of_its_own(self) -> None:
        """EDGAR's getcurrent feed does not carry the issuer on this entry.

        An earlier attempt read a second CIK out of the archive path; against
        live EDGAR that produced no second candidate in any of 499 entries, so
        it never fired. Worse, when the reporting person is itself listed, the
        first resolvable candidate is that insider's own stock. The issuer
        arrives as a separate entry of the same filing, which is where the
        symbol comes from.
        """

        adapter = SecCurrentFilingsAdapter(
            form_type="4",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_FORM4_ATOM)),
            cik_registry=CikTickerRegistry.from_sec_payload(SEC_TICKERS),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, ())
        self.assertIn(("filer_role", "reporting"), item.attributes)


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


BERKSHIRE_FORM4 = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>urn:tag:sec.gov,2008:accession-number=0001193125-26-333151</id>
    <title>4 - BERKSHIRE HATHAWAY INC (0001067983) (Reporting)</title>
    <summary>Statement of changes in beneficial ownership.</summary>
    <link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1067983/000119312526333151/x.htm"/>
    <updated>2026-07-25T13:58:00Z</updated>
  </entry>
</feed>
"""

BERKSHIRE_TICKERS = json.dumps(
    {
        "0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY"},
        "1": {"cik_str": 927066, "ticker": "DVA", "title": "DAVITA INC."},
    }
)


class ReportingPersonAttributionTests(unittest.TestCase):
    def test_a_listed_insider_is_not_the_subject_of_its_own_form_4(self) -> None:
        """Berkshire files a Form 4 about DaVita; both are listed.

        Resolving "the first candidate CIK with a ticker" sent that DaVita
        insider trade to Berkshire's own stock, at relevance 1.0, as verified
        top-reliability evidence. EDGAR labels the entry (Reporting); that
        label is the answer.
        """

        adapter = SecCurrentFilingsAdapter(
            form_type="4",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(BERKSHIRE_FORM4)),
            cik_registry=CikTickerRegistry.from_sec_payload(BERKSHIRE_TICKERS),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, ())
        self.assertIn(("filer_role", "reporting"), item.attributes)
        # Still traceable to the party that filed it.
        self.assertIn(("cik", "0001067983"), item.attributes)

    def test_the_issuer_entry_of_the_same_filing_is_attributed(self) -> None:
        issuer_atom = BERKSHIRE_FORM4.replace(
            b"4 - BERKSHIRE HATHAWAY INC (0001067983) (Reporting)",
            b"4 - DAVITA INC. (0000927066) (Issuer)",
        )
        adapter = SecCurrentFilingsAdapter(
            form_type="4",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(issuer_atom)),
            cik_registry=CikTickerRegistry.from_sec_payload(BERKSHIRE_TICKERS),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertEqual(item.symbol_relevance, (("DVA", 1.0),))


class FormTypePrefixTests(unittest.TestCase):
    def test_a_prefix_match_is_not_labelled_as_the_requested_form(self) -> None:
        """EDGAR's type= parameter matches by prefix.

        Asking for "4" also returns 424B2, 425 and 497K. Stamping those with
        form_type=4 turns a prospectus supplement into an insider transaction
        for anything reading that attribute.
        """

        atom = SEC_ATOM.replace(
            b"8-K - Apple Inc. (0000320193)",
            b"424B2 - Apple Inc. (0000320193)",
        )
        adapter = SecCurrentFilingsAdapter(
            form_type="4",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(atom)),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertIn(("form_type", "424B2"), item.attributes)
        self.assertNotIn(("form_type", "4"), item.attributes)

    def test_the_requested_form_is_still_recorded_when_it_matches(self) -> None:
        adapter = SecCurrentFilingsAdapter(
            form_type="8-K",
            user_agent="USStockHelper/0.1 research@example.test",
            transport=FakeTransport(response(SEC_ATOM)),
        )

        item = adapter.poll(since=NOW - timedelta(hours=1), until=NOW).events[0]

        self.assertIn(("form_type", "8-K"), item.attributes)


# --- Widened current-filings coverage, proven against captured EDGAR payloads.
#
# Every fixture below is the raw Atom body EDGAR actually served on
# 2026-08-16 (12:41 EDT) to this project's own User-Agent, saved unmodified.
# The retrieval moment for replaying them must postdate their entries.

FIXTURE_NOW = datetime(2026, 8, 16, 17, 0, tzinfo=UTC)
FIXTURE_SINCE = FIXTURE_NOW - timedelta(days=3)


def fixture_bytes(name: str) -> bytes:
    from pathlib import Path

    return (Path(__file__).parent / "fixtures" / name).read_bytes()


def fixture_adapter(
    form_type: str,
    fixture: str,
    *,
    tickers: str,
) -> SecCurrentFilingsAdapter:
    return SecCurrentFilingsAdapter(
        form_type=form_type,
        user_agent="USStockHelper/0.1 research@example.test",
        transport=FakeTransport(
            response(fixture_bytes(fixture), retrieved_at=FIXTURE_NOW)
        ),
        cik_registry=CikTickerRegistry.from_sec_payload(tickers),
    )


def events_for(adapter: SecCurrentFilingsAdapter):
    return adapter.poll(since=FIXTURE_SINCE, until=FIXTURE_NOW).events


def event_with_cik(events, cik: str):
    for item in events:
        if ("cik", cik) in item.attributes:
            return item
    raise AssertionError(f"no event carries cik {cik}")


# The Outdoor Holding 13D/A pair: Urvan (Filed by) + Outdoor Holding (Subject)
# share accession 0001493152-26-038570. The holder is deliberately given a
# listed ticker here, exactly the shape of the DaVita/Berkshire incident.
OWNERSHIP_TICKERS = json.dumps(
    {
        "0": {"cik_str": 1015383, "ticker": "POWW", "title": "Outdoor Holding Co"},
        "1": {"cik_str": 1859485, "ticker": "URVN", "title": "Urvan Listed Co"},
        "2": {"cik_str": 1871638, "ticker": "BZAI", "title": "Blaize Holdings"},
        "3": {"cik_str": 1326389, "ticker": "PLRA", "title": "Polar Listed Co"},
    }
)

REPORT_TICKERS = json.dumps(
    {
        "0": {"cik_str": 106040, "ticker": "WDC", "title": "Western Digital"},
        "1": {"cik_str": 1650372, "ticker": "TEAM", "title": "Atlassian Corp"},
    }
)


class BeneficialOwnershipFormCodeTests(unittest.TestCase):
    def test_the_retired_sc_13d_code_returns_no_entries(self) -> None:
        """EDGAR retired SC 13D/SC 13G; getcurrent answers "No recent filings".

        The captured empty feed is the evidence for why the registry declares
        SCHEDULE 13D / SCHEDULE 13G instead of the plan's assumed codes.
        """

        for fixture in (
            "sec_current_sc_13d_empty.atom",
            "sec_current_sc_13g_empty.atom",
        ):
            with self.subTest(fixture=fixture):
                adapter = fixture_adapter(
                    "SC 13D", fixture, tickers=OWNERSHIP_TICKERS
                )
                self.assertEqual(events_for(adapter), ())

    def test_a_multiword_form_builds_a_hyphenated_adapter_id(self) -> None:
        # The registry pins adapter_id == source_id, and a source_id with a
        # space in it breaks every convention the coordinator state is keyed
        # by.
        adapter = fixture_adapter(
            "SCHEDULE 13D",
            "sec_current_schedule_13d.atom",
            tickers=OWNERSHIP_TICKERS,
        )

        self.assertEqual(adapter.adapter_id, "sec-current-schedule-13d")

    def test_a_subject_entry_is_attributed_to_the_issuer(self) -> None:
        """The Subject party of a 13D names the stock being accumulated."""

        events = events_for(
            fixture_adapter(
                "SCHEDULE 13D",
                "sec_current_schedule_13d.atom",
                tickers=OWNERSHIP_TICKERS,
            )
        )

        subject = event_with_cik(events, "0001015383")
        self.assertEqual(subject.symbol_relevance, (("POWW", 1.0),))
        self.assertIn(("filer_role", "subject"), subject.attributes)
        self.assertEqual(subject.claim_status, ClaimStatus.VERIFIED)
        self.assertEqual(subject.available_at, FIXTURE_NOW)
        self.assertEqual(subject.retrieved_at, FIXTURE_NOW)

    def test_a_filed_by_entry_claims_no_symbol_even_when_the_holder_is_listed(
        self,
    ) -> None:
        """The Filed-by party is the holder, not the stock the filing is about.

        When the holder itself is listed, attributing its own ticker files an
        accumulation of Outdoor Holding under the holder's stock — the same
        misattribution that once sent a DaVita insider trade to Berkshire, as
        verified top-reliability evidence. The issuer arrives as the paired
        (Subject) entry of the same accession.
        """

        events = events_for(
            fixture_adapter(
                "SCHEDULE 13D",
                "sec_current_schedule_13d.atom",
                tickers=OWNERSHIP_TICKERS,
            )
        )

        holder = event_with_cik(events, "0001859485")
        self.assertEqual(holder.symbol_relevance, ())
        self.assertIn(("filer_role", "filed by"), holder.attributes)

    def test_an_amendment_carries_its_actual_form_not_the_requested_prefix(
        self,
    ) -> None:
        # type=SCHEDULE 13D prefix-matches SCHEDULE 13D/A. Stamping the
        # amendment with the original's form erases the distinction between
        # a new stake and a change to a disclosed one.
        events = events_for(
            fixture_adapter(
                "SCHEDULE 13D",
                "sec_current_schedule_13d.atom",
                tickers=OWNERSHIP_TICKERS,
            )
        )

        forms = {
            value
            for item in events
            for key, value in item.attributes
            if key == "form_type"
        }
        self.assertEqual(forms, {"SCHEDULE 13D", "SCHEDULE 13D/A"})

    def test_a_13g_subject_entry_is_attributed_to_the_issuer(self) -> None:
        events = events_for(
            fixture_adapter(
                "SCHEDULE 13G",
                "sec_current_schedule_13g.atom",
                tickers=OWNERSHIP_TICKERS,
            )
        )

        subject = event_with_cik(events, "0001871638")
        self.assertEqual(subject.symbol_relevance, (("BZAI", 1.0),))
        holder = event_with_cik(events, "0001326389")
        self.assertEqual(holder.symbol_relevance, ())


class QuarterlyAndAnnualReportFeedTests(unittest.TestCase):
    def test_10q_events_verify_attribute_and_stamp_like_the_8k_feed(self) -> None:
        events = events_for(
            fixture_adapter(
                "10-Q", "sec_current_10q.atom", tickers=REPORT_TICKERS
            )
        )

        self.assertTrue(events)
        forms = {
            value
            for item in events
            for key, value in item.attributes
            if key == "form_type"
        }
        self.assertEqual(forms, {"10-Q", "10-Q/A"})
        for item in events:
            self.assertEqual(item.claim_status, ClaimStatus.VERIFIED)
            self.assertEqual(item.available_at, FIXTURE_NOW)
            self.assertEqual(item.retrieved_at, FIXTURE_NOW)
            self.assertFalse(item.sentiment_measured)

    def test_a_10k_filer_resolves_through_the_cik_registry(self) -> None:
        events = events_for(
            fixture_adapter(
                "10-K", "sec_current_10k.atom", tickers=REPORT_TICKERS
            )
        )

        forms = {
            value
            for item in events
            for key, value in item.attributes
            if key == "form_type"
        }
        self.assertEqual(forms, {"10-K", "10-K/A"})
        western_digital = event_with_cik(events, "0000106040")
        self.assertEqual(western_digital.symbol_relevance, (("WDC", 1.0),))
        atlassian = event_with_cik(events, "0001650372")
        self.assertEqual(atlassian.symbol_relevance, (("TEAM", 1.0),))


class CompanyIrFeedFixtureTests(unittest.TestCase):
    """The captured newsroom payloads, parsed by the sources that declare them."""

    @staticmethod
    def _events(source_id: str, fixture: str):
        from information_layer.feeds.registry import (
            PUBLIC_SOURCES,
            SourceRegistry,
            build_adapters,
        )

        row = next(
            item
            for item in PUBLIC_SOURCES.sources
            if item.source_id == source_id
        )
        (adapter,) = build_adapters(
            registry=SourceRegistry((row,)),
            transport=FakeTransport(
                response(fixture_bytes(fixture), retrieved_at=FIXTURE_NOW)
            ),
        )
        return adapter.poll(
            since=FIXTURE_NOW - timedelta(days=7), until=FIXTURE_NOW
        ).events

    def test_a_boeing_release_naming_the_company_is_attributed(self) -> None:
        events = self._events("boeing-newsroom", "ir_boeing_mediaroom.rss")

        self.assertTrue(events)
        named = [
            item for item in events if "boeing" in item.headline.casefold()
        ]
        self.assertTrue(named)
        for item in named:
            self.assertEqual(item.symbol_relevance, (("BA", 0.9),))
            self.assertEqual(item.claim_status, ClaimStatus.VERIFIED)

    def test_a_release_that_never_names_the_company_claims_no_symbol(
        self,
    ) -> None:
        # "Introducing Gemini 3.7 Flash" never says Google: attribution is
        # earned from the text, not assumed from the channel.
        events = self._events("google-newsroom", "ir_google_blog.rss")

        self.assertTrue(events)
        silent = [
            item
            for item in events
            if "google" not in item.headline.casefold()
            and "google" not in item.summary.casefold()
        ]
        self.assertTrue(silent)
        for item in silent:
            self.assertEqual(item.symbol_relevance, ())


class NasdaqHaltsAdapterTests(unittest.TestCase):
    """The halts feed names tickers authoritatively but carries no links.

    Its items have neither <guid> nor <link>, so the generic parser drops
    every one of them; the dedicated adapter reads the ndaq:* fields instead
    and stands in a stable identity per halt.
    """

    @staticmethod
    def _adapter(transport):
        from information_layer.feeds import NasdaqHaltsAdapter

        return NasdaqHaltsAdapter(
            FeedConfig(
                adapter_id="nasdaq-trade-halts",
                feed_url="https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts",
                allowed_hosts=("www.nasdaqtrader.com",),
                publisher_id="nasdaq",
                publisher_name="Nasdaq Trader",
                source_type="regulatory_filing",
                reliability=0.99,
                user_agent="USStockHelper/0.1 research@example.test",
                robots_allowed=True,
                minimum_poll_interval_seconds=60.0,
                claim_status=ClaimStatus.VERIFIED,
            ),
            transport,
        )

    def _events(self):
        adapter = self._adapter(
            FakeTransport(
                response(
                    fixture_bytes("nasdaq_trade_halts.rss"),
                    retrieved_at=FIXTURE_NOW,
                )
            )
        )
        return adapter.poll(
            since=FIXTURE_NOW - timedelta(days=60), until=FIXTURE_NOW
        ).events

    def test_halt_items_without_links_are_still_read(self) -> None:
        events = self._events()

        self.assertTrue(events)

    def test_a_halt_names_its_ticker_reason_and_pit_stamps(self) -> None:
        events = self._events()

        talk = next(
            item
            for item in events
            if ("halt_symbol", "TALK") in item.attributes
        )
        self.assertEqual(talk.symbol_relevance, (("TALK", 1.0),))
        self.assertIn(("reason_code", "T12"), talk.attributes)
        self.assertIn(("market", "NASDAQ"), talk.attributes)
        self.assertEqual(talk.claim_status, ClaimStatus.VERIFIED)
        self.assertEqual(talk.available_at, FIXTURE_NOW)
        self.assertEqual(talk.retrieved_at, FIXTURE_NOW)
        # A halt notice is exchange metadata, not prose to be scored.
        self.assertFalse(talk.sentiment_measured)
        self.assertEqual(talk.sentiment, 0.0)

    def test_an_unchanged_feed_is_not_reannounced(self) -> None:
        body = fixture_bytes("nasdaq_trade_halts.rss")
        adapter = self._adapter(
            FakeTransport(
                response(body, retrieved_at=FIXTURE_NOW),
                response(body, retrieved_at=FIXTURE_NOW),
            )
        )
        ticks = iter(
            FIXTURE_NOW + timedelta(minutes=5 * step) for step in range(4)
        )
        coordinator = PollingCoordinator(clock=lambda: next(ticks))

        first = coordinator.poll(
            adapter, since=FIXTURE_NOW - timedelta(days=60), until=FIXTURE_NOW
        )
        second = coordinator.poll(
            adapter, since=FIXTURE_NOW - timedelta(days=60), until=FIXTURE_NOW
        )

        self.assertTrue(first.events)
        self.assertEqual(second.events, ())


class AgencyFeedFixtureTests(unittest.TestCase):
    """FDA / FTC / DOJ press feeds, parsed from captured payloads."""

    @staticmethod
    def _events_for(source_id: str, fixture: str, *, days: int = 30):
        from information_layer.feeds.registry import (
            PUBLIC_SOURCES,
            SourceRegistry,
            build_adapters,
        )

        row = next(
            item
            for item in PUBLIC_SOURCES.sources
            if item.source_id == source_id
        )
        (adapter,) = build_adapters(
            registry=SourceRegistry((row,)),
            transport=FakeTransport(
                response(fixture_bytes(fixture), retrieved_at=FIXTURE_NOW)
            ),
        )
        return adapter.poll(
            since=FIXTURE_NOW - timedelta(days=days), until=FIXTURE_NOW
        )

    def test_fda_releases_parse_verified_and_scored(self) -> None:
        result = self._events_for("fda-press-releases", "fda_press_releases.rss")

        self.assertTrue(result.events)
        for item in result.events:
            self.assertEqual(item.claim_status, ClaimStatus.VERIFIED)
        # Agency prose is readable, unlike filing metadata titles.
        self.assertTrue(any(item.sentiment_measured for item in result.events))
        # None of the current items names a mapped company: no symbol may be
        # invented for them.
        for item in result.events:
            self.assertEqual(item.symbol_relevance, ())

    def test_ftc_releases_parse(self) -> None:
        result = self._events_for("ftc-press-releases", "ftc_press_releases.rss")

        self.assertTrue(result.events)

    def test_a_future_dated_doj_item_is_rejected_loudly(self) -> None:
        # The captured DOJ feed really carries a planned item dated
        # 2026-10-30 — later than the capture moment. Publishing it would
        # feed tomorrow's knowledge into today's decision.
        result = self._events_for("doj-press-releases", "doj_justice_news.rss")

        self.assertTrue(result.events)
        self.assertGreaterEqual(result.metadata.future_entries_rejected, 1)
        for item in result.events:
            self.assertLessEqual(item.published_at, FIXTURE_NOW)
