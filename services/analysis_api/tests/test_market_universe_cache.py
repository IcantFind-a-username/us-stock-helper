"""MarketUniverseCache: retention policy and the single-flight discipline.

A named slot's value survives for the whole trading date only when nothing
about computing it failed; a failure or a partial universe instead earns a
short, monotonic-clock-based retry window, so a transient gateway restart
heals inside the same session rather than freezing until the next day's
16:00 ET rollover. `FakeMonotonic` lets every test cross that boundary by an
explicit `advance()` call -- no real sleep, no timing flakiness.

A concurrent miss on the same slot must never make a follower wait behind
the leader's own network I/O: `compute()` runs with the lock released, one
caller is elected leader, and everyone else lands on `pending()` instead of
blocking. `SingleFlightTests` pins that with real threads and hooks/events,
never a sleep, mirroring the house style `test_coordinator_state.py` already
uses for the same shape of race.
"""

from __future__ import annotations

import threading
import unittest
from datetime import UTC, datetime

from us_stock_helper_analysis_api.market_universe_cache import (
    CacheOutcome,
    MarketUniverseCache,
)


AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)
LATER = datetime(2026, 7, 25, 16, 5, tzinfo=UTC)


class FakeMonotonic:
    """A test-controlled stand-in for `time.monotonic`."""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _no_pending(started_at: datetime) -> str:  # pragma: no cover - shape only
    raise AssertionError(f"no follower expected, but one landed on pending() at {started_at}")


class RetentionPolicyTests(unittest.TestCase):
    def test_a_healthy_result_survives_long_past_a_short_retry_window(self) -> None:
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)
        calls = 0

        def compute() -> CacheOutcome[str]:
            nonlocal calls
            calls += 1
            return CacheOutcome(value="live", healthy=True)

        first, first_hit = cache.get_or_compute(
            "breadth", "2026-07-25", AS_OF, compute, _no_pending
        )
        clock.advance(10_000.0)  # long past any short retry window
        second, second_hit = cache.get_or_compute(
            "breadth", "2026-07-25", LATER, compute, _no_pending
        )

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

        first, first_hit = cache.get_or_compute(
            "breadth", "2026-07-25", AS_OF, compute, _no_pending
        )
        clock.advance(59.0)  # still inside the retry window
        second, second_hit = cache.get_or_compute(
            "breadth", "2026-07-25", LATER, compute, _no_pending
        )

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

        during_outage, _ = cache.get_or_compute(
            "breadth", "2026-07-25", AS_OF, compute, _no_pending
        )
        clock.advance(61.0)
        after_recovery, after_hit = cache.get_or_compute(
            "breadth", "2026-07-25", LATER, compute, _no_pending
        )

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

        cache.get_or_compute("breadth", "day-1", AS_OF, compute, _no_pending)
        cache.get_or_compute("breadth", "day-2", AS_OF, compute, _no_pending)

        self.assertEqual(calls, 2)

    def test_independent_slots_never_share_a_retry_clock(self) -> None:
        clock = FakeMonotonic()
        cache = MarketUniverseCache(retry_after_seconds=60.0, monotonic=clock)

        cache.get_or_compute(
            "breadth",
            "2026-07-25",
            AS_OF,
            lambda: CacheOutcome(value="b", healthy=False),
            _no_pending,
        )
        sector_value, sector_hit = cache.get_or_compute(
            "sector",
            "2026-07-25",
            AS_OF,
            lambda: CacheOutcome(value="s", healthy=True),
            _no_pending,
        )

        self.assertEqual((sector_value, sector_hit), ("s", False))


class SingleFlightTests(unittest.TestCase):
    def test_a_follower_never_waits_behind_the_leaders_own_compute(self) -> None:
        entered_compute = threading.Event()
        release_compute = threading.Event()
        cache = MarketUniverseCache()

        def leader_compute() -> CacheOutcome[str]:
            entered_compute.set()
            # A locked cache would keep a concurrent caller queued behind
            # this wait; the fix must let a follower answer without it.
            finished_in_time = release_compute.wait(timeout=5)
            if not finished_in_time:
                raise AssertionError("leader never released -- test bug")
            return CacheOutcome(value="live", healthy=True)

        leader_result: dict[str, object] = {}

        def run_leader() -> None:
            leader_result["value"] = cache.get_or_compute(
                "breadth", "2026-07-25", AS_OF, leader_compute, _no_pending
            )

        leader_thread = threading.Thread(target=run_leader)
        leader_thread.start()
        self.assertTrue(entered_compute.wait(timeout=5), "leader never entered compute")

        follower_value, follower_hit = cache.get_or_compute(
            "breadth",
            "2026-07-25",
            LATER,
            lambda: (_ for _ in ()).throw(  # pragma: no cover - must not run
                AssertionError("a follower must not run its own compute")
            ),
            lambda started_at: f"pending since {started_at.isoformat()}",
        )

        self.assertEqual(follower_value, "pending since 2026-07-25T16:00:00+00:00")
        self.assertTrue(follower_hit)

        release_compute.set()
        leader_thread.join(timeout=5)
        self.assertFalse(leader_thread.is_alive(), "leader thread never finished")
        self.assertEqual(leader_result["value"], ("live", False))

    def test_the_leader_commits_so_the_next_caller_gets_the_real_value(self) -> None:
        entered_compute = threading.Event()
        release_compute = threading.Event()
        cache = MarketUniverseCache()

        def leader_compute() -> CacheOutcome[str]:
            entered_compute.set()
            release_compute.wait(timeout=5)
            return CacheOutcome(value="live", healthy=True)

        leader_thread = threading.Thread(
            target=lambda: cache.get_or_compute(
                "breadth", "2026-07-25", AS_OF, leader_compute, _no_pending
            )
        )
        leader_thread.start()
        self.assertTrue(entered_compute.wait(timeout=5))
        release_compute.set()
        leader_thread.join(timeout=5)

        after, after_hit = cache.get_or_compute(
            "breadth", "2026-07-25", LATER, lambda: CacheOutcome(value="stale", healthy=True), _no_pending
        )

        self.assertEqual((after, after_hit), ("live", True))

    def test_a_slot_left_in_flight_by_a_raising_compute_admits_a_new_leader(
        self,
    ) -> None:
        # A compute that raises must not wedge the slot forever -- the next
        # caller has to be allowed to try again rather than being told
        # "pending" for an attempt that already died.
        cache = MarketUniverseCache()

        def failing_compute() -> CacheOutcome[str]:
            raise RuntimeError("gateway blew up mid-fetch")

        with self.assertRaises(RuntimeError):
            cache.get_or_compute("breadth", "2026-07-25", AS_OF, failing_compute, _no_pending)

        recovered, recovered_hit = cache.get_or_compute(
            "breadth",
            "2026-07-25",
            LATER,
            lambda: CacheOutcome(value="live", healthy=True),
            _no_pending,
        )

        self.assertEqual((recovered, recovered_hit), ("live", False))


if __name__ == "__main__":
    unittest.main()
