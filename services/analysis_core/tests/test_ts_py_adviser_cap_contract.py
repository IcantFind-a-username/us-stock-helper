"""Contract test: ADVISER_SCORE_CAP constant parity across TypeScript and Python."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


class AdviserCapExtractionError(AssertionError):
    """Raised when the TypeScript source does not contain exactly one
    line-anchored, live ADVISER_SCORE_CAP declaration."""


def _extract_adviser_score_cap(ts_content: str) -> str:
    """Pull the literal value out of `export const ADVISER_SCORE_CAP = ...`.

    Anchored to the start of a line (`re.MULTILINE`) so a commented-out
    declaration earlier in the file — `// export const ADVISER_SCORE_CAP =
    99.0;` — can never be mistaken for the real one: `re.search` on an
    unanchored pattern would happily match the substring inside that
    comment and silently return the stale value, since the comment marker
    is not part of the pattern at all. Anchoring alone is not sufficient
    either — a second, distinct live declaration must fail loudly rather
    than have the first one picked, so the match count is checked before
    any match is trusted.
    """
    pattern = r"^export\s+const\s+ADVISER_SCORE_CAP\s*=\s*([0-9.]+)"
    matches = re.findall(pattern, ts_content, re.MULTILINE)
    if len(matches) != 1:
        raise AdviserCapExtractionError(
            "expected exactly one line-anchored ADVISER_SCORE_CAP "
            f"declaration, found {len(matches)}: {matches!r}"
        )
    return matches[0]


class AdviserCapExtractionRegexTests(unittest.TestCase):
    """The extraction helper itself, independent of the real models.ts file.

    A commented-out declaration earlier in the file must never be read as
    the live constant, and more than one live declaration must fail loudly
    rather than silently take the first (today's `re.search` on an
    unanchored pattern does both wrong: it matches anywhere, including
    inside a `// export const ADVISER_SCORE_CAP = 99.0;` comment, and it
    only ever returns the first match found).
    """

    def test_a_commented_out_declaration_earlier_in_the_file_is_ignored(self) -> None:
        source = (
            "// export const ADVISER_SCORE_CAP = 99.0; // stale, do not use\n"
            "export const ADVISER_SCORE_CAP = 3.0;\n"
        )

        self.assertEqual(_extract_adviser_score_cap(source), "3.0")

    def test_multiple_live_declarations_fail_loudly_rather_than_pick_the_first(
        self,
    ) -> None:
        source = (
            "export const ADVISER_SCORE_CAP = 3.0;\n"
            "export const ADVISER_SCORE_CAP = 4.0;\n"
        )

        with self.assertRaises(AdviserCapExtractionError):
            _extract_adviser_score_cap(source)

    def test_no_declaration_at_all_fails_loudly(self) -> None:
        with self.assertRaises(AdviserCapExtractionError):
            _extract_adviser_score_cap("// nothing here\n")


class TypeScriptPythonAdviserCapContractTest(unittest.TestCase):
    """
    Verify that the adviser cap constant in TypeScript matches the Python constant.

    This guards against misalignment where the app displays adviser influence
    the server will never grant.
    """

    def test_adviser_score_cap_parity(self) -> None:
        """Extract ADVISER_SCORE_CAP from TypeScript and assert equality with Python."""
        # Import the Python constant
        from us_stock_helper_core.scoring import ADVISER_SCORE_CAP as python_cap

        # Parse the TypeScript file
        ts_models_path = Path(__file__).parent.parent.parent.parent / "apps" / "mobile" / "src" / "domain" / "models.ts"

        self.assertTrue(
            ts_models_path.exists(),
            f"TypeScript models file not found at {ts_models_path}"
        )

        ts_content = ts_models_path.read_text(encoding="utf-8")

        # Extract ADVISER_SCORE_CAP literal, anchored to a line start so a
        # commented-out declaration elsewhere in the file cannot be mistaken
        # for the real one, and guarded to fail loudly rather than silently
        # pick the first of several live declarations.
        try:
            ts_cap_str = _extract_adviser_score_cap(ts_content)
        except AdviserCapExtractionError as error:
            self.fail(
                f"could not extract a single ADVISER_SCORE_CAP declaration "
                f"from {ts_models_path}: {error}\n"
                "This could mean: the constant was removed, renamed, "
                "duplicated, or the pattern needs updating."
            )

        ts_cap = float(ts_cap_str)

        # Assert parity
        self.assertEqual(
            ts_cap,
            python_cap,
            f"ADVISER_SCORE_CAP mismatch: TypeScript={ts_cap}, Python={python_cap}. "
            "The app may show adviser influence the server will not grant."
        )


if __name__ == "__main__":
    unittest.main()
