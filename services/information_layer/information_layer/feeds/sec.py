from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlencode

from ..cik_registry import (
    CikTickerRegistry,
    extract_ciks,
    filer_role,
    role_attributes_symbol,
)
from ..models import ClaimStatus
from .generic import (
    FeedConfig,
    GenericFeedAdapter,
    KeywordMapping,
    _ParsedEntry,
)
from .http import FeedAccessError, HttpTransport


_ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")
# EDGAR titles begin with the actual form type: "424B2 - LEGAL NAME (...)".
# A form code may itself contain spaces ("SCHEDULE 13D/A - HOLDER (...)"), so
# the token walks word by word and stops, lazily, at the first " - "
# separator — greedily it would swallow a legal name containing " - ".
_TITLE_FORM = re.compile(
    r"^\s*([A-Z0-9][A-Z0-9./-]*(?:\s[A-Z0-9][A-Z0-9./-]*)*?)\s+-\s",
    re.IGNORECASE,
)

# The current-filings feeds production polls, one per form that moves prices.
# Captured EDGAR responses (tests/fixtures/sec_current_*.atom, 2026-08-16) are
# the authority for these codes: beneficial ownership is served as
# "SCHEDULE 13D"/"SCHEDULE 13G", and the retired "SC 13D"/"SC 13G" queries
# answer "No recent filings".
CURRENT_FILING_FORMS = (
    "8-K",
    "4",
    "10-Q",
    "10-K",
    "SCHEDULE 13D",
    "SCHEDULE 13G",
)


def sec_current_source_id(form_type: str) -> str:
    """The one identifier a form's adapter and its registry entry share.

    Multi-word forms would otherwise put a space into an id that keys
    coordinator state and registry lookups.
    """

    return f"sec-current-{form_type.strip().casefold().replace(' ', '-')}"


class SecCurrentFilingsAdapter(GenericFeedAdapter):
    def __init__(
        self,
        *,
        form_type: str,
        user_agent: str,
        transport: HttpTransport,
        reliability: float = 0.99,
        minimum_poll_interval_seconds: float = 1.0,
        symbol_mappings: tuple[KeywordMapping, ...] = (),
        entity_mappings: tuple[KeywordMapping, ...] = (),
        macro_mappings: tuple[KeywordMapping, ...] = (),
        geopolitical_mappings: tuple[KeywordMapping, ...] = (),
        cik_registry: CikTickerRegistry | None = None,
    ) -> None:
        clean_form = form_type.strip().upper()
        if not clean_form:
            raise ValueError("SEC form_type is required")
        if "@" not in user_agent or " " not in user_agent.strip():
            raise FeedAccessError(
                "SEC User-Agent must identify the application and contact email"
            )
        self.form_type = clean_form
        self.cik_registry = cik_registry
        query = urlencode(
            {
                "action": "getcurrent",
                "type": clean_form,
                "company": "",
                "dateb": "",
                "owner": "include",
                "start": "0",
                "count": "100",
                "output": "atom",
            }
        )
        super().__init__(
            FeedConfig(
                adapter_id=sec_current_source_id(clean_form),
                feed_url=f"https://www.sec.gov/cgi-bin/browse-edgar?{query}",
                allowed_hosts=("www.sec.gov",),
                publisher_id="sec-edgar",
                publisher_name="U.S. SEC EDGAR",
                source_type="regulatory_filing",
                reliability=reliability,
                user_agent=user_agent,
                timeout_seconds=10.0,
                max_response_bytes=2_000_000,
                summary_max_chars=400,
                symbol_mappings=symbol_mappings,
                entity_mappings=entity_mappings,
                macro_mappings=macro_mappings,
                geopolitical_mappings=geopolitical_mappings,
                claim_status=ClaimStatus.VERIFIED,
                robots_allowed=True,
                minimum_poll_interval_seconds=minimum_poll_interval_seconds,
                base_backoff_seconds=1.0,
                max_backoff_seconds=60.0,
            ),
            transport,
        )

    def _claim_key(self, entry: _ParsedEntry) -> str:
        accession = self._accession(entry)
        return f"sec|{accession}" if accession else super()._claim_key(entry)

    def _sentiment_text(self, entry: _ParsedEntry) -> str:
        """A filing entry is metadata, not prose.

        EDGAR titles read "8-K - LEGAL NAME (0001234567) (Filer)". Words like
        strong, growth and record occur in company names, so reading them as
        sentiment gave every filing from such an issuer a bullish vote — and
        CIK attribution then delivered it precisely to that ticker. What the
        filing means is in the document, which this feed does not carry.
        """

        return ""

    def _symbol_relevance(
        self, entry: _ParsedEntry, text: str
    ) -> tuple[tuple[str, float], ...]:
        """Attribute a filing by its filer identity, never by its prose.

        Reading the company name out of the text both misses filings that use
        a legal name and matches filings that merely mention a competitor. A
        filer outside the registry gets no symbol at all rather than a guess.
        """

        registry_match = self._resolve_filer(entry)[1]
        if registry_match:
            return registry_match
        # No listed issuer among the candidates: fall back to whatever keyword
        # attribution the caller configured, at its own lower relevance.
        return super()._symbol_relevance(entry, text)

    def _resolve_filer(
        self, entry: _ParsedEntry
    ) -> tuple[str | None, tuple[tuple[str, float], ...]]:
        candidates = extract_ciks(entry.title, entry.canonical_url)
        if not candidates:
            return None, ()
        if not role_attributes_symbol(filer_role(entry.title)):
            # A reporting person is an insider of some other company. Its own
            # CIK may well be listed — corporate ten-percent holders are both
            # — and claiming it would file the trade under the wrong stock.
            # The issuer arrives as its own entry in the same feed.
            return candidates[0], ()
        if self.cik_registry is None:
            return candidates[0], ()
        cik, relevance = self.cik_registry.resolve_first(candidates)
        # With no listed issuer among the candidates, record the filer we saw
        # so the filing is still traceable, but claim no symbol.
        return (cik or candidates[0]), relevance

    def _attributes(self, entry: _ParsedEntry) -> tuple[tuple[str, str], ...]:
        values = list(super()._attributes(entry))
        # browse-edgar matches type= by prefix, so a request for "4" also
        # returns 424B2, 425 and 497K. Record what the entry says it is, not
        # what was asked for, or a prospectus supplement reads as an insider
        # transaction.
        values.append(("form_type", self._entry_form(entry)))
        cik, _ = self._resolve_filer(entry)
        if cik:
            values.append(("cik", cik))
        role = filer_role(entry.title)
        if role:
            values.append(("filer_role", role))
        accession = self._accession(entry)
        if accession:
            values.append(("accession", accession))
        return tuple(values)

    def _entry_form(self, entry: _ParsedEntry) -> str:
        match = _TITLE_FORM.match(entry.title or "")
        return match.group(1).upper() if match else self.form_type

    @staticmethod
    def _accession(entry: _ParsedEntry) -> str | None:
        combined = " ".join(
            (entry.identity, entry.title, entry.summary, entry.canonical_url)
        )
        match = _ACCESSION.search(combined)
        return match.group(0) if match else None


def build_sec_current_filings_adapters(
    *,
    transport: HttpTransport,
    user_agent: str,
    forms: Iterable[str] = CURRENT_FILING_FORMS,
    symbol_mappings: tuple[KeywordMapping, ...] = (),
    entity_mappings: tuple[KeywordMapping, ...] = (),
    macro_mappings: tuple[KeywordMapping, ...] = (),
    geopolitical_mappings: tuple[KeywordMapping, ...] = (),
    cik_registry: CikTickerRegistry | None = None,
) -> tuple[SecCurrentFilingsAdapter, ...]:
    return tuple(
        SecCurrentFilingsAdapter(
            form_type=form,
            user_agent=user_agent,
            transport=transport,
            symbol_mappings=symbol_mappings,
            entity_mappings=entity_mappings,
            macro_mappings=macro_mappings,
            geopolitical_mappings=geopolitical_mappings,
            cik_registry=cik_registry,
        )
        for form in forms
    )
