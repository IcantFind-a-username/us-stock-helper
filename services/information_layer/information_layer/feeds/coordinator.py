from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable

from ..models import EvidenceEvent
from .generic import (
    CacheValidators,
    FeedPollMetadata,
    FeedPollResult,
    GenericFeedAdapter,
)


@dataclass(frozen=True, slots=True)
class _PublishedRecord:
    content_hash: str
    event_id: str
    revision_number: int


@dataclass(slots=True)
class _AdapterState:
    validators: CacheValidators = CacheValidators()
    consecutive_failures: int = 0
    published: dict[str, _PublishedRecord] = field(default_factory=dict)
    last_polled_at: datetime | None = None


class PollingCoordinator:
    """Tracks what each feed has already published, and how recently it was asked.

    Both halves matter operationally. Without the published record, a restart
    re-announces every item still in the feed as if it had just happened.
    Without the interval, a caller in a loop hammers the source — SEC EDGAR and
    most wires block clients that ignore their published limits.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> None:
        self._states: dict[str, _AdapterState] = {}
        self._clock = clock
        # Guards the throttle check-and-reserve and the post-poll commit, so
        # two ThreadingHTTPServer requests racing on the same adapter cannot
        # both read a stale last_polled_at and both reach the network. Never
        # held across adapter.poll() itself -- that is the network call.
        self._lock = threading.Lock()

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Any,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    ) -> "PollingCoordinator":
        """Restore from a plain JSON structure, rejecting anything malformed.

        Loading only what parses would drop a feed's published record silently,
        and that feed would then re-announce its whole backlog.
        """

        if not isinstance(snapshot, dict):
            raise ValueError("coordinator snapshot must be an object")
        coordinator = cls(clock=clock)
        for adapter_id, raw in snapshot.items():
            if not isinstance(raw, dict):
                raise ValueError(f"state for {adapter_id!r} must be an object")
            published_raw = raw.get("published", {})
            if not isinstance(published_raw, dict):
                raise ValueError(f"published record for {adapter_id!r} is malformed")
            published: dict[str, _PublishedRecord] = {}
            for claim_key, record in published_raw.items():
                if not isinstance(record, dict):
                    raise ValueError(f"published entry for {claim_key!r} is malformed")
                try:
                    published[claim_key] = _PublishedRecord(
                        content_hash=str(record["content_hash"]),
                        event_id=str(record["event_id"]),
                        revision_number=int(record["revision_number"]),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"published entry for {claim_key!r} is incomplete"
                    ) from error
            last_polled = raw.get("last_polled_at")
            coordinator._states[adapter_id] = _AdapterState(
                validators=CacheValidators(
                    etag=raw.get("etag"),
                    last_modified=raw.get("last_modified"),
                ),
                consecutive_failures=int(raw.get("consecutive_failures", 0)),
                published=published,
                last_polled_at=(
                    datetime.fromisoformat(last_polled) if last_polled else None
                ),
            )
        return coordinator

    def snapshot(self) -> dict[str, Any]:
        """A JSON-serializable record of what each feed has already published.

        Holds the same lock as poll()'s reserve/commit sections: a snapshot
        taken for persistence while another request polls must not iterate a
        dict that changes size mid-read, and must not mix pre- and
        post-commit validators for one adapter.
        """

        with self._lock:
            return {
                adapter_id: {
                    "etag": state.validators.etag,
                    "last_modified": state.validators.last_modified,
                    "consecutive_failures": state.consecutive_failures,
                    "last_polled_at": (
                        state.last_polled_at.isoformat()
                        if state.last_polled_at
                        else None
                    ),
                    "published": {
                        claim_key: {
                            "content_hash": record.content_hash,
                            "event_id": record.event_id,
                            "revision_number": record.revision_number,
                        }
                        for claim_key, record in state.published.items()
                    },
                }
                for adapter_id, state in self._states.items()
            }

    def poll(
        self,
        adapter: GenericFeedAdapter,
        *,
        since: datetime,
        until: datetime,
    ) -> FeedPollResult:
        # Check-and-reserve happens as one atomic step under the lock: two
        # requests racing on the same adapter can no longer both read a
        # last_polled_at set before either of them and both decide "we may
        # poll". Whichever gets the lock first reserves the moment; the
        # other is throttled by the same check every solo caller already
        # went through. A poll reserved here and never committed (the
        # network call below raises, or times out) still keeps the
        # reservation -- exactly as a successful poll always has -- so a
        # failure narrows the next attempt to the ordinary interval instead
        # of leaving nothing recorded and inviting an immediate retry storm.
        # It is a timestamp, not a flag that needs an explicit release, so
        # it can never block polling forever: once the interval has
        # genuinely passed, the next call reserves cleanly regardless of
        # how the previous one ended.
        with self._lock:
            state = self._states.setdefault(adapter.adapter_id, _AdapterState())
            now = self._clock()
            interval = adapter.config.minimum_poll_interval_seconds
            if state.last_polled_at is not None:
                elapsed = (now - state.last_polled_at).total_seconds()
                if elapsed < interval:
                    # Report the skip rather than an empty success: "we did
                    # not ask" must not read as "nothing happened".
                    return FeedPollResult(
                        events=(),
                        metadata=_skipped_metadata(now),
                        throttled=True,
                        retry_after_seconds=interval - elapsed,
                    )
            state.last_polled_at = now
            validators = state.validators
            consecutive_failures = state.consecutive_failures

        # The network call runs outside the lock: it can take seconds, and
        # holding the lock across it would stall every other adapter's
        # throttle check and commit behind one slow publisher.
        batch = adapter.poll(
            since=since,
            until=until,
            validators=validators,
            consecutive_failures=consecutive_failures,
        )

        # Commit is its own atomic step. Reservation already serialized who
        # is allowed to poll this adapter during this interval, so at most
        # one caller ever reaches this point per interval window -- the lock
        # here protects readers of `published`/`validators` (a snapshot(),
        # say) from observing a partial write, not from a second committer.
        with self._lock:
            state = self._states[adapter.adapter_id]
            if _is_retryable(batch.metadata.status_code):
                state.consecutive_failures += 1
                return FeedPollResult(events=(), metadata=batch.metadata)

            state.consecutive_failures = 0
            state.validators = CacheValidators(
                etag=batch.metadata.etag or state.validators.etag,
                last_modified=(
                    batch.metadata.last_modified or state.validators.last_modified
                ),
            )
            published: list[EvidenceEvent] = []
            for item in batch.events:
                previous = state.published.get(item.claim_key)
                if previous is not None and previous.content_hash == item.content_hash:
                    continue
                if previous is not None:
                    item = replace(
                        item,
                        revision_of=previous.event_id,
                        revision_number=previous.revision_number + 1,
                        revised_at=item.available_at,
                    )
                state.published[item.claim_key] = _PublishedRecord(
                    content_hash=item.content_hash,
                    event_id=item.event_id,
                    revision_number=item.revision_number,
                )
                published.append(item)
            return FeedPollResult(events=tuple(published), metadata=batch.metadata)


def _skipped_metadata(now: datetime) -> FeedPollMetadata:
    return FeedPollMetadata(
        status_code=0,
        retrieved_at=now,
        etag=None,
        last_modified=None,
        retry_after_seconds=None,
        recommended_delay_seconds=0.0,
        not_modified=False,
        future_entries_rejected=0,
    )


def _is_retryable(status_code: int) -> bool:
    return status_code in {408, 425, 429} or status_code >= 500
