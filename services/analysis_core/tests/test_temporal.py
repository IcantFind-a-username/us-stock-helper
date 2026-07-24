from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import unittest

from us_stock_helper_core.models import (
    EvidenceKind,
    EvidenceRecord,
    MarketContext,
    OHLCVBar,
)
from us_stock_helper_core.temporal import select_bars_as_of, select_evidence_as_of


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 24, hour, minute, tzinfo=UTC)


def bar(
    *,
    closed_at: datetime = at(14),
    available_at: datetime = at(14),
    close: float = 101.0,
    complete: bool = True,
    revision: int = 1,
) -> OHLCVBar:
    return OHLCVBar(
        symbol="NVDA",
        interval="5m",
        opened_at=closed_at - timedelta(minutes=5),
        closed_at=closed_at,
        available_at=available_at,
        open=100.0,
        high=max(102.0, close),
        low=min(99.0, close),
        close=close,
        volume=1_000.0,
        complete=complete,
        revision=revision,
    )


def evidence(
    *,
    evidence_id: str = "news-v1",
    available_at: datetime = at(14),
    revision: int = 1,
    sentiment: float = 0.4,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        series_id="news-series",
        symbol="NVDA",
        kind=EvidenceKind.NEWS,
        source_name="Issuer newsroom",
        source_url="https://example.com/source",
        headline="A point-in-time announcement",
        event_time=at(13),
        published_at=at(13, 30),
        first_seen_at=at(13, 31),
        available_at=available_at,
        revision=revision,
        sentiment=sentiment,
        confidence=0.8,
        claim_key="guidance",
    )


class TemporalValidationTests(unittest.TestCase):
    def test_rejects_naive_datetimes_at_the_model_boundary(self) -> None:
        naive = datetime(2026, 7, 24, 14)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            bar(closed_at=naive, available_at=naive)

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            MarketContext(
                as_of=naive,
                market_sentiment=0.0,
                macro=0.0,
                geopolitics=0.0,
                institutional_flow=0.0,
            )

    def test_rejects_invalid_ohlcv_and_revision_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "high"):
            replace(bar(), high=100.0, close=101.0)
        with self.assertRaisesRegex(ValueError, "volume"):
            replace(bar(), volume=-1.0)
        with self.assertRaisesRegex(ValueError, "revision"):
            replace(bar(), revision=0)
        with self.assertRaisesRegex(ValueError, "available_at"):
            replace(
                bar(closed_at=at(14), available_at=at(14)),
                available_at=at(13, 59),
            )

    def test_rejects_invalid_evidence_ranges_and_timestamp_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "sentiment"):
            replace(evidence(), sentiment=1.1)
        with self.assertRaisesRegex(ValueError, "confidence"):
            replace(evidence(), confidence=-0.1)
        with self.assertRaisesRegex(ValueError, "published_at"):
            replace(evidence(), published_at=at(13, 40), first_seen_at=at(13, 31))

    def test_point_in_time_bars_reject_future_and_incomplete_rows(self) -> None:
        decision_time = at(14)
        accepted = bar(closed_at=at(13, 55), available_at=at(13, 56))
        future_available = bar(closed_at=at(13, 50), available_at=at(14, 1))
        future_close = bar(closed_at=at(14, 1), available_at=at(14, 2))
        incomplete = bar(
            closed_at=at(13, 45), available_at=at(13, 46), complete=False
        )

        selected = select_bars_as_of(
            [future_available, incomplete, accepted, future_close], decision_time
        )

        self.assertEqual(selected, (accepted,))

    def test_point_in_time_bars_resolve_revisions_and_order_deterministically(self) -> None:
        original = bar(closed_at=at(13, 50), available_at=at(13, 51), close=100.0)
        revision = bar(
            closed_at=at(13, 50),
            available_at=at(14, 5),
            close=103.0,
            revision=2,
        )
        later_bar = bar(closed_at=at(13, 55), available_at=at(13, 56), close=102.0)

        before_revision = select_bars_as_of(
            [later_bar, revision, original], at(14)
        )
        after_revision = select_bars_as_of(
            [later_bar, revision, original], at(14, 10)
        )

        self.assertEqual([row.close for row in before_revision], [100.0, 102.0])
        self.assertEqual([row.close for row in after_revision], [103.0, 102.0])

    def test_evidence_revisions_are_frozen_at_the_decision_cutoff(self) -> None:
        original = evidence(available_at=at(13, 40), sentiment=0.3)
        correction = evidence(
            evidence_id="news-v2",
            available_at=at(14, 5),
            revision=2,
            sentiment=-0.2,
        )

        before = select_evidence_as_of([correction, original], at(14))
        after = select_evidence_as_of([correction, original], at(14, 10))

        self.assertEqual([(item.evidence_id, item.sentiment) for item in before], [("news-v1", 0.3)])
        self.assertEqual([(item.evidence_id, item.sentiment) for item in after], [("news-v2", -0.2)])

    def test_naive_as_of_is_rejected_instead_of_silently_assumed(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            select_bars_as_of([bar()], datetime(2026, 7, 24, 14))


if __name__ == "__main__":
    unittest.main()
