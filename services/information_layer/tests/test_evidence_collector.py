from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta, timezone

from information_layer import ClaimStatus, EvidenceEvent, SourceProvenance
from information_layer.feeds import (
    FeedConfig,
    GenericFeedAdapter,
    HttpRequest,
    HttpResponse,
    KeywordMapping,
)
from information_layer.feeds.collector import (
    FRESHNESS_ATTRIBUTE,
    STALE_ATTRIBUTE,
    EvidenceCollector,
    EvidenceUnavailable,
    freshness_seconds,
)


UTC = timezone.utc
FIRST_POLL = datetime(2026, 7, 25, 14, 0, tzinfo=UTC)
SECOND_POLL = datetime(2026, 7, 25, 14, 5, tzinfo=UTC)


def entry(identity: bytes, title: bytes, published: bytes) -> bytes:
    return (
        b"<entry><id>" + identity + b"</id>"
        b"<title>" + title + b"</title>"
        b"<summary>Details follow.</summary>"
        b'<link rel="alternate" href="https://feeds.example.test/'
        + identity
        + b'"/>'
        b"<published>" + published + b"</published>"
        b"<updated>" + published + b"</updated></entry>"
    )


def atom(*entries: bytes) -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<feed xmlns="http://www.w3.org/2005/Atom">'
        + b"".join(entries)
        + b"</feed>"
    )


NVDA_ENTRY = entry(
    b"item-1",
    b"NVIDIA supplier raises shipment forecast",
    b"2026-07-25T13:55:00Z",
)
EARLIER_ENTRY = entry(
    b"item-0",
    b"NVIDIA opens a design centre",
    b"2026-07-25T13:50:00Z",
)
MACRO_ENTRY = entry(
    b"item-macro",
    b"Consumer inflation cooled in June",
    b"2026-07-25T13:52:00Z",
)
LATER_ENTRY = entry(
    b"item-2",
    b"NVIDIA lifts full-year outlook",
    b"2026-07-25T14:02:00Z",
)
EMPTY_FEED = atom()


class FakeTransport:
    def __init__(self, *answers: HttpResponse | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[HttpRequest] = []

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self.answers:
            raise AssertionError("no fake answer queued")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


def response(
    body: bytes = EMPTY_FEED,
    *,
    status: int = 200,
    retrieved_at: datetime = FIRST_POLL,
) -> HttpResponse:
    return HttpResponse(
        status_code=status,
        headers=(),
        body=body,
        retrieved_at=retrieved_at,
    )


def config(adapter_id: str = "example-feed") -> FeedConfig:
    return FeedConfig(
        adapter_id=adapter_id,
        feed_url="https://feeds.example.test/atom.xml",
        allowed_hosts=("feeds.example.test",),
        publisher_id="example-news",
        publisher_name="Example News",
        source_type="official_announcement",
        reliability=0.8,
        user_agent="us-stock-helper/0.1 (contact placeholder)",
        robots_allowed=True,
        minimum_poll_interval_seconds=60.0,
        symbol_mappings=(KeywordMapping("NVDA", ("nvidia",), 0.9),),
        macro_mappings=(KeywordMapping("INFLATION", ("inflation",), 0.9),),
    )


def collector(
    transport: FakeTransport,
    clock: Clock,
    **overrides: float,
) -> EvidenceCollector:
    return EvidenceCollector(
        (GenericFeedAdapter(config(), transport),),
        clock=clock,
        **overrides,  # type: ignore[arg-type]
    )


def attribute(event: EvidenceEvent, name: str) -> str | None:
    return dict(event.attributes).get(name)


def sample_event(available_at: datetime) -> EvidenceEvent:
    return EvidenceEvent.create(
        event_id="e1",
        claim_key="k1",
        headline="Headline",
        summary="Summary",
        provenance=SourceProvenance(
            source_id="s1",
            publisher_id="p1",
            publisher_name="Publisher",
            canonical_url="https://example.test/a",
            source_type="official_announcement",
            reliability=0.9,
        ),
        event_time=available_at,
        published_at=available_at,
        first_seen_at=available_at,
        available_at=available_at,
        retrieved_at=available_at,
        claim_status=ClaimStatus.REPORTED,
        sentiment=0.0,
        confidence=0.9,
    )


class OrderingTests(unittest.TestCase):
    def test_evidence_is_ordered_newest_first_by_availability(self) -> None:
        transport = FakeTransport(
            response(atom(NVDA_ENTRY), retrieved_at=FIRST_POLL),
            response(atom(LATER_ENTRY), retrieved_at=SECOND_POLL),
        )
        clock = Clock(FIRST_POLL)
        subject = collector(transport, clock)

        subject.refresh()
        clock.now = SECOND_POLL
        subject.refresh()

        self.assertEqual(
            [item.available_at for item in subject.evidence()],
            [SECOND_POLL, FIRST_POLL],
        )

    def test_evidence_from_one_poll_falls_back_to_publication_time(self) -> None:
        # A single poll stamps every entry with the same availability, so the
        # order the publisher stated is the only remaining truth about which
        # of them came first.
        subject = collector(
            FakeTransport(response(atom(EARLIER_ENTRY, NVDA_ENTRY))),
            Clock(FIRST_POLL),
        )

        subject.refresh()

        self.assertEqual(
            [item.published_at.minute for item in subject.evidence()],
            [55, 50],
        )


class FreshnessTests(unittest.TestCase):
    def test_freshness_measures_availability_to_the_moment_of_reading(self) -> None:
        self.assertEqual(
            freshness_seconds(
                sample_event(FIRST_POLL),
                FIRST_POLL + timedelta(minutes=10),
            ),
            600.0,
        )

    def test_reading_evidence_before_it_was_available_is_a_defect(self) -> None:
        with self.assertRaises(ValueError):
            freshness_seconds(
                sample_event(FIRST_POLL),
                FIRST_POLL - timedelta(seconds=1),
            )

    def test_every_returned_item_carries_its_own_freshness(self) -> None:
        clock = Clock(FIRST_POLL)
        subject = collector(FakeTransport(response(atom(NVDA_ENTRY))), clock)

        subject.refresh()
        clock.advance(minutes=10)

        self.assertEqual(
            attribute(subject.evidence()[0], FRESHNESS_ATTRIBUTE),
            "600",
        )

    def test_freshness_is_recomputed_per_read_not_frozen_at_collection(
        self,
    ) -> None:
        clock = Clock(FIRST_POLL)
        subject = collector(FakeTransport(response(atom(NVDA_ENTRY))), clock)

        subject.refresh()
        clock.advance(minutes=10)
        first = subject.evidence()
        clock.advance(minutes=20)
        second = subject.evidence()

        self.assertEqual(attribute(first[0], FRESHNESS_ATTRIBUTE), "600")
        self.assertEqual(attribute(second[0], FRESHNESS_ATTRIBUTE), "1800")


class StalenessTests(unittest.TestCase):
    def test_evidence_past_the_window_is_marked_rather_than_dropped(self) -> None:
        clock = Clock(FIRST_POLL)
        subject = collector(
            FakeTransport(response(atom(NVDA_ENTRY))),
            clock,
            stale_after_seconds=600.0,
        )

        subject.refresh()
        clock.advance(minutes=20)
        events = subject.evidence()

        self.assertEqual(len(events), 1)
        self.assertEqual(attribute(events[0], STALE_ATTRIBUTE), "true")

    def test_evidence_inside_the_window_says_so_explicitly(self) -> None:
        clock = Clock(FIRST_POLL)
        subject = collector(
            FakeTransport(response(atom(NVDA_ENTRY))),
            clock,
            stale_after_seconds=600.0,
        )

        subject.refresh()
        clock.advance(minutes=5)

        self.assertEqual(
            attribute(subject.evidence()[0], STALE_ATTRIBUTE),
            "false",
        )

    def test_a_retention_bound_below_the_staleness_window_is_refused(self) -> None:
        # Retention exists to bound memory. Setting it inside the staleness
        # window would delete the very items the window promises to mark.
        with self.assertRaises(ValueError):
            collector(
                FakeTransport(),
                Clock(FIRST_POLL),
                stale_after_seconds=600.0,
                retention_seconds=300.0,
            )


class FailureTests(unittest.TestCase):
    def test_an_unreachable_source_fails_loudly_instead_of_answering_nothing(
        self,
    ) -> None:
        subject = collector(
            FakeTransport(OSError("connection refused")),
            Clock(FIRST_POLL),
        )

        with self.assertRaises(EvidenceUnavailable):
            subject.collect()

    def test_a_retryable_upstream_status_is_a_failure_not_an_empty_answer(
        self,
    ) -> None:
        for status in (429, 503):
            with self.subTest(status=status):
                subject = collector(
                    FakeTransport(response(status=status)),
                    Clock(FIRST_POLL),
                )

                with self.assertRaises(EvidenceUnavailable):
                    subject.collect()

    def test_a_refused_or_unparsable_feed_is_a_failure(self) -> None:
        answers = {
            "refused": response(status=404),
            "unparsable": response(b"not a feed"),
        }
        for name, answer in answers.items():
            with self.subTest(answer=name):
                subject = collector(FakeTransport(answer), Clock(FIRST_POLL))

                with self.assertRaises(EvidenceUnavailable):
                    subject.collect()

    def test_a_source_with_nothing_to_report_is_not_a_failure(self) -> None:
        subject = collector(FakeTransport(response(EMPTY_FEED)), Clock(FIRST_POLL))

        self.assertEqual(subject.collect(), ())

    def test_the_failure_names_the_source_that_could_not_be_read(self) -> None:
        subject = EvidenceCollector(
            (
                GenericFeedAdapter(
                    config("working-feed"),
                    FakeTransport(response(atom(NVDA_ENTRY))),
                ),
                GenericFeedAdapter(
                    config("broken-feed"),
                    FakeTransport(OSError("connection refused")),
                ),
            ),
            clock=Clock(FIRST_POLL),
        )

        with self.assertRaises(EvidenceUnavailable) as failure:
            subject.refresh()

        self.assertEqual(
            [item.source_id for item in failure.exception.failures],
            ["broken-feed"],
        )

    def test_one_reachable_source_cannot_answer_for_a_broken_one(self) -> None:
        # Half the sources answering looks exactly like all of them answering
        # quietly, and the caller has no way to tell the two apart.
        subject = EvidenceCollector(
            (
                GenericFeedAdapter(
                    config("working-feed"),
                    FakeTransport(response(atom(NVDA_ENTRY))),
                ),
                GenericFeedAdapter(
                    config("broken-feed"),
                    FakeTransport(response(status=503)),
                ),
            ),
            clock=Clock(FIRST_POLL),
        )

        with self.assertRaises(EvidenceUnavailable):
            subject.collect()

    def test_a_partial_read_is_offered_only_together_with_its_failures(
        self,
    ) -> None:
        # Refusing everything when one source times out took every symbol in
        # the product offline at once, which is a worse answer than a named
        # gap. The gap is only offered through a call that hands back the
        # failures in the same breath, so a caller cannot receive a thinner
        # answer without also receiving the reason it is thinner.
        subject = EvidenceCollector(
            (
                GenericFeedAdapter(
                    config("working-feed"),
                    FakeTransport(response(atom(NVDA_ENTRY))),
                ),
                GenericFeedAdapter(
                    config("broken-feed"),
                    FakeTransport(response(status=503)),
                ),
            ),
            clock=Clock(FIRST_POLL),
        )

        events, failures = subject.collect_with_failures()

        self.assertEqual(len(events), 1)
        self.assertEqual([failure.source_id for failure in failures], ["broken-feed"])

    def test_every_source_failing_is_still_refused_outright(self) -> None:
        # Nothing was read at all, so there is no partial answer to qualify —
        # returning an empty tuple here would be indistinguishable from a quiet
        # market, which is the confusion this whole design exists to prevent.
        subject = EvidenceCollector(
            (
                GenericFeedAdapter(
                    config("broken-feed"),
                    FakeTransport(response(status=503)),
                ),
            ),
            clock=Clock(FIRST_POLL),
        )

        with self.assertRaises(EvidenceUnavailable):
            subject.collect_with_failures()

    def test_a_collector_without_a_source_cannot_be_built(self) -> None:
        # No source configured is a deployment mistake, and an empty answer
        # would present it as a quiet market.
        with self.assertRaises(ValueError):
            EvidenceCollector((), clock=Clock(FIRST_POLL))


class CacheTests(unittest.TestCase):
    def test_a_throttled_source_serves_what_it_already_collected(self) -> None:
        transport = FakeTransport(response(atom(NVDA_ENTRY)))
        clock = Clock(FIRST_POLL)
        subject = collector(transport, clock)

        first = subject.collect()
        clock.advance(seconds=10)
        second = subject.collect()

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(
            [item.event_id for item in first],
            [item.event_id for item in second],
        )

    def test_an_unchanged_source_keeps_the_evidence_already_collected(self) -> None:
        transport = FakeTransport(
            response(atom(NVDA_ENTRY)),
            response(status=304, retrieved_at=SECOND_POLL),
        )
        clock = Clock(FIRST_POLL)
        subject = collector(transport, clock)

        subject.collect()
        clock.now = SECOND_POLL
        second = subject.collect()

        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(second), 1)


class _RaceDict(dict):
    """Wraps the live store dict so its `.values()` pauses right after
    yielding its first item, deterministically handing control to a
    concurrent writer before the real dict iterator is asked for its next
    item -- the exact window `evidence()`'s iteration and `_poll_sources`'s
    store writes must not both occupy unsynchronized under a
    ThreadingHTTPServer. Real threads and `Event`s stand in for the two
    concurrent requests; nothing here depends on sleep-based timing.
    """

    def __init__(self, *args: object, on_first_pause, wait_for: threading.Event, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._on_first_pause = on_first_pause
        self._wait_for = wait_for

    def values(self):  # type: ignore[override]
        iterator = iter(dict.values(self))
        first = next(iterator)
        yield first
        self._on_first_pause()
        self._wait_for.wait(timeout=1.0)
        yield from iterator


class ThreadSafetyTests(unittest.TestCase):
    """Reproduces the collector.py:158/171-175/234 races a ThreadingHTTPServer
    exposes: one request iterating `evidence()` while another request's
    `_poll_sources()` inserts into the same shared `_store` dict.
    """

    def test_a_concurrent_poll_cannot_corrupt_a_read_in_progress(self) -> None:
        transport = FakeTransport(
            response(atom(EARLIER_ENTRY), retrieved_at=FIRST_POLL),
            response(atom(NVDA_ENTRY), retrieved_at=SECOND_POLL),
        )
        clock = Clock(FIRST_POLL)
        subject = collector(transport, clock)
        subject.refresh()  # seeds the store with one item to iterate
        clock.now = SECOND_POLL  # past the adapter's minimum_poll_interval

        reader_paused = threading.Event()
        writer_done = threading.Event()
        subject._store = _RaceDict(
            subject._store,
            on_first_pause=reader_paused.set,
            wait_for=writer_done,
        )

        errors: list[BaseException] = []

        def read() -> None:
            try:
                subject.evidence(symbols=("NVDA",))
            except BaseException as error:  # noqa: BLE001 - captured for the assertion
                errors.append(error)

        def write() -> None:
            reader_paused.wait(timeout=5)
            # Stands in for a concurrent request's `_poll_sources()` commit
            # landing on the same store while the first request's read is
            # mid-iteration.
            subject._poll_sources()
            writer_done.set()

        reader = threading.Thread(target=read)
        writer = threading.Thread(target=write)
        reader.start()
        writer.start()
        reader.join(timeout=5)
        writer.join(timeout=5)

        self.assertFalse(
            errors,
            f"a concurrent store write corrupted the read in progress: {errors}",
        )
        self.assertEqual(len(subject._store), 2)


class ScopeTests(unittest.TestCase):
    def test_a_symbol_request_keeps_market_wide_context_alongside_it(self) -> None:
        subject = collector(
            FakeTransport(response(atom(NVDA_ENTRY, MACRO_ENTRY))),
            Clock(FIRST_POLL),
        )

        self.assertEqual(len(subject.collect(symbols=("NVDA",))), 2)

    def test_evidence_about_another_symbol_is_left_out(self) -> None:
        subject = collector(
            FakeTransport(response(atom(NVDA_ENTRY, MACRO_ENTRY))),
            Clock(FIRST_POLL),
        )

        events = subject.collect(symbols=("AAPL",))

        self.assertEqual([item.macro_tags for item in events], [("INFLATION",)])


if __name__ == "__main__":
    unittest.main()
