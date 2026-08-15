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

# Not a credential any more, just something shaped like one: no shipped file
# carries a secret now, so the unit checks below have to plant their own.
INLINED_SECRET = "a" * 64
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
            # Copied as shipped. There is nothing left for an operator to fill
            # in before the first start, which is itself part of what these
            # tests hold in place.
            target = self.environment_dir / f"{name}.env"
            target.write_text(
                (DEPLOY_ROOT / "env" / f"{name}.env.example").read_text("utf-8"),
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
                "environment-file-credential",
                "state-directory",
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

    def test_a_missing_analysis_environment_file_does_not_abort_the_run(self) -> None:
        # check_credential_database and check_state_directory both read this
        # file through read_setting; under pipefail a missing file used to
        # kill the whole script instead of reporting the row and moving on.
        (self.environment_dir / "analysis-api.env").unlink()

        result = self.run_preflight()

        reported = {name for _, name in result.rows}
        self.assertEqual(
            reported,
            {
                "environment-file-mode",
                "environment-file-credential",
                "state-directory",
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
        self.assertIn("check(s) failed", result.stdout)

    def rewrite_analysis_environment(self, old: str, new: str) -> None:
        path = self.environment_dir / "analysis-api.env"
        path.write_text(path.read_text("utf-8").replace(old, new), encoding="utf-8")
        path.chmod(0o600)

    def test_a_missing_credential_database_fails_before_the_service_starts(
        self,
    ) -> None:
        self.rewrite_analysis_environment("DEVICE_AUTH_DATABASE=", "UNUSED_SETTING=")

        self.assertIn(
            "FAIL", self.run_preflight().statuses("environment-file-credential")
        )

    def test_a_relative_database_path_fails(self) -> None:
        # It would be resolved against the working directory, which is the
        # install tree the service cannot write.
        self.rewrite_analysis_environment(
            "DEVICE_AUTH_DATABASE=/var/lib", "DEVICE_AUTH_DATABASE=var/lib"
        )

        self.assertIn(
            "FAIL", self.run_preflight().statuses("environment-file-credential")
        )

    def test_the_retired_static_token_fails_rather_than_being_ignored(self) -> None:
        path = self.environment_dir / "analysis-api.env"
        path.write_text(
            path.read_text("utf-8") + f"\nANALYSIS_API_TOKEN={INLINED_SECRET}\n",
            encoding="utf-8",
        )
        path.chmod(0o600)

        self.assertIn(
            "FAIL", self.run_preflight().statuses("environment-file-credential")
        )

    def test_the_shipped_configuration_names_a_credential_database(self) -> None:
        self.assertEqual(
            self.run_preflight().statuses("environment-file-credential"), {"PASS"}
        )

    def test_a_database_outside_the_granted_directory_fails(self) -> None:
        # ProtectSystem=strict makes every other path read-only, so this is a
        # service that starts and then cannot pair a single phone.
        self.rewrite_analysis_environment(
            "DEVICE_AUTH_DATABASE=/var/lib", "DEVICE_AUTH_DATABASE=/srv"
        )

        self.assertIn("FAIL", self.run_preflight().statuses("state-directory"))

    def test_a_unit_that_grants_no_state_directory_fails(self) -> None:
        unit = self.unit_dir / "analysis-api.service"
        unit.write_text(
            unit.read_text("utf-8").replace("StateDirectory=", "UnusedDirective="),
            encoding="utf-8",
        )

        self.assertIn("FAIL", self.run_preflight().statuses("state-directory"))

    def test_the_shipped_unit_and_environment_agree_on_the_directory(self) -> None:
        self.assertEqual(self.run_preflight().statuses("state-directory"), {"PASS"})


class UnitFileTests(PreflightTestCase):
    def test_a_unit_that_inlines_a_token_fails(self) -> None:
        unit = self.unit_dir / "analysis-api.service"
        unit.write_text(
            unit.read_text("utf-8").replace(
                "[Install]", f"Environment=DEVICE_SECRET={INLINED_SECRET}\n\n[Install]"
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
                "[Install]", "Environment=DEVICE_SECRET=correct-horse\n\n[Install]"
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
            'printf "Status: active\\nDefault: deny (incoming), allow (outgoing)'
            '\\n\\n8765/tcp ALLOW IN Anywhere\\n443/tcp ALLOW IN Anywhere\\n"',
        )
        self.assertIn("FAIL", self.run_preflight().statuses("firewall"))

    def test_a_firewall_that_opens_only_https_and_ssh_passes(self) -> None:
        self.stub(
            "ufw",
            'printf "Status: active\\nDefault: deny (incoming), allow (outgoing)'
            '\\n\\n443/tcp ALLOW IN Anywhere\\nOpenSSH ALLOW IN Anywhere\\n"',
        )
        self.assertEqual(self.run_preflight().statuses("firewall"), {"PASS"})

    def test_a_firewall_that_opens_the_sshd_reported_port_passes(self) -> None:
        # bootstrap.sh reads the real port from `sshd -T` and opens exactly
        # this rule for a host whose sshd was moved off 22 (its own comment:
        # "A host whose sshd was moved elsewhere would become unreachable").
        # preflight has to accept the very rule it just watched bootstrap open.
        self.stub("sshd", 'if [ "$1" = "-T" ]; then printf "port 2200\\n"; fi')
        self.stub(
            "ufw",
            'printf "Status: active\\nDefault: deny (incoming), allow (outgoing)'
            '\\n\\n2200/tcp ALLOW IN Anywhere\\n443/tcp ALLOW IN Anywhere\\n"',
        )
        self.assertEqual(self.run_preflight().statuses("firewall"), {"PASS"})

    def test_a_firewall_that_opens_a_port_the_sshd_config_does_not_name_still_fails(
        self,
    ) -> None:
        # A moved sshd does not amnesty every other port: only the one sshd
        # itself reports is exempt from the whitelist.
        self.stub("sshd", 'if [ "$1" = "-T" ]; then printf "port 2200\\n"; fi')
        self.stub(
            "ufw",
            'printf "Status: active\\nDefault: deny (incoming), allow (outgoing)'
            '\\n\\n8765/tcp ALLOW IN Anywhere\\n443/tcp ALLOW IN Anywhere\\n"',
        )
        self.assertIn("FAIL", self.run_preflight().statuses("firewall"))


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


class EvidenceHonestyTests(PreflightTestCase):
    """The header promises this script never passes what it could not inspect.

    These two checks are the only automated evidence that OpenD's control
    port and the gateway stay off the public internet. Reporting PASS without
    looking is worse than having no check: it turns "unverified" into
    "verified safe" on the one question whose wrong answer exposes a
    logged-in broker session.
    """

    def test_a_failing_ss_is_unknown_rather_than_pass(self) -> None:
        self.stub("ss", 'echo "ss: no netlink" >&2; exit 1')

        result = self.run_preflight()

        self.assertEqual(result.statuses("port-exposure"), {"UNKNOWN"})

    def test_the_firewall_check_reads_the_default_incoming_policy(self) -> None:
        # `ufw status` omits the default policy line, so a host running
        # `default allow incoming` prints text identical to a correct one.
        recorded = self.tree / "ufw-args"
        self.stub(
            "ufw",
            f'printf "%s\\n" "$@" >> {recorded}\n'
            'echo "Status: active"\n'
            'echo "443/tcp ALLOW Anywhere"\n'
            'echo "OpenSSH ALLOW Anywhere"',
        )

        self.run_preflight()

        self.assertIn("verbose", recorded.read_text(encoding="utf-8"))

    def test_a_default_allow_incoming_policy_fails(self) -> None:
        self.stub(
            "ufw",
            'echo "Status: active"\n'
            'echo "Default: allow (incoming), allow (outgoing), disabled (routed)"\n'
            'echo "443/tcp ALLOW IN Anywhere"\n'
            'echo "OpenSSH ALLOW IN Anywhere"',
        )

        self.assertIn("FAIL", self.run_preflight().statuses("firewall"))
