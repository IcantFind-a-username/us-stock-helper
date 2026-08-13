from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from information_layer.factors import (
    FactorInput,
    FactorReading,
    FactorUnavailable,
)


AS_OF = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def an_input(**overrides: object) -> FactorInput:
    values: dict[str, object] = {
        "name": "revenue_current_quarter",
        "value": 109417000000.0,
        "observed_at": datetime(2026, 6, 27, tzinfo=timezone.utc),
        "available_at": AS_OF - timedelta(days=12),
        "source_url": "https://data.sec.gov/api/xbrl/companyconcept/x.json",
    }
    values.update(overrides)
    return FactorInput(**values)  # type: ignore[arg-type]


class FactorReadingTests(unittest.TestCase):
    def test_measured_reading_carries_value_lag_and_inputs(self) -> None:
        reading = FactorReading.measured(
            factor="fundamentals",
            method_version="sec-xbrl-fundamentals-v1",
            as_of=AS_OF,
            value=0.5,
            detail="Revenue grew year over year.",
            inputs=(an_input(),),
        )

        self.assertEqual(reading.value, 0.5)
        self.assertIsNone(reading.unavailable_reason)
        self.assertEqual(reading.available_at, AS_OF - timedelta(days=12))
        self.assertEqual(reading.lag_seconds, 12 * 24 * 3600.0)

    def test_a_measured_reading_may_not_be_built_on_data_from_the_future(
        self,
    ) -> None:
        # The whole point-in-time contract lives here: an input that became
        # public after the cutoff cannot have informed a decision taken at it.
        # The message is asserted because an earlier version of this test left
        # `detail` blank and passed on the wrong invariant while the look-ahead
        # guard was removed.
        with self.assertRaisesRegex(ValueError, "published after its cutoff"):
            FactorReading.measured(
                factor="macro",
                method_version="us-treasury-curve-macro-v1",
                as_of=AS_OF,
                value=0.1,
                detail="10y-2y slope +0.48pp.",
                inputs=(an_input(available_at=AS_OF + timedelta(seconds=1)),),
            )

    def test_an_input_exactly_at_the_cutoff_is_still_usable(self) -> None:
        # The boundary belongs on the visible side: a release timestamped at
        # the cutoff was public at the cutoff.
        reading = FactorReading.measured(
            factor="macro",
            method_version="us-treasury-curve-macro-v1",
            as_of=AS_OF,
            value=0.1,
            detail="10y-2y slope +0.48pp.",
            inputs=(an_input(available_at=AS_OF),),
        )

        self.assertEqual(reading.lag_seconds, 0.0)

    def test_a_measured_reading_needs_something_it_was_measured_from(self) -> None:
        with self.assertRaisesRegex(ValueError, "cite what it measured"):
            FactorReading.measured(
                factor="macro",
                method_version="us-treasury-curve-macro-v1",
                as_of=AS_OF,
                value=0.1,
                detail="10y-2y slope +0.48pp.",
                inputs=(),
            )

    def test_a_measured_value_outside_the_unit_range_is_rejected(self) -> None:
        for value in (-1.01, 1.01, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, r"within \[-1, 1\]"):
                    FactorReading.measured(
                        factor="macro",
                        method_version="us-treasury-curve-macro-v1",
                        as_of=AS_OF,
                        value=value,
                        detail="10y-2y slope +0.48pp.",
                        inputs=(an_input(),),
                    )

    def test_an_unavailable_reading_has_no_value_at_all(self) -> None:
        reading = FactorReading.unavailable(
            factor="geopolitics",
            method_version="none",
            as_of=AS_OF,
            reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
            detail="No free structured source maps to a defensible number.",
        )

        self.assertIsNone(reading.value)
        self.assertEqual(
            reading.unavailable_reason, FactorUnavailable.NO_QUALIFIED_SOURCE
        )
        self.assertIsNone(reading.available_at)
        self.assertIsNone(reading.lag_seconds)

    def test_an_unavailable_reading_must_say_why_in_words(self) -> None:
        # A bare enum tells an operator nothing actionable, and "unavailable"
        # with no explanation is how a dead source stays dead unnoticed.
        with self.assertRaises(ValueError):
            FactorReading.unavailable(
                factor="macro",
                method_version="us-treasury-curve-macro-v1",
                as_of=AS_OF,
                reason=FactorUnavailable.SOURCE_UNREACHABLE,
                detail="   ",
            )

    def test_the_two_constructors_are_the_only_way_in(self) -> None:
        # Direct construction with both a value and a reason would let a
        # caller publish "0.0 because the source was down", which is the one
        # thing this project forbids outright.
        with self.assertRaisesRegex(ValueError, "never both"):
            FactorReading(
                factor="macro",
                method_version="us-treasury-curve-macro-v1",
                as_of=AS_OF,
                value=0.0,
                unavailable_reason=FactorUnavailable.SOURCE_UNREACHABLE,
                detail="down",
            )
        with self.assertRaisesRegex(ValueError, "never both"):
            FactorReading(
                factor="macro",
                method_version="us-treasury-curve-macro-v1",
                as_of=AS_OF,
                value=None,
                unavailable_reason=None,
                detail="down",
            )

    def test_naive_timestamps_are_refused_everywhere(self) -> None:
        with self.assertRaises(ValueError):
            FactorReading.unavailable(
                factor="macro",
                method_version="v",
                as_of=datetime(2026, 8, 13, 12, 0),
                reason=FactorUnavailable.SOURCE_UNREACHABLE,
                detail="down",
            )
        with self.assertRaises(ValueError):
            an_input(available_at=datetime(2026, 8, 1, 12, 0))


if __name__ == "__main__":
    unittest.main()
