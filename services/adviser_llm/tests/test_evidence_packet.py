from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from adviser_llm import EvidenceItem, build_packet

from tests.fakes import AS_OF, UTC, evidence_item


class EvidenceItemTimelinessTest(unittest.TestCase):
    def test_naive_available_at_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceItem(
                id="ev-1",
                headline="h",
                body="b",
                url="https://example.com/a",
                publisher="p",
                available_at=datetime(2026, 8, 12, 12, 0),
                received_at=AS_OF,
            )

    def test_naive_received_at_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceItem(
                id="ev-1",
                headline="h",
                body="b",
                url="https://example.com/a",
                publisher="p",
                available_at=AS_OF,
                received_at=datetime(2026, 8, 12, 12, 0),
            )

    def test_received_before_published_is_rejected(self) -> None:
        published = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
        with self.assertRaises(ValueError):
            EvidenceItem(
                id="ev-1",
                headline="h",
                body="b",
                url="https://example.com/a",
                publisher="p",
                available_at=published,
                received_at=published - timedelta(seconds=1),
            )

    def test_credential_bearing_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            evidence_item(url="https://user:secret@example.com/a")

    def test_non_http_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            evidence_item(url="ftp://example.com/a")


class PacketPointInTimeTest(unittest.TestCase):
    def test_items_published_after_as_of_are_dropped(self) -> None:
        visible = evidence_item(
            item_id="ev-visible",
            available_at=AS_OF - timedelta(hours=1),
        )
        future = evidence_item(
            item_id="ev-future",
            available_at=AS_OF + timedelta(seconds=1),
        )
        packet = build_packet(
            symbol="NVDA",
            horizon="swing",
            as_of=AS_OF,
            items=(visible, future),
        )
        self.assertEqual([item.id for item in packet.items], ["ev-visible"])

    def test_items_are_ordered_by_publication_moment(self) -> None:
        later = evidence_item(
            item_id="ev-later", available_at=AS_OF - timedelta(hours=1)
        )
        earlier = evidence_item(
            item_id="ev-earlier", available_at=AS_OF - timedelta(hours=5)
        )
        packet = build_packet(
            symbol="NVDA",
            horizon="swing",
            as_of=AS_OF,
            items=(later, earlier),
        )
        self.assertEqual(
            [item.id for item in packet.items], ["ev-earlier", "ev-later"]
        )

    def test_empty_packet_is_rejected_rather_than_silently_neutral(self) -> None:
        with self.assertRaises(ValueError):
            build_packet(symbol="NVDA", horizon="swing", as_of=AS_OF, items=())

    def test_naive_as_of_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_packet(
                symbol="NVDA",
                horizon="swing",
                as_of=datetime(2026, 8, 12, 20, 0),
                items=(evidence_item(),),
            )

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_packet(
                symbol="NVDA",
                horizon="swing",
                as_of=AS_OF,
                items=(evidence_item(), evidence_item(body="其他内容")),
            )

    def test_rendered_packet_carries_both_timestamps_and_source_url(self) -> None:
        item = evidence_item(
            available_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
            received_at=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
        )
        packet = build_packet(
            symbol="NVDA", horizon="swing", as_of=AS_OF, items=(item,)
        )
        rendered = packet.render()
        self.assertIn("2026-08-12T12:00:00+00:00", rendered)
        self.assertIn("2026-08-12T12:30:00+00:00", rendered)
        self.assertIn(item.url, rendered)
        self.assertIn(packet.as_of.isoformat(), rendered)

    def test_packet_never_falls_back_to_wall_clock(self) -> None:
        stale = evidence_item(available_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        packet = build_packet(
            symbol="NVDA", horizon="swing", as_of=AS_OF, items=(stale,)
        )
        self.assertEqual(packet.items[0].available_at, stale.available_at)
        self.assertEqual(packet.latest_available_at, stale.available_at)


if __name__ == "__main__":
    unittest.main()
