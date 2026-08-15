from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from information_layer.cik_registry import CikTickerRegistry
from information_layer.factors import FactorReading, FactorUnavailable
from information_layer.factors.provider import (
    FactorSnapshot,
    PublicFactorProvider,
)
from information_layer.factors.unsupported import geopolitics_reading
from information_layer.feeds import HttpRequest, HttpResponse


FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
CONTACT_USER_AGENT = "us-stock-helper/0.1 (ops@example.test)"

TICKER_PAYLOAD = (
    '{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},'
    ' "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}}'
)


class StubFactor:
    def __init__(self, reading: FactorReading) -> None:
        self._reading = reading
        self.calls = 0

    def reading(self, **_kwargs: object) -> FactorReading:
        self.calls += 1
        return self._reading


class ExplodingFactor:
    def reading(self, **_kwargs: object) -> FactorReading:
        raise RuntimeError("a source adapter should never take the chain down")


def measured(factor: str) -> FactorReading:
    return FactorReading.measured(
        factor=factor,
        method_version=f"{factor}-v1",
        as_of=AS_OF,
        value=0.25,
        detail="measured",
        inputs=(
            _input(available_at=datetime(2026, 8, 12, tzinfo=timezone.utc)),
        ),
    )


def _input(**overrides: object):
    from information_layer.factors import FactorInput

    values: dict[str, object] = {
        "name": "example",
        "value": 1.0,
        "observed_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "available_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "source_url": "https://data.sec.gov/example.json",
    }
    values.update(overrides)
    return FactorInput(**values)  # type: ignore[arg-type]


class AbstentionTests(unittest.TestCase):
    def test_geopolitics_abstains_and_says_why_in_words(self) -> None:
        reading = geopolitics_reading(as_of=AS_OF)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_QUALIFIED_SOURCE
        )
        self.assertTrue(len(reading.detail.strip()) > 40)

    def test_an_abstention_is_not_a_neutral_opinion(self) -> None:
        reading = geopolitics_reading(as_of=AS_OF)

        self.assertIsNot(reading.value, 0.0)
        self.assertIsNone(reading.value)


class ProviderTests(unittest.TestCase):
    def test_a_snapshot_answers_for_all_three_missing_factors(self) -> None:
        provider = PublicFactorProvider(
            fundamentals=StubFactor(measured("fundamentals")),
            macro=StubFactor(measured("macro")),
            cik_registry=CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD),
        )

        snapshot = provider.snapshot(symbol="AAPL", as_of=AS_OF)

        self.assertIsInstance(snapshot, FactorSnapshot)
        self.assertEqual(snapshot.fundamentals.value, 0.25)
        self.assertEqual(snapshot.macro.value, 0.25)
        self.assertIsNone(snapshot.geopolitics.value)

    def test_one_broken_factor_does_not_take_the_other_down(self) -> None:
        provider = PublicFactorProvider(
            fundamentals=ExplodingFactor(),
            macro=StubFactor(measured("macro")),
            cik_registry=CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD),
        )

        snapshot = provider.snapshot(symbol="AAPL", as_of=AS_OF)

        self.assertIsNone(snapshot.fundamentals.value)
        self.assertEqual(
            snapshot.fundamentals.unavailable_reason,
            FactorUnavailable.SOURCE_UNREACHABLE,
        )
        self.assertEqual(snapshot.macro.value, 0.25)

    def test_an_unknown_symbol_yields_no_fundamentals_and_no_sec_request(
        self,
    ) -> None:
        fundamentals = StubFactor(measured("fundamentals"))
        provider = PublicFactorProvider(
            fundamentals=fundamentals,
            macro=StubFactor(measured("macro")),
            cik_registry=CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD),
        )

        snapshot = provider.snapshot(symbol="ZZZZ", as_of=AS_OF)

        self.assertEqual(fundamentals.calls, 0)
        self.assertIsNone(snapshot.fundamentals.value)
        self.assertEqual(
            snapshot.fundamentals.unavailable_reason,
            FactorUnavailable.NO_QUALIFIED_SOURCE,
        )
        # The macro factor is symbol-independent, so an unmapped ticker must
        # not cost the snapshot its one working factor.
        self.assertEqual(snapshot.macro.value, 0.25)

    def test_the_snapshot_reports_which_factors_are_unavailable_and_why(
        self,
    ) -> None:
        provider = PublicFactorProvider(
            fundamentals=StubFactor(measured("fundamentals")),
            macro=StubFactor(measured("macro")),
            cik_registry=CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD),
        )

        snapshot = provider.snapshot(symbol="AAPL", as_of=AS_OF)

        self.assertEqual(
            dict(snapshot.unavailable_reasons()),
            {
                "geopolitics": FactorUnavailable.NO_QUALIFIED_SOURCE,
            },
        )


class TickerLookupTests(unittest.TestCase):
    def test_the_registry_resolves_a_ticker_back_to_its_filer(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD)

        self.assertEqual(registry.cik_for("aapl"), "0000320193")
        self.assertEqual(registry.cik_for("NVDA"), "0001045810")
        self.assertIsNone(registry.cik_for("ZZZZ"))
        self.assertIsNone(registry.cik_for(""))

    def test_a_ticker_claimed_by_two_filers_resolves_to_neither(self) -> None:
        # Guessing between them would file one company's financials under the
        # other's symbol, which is worse than having no fundamentals factor.
        payload = (
            '{"0": {"cik_str": 320193, "ticker": "DUP", "title": "A"},'
            ' "1": {"cik_str": 1045810, "ticker": "DUP", "title": "B"}}'
        )
        registry = CikTickerRegistry.from_sec_payload(payload)

        self.assertIsNone(registry.cik_for("DUP"))


class TransportGuardTests(unittest.TestCase):
    def test_the_provider_never_performs_io_while_being_built(self) -> None:
        class NullTransport:
            def request(self, request: HttpRequest) -> HttpResponse:
                raise AssertionError("construction must not reach the network")

        from information_layer.factors.fundamentals import (
            SecXbrlFundamentalsFactor,
        )
        from information_layer.factors.macro import (
            TreasuryYieldCurveMacroFactor,
        )

        PublicFactorProvider(
            fundamentals=SecXbrlFundamentalsFactor(
                transport=NullTransport(), user_agent=CONTACT_USER_AGENT
            ),
            macro=TreasuryYieldCurveMacroFactor(transport=NullTransport()),
            cik_registry=CikTickerRegistry.from_sec_payload(TICKER_PAYLOAD),
        )


if __name__ == "__main__":
    unittest.main()
