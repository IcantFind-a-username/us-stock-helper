"""What preflight must refuse to say.

A pre-deployment check earns its place only by being trusted, and it stops
being trustworthy the moment it prints PASS for something it could not
actually look at. The absent-tool cases below exist for that reason: on a host
without `ss` the exposure check has no evidence, and "no evidence" has to reach
the operator as UNKNOWN with a non-zero exit, never as a clean run.

The script is pointed at a fixture tree through its path overrides, so these
tests exercise the real script rather than a transcription of it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


DEPLOY_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = DEPLOY_ROOT / "preflight.sh"

ISSUED_TOKEN = "a" * 64
DEPLOYED_DOMAIN = "helper.invalid"
DEPLOYED_EMAIL = "ops@helper.invalid"


class Result:
    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.exit_code = completed.returncode
        self.stdout = completed.stdout
        self.rows = [
            (parts[0], parts[1])
            for line in completed.stdout.splitlines()
            if len(parts := line.split(None, 2)) >= 2
            and parts[0] in {"PASS", "FAIL", "UNKNOWN"}
        ]

    def statuses(self, check: str) -> set[str]:
        return {status for status, name in self.rows if name == check}

    def failures(self) -> set[str]:
        return {name for status, name in self.rows if status == "FAIL"}


class PreflightTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = Path(tempfile.mkdtemp(prefix="preflight-"))
        self.addCleanup(shutil.rmtree, self.tree, True)
        self.environment_dir = self.tree / "etc"
        self.unit_dir = self.tree / "units"
        self.stub_dir = self.tree / "bin"
        for directory in (self.environment_dir, self.unit_dir, self.stub_dir):
            directory.mkdir()

        for name in ("opend", "market-gateway", "analysis-api"):
            source = (DEPLOY_ROOT / "env" / f"{name}.env.example").read_text("utf-8")
            target = self.environment_dir / f"{name}.env"
            target.write_text(
                source.replace("ANALYSIS_API_TOKEN=", f"ANALYSIS_API_TOKEN={ISSUED_TOKEN}"),
                encoding="utf-8",
            )
            target.chmod(0o600)
        for name in ("opend.service", "market-gateway.service", "analysis-api.service"):
            shutil.copy(DEPLOY_ROOT / "systemd" / name, self.unit_dir / name)

        self.caddyfile = self.tree / "Caddyfile"
        self.caddyfile.write_text(
            (DEPLOY_ROOT / "Caddyfile")
            .read_text("utf-8")
            .replace("ops@example.com", DEPLOYED_EMAIL)
            .replace("stock.example.com", DEPLOYED_DOMAIN),
            encoding="utf-8",
        )

    def stub(self, name: str, body: str) -> None:
        path = self.stub_dir / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def run_preflight(self, **overrides: str) -> Result:
        environment = dict(os.environ)
        environment.update(
            PATH=f"{self.stub_dir}:{environment['PATH']}",
            PREFLIGHT_ENV_DIR=str(self.environment_dir),
            PREFLIGHT_UNIT_DIR=str(self.unit_dir),
            PREFLIGHT_CADDYFILE=str(self.caddyfile),
            PREFLIGHT_EXPECTED_OWNER=Path(self.environment_dir).owner(),
        )
        environment.update(overrides)
        return Result(
            subprocess.run(
                [str(PREFLIGHT)],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        )


class HonestReportingTests(PreflightTestCase):
    def test_a_check_it_cannot_run_is_unknown_rather_than_passed(self) -> None:
        # No `ss` on this machine, so nothing is known about who can reach the
        # ports. A green run here would be the script inventing evidence.
        result = self.run_preflight()
        self.assertEqual(result.statuses("port-exposure"), {"UNKNOWN"})
        self.assertNotIn("PASS port-exposure", result.stdout)

    def test_an_unverifiable_run_still_exits_non_zero(self) -> None:
        result = self.run_preflight()
        self.assertEqual(result.failures(), set())
        self.assertEqual(result.exit_code, 2)

    def test_a_failure_outranks_an_unverifiable_check_in_the_exit_code(self) -> None:
        (self.environment_dir / "analysis-api.env").chmod(0o644)
        result = self.run_preflight()
        self.assertEqual(result.exit_code, 1)

    def test_every_check_reports_a_row(self) -> None:
        result = self.run_preflight()
        reported = {name for _, name in result.rows}
        self.assertEqual(
            reported,
            {
                "environment-file-mode",
                "environment-file-token",
                "unit-plaintext-secret",
                "unit-syntax",
                "caddyfile-internal-port",
                "caddyfile-placeholder",
                "caddyfile-syntax",
                "port-exposure",
                "firewall",
                "opend-cmdline",
            },
        )


class EnvironmentFileTests(PreflightTestCase):
    def test_a_readable_environment_file_fails(self) -> None:
        (self.environment_dir / "analysis-api.env").chmod(0o644)
        result = self.run_preflight()
        self.assertIn("FAIL", result.statuses("environment-file-mode"))
        self.assertIn("analysis-api.env", result.stdout)

    def test_a_correctly_locked_environment_file_passes(self) -> None:
        self.assertNotIn("FAIL", self.run_preflight().statuses("environment-file-mode"))

    def test_a_missing_environment_file_fails(self) -> None:
        (self.environment_dir / "market-gateway.env").unlink()
        self.assertIn("FAIL", self.run_preflight().statuses("environment-file-mode"))

    def test_an_environment_file_owned_by_another_account_fails(self) -> None:
        result = self.run_preflight(PREFLIGHT_EXPECTED_OWNER="nobody-who-owns-this")
        self.assertIn("FAIL", result.statuses("environment-file-mode"))

    def test_an_unissued_token_fails_before_the_service_ever_starts(self) -> None:
        path = self.environment_dir / "analysis-api.env"
        path.write_text(
            path.read_text("utf-8").replace(f"ANALYSIS_API_TOKEN={ISSUED_TOKEN}",
                                            "ANALYSIS_API_TOKEN="),
            encoding="utf-8",
        )
        path.chmod(0o600)
        self.assertIn("FAIL", self.run_preflight().statuses("environment-file-token"))

    def test_an_issued_token_passes(self) -> None:
        self.assertEqual(
            self.run_preflight().statuses("environment-file-token"), {"PASS"}
        )


class UnitFileTests(PreflightTestCase):
    def test_a_unit_that_inlines_a_token_fails(self) -> None:
        unit = self.unit_dir / "analysis-api.service"
        unit.write_text(
            unit.read_text("utf-8").replace(
                "[Install]", f"Environment=ANALYSIS_API_TOKEN={ISSUED_TOKEN}\n\n[Install]"
            ),
            encoding="utf-8",
        )
        self.assertIn("FAIL", self.run_preflight().statuses("unit-plaintext-secret"))

    def test_a_unit_that_inlines_a_secret_shaped_like_nothing_in_particular_fails(
        self,
    ) -> None:
        # A mutation showed the hex-shaped case alone cannot prove the
        # Environment= rule works, because the hex rule was catching it. A
        # passphrase is not hex and only the Environment= rule can see it.
        unit = self.unit_dir / "analysis-api.service"
        unit.write_text(
            unit.read_text("utf-8").replace(
                "[Install]", "Environment=ANALYSIS_API_TOKEN=correct-horse\n\n[Install]"
            ),
            encoding="utf-8",
        )
        self.assertIn("FAIL", self.run_preflight().statuses("unit-plaintext-secret"))

    def test_the_shipped_units_carry_no_plaintext_secret(self) -> None:
        self.assertEqual(
            self.run_preflight().statuses("unit-plaintext-secret"), {"PASS"}
        )

    def test_unit_syntax_is_unknown_without_systemd(self) -> None:
        self.assertEqual(self.run_preflight().statuses("unit-syntax"), {"UNKNOWN"})

    def test_unit_syntax_reports_what_systemd_says(self) -> None:
        self.stub("systemd-analyze", 'echo "bad unit" >&2; exit 1')
        self.assertIn("FAIL", self.run_preflight().statuses("unit-syntax"))


class CaddyfileTests(PreflightTestCase):
    def test_an_upstream_that_reaches_the_gateway_fails(self) -> None:
        self.caddyfile.write_text(
            self.caddyfile.read_text("utf-8").replace("127.0.0.1:8770", "127.0.0.1:8765"),
            encoding="utf-8",
        )
        self.assertIn("FAIL", self.run_preflight().statuses("caddyfile-internal-port"))

    def test_an_upstream_that_reaches_opend_fails(self) -> None:
        self.caddyfile.write_text(
            self.caddyfile.read_text("utf-8").replace("127.0.0.1:8770", "127.0.0.1:11111"),
            encoding="utf-8",
        )
        self.assertIn("FAIL", self.run_preflight().statuses("caddyfile-internal-port"))

    def test_the_deployed_caddyfile_passes(self) -> None:
        result = self.run_preflight()
        self.assertEqual(result.statuses("caddyfile-internal-port"), {"PASS"})
        self.assertEqual(result.statuses("caddyfile-placeholder"), {"PASS"})

    def test_an_unreplaced_placeholder_domain_fails(self) -> None:
        self.caddyfile.write_text(
            (DEPLOY_ROOT / "Caddyfile").read_text("utf-8"), encoding="utf-8"
        )
        self.assertIn("FAIL", self.run_preflight().statuses("caddyfile-placeholder"))

    def test_caddyfile_syntax_is_unknown_without_caddy(self) -> None:
        self.assertEqual(self.run_preflight().statuses("caddyfile-syntax"), {"UNKNOWN"})

    def test_caddyfile_syntax_reports_what_caddy_says(self) -> None:
        self.stub("caddy", 'echo "adapt failed" >&2; exit 1')
        self.assertIn("FAIL", self.run_preflight().statuses("caddyfile-syntax"))


class PortExposureTests(PreflightTestCase):
    def _listeners(self, *rows: str) -> None:
        body = "\n".join(f'echo "{row}"' for row in rows) or "true"
        self.stub("ss", body)

    def test_a_gateway_bound_to_every_interface_fails(self) -> None:
        self._listeners("LISTEN 0 4096 0.0.0.0:8765 0.0.0.0:*")
        self.assertIn("FAIL", self.run_preflight().statuses("port-exposure"))

    def test_an_opend_bound_to_every_interface_fails(self) -> None:
        self._listeners("LISTEN 0 4096 *:11111 *:*")
        self.assertIn("FAIL", self.run_preflight().statuses("port-exposure"))

    def test_an_analysis_api_on_a_public_address_fails(self) -> None:
        self._listeners("LISTEN 0 4096 203.0.113.7:8770 0.0.0.0:*")
        self.assertIn("FAIL", self.run_preflight().statuses("port-exposure"))

    def test_an_internal_port_on_an_ipv6_wildcard_fails(self) -> None:
        self._listeners("LISTEN 0 4096 [::]:8765 [::]:*")
        self.assertIn("FAIL", self.run_preflight().statuses("port-exposure"))

    def test_loopback_listeners_pass(self) -> None:
        self._listeners(
            "LISTEN 0 4096 127.0.0.1:11111 0.0.0.0:*",
            "LISTEN 0 4096 127.0.0.1:8765 0.0.0.0:*",
            "LISTEN 0 4096 [::1]:8770 [::]:*",
            "LISTEN 0 4096 *:443 *:*",
        )
        self.assertEqual(self.run_preflight().statuses("port-exposure"), {"PASS"})

    def test_nothing_listening_yet_is_not_reported_as_exposure(self) -> None:
        self._listeners()
        self.assertEqual(self.run_preflight().statuses("port-exposure"), {"PASS"})


class FirewallTests(PreflightTestCase):
    def test_an_absent_firewall_tool_is_unknown(self) -> None:
        self.assertEqual(self.run_preflight().statuses("firewall"), {"UNKNOWN"})

    def test_an_inactive_firewall_fails(self) -> None:
        self.stub("ufw", 'echo "Status: inactive"')
        self.assertIn("FAIL", self.run_preflight().statuses("firewall"))

    def test_a_firewall_that_needs_root_is_unknown(self) -> None:
        self.stub("ufw", 'echo "ERROR: You need to be root to run this script" >&2; exit 1')
        self.assertEqual(self.run_preflight().statuses("firewall"), {"UNKNOWN"})

    def test_a_firewall_that_opens_an_internal_port_fails(self) -> None:
        self.stub(
            "ufw",
            'printf "Status: active\\n\\n8765/tcp ALLOW Anywhere\\n443/tcp ALLOW Anywhere\\n"',
        )
        self.assertIn("FAIL", self.run_preflight().statuses("firewall"))

    def test_a_firewall_that_opens_only_https_and_ssh_passes(self) -> None:
        self.stub(
            "ufw",
            'printf "Status: active\\n\\n443/tcp ALLOW Anywhere\\nOpenSSH ALLOW Anywhere\\n"',
        )
        self.assertEqual(self.run_preflight().statuses("firewall"), {"PASS"})


class OpenDCommandLineTests(PreflightTestCase):
    """Arguments are world-readable, so login material there is already leaked."""

    def _proc(self, *cmdlines: str) -> str:
        root = self.tree / "proc"
        root.mkdir(exist_ok=True)
        for index, cmdline in enumerate(cmdlines, start=100):
            entry = root / str(index)
            entry.mkdir()
            (entry / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode())
        return str(root)

    def test_a_host_without_proc_is_unknown(self) -> None:
        result = self.run_preflight(PREFLIGHT_PROC_DIR=str(self.tree / "absent"))
        self.assertEqual(result.statuses("opend-cmdline"), {"UNKNOWN"})

    def test_login_material_on_the_opend_command_line_fails(self) -> None:
        proc = self._proc("/opt/opend/OpenD -login_pwd_md5=deadbeef")
        result = self.run_preflight(PREFLIGHT_PROC_DIR=proc)
        self.assertIn("FAIL", result.statuses("opend-cmdline"))

    def test_a_command_line_that_names_only_a_config_file_passes(self) -> None:
        proc = self._proc("/opt/opend/OpenD -cfg_file=/etc/us-stock-helper/opend.conf")
        result = self.run_preflight(PREFLIGHT_PROC_DIR=proc)
        self.assertEqual(result.statuses("opend-cmdline"), {"PASS"})


if __name__ == "__main__":
    unittest.main()
