"""Macro conditions from the US Treasury daily yield curve.

Of the free macro releases, the daily par yield curve is the only one whose
point-in-time properties are clean without a release calendar. CPI and payroll
prints carry a reference month, not a publication instant, so dating them
correctly means hard-coding a schedule of 08:30 ET announcements that changes
every year — and getting it wrong is a future function on the most
market-moving numbers there are. Treasury publishes the curve for day D on day
D, late in the New York afternoon, so the observation date and the release are
the same day and the availability rule is one line.

What the number means is a modelling choice, and it is stated here rather than
buried in the arithmetic:

* **Slope.** Ten-year minus two-year, in percentage points. An inverted curve
  is the most documented single macro warning for equities; a positive slope
  reads as ordinary conditions. Signed so that steeper is more supportive.
* **Ten-year momentum.** The change in the ten-year over the last 21 sessions,
  signed so that *falling* yields score positive. This is the honest weak
  point of v1: outside a crisis, falling long yields ease financial conditions
  and support equity multiples, but in a flight to quality yields and equities
  fall together and this term will have the sign exactly backwards. It is kept
  because it is the timely half of the factor, and it is versioned so a v2 that
  conditions on a stress regime can replace it without rewriting history.

Neither term is a claim of predictive power. Both are deterministic functions
of published numbers, so any backtest can recompute them exactly, and every
yield the reading used is attached to it.

Method version: ``us-treasury-curve-macro-v1``.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ..feeds.http import FeedError, HttpRequest, HttpResponse, HttpTransport
from .base import (
    FACTOR_MACRO,
    FactorInput,
    FactorReading,
    FactorUnavailable,
    clamp_unit,
)


TREASURY_MACRO_METHOD_VERSION = "us-treasury-curve-macro-v1"

_HOST = "home.treasury.gov"
_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"
    "/daily-treasury-rates.csv/{year}/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv"
)

_DATE_COLUMN = "Date"
_TWO_YEAR_COLUMN = "2 Yr"
_TEN_YEAR_COLUMN = "10 Yr"

_TIMEOUT_SECONDS = 15.0
_MAX_RESPONSE_BYTES = 2_000_000

# Roughly one calendar month of sessions.
_DEFAULT_LOOKBACK_ROWS = 21

# Treasury has published every business day for decades. A gap this long means
# the download is broken or the file moved, not that rates stood still, and
# scoring a month-old curve as today's macro is exactly the stale-data failure
# the decision chain gates on elsewhere.
_STALE_AFTER_DAYS = 10

# A full-strength reading at a one point slope, or a 50 basis point move in the
# ten-year over the lookback. Both are versioned with the method.
_SLOPE_SCALE = 1.0
_MOMENTUM_SCALE = 0.50


class _SourceUnreachable(Exception):
    pass


class _SourceMalformed(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _CurveRow:
    observed_on: date
    two_year: float
    ten_year: float

    @property
    def available_at(self) -> datetime:
        return treasury_available_at(self.observed_on)


def treasury_available_at(observed_on: date) -> datetime:
    """When the curve for a given business day was certainly published.

    Treasury posts the day's par yields in the late New York afternoon. 23:00
    UTC is 18:00 ET under standard time and 19:00 ET under daylight time, so
    it is never earlier than publication under either offset, and it is always
    after the 16:00 ET equity close — which means a same-session decision can
    never read a curve the market had not yet seen.
    """

    return datetime(
        observed_on.year, observed_on.month, observed_on.day, 23, 0,
        tzinfo=timezone.utc,
    )


class TreasuryYieldCurveMacroFactor:
    def __init__(
        self,
        *,
        transport: HttpTransport,
        user_agent: str = "us-stock-helper/0.1",
        lookback_rows: int = _DEFAULT_LOOKBACK_ROWS,
    ) -> None:
        if lookback_rows < 1:
            raise ValueError("the momentum lookback must be at least one row")
        self._transport = transport
        self._user_agent = user_agent
        self._lookback_rows = lookback_rows

    def reading(self, *, as_of: datetime) -> FactorReading:
        try:
            rows = self._rows_visible_at(as_of)
        except _SourceUnreachable as error:
            return self._unavailable(
                as_of,
                FactorUnavailable.SOURCE_UNREACHABLE,
                f"The Treasury yield curve could not be read: {error}.",
            )
        except _SourceMalformed as error:
            return self._unavailable(
                as_of,
                FactorUnavailable.SOURCE_MALFORMED,
                f"The Treasury yield curve download was not the expected CSV: "
                f"{error}.",
            )

        if not rows:
            return self._unavailable(
                as_of,
                FactorUnavailable.NO_DATA_AT_CUTOFF,
                "No Treasury yield curve had been published at the decision "
                "cutoff.",
            )

        latest = rows[-1]
        if (as_of.date() - latest.observed_on).days > _STALE_AFTER_DAYS:
            return self._unavailable(
                as_of,
                FactorUnavailable.STALE_BEYOND_WINDOW,
                f"The newest published curve is from "
                f"{latest.observed_on.isoformat()}, more than "
                f"{_STALE_AFTER_DAYS} days before the cutoff.",
            )

        slope = latest.ten_year - latest.two_year
        details = [f"10y-2y slope {slope:+.2f}pp"]
        values = [clamp_unit(slope / _SLOPE_SCALE)]
        inputs = [
            _factor_input("treasury_10y", latest.observed_on, latest.ten_year),
            _factor_input("treasury_2y", latest.observed_on, latest.two_year),
        ]

        if len(rows) > self._lookback_rows:
            earlier = rows[-(self._lookback_rows + 1)]
            change = latest.ten_year - earlier.ten_year
            values.append(clamp_unit(-change / _MOMENTUM_SCALE))
            details.append(
                f"10y {change:+.2f}pp over {self._lookback_rows} sessions"
            )
            inputs.append(
                _factor_input(
                    "treasury_10y_lookback",
                    earlier.observed_on,
                    earlier.ten_year,
                )
            )
        else:
            # Saying so beats silently scoring the slope alone as if it were
            # the whole factor.
            details.append(
                f"momentum omitted: only {len(rows)} sessions on file"
            )

        return FactorReading.measured(
            factor=FACTOR_MACRO,
            method_version=TREASURY_MACRO_METHOD_VERSION,
            as_of=as_of,
            value=clamp_unit(sum(values) / len(values)),
            detail=f"{latest.observed_on.isoformat()}: " + "; ".join(details) + ".",
            inputs=tuple(inputs),
        )

    def _unavailable(
        self, as_of: datetime, reason: FactorUnavailable, detail: str
    ) -> FactorReading:
        return FactorReading.unavailable(
            factor=FACTOR_MACRO,
            method_version=TREASURY_MACRO_METHOD_VERSION,
            as_of=as_of,
            reason=reason,
            detail=detail,
        )

    def _rows_visible_at(self, as_of: datetime) -> list[_CurveRow]:
        """Every curve published at or before the cutoff, oldest first.

        Treasury serves one file per calendar year, so a January cutoff needs
        the previous year's file to reach a month back. The fetch is
        conditional rather than unconditional: eleven months of the year it
        would be a second request for rows nobody reads.
        """

        collected = {
            row.observed_on: row
            for row in self._year_rows(as_of.year)
            if row.available_at <= as_of
        }
        if len(collected) <= self._lookback_rows:
            collected.update(
                {
                    row.observed_on: row
                    for row in self._year_rows(as_of.year - 1)
                    if row.available_at <= as_of
                }
            )
        return [collected[key] for key in sorted(collected)]

    def _year_rows(self, year: int) -> list[_CurveRow]:
        url = _CURVE_URL.format(year=year)
        response = self._get(url)
        if response.status_code == 404:
            # Treasury has no file for a year it has not reached.
            return []
        if response.status_code != 200:
            raise _SourceUnreachable(f"{url} answered {response.status_code}")
        return _parse_curve(response.body, url)

    def _get(self, url: str) -> HttpResponse:
        request = HttpRequest(
            url=url,
            allowed_hosts=(_HOST,),
            headers=(
                ("User-Agent", self._user_agent),
                ("Accept", "text/csv, */*;q=0.1"),
            ),
            timeout_seconds=_TIMEOUT_SECONDS,
            max_response_bytes=_MAX_RESPONSE_BYTES,
        )
        try:
            return self._transport.request(request)
        except (FeedError, OSError, ValueError) as error:
            raise _SourceUnreachable(str(error) or type(error).__name__) from error


def _parse_curve(body: bytes, url: str) -> list[_CurveRow]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise _SourceMalformed(f"{url} is not UTF-8 text") from error
    reader = csv.DictReader(io.StringIO(text))
    header = [name.strip() for name in (reader.fieldnames or [])]
    missing = [
        column
        for column in (_DATE_COLUMN, _TWO_YEAR_COLUMN, _TEN_YEAR_COLUMN)
        if column not in header
    ]
    if missing:
        # A maintenance page, a redirect to HTML, or a renamed tenor column
        # all land here. Continuing would produce an empty series that reads
        # as "the curve is quiet" instead of "the download broke".
        raise _SourceMalformed(f"{url} is missing column(s) {', '.join(missing)}")
    return _rows_from(reader)


def _rows_from(reader: csv.DictReader) -> list[_CurveRow]:  # type: ignore[type-arg]
    rows: list[_CurveRow] = []
    for record in reader:
        observed_on = _as_date(record.get(_DATE_COLUMN))
        two_year = _as_rate(record.get(_TWO_YEAR_COLUMN))
        ten_year = _as_rate(record.get(_TEN_YEAR_COLUMN))
        if observed_on is None or two_year is None or ten_year is None:
            # Treasury blanks a tenor it did not publish that day. A gap is
            # not a zero rate, so the whole session is dropped rather than
            # half-used.
            continue
        rows.append(
            _CurveRow(
                observed_on=observed_on, two_year=two_year, ten_year=ten_year
            )
        )
    return rows


def _as_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _as_rate(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _factor_input(name: str, observed_on: date, value: float) -> FactorInput:
    return FactorInput(
        name=name,
        value=value,
        observed_at=datetime(
            observed_on.year, observed_on.month, observed_on.day,
            tzinfo=timezone.utc,
        ),
        available_at=treasury_available_at(observed_on),
        source_url=_CURVE_URL.format(year=observed_on.year),
    )
