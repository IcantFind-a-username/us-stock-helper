from __future__ import annotations

import re
import unittest
from pathlib import Path

from us_stock_helper_market_gateway.http_gateway import _PATHS


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_README = REPOSITORY_ROOT / "services/market_gateway/README.md"
SERVICES_README = REPOSITORY_ROOT / "services/README.md"


class DocumentationDriftTests(unittest.TestCase):
    """Documentation that contradicts the code is worse than none at all.

    Both claims guarded here had already drifted: the README advertised an
    allowlist one path short of the real one, and its test command omitted the
    analysis_core path, so following it verbatim produced import errors.
    """

    def test_the_documented_allowlist_matches_the_served_paths(self) -> None:
        text = GATEWAY_README.read_text(encoding="utf-8")
        documented = set(re.findall(r"`GET (/[a-z-]+)`|`(/[a-z-]+)`", text))
        flattened = {value for pair in documented for value in pair if value}

        for path in _PATHS:
            self.assertIn(path, flattened, f"{path} is served but undocumented")

    def test_documented_test_commands_include_every_needed_path(self) -> None:
        for readme in (GATEWAY_README, SERVICES_README):
            text = readme.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "market_gateway/tests" not in line:
                    continue
                command = text[: text.index(line)]
                self.assertIn(
                    "services/market_gateway/src:services/analysis_core",
                    command,
                    f"{readme.name} documents a gateway test command without "
                    "analysis_core, which cannot import",
                )


if __name__ == "__main__":
    unittest.main()
