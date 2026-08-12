from __future__ import annotations

import json
import unittest

from information_layer.cik_registry import (
    CIK_REGISTRY_VERSION,
    CikTickerRegistry,
    extract_cik,
    extract_ciks,
)


SEC_PAYLOAD = json.dumps(
    {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
        "3": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    }
)


class CikRegistryTests(unittest.TestCase):
    def test_registry_maps_a_padded_or_bare_cik_to_its_ticker(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)

        self.assertEqual(registry.tickers_for("0000320193"), ("AAPL",))
        self.assertEqual(registry.tickers_for("320193"), ("AAPL",))
        self.assertEqual(registry.tickers_for(320193), ("AAPL",))
        self.assertEqual(registry.version, CIK_REGISTRY_VERSION)

    def test_one_filer_with_several_share_classes_keeps_all_of_them(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)

        self.assertEqual(registry.tickers_for("1652044"), ("GOOG", "GOOGL"))

    def test_an_unknown_filer_maps_to_nothing_rather_than_a_guess(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)

        self.assertEqual(registry.tickers_for("9999999999"), ())
        self.assertEqual(registry.tickers_for(""), ())
        self.assertEqual(registry.tickers_for("not-a-cik"), ())

    def test_a_malformed_payload_is_rejected_not_partially_loaded(self) -> None:
        # A half-loaded registry silently drops filers, and a filing that
        # should have been attributed just quietly is not.
        for payload in ("[]", "{}", '{"0": {"ticker": "AAPL"}}', "not json"):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    CikTickerRegistry.from_sec_payload(payload)

    def test_relevance_for_a_registry_match_is_exact(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)

        # A CIK is the filer's identity, not a keyword that happened to appear.
        # Anything below 1.0 would put an exact match on the same footing as a
        # text guess.
        self.assertEqual(
            registry.symbol_relevance_for("0000320193"), (("AAPL", 1.0),)
        )
        self.assertEqual(registry.symbol_relevance_for("1652044"),
                         (("GOOG", 1.0), ("GOOGL", 1.0)))
        self.assertEqual(registry.symbol_relevance_for("9999999999"), ())


class InsiderFilingAttributionTests(unittest.TestCase):
    def test_a_form_4_resolves_to_the_issuer_not_the_insider(self) -> None:
        # EDGAR titles a Form 4 with the *reporting person*. Taking that CIK
        # attributes an insider transaction to a natural person, who has no
        # ticker — so the signal is silently lost instead of reaching the
        # stock it is about.
        candidates = extract_ciks(
            "4 - Cook Timothy D (0001214128) (Reporting)",
            "https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/x.htm",
        )

        self.assertIn("0001214128", candidates)
        self.assertIn("0000320193", candidates)

    def test_the_registry_itself_disambiguates_person_from_issuer(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)
        candidates = extract_ciks(
            "4 - Cook Timothy D (0001214128) (Reporting)",
            "https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/x.htm",
        )

        resolved = registry.resolve_first(candidates)

        # A person's CIK never maps to a ticker, so the registry picks the
        # issuer without needing to parse EDGAR's role labels.
        self.assertEqual(resolved, ("0000320193", (("AAPL", 1.0),)))

    def test_resolution_reports_nothing_when_no_candidate_is_listed(self) -> None:
        registry = CikTickerRegistry.from_sec_payload(SEC_PAYLOAD)

        self.assertEqual(
            registry.resolve_first(("0001214128", "0009999999")), (None, ())
        )
        self.assertEqual(registry.resolve_first(()), (None, ()))


class CikExtractionTests(unittest.TestCase):
    def test_cik_is_read_from_an_edgar_title(self) -> None:
        self.assertEqual(
            extract_cik("8-K - Apple Inc. (0000320193)", ""), "0000320193"
        )

    def test_cik_is_read_from_an_archives_url_when_the_title_lacks_it(
        self,
    ) -> None:
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000081/x.htm"

        self.assertEqual(extract_cik("8-K current report", url), "0000320193")

    def test_the_title_wins_over_the_url(self) -> None:
        # The parenthesised CIK names the filer; a URL path can belong to a
        # related entity in combined filings.
        cik = extract_cik(
            "4 - NVIDIA CORP (0001045810)",
            "https://www.sec.gov/Archives/edgar/data/320193/x.htm",
        )

        self.assertEqual(cik, "0001045810")

    def test_text_without_a_cik_yields_none(self) -> None:
        self.assertIsNone(extract_cik("Quarterly report", "https://example.com"))
        self.assertIsNone(extract_cik("", ""))

    def test_an_accession_number_is_not_mistaken_for_a_cik(self) -> None:
        # Accession numbers are ten digits too; matching them would attribute
        # filings to whatever filer shares those leading digits.
        self.assertIsNone(
            extract_cik("8-K filed under 0000320193-26-000081", "")
        )


if __name__ == "__main__":
    unittest.main()
