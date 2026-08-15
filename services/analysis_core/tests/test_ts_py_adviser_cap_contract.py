"""Contract test: ADVISER_SCORE_CAP constant parity across TypeScript and Python."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


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

        # Extract ADVISER_SCORE_CAP literal using regex.
        # Pattern: export const ADVISER_SCORE_CAP = <number>;
        pattern = r"export\s+const\s+ADVISER_SCORE_CAP\s*=\s*([0-9.]+)"
        match = re.search(pattern, ts_content)

        self.assertIsNotNone(
            match,
            f"ADVISER_SCORE_CAP constant not found in {ts_models_path} using pattern: {pattern}\n"
            "This could mean: the constant was removed, renamed, or the pattern needs updating."
        )

        ts_cap_str = match.group(1)
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
