"""The token must never exist somewhere the operator cannot see it.

The failure that matters is quiet: if the script installs a new token and only
then discovers it has nowhere safe to display it, the service starts demanding
a secret nobody knows and the phone is locked out until someone reads the file
that was supposed to be unreadable. So a run that cannot reach a terminal has
to change nothing at all.

`start_new_session` detaches the child from the controlling terminal, which is
what a cron job, a CI runner or a `systemd-run` invocation would look like.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


DEPLOY_ROOT = Path(__file__).resolve().parents[1]
ISSUE_TOKEN = DEPLOY_ROOT / "issue-device-token.sh"
TOKEN_SHAPE = re.compile(r"[0-9a-f]{64}")


class IssueDeviceTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = Path(tempfile.mkdtemp(prefix="issue-token-"))
        self.addCleanup(shutil.rmtree, self.tree, True)
        self.env_file = self.tree / "analysis-api.env"
        shutil.copy(DEPLOY_ROOT / "env" / "analysis-api.env.example", self.env_file)
        self.original = self.env_file.read_text(encoding="utf-8")

    def run_issuer(self, env_file: Path | None = None) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["DEVICE_TOKEN_ENV_FILE"] = str(env_file or self.env_file)
        return subprocess.run(
            [str(ISSUE_TOKEN)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            start_new_session=True,
        )

    def test_a_run_without_a_terminal_fails(self) -> None:
        result = self.run_issuer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("terminal", result.stderr)

    def test_a_run_without_a_terminal_leaves_the_environment_file_untouched(self) -> None:
        self.run_issuer()
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), self.original)

    def test_a_run_without_a_terminal_never_emits_the_token(self) -> None:
        result = self.run_issuer()
        self.assertNotRegex(result.stdout, TOKEN_SHAPE)
        self.assertNotRegex(result.stderr, TOKEN_SHAPE)

    def test_a_missing_environment_file_is_refused(self) -> None:
        result = self.run_issuer(self.tree / "absent.env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)
        self.assertFalse((self.tree / "absent.env").exists())

    def test_no_scratch_file_survives_a_refused_run(self) -> None:
        # A leftover temporary file beside the real one would hold the token at
        # whatever mode mktemp chose, which is not the mode the token needs.
        self.run_issuer()
        self.assertEqual(
            sorted(path.name for path in self.tree.iterdir()), ["analysis-api.env"]
        )


if __name__ == "__main__":
    unittest.main()
