from __future__ import annotations

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
        """A JSON-serializable record of what each feed has already published."""

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
        state = self._states.setdefault(adapter.adapter_id, _AdapterState())
        now = self._clock()
        interval = adapter.config.minimum_poll_interval_seconds
        if state.last_polled_at is not None:
            elapsed = (now - state.last_polled_at).total_seconds()
            if elapsed < interval:
                # Report the skip rather than an empty success: "we did not
                # ask" must not read as "nothing happened".
                return FeedPollResult(
                    events=(),
                    metadata=_skipped_metadata(now),
                    throttled=True,
                    retry_after_seconds=interval - elapsed,
                )
        state.last_polled_at = now
        batch = adapter.poll(
            since=since,
            until=until,
            validators=state.validators,
            consecutive_failures=state.consecutive_failures,
        )
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
