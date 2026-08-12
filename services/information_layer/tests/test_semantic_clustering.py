from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from information_layer.clustering import build_clusters
from information_layer.models import ClaimStatus, EvidenceEvent, SourceProvenance
from information_layer.similarity import (
    SIMILARITY_VERSION,
    headline_tokens,
    same_story,
)


UTC = timezone.utc
AS_OF = datetime(2026, 7, 24, 16, tzinfo=UTC)


def event(
    event_id: str,
    publisher_id: str,
    headline: str,
    summary: str = "",
    *,
    published_at: datetime | None = None,
    symbol: str = "NVDA",
    sentiment: float = 0.6,
) -> EvidenceEvent:
    published = published_at or AS_OF - timedelta(minutes=20)
    return EvidenceEvent.create(
        event_id=event_id,
        claim_key=f"{publisher_id}|{event_id}",
        headline=headline,
        summary=summary,
        provenance=SourceProvenance(
            source_id=f"feed:{publisher_id}",
            publisher_id=publisher_id,
            publisher_name=publisher_id,
            canonical_url=f"https://{publisher_id}.example/{event_id}",
            source_type="wire",
            reliability=0.85,
        ),
        event_time=published - timedelta(minutes=10),
        published_at=published,
        first_seen_at=published + timedelta(minutes=1),
        available_at=published + timedelta(minutes=2),
        retrieved_at=published + timedelta(minutes=3),
        claim_status=ClaimStatus.REPORTED,
        sentiment=sentiment,
        confidence=0.85,
        symbol_relevance=((symbol, 0.95),),
    )


class HeadlineTokenTests(unittest.TestCase):
    def test_tokens_drop_case_punctuation_and_filler(self) -> None:
        left = headline_tokens("NVIDIA raises full-year revenue guidance")
        right = headline_tokens("Nvidia lifts the full year revenue guidance!")

        self.assertIn("nvidia", left)
        self.assertIn("revenue", left)
        self.assertNotIn("the", right)
        self.assertEqual(headline_tokens(""), frozenset())

    def test_a_single_digit_is_kept_because_it_carries_meaning(self) -> None:
        # Dropping short tokens to remove stray letters also removed the digit
        # in "Q1" or "up 5%", which is exactly what tells two events apart.
        tokens = headline_tokens("Q1 revenue up 5 percent")

        # "q1" stays whole, which keeps the quarter identity, and the bare
        # digit survives the short-token filter that exists to drop stray
        # letters.
        self.assertIn("q1", tokens)
        self.assertIn("5", tokens)
        self.assertNotIn("q", headline_tokens("q revenue"))

    def test_token_extraction_is_stable_for_the_same_text(self) -> None:
        self.assertEqual(
            headline_tokens("Guidance raised"), headline_tokens("guidance  RAISED")
        )


class SameStoryTests(unittest.TestCase):
    def test_two_wordings_of_one_event_are_the_same_story(self) -> None:
        left = event("a", "reuters", "NVIDIA raises full-year revenue guidance")
        right = event(
            "b", "bloomberg", "Nvidia raises full year revenue guidance outlook"
        )

        self.assertTrue(same_story(left, right))

    def test_two_different_events_about_one_company_stay_apart(self) -> None:
        # Over-merging is worse than under-merging: it would invent
        # corroboration between unrelated claims and let one of them inherit
        # the other's source count.
        left = event("a", "reuters", "NVIDIA raises full-year revenue guidance")
        right = event("b", "reuters", "NVIDIA announces a chief financial officer change")

        self.assertFalse(same_story(left, right))

    def test_stories_about_different_symbols_never_merge(self) -> None:
        left = event("a", "reuters", "Company raises full-year revenue guidance")
        right = event(
            "b", "bloomberg", "Company raises full-year revenue guidance", symbol="TSLA"
        )

        self.assertFalse(same_story(left, right))

    def test_the_same_wording_far_apart_in_time_is_a_new_event(self) -> None:
        # Companies raise guidance every quarter in nearly identical language.
        left = event("a", "reuters", "NVIDIA raises full-year revenue guidance")
        right = event(
            "b",
            "bloomberg",
            "NVIDIA raises full-year revenue guidance",
            published_at=AS_OF - timedelta(days=90),
        )

        self.assertFalse(same_story(left, right))

    def test_headlines_differing_only_by_a_number_are_different_events(
        self,
    ) -> None:
        # In this register the number is usually the discriminating detail:
        # "first-quarter" versus "second-quarter", "up 5%" versus "up 12%".
        left = event("a", "reuters", "NVIDIA reports first quarter revenue of 30 billion")
        right = event(
            "b", "bloomberg", "NVIDIA reports first quarter revenue of 44 billion"
        )

        self.assertFalse(same_story(left, right))

    def test_a_number_on_only_one_side_does_not_block_a_match(self) -> None:
        # One outlet quoting the figure and another not is ordinary coverage of
        # the same announcement.
        left = event("a", "reuters", "NVIDIA raises full-year revenue guidance")
        right = event(
            "b",
            "bloomberg",
            "NVIDIA raises full-year revenue guidance to 200 billion",
        )

        self.assertTrue(same_story(left, right))

    def test_the_rule_is_symmetric(self) -> None:
        left = event("a", "reuters", "NVIDIA raises full-year revenue guidance")
        right = event(
            "b", "bloomberg", "Nvidia raises full year revenue guidance outlook"
        )

        self.assertEqual(same_story(left, right), same_story(right, left))

    def test_the_rule_declares_its_version(self) -> None:
        self.assertTrue(SIMILARITY_VERSION)


class ClusterCorroborationTests(unittest.TestCase):
    def test_two_outlets_reporting_one_event_corroborate_each_other(self) -> None:
        clusters = build_clusters(
            (
                event("a", "reuters", "NVIDIA raises full-year revenue guidance"),
                event(
                    "b",
                    "bloomberg",
                    "Nvidia raises full year revenue guidance outlook",
                ),
            ),
            AS_OF,
        )

        # Before this, each wording formed its own cluster and the two-source
        # actionability gate could never be met by real newsflow.
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].independent_source_count, 2)

    def test_unrelated_company_news_still_forms_separate_clusters(self) -> None:
        clusters = build_clusters(
            (
                event("a", "reuters", "NVIDIA raises full-year revenue guidance"),
                event(
                    "b",
                    "bloomberg",
                    "NVIDIA chief financial officer departs after eight years",
                ),
            ),
            AS_OF,
        )

        self.assertEqual(len(clusters), 2)

    def test_one_outlet_repeating_itself_is_not_corroboration(self) -> None:
        clusters = build_clusters(
            (
                event("a", "reuters", "NVIDIA raises full-year revenue guidance"),
                event(
                    "b", "reuters", "Nvidia raises full year revenue guidance outlook"
                ),
            ),
            AS_OF,
        )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].independent_source_count, 1)

    def test_merging_is_order_independent(self) -> None:
        rows = (
            event("a", "reuters", "NVIDIA raises full-year revenue guidance"),
            event("b", "bloomberg", "Nvidia raises full year revenue guidance outlook"),
            event("c", "ft", "NVIDIA chief financial officer departs"),
        )

        forward = build_clusters(rows, AS_OF)
        backward = build_clusters(tuple(reversed(rows)), AS_OF)

        self.assertEqual(
            [cluster.independent_source_count for cluster in forward],
            [cluster.independent_source_count for cluster in backward],
        )


if __name__ == "__main__":
    unittest.main()
