"""Nasdaq Trader trade-halts feed.

The feed is authoritative for which ticker is halted and why, but its items
carry neither <guid> nor <link>, so the generic RSS parser drops every one of
them. This adapter reads the ndaq:* fields instead, stands in a stable
identity per halt (symbol + halt date + halt time), and points the citation
at Nasdaq Trader's public halts page. A resumption later fills the same
item's resumption fields, which changes its content hash and publishes as a
revision of the original halt rather than a second event.

The feed's own <pubDate> is *not* used for the entry's timestamp. Nasdaq
stamps every item's <pubDate> at midnight Eastern for the halt's date,
regardless of when the halt actually happened -- a halt at 19:50 ET is still
reported as "04:00:00 GMT" (midnight ET) that day. Trusting it would both
backdate every halt by up to ~20 hours (a PIT-honesty problem) and, worse,
made the collector's production 6-hour lookback (DEFAULT_LOOKBACK_SECONDS)
drop every same-day halt for any poll after roughly 06:00 ET: exactly the
regular session, when a halt matters most. The item's own
ndaq:HaltDate/ndaq:HaltTime fields carry the real wall-clock moment in
Eastern time, so the entry's published_at/updated_at are synthesized from
those instead. The same treatment applies to ndaq:ResumptionDate paired with
ndaq:ResumptionTradeTime (falling back to ndaq:ResumptionQuoteTime) when a
resumption has been filled in: updated_at reflects the later of the halt and
the resumption, so a same-day resumption revision is not itself dropped by
the same lookback.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .generic import (
    GenericFeedAdapter,
    _ParsedEntry,
    _child_text,
    _descendants,
)


HALTS_PAGE_URL = "https://www.nasdaqtrader.com/trader.aspx?id=TradeHalts"

_EASTERN = ZoneInfo("America/New_York")


def _parse_eastern_stamp(date_text: str, time_text: str) -> datetime | None:
    """Combine a "MM/DD/YYYY" date and "HH:MM:SS[.ffffff]" time -- both
    naive, both Eastern, as the feed writes HaltDate/HaltTime and
    ResumptionDate/Resumption*Time -- into an aware UTC timestamp.

    zoneinfo resolves the correct UTC offset (EST or EDT) for the given wall
    clock moment, so daylight saving is handled without a manual table.
    Returns None if either field is missing or does not match the feed's
    grammar; callers must not fall back to a different, less trustworthy
    timestamp when that happens.
    """

    date_text = date_text.strip()
    time_text = time_text.strip()
    if not date_text or not time_text:
        return None
    try:
        date_part = datetime.strptime(date_text, "%m/%d/%Y")
    except ValueError:
        return None
    time_part = None
    for time_format in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            time_part = datetime.strptime(time_text, time_format)
            break
        except ValueError:
            continue
    if time_part is None:
        return None
    naive = date_part.replace(
        hour=time_part.hour,
        minute=time_part.minute,
        second=time_part.second,
        microsecond=time_part.microsecond,
    )
    return naive.replace(tzinfo=_EASTERN).astimezone(timezone.utc)


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
            issue_name = _child_text(node, "IssueName").strip()
            market = _child_text(node, "Market").strip()
            reason_code = _child_text(node, "ReasonCode").strip()
            halt_date = _child_text(node, "HaltDate").strip()
            halt_time = _child_text(node, "HaltTime").strip()
            resumption_date = _child_text(node, "ResumptionDate").strip()
            resumption_quote = _child_text(node, "ResumptionQuoteTime").strip()
            resumption_trade = _child_text(node, "ResumptionTradeTime").strip()

            # The halt moment, not <pubDate> (see module docstring): the feed
            # stamps <pubDate> at midnight ET for every item, which both
            # backdates the halt and drops it from the collector's 6-hour
            # production lookback.
            halt_at = _parse_eastern_stamp(halt_date, halt_time)
            if not symbol or halt_at is None:
                # An item that names no ticker, or whose halt moment cannot
                # be honestly parsed from HaltDate/HaltTime, states nothing
                # this adapter could attribute or order in time -- it is
                # dropped rather than falling back to the unreliable
                # <pubDate>.
                continue
            published_at = halt_at
            # A resumption fills the same item's resumption fields later and
            # changes its content hash (see module docstring), so the item's
            # updated_at should track the later of the two real moments, not
            # stay pinned to the original halt. Resumption trade time is
            # preferred over quote time as the more definitive "resumed"
            # moment; either is used only if it parses and is not earlier
            # than the halt itself.
            resumed_at = _parse_eastern_stamp(
                resumption_date, resumption_trade
            ) or _parse_eastern_stamp(resumption_date, resumption_quote)
            updated_at = (
                resumed_at
                if resumed_at is not None and resumed_at > halt_at
                else halt_at
            )

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
                    updated_at=updated_at,
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
