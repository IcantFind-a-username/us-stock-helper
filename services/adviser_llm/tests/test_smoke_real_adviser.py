from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from adviser_llm.client import TokenUsage


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "services/adviser_llm/scripts/smoke_real_adviser.py"
SPEC = importlib.util.spec_from_file_location("smoke_real_adviser", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


class CacheMessageHonestyTest(unittest.TestCase):
    """No request this service sends ever sets cache_control (commit 092be7a
    measured the council's stable prefix at 1059 tokens, below Opus 4.8's
    4096-token cache minimum, and concluded caching would change nothing),
    so cache_read_input_tokens == 0 can never mean "the first call primed
    the cache" — it is zero on every call, including every rerun."""

    def test_a_zero_cache_read_does_not_promise_a_cheaper_rerun(self) -> None:
        usage = TokenUsage(input_tokens=1000, output_tokens=200)

        note = SMOKE._cache_note(usage)

        self.assertIsNotNone(note)
        self.assertNotIn("再跑一次就能看到缓存后的价格", note)
        self.assertNotIn("写入缓存", note)

    def test_a_nonzero_cache_read_needs_no_note(self) -> None:
        usage = TokenUsage(
            input_tokens=1000, output_tokens=200, cache_read_input_tokens=500
        )

        self.assertIsNone(SMOKE._cache_note(usage))


if __name__ == "__main__":
    unittest.main()
