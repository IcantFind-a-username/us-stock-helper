from __future__ import annotations

from datetime import datetime
from typing import Iterable, Protocol, runtime_checkable

from .models import EvidenceEvent


@runtime_checkable
class SourceAdapter(Protocol):
    """Boundary implemented by production feeds; this package performs no I/O."""

    adapter_id: str

    def fetch(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> Iterable[EvidenceEvent]:
        ...
