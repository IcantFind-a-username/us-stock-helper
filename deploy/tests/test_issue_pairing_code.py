"""A pairing code must never exist somewhere the operator cannot see it.

The failure that matters is quiet: a code recorded in the database and then
written to a pipe, a CI log or a scrollback nobody is watching is a live
credential in a place it was never meant to be, for as long as it lasts. So a
run that cannot reach a terminal has to stop before it records anything, and
the refusals that come earlier — no label, no environment file, no database
path — have to stop before that.

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
ISSUE_PAIRING_CODE = DEPLOY_ROOT / "issue-pairing-code.sh"
# What the command prints: four characters from the code alphabet, a dash, and
# four more. Nothing shaped like this may reach a captured stream.
CODE_SHAPE = re.compile(r"\b[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}\b")

LABEL = "operator iPhone"


class IssuePairingCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = Path(tempfile.mkdtemp(prefix="issue-pairing-"))
        self.addCleanup(shutil.rmtree, self.tree, True)
        self.env_file = self.tree / "analysis-api.env"
        shutil.copy(DEPLOY_ROOT / "env" / "analysis-api.env.example", self.env_file)
        self.original = self.env_file.read_text(encoding="utf-8")

    def run_issuer(
        self, *arguments: str, env_file: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PAIRING_ENV_FILE"] = str(env_file or self.env_file)
        return subprocess.run(
            [str(ISSUE_PAIRING_CODE), *arguments],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            start_new_session=True,
        )

    def test_a_run_without_a_terminal_fails(self) -> None:
        result = self.run_issuer(LABEL)

        self.assertEqual(result.returncode, 1)
        self.assertIn("terminal", result.stderr)

    def test_a_run_without_a_terminal_never_emits_a_code(self) -> None:
        result = self.run_issuer(LABEL)

        self.assertNotRegex(result.stdout, CODE_SHAPE)
        self.assertNotRegex(result.stderr, CODE_SHAPE)

    def test_issuing_a_code_never_rewrites_the_configuration(self) -> None:
        # The old static token was written into this file, so rotating it
        # edited configuration under a running service. A pairing code goes
        # into the database and nowhere else.
        self.run_issuer(LABEL)

        self.assertEqual(self.env_file.read_text(encoding="utf-8"), self.original)
        self.assertEqual(
            sorted(path.name for path in self.tree.iterdir()), ["analysis-api.env"]
        )

    def test_a_run_without_a_label_explains_itself_and_stops(self) -> None:
        result = self.run_issuer()

        self.assertEqual(result.returncode, 1)
        self.assertIn("usage", result.stderr)

    def test_a_missing_environment_file_is_refused(self) -> None:
        result = self.run_issuer(LABEL, env_file=self.tree / "absent.env")

        self.assertEqual(result.returncode, 1)
        self.assertIn("not readable", result.stderr)
        self.assertFalse((self.tree / "absent.env").exists())

    def test_an_environment_naming_no_database_is_refused(self) -> None:
        # Falling back to the package default would put the codes in a file the
        # service does not read, and the operator would be typing codes that
        # nothing can redeem.
        self.env_file.write_text(
            self.original.replace("DEVICE_AUTH_DATABASE=", "UNUSED_SETTING="),
            encoding="utf-8",
        )

        result = self.run_issuer(LABEL)

        self.assertEqual(result.returncode, 1)
        self.assertIn("DEVICE_AUTH_DATABASE", result.stderr)

    def test_an_environment_naming_no_pythonpath_is_refused(self) -> None:
        self.env_file.write_text(
            self.original.replace("PYTHONPATH=", "UNUSED_PATH="), encoding="utf-8"
        )

        result = self.run_issuer(LABEL)

        self.assertEqual(result.returncode, 1)
        self.assertIn("PYTHONPATH", result.stderr)


if __name__ == "__main__":
    unittest.main()
