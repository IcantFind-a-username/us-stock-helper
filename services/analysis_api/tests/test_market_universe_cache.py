"""MarketUniverseCache: what earns the full trading date vs. a short retry.

A named slot's value survives for the whole trading date only when nothing
about computing it failed; a failure or a partial universe instead earns a
short, monotonic-clock-based retry window, so a transient gateway restart
heals inside the same session rather than freezing until the next day's
16:00 ET rollover. `FakeMonotonic` lets every test cross that boundary by an
explicit `advance()` call -- no real sleep, no timing flakiness.
"""

from __future__ import annotations

import unittest

from us_stock_helper_analysis_api.market_universe_cache import (
    CacheOutcome,
    MarketUniverseCache,
)


class FakeMonotonic:
    """A test-controlled stand-in for `time.monotonic`."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RetentionPolicyTests(unittest.TestCase):
    def test_a_healthy_result_survives_long_past_a_short_retry_window(self) -> None:
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)
        calls = 0

        def compute() -> CacheOutcome[str]:
            nonlocal calls
            calls += 1
            return CacheOutcome(value="live", healthy=True)

        first, first_hit = cache.get_or_compute("breadth", "2026-07-25", compute)
        clock.advance(10_000.0)  # long past any short retry window
        second, second_hit = cache.get_or_compute("breadth", "2026-07-25", compute)

        self.assertEqual((first, first_hit), ("live", False))
        self.assertEqual((second, second_hit), ("live", True))
        self.assertEqual(calls, 1)

    def test_an_unhealthy_result_is_replayed_inside_its_retry_window(self) -> None:
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)
        calls = 0

        def compute() -> CacheOutcome[str]:
            nonlocal calls
            calls += 1
            return CacheOutcome(value="unavailable", healthy=False)

        first, first_hit = cache.get_or_compute("breadth", "2026-07-25", compute)
        clock.advance(59.0)  # still inside the retry window
        second, second_hit = cache.get_or_compute("breadth", "2026-07-25", compute)

        self.assertEqual((first, first_hit), ("unavailable", False))
        self.assertEqual((second, second_hit), ("unavailable", True))
        self.assertEqual(calls, 1)

    def test_an_unhealthy_result_is_recomputed_once_its_retry_window_elapses(
        self,
    ) -> None:
        # The reviewer's scenario: an outage caches "unavailable" briefly,
        # never for the whole trading date, so a recovered gateway heals the
        # next read past the retry window instead of waiting for rollover.
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)
        outcomes = iter(
            [
                CacheOutcome(value="unavailable", healthy=False),
                CacheOutcome(value="live", healthy=True),
            ]
        )
        calls = 0

        def compute() -> CacheOutcome[str]:
            nonlocal calls
            calls += 1
            return next(outcomes)

        during_outage, _ = cache.get_or_compute("breadth", "2026-07-25", compute)
        clock.advance(61.0)
        after_recovery, after_hit = cache.get_or_compute("breadth", "2026-07-25", compute)

        self.assertEqual(during_outage, "unavailable")
        self.assertEqual((after_recovery, after_hit), ("live", False))
        self.assertEqual(calls, 2)

    def test_a_key_change_always_forces_a_recompute_regardless_of_health(
        self,
    ) -> None:
        cache = MarketUniverseCache()
        calls = 0

        def compute() -> CacheOutcome[str]:
            nonlocal calls
            calls += 1
            return CacheOutcome(value="live", healthy=True)

        cache.get_or_compute("breadth", "day-1", compute)
        cache.get_or_compute("breadth", "day-2", compute)

        self.assertEqual(calls, 2)

    def test_independent_slots_never_share_a_retry_clock(self) -> None:
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)

        cache.get_or_compute(
            "breadth", "2026-07-25", lambda: CacheOutcome(value="b", healthy=False)
        )
        sector_value, sector_hit = cache.get_or_compute(
            "sector", "2026-07-25", lambda: CacheOutcome(value="s", healthy=True)
        )

        self.assertEqual((sector_value, sector_hit), ("s", False))


if __name__ == "__main__":
    unittest.main()
