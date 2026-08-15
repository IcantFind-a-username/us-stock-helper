"""The documented test command is executed, not merely quoted.

services/analysis_api/README.md and services/README.md both got their
`PYTHONPATH` list fixed recently (a missing `analysis_core` path, a stale
`device_auth` entry), and both drifted silently before that: a reader who
pasted the command got an import error, not a warning. Pinning a substring --
the style `services/market_gateway/tests/test_documentation.py` uses -- would
have caught neither drift; only actually running the command would.
"""

from __future__ import annotations

import os
import re
import subprocess
import unittest
from pathlib import Path

from us_stock_helper_analysis_api.http_app import PAIRING_PATH, _READ_PATHS


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_API_README = REPOSITORY_ROOT / "services/analysis_api/README.md"
SERVICES_README = REPOSITORY_ROOT / "services/README.md"

# The line every fenced command that runs this package's own suite must
# contain, in both READMEs.
_MARKER = "python3 -m unittest discover -s services/analysis_api/tests"

# Set on the subprocess this test spawns. The documented command it runs is
# `unittest discover -s services/analysis_api/tests`, which rediscovers this
# very test file -- without this guard the nested run would spawn another
# subprocess running the same command, and so on. The nested run sees the
# variable set and skips instead, so the command is still executed in full
# (everything else in the package runs there, once) without recursing.
_DEPTH_GUARD = "ANALYSIS_API_DOCUMENTATION_TEST_DEPTH"


def _extract_command(readme: Path) -> str:
    """The fenced shell command that runs analysis_api's own test suite.

    Read literally out of the ```bash block so a hand-edited command -- a
    dropped PYTHONPATH entry, a stale flag -- is caught exactly the way a
    reader pasting it into a shell would hit it, rather than by a substring
    check that only knows to look for specific paths.

    services/README.md's verification list packs every package's command
    into one fenced block, so this walks backward from the discover line
    across backslash-joined continuation lines only, rather than returning
    the whole block -- which would hand back five unrelated commands too.
    """
    text = readme.read_text(encoding="utf-8")
    for block in re.findall(r"```bash\n(.*?)\n```", text, re.DOTALL):
        if _MARKER not in block:
            continue
        lines = [
            line
            for line in block.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        marker_index = next(
            index for index, line in enumerate(lines) if _MARKER in line
        )
        start = marker_index
        while start > 0 and lines[start - 1].rstrip().endswith("\\"):
            start -= 1
        return "\n".join(lines[start : marker_index + 1])
    raise AssertionError(
        f"{readme} has no fenced bash command running analysis_api's own tests"
    )


class DocumentationDriftTests(unittest.TestCase):
    def test_both_readmes_document_the_identical_command(self) -> None:
        # services/README.md is the one-stop verification list; its
        # analysis_api entry has to say exactly what the package's own
        # README says, or a reader following one gets a different answer
        # than a reader following the other.
        self.assertEqual(
            _extract_command(ANALYSIS_API_README),
            _extract_command(SERVICES_README),
        )

    def test_the_documented_test_command_actually_passes(self) -> None:
        if os.environ.get(_DEPTH_GUARD):
            self.skipTest(
                "nested invocation from the documented command itself"
            )

        command = _extract_command(ANALYSIS_API_README)
        completed = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            cwd=REPOSITORY_ROOT,
            env={**os.environ, _DEPTH_GUARD: "1"},
            text=True,
            timeout=300,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg="documented command failed:\n"
            f"{command}\n--- stdout (tail) ---\n{completed.stdout[-4000:]}\n"
            f"--- stderr (tail) ---\n{completed.stderr[-4000:]}",
        )


class AllowlistDriftTests(unittest.TestCase):
    """The README's own safety claim has to name every path actually served.

    services/analysis_api/README.md said the allowlist was exactly
    `GET /health`, `GET /decision` and `POST /v1/device-pairings` after
    `GET /market-brief` (http_app.MARKET_BRIEF_PATH) had already joined
    `http_app._READ_PATHS` -- a reader trusting the safety-invariants section
    over the code would not have known that path existed at all.
    """

    def test_the_documented_allowlist_sentence_matches_the_served_paths(
        self,
    ) -> None:
        text = ANALYSIS_API_README.read_text(encoding="utf-8")
        # DOTALL: the README wraps this sentence across lines inside the
        # `- The path allowlist is exactly ...;` bullet.
        match = re.search(r"The path allowlist is exactly (.+?);", text, re.DOTALL)
        self.assertIsNotNone(
            match, "README has no 'the path allowlist is exactly ...' sentence"
        )
        documented = set(re.findall(r"`(GET|POST) (/[\w/-]+)`", match.group(1)))
        expected = {("GET", path) for path in _READ_PATHS} | {
            ("POST", PAIRING_PATH)
        }
        self.assertEqual(documented, expected)


if __name__ == "__main__":
    unittest.main()
