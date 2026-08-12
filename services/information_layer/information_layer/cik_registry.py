"""Map an SEC filer's CIK to the tickers it trades under.

A filing is the highest-reliability evidence this system can get, and without
this mapping it could only be attached to a symbol by looking for the company
name in the text — a guess that misses filings using a legal name and matches
filings that merely mention a competitor.

A CIK is the filer's registered identity, so a match here is exact. Keyword
matches carry whatever relevance their mapping was configured with; these carry
1.0, and the two must not be blurred together.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Mapping


CIK_REGISTRY_VERSION = "sec-company-tickers-v1"

# EDGAR writes the filer's CIK in parentheses after the company name. The
# accession number is also ten digits, so it must be excluded explicitly.
_TITLE_CIK = re.compile(r"\((\d{10})\)")
_URL_CIK = re.compile(r"/data/(\d{1,10})(?:/|$)")
_BARE_CIK = re.compile(r"^\d{1,10}$")


@dataclass(frozen=True, slots=True)
class CikTickerRegistry:
    _by_cik: Mapping[str, tuple[str, ...]]
    version: str = CIK_REGISTRY_VERSION

    @classmethod
    def from_sec_payload(cls, payload: str | bytes) -> "CikTickerRegistry":
        """Parse SEC's company_tickers.json.

        Rejects a malformed payload outright rather than loading what parses.
        A half-loaded registry drops filers silently, and a filing that should
        have been attributed simply never is — with nothing to notice.
        """

        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("SEC ticker payload is not valid JSON") from error
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError("SEC ticker payload must be a non-empty object")

        by_cik: dict[str, set[str]] = {}
        for row in parsed.values():
            if not isinstance(row, dict):
                raise ValueError("SEC ticker rows must be objects")
            cik = row.get("cik_str")
            ticker = row.get("ticker")
            if cik is None or not isinstance(ticker, str) or not ticker.strip():
                raise ValueError("SEC ticker row is missing cik_str or ticker")
            normalized = _normalize(cik)
            if not normalized:
                # Otherwise it lands in an empty-string bucket that every
                # invalid lookup later resolves to.
                raise ValueError(f"SEC ticker row has an unusable cik_str: {cik!r}")
            by_cik.setdefault(normalized, set()).add(ticker.strip().upper())
        return cls(
            _by_cik={key: tuple(sorted(value)) for key, value in by_cik.items()}
        )

    def tickers_for(self, cik: str | int) -> tuple[str, ...]:
        return self._by_cik.get(_normalize(cik), ())

    def symbol_relevance_for(self, cik: str | int) -> tuple[tuple[str, float], ...]:
        return tuple((ticker, 1.0) for ticker in self.tickers_for(cik))

    def resolve_first(
        self, candidates: tuple[str, ...]
    ) -> tuple[str | None, tuple[tuple[str, float], ...]]:
        """Pick the first candidate CIK that is a listed issuer.

        An insider's CIK is never in this registry, so looking a filing's
        candidates up here separates the reporting person from the issuer
        without parsing EDGAR's role labels — which vary by form and year.
        """

        for cik in candidates:
            relevance = self.symbol_relevance_for(cik)
            if relevance:
                return _normalize(cik), relevance
        return None, ()


def extract_cik(title: str, url: str) -> str | None:
    """The single most likely filer CIK, title first."""

    candidates = extract_ciks(title, url)
    return candidates[0] if candidates else None


def extract_ciks(title: str, url: str) -> tuple[str, ...]:
    """Every CIK an EDGAR entry mentions, in the order they should be tried.

    A Form 4 is titled with the reporting person, whose CIK belongs to a human
    being; the issuer's appears only in the archive path. Returning both lets
    the registry decide which one is a listed company.
    """

    found: list[str] = []
    for match in _TITLE_CIK.finditer(title or ""):
        cik = _normalize(match.group(1))
        if cik and cik not in found:
            found.append(cik)
    for match in _URL_CIK.finditer(url or ""):
        cik = _normalize(match.group(1))
        if cik and cik not in found:
            found.append(cik)
    return tuple(found)


def _normalize(cik: str | int) -> str:
    text = str(cik).strip()
    if not _BARE_CIK.match(text):
        return ""
    return text.zfill(10)
