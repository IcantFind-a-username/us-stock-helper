"""Invariants the Singapore deployment cannot be allowed to lose.

Configuration drifts more quietly than code: nothing fails to compile when a
Caddyfile grows a second upstream or a unit file loses a hardening line, and
the first symptom is that the market gateway or the OpenD port answers a
stranger. Every check here pins one property that, if it broke, would put the
user's broker session or their bearer token where it must never be.

Where a claim can be checked against the running code rather than against the
text of a file, it is: the assertion that the analysis API still demands a
token when it sits behind Caddy is made by building its real configuration
object from the shipped template, not by grepping for a variable name.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from us_stock_helper_analysis_api.http_app import AnalysisServerConfig, _PATHS
from us_stock_helper_market_gateway.http_gateway import GatewayServerConfig


DEPLOY_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DEPLOY_ROOT.parent
ANALYSIS_API_SOURCE = REPOSITORY_ROOT / "services/analysis_api/src"
CADDYFILE = DEPLOY_ROOT / "Caddyfile"
RUNBOOK = DEPLOY_ROOT / "README.md"
UNIT_DIR = DEPLOY_ROOT / "systemd"
ENV_DIR = DEPLOY_ROOT / "env"

UNITS = ("opend.service", "market-gateway.service", "analysis-api.service")
PYTHON_UNITS = ("market-gateway.service", "analysis-api.service")
SCRIPTS = ("preflight.sh", "issue-device-token.sh")

ANALYSIS_API_PORT = "8770"
MARKET_GATEWAY_PORT = "8765"
OPEND_PORT = "11111"

INSTALL_ROOT = "/opt/us-stock-helper"
ENVIRONMENT_DIR = "/etc/us-stock-helper"

# Applied to all three units. Each line closes a way a compromised or
# misbehaving service could reach past its own job.
HARDENING_FLOOR = {
    "NoNewPrivileges": "yes",
    "PrivateTmp": "yes",
    "ProtectSystem": "strict",
    "ProtectHome": "yes",
    "ProtectProc": "invisible",
    "ProcSubset": "pid",
    "PrivateDevices": "yes",
    "ProtectClock": "yes",
    "ProtectHostname": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectKernelLogs": "yes",
    "ProtectControlGroups": "yes",
    "RestrictNamespaces": "yes",
    "RestrictRealtime": "yes",
    "RestrictSUIDSGID": "yes",
    "LockPersonality": "yes",
    "RemoveIPC": "yes",
    "SystemCallArchitectures": "native",
    "UMask": "0077",
}
ALLOWED_ADDRESS_FAMILIES = {"AF_INET", "AF_INET6", "AF_UNIX"}
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL|APIKEY", re.I)
TRADING_CAPABILITY = (
    "TradeContext",
    "OpenSecTradeContext",
    "place_order",
    "modify_order",
    "unlock_trade",
    "accinfo_query",
)


def read_unit(name: str) -> dict[str, dict[str, list[str]]]:
    """Parse a unit file into sections of repeatable key/value pairs.

    systemd allows a key to appear more than once, and for the directives that
    matter here — ReadWritePaths, SystemCallFilter — the repeats are the point,
    so nothing may collapse them to a single value.
    """
    sections: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for raw in (UNIT_DIR / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        current.setdefault(key.strip(), []).append(value.strip())
    return sections


def read_environment(name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in (ENV_DIR / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def caddyfile_lines() -> list[str]:
    return [line.strip() for line in CADDYFILE.read_text(encoding="utf-8").splitlines()]


def shipped_files() -> list[Path]:
    return sorted(
        path
        for path in DEPLOY_ROOT.rglob("*")
        if path.is_file() and "tests" not in path.relative_to(DEPLOY_ROOT).parts
    )


class ReadOnlyBoundaryTests(unittest.TestCase):
    def test_no_deployment_file_can_reach_a_trading_capability(self) -> None:
        # The tests directory is excluded because this list of forbidden names
        # lives in it; every file that actually ships is scanned.
        files = shipped_files()
        self.assertGreaterEqual(len(files), len(UNITS) + len(SCRIPTS))
        for path in files:
            text = path.read_text(encoding="utf-8")
            for capability in TRADING_CAPABILITY:
                self.assertNotIn(
                    capability,
                    text,
                    f"{path.name} names a trading capability",
                )

    def test_the_public_edge_never_addresses_the_gateway_or_opend(self) -> None:
        text = CADDYFILE.read_text(encoding="utf-8")
        for port in (MARKET_GATEWAY_PORT, OPEND_PORT):
            self.assertNotRegex(
                text,
                rf"\b{port}\b",
                f"port {port} appears in the public entry point",
            )


class AuthenticationAssumptionTests(unittest.TestCase):
    def test_the_deployment_matches_what_the_api_actually_enforces(self) -> None:
        """A pairing service exists in this tree, but nothing serves it yet.

        `services/device_auth` implements single-use codes and revocable
        per-device tokens; no HTTP boundary reaches it, so the deployed API
        still checks one static bearer token and the runbook says so. The day
        that changes, three things here become false at once: the revocation
        section, the empty-token fail-closed behaviour, and the unit's refusal
        to grant a writable directory for a credential database. Failing here
        first is how they get revisited together instead of one at a time.
        """
        sources = sorted(ANALYSIS_API_SOURCE.rglob("*.py"))
        self.assertTrue(sources, "the analysis API source tree was not found")
        # Both spellings, because the import path underscores the name and the
        # distribution hyphenates it, and either one arriving means the same
        # thing.
        for path in sources + [REPOSITORY_ROOT / "services/analysis_api/pyproject.toml"]:
            text = path.read_text(encoding="utf-8").lower()
            for spelling in ("device_auth", "device-auth"):
                self.assertNotIn(
                    spelling,
                    text,
                    f"{path.name} now reaches the pairing service; deploy/ must be revisited",
                )


class CaddyfileTests(unittest.TestCase):
    def test_every_reverse_proxy_upstream_is_the_loopback_analysis_api(self) -> None:
        upstreams = [
            match.group(1)
            for line in caddyfile_lines()
            if (match := re.match(r"reverse_proxy\s+(\S+)", line))
        ]
        self.assertTrue(upstreams, "the Caddyfile proxies nothing at all")
        for upstream in upstreams:
            self.assertEqual(upstream, f"127.0.0.1:{ANALYSIS_API_PORT}")

    def test_the_public_path_allowlist_matches_the_served_allowlist(self) -> None:
        matcher = [line for line in caddyfile_lines() if line.startswith("@api path ")]
        self.assertEqual(len(matcher), 1, "the API path matcher is not stated once")
        self.assertEqual(set(matcher[0].removeprefix("@api path ").split()), _PATHS)

    def test_only_get_survives_the_edge(self) -> None:
        text = CADDYFILE.read_text(encoding="utf-8")
        self.assertRegex(text, r"@\w+\s+not\s+method\s+GET")
        self.assertRegex(text, r"respond\s+405")

    def test_an_unlisted_path_is_refused_before_the_service_sees_it(self) -> None:
        self.assertRegex(CADDYFILE.read_text(encoding="utf-8"), r"respond\s+404")

    def test_the_security_headers_are_present(self) -> None:
        text = CADDYFILE.read_text(encoding="utf-8")
        for header in (
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Content-Security-Policy",
            "Cross-Origin-Resource-Policy",
            "Permissions-Policy",
        ):
            self.assertIn(header, text, f"{header} is not set at the edge")
        hsts = re.search(r"Strict-Transport-Security\s+\"([^\"]+)\"", text)
        self.assertIsNotNone(hsts, "HSTS is not set")
        assert hsts is not None
        age = re.search(r"max-age=(\d+)", hsts.group(1))
        self.assertIsNotNone(age, "HSTS carries no max-age")
        assert age is not None
        self.assertGreaterEqual(int(age.group(1)), 31536000)
        self.assertIn("includeSubDomains", hsts.group(1))

    def test_the_transport_cannot_fall_back_to_cleartext(self) -> None:
        text = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("auto_https disable_redirects", text)
        self.assertIn("disable_http_challenge", text)
        self.assertNotIn("auto_https off", text)
        self.assertNotIn("tls internal", text)
        for line in caddyfile_lines():
            self.assertFalse(line.startswith("http://"), "a cleartext site is defined")
            self.assertFalse(line.startswith(":80"), "port 80 is bound")

    def test_the_admin_api_is_off(self) -> None:
        # Caddy's admin endpoint reconfigures the running server and needs no
        # credential, so any local account could repoint the upstream.
        self.assertIn("admin off", CADDYFILE.read_text(encoding="utf-8"))

    def test_the_access_log_drops_the_bearer_token(self) -> None:
        text = CADDYFILE.read_text(encoding="utf-8")
        self.assertRegex(text, r"request>headers>Authorization\s+delete")

    def test_the_site_address_is_still_an_unusable_placeholder(self) -> None:
        # A committed real hostname would be deployed by anyone who copied the
        # file without reading it; preflight rejects the placeholder in turn,
        # so the substitution cannot be forgotten either.
        self.assertIn("example.com", CADDYFILE.read_text(encoding="utf-8"))


class SystemdUnitTests(unittest.TestCase):
    def test_every_unit_ships(self) -> None:
        for name in UNITS:
            self.assertTrue((UNIT_DIR / name).is_file(), f"{name} is missing")

    def test_every_service_runs_as_its_own_non_root_user(self) -> None:
        seen: set[str] = set()
        for name in UNITS:
            service = read_unit(name)["Service"]
            user = service["User"][0]
            self.assertNotEqual(user, "root", f"{name} runs as root")
            self.assertNotIn(user, seen, f"{name} shares a user with another service")
            seen.add(user)
            self.assertNotEqual(service["Group"][0], "root", f"{name} has root group")

    def test_every_service_restarts_always(self) -> None:
        for name in UNITS:
            self.assertEqual(read_unit(name)["Service"]["Restart"][0], "always", name)

    def test_a_login_retry_loop_cannot_hammer_the_broker(self) -> None:
        # moomoo rate-limits and eventually locks an account that is hit with
        # repeated failed logins, so OpenD must back off further than a
        # service whose restart costs nothing.
        self.assertGreaterEqual(
            int(read_unit("opend.service")["Service"]["RestartSec"][0]), 30
        )

    def test_environment_arrives_from_a_file_and_never_from_the_unit(self) -> None:
        for name in UNITS:
            service = read_unit(name)["Service"]
            paths = service["EnvironmentFile"]
            self.assertEqual(len(paths), 1, f"{name} reads more than one env file")
            self.assertTrue(
                paths[0].lstrip("-").startswith(f"{ENVIRONMENT_DIR}/"),
                f"{name} reads its environment from outside {ENVIRONMENT_DIR}",
            )
            self.assertFalse(
                paths[0].startswith("-"),
                f"{name} tolerates a missing environment file",
            )
            # Environment= is visible to every local account through
            # `systemctl show`; EnvironmentFile= is read by the manager and is
            # not, which is the whole reason the token lives in a file.
            self.assertNotIn("Environment", service, f"{name} inlines an environment")

    def test_no_unit_carries_a_credential_in_plaintext(self) -> None:
        for name in UNITS:
            for line in (UNIT_DIR / name).read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                if key.strip() == "EnvironmentFile":
                    continue
                self.assertNotRegex(
                    value,
                    r"[0-9a-fA-F]{32,}",
                    f"{name} contains something shaped like a secret",
                )
                if SECRET_NAME.search(key):
                    self.fail(f"{name} sets {key.strip()} in the unit itself")

    def test_every_unit_declares_the_hardening_floor(self) -> None:
        for name in UNITS:
            service = read_unit(name)["Service"]
            for key, expected in HARDENING_FLOOR.items():
                self.assertIn(key, service, f"{name} is missing {key}")
                self.assertEqual(service[key][0], expected, f"{name} weakens {key}")

    def test_every_unit_restricts_itself_to_ip_and_unix_sockets(self) -> None:
        for name in UNITS:
            families = set(read_unit(name)["Service"]["RestrictAddressFamilies"][0].split())
            self.assertTrue(families, f"{name} restricts no address family")
            self.assertTrue(
                families <= ALLOWED_ADDRESS_FAMILIES,
                f"{name} allows {families - ALLOWED_ADDRESS_FAMILIES}",
            )

    def test_every_unit_drops_every_capability(self) -> None:
        for name in UNITS:
            service = read_unit(name)["Service"]
            self.assertEqual(service["CapabilityBoundingSet"], [""], name)
            self.assertEqual(service["AmbientCapabilities"], [""], name)

    def test_every_unit_filters_privileged_system_calls(self) -> None:
        for name in UNITS:
            filters = read_unit(name)["Service"]["SystemCallFilter"]
            self.assertIn("@system-service", filters[0], name)
            self.assertTrue(
                any(entry.startswith("~") for entry in filters),
                f"{name} has no deny list",
            )

    def test_neither_python_service_can_open_a_connection_off_this_host(self) -> None:
        # Both speak only to loopback. Denying everything else means no
        # misconfiguration or dependency can turn either into a client of a
        # broker endpoint; OpenD is excluded because it must reach moomoo.
        for name in PYTHON_UNITS:
            service = read_unit(name)["Service"]
            self.assertEqual(service["IPAddressDeny"], ["any"], name)
            self.assertEqual(service["IPAddressAllow"], ["localhost"], name)

    def test_logs_go_to_journald_and_nowhere_else(self) -> None:
        for name in UNITS:
            service = read_unit(name)["Service"]
            self.assertEqual(service["StandardOutput"][0], "journal", name)
            self.assertEqual(service["StandardError"][0], "journal", name)
            self.assertIn("SyslogIdentifier", service, f"{name} logs unidentified")

    def test_the_chain_is_ordered_without_coupling_the_failures(self) -> None:
        # A hard dependency would stop the analysis API when OpenD stops, and
        # the API's honest "unavailable" answer is exactly what the phone needs
        # at that moment. Ordering yes, coupling no.
        for name, upstream in (
            ("market-gateway.service", "opend.service"),
            ("analysis-api.service", "market-gateway.service"),
        ):
            unit = read_unit(name)["Unit"]
            self.assertIn(upstream, " ".join(unit["After"]), f"{name} is unordered")
            self.assertNotIn("Requires", unit, f"{name} hard-requires an upstream")
            self.assertNotIn("BindsTo", unit, f"{name} binds to an upstream")

    def test_no_command_runs_with_privileges_the_service_user_lacks(self) -> None:
        for name in UNITS:
            service = read_unit(name)["Service"]
            self.assertNotIn("PermissionsStartOnly", service, name)
            for key, values in service.items():
                if not key.startswith("Exec"):
                    continue
                for value in values:
                    self.assertFalse(
                        value.startswith(("+", "!")),
                        f"{name} runs {key} with elevated privileges",
                    )

    def test_python_services_run_from_a_tree_they_cannot_write(self) -> None:
        # `python -m` puts the working directory on sys.path, so a directory
        # the service user could write to would be an import-time backdoor.
        for name in PYTHON_UNITS:
            service = read_unit(name)["Service"]
            self.assertEqual(service["WorkingDirectory"][0], INSTALL_ROOT, name)
            self.assertTrue(service["ExecStart"][0].startswith("/"), name)
            self.assertNotIn("ReadWritePaths", service, f"{name} may write somewhere")


class EnvironmentTemplateTests(unittest.TestCase):
    def test_every_unit_has_a_template_for_its_environment_file(self) -> None:
        for name in UNITS:
            expected = f"{name.removesuffix('.service')}.env.example"
            self.assertTrue((ENV_DIR / expected).is_file(), f"{expected} is missing")

    def test_no_template_ships_a_value_for_a_secret(self) -> None:
        # An empty token is not an oversight: the analysis API refuses to start
        # without one, so a template that was never filled in fails loudly.
        found: set[str] = set()
        for path in sorted(ENV_DIR.glob("*.env.example")):
            for key, value in read_environment(path.name).items():
                if SECRET_NAME.search(key):
                    found.add(key)
                    self.assertEqual(value, "", f"{path.name} ships a value for {key}")
        self.assertIn("ANALYSIS_API_TOKEN", found)

    def test_no_template_binds_a_public_interface(self) -> None:
        templates = sorted(ENV_DIR.glob("*.env.example"))
        self.assertEqual(len(templates), len(UNITS))
        for path in templates:
            text = path.read_text(encoding="utf-8")
            for address in ("0.0.0.0", "::"):
                self.assertNotIn(
                    address, text, f"{path.name} names a wildcard bind address"
                )

    def test_no_template_puts_login_material_on_a_command_line(self) -> None:
        # Arguments are world-readable through /proc/<pid>/cmdline, so a login
        # flag there hands the account to every local process.
        arguments = read_environment("opend.env.example").get("OPEND_ARGS", "")
        for flag in ("login_account", "login_pwd", "passwd", "password", "token"):
            self.assertNotIn(flag, arguments, f"OPEND_ARGS carries {flag}")

    def test_the_analysis_api_still_demands_a_token_behind_caddy(self) -> None:
        # The loopback default drops the token outright, which behind a public
        # reverse proxy would publish the whole decision chain unauthenticated.
        # This is the single most load-bearing line of the deployment.
        config = AnalysisServerConfig.from_environment(self._issued_analysis_env())
        self.assertTrue(config.allow_lan)
        self.assertFalse(config.authorizes(None))
        self.assertFalse(config.authorizes("Bearer not-the-issued-token"))
        self.assertTrue(config.authorizes(f"Bearer {self._token()}"))

    def test_the_analysis_api_answers_only_the_local_reverse_proxy(self) -> None:
        config = AnalysisServerConfig.from_environment(self._issued_analysis_env())
        self.assertEqual(config.host, "127.0.0.1")
        self.assertTrue(config.allows_client("127.0.0.1"))
        self.assertFalse(config.allows_client("203.0.113.7"))

    def test_the_shipped_template_fails_closed_until_a_token_is_issued(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisServerConfig.from_environment(
                read_environment("analysis-api.env.example")
            )

    def test_the_gateway_template_stays_on_loopback(self) -> None:
        config = GatewayServerConfig.from_environment(
            read_environment("market-gateway.env.example")
        )
        self.assertEqual(config.host, "127.0.0.1")
        self.assertFalse(config.allow_lan)
        self.assertEqual(config.allowed_client_networks, ("127.0.0.0/8", "::1/128"))

    def test_each_template_puts_every_package_it_imports_on_the_path(self) -> None:
        expected = {
            "market-gateway.env.example": (
                "services/market_gateway/src",
                "services/analysis_core",
            ),
            "analysis-api.env.example": (
                "services/analysis_api/src",
                "services/analysis_core",
                "services/information_layer",
                "services/adviser_layer",
                "services/decision_engine",
            ),
        }
        for name, packages in expected.items():
            entries = read_environment(name)["PYTHONPATH"].split(":")
            for package in packages:
                self.assertIn(
                    f"{INSTALL_ROOT}/{package}",
                    entries,
                    f"{name} would start with an unimportable package",
                )

    def _token(self) -> str:
        return "0" * 64

    def _issued_analysis_env(self) -> dict[str, str]:
        environment = read_environment("analysis-api.env.example")
        environment["ANALYSIS_API_TOKEN"] = self._token()
        return environment


class RunbookTests(unittest.TestCase):
    def test_the_runbook_names_every_file_it_ships(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        for path in shipped_files():
            relative = path.relative_to(DEPLOY_ROOT).as_posix()
            if relative == "README.md":
                continue
            self.assertIn(relative, text, f"{relative} ships undocumented")

    def test_the_runbook_leaves_the_moomoo_login_with_the_operator(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("never", text.lower())
        for claim in (
            "no automation enters",
            "never committed",
            "log in to moomoo yourself",
        ):
            self.assertIn(claim, text.lower(), f"the runbook does not state: {claim}")

    def test_the_runbook_states_that_the_broker_session_lives_on_this_host(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8").lower()
        self.assertIn("security decision", text)
        self.assertIn("logged-in moomoo session", text)

    def test_the_runbook_opens_only_https_and_ssh(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        allowed = set(re.findall(r"ufw allow (\S+)", text))
        self.assertTrue(allowed, "the runbook configures no firewall")
        self.assertTrue(
            allowed <= {"443/tcp", "OpenSSH"},
            f"the runbook opens {allowed - {'443/tcp', 'OpenSSH'}}",
        )
        for port in (MARKET_GATEWAY_PORT, OPEND_PORT, ANALYSIS_API_PORT):
            self.assertNotIn(
                f"ufw allow {port}", text, f"the runbook opens port {port}"
            )

    def test_the_runbook_states_what_the_static_token_still_cannot_do(self) -> None:
        # There is no single-use pairing endpoint yet. Describing the shipped
        # token as if it were one would leave the operator believing in a
        # revocation path that does not exist. The denial has to be the words
        # on the page: a mutation proved that looking for "single-use" anywhere
        # in the file was satisfied by an unrelated sentence.
        text = RUNBOOK.read_text(encoding="utf-8").lower()
        self.assertIn("not a single-use pairing code", text)
        self.assertIn("no per-device revocation", text)
        self.assertIn("invalidates every device at once", text)


class ScriptTests(unittest.TestCase):
    def test_every_script_is_executable(self) -> None:
        for name in SCRIPTS:
            self.assertTrue(
                os.access(DEPLOY_ROOT / name, os.X_OK), f"{name} is not executable"
            )

    def test_every_script_stops_on_an_unset_variable(self) -> None:
        # An unset path variable that expands to nothing turns a targeted check
        # or a targeted write into one against the wrong file.
        for name in SCRIPTS:
            self.assertIn(
                "set -euo pipefail",
                (DEPLOY_ROOT / name).read_text(encoding="utf-8"),
                f"{name} keeps going after an unset variable",
            )


if __name__ == "__main__":
    unittest.main()
