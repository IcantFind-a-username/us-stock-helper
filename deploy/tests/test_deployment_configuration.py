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

from us_stock_helper_analysis_api.http_app import (
    PAIRING_PATH,
    AnalysisServerConfig,
    _PATHS,
    _READ_PATHS,
)
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
SCRIPTS = ("preflight.sh", "issue-pairing-code.sh")

ANALYSIS_API_PORT = "8770"
MARKET_GATEWAY_PORT = "8765"
OPEND_PORT = "11111"

INSTALL_ROOT = "/opt/us-stock-helper"
ENVIRONMENT_DIR = "/etc/us-stock-helper"
# systemd creates this directory, owns its mode, and it is the only place the
# analysis API may write. ProtectSystem=strict and ProtectHome=yes make every
# other path read-only to it, the package's own default under $HOME included.
STATE_DIRECTORY = "us-stock-helper-analysis-api"
DEVICE_DATABASE = f"/var/lib/{STATE_DIRECTORY}/device-auth.sqlite3"

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


def caddy_matchers() -> dict[str, dict[str, list[str]]]:
    """Every named matcher in the Caddyfile, as {name: {token: values}}.

    Both spellings are read: the one-line `@name method GET` and the block
    form. A negated token keeps its `not ` prefix, because the negation is the
    part that makes two matchers disjoint and dropping it here would make this
    parser agree with a file that does not.
    """
    matchers: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for line in caddyfile_lines():
        if current is not None:
            if line == "}":
                current = None
            elif line and not line.startswith("#"):
                token, _, arguments = line.partition(" ")
                if token == "not":
                    token, _, arguments = arguments.partition(" ")
                    token = f"not {token}"
                current.setdefault(token, []).extend(arguments.split())
            continue
        if not line.startswith("@"):
            continue
        name, _, rest = line[1:].partition(" ")
        current = matchers.setdefault(name, {})
        if rest.strip() == "{":
            continue
        token, _, arguments = rest.strip().removesuffix("{").strip().partition(" ")
        if token == "not":
            token, _, arguments = arguments.partition(" ")
            token = f"not {token}"
        if token:
            current.setdefault(token, []).extend(arguments.split())
        current = None
    return matchers


def caddy_matches(matcher: dict[str, list[str]], method: str, path: str) -> bool:
    """Whether one request shape satisfies one named matcher.

    Only the two matcher types this file uses are understood; anything else
    raises rather than being silently treated as a match, because a matcher
    this cannot read is a matcher whose disjointness was never checked.
    """
    for token, values in matcher.items():
        negated = token.startswith("not ")
        name = token.removeprefix("not ")
        if name == "method":
            hit = method in values
        elif name == "path":
            hit = path in values
        else:
            raise AssertionError(f"the edge uses a matcher this test cannot read: {name}")
        if hit == negated:
            return False
    return True


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
    """The pairing service is served now, and this is where that is pinned.

    The test that stood here asserted the opposite — that no HTTP boundary
    reached `services/device_auth` — so that the day one did, the three
    deployment facts riding on that absence would be revisited together instead
    of one at a time. They were the runbook's revocation section, the
    fail-closed rule for the credential, and the unit's refusal to grant a
    writable directory for a credential database. All three moved, and each has
    its own test below; what is left here is the wiring itself and the removal
    of the credential it replaced.
    """

    def test_the_analysis_api_reaches_the_pairing_service(self) -> None:
        sources = sorted(ANALYSIS_API_SOURCE.rglob("*.py"))
        self.assertTrue(sources, "the analysis API source tree was not found")
        text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
        self.assertIn("us_stock_helper_device_auth", text)
        self.assertIn(PAIRING_PATH, text)

    def test_the_retired_static_token_stops_a_deployment_that_still_sets_it(
        self,
    ) -> None:
        # Ignoring the variable would leave an operator believing the token
        # they issued is being checked, while the only credential that opens
        # the service is one they have never seen.
        environment = read_environment("analysis-api.env.example")
        with self.assertRaisesRegex(ValueError, "ANALYSIS_API_TOKEN"):
            AnalysisServerConfig.from_environment(
                {**environment, "ANALYSIS_API_TOKEN": "0" * 64}
            )

    def test_no_template_or_unit_still_carries_the_retired_token(self) -> None:
        shipped = [ENV_DIR / f"{name}.env.example" for name in
                   (unit.removesuffix(".service") for unit in UNITS)]
        shipped += [UNIT_DIR / name for name in UNITS]
        for path in shipped:
            self.assertNotIn(
                "ANALYSIS_API_TOKEN",
                path.read_text(encoding="utf-8"),
                f"{path.name} still configures a credential nothing reads",
            )

    def test_the_pairing_path_is_the_only_path_that_was_added(self) -> None:
        self.assertEqual(_PATHS, _READ_PATHS | {PAIRING_PATH})
        self.assertNotIn(PAIRING_PATH, _READ_PATHS)


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

    def test_the_public_read_allowlist_matches_the_served_read_allowlist(self) -> None:
        api = caddy_matchers()["api"]

        self.assertEqual(set(api["path"]), _READ_PATHS)
        self.assertEqual(api["method"], ["GET"])
        # The write is routed by its own matcher, so it must not also be
        # reachable through the read allowlist.
        self.assertNotIn(PAIRING_PATH, api["path"])

    def test_the_only_write_the_edge_admits_is_the_pairing_exchange(self) -> None:
        matchers = caddy_matchers()
        writes = {
            name
            for name, matcher in matchers.items()
            if any(method != "GET" for method in matcher.get("method", ()))
        }

        self.assertEqual(writes, {"pairing"})
        self.assertEqual(matchers["pairing"]["method"], ["POST"])
        self.assertEqual(matchers["pairing"]["path"], [PAIRING_PATH])
        self.assertRegex(CADDYFILE.read_text(encoding="utf-8"), r"respond\s+405")

    def test_no_request_can_match_two_of_the_edge_matchers(self) -> None:
        """The edge's answer must not depend on the order Caddy sorts routes in.

        `handle` blocks are mutually exclusive, but which of two matching
        blocks wins is a question about Caddy's route ordering, and nothing
        about who may write to this service should rest on the answer. Every
        matcher therefore pins its method as well as its path, and this is the
        test that says so: at most one may ever match.
        """
        matchers = caddy_matchers()
        for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
            for path in sorted(_PATHS | {"/orders", "/", "/v1"}):
                with self.subTest(method=method, path=path):
                    matched = [
                        name
                        for name, matcher in matchers.items()
                        if caddy_matches(matcher, method, path)
                    ]

                    self.assertLessEqual(
                        len(matched), 1, f"{method} {path} matches {matched}"
                    )

    def test_the_edge_admits_exactly_the_reads_and_the_one_write(self) -> None:
        # Written out request by request, because "the allowlist looks right"
        # is not the same claim as "this request reaches the service". None
        # means no matcher at all, which is the catch-all 404.
        expected = {
            ("GET", "/health"): "api",
            ("GET", "/decision"): "api",
            ("GET", "/market-brief"): "api",
            ("POST", PAIRING_PATH): "pairing",
            ("POST", "/health"): "disallowed_method",
            ("DELETE", "/decision"): "disallowed_method",
            ("POST", "/market-brief"): "disallowed_method",
            ("POST", "/orders"): "disallowed_method",
            ("GET", PAIRING_PATH): None,
            ("PUT", PAIRING_PATH): None,
            ("GET", "/orders"): None,
        }
        matchers = caddy_matchers()
        for (method, path), name in expected.items():
            with self.subTest(method=method, path=path):
                matched = [
                    candidate
                    for candidate, matcher in matchers.items()
                    if caddy_matches(matcher, method, path)
                ]

                self.assertEqual(matched, [name] if name else [])

    def test_the_edge_states_the_address_it_observed_for_the_pairing_route(
        self,
    ) -> None:
        # The pairing throttle counts against this value. Caddy appends the
        # observed address to whatever the caller sent, so an operator reading
        # only the appended form would still be safe; replacing the header
        # outright means a caller cannot even write the history.
        self.assertRegex(
            CADDYFILE.read_text(encoding="utf-8"),
            r"header_up\s+X-Forwarded-For\s+\{http\.request\.remote\.host\}",
        )

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

    def test_the_analysis_api_writes_only_where_systemd_made_a_directory(self) -> None:
        """The credential database needs one writable path, and only one.

        `ProtectSystem=strict` leaves nothing writable, which is why the
        package's default under `$HOME` cannot work here. StateDirectory is the
        answer rather than ReadWritePaths because systemd creates it, owns its
        mode, and keeps it outside the install tree that `python -m` imports
        from.
        """
        service = read_unit("analysis-api.service")["Service"]

        self.assertEqual(service["StateDirectory"], [STATE_DIRECTORY])
        self.assertEqual(service["StateDirectoryMode"][0], "0700")
        self.assertEqual(service["ProtectSystem"][0], "strict")
        self.assertEqual(service["ProtectHome"][0], "yes")

    def test_the_gateway_is_granted_no_state_of_its_own(self) -> None:
        # It holds no credential and writes nothing; a directory it never uses
        # is a directory a compromise could use.
        self.assertNotIn(
            "StateDirectory", read_unit("market-gateway.service")["Service"]
        )


class EnvironmentTemplateTests(unittest.TestCase):
    def test_every_unit_has_a_template_for_its_environment_file(self) -> None:
        for name in UNITS:
            expected = f"{name.removesuffix('.service')}.env.example"
            self.assertTrue((ENV_DIR / expected).is_file(), f"{expected} is missing")

    def test_no_template_ships_a_value_for_a_secret(self) -> None:
        # There is no secret left in these templates to fill in: the phone's
        # credential is minted by the pairing exchange and lives in the
        # database, never in a file an operator edits. The check stays because
        # the next variable someone adds might be one.
        for path in sorted(ENV_DIR.glob("*.env.example")):
            for key, value in read_environment(path.name).items():
                if SECRET_NAME.search(key):
                    self.assertEqual(value, "", f"{path.name} ships a value for {key}")

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

    def test_the_analysis_api_still_demands_a_credential_behind_caddy(self) -> None:
        # Behind a public reverse proxy every request arrives from loopback, so
        # a service that trusted its peer address would publish the whole
        # decision chain unauthenticated. This is the single most load-bearing
        # line of the deployment; only the credential behind it changed.
        config = AnalysisServerConfig.from_environment(
            read_environment("analysis-api.env.example")
        )

        self.assertTrue(config.trust_proxy)
        self.assertEqual(config.device_database, DEVICE_DATABASE)

    def test_the_shipped_template_fails_closed_without_that_credential(self) -> None:
        environment = read_environment("analysis-api.env.example")
        self.assertIn("DEVICE_AUTH_DATABASE", environment)
        del environment["DEVICE_AUTH_DATABASE"]

        with self.assertRaisesRegex(ValueError, "DEVICE_AUTH_DATABASE"):
            AnalysisServerConfig.from_environment(environment)

    def test_the_credential_database_lives_where_systemd_created_a_directory(
        self,
    ) -> None:
        # A path the unit does not grant is a service that cannot start, and
        # the failure would read as a permission problem rather than as a
        # missing StateDirectory line.
        environment = read_environment("analysis-api.env.example")
        state = read_unit("analysis-api.service")["Service"]["StateDirectory"][0]

        self.assertTrue(
            environment["DEVICE_AUTH_DATABASE"].startswith(f"/var/lib/{state}/"),
            "the database is outside the only directory this unit may write",
        )

    def test_the_analysis_api_answers_only_the_local_reverse_proxy(self) -> None:
        config = AnalysisServerConfig.from_environment(
            read_environment("analysis-api.env.example")
        )
        self.assertEqual(config.host, "127.0.0.1")
        self.assertTrue(config.allows_client("127.0.0.1"))
        self.assertFalse(config.allows_client("203.0.113.7"))

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
                # Without this the service starts and then refuses every
                # request, because the credential it verifies against cannot be
                # imported.
                "services/device_auth/src",
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

    def test_the_runbook_states_how_a_phone_is_paired_and_cut_off(self) -> None:
        # The claims have to be the words on the page. A mutation once showed
        # that looking for "single-use" anywhere in the file was satisfied by
        # an unrelated sentence, so each of these is a whole sentence that only
        # the pairing section can carry.
        text = RUNBOOK.read_text(encoding="utf-8").lower()
        for claim in (
            "the pairing code is single-use and expires",
            "revoke one phone without touching the others",
            "the device token is never printed",
        ):
            self.assertIn(claim, text, f"the runbook does not state: {claim}")

    def test_the_runbook_no_longer_promises_the_old_static_token(self) -> None:
        # These sentences described a deployment where revocation meant
        # re-typing a token on every phone. Leaving them next to a pairing flow
        # would tell the operator to do the one thing that no longer works.
        text = RUNBOOK.read_text(encoding="utf-8").lower()
        for stale in (
            "not a single-use pairing code",
            "no per-device revocation",
            "invalidates every device at once",
        ):
            self.assertNotIn(stale, text, f"the runbook still claims: {stale}")


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


class AccessLogPrivacyTests(unittest.TestCase):
    def test_both_client_address_fields_are_masked(self) -> None:
        """Masking one of the two still records where the reader is.

        Caddy writes remote_ip and client_ip; the log line also carries the
        requested symbol, so an unmasked address turns the access log into a
        record of who looked at what from where.
        """
        caddyfile = (DEPLOY_ROOT / "Caddyfile").read_text(encoding="utf-8")

        self.assertIn("request>remote_ip ip_mask", caddyfile)
        self.assertIn("request>client_ip ip_mask", caddyfile)


class EvidenceContactTests(unittest.TestCase):
    def test_the_sec_contact_address_is_templated_and_empty(self) -> None:
        """Shipping a real address would make every deployment poll as us."""
        template = (
            DEPLOY_ROOT / "env" / "analysis-api.env.example"
        ).read_text(encoding="utf-8")

        self.assertIn("US_STOCK_HELPER_CONTACT_EMAIL=", template)
        self.assertNotIn("US_STOCK_HELPER_CONTACT_EMAIL=@", template)
        for line in template.splitlines():
            if line.startswith("US_STOCK_HELPER_CONTACT_EMAIL="):
                self.assertEqual(line.split("=", 1)[1].strip(), "")

    def test_the_runbook_tells_the_operator_to_fill_it_in(self) -> None:
        runbook = (DEPLOY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("US_STOCK_HELPER_CONTACT_EMAIL", runbook)
