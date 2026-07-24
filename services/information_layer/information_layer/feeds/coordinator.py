from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

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


class PollingCoordinator:
    """In-memory coordinator; persistence can serialize the same state fields."""

    def __init__(self) -> None:
        self._states: dict[str, _AdapterState] = {}

    def poll(
        self,
        adapter: GenericFeedAdapter,
        *,
        since: datetime,
        until: datetime,
    ) -> FeedPollResult:
        state = self._states.setdefault(adapter.adapter_id, _AdapterState())
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


def _is_retryable(status_code: int) -> bool:
    return status_code in {408, 425, 429} or status_code >= 500
