from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from us_stock_helper_device_auth.errors import DeviceAuthError, ErrorCode
from us_stock_helper_device_auth.time_utils import (
    from_storage,
    optional_from_storage,
    require_utc,
    to_storage,
    utc_now,
)


class StoredTimestampTests(unittest.TestCase):
    def test_an_instant_survives_the_round_trip(self) -> None:
        moment = datetime(2026, 8, 12, 9, 0, 0, 123456, tzinfo=timezone.utc)

        self.assertEqual(from_storage(to_storage(moment)), moment)

    def test_the_stored_form_is_fixed_width_so_it_sorts_as_it_reads(self) -> None:
        # The rate-limit window compares these as text in SQLite. A format that
        # drops the fraction on a whole second sorts "09:00:00Z" after
        # "09:00:00.5Z" and hands a client extra attempts.
        whole = to_storage(datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc))
        fractional = to_storage(
            datetime(2026, 8, 12, 9, 0, 0, 500000, tzinfo=timezone.utc)
        )

        self.assertEqual(len(whole), len(fractional))
        self.assertLess(whole, fractional)
        self.assertTrue(whole.endswith("Z"))

    def test_an_ordering_of_instants_is_an_ordering_of_their_text(self) -> None:
        base = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
        moments = [
            base,
            base + timedelta(microseconds=1),
            base + timedelta(seconds=1),
            base + timedelta(days=400),
        ]

        stored = [to_storage(moment) for moment in moments]

        self.assertEqual(stored, sorted(stored))

    def test_a_naive_datetime_is_refused_rather_than_assumed_to_be_utc(self) -> None:
        # Assuming a naive timestamp means UTC is how a code that reads as
        # expired on one host is still live on another.
        with self.assertRaises(DeviceAuthError) as caught:
            to_storage(datetime(2026, 8, 12, 9, 0))

        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        with self.assertRaises(DeviceAuthError):
            require_utc(datetime(2026, 8, 12, 9, 0))
        with self.assertRaises(DeviceAuthError):
            require_utc("2026-08-12T09:00:00Z")  # type: ignore[arg-type]

    def test_another_zone_is_converted_rather_than_relabelled(self) -> None:
        singapore = timezone(timedelta(hours=8))
        moment = datetime(2026, 8, 12, 17, 0, tzinfo=singapore)

        self.assertEqual(to_storage(moment), "2026-08-12T09:00:00.000000Z")

    def test_stored_text_that_cannot_be_read_fails_closed(self) -> None:
        for stored in ("", "yesterday", "2026-08-12T09:00:00Z", "2026-08-12", 17, None):
            with self.subTest(stored=stored):
                with self.assertRaises(DeviceAuthError) as caught:
                    from_storage(stored)
                self.assertEqual(caught.exception.code, ErrorCode.SCHEMA_UNSUPPORTED)

    def test_an_absent_timestamp_stays_absent(self) -> None:
        # A device that has never called in has no last-seen instant, and that
        # is reported as nothing rather than as the epoch or as now.
        self.assertIsNone(optional_from_storage(None))
        self.assertEqual(
            optional_from_storage("2026-08-12T09:00:00.000000Z"),
            datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc),
        )

    def test_the_default_clock_is_aware_and_utc(self) -> None:
        now = utc_now()

        self.assertEqual(now.tzinfo, timezone.utc)
        self.assertEqual(to_storage(now), to_storage(now))


if __name__ == "__main__":
    unittest.main()
