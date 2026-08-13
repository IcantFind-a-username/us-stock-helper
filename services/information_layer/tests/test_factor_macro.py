from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from information_layer.factors import FactorUnavailable
from information_layer.factors.macro import (
    TREASURY_MACRO_METHOD_VERSION,
    TreasuryYieldCurveMacroFactor,
    treasury_available_at,
)
from information_layer.feeds import FeedAccessError, HttpRequest, HttpResponse


FIXTURES = Path(__file__).parent / "fixtures"
# Verbatim download of Treasury's 2026 daily yield curve CSV, captured
# 2026-08-14. Rows arrive newest first, which the parser must not rely on.
CURVE_2026 = (FIXTURES / "treasury_yield_curve_2026.csv").read_bytes()

AFTER_PUBLICATION = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
BEFORE_PUBLICATION = datetime(2026, 8, 12, 22, 59, tzinfo=timezone.utc)


class YearTransport:
    def __init__(self, bodies: dict[int, bytes], status: int = 200) -> None:
        self._bodies = bodies
        self._status = status
        self.requests: list[HttpRequest] = []

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        year = next(
            (item for item in self._bodies if f"/{item}/all" in request.url),
            None,
        )
        body = self._bodies.get(year or -1, b"")
        return HttpResponse(
            status_code=self._status if body else 404,
            headers=(("Content-Type", "text/csv"),),
            body=body,
            retrieved_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        )


class FailingTransport:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def request(self, request: HttpRequest) -> HttpResponse:
        raise self._error


def factor(transport: object, **overrides: object) -> TreasuryYieldCurveMacroFactor:
    values: dict[str, object] = {"transport": transport}
    values.update(overrides)
    return TreasuryYieldCurveMacroFactor(**values)  # type: ignore[arg-type]


class TreasuryAvailabilityTests(unittest.TestCase):
    def test_a_curve_date_becomes_public_after_that_days_equity_close(
        self,
    ) -> None:
        # Treasury posts the curve late in the afternoon New York time. 23:00Z
        # is 18:00 ET in winter and 19:00 ET in summer, so it is never earlier
        # than publication and always after the 16:00 ET equity close.
        self.assertEqual(
            treasury_available_at(date(2026, 8, 12)),
            datetime(2026, 8, 12, 23, 0, tzinfo=timezone.utc),
        )


class MacroMeasurementTests(unittest.TestCase):
    def test_the_real_curve_produces_a_measured_reading(self) -> None:
        reading = factor(YearTransport({2026: CURVE_2026})).reading(
            as_of=AFTER_PUBLICATION
        )

        self.assertEqual(reading.factor, "macro")
        self.assertEqual(reading.method_version, TREASURY_MACRO_METHOD_VERSION)
        self.assertIsNone(reading.unavailable_reason)
        # 2026-08-12: 10Y 4.68 minus 2Y 4.20 is a 0.48pp slope (scaled by
        # 1pp -> 0.48); 10Y rose 0.10pp over 21 sessions, and rising yields
        # score negative (scaled by 0.5pp -> -0.20). Mean 0.14.
        self.assertAlmostEqual(reading.value or 0.0, 0.14, places=6)
        self.assertEqual(
            reading.available_at,
            datetime(2026, 8, 12, 23, 0, tzinfo=timezone.utc),
        )

    def test_the_reading_exposes_the_yields_it_was_computed_from(self) -> None:
        reading = factor(YearTransport({2026: CURVE_2026})).reading(
            as_of=AFTER_PUBLICATION
        )
        by_name = {item.name: item for item in reading.inputs}

        self.assertAlmostEqual(by_name["treasury_10y"].value, 4.68)
        self.assertAlmostEqual(by_name["treasury_2y"].value, 4.20)
        self.assertAlmostEqual(by_name["treasury_10y_lookback"].value, 4.58)
        self.assertEqual(
            by_name["treasury_10y"].observed_at.date(), date(2026, 8, 12)
        )
        self.assertEqual(
            by_name["treasury_10y_lookback"].observed_at.date(),
            date(2026, 7, 14),
        )

    def test_a_row_published_after_the_cutoff_is_not_read(self) -> None:
        # One minute before Treasury posts the 12 August curve, the newest
        # row this system may use is 11 August.
        reading = factor(YearTransport({2026: CURVE_2026})).reading(
            as_of=BEFORE_PUBLICATION
        )
        by_name = {item.name: item for item in reading.inputs}

        self.assertEqual(
            by_name["treasury_10y"].observed_at.date(), date(2026, 8, 11)
        )
        self.assertAlmostEqual(by_name["treasury_10y"].value, 4.70)

    def test_the_previous_year_is_fetched_when_the_lookback_reaches_into_it(
        self,
    ) -> None:
        transport = YearTransport({2026: CURVE_2026})
        factor(transport).reading(
            as_of=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
        )

        requested = [item.url for item in transport.requests]
        self.assertTrue(any("/2026/all" in url for url in requested))
        self.assertTrue(any("/2025/all" in url for url in requested))


class MacroDegradationTests(unittest.TestCase):
    def test_an_unreachable_source_degrades_instead_of_breaking_the_chain(
        self,
    ) -> None:
        for error in (
            FeedAccessError("blocked"),
            OSError("connection reset"),
            TimeoutError("timed out"),
        ):
            with self.subTest(error=type(error).__name__):
                reading = factor(FailingTransport(error)).reading(
                    as_of=AFTER_PUBLICATION
                )
                self.assertIsNone(reading.value)
                self.assertEqual(
                    reading.unavailable_reason,
                    FactorUnavailable.SOURCE_UNREACHABLE,
                )

    def test_a_body_that_is_not_the_expected_csv_is_reported_as_malformed(
        self,
    ) -> None:
        for body in (b"<html>maintenance</html>", b"Date,1 Mo\n08/12/2026,3.78\n"):
            with self.subTest(body=body):
                reading = factor(YearTransport({2026: body})).reading(
                    as_of=AFTER_PUBLICATION
                )
                self.assertIsNone(reading.value)
                self.assertEqual(
                    reading.unavailable_reason,
                    FactorUnavailable.SOURCE_MALFORMED,
                )

    def test_a_curve_that_stopped_updating_is_stale_rather_than_current(
        self,
    ) -> None:
        reading = factor(YearTransport({2026: CURVE_2026})).reading(
            as_of=datetime(2026, 9, 30, tzinfo=timezone.utc)
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.STALE_BEYOND_WINDOW
        )

    def test_too_little_history_for_the_lookback_still_scores_the_slope(
        self,
    ) -> None:
        head = CURVE_2026.split(b"\n")
        trimmed = b"\n".join([head[0]] + head[1:4])
        reading = factor(YearTransport({2026: trimmed})).reading(
            as_of=AFTER_PUBLICATION
        )

        self.assertIsNotNone(reading.value)
        self.assertAlmostEqual(reading.value or 0.0, 0.48, places=6)
        self.assertNotIn(
            "treasury_10y_lookback", {item.name for item in reading.inputs}
        )

    def test_a_session_with_a_blank_tenor_is_dropped_not_read_as_zero(
        self,
    ) -> None:
        # Treasury leaves a cell empty for a tenor it did not publish that
        # day — the 30 year was blank for four years after 2002. An empty
        # string is not a zero rate, and treating it as one would print a
        # five point slope out of nowhere.
        lines = CURVE_2026.split(b"\n")
        header, newest = lines[0], lines[1].split(b",")
        self.assertEqual(newest[0], b"08/12/2026")
        newest[8] = b""  # the "2 Yr" column
        blanked = b"\n".join([header, b",".join(newest)] + lines[2:])

        reading = factor(YearTransport({2026: blanked})).reading(
            as_of=AFTER_PUBLICATION
        )

        self.assertIsNotNone(reading.value)
        by_name = {item.name: item for item in reading.inputs}
        self.assertEqual(
            by_name["treasury_10y"].observed_at.date(), date(2026, 8, 11)
        )
        self.assertNotIn(
            0.0, [item.value for item in reading.inputs]
        )

    def test_a_csv_with_no_usable_row_is_unavailable_and_never_zero(self) -> None:
        header = CURVE_2026.split(b"\n")[0]
        reading = factor(YearTransport({2026: header + b"\n"})).reading(
            as_of=AFTER_PUBLICATION
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_DATA_AT_CUTOFF
        )


if __name__ == "__main__":
    unittest.main()
