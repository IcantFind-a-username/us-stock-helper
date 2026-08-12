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
            by_cik.setdefault(_normalize(cik), set()).add(ticker.strip().upper())
        return cls(
            _by_cik={key: tuple(sorted(value)) for key, value in by_cik.items()}
        )

    def tickers_for(self, cik: str | int) -> tuple[str, ...]:
        return self._by_cik.get(_normalize(cik), ())

    def symbol_relevance_for(self, cik: str | int) -> tuple[tuple[str, float], ...]:
        return tuple((ticker, 1.0) for ticker in self.tickers_for(cik))


def extract_cik(title: str, url: str) -> str | None:
    """Find the filer's CIK in an EDGAR entry, or report that there is none."""

    match = _TITLE_CIK.search(title or "")
    if match:
        return _normalize(match.group(1))
    match = _URL_CIK.search(url or "")
    if match:
        return _normalize(match.group(1))
    return None


def _normalize(cik: str | int) -> str:
    text = str(cik).strip()
    if not _BARE_CIK.match(text):
        return ""
    return text.zfill(10)
