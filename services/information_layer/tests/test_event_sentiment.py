from __future__ import annotations

import unittest

from information_layer.event_sentiment import (
    SENTIMENT_LEXICON_VERSION,
    EventSentiment,
    score_event_sentiment,
)


class EventSentimentTests(unittest.TestCase):
    def test_text_with_no_known_term_is_unmeasured_not_neutral(self) -> None:
        result = score_event_sentiment("Company schedules its annual meeting")

        self.assertIsInstance(result, EventSentiment)
        self.assertIsNone(result.score)
        self.assertEqual(result.matched_terms, ())
        self.assertFalse(result.measured)
        self.assertEqual(result.method_version, SENTIMENT_LEXICON_VERSION)

    def test_a_measured_neutral_is_distinct_from_no_measurement(self) -> None:
        # One positive and one negative term of equal weight cancel out. That
        # is a measurement of zero, which must not look like "we did not read
        # this" — the aggregator weights the two completely differently.
        balanced = score_event_sentiment("Revenue beat estimates but guidance was cut")
        silent = score_event_sentiment("The board will meet on Tuesday")

        self.assertTrue(balanced.measured)
        self.assertIsNotNone(balanced.score)
        self.assertGreater(len(balanced.matched_terms), 1)
        self.assertFalse(silent.measured)
        self.assertIsNone(silent.score)

    def test_positive_and_negative_financial_language_separate(self) -> None:
        upbeat = score_event_sentiment("Quarterly profit surged and guidance raised")
        grim = score_event_sentiment("Company reports widening loss and cuts outlook")

        assert upbeat.score is not None and grim.score is not None
        self.assertGreater(upbeat.score, 0.2)
        self.assertLess(grim.score, -0.2)

    def test_negation_flips_the_term_it_governs(self) -> None:
        plain = score_event_sentiment("Earnings beat expectations")
        negated = score_event_sentiment("Earnings did not beat expectations")

        assert plain.score is not None and negated.score is not None
        self.assertGreater(plain.score, 0.0)
        self.assertLess(negated.score, 0.0)

    def test_negation_does_not_reach_past_its_window(self) -> None:
        # "not" here governs the first clause only; the later upgrade must keep
        # its own sign or every long headline would be inverted wholesale.
        text = "Not a recall issue; separately the analyst upgraded the stock"

        result = score_event_sentiment(text)

        assert result.score is not None
        self.assertGreater(result.score, 0.0)

    def test_denying_bad_news_is_not_good_news(self) -> None:
        # A denial does not turn an allegation into an achievement. Flipping
        # the sign made "denies fraud" the most bullish reading the lexicon
        # can produce, which is the single most dangerous thing it could say.
        for text in (
            "Company denies fraud allegations",
            "Company denies bankruptcy rumors",
            "Company denied the investigation findings",
        ):
            with self.subTest(text=text):
                result = score_event_sentiment(text)
                assert result.score is not None
                self.assertLessEqual(result.score, 0.0)

    def test_denying_good_news_still_reads_as_bad(self) -> None:
        result = score_event_sentiment("Company denies it will raise guidance")

        assert result.score is not None
        self.assertLess(result.score, 0.0)

    def test_a_negator_governs_every_term_in_its_window(self) -> None:
        # Clearing the negation on the first hit let the second term through
        # unflipped, so "no growth in profit" came out measured-neutral.
        result = score_event_sentiment("No growth in profit this quarter")

        assert result.score is not None
        self.assertLess(result.score, 0.0)

    def test_a_negator_reaches_across_the_words_that_carry_no_meaning(
        self,
    ) -> None:
        # "fails to win FDA approval" is a rejection — one of the sharpest
        # negative events there is — but the filler words between the negator
        # and the term used to exhaust its reach, so it read as good news.
        for text in (
            "Novavax fails to win FDA approval for its COVID booster",
            "Company failed to secure the approval it needed",
            "Regulator denies the approval sought by the sponsor",
        ):
            with self.subTest(text=text):
                result = score_event_sentiment(text)
                assert result.score is not None
                self.assertLess(result.score, 0.0)

    def test_negation_expires_after_a_few_words(self) -> None:
        # No clause break here, so only the window itself can stop the negator
        # from reaching "profit" nine words later.
        near = score_event_sentiment("did not manage to beat estimates")
        far = score_event_sentiment(
            "not going to be a very long wait before profit"
        )

        assert near.score is not None and far.score is not None
        self.assertLess(near.score, 0.0)
        self.assertGreater(far.score, 0.0)

    def test_a_headline_about_the_shares_falling_is_not_bullish(self) -> None:
        # Two mild positives used to outvote the actual news: the market's own
        # verdict on the stock is the story, not the profit it reacted to.
        result = score_event_sentiment(
            "Shares fell after the record profit was reported"
        )

        assert result.score is not None
        self.assertLess(result.score, 0.0)

    def test_cutting_costs_is_not_the_same_as_cutting_guidance(self) -> None:
        # "cut" alone is one of the most negative words in this register, but
        # "cut costs" is what companies say when margins are improving.
        cost = score_event_sentiment("Company cut costs and margins expanded")
        guidance = score_event_sentiment("Company cut its full-year guidance")

        assert cost.score is not None and guidance.score is not None
        self.assertGreater(cost.score, 0.0)
        self.assertLess(guidance.score, 0.0)

    def test_a_matched_phrase_consumes_its_own_words(self) -> None:
        # Re-scanning a phrase's tokens counts the same evidence twice, which
        # both distorts the weighting and makes the audit trail claim two
        # findings where the text contained one.
        result = score_event_sentiment("Shares fell on the news")

        terms = [term for term, _ in result.matched_terms]
        self.assertEqual(terms, ["shares fell"])

    def test_a_strong_term_is_not_diluted_by_weak_company(self) -> None:
        # Averaging every matched term equally let a decisive word be watered
        # down by whatever else happened to appear beside it.
        alone = score_event_sentiment("The company disclosed fraud")
        padded = score_event_sentiment(
            "The company disclosed fraud despite record growth and a dividend"
        )

        assert alone.score is not None and padded.score is not None
        self.assertLess(alone.score, 0.0)
        self.assertLess(padded.score, 0.0)

    def test_scores_stay_within_the_declared_range(self) -> None:
        piled_on = score_event_sentiment(
            "surged soared beat raised upgraded record profit growth strong"
        )
        collapsed = score_event_sentiment(
            "plunged slumped missed cut downgraded loss bankruptcy fraud probe"
        )

        assert piled_on.score is not None and collapsed.score is not None
        self.assertLessEqual(piled_on.score, 1.0)
        self.assertGreaterEqual(collapsed.score, -1.0)

    def test_matching_is_case_and_punctuation_insensitive(self) -> None:
        variants = [
            "Profit SURGED, guidance RAISED.",
            "profit surged; guidance raised",
            "  Profit   surged -- guidance raised!  ",
        ]

        scores = [score_event_sentiment(text).score for text in variants]

        self.assertEqual(len(set(scores)), 1)
        assert scores[0] is not None
        self.assertGreater(scores[0], 0.0)

    def test_a_term_inside_a_longer_word_does_not_match(self) -> None:
        # "misses" must not be found inside "missest"; substring matching is how
        # a lexicon silently starts scoring words it was never given.
        result = score_event_sentiment("The mission was accomplished")

        self.assertEqual(result.matched_terms, ())
        self.assertFalse(result.measured)

    def test_matched_terms_are_reported_for_audit(self) -> None:
        result = score_event_sentiment("Profit surged after the guidance was cut")

        terms = {term for term, _ in result.matched_terms}
        self.assertIn("surged", terms)
        self.assertIn("cut", terms)
        for _, weight in result.matched_terms:
            self.assertTrue(-1.0 <= weight <= 1.0)

    def test_empty_and_whitespace_text_is_unmeasured(self) -> None:
        for text in ("", "   ", "\n\t"):
            with self.subTest(text=repr(text)):
                self.assertFalse(score_event_sentiment(text).measured)

    def test_the_same_text_always_scores_the_same(self) -> None:
        text = "Quarterly profit surged but the outlook was cut"

        self.assertEqual(
            score_event_sentiment(text), score_event_sentiment(text)
        )


if __name__ == "__main__":
    unittest.main()
