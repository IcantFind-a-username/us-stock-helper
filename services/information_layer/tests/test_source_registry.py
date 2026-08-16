from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from information_layer import CikTickerRegistry, ClaimStatus
from information_layer.feeds import (
    FeedAccessError,
    GenericFeedAdapter,
    HttpRequest,
    HttpResponse,
    SecCurrentFilingsAdapter,
)
from information_layer.feeds.registry import (
    PUBLIC_SOURCES,
    SourceKind,
    SourceRegistry,
    SourceSpec,
    build_adapters,
    company_ir_source,
    contact_email_from_environment,
    minimum_poll_interval_seconds,
    user_agent_for,
)


CONTACT = "ops@example.test"


def cik_registry() -> CikTickerRegistry:
    return CikTickerRegistry.from_sec_payload(
        json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}})
    )


class NullTransport:
    def request(self, request: HttpRequest) -> HttpResponse:
        raise AssertionError("the registry must not perform I/O while building")


def spec(**overrides: object) -> SourceSpec:
    values: dict[str, object] = {
        "source_id": "example-official",
        "kind": SourceKind.OFFICIAL_ANNOUNCEMENT,
        "publisher_id": "example-issuer",
        "publisher_name": "Example Issuer",
        "feed_url": "https://ir.example.test/press.rss",
        "allowed_hosts": ("ir.example.test",),
        "reliability": 0.9,
        "poll_interval_seconds": 900.0,
        "requires_contact_user_agent": False,
        "robots_allows_polling": True,
        "claim_status": ClaimStatus.REPORTED,
    }
    values.update(overrides)
    return SourceSpec(**values)  # type: ignore[arg-type]


def edgar_spec(**overrides: object) -> SourceSpec:
    values: dict[str, object] = {
        "source_id": "example-filing",
        "kind": SourceKind.REGULATORY_FILING,
        "publisher_id": "sec-edgar",
        "publisher_name": "U.S. SEC EDGAR",
        "feed_url": None,
        "sec_form_type": "8-K",
        "allowed_hosts": ("www.sec.gov",),
        "reliability": 0.99,
        "poll_interval_seconds": 300.0,
        "requires_contact_user_agent": True,
        "robots_allows_polling": True,
        "claim_status": ClaimStatus.VERIFIED,
    }
    values.update(overrides)
    return SourceSpec(**values)  # type: ignore[arg-type]


class SourceSpecValidationTests(unittest.TestCase):
    def test_a_plain_http_endpoint_is_refused(self) -> None:
        with self.assertRaises(FeedAccessError):
            spec(feed_url="http://ir.example.test/press.rss")

    def test_an_endpoint_outside_its_own_allowlist_is_refused(self) -> None:
        with self.assertRaises(FeedAccessError):
            spec(feed_url="https://elsewhere.example/press.rss")

    def test_a_source_robots_disallows_cannot_be_declared(self) -> None:
        with self.assertRaises(FeedAccessError):
            spec(robots_allows_polling=False)

    def test_a_spec_must_name_exactly_one_endpoint_kind(self) -> None:
        with self.assertRaises(FeedAccessError):
            spec(feed_url=None, sec_form_type=None)
        with self.assertRaises(FeedAccessError):
            spec(sec_form_type="8-K")

    def test_reliability_outside_the_unit_range_is_refused(self) -> None:
        for value in (-0.1, 0.0, 1.1):
            with self.subTest(reliability=value):
                with self.assertRaises(ValueError):
                    spec(reliability=value)

    def test_polling_faster_than_the_floor_for_its_kind_is_refused(self) -> None:
        floor = minimum_poll_interval_seconds(SourceKind.OFFICIAL_ANNOUNCEMENT)
        with self.assertRaises(ValueError):
            spec(poll_interval_seconds=floor - 1.0)
        self.assertIsNotNone(spec(poll_interval_seconds=floor))

    def test_an_edgar_spec_must_declare_the_contact_user_agent_it_needs(self) -> None:
        with self.assertRaises(FeedAccessError):
            edgar_spec(requires_contact_user_agent=False)

    def test_an_edgar_spec_may_only_address_the_commissions_own_host(self) -> None:
        with self.assertRaises(FeedAccessError):
            edgar_spec(allowed_hosts=("edgar.example.test",))
        self.assertIsNotNone(edgar_spec())


class RegistryValidationTests(unittest.TestCase):
    def test_a_duplicate_source_id_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SourceRegistry((spec(), spec()))

    def test_an_empty_registry_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SourceRegistry(())

    def test_a_registry_can_report_which_sources_need_a_contact(self) -> None:
        registry = SourceRegistry((spec(), edgar_spec()))

        self.assertEqual(
            [item.source_id for item in registry.requiring_contact()],
            ["example-filing"],
        )


class ShippedRegistryTests(unittest.TestCase):
    def test_every_shipped_source_carries_its_full_declaration(self) -> None:
        self.assertTrue(PUBLIC_SOURCES.sources)
        for item in PUBLIC_SOURCES.sources:
            with self.subTest(source=item.source_id):
                self.assertIsInstance(item.kind, SourceKind)
                self.assertGreater(item.reliability, 0.0)
                self.assertLessEqual(item.reliability, 1.0)
                self.assertGreaterEqual(
                    item.poll_interval_seconds,
                    minimum_poll_interval_seconds(item.kind),
                )
                self.assertTrue(item.robots_allows_polling)
                self.assertTrue(item.publisher_name.strip())

    def test_only_public_official_or_issuer_channels_ship(self) -> None:
        # A licensed wire cannot be polled without a contract, so none is
        # declared here; the enum keeps the slot so an entry is a deliberate
        # act rather than an omission.
        self.assertEqual(
            {item.kind for item in PUBLIC_SOURCES.sources},
            {
                SourceKind.REGULATORY_FILING,
                SourceKind.MACRO_DATA,
                SourceKind.OFFICIAL_ANNOUNCEMENT,
            },
        )

    def test_edgar_is_the_only_source_demanding_a_contact_user_agent(self) -> None:
        self.assertTrue(PUBLIC_SOURCES.requiring_contact())
        for item in PUBLIC_SOURCES.requiring_contact():
            with self.subTest(source=item.source_id):
                self.assertEqual(item.publisher_id, "sec-edgar")

    def test_the_registry_hardcodes_no_contact_address(self) -> None:
        source = Path(
            __import__(
                "information_layer.feeds.registry",
                fromlist=["__file__"],
            ).__file__
        ).read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", source))


class WidenedSecCoverageTests(unittest.TestCase):
    """The six form feeds that actually move prices, declared as one set.

    Captured live samples (tests/fixtures/sec_current_*.atom, 2026-08-16)
    are the authority for the codes: EDGAR retired SC 13D / SC 13G — those
    type= queries answer "No recent filings" — and serves beneficial
    ownership under SCHEDULE 13D / SCHEDULE 13G.
    """

    def test_the_registry_polls_all_six_current_filing_forms(self) -> None:
        self.assertEqual(
            {item.sec_form_type for item in PUBLIC_SOURCES.requiring_cik_registry()},
            {"8-K", "4", "10-Q", "10-K", "SCHEDULE 13D", "SCHEDULE 13G"},
        )

    def test_beneficial_ownership_uses_the_codes_edgar_actually_serves(
        self,
    ) -> None:
        declared = {item.sec_form_type for item in PUBLIC_SOURCES.sources}
        self.assertNotIn("SC 13D", declared)
        self.assertNotIn("SC 13G", declared)

    def test_every_sec_source_shares_the_8k_terms(self) -> None:
        sec_sources = PUBLIC_SOURCES.requiring_cik_registry()
        self.assertEqual(len(sec_sources), 6)
        for item in sec_sources:
            with self.subTest(source=item.source_id):
                self.assertIs(item.kind, SourceKind.REGULATORY_FILING)
                self.assertEqual(item.publisher_id, "sec-edgar")
                self.assertEqual(item.allowed_hosts, ("www.sec.gov",))
                self.assertEqual(item.reliability, 0.99)
                self.assertEqual(item.poll_interval_seconds, 300.0)
                self.assertTrue(item.requires_contact_user_agent)
                self.assertIs(item.claim_status, ClaimStatus.VERIFIED)

    def test_the_standalone_factory_agrees_with_the_registry(self) -> None:
        # Production builds through SourceSpec/_adapter_for; the factory is
        # the documented library entry point. Two disagreeing form lists mean
        # one of them silently polls less than the product claims.
        from information_layer.feeds import build_sec_current_filings_adapters

        factory_ids = {
            adapter.adapter_id
            for adapter in build_sec_current_filings_adapters(
                transport=NullTransport(),
                user_agent="USStockHelper/0.1 research@example.test",
            )
        }
        registry_ids = {
            item.source_id for item in PUBLIC_SOURCES.requiring_cik_registry()
        }
        self.assertEqual(factory_ids, registry_ids)


def ir_row(**overrides: object) -> SourceSpec:
    values: dict[str, object] = {
        "symbol": "MSFT",
        "company_name": "Microsoft Corporation",
        "publisher_id": "microsoft",
        "publisher_name": "Microsoft Source",
        "feed_url": "https://news.microsoft.com/feed/",
        "host": "news.microsoft.com",
        "keywords": ("microsoft", "msft"),
    }
    values.update(overrides)
    return company_ir_source(**values)  # type: ignore[arg-type]


class CompanyIrSourceBuilderTests(unittest.TestCase):
    """One declarative row per verified newsroom, instead of hand-written specs.

    Every shipped row's feed was actually fetched and its robots policy read
    before registration (ledger, Task 2). The builder exists so declaring the
    next one is one line whose invariants are enforced at construction.
    """

    def test_a_row_expands_into_a_complete_official_announcement_spec(
        self,
    ) -> None:
        source = ir_row()

        self.assertEqual(source.source_id, "microsoft-newsroom")
        self.assertIs(source.kind, SourceKind.OFFICIAL_ANNOUNCEMENT)
        self.assertEqual(source.publisher_name, "Microsoft Source")
        self.assertEqual(source.allowed_hosts, ("news.microsoft.com",))
        self.assertEqual(source.reliability, 0.95)
        self.assertEqual(source.poll_interval_seconds, 900.0)
        self.assertIs(source.claim_status, ClaimStatus.VERIFIED)
        self.assertEqual(len(source.symbol_mappings), 1)
        mapping = source.symbol_mappings[0]
        self.assertEqual(mapping.key, "MSFT")
        self.assertEqual(mapping.keywords, ("microsoft", "msft"))
        self.assertEqual(mapping.relevance, 0.9)
        # The entity is keyed by the issuer's name and earned from the text by
        # the company word, exactly like the original two newsrooms.
        self.assertEqual(len(source.entity_mappings), 1)
        self.assertEqual(source.entity_mappings[0].key, "Microsoft Corporation")
        self.assertEqual(source.entity_mappings[0].keywords, ("microsoft",))

    def test_a_blank_symbol_is_refused(self) -> None:
        for symbol in ("", "   "):
            with self.subTest(symbol=repr(symbol)):
                with self.assertRaises(ValueError):
                    ir_row(symbol=symbol)

    def test_a_blank_company_name_or_empty_keywords_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            ir_row(company_name="  ")
        with self.assertRaises(ValueError):
            ir_row(keywords=())

    def test_a_plain_http_feed_is_refused(self) -> None:
        with self.assertRaises(FeedAccessError):
            ir_row(feed_url="http://news.microsoft.com/feed/")

    def test_a_feed_outside_its_declared_host_is_refused(self) -> None:
        with self.assertRaises(FeedAccessError):
            ir_row(feed_url="https://elsewhere.example/feed/")

    def test_two_rows_for_one_publisher_are_refused_by_the_registry(self) -> None:
        with self.assertRaises(ValueError):
            SourceRegistry((ir_row(), ir_row(symbol="MSFT2")))


# Common English words mis-attribute: an issuer feed saying "grab a coffee"
# is not about Grab Holdings. Tickers whose only obvious keyword is such a
# word (GRAB, SOUN via "sound", COIN, RIOT …) stay out of the table until
# they get a distinctive key like "grab holdings" — leaving them out is the
# documented decision, not an oversight.
_AMBIGUOUS_COMMON_WORDS = frozenset(
    {"grab", "sound", "coin", "riot", "circle", "nio", "mo", "ba"}
)


class IrKeywordHonestyTests(unittest.TestCase):
    def test_a_common_word_keyword_would_misattribute(self) -> None:
        """The trap itself, demonstrated: the verb fires, the symbol lies."""

        from information_layer.feeds import FeedConfig, GenericFeedAdapter

        rss = (
            b'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            b"<item><guid>x-1</guid>"
            b"<title>Analysts grab bargains after the selloff</title>"
            b"<description>Nothing about any listed holding company.</description>"
            b"<link>https://news.example.test/x-1</link>"
            b"<pubDate>Sat, 25 Jul 2026 13:50:00 +0000</pubDate>"
            b"</item></channel></rss>"
        )

        import datetime as _dt

        from information_layer.feeds import HttpResponse, KeywordMapping

        now = _dt.datetime(2026, 7, 25, 14, 0, tzinfo=_dt.timezone.utc)

        class OneShot:
            def request(self, request: HttpRequest) -> HttpResponse:
                return HttpResponse(
                    status_code=200, headers=(), body=rss, retrieved_at=now
                )

        adapter = GenericFeedAdapter(
            FeedConfig(
                adapter_id="misattribution-demo",
                feed_url="https://news.example.test/rss",
                allowed_hosts=("news.example.test",),
                publisher_id="example",
                publisher_name="Example",
                source_type="official_announcement",
                reliability=0.95,
                user_agent="USStockHelper/0.1 research@example.test",
                robots_allowed=True,
                symbol_mappings=(KeywordMapping("GRAB", ("grab",), 0.9),),
            ),
            OneShot(),
        )

        item = adapter.poll(
            since=now - _dt.timedelta(hours=1), until=now
        ).events[0]

        self.assertEqual(item.symbol_relevance, (("GRAB", 0.9),))

    def test_no_shipped_ir_keyword_is_an_ambiguous_common_word(self) -> None:
        for source in PUBLIC_SOURCES.of_kind(SourceKind.OFFICIAL_ANNOUNCEMENT):
            for mapping in source.symbol_mappings:
                for keyword in mapping.keywords:
                    with self.subTest(source=source.source_id, keyword=keyword):
                        self.assertNotIn(
                            keyword.casefold(), _AMBIGUOUS_COMMON_WORDS
                        )


class ShippedIrCoverageTests(unittest.TestCase):
    def test_the_registry_carries_the_seven_verified_newsrooms(self) -> None:
        announcements = {
            item.source_id: item
            for item in PUBLIC_SOURCES.of_kind(SourceKind.OFFICIAL_ANNOUNCEMENT)
        }

        expected_symbols = {
            "apple-newsroom": "AAPL",
            "nvidia-newsroom": "NVDA",
            "microsoft-newsroom": "MSFT",
            "intel-newsroom": "INTC",
            "boeing-newsroom": "BA",
            "amazon-newsroom": "AMZN",
            "google-newsroom": "GOOGL",
        }
        self.assertEqual(set(announcements), set(expected_symbols))
        for source_id, symbol in expected_symbols.items():
            with self.subTest(source=source_id):
                source = announcements[source_id]
                self.assertEqual(source.symbol_mappings[0].key, symbol)
                self.assertEqual(source.reliability, 0.95)
                self.assertEqual(source.poll_interval_seconds, 900.0)
                self.assertFalse(source.requires_contact_user_agent)


class UserAgentTests(unittest.TestCase):
    def test_a_missing_contact_address_is_refused_rather_than_invented(self) -> None:
        for environment in ({}, {"US_STOCK_HELPER_CONTACT_EMAIL": "   "}):
            with self.subTest(environment=environment):
                with self.assertRaises(FeedAccessError):
                    contact_email_from_environment(environment)

    def test_a_contact_address_that_is_not_an_address_is_refused(self) -> None:
        with self.assertRaises(FeedAccessError):
            contact_email_from_environment(
                {"US_STOCK_HELPER_CONTACT_EMAIL": "not-an-address"}
            )

    def test_the_user_agent_names_the_application_and_the_contact(self) -> None:
        agent = user_agent_for(CONTACT)

        self.assertIn(CONTACT, agent)
        self.assertIn("us-stock-helper", agent)
        # SEC refuses a User-Agent that does not identify both.
        self.assertIn("@", agent)
        self.assertIn(" ", agent.strip())


class AdapterBuildTests(unittest.TestCase):
    def test_edgar_refuses_to_start_without_a_configured_contact(self) -> None:
        with self.assertRaises(FeedAccessError) as failure:
            build_adapters(transport=NullTransport(), contact_email=None)

        # Naming the variable, not just failing: the deeper SEC adapter would
        # also refuse this User-Agent, and an operator reading that message
        # learns nothing about what to configure.
        message = str(failure.exception)
        self.assertIn("US_STOCK_HELPER_CONTACT_EMAIL", message)
        self.assertIn("sec-current-8-k", message)

    def test_sources_that_need_no_contact_still_start_without_one(self) -> None:
        registry = SourceRegistry((spec(),))

        adapters = build_adapters(
            registry=registry,
            transport=NullTransport(),
            contact_email=None,
        )

        self.assertEqual([item.adapter_id for item in adapters], ["example-official"])

    def test_sec_sources_refuse_to_build_without_a_cik_registry(self) -> None:
        # A filing without registry attribution never reaches any symbol's
        # decision (its symbol_relevance is empty, so the scope filter drops
        # it), and that happened silently in production because nothing
        # stopped this construction from succeeding. Building the real public
        # source set has to be impossible without a registry, not just
        # degraded.
        with self.assertRaises(FeedAccessError) as failure:
            build_adapters(
                transport=NullTransport(),
                contact_email=CONTACT,
            )

        message = str(failure.exception)
        self.assertIn("cik", message.lower())
        self.assertIn("sec-current-8-k", message)
        self.assertIn("sec-current-4", message)

    def test_every_declared_source_becomes_an_adapter_carrying_its_terms(
        self,
    ) -> None:
        adapters = build_adapters(
            transport=NullTransport(),
            contact_email=CONTACT,
            cik_registry=cik_registry(),
        )

        by_id = {adapter.adapter_id: adapter for adapter in adapters}
        self.assertEqual(len(by_id), len(PUBLIC_SOURCES.sources))
        for item in PUBLIC_SOURCES.sources:
            with self.subTest(source=item.source_id):
                adapter = by_id[item.source_id]
                self.assertIsInstance(adapter, GenericFeedAdapter)
                self.assertEqual(adapter.config.reliability, item.reliability)
                self.assertEqual(
                    adapter.config.minimum_poll_interval_seconds,
                    item.poll_interval_seconds,
                )
                self.assertEqual(adapter.config.source_type, item.kind.value)
                self.assertIn(CONTACT, adapter.config.user_agent)

    def test_an_edgar_source_builds_the_filing_adapter_not_the_generic_one(
        self,
    ) -> None:
        adapters = build_adapters(
            transport=NullTransport(),
            contact_email=CONTACT,
            cik_registry=cik_registry(),
        )

        filings = [
            adapter
            for adapter in adapters
            if isinstance(adapter, SecCurrentFilingsAdapter)
        ]
        self.assertTrue(filings)
        for adapter in filings:
            with self.subTest(adapter=adapter.adapter_id):
                self.assertEqual(adapter.config.allowed_hosts, ("www.sec.gov",))
                self.assertIsNotNone(adapter.cik_registry)


if __name__ == "__main__":
    unittest.main()
