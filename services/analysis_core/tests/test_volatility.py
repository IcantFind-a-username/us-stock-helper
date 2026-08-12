from __future__ import annotations

from datetime import UTC, datetime, timedelta
import math
import unittest

from us_stock_helper_core.models import OHLCVBar
from us_stock_helper_core.volatility import (
    VOLATILITY_VERSION,
    VolatilityEstimate,
    estimate_annualized_volatility,
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


if __name__ == "__main__":
    unittest.main()
