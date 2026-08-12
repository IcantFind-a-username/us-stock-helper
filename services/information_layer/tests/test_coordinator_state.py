from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from information_layer.feeds import (
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
