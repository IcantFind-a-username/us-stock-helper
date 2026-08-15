"""Company financial health from SEC XBRL company facts.

This is the one missing factor with a free, primary, machine-readable source
behind it: every US issuer tags its own financial statements in XBRL, and SEC
republishes them at ``data.sec.gov`` with the accession and filing date of the
document each number came from. Nothing here is estimated, inferred or bought.

Two properties of that source shape the whole module.

The first is that a filing date is a *date*, not a timestamp. EDGAR
disseminates until 22:00 New York time and stamps anything accepted after
17:30 with the next business day, so the only bound that cannot claim
knowledge before the public had it is the end of the dissemination window.
This module therefore treats a filing as public at 22:00 ET on its filing
date, which costs at most one session of timeliness on a quarterly factor and
removes the possibility of a look-ahead entirely.

The second is that a period is reported more than once: a quarter appears in
its own 10-Q and again as the comparative in next year's. Both are real, and
which one was in force depends on when you ask. The selection here is
therefore point-in-time twice over — only facts already filed at the cutoff
are visible, and among those the latest filing for a period wins.

Method version: ``sec-xbrl-fundamentals-v1``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Mapping, Sequence

from ..feeds.http import (
    FeedError,
    HttpRequest,
    HttpResponse,
    HttpTransport,
)
from .base import (
    FACTOR_FUNDAMENTALS,
    FactorInput,
    FactorReading,
    FactorUnavailable,
    clamp_unit,
)


SEC_FUNDAMENTALS_METHOD_VERSION = "sec-xbrl-fundamentals-v1"

_HOST = "data.sec.gov"
# The whole fact set in one request, rather than one request per concept.
# That costs several megabytes, and it is not an optimisation trade: the
# per-concept endpoint answers 200 with "units": {"USD": {}} for filers whose
# facts are plainly present here — Coca-Cola on every tag this factor reads,
# Ford on its revenue tag — so reading per concept silently reported blue
# chips as having filed nothing. One complete source cannot disagree with
# itself, and one request is easier on SEC than six.
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# SEC asks for no more than ten requests a second and for a User-Agent naming
# a contact address. A floor between requests is cheaper than being blocked,
# and a blocked client reports "no fundamentals" for reasons that have nothing
# to do with the company.
_DEFAULT_REQUEST_INTERVAL_SECONDS = 0.15
_TIMEOUT_SECONDS = 60.0
# The largest fact sets among big filers run to eight megabytes today and only
# grow. The cap exists to bound memory, not to filter, so it is set well clear
# of that rather than at it: a company that outgrows the limit would otherwise
# lose its fundamentals with no signal that size was the reason.
_MAX_RESPONSE_BYTES = 32_000_000

# A quarter as filers actually report it: thirteen weeks, give or take the
# 52/53-week fiscal calendars that retailers and Apple use.
_MINIMUM_QUARTER_DAYS = 80
_MAXIMUM_QUARTER_DAYS = 100
# How far from exactly a year earlier a comparison quarter may sit. A
# 52/53-week calendar shifts period ends by up to a week each year.
_YEAR_OVER_YEAR_TOLERANCE_DAYS = 20
# A 10-Q is due within 45 days of its own quarter end, so a bound of "45 days
# past the newest quarter" looks safe — except fiscal Q4 never gets its own
# quarterly duration: the 10-K carries only the full-year span, which
# _parse_fact rejects as not a quarter. So after a Q3 10-Q, the next
# quarterly datum is next year's Q1 - a full extra quarter away - before that
# quarter's own 45-day filing deadline even starts running. Budgeting for two
# quarters at this module's own maximum quarter length plus that deadline
# covers the structural gap every calendar-year filer goes through each
# spring, while still catching a filer that has genuinely gone quiet.
_STALE_AFTER_DAYS = 2 * _MAXIMUM_QUARTER_DAYS + 45

# Scales convert a percentage into the [-1, 1] the scorer expects. They are
# the modelling choice in this module and are versioned with it: 20% revenue
# growth, a 5 point margin move, or 30% earnings growth each read as a full
# strength signal.
_REVENUE_GROWTH_SCALE = 0.20
_MARGIN_DELTA_SCALE = 0.05
_EPS_GROWTH_SCALE = 0.30

_USD = "USD"
_USD_PER_SHARE = "USD/shares"


@dataclass(frozen=True, slots=True)
class _Measure:
    """One line of the income statement and the tags filers report it under.

    Candidates are chosen between, never merged. Two tags can cover
    differently-scoped totals, and stitching a current quarter from one onto a
    year-earlier quarter from another would compute growth between two
    different definitions of the same word.
    """

    label: str
    candidates: tuple[tuple[str, str], ...]


_REVENUE = _Measure(
    "revenue",
    (
        ("RevenueFromContractWithCustomerExcludingAssessedTax", _USD),
        ("Revenues", _USD),
        ("SalesRevenueNet", _USD),
    ),
)
_GROSS_PROFIT = _Measure("gross_profit", (("GrossProfit", _USD),))
_EARNINGS = _Measure(
    "diluted_eps",
    (
        ("EarningsPerShareDiluted", _USD_PER_SHARE),
        ("EarningsPerShareBasicAndDiluted", _USD_PER_SHARE),
    ),
)


def edgar_available_at(filed: date) -> datetime:
    """The earliest moment a filing stamped with this date was certainly public.

    EDGAR accepts filings from 06:00 to 22:00 ET and gives anything after
    17:30 the next business day's date, so a document dated D was disseminated
    somewhere inside a window that closes at 22:00 ET on D. 03:00 UTC the
    following day is 22:00 ET in winter and 23:00 ET in summer — never earlier
    than the close of that window under either offset, which is what makes it
    safe without a timezone database.
    """

    return datetime(
        filed.year, filed.month, filed.day, tzinfo=timezone.utc
    ) + timedelta(days=1, hours=3)


class _SourceUnreachable(Exception):
    pass


class _SourceMalformed(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _Fact:
    start: date
    end: date
    value: float
    filed: date
    accession: str
    source_url: str

    @property
    def available_at(self) -> datetime:
        return edgar_available_at(self.filed)


@dataclass(frozen=True, slots=True)
class _SubSignal:
    name: str
    value: float
    detail: str
    inputs: tuple[FactorInput, ...]


class SecXbrlFundamentalsFactor:
    def __init__(
        self,
        *,
        transport: HttpTransport,
        user_agent: str,
        taxonomy: str = "us-gaap",
        minimum_request_interval_seconds: float = _DEFAULT_REQUEST_INTERVAL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        # SEC states plainly that it blocks clients it cannot identify. A
        # deployment that starts without a contact address would look healthy
        # and quietly report no fundamentals for anything.
        if "@" not in user_agent or " " not in user_agent.strip():
            raise _contact_required()
        if minimum_request_interval_seconds < 0:
            raise ValueError("request interval cannot be negative")
        self._transport = transport
        self._user_agent = user_agent
        self._taxonomy = taxonomy
        self._interval = float(minimum_request_interval_seconds)
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def reading(self, *, cik: str | int, as_of: datetime) -> FactorReading:
        normalized = str(cik).strip().zfill(10)
        url = _COMPANY_FACTS_URL.format(cik=normalized)
        try:
            taxonomy, published_taxonomies = self._company_facts(normalized)
            revenue = _select(taxonomy, _REVENUE, as_of, url)
            gross_profit = _select(taxonomy, _GROSS_PROFIT, as_of, url)
            eps = _select(taxonomy, _EARNINGS, as_of, url)
        except _SourceUnreachable as error:
            return self._unavailable(
                as_of,
                FactorUnavailable.SOURCE_UNREACHABLE,
                f"SEC company facts could not be read: {error}.",
            )
        except _SourceMalformed as error:
            return self._unavailable(
                as_of,
                FactorUnavailable.SOURCE_MALFORMED,
                f"SEC company facts were not in the expected shape: {error}.",
            )

        # The period being measured is the newest one *any* measure reaches,
        # not the newest one a chosen measure reaches. JPMorgan's last tagged
        # Revenues quarter is from 2014 while its diluted EPS is current:
        # letting revenue nominate the period declared the whole company
        # stale and discarded the one measure that still works.
        known_ends = set(revenue) | set(gross_profit) | set(eps)
        if not known_ends:
            return self._unavailable(
                as_of,
                FactorUnavailable.NO_DATA_AT_CUTOFF,
                self._nothing_readable(published_taxonomies),
            )

        current_end = max(known_ends)
        if (as_of.date() - current_end).days > _STALE_AFTER_DAYS:
            return self._unavailable(
                as_of,
                FactorUnavailable.STALE_BEYOND_WINDOW,
                f"The newest quarter on file ended {current_end.isoformat()}, "
                f"more than {_STALE_AFTER_DAYS} days before the cutoff. That "
                "bound already covers the structural gap a fiscal Q4 leaves "
                "(no quarterly filing covers Q4 itself, so the wait between a "
                "Q3 10-Q and the next quarterly data point is a full extra "
                "quarter), so this describes a company that has stopped "
                "reporting rather than one still inside its normal filing "
                "calendar.",
            )
        prior_end = _year_earlier(current_end, known_ends)
        if prior_end is None:
            return self._unavailable(
                as_of,
                FactorUnavailable.INSUFFICIENT_HISTORY,
                f"No quarter a year before {current_end.isoformat()} had been "
                "filed at the cutoff, so no year-over-year comparison exists. "
                "A quarter-over-quarter change would be a different, "
                "seasonally distorted measurement, not a substitute.",
            )

        signals = [
            signal
            for signal in (
                _revenue_growth(revenue, current_end, prior_end),
                _margin_change(revenue, gross_profit, current_end, prior_end),
                _earnings_growth(eps, current_end, prior_end),
            )
            if signal is not None
        ]
        if not signals:
            return self._unavailable(
                as_of,
                FactorUnavailable.INSUFFICIENT_HISTORY,
                f"Both {prior_end.isoformat()} and {current_end.isoformat()} "
                "are on file, but no measure could be compared across them.",
            )

        value = sum(signal.value for signal in signals) / len(signals)
        return FactorReading.measured(
            factor=FACTOR_FUNDAMENTALS,
            method_version=SEC_FUNDAMENTALS_METHOD_VERSION,
            as_of=as_of,
            value=clamp_unit(value),
            detail=(
                f"Quarter ending {current_end.isoformat()} against "
                f"{prior_end.isoformat()}: "
                + "; ".join(signal.detail for signal in signals)
                + "."
            ),
            inputs=tuple(
                item for signal in signals for item in signal.inputs
            ),
        )

    def _nothing_readable(self, published_taxonomies: tuple[str, ...]) -> str:
        """Say which of the three ways this filer is unreadable applies.

        All three end in no number, but they send an operator to three
        different places: a wrong CIK, a foreign filer, and an annual-only
        filer are not one problem with one fix.
        """

        if not published_taxonomies:
            return (
                "EDGAR publishes no XBRL facts for this filer at all, so there "
                "are no financials to read."
            )
        if self._taxonomy not in published_taxonomies:
            listed = ", ".join(published_taxonomies)
            return (
                f"This filer publishes no {self._taxonomy} facts; EDGAR carries "
                f"only {listed}. Foreign private issuers report under IFRS, "
                "which this method version does not read."
            )
        return (
            f"This filer publishes {self._taxonomy} facts, but none of them "
            "covers a quarter — an annual-only filer such as a 20-F reporter "
            "has nothing for a year-over-year quarterly comparison."
        )

    def _unavailable(
        self, as_of: datetime, reason: FactorUnavailable, detail: str
    ) -> FactorReading:
        return FactorReading.unavailable(
            factor=FACTOR_FUNDAMENTALS,
            method_version=SEC_FUNDAMENTALS_METHOD_VERSION,
            as_of=as_of,
            reason=reason,
            detail=detail,
        )

    def _company_facts(
        self, cik: str
    ) -> tuple[Mapping[str, object], tuple[str, ...]]:
        url = _COMPANY_FACTS_URL.format(cik=cik)
        response = self._get(url)
        if response.status_code == 404:
            # EDGAR has no XBRL facts for this filer at all — a trust, a fund,
            # or a company that predates the mandate.
            return {}, ()
        if response.status_code != 200:
            raise _SourceUnreachable(f"{url} answered {response.status_code}")
        try:
            payload = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise _SourceMalformed(f"{url} is not JSON") from error
        if not isinstance(payload, dict):
            raise _SourceMalformed(f"{url} is not a JSON object")
        facts = payload.get("facts")
        if not isinstance(facts, dict):
            raise _SourceMalformed(f"{url} carries no fact set")
        taxonomy = facts.get(self._taxonomy)
        # A foreign private issuer files under ifrs-full and simply has no
        # us-gaap section. That is a company this factor cannot read, not a
        # broken download, and the difference matters to whoever is paged —
        # so the taxonomies that *are* present travel back with the answer.
        return (
            taxonomy if isinstance(taxonomy, dict) else {},
            tuple(sorted(str(name) for name in facts)),
        )

    def _get(self, url: str) -> HttpResponse:
        self._throttle()
        request = HttpRequest(
            url=url,
            allowed_hosts=(_HOST,),
            headers=(
                ("User-Agent", self._user_agent),
                ("Accept", "application/json"),
            ),
            timeout_seconds=_TIMEOUT_SECONDS,
            max_response_bytes=_MAX_RESPONSE_BYTES,
        )
        try:
            return self._transport.request(request)
        except (FeedError, OSError, ValueError) as error:
            raise _SourceUnreachable(str(error) or type(error).__name__) from error

    def _throttle(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()


def _contact_required() -> Exception:
    from ..feeds.http import FeedAccessError

    return FeedAccessError(
        "SEC serves only clients whose User-Agent names the application and a "
        "contact email address"
    )


def _select(
    taxonomy: Mapping[str, object],
    measure: _Measure,
    as_of: datetime,
    source_url: str,
) -> dict[date, _Fact]:
    """The tag for this measure that the filer is using *now*, point-in-time.

    Issuers pick different tags for the same line — a bank's revenue may be
    ``Revenues`` while a device maker uses the contract-revenue tag — so a
    single tag would silently blank whole sectors. They also change tag over
    time and the old series stays published: NVIDIA stopped tagging revenue as
    ``RevenueFromContractWithCustomer...`` in 2020 and those sixteen quarters
    are still served. Taking the first candidate with any data therefore
    scored NVIDIA on its January 2020 quarter, so the winner is the candidate
    reaching furthest forward, with the declared order breaking ties.
    """

    best: dict[date, _Fact] = {}
    best_end: date | None = None
    for tag, unit in measure.candidates:
        rows = _rows_for(taxonomy, tag, unit)
        if not rows:
            continue
        quarters = _quarterly_by_end(rows, as_of, source_url)
        if not quarters:
            continue
        newest = max(quarters)
        if best_end is None or newest > best_end:
            best, best_end = quarters, newest
    return best


def _rows_for(
    taxonomy: Mapping[str, object], tag: str, unit: str
) -> list[Mapping[str, object]]:
    entry = taxonomy.get(tag)
    if not isinstance(entry, dict):
        return []
    units = entry.get("units")
    if not isinstance(units, dict):
        return []
    rows = units.get(unit)
    if not isinstance(rows, list):
        # SEC serialises an empty series as {} rather than []. A filer
        # reporting the tag in another unit — a foreign currency, or the
        # "pure" unit some filers mistakenly use for EPS — lands here too, and
        # in both cases there is nothing to read rather than something broken.
        return []
    return [row for row in rows if isinstance(row, dict)]


def _quarterly_by_end(
    rows: Sequence[Mapping[str, object]],
    as_of: datetime,
    source_url: str,
) -> dict[date, _Fact]:
    """Quarters visible at the cutoff, one winning fact per period end.

    Keyed by period end rather than by (start, end) so the same quarter can be
    matched across concepts whose start dates differ, and reduced to the
    latest filing for that period because a restatement supersedes what it
    restates — but only if it had itself been filed by the cutoff.
    """

    best: dict[date, _Fact] = {}
    for row in rows:
        fact = _parse_fact(row, source_url)
        if fact is None:
            continue
        if fact.available_at > as_of:
            continue
        incumbent = best.get(fact.end)
        if incumbent is None or (fact.filed, fact.accession) > (
            incumbent.filed,
            incumbent.accession,
        ):
            best[fact.end] = fact
    return best


def _parse_fact(
    row: Mapping[str, object], source_url: str
) -> _Fact | None:
    start = _as_date(row.get("start"))
    end = _as_date(row.get("end"))
    filed = _as_date(row.get("filed"))
    raw_value = row.get("val")
    if start is None or end is None or filed is None:
        # An instant fact (a balance-sheet item) has no start; it is simply
        # not a quarterly flow and belongs to no period this factor measures.
        return None
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        return None
    span = (end - start).days
    if not _MINIMUM_QUARTER_DAYS <= span <= _MAXIMUM_QUARTER_DAYS:
        # Year-to-date and full-year durations live in the same array. Mixing
        # them into a quarterly comparison is how a 10-K makes a company look
        # like it quadrupled.
        return None
    accession = row.get("accn")
    return _Fact(
        start=start,
        end=end,
        value=float(raw_value),
        filed=filed,
        accession=accession if isinstance(accession, str) else "",
        source_url=source_url,
    )


def _as_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _year_earlier(
    current_end: date, known_ends: Iterable[date]
) -> date | None:
    target = current_end - timedelta(days=365)
    candidates = [
        end
        for end in known_ends
        if end != current_end
        and abs((end - target).days) <= _YEAR_OVER_YEAR_TOLERANCE_DAYS
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda end: (abs((end - target).days), end))


def _factor_input(name: str, fact: _Fact) -> FactorInput:
    return FactorInput(
        name=name,
        value=fact.value,
        observed_at=datetime(
            fact.end.year, fact.end.month, fact.end.day, tzinfo=timezone.utc
        ),
        available_at=fact.available_at,
        source_url=fact.source_url,
    )


def _span_days(fact: _Fact) -> int:
    return (fact.end - fact.start).days


def _comparability_note(current: _Fact, prior: _Fact) -> str:
    """State it when a ratio was computed per-day rather than raw.

    A 52/53-week fiscal calendar shifts a quarter's own length by up to a
    week, and an extra week of revenue reads as organic growth if the two
    periods are ratioed as filed. Normalizing to a daily rate before ratioing
    removes that artifact silently unless the reader is told the periods
    being compared were not the same length.
    """

    current_span = _span_days(current)
    prior_span = _span_days(prior)
    if current_span == prior_span:
        return ""
    return (
        f" (normalized to a daily rate: the compared quarters span "
        f"{current_span} and {prior_span} days)"
    )


def _revenue_growth(
    revenue: Mapping[date, _Fact], current_end: date, prior_end: date
) -> _SubSignal | None:
    current = revenue.get(current_end)
    prior = revenue.get(prior_end)
    if current is None or prior is None:
        return None
    # Ratioed as filed, an extra week in one period is counted twice: once as
    # more dollars and again as a faster growth rate. Ratioing the per-day
    # rate instead cancels a span difference and is a no-op when the two
    # periods already span the same number of days.
    current_rate = current.value / _span_days(current)
    prior_rate = prior.value / _span_days(prior)
    if prior_rate <= 0:
        # A non-positive base makes a growth ratio meaningless rather than
        # extreme, and an extreme number here would dominate the average.
        return None
    growth = current_rate / prior_rate - 1.0
    return _SubSignal(
        name="revenue_growth",
        value=clamp_unit(growth / _REVENUE_GROWTH_SCALE),
        detail=f"revenue {growth:+.1%} year over year"
        + _comparability_note(current, prior),
        inputs=(
            _factor_input("revenue_current", current),
            _factor_input("revenue_prior", prior),
        ),
    )


def _margin_change(
    revenue: Mapping[date, _Fact],
    gross_profit: Mapping[date, _Fact],
    current_end: date,
    prior_end: date,
) -> _SubSignal | None:
    parts = [
        revenue.get(current_end),
        revenue.get(prior_end),
        gross_profit.get(current_end),
        gross_profit.get(prior_end),
    ]
    if any(part is None for part in parts):
        return None
    current_revenue, prior_revenue, current_profit, prior_profit = parts
    assert current_revenue and prior_revenue and current_profit and prior_profit
    if current_revenue.value <= 0 or prior_revenue.value <= 0:
        return None
    delta = (
        current_profit.value / current_revenue.value
        - prior_profit.value / prior_revenue.value
    )
    return _SubSignal(
        name="gross_margin_change",
        value=clamp_unit(delta / _MARGIN_DELTA_SCALE),
        detail=f"gross margin {delta * 100:+.1f} points year over year",
        inputs=(
            _factor_input("gross_profit_current", current_profit),
            _factor_input("gross_profit_prior", prior_profit),
        ),
    )


def _earnings_growth(
    eps: Mapping[date, _Fact], current_end: date, prior_end: date
) -> _SubSignal | None:
    current = eps.get(current_end)
    prior = eps.get(prior_end)
    if current is None or prior is None:
        return None
    # Diluted EPS is a period flow like revenue, so the same extra-week
    # artifact applies: ratio the per-day rate, not the value as filed.
    current_rate = current.value / _span_days(current)
    prior_rate = prior.value / _span_days(prior)
    if prior_rate > 0:
        growth = current_rate / prior_rate - 1.0
        value = clamp_unit(growth / _EPS_GROWTH_SCALE)
        detail = f"diluted EPS {growth:+.1%} year over year" + _comparability_note(
            current, prior
        )
    elif current_rate > 0:
        # Crossing from a loss into a profit is real information, but it has
        # no percentage: any denominator here would be invented.
        value = 1.0
        detail = "diluted EPS turned positive from a year-earlier loss"
    else:
        # Loss to loss. Which loss is worse is a judgement this version does
        # not make, and scoring it zero would call it neutral.
        return None
    return _SubSignal(
        name="earnings_growth",
        value=value,
        detail=detail,
        inputs=(
            _factor_input("diluted_eps_current", current),
            _factor_input("diluted_eps_prior", prior),
        ),
    )
