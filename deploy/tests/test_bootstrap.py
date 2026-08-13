from __future__ import annotations

import re
import stat
import subprocess
import unittest
from pathlib import Path


BOOTSTRAP = Path(__file__).resolve().parents[1] / "bootstrap.sh"
SOURCE = BOOTSTRAP.read_text(encoding="utf-8")


class CredentialBoundaryTests(unittest.TestCase):
    """The script must be structurally incapable of handling a login.

    A convenience wrapper around a runbook is exactly where someone would be
    tempted to "just prompt for the account too". These tests exist so that
    temptation fails the build rather than shipping.
    """

    def test_the_script_never_reads_input(self) -> None:
        # `read` as a command, not the English word in a comment.
        reads_input = re.compile(r"^\s*(read|stty)\b", re.MULTILINE)
        offending = [
            line
            for line in SOURCE.splitlines()
            if reads_input.match(line) and not line.strip().startswith("#")
        ]

        self.assertEqual(offending, [])

    def test_no_credential_vocabulary_is_collected(self) -> None:
        # Naming them in prose is how the boundary gets explained; assigning
        # one to a variable is how it gets crossed.
        forbidden = re.compile(
            r"(?i)\b(password|passwd|account_id|trade_?unlock|otp|2fa|totp|secret)\s*=",
        )
        offending = [
            line
            for line in SOURCE.splitlines()
            if forbidden.search(line) and not line.strip().startswith("#")
        ]

        self.assertEqual(offending, [])

    def test_the_login_step_is_left_to_the_operator(self) -> None:
        self.assertIn("Log in to moomoo yourself", SOURCE)
        self.assertIn("only you can do it", SOURCE)


class SequenceTests(unittest.TestCase):
    def test_finishing_refuses_before_opend_answers(self) -> None:
        # Bringing the stack up against a logged-out OpenD yields services
        # that look healthy and return nothing, which reads as "quiet market"
        # rather than "not logged in".
        self.assertIn("OPEND_PORT=11111", SOURCE)
        self.assertIn("/dev/tcp/127.0.0.1/${OPEND_PORT}", SOURCE)
        self.assertIn("sections 5 and 6 first", SOURCE)

    def test_prepare_stops_before_starting_the_stack(self) -> None:
        prepare = SOURCE.split("cmd_prepare()")[1].split("cmd_finish()")[0]

        self.assertNotIn("systemctl enable", prepare)
        self.assertNotIn("systemctl start", prepare)

    def test_an_existing_environment_file_is_never_overwritten(self) -> None:
        # Re-running the script must not silently replace a file the operator
        # has already filled in.
        self.assertIn("left alone", SOURCE)


class ExposureTests(unittest.TestCase):
    def test_only_ssh_and_https_are_opened(self) -> None:
        self.assertIn("ufw default deny incoming", SOURCE)
        self.assertIn("ufw allow OpenSSH", SOURCE)
        self.assertIn("ufw allow 443/tcp", SOURCE)
        for port in ("11111", "8765", "8770"):
            with self.subTest(port=port):
                self.assertNotIn(f"ufw allow {port}", SOURCE)

    def test_environment_files_are_created_private(self) -> None:
        # Root-owned 0600 is what the runbook specifies: systemd reads
        # EnvironmentFile as the manager, before dropping privileges, so no
        # service account ever needs to read it.
        self.assertIn("install -m 0600 -o root -g root", SOURCE)
        self.assertIn("/etc/us-stock-helper", SOURCE)
        self.assertNotIn("/etc/usstock/", SOURCE)


class ShellHygieneTests(unittest.TestCase):
    def test_the_script_is_executable_and_parses(self) -> None:
        mode = BOOTSTRAP.stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR, "bootstrap.sh must be executable")
        subprocess.run(
            ["bash", "-n", str(BOOTSTRAP)], check=True, capture_output=True
        )

    def test_it_fails_fast_on_error(self) -> None:
        self.assertIn("set -euo pipefail", SOURCE)

    def test_usage_is_printed_for_an_unknown_verb(self) -> None:
        result = subprocess.run(
            ["bash", str(BOOTSTRAP), "deploy-everything"],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
