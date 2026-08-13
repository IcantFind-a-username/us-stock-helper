"""Hold what the configured sources have actually said, and how old it is.

Two distinctions carry the whole module. The first is between a source that
answered with nothing and a source that could not be read: an empty answer is
a fact the decision chain may act on, an unread source is an absence of
knowledge, and collapsing them makes the "not enough evidence" gate meaningless
because it can no longer tell a quiet market from a broken feed. So every
unreachable, refused, throttled-by-the-publisher or unparsable source raises
rather than shrinking the result.

The second is between age and irrelevance. A feed publishes on its own
schedule, so evidence is routinely older than the request that reads it. Age is
therefore measured and attached to every item at read time; passing the
configured window marks an item, and never removes it, because the reader
deciding an old filing no longer matters is a judgement the reader has to be
allowed to make.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Sequence

from ..models import EvidenceEvent, _require_aware
from .coordinator import PollingCoordinator, _is_retryable
from .generic import GenericFeedAdapter
from .http import (
    FeedAccessError,
    FeedError,
    FeedParseError,
    ResponseTooLargeError,
)


FRESHNESS_ATTRIBUTE = "freshness_seconds"
STALE_ATTRIBUTE = "stale"

DEFAULT_LOOKBACK_SECONDS = 6 * 60 * 60.0
DEFAULT_STALE_AFTER_SECONDS = 24 * 60 * 60.0
DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60.0


@dataclass(frozen=True, slots=True)
class SourceFailure:
    source_id: str
    reason: str


class EvidenceUnavailable(FeedError):
    """At least one configured source could not be read at all.

    Carries the sources by name so an operator can act on it, and stays
    distinct from an empty result, which means every source was read and none
    of them had anything to report.
    """

    def __init__(self, failures: Sequence[SourceFailure]) -> None:
        self.failures = tuple(failures)
        listed = ", ".join(
            f"{item.source_id} ({item.reason})" for item in self.failures
        )
        super().__init__(f"evidence sources could not be read: {listed}")


def freshness_seconds(event: EvidenceEvent, as_of: datetime) -> float:
    """How long the item has been available at the moment it is being read."""

    _require_aware(as_of, "as_of")
    age = (as_of - event.available_at).total_seconds()
    if age < 0:
        raise ValueError(
            "evidence cannot be read before the moment it became available"
        )
    return age


class EvidenceCollector:
    def __init__(
        self,
        adapters: Iterable[GenericFeedAdapter],
        *,
        coordinator: PollingCoordinator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
        lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        retention_seconds: float = DEFAULT_RETENTION_SECONDS,
    ) -> None:
        self._adapters = tuple(adapters)
        if not self._adapters:
            raise ValueError("at least one source adapter is required")
        if lookback_seconds <= 0 or stale_after_seconds <= 0:
            raise ValueError("lookback and staleness windows must be positive")
        if retention_seconds <= stale_after_seconds:
            # Retention is a bound on this process's memory, not a statement
            # about relevance. Set inside the staleness window it would delete
            # the very items that window exists to mark.
            raise ValueError(
                "retention must outlast the staleness window it holds items for"
            )
        self._clock = clock
        self._coordinator = (
            PollingCoordinator(clock=clock) if coordinator is None else coordinator
        )
        self._lookback = timedelta(seconds=lookback_seconds)
        self._stale_after = stale_after_seconds
        self._retention = timedelta(seconds=retention_seconds)
        self._store: dict[str, EvidenceEvent] = {}

    @property
    def adapters(self) -> tuple[GenericFeedAdapter, ...]:
        return self._adapters

    @property
    def lookback_seconds(self) -> float:
        return self._lookback.total_seconds()

    @property
    def stale_after_seconds(self) -> float:
        return self._stale_after

    @property
    def retention_seconds(self) -> float:
        return self._retention.total_seconds()

    def refresh(self) -> None:
        """Ask every source once, honouring each source's own poll interval."""

        now = self._clock()
        since = now - self._lookback
        failures: list[SourceFailure] = []
        for adapter in self._adapters:
            try:
                result = self._coordinator.poll(adapter, since=since, until=now)
            except (FeedError, OSError) as error:
                failures.append(SourceFailure(adapter.adapter_id, _reason(error)))
                continue
            if result.throttled:
                # The publisher's own interval said not yet. What was collected
                # before is still what that source has said.
                continue
            if _is_retryable(result.metadata.status_code):
                failures.append(
                    SourceFailure(
                        adapter.adapter_id,
                        f"HTTP {result.metadata.status_code}",
                    )
                )
                continue
            for item in result.events:
                self._store[item.event_id] = item
        self._evict(now)
        if failures:
            raise EvidenceUnavailable(failures)

    def evidence(
        self,
        *,
        symbols: Iterable[str] = (),
    ) -> tuple[EvidenceEvent, ...]:
        """What has been collected, newest first, each stamped with its age."""

        as_of = self._clock()
        focus = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        selected = [
            item
            for item in self._store.values()
            if not focus or _is_in_scope(item, focus)
        ]
        selected.sort(key=lambda item: item.event_id)
        # One poll stamps every entry it returned with the same availability,
        # so the publisher's own publication time is the only thing left that
        # can order them.
        selected.sort(
            key=lambda item: (item.available_at, item.published_at),
            reverse=True,
        )
        return tuple(self._stamped(item, as_of) for item in selected)

    def collect(
        self,
        *,
        symbols: Iterable[str] = (),
    ) -> tuple[EvidenceEvent, ...]:
        self.refresh()
        return self.evidence(symbols=symbols)

    def _stamped(self, event: EvidenceEvent, as_of: datetime) -> EvidenceEvent:
        age = freshness_seconds(event, as_of)
        stale = age > self._stale_after
        return replace(
            event,
            attributes=event.attributes
            + (
                (FRESHNESS_ATTRIBUTE, f"{age:.0f}"),
                (STALE_ATTRIBUTE, "true" if stale else "false"),
            ),
        )

    def _evict(self, now: datetime) -> None:
        horizon = now - self._retention
        for event_id, item in list(self._store.items()):
            if item.available_at < horizon:
                del self._store[event_id]


def _is_in_scope(event: EvidenceEvent, focus: set[str]) -> bool:
    if any(symbol in focus and score > 0 for symbol, score in event.symbol_relevance):
        return True
    # Macro and geopolitical items describe the market every symbol trades in,
    # so scoping them away would hide the context the decision sits inside.
    return bool(event.macro_tags or event.geopolitical_tags)


def _reason(error: Exception) -> str:
    if isinstance(error, FeedParseError):
        return "unparsable feed"
    if isinstance(error, ResponseTooLargeError):
        return "oversized response"
    if isinstance(error, FeedAccessError):
        return "access refused"
    if isinstance(error, FeedError):
        return "feed error"
    return "unreachable"
