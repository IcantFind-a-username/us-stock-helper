from __future__ import annotations

import unittest

from adviser_llm.client import TokenUsage


class TokenUsageTests(unittest.TestCase):
    """What a call cost has to be measured, not estimated.

    Every number I gave the user for this feature was an estimate, because
    nothing read the usage the API already returns on every response.
    """

    def test_it_adds_up_across_the_calls_a_briefing_makes(self) -> None:
        total = TokenUsage() + TokenUsage(
            input_tokens=1200,
            output_tokens=300,
            cache_read_input_tokens=8000,
        )
        total = total + TokenUsage(input_tokens=400, output_tokens=90)

        self.assertEqual(total.input_tokens, 1600)
        self.assertEqual(total.output_tokens, 390)
        self.assertEqual(total.cache_read_input_tokens, 8000)

    def test_it_prices_a_cache_read_far_below_a_fresh_read(self) -> None:
        fresh = TokenUsage(input_tokens=10_000).cost_usd()
        cached = TokenUsage(cache_read_input_tokens=10_000).cost_usd()

        self.assertGreater(fresh, cached * 5)

    def test_an_absent_usage_object_reports_nothing_rather_than_zero(self) -> None:
        # Zero cost and unmeasured cost are different claims, and only one of
        # them is ever true.
        self.assertIsNone(TokenUsage.from_response(None))
