"""Point-in-time selection utilities."""

from datetime import datetime
from typing import Iterable

from .models import EvidenceRecord, OHLCVBar, require_utc


def select_bars_as_of(
    bars: Iterable[OHLCVBar], as_of: datetime
) -> tuple[OHLCVBar, ...]:
    require_utc(as_of, "as_of")
    latest: dict[tuple[str, str, datetime], OHLCVBar] = {}
    for row in bars:
        if not row.complete or row.closed_at > as_of or row.available_at > as_of:
            continue
        key = (row.symbol.upper(), row.interval, row.closed_at)
        current = latest.get(key)
        if current is None or (row.revision, row.available_at) > (
            current.revision,
            current.available_at,
        ):
            latest[key] = row
    return tuple(
        sorted(
            latest.values(),
            key=lambda row: (
                row.closed_at,
                row.symbol.upper(),
                row.interval,
                row.revision,
            ),
        )
    )


def select_evidence_as_of(
    records: Iterable[EvidenceRecord], as_of: datetime
) -> tuple[EvidenceRecord, ...]:
    require_utc(as_of, "as_of")
    latest: dict[tuple[str | None, str], EvidenceRecord] = {}
    for record in records:
        if record.available_at > as_of:
            continue
        key = (
            record.symbol.upper() if record.symbol is not None else None,
            record.series_id,
        )
        current = latest.get(key)
        if current is None or (record.revision, record.available_at) > (
            current.revision,
            current.available_at,
        ):
            latest[key] = record
    return tuple(
        sorted(
            latest.values(),
            key=lambda record: (
                record.available_at,
                record.series_id,
                record.revision,
                record.evidence_id,
            ),
        )
    )
