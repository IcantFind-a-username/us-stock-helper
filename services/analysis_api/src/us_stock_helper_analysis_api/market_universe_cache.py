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

The whole compute runs under one lock rather than a per-slot one: a burst of
concurrent dashboard loads landing on a cache miss must perform at most one
universe fetch, the same throttle discipline the evidence collector's poll
coordinator already holds for news. Breadth and sector-RS computations are
both a handful of sequential loopback reads, so serializing the two of them
against each other is a deliberate simplicity trade, not an oversight.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
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
class MarketUniverseCache:
    """A handful of named slots, each independently keyed and replaced."""

    retry_after_seconds: float = DEFAULT_RETRY_AFTER_SECONDS
    monotonic: Callable[[], float] = field(default=time.monotonic)
    _lock: Lock = field(default_factory=Lock)
    _slots: dict[str, _Slot] = field(default_factory=dict)

    def get_or_compute(
        self, name: str, key: Hashable, compute: Callable[[], CacheOutcome[_T]]
    ) -> tuple[_T, bool]:
        """Returns ``(value, was_cache_hit)`` for the named slot.

        Held under the lock for the whole call — including ``compute`` — so a
        concurrent miss on the same slot waits for the in-flight compute
        instead of duplicating its universe fetch.
        """

        with self._lock:
            slot = self._slots.get(name)
            if slot is not None and slot.key == key and self._still_fresh(slot):
                return slot.value, True  # type: ignore[return-value]
            outcome = compute()
            retry_at = (
                None
                if outcome.healthy
                else self.monotonic() + self.retry_after_seconds
            )
            self._slots[name] = _Slot(key=key, value=outcome.value, retry_at=retry_at)
            return outcome.value, False

    def _still_fresh(self, slot: _Slot) -> bool:
        return slot.retry_at is None or self.monotonic() < slot.retry_at
