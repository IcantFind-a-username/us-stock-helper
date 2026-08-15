from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math
import unittest

from us_stock_helper_core.models import OHLCVBar
from us_stock_helper_core.volatility import (
    RANGE_VOLATILITY_VERSION,
    VOLATILITY_VERSION,
    VolatilityEstimate,
    estimate_annualized_volatility,
    estimate_garman_klass_volatility,
    estimate_parkinson_volatility,
)


BASE_TIME = datetime(2026, 7, 24, 14, tzinfo=UTC)


def bar(
    index: int,
    close: float,
    *,
    interval: str = "5m",
    minutes: int = 5,
    complete: bool = True,
    available_at: datetime | None = None,
) -> OHLCVBar:
    closed_at = BASE_TIME + timedelta(minutes=minutes * index)
    return OHLCVBar(
        symbol="NVDA",
        interval=interval,
        opened_at=closed_at - timedelta(minutes=minutes),
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=1_000.0,
        complete=complete,
    )


def series(closes: list[float], **kwargs: object) -> tuple[OHLCVBar, ...]:
    return tuple(
        bar(index, close, **kwargs)  # type: ignore[arg-type]
        for index, close in enumerate(closes)
    )


def alternating(count: int, *, step: float = 0.01) -> list[float]:
    closes = [100.0]
    for index in range(1, count):
        closes.append(closes[-1] * (1.0 + step if index % 2 else 1.0 - step))
    return closes


class VolatilityEstimateTests(unittest.TestCase):
    def test_estimate_is_unavailable_below_the_minimum_sample(self) -> None:
        bars = series(alternating(15))

        estimate = estimate_annualized_volatility(bars, BASE_TIME + timedelta(days=1))

        self.assertIsInstance(estimate, VolatilityEstimate)
        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")
        self.assertIn("sample", estimate.missing_reason or "")
        self.assertEqual(estimate.method_version, VOLATILITY_VERSION)

    def test_estimate_reports_a_positive_annualized_value(self) -> None:
        bars = series(alternating(80))

        estimate = estimate_annualized_volatility(bars, BASE_TIME + timedelta(days=1))

        self.assertEqual(estimate.quality_status, "live")
        self.assertIsNone(estimate.missing_reason)
        assert estimate.value is not None
        self.assertGreater(estimate.value, 0.0)
        self.assertEqual(estimate.sample_size, 79)

    def test_a_flat_market_is_unavailable_rather_than_zero_volatility(self) -> None:
        bars = series([100.0] * 80)

        estimate = estimate_annualized_volatility(bars, BASE_TIME + timedelta(days=1))

        # Zero would flow into the forecast as an infinitely confident range.
        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")

    def test_estimate_ignores_bars_the_cutoff_could_not_have_seen(self) -> None:
        closes = alternating(80)
        bars = series(closes)
        cutoff = bars[39].closed_at

        limited = estimate_annualized_volatility(bars, cutoff)
        direct = estimate_annualized_volatility(bars[:40], cutoff)

        self.assertEqual(limited.sample_size, 39)
        self.assertEqual(limited.value, direct.value)

    def test_estimate_never_revises_when_later_bars_arrive(self) -> None:
        closes = alternating(120)
        cutoff = BASE_TIME + timedelta(minutes=5 * 79)

        prefix = estimate_annualized_volatility(series(closes[:80]), cutoff)
        full = estimate_annualized_volatility(series(closes), cutoff)

        self.assertEqual(prefix.value, full.value)
        self.assertEqual(prefix.sample_size, full.sample_size)

    def test_estimate_rejects_bars_available_after_the_cutoff(self) -> None:
        closes = alternating(80)
        bars = list(series(closes))
        late = bars[40]
        bars[40] = OHLCVBar(
            **{
                **{name: getattr(late, name) for name in late.__dataclass_fields__},
                "available_at": late.closed_at + timedelta(days=2),
            }
        )
        cutoff = BASE_TIME + timedelta(days=1)

        estimate = estimate_annualized_volatility(tuple(bars), cutoff)

        # The late bar is simply not yet knowable; it drops out rather than
        # poisoning the sample or raising.
        self.assertEqual(estimate.sample_size, 78)

    def test_estimate_rejects_incomplete_bars_and_mixed_series(self) -> None:
        bars = series(alternating(80))
        cutoff = BASE_TIME + timedelta(days=1)
        with self.assertRaisesRegex(ValueError, "completed"):
            estimate_annualized_volatility(
                bars[:-1] + (bar(79, 100.0, complete=False),), cutoff
            )
        with self.assertRaisesRegex(ValueError, "interval"):
            estimate_annualized_volatility(
                bars[:-1] + (bar(79, 100.0, interval="day"),), cutoff
            )

    def test_annualization_scales_with_the_bar_interval(self) -> None:
        closes = alternating(80)
        cutoff = BASE_TIME + timedelta(days=400)

        intraday = estimate_annualized_volatility(series(closes), cutoff)
        daily = estimate_annualized_volatility(
            series(closes, interval="day", minutes=1_440), cutoff
        )

        assert intraday.value is not None and daily.value is not None
        # The same per-bar moves compound far more often in a 5-minute series.
        self.assertGreater(intraday.value, daily.value)
        self.assertAlmostEqual(
            intraday.value / daily.value, math.sqrt(78.0), places=6
        )

    def test_estimate_rejects_an_unsupported_interval_explicitly(self) -> None:
        bars = series(alternating(80), interval="3m", minutes=3)

        with self.assertRaisesRegex(ValueError, "interval"):
            estimate_annualized_volatility(bars, BASE_TIME + timedelta(days=1))


def range_bar(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    interval: str = "day",
    minutes: int = 1_440,
    complete: bool = True,
    available_at: datetime | None = None,
) -> OHLCVBar:
    closed_at = BASE_TIME + timedelta(minutes=minutes * index)
    return OHLCVBar(
        symbol="NVDA",
        interval=interval,
        opened_at=closed_at - timedelta(minutes=minutes),
        closed_at=closed_at,
        available_at=available_at or closed_at,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
        complete=complete,
    )


def constant_range_bars(
    closes: list[float], *, high_multiple: float
) -> tuple[OHLCVBar, ...]:
    """Every bar's open == close == low, and high == low * high_multiple.

    Because the ratio is scale-invariant, ``ln(high/low)`` is the identical
    constant on every bar regardless of the price level, which is what
    makes the aggregate Parkinson/Garman-Klass term a clean, hand-derivable
    closed form independent of how many bars are supplied.
    """

    return tuple(
        range_bar(index, open_=value, high=value * high_multiple, low=value, close=value)
        for index, value in enumerate(closes)
    )


def symmetric_range_bars(closes: list[float], *, half_width: float) -> tuple[OHLCVBar, ...]:
    """Every bar's open == close, high/low symmetric by +/- half_width."""

    return tuple(
        range_bar(
            index,
            open_=value,
            high=value * (1.0 + half_width),
            low=value * (1.0 - half_width),
            close=value,
        )
        for index, value in enumerate(closes)
    )


class ParkinsonAndGarmanKlassHandComputedTests(unittest.TestCase):
    def test_parkinson_matches_the_hand_derived_closed_form(self) -> None:
        closes = alternating(10)
        bars = constant_range_bars(closes, high_multiple=2.0)
        cutoff = BASE_TIME + timedelta(days=400)

        estimate = estimate_parkinson_volatility(bars, cutoff, minimum_sample=1)

        # Every bar has high/low == 2.0, so ln(high/low) == ln(2) on every
        # bar regardless of price level; the per-bar Parkinson term
        # ln(2)**2 / (4*ln2) reduces to the constant ln(2)/4, independent of
        # N. Annualized (252 trading days): sqrt(ln(2)/4 * 252).
        expected = math.sqrt((math.log(2.0) / 4.0) * 252.0)

        self.assertEqual(estimate.quality_status, "live")
        assert estimate.value is not None
        self.assertAlmostEqual(estimate.value, expected, places=9)
        self.assertEqual(estimate.sample_size, 10)
        self.assertEqual(estimate.estimator, "parkinson")
        self.assertEqual(estimate.method_version, RANGE_VOLATILITY_VERSION)

    def test_garman_klass_matches_the_hand_derived_closed_form(self) -> None:
        closes = alternating(10)
        bars = constant_range_bars(closes, high_multiple=2.0)
        cutoff = BASE_TIME + timedelta(days=400)

        estimate = estimate_garman_klass_volatility(bars, cutoff, minimum_sample=1)

        # open == close on every bar, so the close-open term vanishes and
        # the per-bar Garman-Klass term reduces to 0.5*ln(2)**2, independent
        # of N. Annualized: sqrt(0.5*ln(2)**2 * 252) == ln(2)*sqrt(0.5*252).
        expected = math.log(2.0) * math.sqrt(0.5 * 252.0)

        self.assertEqual(estimate.quality_status, "live")
        assert estimate.value is not None
        self.assertAlmostEqual(estimate.value, expected, places=9)
        self.assertEqual(estimate.sample_size, 10)
        self.assertEqual(estimate.estimator, "garman_klass")
        self.assertEqual(estimate.method_version, RANGE_VOLATILITY_VERSION)

    def test_close_to_close_estimator_metadata_is_unchanged(self) -> None:
        bars = series(alternating(80))
        cutoff = BASE_TIME + timedelta(days=1)

        estimate = estimate_annualized_volatility(bars, cutoff)

        self.assertEqual(estimate.estimator, "close_to_close")
        self.assertEqual(estimate.method_version, VOLATILITY_VERSION)


class RangeVolatilityCrossCheckTests(unittest.TestCase):
    def test_wider_intrabar_range_increases_range_estimators_but_not_close_to_close(
        self,
    ) -> None:
        closes = alternating(10)
        narrow = symmetric_range_bars(closes, half_width=0.001)
        wide = symmetric_range_bars(closes, half_width=0.05)
        cutoff = BASE_TIME + timedelta(days=400)

        narrow_close = estimate_annualized_volatility(narrow, cutoff, minimum_sample=2)
        wide_close = estimate_annualized_volatility(wide, cutoff, minimum_sample=2)
        narrow_parkinson = estimate_parkinson_volatility(narrow, cutoff, minimum_sample=1)
        wide_parkinson = estimate_parkinson_volatility(wide, cutoff, minimum_sample=1)
        narrow_gk = estimate_garman_klass_volatility(narrow, cutoff, minimum_sample=1)
        wide_gk = estimate_garman_klass_volatility(wide, cutoff, minimum_sample=1)

        # close_to_close only ever reads .close, which is identical between
        # the two fixtures -- widening the intrabar range must not move it.
        self.assertEqual(narrow_close.value, wide_close.value)
        # Parkinson/GK read exactly the range close_to_close cannot see.
        assert narrow_parkinson.value is not None and wide_parkinson.value is not None
        assert narrow_gk.value is not None and wide_gk.value is not None
        self.assertLess(narrow_parkinson.value, wide_parkinson.value)
        self.assertLess(narrow_gk.value, wide_gk.value)

    def test_all_three_estimators_land_in_the_same_order_of_magnitude_on_a_realistic_series(
        self,
    ) -> None:
        # A geometric-Brownian-like fixture: closes alternate +/-1% (the same
        # deterministic walk used throughout this file), and every bar's own
        # intrabar range is a comparable +/-0.6%, a realistic day's high/low
        # spread relative to its close-to-close move.
        closes = alternating(80)
        bars = symmetric_range_bars(closes, half_width=0.006)
        cutoff = BASE_TIME + timedelta(days=400)

        close_to_close = estimate_annualized_volatility(bars, cutoff)
        parkinson = estimate_parkinson_volatility(bars, cutoff)
        garman_klass = estimate_garman_klass_volatility(bars, cutoff)

        for estimate in (close_to_close, parkinson, garman_klass):
            self.assertEqual(estimate.quality_status, "live")
            assert estimate.value is not None
            self.assertGreater(estimate.value, 0.0)

        assert close_to_close.value is not None
        # Parkinson (1980) is a known ~5x more statistically efficient
        # estimator of the same underlying volatility for a continuous GBM
        # process; for a fixture whose intrabar range and close-to-close
        # step are the same order of magnitude, the point estimates
        # themselves should land within a generous band of one another --
        # not a precision match, just a sanity check against a formula
        # error (wrong annualization factor, a missing sqrt, a sign flip)
        # that would move a value by an order of magnitude or more.
        for estimate in (parkinson, garman_klass):
            assert estimate.value is not None
            ratio = estimate.value / close_to_close.value
            self.assertGreater(ratio, 0.2)
            self.assertLess(ratio, 5.0)


class RangeVolatilityDegenerateInputTests(unittest.TestCase):
    def test_a_perfectly_flat_window_is_unavailable_for_parkinson(self) -> None:
        bars = constant_range_bars([100.0] * 25, high_multiple=1.0)  # high == low

        estimate = estimate_parkinson_volatility(
            bars, BASE_TIME + timedelta(days=400), minimum_sample=1
        )

        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")
        self.assertIn("no price variation", estimate.missing_reason or "")

    def test_a_perfectly_flat_window_is_unavailable_for_garman_klass(self) -> None:
        bars = constant_range_bars([100.0] * 25, high_multiple=1.0)  # high == low

        estimate = estimate_garman_klass_volatility(
            bars, BASE_TIME + timedelta(days=400), minimum_sample=1
        )

        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")
        self.assertIn("no price variation", estimate.missing_reason or "")

    def test_zero_or_negative_price_bars_cannot_be_constructed(self) -> None:
        # Both range estimators divide by low and by open; OHLCVBar's own
        # positivity guarantee is what keeps that division safe. Confirm
        # the guarantee still holds rather than assuming it silently.
        with self.assertRaisesRegex(ValueError, "positive"):
            range_bar(0, open_=0.0, high=1.0, low=0.0, close=0.0)

    def test_parkinson_is_unavailable_below_the_minimum_sample(self) -> None:
        bars = constant_range_bars(alternating(5), high_multiple=1.5)

        estimate = estimate_parkinson_volatility(
            bars, BASE_TIME + timedelta(days=400), minimum_sample=20
        )

        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")
        self.assertIn("sample", estimate.missing_reason or "")
        self.assertEqual(estimate.sample_size, 5)

    def test_garman_klass_is_unavailable_below_the_minimum_sample(self) -> None:
        bars = constant_range_bars(alternating(5), high_multiple=1.5)

        estimate = estimate_garman_klass_volatility(
            bars, BASE_TIME + timedelta(days=400), minimum_sample=20
        )

        self.assertIsNone(estimate.value)
        self.assertEqual(estimate.quality_status, "unavailable")
        self.assertIn("sample", estimate.missing_reason or "")
        self.assertEqual(estimate.sample_size, 5)

    def test_parkinson_rejects_incomplete_bars(self) -> None:
        bars = constant_range_bars(alternating(10), high_multiple=1.5)
        broken = bars[:-1] + (
            range_bar(9, open_=100.0, high=101.0, low=99.0, close=100.0, complete=False),
        )

        with self.assertRaisesRegex(ValueError, "completed"):
            estimate_parkinson_volatility(
                broken, BASE_TIME + timedelta(days=400), minimum_sample=1
            )


class RangeVolatilityPITTests(unittest.TestCase):
    def test_parkinson_ignores_bars_not_yet_knowable_at_the_cutoff(self) -> None:
        closes = alternating(30)
        bars = constant_range_bars(closes, high_multiple=1.5)
        cutoff = bars[19].closed_at

        limited = estimate_parkinson_volatility(bars, cutoff, minimum_sample=1)
        direct = estimate_parkinson_volatility(bars[:20], cutoff, minimum_sample=1)

        self.assertEqual(limited.sample_size, 20)
        self.assertEqual(limited.value, direct.value)

    def test_garman_klass_rejects_a_bar_available_after_the_cutoff(self) -> None:
        closes = alternating(30)
        bars = list(constant_range_bars(closes, high_multiple=1.5))
        late = bars[15]
        cutoff = bars[29].closed_at
        bars[15] = OHLCVBar(
            **{
                **{name: getattr(late, name) for name in late.__dataclass_fields__},
                # Knowable well after every other bar's own closed_at, and
                # specifically after the cutoff itself.
                "available_at": cutoff + timedelta(days=100),
            }
        )

        estimate = estimate_garman_klass_volatility(
            tuple(bars), cutoff, minimum_sample=1
        )

        self.assertEqual(estimate.sample_size, 29)


if __name__ == "__main__":
    unittest.main()
