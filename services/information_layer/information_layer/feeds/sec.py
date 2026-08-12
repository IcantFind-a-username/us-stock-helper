from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlencode

from ..cik_registry import CikTickerRegistry, extract_cik
from ..models import ClaimStatus
from .generic import (
    FeedConfig,
    GenericFeedAdapter,
    KeywordMapping,
    _ParsedEntry,
)
from .http import FeedAccessError, HttpTransport


_ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")


class SecCurrentFilingsAdapter(GenericFeedAdapter):
    def __init__(
        self,
        *,
        form_type: str,
        user_agent: str,
        transport: HttpTransport,
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
                adapter_id=f"sec-current-{clean_form.casefold()}",
                feed_url=f"https://www.sec.gov/cgi-bin/browse-edgar?{query}",
                allowed_hosts=("www.sec.gov",),
                publisher_id="sec-edgar",
                publisher_name="U.S. SEC EDGAR",
                source_type="regulatory_filing",
                reliability=0.99,
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
                minimum_poll_interval_seconds=1.0,
                base_backoff_seconds=1.0,
                max_backoff_seconds=60.0,
            ),
            transport,
        )

    def _claim_key(self, entry: _ParsedEntry) -> str:
        accession = self._accession(entry)
        return f"sec|{accession}" if accession else super()._claim_key(entry)

    def _symbol_relevance(
        self, entry: _ParsedEntry, text: str
    ) -> tuple[tuple[str, float], ...]:
        """Attribute a filing by its filer identity, never by its prose.

        Reading the company name out of the text both misses filings that use
        a legal name and matches filings that merely mention a competitor. A
        filer outside the registry gets no symbol at all rather than a guess.
        """

        cik = extract_cik(entry.title, entry.canonical_url)
        if cik is None or self.cik_registry is None:
            return ()
        return self.cik_registry.symbol_relevance_for(cik)

    def _attributes(self, entry: _ParsedEntry) -> tuple[tuple[str, str], ...]:
        values = list(super()._attributes(entry))
        values.append(("form_type", self.form_type))
        cik = extract_cik(entry.title, entry.canonical_url)
        if cik:
            values.append(("cik", cik))
        accession = self._accession(entry)
        if accession:
            values.append(("accession", accession))
        return tuple(values)

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
    forms: Iterable[str] = ("8-K", "4"),
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
