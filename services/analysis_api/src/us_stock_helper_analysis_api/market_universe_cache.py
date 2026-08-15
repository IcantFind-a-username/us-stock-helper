"""In-process cache for the market-brief's breadth/sector-RS driver values.

Daily bars change once a session, so recomputing a whole universe fetch on
every dashboard pull is wasted work the loopback gateway would feel first.
This cache holds at most one computed entry per named slot (``"breadth"``,
``"sector"``), replaced wholesale the moment its key — the caller's own
trading-date key — changes. It never disposes anything silently: a stale slot
is simply overwritten by the next successful compute for a new key, and a hit
always replays the exact value (its own ``computedAt`` included) the miss
produced, rather than a value recomputed against the current request.

The whole compute runs under one lock rather than a per-slot one: a burst of
concurrent dashboard loads landing on a cache miss must perform at most one
universe fetch, the same throttle discipline the evidence collector's poll
coordinator already holds for news. Breadth and sector-RS computations are
both a handful of sequential loopback reads, so serializing the two of them
against each other is a deliberate simplicity trade, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Hashable, TypeVar


_T = TypeVar("_T")


@dataclass(slots=True)
class MarketUniverseCache:
    """A handful of named slots, each independently keyed and replaced."""

    _lock: Lock = field(default_factory=Lock)
    _slots: dict[str, tuple[Hashable, object]] = field(default_factory=dict)

    def get_or_compute(
        self, name: str, key: Hashable, compute: Callable[[], _T]
    ) -> tuple[_T, bool]:
        """Returns ``(value, was_cache_hit)`` for the named slot.

        Held under the lock for the whole call — including ``compute`` — so a
        concurrent miss on the same slot waits for the in-flight compute
        instead of duplicating its universe fetch.
        """

        with self._lock:
            cached = self._slots.get(name)
            if cached is not None and cached[0] == key:
                return cached[1], True  # type: ignore[return-value]
            value = compute()
            self._slots[name] = (key, value)
            return value, False
