from __future__ import annotations

import json
import threading
import unittest
from datetime import datetime, timedelta, timezone

from information_layer.feeds import (
    CacheValidators,
    FeedConfig,
    GenericFeedAdapter,
    HttpResponse,
    PollingCoordinator,
)
from information_layer.models import ClaimStatus


UTC = timezone.utc
NOW = datetime(2026, 7, 25, 14, 0, tzinfo=UTC)

ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>urn:example:1</id>
    <title>NVDA supplier raises shipment forecast</title>
    <summary>Guidance was raised.</summary>
    <link rel="alternate" href="https://wire.example/1"/>
    <updated>2026-07-25T13:50:00Z</updated>
  </entry>
</feed>
"""


class FakeTransport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = list(responses)
        self.calls = 0

    def request(self, request: object) -> HttpResponse:
        self.calls += 1
        if not self.responses:
            raise AssertionError("no fake response queued")
        return self.responses[0] if len(self.responses) == 1 else self.responses.pop(0)


def response(body: bytes = ATOM, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status_code=status, headers=(), body=body, retrieved_at=NOW
    )


def adapter(transport: FakeTransport) -> GenericFeedAdapter:
    return GenericFeedAdapter(
        FeedConfig(
            adapter_id="wire",
            feed_url="https://wire.example/feed.atom",
            allowed_hosts=("wire.example",),
            publisher_id="wire",
            publisher_name="Wire",
            source_type="wire",
            reliability=0.9,
            user_agent="USStockHelper/0.1 research@example.test",
            claim_status=ClaimStatus.REPORTED,
            robots_allowed=True,
            minimum_poll_interval_seconds=60.0,
        ),
        transport,
    )


class PollIntervalTests(unittest.TestCase):
    def test_a_second_poll_inside_the_interval_does_not_reach_the_network(
        self,
    ) -> None:
        # SEC and most wires block clients that ignore their rate limits, and
        # the configured interval was validated but never enforced.
        transport = FakeTransport(response())
        clock = iter([NOW, NOW + timedelta(seconds=10)])
        coordinator = PollingCoordinator(clock=lambda: next(clock))
        feed = adapter(transport)

        first = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        second = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        self.assertEqual(transport.calls, 1)
        self.assertEqual(len(first.events), 1)
        self.assertEqual(second.events, ())
        self.assertTrue(second.throttled)

    def test_a_throttled_result_is_not_mistaken_for_a_quiet_feed(self) -> None:
        transport = FakeTransport(response())
        clock = iter([NOW, NOW + timedelta(seconds=10)])
        coordinator = PollingCoordinator(clock=lambda: next(clock))
        feed = adapter(transport)

        coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        throttled = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        # Without this flag "we did not ask" looks exactly like "nothing
        # happened", and the reader draws a conclusion from a poll that never
        # took place.
        self.assertTrue(throttled.throttled)
        self.assertGreater(throttled.retry_after_seconds, 0.0)

    def test_polling_resumes_once_the_interval_has_passed(self) -> None:
        transport = FakeTransport(response())
        clock = iter([NOW, NOW + timedelta(seconds=61)])
        coordinator = PollingCoordinator(clock=lambda: next(clock))
        feed = adapter(transport)

        coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        second = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        self.assertEqual(transport.calls, 2)
        self.assertFalse(second.throttled)


class _HookedState:
    """Stands in for the coordinator's private `_AdapterState` so the very
    first read of `last_polled_at` can be paused deterministically. A second
    real thread is then driven up to (or into) its own reservation attempt
    before the paused caller resumes with the value it already captured --
    reproducing the exact check-then-set interleaving that lets two threads
    both see a stale `last_polled_at` and both reach the network.
    """

    def __init__(self, *, on_first_read) -> None:
        self.validators = CacheValidators()
        self.consecutive_failures = 0
        self.published: dict[str, object] = {}
        self._last_polled_at: datetime | None = None
        self._on_first_read = on_first_read
        self._fired = False

    @property
    def last_polled_at(self) -> datetime | None:
        value = self._last_polled_at
        if not self._fired:
            self._fired = True
            self._on_first_read()
        return value

    @last_polled_at.setter
    def last_polled_at(self, value: datetime | None) -> None:
        self._last_polled_at = value


class ConcurrentPollTests(unittest.TestCase):
    """Reproduces coordinator.py:130-144: two ThreadingHTTPServer requests
    for the same adapter can both pass the throttle check before either
    writes `last_polled_at`, double-polling and bypassing
    minimum_poll_interval_seconds (an SEC rate-limit exposure).
    """

    def test_two_concurrent_first_polls_do_not_both_reach_the_network(self) -> None:
        transport = FakeTransport(response(), response())
        coordinator = PollingCoordinator(clock=lambda: NOW)
        feed = adapter(transport)

        reader_arrived = threading.Event()
        writer_done = threading.Event()

        def on_first_read() -> None:
            reader_arrived.set()
            writer_done.wait(timeout=1.0)

        coordinator._states["wire"] = _HookedState(on_first_read=on_first_read)

        def call_a() -> None:
            coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        def call_b() -> None:
            reader_arrived.wait(timeout=5)
            coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
            writer_done.set()

        thread_a = threading.Thread(target=call_a)
        thread_b = threading.Thread(target=call_b)
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)

        self.assertEqual(
            transport.calls,
            1,
            "two concurrent first polls both reached the network, "
            "bypassing minimum_poll_interval_seconds",
        )


class ReservationReleaseTests(unittest.TestCase):
    """Decides and pins the release semantics for a reservation whose poll
    then fails: the failed attempt still reserves the interval (a retry
    inside it is throttled, matching what a successful attempt would have
    done), but that reservation is a timestamp, not a stuck flag, so it
    never blocks polling permanently -- the next interval goes through.
    """

    def test_a_failed_poll_still_reserves_the_interval_but_not_forever(self) -> None:
        class ExplodingTransport:
            """Fails once, as a real connection blip would, then recovers --
            isolating "does a failure release the reservation" from "does
            the source stay reachable"."""

            def __init__(self) -> None:
                self.calls = 0

            def request(self, request: object) -> HttpResponse:
                self.calls += 1
                if self.calls == 1:
                    raise OSError("connection refused")
                return response()

        transport = ExplodingTransport()
        clock = iter([NOW, NOW + timedelta(seconds=10), NOW + timedelta(seconds=61)])
        coordinator = PollingCoordinator(clock=lambda: next(clock))
        feed = adapter(transport)

        with self.assertRaises(OSError):
            coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        # The failed attempt still reserved this moment: a retry inside the
        # interval is throttled exactly as a successful attempt would have
        # been, not free to hammer the source immediately after a failure.
        second = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        self.assertTrue(second.throttled)
        self.assertEqual(transport.calls, 1)

        # Once the interval has actually passed, polling resumes normally --
        # the reservation from the failed attempt does not block forever.
        third = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        self.assertFalse(third.throttled)
        self.assertEqual(transport.calls, 2)


class _PausingStates(dict):
    """A `_states` stand-in whose iteration pauses after the first entry so a
    concurrent poll can try to insert a new adapter state mid-snapshot. An
    unlocked snapshot then resumes iterating a dict that changed size."""

    def __init__(self, *args, on_first_item, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._on_first_item = on_first_item
        self._fired = False

    def items(self):  # type: ignore[override]
        view = super().items()

        def paused():
            for index, entry in enumerate(iter(view)):
                yield entry
                if index == 0 and not self._fired:
                    self._fired = True
                    self._on_first_item()

        return paused()


class SnapshotConsistencyTests(unittest.TestCase):
    """snapshot() is the persistence read; it must hold the same lock that
    protects poll()'s inserts, or a restore-time snapshot taken while another
    request polls raises `dictionary changed size during iteration`."""

    def test_snapshot_survives_a_concurrent_first_poll(self) -> None:
        transport = FakeTransport(response(), response())
        coordinator = PollingCoordinator(clock=lambda: NOW)
        feed = adapter(transport)

        snapshot_paused = threading.Event()
        poll_finished = threading.Event()

        def on_first_item() -> None:
            snapshot_paused.set()
            # Give the concurrent poll a full second to insert its state; a
            # locked snapshot keeps it queued and this wait simply times out.
            poll_finished.wait(timeout=1.0)

        seeded = coordinator.poll(
            feed, since=NOW - timedelta(hours=1), until=NOW
        )
        self.assertEqual(len(seeded.events), 1)
        coordinator._states = _PausingStates(
            coordinator._states, on_first_item=on_first_item
        )

        other = GenericFeedAdapter(
            FeedConfig(
                adapter_id="wire-2",
                feed_url="https://wire.example/feed2.atom",
                allowed_hosts=("wire.example",),
                publisher_id="wire",
                publisher_name="Wire",
                source_type="wire",
                reliability=0.9,
                user_agent="USStockHelper/0.1 research@example.test",
                claim_status=ClaimStatus.REPORTED,
                robots_allowed=True,
                minimum_poll_interval_seconds=60.0,
            ),
            transport,
        )

        captured: dict[str, object] = {}

        def take_snapshot() -> None:
            try:
                captured["snapshot"] = coordinator.snapshot()
            except RuntimeError as error:
                captured["error"] = error

        def insert_via_poll() -> None:
            snapshot_paused.wait(timeout=5)
            coordinator.poll(other, since=NOW - timedelta(hours=1), until=NOW)
            poll_finished.set()

        snapshot_thread = threading.Thread(target=take_snapshot)
        poll_thread = threading.Thread(target=insert_via_poll)
        snapshot_thread.start()
        poll_thread.start()
        snapshot_thread.join(timeout=10)
        poll_thread.join(timeout=10)

        self.assertNotIn(
            "error",
            captured,
            f"snapshot raised under a concurrent poll: {captured.get('error')}",
        )
        self.assertIn("wire", captured["snapshot"])  # type: ignore[operator]


class CoordinatorStateTests(unittest.TestCase):
    def test_a_restored_coordinator_does_not_republish_old_news(self) -> None:
        # Losing this state on restart re-announces every item in the feed as
        # if it had just happened, which is the worst possible alert flood.
        transport = FakeTransport(response())
        clock = iter([NOW, NOW + timedelta(hours=2)])
        coordinator = PollingCoordinator(clock=lambda: next(clock))
        feed = adapter(transport)

        first = coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)
        snapshot = json.loads(json.dumps(coordinator.snapshot()))

        restored = PollingCoordinator.from_snapshot(
            snapshot, clock=lambda: NOW + timedelta(hours=2)
        )
        again = restored.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        self.assertEqual(len(first.events), 1)
        self.assertEqual(again.events, ())

    def test_a_restored_coordinator_keeps_its_cache_validators(self) -> None:
        transport = FakeTransport(
            HttpResponse(
                status_code=200,
                headers=(
                    ("etag", '"abc"'),
                    ("last-modified", "Fri, 25 Jul 2026 13:50:00 GMT"),
                ),
                body=ATOM,
                retrieved_at=NOW,
            )
        )
        coordinator = PollingCoordinator(clock=lambda: NOW)
        feed = adapter(transport)
        coordinator.poll(feed, since=NOW - timedelta(hours=1), until=NOW)

        restored = PollingCoordinator.from_snapshot(
            coordinator.snapshot(), clock=lambda: NOW + timedelta(hours=2)
        )

        # Re-downloading everything after every restart is how a client gets
        # itself rate limited.
        self.assertEqual(restored.snapshot()["wire"]["etag"], '"abc"')

    def test_a_snapshot_is_plain_json(self) -> None:
        transport = FakeTransport(response())
        coordinator = PollingCoordinator(clock=lambda: NOW)
        coordinator.poll(adapter(transport), since=NOW - timedelta(hours=1), until=NOW)

        encoded = json.dumps(coordinator.snapshot())

        self.assertIn("wire", json.loads(encoded))

    def test_a_malformed_snapshot_is_rejected_not_partially_loaded(self) -> None:
        payloads = (
            {"wire": "not-a-record"},
            {"wire": {"published": 5}},
            [],
            # An entry missing a field would otherwise be skipped, and that
            # feed would re-announce the item it silently forgot.
            {"wire": {"published": {"k": {"event_id": "e"}}}},
            {"wire": {"published": {"k": {"content_hash": 1, "event_id": "e",
                                          "revision_number": "not-a-number"}}}},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    PollingCoordinator.from_snapshot(payload, clock=lambda: NOW)

    def test_an_empty_snapshot_restores_an_empty_coordinator(self) -> None:
        restored = PollingCoordinator.from_snapshot({}, clock=lambda: NOW)

        self.assertEqual(restored.snapshot(), {})


if __name__ == "__main__":
    unittest.main()
