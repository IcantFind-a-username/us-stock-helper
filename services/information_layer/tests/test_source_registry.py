from __future__ import annotations

import re
import unittest
from pathlib import Path

from information_layer import ClaimStatus
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
    contact_email_from_environment,
    minimum_poll_interval_seconds,
    user_agent_for,
)


CONTACT = "ops@example.test"


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

    def test_every_declared_source_becomes_an_adapter_carrying_its_terms(
        self,
    ) -> None:
        adapters = build_adapters(
            transport=NullTransport(),
            contact_email=CONTACT,
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


if __name__ == "__main__":
    unittest.main()
