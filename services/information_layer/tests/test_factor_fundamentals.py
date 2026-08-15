from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from information_layer.factors import FactorUnavailable
from information_layer.factors.fundamentals import (
    SEC_FUNDAMENTALS_METHOD_VERSION,
    SecXbrlFundamentalsFactor,
    edgar_available_at,
)
from information_layer.feeds import (
    FeedAccessError,
    HttpRequest,
    HttpResponse,
    ResponseTooLargeError,
)


FIXTURES = Path(__file__).parent / "fixtures"
CONTACT_USER_AGENT = "us-stock-helper/0.1 (ops@example.test)"

APPLE_CIK = "0000320193"
NVIDIA_CIK = "0001045810"
JPMORGAN_CIK = "0000019617"
COCA_COLA_CIK = "0000021344"
FORD_CIK = "0000037996"

# Apple's FY2026 Q3 10-Q was filed 2026-07-31, so under this module's
# conservative EDGAR dissemination rule it is public from 2026-08-01T03:00Z.
AFTER_Q3 = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
JUST_BEFORE_Q3 = datetime(2026, 8, 1, 2, 59, tzinfo=timezone.utc)

# Every fixture below is a real data.sec.gov companyfacts response captured on
# 2026-08-14, subset to the tags this factor reads and to facts filed since
# 2024-06-01. The values, period boundaries, filing dates and accession
# numbers are untouched.
FIXTURE_FOR_CIK = {
    APPLE_CIK: "sec_aapl_companyfacts.json",
    NVIDIA_CIK: "sec_nvda_companyfacts.json",
    JPMORGAN_CIK: "sec_jpm_companyfacts.json",
    COCA_COLA_CIK: "sec_ko_companyfacts.json",
    FORD_CIK: "sec_ford_companyfacts.json",
}

NOT_FOUND_BODY = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b"<Error><Code>NoSuchKey</Code><Message>The specified key does not "
    b"exist.</Message></Error>"
)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class CompanyFactsTransport:
    def __init__(self, body: bytes | None = None, status: int = 200) -> None:
        self.requests: list[HttpRequest] = []
        self._body = body
        self._status = status

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self._body is not None:
            return self._response(self._status, self._body)
        for cik, name in FIXTURE_FOR_CIK.items():
            if f"CIK{cik}.json" in request.url:
                return self._response(200, fixture(name))
        return self._response(404, NOT_FOUND_BODY)

    def _response(self, status: int, body: bytes) -> HttpResponse:
        return HttpResponse(
            status_code=status,
            headers=(("Content-Type", "application/json"),),
            body=body,
            retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        )


class FailingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.requests: list[HttpRequest] = []

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        raise self._error


def factor(transport: object, **overrides: object) -> SecXbrlFundamentalsFactor:
    values: dict[str, object] = {
        "transport": transport,
        "user_agent": CONTACT_USER_AGENT,
        "sleep": lambda _seconds: None,
    }
    values.update(overrides)
    return SecXbrlFundamentalsFactor(**values)  # type: ignore[arg-type]


def inputs_by_name(reading: object) -> dict[str, object]:
    return {item.name: item for item in reading.inputs}  # type: ignore[attr-defined]


class EdgarAvailabilityTests(unittest.TestCase):
    def test_a_filing_date_becomes_the_end_of_that_day_in_new_york(self) -> None:
        # EDGAR stamps a filing with a date, not a time, and disseminates
        # until 22:00 ET. Taking the end of the window rather than its start
        # is the only choice that cannot claim knowledge before the public
        # had it, and 03:00Z is 22:00 ET even in winter.
        self.assertEqual(
            edgar_available_at(date(2026, 7, 31)),
            datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            edgar_available_at(date(2025, 12, 31)),
            datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc),
        )


class SecAccessTests(unittest.TestCase):
    def test_a_user_agent_without_a_contact_address_is_refused(self) -> None:
        for agent in ("us-stock-helper/0.1", "someone@example.test", ""):
            with self.subTest(agent=agent):
                with self.assertRaises(FeedAccessError):
                    factor(CompanyFactsTransport(), user_agent=agent)

    def test_a_company_costs_exactly_one_request_to_the_facts_endpoint(
        self,
    ) -> None:
        transport = CompanyFactsTransport()
        factor(transport).reading(cik=APPLE_CIK, as_of=AFTER_Q3)

        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(
            request.url,
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json",
        )
        self.assertEqual(request.allowed_hosts, ("data.sec.gov",))
        self.assertEqual(request.header("User-Agent"), CONTACT_USER_AGENT)

    def test_back_to_back_companies_are_spaced_by_the_rate_limit(self) -> None:
        slept: list[float] = []
        transport = CompanyFactsTransport()
        subject = factor(
            transport,
            minimum_request_interval_seconds=0.4,
            sleep=slept.append,
            monotonic=lambda: 100.0,
        )
        subject.reading(cik=APPLE_CIK, as_of=AFTER_Q3)
        subject.reading(cik=NVIDIA_CIK, as_of=AFTER_Q3)

        self.assertEqual(len(transport.requests), 2)
        # The first request has nothing to wait behind; the second does.
        self.assertEqual(slept, [0.4])

    def test_a_request_that_already_waited_long_enough_does_not_sleep(self) -> None:
        slept: list[float] = []
        ticks = iter(float(step) for step in range(0, 200, 5))
        subject = factor(
            CompanyFactsTransport(),
            minimum_request_interval_seconds=0.4,
            sleep=slept.append,
            monotonic=lambda: next(ticks),
        )
        subject.reading(cik=APPLE_CIK, as_of=AFTER_Q3)
        subject.reading(cik=NVIDIA_CIK, as_of=AFTER_Q3)

        self.assertEqual(slept, [])


class FundamentalsMeasurementTests(unittest.TestCase):
    def test_apples_real_filings_produce_a_measured_year_over_year_reading(
        self,
    ) -> None:
        reading = factor(CompanyFactsTransport()).reading(
            cik=APPLE_CIK, as_of=AFTER_Q3
        )

        self.assertEqual(reading.factor, "fundamentals")
        self.assertEqual(reading.method_version, SEC_FUNDAMENTALS_METHOD_VERSION)
        self.assertIsNone(reading.unavailable_reason)
        # Revenue 109_417M vs 94_036M (+16.36%, scaled by 20% -> 0.8178),
        # gross margin 50.06% vs 46.49% (+3.57pp, scaled by 5pp -> 0.7131)
        # and diluted EPS 2.02 vs 1.57 (+28.66%, scaled by 30% -> 0.9554).
        self.assertAlmostEqual(reading.value or 0.0, 0.828780, places=6)
        self.assertEqual(
            reading.available_at,
            datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc),
        )

    def test_the_reading_exposes_the_numbers_it_was_computed_from(self) -> None:
        reading = factor(CompanyFactsTransport()).reading(
            cik=APPLE_CIK, as_of=AFTER_Q3
        )
        by_name = inputs_by_name(reading)

        self.assertEqual(by_name["revenue_current"].value, 109417000000.0)
        self.assertEqual(by_name["revenue_prior"].value, 94036000000.0)
        self.assertEqual(by_name["gross_profit_current"].value, 54770000000.0)
        self.assertEqual(by_name["diluted_eps_current"].value, 2.02)
        self.assertEqual(by_name["diluted_eps_prior"].value, 1.57)
        self.assertEqual(
            by_name["revenue_current"].observed_at.date(), date(2026, 6, 27)
        )
        self.assertEqual(
            by_name["revenue_prior"].observed_at.date(), date(2025, 6, 28)
        )
        for item in reading.inputs:
            self.assertLessEqual(item.available_at, AFTER_Q3)

    def test_a_quarter_is_invisible_until_its_filing_was_disseminated(
        self,
    ) -> None:
        # One minute before the FY2026 Q3 10-Q went out, the newest quarter
        # this system may see is the one filed on 2026-05-01. Reading the Q3
        # numbers here would be a look-ahead worth 16% of revenue growth.
        reading = factor(CompanyFactsTransport()).reading(
            cik=APPLE_CIK, as_of=JUST_BEFORE_Q3
        )
        by_name = inputs_by_name(reading)

        self.assertEqual(
            by_name["revenue_current"].observed_at.date(), date(2026, 3, 28)
        )
        self.assertEqual(by_name["revenue_current"].value, 111184000000.0)

    def test_a_restated_prior_quarter_uses_the_newest_filing_at_the_cutoff(
        self,
    ) -> None:
        # The June 2025 quarter appears twice: in its own 10-Q filed
        # 2025-08-01 and again as the comparative in the 10-Q filed
        # 2026-07-31. After the cutoff the later filing is the one in force.
        reading = factor(CompanyFactsTransport()).reading(
            cik=APPLE_CIK, as_of=AFTER_Q3
        )

        self.assertEqual(
            inputs_by_name(reading)["revenue_prior"].available_at,
            datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc),
        )


class RealFilerShapeTests(unittest.TestCase):
    """Cases found by running this factor against live SEC data, not invented.

    Every one of them passed the unit suite before it was run for real. They
    are kept as fixtures so the next change has to keep clearing the same bar.
    """

    def test_a_tag_the_filer_abandoned_does_not_win_over_the_one_in_use(
        self,
    ) -> None:
        # NVIDIA tagged revenue as RevenueFromContractWithCustomerExcluding-
        # AssessedTax until fiscal 2020 and has used Revenues ever since. Both
        # tags are still served; taking the first that has any quarters at all
        # scored NVIDIA on its January 2020 quarter, six years stale.
        reading = factor(CompanyFactsTransport()).reading(
            cik=NVIDIA_CIK, as_of=AFTER_Q3
        )

        self.assertIsNone(reading.unavailable_reason)
        by_name = inputs_by_name(reading)
        self.assertEqual(
            by_name["revenue_current"].observed_at.date(), date(2026, 4, 26)
        )
        self.assertAlmostEqual(reading.value or 0.0, 1.0, places=6)

    def test_a_filer_with_no_revenue_tag_is_scored_on_what_it_does_report(
        self,
    ) -> None:
        # JPMorgan's last tagged Revenues quarter is from 2014 and it reports
        # no gross profit at all, but its diluted EPS is current. Letting
        # revenue nominate the period declared the whole company stale.
        reading = factor(CompanyFactsTransport()).reading(
            cik=JPMORGAN_CIK, as_of=AFTER_Q3
        )

        self.assertIsNone(reading.unavailable_reason)
        by_name = inputs_by_name(reading)
        self.assertEqual(
            by_name["diluted_eps_current"].observed_at.date(), date(2026, 6, 30)
        )
        self.assertEqual(by_name["diluted_eps_current"].value, 7.7)
        self.assertNotIn("revenue_current", by_name)
        # Pairing 2026 earnings with 2014 revenue would produce a gross margin
        # that never existed, so nothing from 2014 may appear here at all.
        self.assertEqual(
            {item.observed_at.date().year for item in reading.inputs},
            {2026, 2025},
        )

    def test_a_filer_the_per_concept_endpoint_answers_empty_is_still_scored(
        self,
    ) -> None:
        # data.sec.gov's companyconcept endpoint returns "units": {"USD": {}}
        # for Coca-Cola on every tag this factor reads, while companyfacts
        # carries twelve quarters of the same numbers. Reading per concept
        # therefore reported a blue chip as having filed nothing.
        reading = factor(CompanyFactsTransport()).reading(
            cik=COCA_COLA_CIK, as_of=AFTER_Q3
        )

        self.assertIsNone(reading.unavailable_reason)
        # Coca-Cola's week-aligned fiscal calendar makes the current quarter
        # (2026-01-01..2026-04-03) 92 days and the year-earlier one
        # (2025-01-01..2025-03-28) 86 days. Growth is normalized to a daily
        # rate before being ratioed, so this is no longer the raw
        # 12472/11129-1 comparison (which would overstate the signal with six
        # days of revenue counted as if they were organic growth).
        self.assertAlmostEqual(reading.value or 0.0, 0.219948, places=6)
        self.assertEqual(
            inputs_by_name(reading)["revenue_current"].observed_at.date(),
            date(2026, 4, 3),
        )

    def test_a_fiscal_calendar_that_shifts_by_days_still_finds_its_comparison(
        self,
    ) -> None:
        # Coca-Cola's quarter ends 2026-04-03 and the year-earlier one ends
        # 2025-03-28: six days apart, because the periods are week-aligned.
        # An exact 365 day match would find nothing.
        reading = factor(CompanyFactsTransport()).reading(
            cik=COCA_COLA_CIK, as_of=AFTER_Q3
        )

        self.assertEqual(
            inputs_by_name(reading)["revenue_prior"].observed_at.date(),
            date(2025, 3, 28),
        )

    def test_a_series_filed_under_the_wrong_unit_is_not_read_as_dollars(
        self,
    ) -> None:
        # Coca-Cola files four quarters of diluted EPS under the "pure" unit,
        # a tagging slip from 2009. Reading whatever unit happens to be there
        # would put a 2009 number next to a 2026 one.
        payload = json.loads(fixture("sec_ko_companyfacts.json"))
        units = payload["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]
        self.assertIn("pure", units)
        self.assertTrue(units["pure"])

        reading = factor(CompanyFactsTransport()).reading(
            cik=COCA_COLA_CIK, as_of=AFTER_Q3
        )

        self.assertEqual(
            inputs_by_name(reading)["diluted_eps_current"].observed_at.date(),
            date(2026, 4, 3),
        )

    def test_a_filer_with_no_gross_profit_is_scored_on_the_rest(self) -> None:
        reading = factor(CompanyFactsTransport()).reading(
            cik=FORD_CIK, as_of=AFTER_Q3
        )

        self.assertIsNone(reading.unavailable_reason)
        self.assertAlmostEqual(reading.value or 0.0, 0.659497, places=6)
        self.assertEqual(
            {item.name for item in reading.inputs},
            {
                "revenue_current",
                "revenue_prior",
                "diluted_eps_current",
                "diluted_eps_prior",
            },
        )
        self.assertNotIn("gross margin", reading.detail)


class FundamentalsDegradationTests(unittest.TestCase):
    def test_a_company_edgar_does_not_know_is_unavailable_never_zero(
        self,
    ) -> None:
        reading = factor(CompanyFactsTransport()).reading(
            cik="0009999999", as_of=AFTER_Q3
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )
        self.assertTrue(reading.detail.strip())

    def test_a_filer_reporting_under_another_taxonomy_says_which(self) -> None:
        # Taiwan Semiconductor files under ifrs-full and has no us-gaap
        # section at all. "No data" would send an operator looking for a
        # broken download; the reading has to name the actual obstacle.
        body = json.dumps(
            {
                "cik": 1046179,
                "entityName": "Taiwan Semiconductor Manufacturing Company",
                "facts": {"dei": {}, "ifrs-full": {}, "srt": {}},
            }
        ).encode()
        reading = factor(CompanyFactsTransport(body)).reading(
            cik="0001046179", as_of=AFTER_Q3
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )
        self.assertIn("us-gaap", reading.detail)
        self.assertIn("ifrs-full", reading.detail)

    def test_an_annual_only_filer_is_told_apart_from_a_missing_taxonomy(
        self,
    ) -> None:
        # Alibaba files a 20-F once a year and does have a us-gaap section,
        # but nothing in it covers a quarter. That is a different limitation
        # from filing under IFRS, and conflating them hides both.
        payload = json.loads(fixture("sec_aapl_companyfacts.json"))
        for info in payload["facts"]["us-gaap"].values():
            for unit, rows in list(info["units"].items()):
                info["units"][unit] = [
                    row
                    for row in rows
                    if row.get("start")
                    and (
                        date.fromisoformat(row["end"])
                        - date.fromisoformat(row["start"])
                    ).days
                    > 300
                ]
        reading = factor(
            CompanyFactsTransport(json.dumps(payload).encode())
        ).reading(cik=APPLE_CIK, as_of=AFTER_Q3)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )
        self.assertIn("quarter", reading.detail.lower())
        self.assertNotIn("ifrs", reading.detail.lower())

    def test_an_unreachable_source_degrades_instead_of_breaking_the_chain(
        self,
    ) -> None:
        for error in (
            FeedAccessError("blocked"),
            ResponseTooLargeError("too big"),
            OSError("connection reset"),
            TimeoutError("timed out"),
        ):
            with self.subTest(error=type(error).__name__):
                reading = factor(FailingTransport(error)).reading(
                    cik=APPLE_CIK, as_of=AFTER_Q3
                )
                self.assertIsNone(reading.value)
                self.assertEqual(
                    reading.unavailable_reason,
                    FactorUnavailable.SOURCE_UNREACHABLE,
                )

    def test_a_server_error_is_unreachable_rather_than_empty(self) -> None:
        reading = factor(CompanyFactsTransport(b"oops", status=503)).reading(
            cik=APPLE_CIK, as_of=AFTER_Q3
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.SOURCE_UNREACHABLE
        )

    def test_a_payload_that_is_not_the_expected_shape_is_reported_as_malformed(
        self,
    ) -> None:
        for body in (b"not json", b"[]", b"{}", b'{"facts": 3}'):
            with self.subTest(body=body):
                reading = factor(CompanyFactsTransport(body)).reading(
                    cik=APPLE_CIK, as_of=AFTER_Q3
                )
                self.assertIsNone(reading.value)
                self.assertEqual(
                    reading.unavailable_reason,
                    FactorUnavailable.SOURCE_MALFORMED,
                )

    def test_filings_that_stopped_arriving_are_stale_rather_than_current(
        self,
    ) -> None:
        # A delisted or delinquent filer keeps returning its last numbers
        # forever. Scoring them as this quarter's fundamentals would treat a
        # two-year-old company as today's.
        reading = factor(CompanyFactsTransport()).reading(
            cik=APPLE_CIK,
            as_of=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.STALE_BEYOND_WINDOW
        )

    def test_a_calendar_filers_q4_gap_is_not_reported_as_stopped_reporting(
        self,
    ) -> None:
        # Coca-Cola's Q3 ends 2025-09-26. Q4 never appears as its own
        # quarterly duration (the 10-K carries only the full-year span,
        # which _parse_fact rejects), so the next quarterly datum is next
        # year's Q1 10-Q, filed 2026-04-30 - a structural ~216 day gap every
        # calendar-year filer goes through every spring while filing exactly
        # on schedule. A 200-day window called this "stopped reporting".
        for as_of in (
            datetime(2026, 4, 20, tzinfo=timezone.utc),
            datetime(2026, 4, 30, tzinfo=timezone.utc),
        ):
            with self.subTest(as_of=as_of):
                reading = factor(CompanyFactsTransport()).reading(
                    cik=COCA_COLA_CIK, as_of=as_of
                )

                self.assertIsNone(reading.unavailable_reason)
                self.assertIsNotNone(reading.value)

    def test_a_gap_beyond_the_widened_calendar_aware_bound_is_still_stale(
        self,
    ) -> None:
        # The fixture's newest Coca-Cola quarter ends 2026-04-03 with no
        # later quarter on file. By 2027-01-01 (273 days later) that is well
        # past even a Q4-gap-adjusted bound: widening the window to cover the
        # structural gap must not turn it into a licence to call a company
        # that has genuinely stopped filing "current".
        reading = factor(CompanyFactsTransport()).reading(
            cik=COCA_COLA_CIK,
            as_of=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.STALE_BEYOND_WINDOW
        )

    def test_a_quarter_with_no_year_earlier_comparison_is_not_a_growth_rate(
        self,
    ) -> None:
        payload = json.loads(fixture("sec_aapl_companyfacts.json"))
        for info in payload["facts"]["us-gaap"].values():
            for unit, rows in list(info["units"].items()):
                info["units"][unit] = [
                    row for row in rows if row.get("end", "") >= "2026-01-01"
                ]
        reading = factor(
            CompanyFactsTransport(json.dumps(payload).encode())
        ).reading(cik=APPLE_CIK, as_of=AFTER_Q3)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.INSUFFICIENT_HISTORY
        )


def _quarter_row(
    *, start: str, end: str, value: float, filed: str, accn: str
) -> dict[str, object]:
    return {
        "start": start,
        "end": end,
        "val": value,
        "filed": filed,
        "accn": accn,
        "fy": 2026,
        "fp": "Q1",
        "form": "10-Q",
    }


def _single_tag_payload(tag: str, unit: str, rows: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "cik": 9999999,
            "entityName": "Synthetic Test Co",
            "facts": {"us-gaap": {tag: {"units": {unit: rows}}}},
        }
    ).encode()


class StaleWindowBoundaryTests(unittest.TestCase):
    """Pins the exact calendar-aware bound rather than only its rough shape.

    A single quarterly fact with nothing before or after it, so the gap being
    measured is controlled to the day: the newest quarter's own end date, with
    no other data to shift what "current" means.
    """

    _END = date(2024, 12, 31)  # a 91-day quarter starting 2024-10-01

    def _reading_at_gap(self, days: int):
        rows = [
            _quarter_row(
                start="2024-10-01",
                end=self._END.isoformat(),
                value=1_000_000.0,
                filed="2025-01-15",
                accn="0000000000-25-000001",
            )
        ]
        as_of = datetime(
            self._END.year, self._END.month, self._END.day, tzinfo=timezone.utc
        ) + timedelta(days=days)
        return factor(
            CompanyFactsTransport(_single_tag_payload("Revenues", "USD", rows))
        ).reading(cik="0009999999", as_of=as_of)

    def test_two_quarters_and_the_45_day_10q_deadline_is_still_current(
        self,
    ) -> None:
        # The structural Q3 -> Q1 gap is one quarter that never gets its own
        # quarterly tag (Q4, folded into the 10-K) plus the following
        # quarter's own length, plus that quarter's 45-day filing deadline:
        # two quarters at this module's own maximum quarter length (100 days
        # each) plus 45 days is 245 days. One day inside that must not be
        # reported as a company that stopped filing.
        reading = self._reading_at_gap(244)

        self.assertNotEqual(
            reading.unavailable_reason, FactorUnavailable.STALE_BEYOND_WINDOW
        )

    def test_past_the_calendar_aware_bound_is_reported_stale(self) -> None:
        reading = self._reading_at_gap(246)

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.STALE_BEYOND_WINDOW
        )


class UnequalQuarterLengthComparabilityTests(unittest.TestCase):
    """A 52/53-week fiscal calendar shifts a quarter's own length by days.

    An extra week of revenue is real revenue, but it is not organic growth,
    and ratioing two differently-scoped periods reports it as if it were.
    """

    # 91-day current quarter vs an 85-day year-earlier quarter: exactly the
    # KO-style calendar shift the finding reproduced, sized so the expected
    # normalized value can be hand-computed rather than merely observed.
    _CURRENT = _quarter_row(
        start="2026-01-01",
        end="2026-04-02",
        value=1000.0,
        filed="2026-04-20",
        accn="0000000000-26-000001",
    )
    _PRIOR = _quarter_row(
        start="2025-01-01",
        end="2025-03-27",
        value=900.0,
        filed="2025-04-20",
        accn="0000000000-25-000001",
    )
    _AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)

    def test_revenue_growth_is_normalized_to_a_daily_rate_not_ratioed_raw(
        self,
    ) -> None:
        # Raw ratio: 1000/900 - 1 = +11.11% (scaled: 0.55556). Per-day rate:
        # (1000/91) / (900/85) - 1 = +3.79% (scaled: 0.18925). The six extra
        # days of revenue must not be counted twice: once as more dollars and
        # again as a faster growth rate.
        reading = factor(
            CompanyFactsTransport(
                _single_tag_payload("Revenues", "USD", [self._CURRENT, self._PRIOR])
            )
        ).reading(cik="0009999999", as_of=self._AS_OF)

        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(reading.value or 0.0, 0.189255, places=5)
        self.assertNotAlmostEqual(reading.value or 0.0, 0.555556, places=3)
        self.assertIn("91", reading.detail)
        self.assertIn("85", reading.detail)

    def test_earnings_growth_is_also_normalized_to_a_daily_rate(self) -> None:
        current = dict(self._CURRENT)
        prior = dict(self._PRIOR)
        reading = factor(
            CompanyFactsTransport(
                _single_tag_payload(
                    "EarningsPerShareDiluted", "USD/shares", [current, prior]
                )
            )
        ).reading(cik="0009999999", as_of=self._AS_OF)

        self.assertIsNotNone(reading.value)
        # Same 1000-vs-900-over-91-vs-85-days shape as the revenue case,
        # scaled by the (wider) EPS-growth scale instead.
        self.assertAlmostEqual(reading.value or 0.0, 0.126170, places=5)

    def test_equal_length_quarters_are_unaffected_by_the_normalization(
        self,
    ) -> None:
        # The fix must be a no-op when there is nothing to correct: two
        # 91-day quarters produce the same ratio normalized or not.
        current = dict(self._CURRENT)
        prior = dict(self._PRIOR, start="2025-01-02", end="2025-04-03", val=900.0)
        # 2025-01-02 -> 2025-04-03 is also 91 days.
        self.assertEqual(
            (date(2025, 4, 3) - date(2025, 1, 2)).days, 91
        )

        reading = factor(
            CompanyFactsTransport(
                _single_tag_payload("Revenues", "USD", [current, prior])
            )
        ).reading(cik="0009999999", as_of=self._AS_OF)

        self.assertAlmostEqual(reading.value or 0.0, 0.555556, places=5)


if __name__ == "__main__":
    unittest.main()
