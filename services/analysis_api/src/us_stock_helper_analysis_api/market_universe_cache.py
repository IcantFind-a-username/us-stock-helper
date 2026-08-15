"""In-process cache for the market-brief's breadth/sector-RS driver values.

Daily bars change once a session, so recomputing a whole universe fetch on
every dashboard pull is wasted work the loopback gateway would feel first.
This cache holds at most one computed entry per named slot (``"breadth"``,
``"sector"``), replaced wholesale the moment its key — the caller's own
trading-date key — changes. It never disposes anything silently: a stale slot
is simply overwritten by the next successful compute for a new key, and a hit
always replays the exact value (its own ``computedAt`` included) the miss
produced, rather than a value recomputed against the current request.

Two retention policies apply to what a compute produces, disclosed back to
the cache via ``CacheOutcome.healthy`` rather than inferred: a result every
symbol answered earns the full trading date, the same rollover-driven
lifetime the key itself already gives a slot. A result born from any failure
or partial fetch instead earns only ``retry_after_seconds`` of grace — a
short, ``monotonic()``-based window — so a transient gateway restart heals
within the same session instead of freezing a "均未能获取" or a partial
reading until the next day's 16:00 ET rollover.

A burst of concurrent dashboard loads landing on a cache miss must perform at
most one universe fetch — the same throttle discipline the evidence
collector's poll coordinator already holds for news — but that throttle must
never queue a caller behind another's network I/O. ``compute`` (up to ~91
sequential loopback fetches, each with its own timeout) always runs with the
lock released: exactly one caller is elected leader and calls it; every other
caller concurrently missing the same slot lands on ``pending`` instead,
telling it when the attempt already under way started rather than making it
wait behind one. The leader commits its result back under the lock once
``compute`` returns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Callable, Generic, Hashable, TypeVar


_T = TypeVar("_T")

# A transient gateway hiccup should heal well inside one trading session; a
# full day is reserved for a result nothing failed to produce.
DEFAULT_RETRY_AFTER_SECONDS = 180.0


@dataclass(frozen=True, slots=True)
class CacheOutcome(Generic[_T]):
    """What ``compute()`` hands back: the value, plus how long it may stand.

    ``healthy=True`` — every symbol the compute needed answered — earns the
    full-trading-date retention ``get_or_compute`` was designed around.
    ``healthy=False`` — any failure or partial universe, including one that
    simply was not configured — instead earns only ``retry_after_seconds``
    before the next caller may trigger a fresh attempt. The cache never
    infers this from the value's own shape: only the caller, who knows what
    a driver entry's ``available``/failed-symbol bookkeeping means, can say.
    """

    value: _T
    healthy: bool


@dataclass(slots=True)
class _Slot:
    key: Hashable
    value: object
    retry_at: float | None  # a ``monotonic()`` deadline; ``None`` = healthy


@dataclass(slots=True)
class _Attempt:
    """Marks a slot as being computed right now, by exactly one leader."""

    key: Hashable
    started_at: datetime


@dataclass(slots=True)
class MarketUniverseCache:
    """A handful of named slots, each independently keyed and replaced."""

    retry_after_seconds: float = DEFAULT_RETRY_AFTER_SECONDS
    monotonic: Callable[[], float] = field(default=time.monotonic)
    _lock: Lock = field(default_factory=Lock)
    _slots: dict[str, _Slot] = field(default_factory=dict)
    _inflight: dict[str, _Attempt] = field(default_factory=dict)

    def get_or_compute(
        self,
        name: str,
        key: Hashable,
        now: datetime,
        compute: Callable[[], CacheOutcome[_T]],
        pending: Callable[[datetime], _T],
    ) -> tuple[_T, bool]:
        """Returns ``(value, was_cache_hit)`` for the named slot.

        ``compute`` never runs under the lock: a caller that finds the slot
        neither fresh nor already being computed is elected leader (marked
        via a private ``_Attempt`` object, cleared by identity so a key that
        changes mid-flight can never let two leaders trample each other's
        bookkeeping) and calls ``compute`` with the lock released. Any other
        caller that lands on the same in-flight (name, key) — including one
        that never sees this call race at all, just a slow leader still
        running — gets ``pending(started_at)`` immediately instead of
        waiting: exactly the ``compute()``-under-the-lock behaviour this
        replaced would otherwise have queued it behind.
        """

        marker: _Attempt | None = None
        with self._lock:
            slot = self._slots.get(name)
            if slot is not None and slot.key == key and self._still_fresh(slot):
                return slot.value, True  # type: ignore[return-value]

            attempt = self._inflight.get(name)
            if attempt is not None and attempt.key == key:
                return pending(attempt.started_at), True

            marker = _Attempt(key=key, started_at=now)
            self._inflight[name] = marker

        try:
            outcome = compute()
        finally:
            with self._lock:
                if self._inflight.get(name) is marker:
                    del self._inflight[name]

        retry_at = (
            None if outcome.healthy else self.monotonic() + self.retry_after_seconds
        )
        with self._lock:
            self._slots[name] = _Slot(key=key, value=outcome.value, retry_at=retry_at)
        return outcome.value, False

    def _still_fresh(self, slot: _Slot) -> bool:
        return slot.retry_at is None or self.monotonic() < slot.retry_at
