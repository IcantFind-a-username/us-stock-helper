"""Nasdaq Trader trade-halts feed.

The feed is authoritative for which ticker is halted and why, but its items
carry neither <guid> nor <link>, so the generic RSS parser drops every one of
them. This adapter reads the ndaq:* fields instead, stands in a stable
identity per halt (symbol + halt date + halt time), and points the citation
at Nasdaq Trader's public halts page. A resumption later fills the same
item's resumption fields, which changes its content hash and publishes as a
revision of the original halt rather than a second event.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .generic import (
    GenericFeedAdapter,
    _ParsedEntry,
    _child_text,
    _descendants,
    _parse_timestamp,
)


HALTS_PAGE_URL = "https://www.nasdaqtrader.com/trader.aspx?id=TradeHalts"


@dataclass(frozen=True, slots=True)
class _HaltEntry(_ParsedEntry):
    symbol: str = ""
    issue_name: str = ""
    market: str = ""
    reason_code: str = ""
    halt_date: str = ""
    halt_time: str = ""
    resumption_date: str = ""
    resumption_quote_time: str = ""
    resumption_trade_time: str = ""


class NasdaqHaltsAdapter(GenericFeedAdapter):
    def _parse_rss(self, root: ET.Element) -> tuple[_ParsedEntry, ...]:
        entries: list[_ParsedEntry] = []
        for node in _descendants(root, "item"):
            symbol = _child_text(node, "IssueSymbol").strip().upper()
            published_text = _child_text(node, "pubDate")
            published_at = _parse_timestamp(published_text)
            if not symbol or published_at is None:
                # An item that names no ticker or no moment states nothing
                # this adapter could honestly attribute or order in time.
                continue
            issue_name = _child_text(node, "IssueName").strip()
            market = _child_text(node, "Market").strip()
            reason_code = _child_text(node, "ReasonCode").strip()
            halt_date = _child_text(node, "HaltDate").strip()
            halt_time = _child_text(node, "HaltTime").strip()
            resumption_date = _child_text(node, "ResumptionDate").strip()
            resumption_quote = _child_text(node, "ResumptionQuoteTime").strip()
            resumption_trade = _child_text(node, "ResumptionTradeTime").strip()

            title = f"Trading halt: {symbol}"
            if issue_name:
                title += f" — {issue_name}"
            if reason_code:
                title += f" ({reason_code})"
            summary = (
                f"Halted {halt_date} {halt_time} ET"
                f"{f' on {market}' if market else ''}"
                f"{f', reason code {reason_code}' if reason_code else ''}."
            )
            if resumption_trade or resumption_quote or resumption_date:
                summary += (
                    " Resumption:"
                    f"{f' {resumption_date}' if resumption_date else ''}"
                    f"{f' quote {resumption_quote}' if resumption_quote else ''}"
                    f"{f' trade {resumption_trade}' if resumption_trade else ''}."
                )
            entries.append(
                _HaltEntry(
                    identity=f"nasdaq-halt|{symbol}|{halt_date}|{halt_time}",
                    title=title,
                    summary=summary,
                    canonical_url=HALTS_PAGE_URL,
                    published_at=published_at,
                    updated_at=published_at,
                    symbol=symbol,
                    issue_name=issue_name,
                    market=market,
                    reason_code=reason_code,
                    halt_date=halt_date,
                    halt_time=halt_time,
                    resumption_date=resumption_date,
                    resumption_quote_time=resumption_quote,
                    resumption_trade_time=resumption_trade,
                )
            )
        return tuple(entries)

    def _claim_key(self, entry: _ParsedEntry) -> str:
        if isinstance(entry, _HaltEntry):
            return f"halt|{entry.identity}"
        return super()._claim_key(entry)

    def _sentiment_text(self, entry: _ParsedEntry) -> str:
        """A halt notice is exchange metadata, not prose to be scored."""

        return ""

    def _symbol_relevance(
        self, entry: _ParsedEntry, text: str
    ) -> tuple[tuple[str, float], ...]:
        if isinstance(entry, _HaltEntry):
            # The exchange names the halted issue itself; this is as exact
            # as a CIK match, not a keyword guess.
            return ((entry.symbol, 1.0),)
        return super()._symbol_relevance(entry, text)

    def _attributes(self, entry: _ParsedEntry) -> tuple[tuple[str, str], ...]:
        values = list(super()._attributes(entry))
        if isinstance(entry, _HaltEntry):
            values.append(("halt_symbol", entry.symbol))
            for key, value in (
                ("issue_name", entry.issue_name),
                ("market", entry.market),
                ("reason_code", entry.reason_code),
                ("halt_date", entry.halt_date),
                ("halt_time", entry.halt_time),
                ("resumption_date", entry.resumption_date),
                ("resumption_quote_time", entry.resumption_quote_time),
                ("resumption_trade_time", entry.resumption_trade_time),
            ):
                if value:
                    values.append((key, value))
        return tuple(values)
