"""Immutable, point-in-time evidence packets."""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Iterable

from .models import EvidenceKind, EvidenceRecord, require_utc
from .temporal import select_evidence_as_of


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    packet_id: str
    symbol: str
    as_of: datetime
    citations: tuple[EvidenceRecord, ...]
    conflicts: tuple[str, ...]
    missing_kinds: tuple[EvidenceKind, ...]
    content_hash: str
    method_version: str = "point-in-time-evidence-packet-v1"


def freeze_evidence_packet(
    symbol: str,
    as_of: datetime,
    records: Iterable[EvidenceRecord],
    *,
    required_kinds: Iterable[EvidenceKind] = (),
) -> EvidencePacket:
    require_utc(as_of, "as_of")
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")
    selected = tuple(
        record
        for record in select_evidence_as_of(records, as_of)
        if record.symbol is None or record.symbol.upper() == normalized_symbol
    )
    present = {record.kind for record in selected}
    required = tuple(dict.fromkeys(required_kinds))
    missing = tuple(kind for kind in required if kind not in present)
    claims: dict[str, list[EvidenceRecord]] = {}
    for citation in selected:
        if citation.claim_key:
            claims.setdefault(citation.claim_key, []).append(citation)
    conflicts = tuple(
        f"Conflicting evidence for claim '{claim_key}': "
        + ", ".join(record.evidence_id for record in claim_records)
        for claim_key, claim_records in sorted(claims.items())
        if any(record.sentiment >= 0.25 for record in claim_records)
        and any(record.sentiment <= -0.25 for record in claim_records)
    )
    canonical = {
        "symbol": normalized_symbol,
        "as_of": as_of.isoformat(),
        "citations": [
            {
                "evidence_id": record.evidence_id,
                "series_id": record.series_id,
                "kind": record.kind.value,
                "source_name": record.source_name,
                "source_url": record.source_url,
                "headline": record.headline,
                "event_time": record.event_time.isoformat(),
                "published_at": record.published_at.isoformat(),
                "first_seen_at": record.first_seen_at.isoformat(),
                "available_at": record.available_at.isoformat(),
                "revision": record.revision,
                "sentiment": record.sentiment,
                "confidence": record.confidence,
                "claim_key": record.claim_key,
                "tags": record.tags,
            }
            for record in selected
        ],
        "conflicts": conflicts,
        "missing_kinds": [kind.value for kind in missing],
    }
    content_hash = sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return EvidencePacket(
        packet_id=f"{normalized_symbol}-{content_hash[:12]}",
        symbol=normalized_symbol,
        as_of=as_of,
        citations=selected,
        conflicts=conflicts,
        missing_kinds=missing,
        content_hash=content_hash,
    )
