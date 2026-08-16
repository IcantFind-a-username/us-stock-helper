from __future__ import annotations

import contextlib
import dataclasses
import importlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


EXPECTED_ENVIRONMENT_KEYS = {
    "ANALYSIS_API_ALLOWED_CLIENTS",
    "ANALYSIS_API_ALLOW_LAN",
    "ANALYSIS_API_GATEWAY_URL",
    "ANALYSIS_API_HOST",
    "ANALYSIS_API_PORT",
    "ANTHROPIC_API_KEY",
    "MOOMOO_GATEWAY_ALLOWED_CLIENTS",
    "MOOMOO_GATEWAY_ALLOW_LAN",
    "MOOMOO_GATEWAY_HOST",
    "MOOMOO_GATEWAY_PORT",
    "MOOMOO_GATEWAY_TOKEN",
    "US_STOCK_HELPER_CONTACT_EMAIL",
}

SYNTHETIC_ENVIRONMENT = {
    "MOOMOO_GATEWAY_ALLOW_LAN": "true",
    "MOOMOO_GATEWAY_HOST": "203.0.113.20",
    "MOOMOO_GATEWAY_PORT": "19001",
    "MOOMOO_GATEWAY_TOKEN": "synthetic-gateway-secret-000000000001",
    "MOOMOO_GATEWAY_ALLOWED_CLIENTS": "192.0.2.0/24",
    "ANALYSIS_API_ALLOW_LAN": "true",
    "ANALYSIS_API_HOST": "203.0.113.21",
    "ANALYSIS_API_PORT": "19002",
    "ANALYSIS_API_ALLOWED_CLIENTS": "198.51.100.0/24",
    "ANALYSIS_API_GATEWAY_URL": "https://wrong.example.test:9443",
    "US_STOCK_HELPER_CONTACT_EMAIL": "runtime@example.test",
    "ANTHROPIC_API_KEY": "synthetic-anthropic-secret-000000000001",
}


def support_module():
    try:
        return importlib.import_module("scripts.local_runtime_support")
    except ModuleNotFoundError as error:
        raise AssertionError(
            "scripts.local_runtime_support is not implemented"
        ) from error


class RuntimeEnvironmentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.private_parent = self.root / ".us-stock-helper"
        self.private_parent.mkdir(mode=0o700)
        self.environment_path = self.private_parent / "lan.env"

    def write_environment(self, content: bytes, *, mode: int = 0o600) -> Path:
        if self.environment_path.exists():
            self.environment_path.chmod(0o600)
        self.environment_path.write_bytes(content)
        self.environment_path.chmod(mode)
        return self.environment_path

    def add_acl(self, path: Path, entry: str) -> None:
        if sys.platform != "darwin":
            self.skipTest("macOS extended ACL integration test")
        subprocess.run(["chmod", "+a", entry, str(path)], check=True)
        self.addCleanup(
            subprocess.run,
            ["chmod", "-N", str(path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def assert_extended_acl(self, path: Path, expected: bool) -> None:
        support = support_module()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        if path.is_dir():
            flags |= getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            self.assertEqual(
                support.DEFAULT_FILE_SYSTEM.has_extended_acl(descriptor), expected
            )
        finally:
            os.close(descriptor)

    @staticmethod
    def open_search(path: Path) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        if sys.platform == "darwin":
            flags = 0x40000000 | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        return os.open(path, flags)

    @staticmethod
    def encoded_environment(values: dict[str, str]) -> bytes:
        lines = ["# synthetic runtime environment", ""]
        lines.extend(f"{key}={value}" for key, value in values.items())
        return ("\n".join(lines) + "\n").encode("utf-8")

    def test_parser_accepts_blank_lines_comments_and_exact_current_key_set(
        self,
    ) -> None:
        support = support_module()
        self.write_environment(self.encoded_environment(SYNTHETIC_ENVIRONMENT))
        ambient_key = "US_STOCK_HELPER_TEST_AMBIENT_CANARY"
        ambient_value = "ambient-value-must-not-be-touched"

        with mock.patch.dict(os.environ, {ambient_key: ambient_value}, clear=False):
            before = dict(os.environ)
            parsed = support.parse_runtime_environment(self.environment_path)
            after = dict(os.environ)

        self.assertEqual(parsed, SYNTHETIC_ENVIRONMENT)
        self.assertEqual(set(parsed), EXPECTED_ENVIRONMENT_KEYS)
        self.assertEqual(after, before)

    def test_parser_refuses_non_regular_files_including_symlinks(self) -> None:
        support = support_module()
        directory_path = self.private_parent / "directory.env"
        directory_path.mkdir(mode=0o700)
        target_path = self.write_environment(
            self.encoded_environment(SYNTHETIC_ENVIRONMENT)
        )
        symlink_path = self.private_parent / "linked.env"
        symlink_path.symlink_to(target_path)

        for candidate in (directory_path, symlink_path):
            with self.subTest(candidate=candidate.name):
                with self.assertRaises(support.RuntimeConfigurationError):
                    support.parse_runtime_environment(candidate)

    def test_parser_refuses_fifo_without_waiting_for_a_writer(self) -> None:
        fifo_path = self.private_parent / "pipe.env"
        os.mkfifo(fifo_path, 0o600)
        repository = Path(__file__).resolve().parents[2]
        script = """
from pathlib import Path
import sys
from scripts.local_runtime_support import RuntimeConfigurationError, parse_runtime_environment
try:
    parse_runtime_environment(Path(sys.argv[1]))
except RuntimeConfigurationError:
    raise SystemExit(0)
raise SystemExit(2)
"""

        try:
            result = subprocess.run(
                [sys.executable, "-c", script, str(fifo_path)],
                cwd=repository,
                env={"PYTHONPATH": str(repository)},
                capture_output=True,
                check=False,
                timeout=1,
            )
        except subprocess.TimeoutExpired:
            self.fail("parser waited for a writer on a non-regular environment file")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")

    def test_parser_refuses_any_mode_other_than_0600(self) -> None:
        support = support_module()
        for mode in (0o400, 0o640, 0o644, 0o660):
            with self.subTest(mode=oct(mode)):
                self.write_environment(
                    self.encoded_environment(SYNTHETIC_ENVIRONMENT), mode=mode
                )
                with self.assertRaises(support.RuntimeConfigurationError):
                    support.parse_runtime_environment(self.environment_path)

    def test_parser_refuses_non_private_or_non_directory_parent(self) -> None:
        support = support_module()
        self.write_environment(self.encoded_environment(SYNTHETIC_ENVIRONMENT))
        self.private_parent.chmod(0o755)

        with self.assertRaises(support.RuntimeConfigurationError):
            support.parse_runtime_environment(self.environment_path)

    def test_parser_refuses_foreign_owner_on_parent_or_environment_file(self) -> None:
        support = support_module()
        self.write_environment(self.encoded_environment(SYNTHETIC_ENVIRONMENT))
        real_fstat = support.DEFAULT_FILE_SYSTEM.fstat

        for foreign_kind in ("directory", "file"):
            with self.subTest(foreign_kind=foreign_kind):
                def synthetic_fstat(descriptor: int):
                    metadata = real_fstat(descriptor)
                    is_target = (
                        foreign_kind == "directory" and stat.S_ISDIR(metadata.st_mode)
                    ) or (
                        foreign_kind == "file" and stat.S_ISREG(metadata.st_mode)
                    )
                    if not is_target:
                        return metadata
                    values = list(metadata)
                    values[4] = support.DEFAULT_FILE_SYSTEM.geteuid() + 1
                    return os.stat_result(values)

                filesystem = dataclasses.replace(
                    support.DEFAULT_FILE_SYSTEM, fstat=synthetic_fstat
                )
                with self.assertRaises(support.RuntimeConfigurationError):
                    support.parse_runtime_environment(
                        self.environment_path, filesystem=filesystem
                    )

    def test_parser_refuses_extended_acl_on_parent_or_environment_file(self) -> None:
        support = support_module()
        self.write_environment(self.encoded_environment(SYNTHETIC_ENVIRONMENT))

        self.add_acl(self.private_parent, "everyone allow search")
        self.assert_extended_acl(self.private_parent, True)
        with self.assertRaises(support.RuntimeConfigurationError):
            support.parse_runtime_environment(self.environment_path)

        subprocess.run(["chmod", "-N", str(self.private_parent)], check=True)
        self.add_acl(self.environment_path, "everyone allow read")
        self.assert_extended_acl(self.environment_path, True)
        with self.assertRaises(support.RuntimeConfigurationError):
            support.parse_runtime_environment(self.environment_path)

    def test_acl_boundary_imports_without_platform_support_and_fails_closed(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[2]
        module_path = repository / "scripts/local_runtime_support.py"
        script = r'''
import ctypes
import dataclasses
import errno
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

scenario = sys.argv[2]
if scenario == "non-darwin":
    sys.platform = "linux"

    def forbidden_cdll(*args, **kwargs):
        raise AssertionError("libc ACL loading must not run off macOS")

    ctypes.CDLL = forbidden_cdll
else:
    sys.platform = "darwin"

    class LibcWithoutAclSymbols:
        def __getattr__(self, name):
            raise AttributeError(name)

    ctypes.CDLL = lambda *args, **kwargs: LibcWithoutAclSymbols()

spec = importlib.util.spec_from_file_location("isolated_runtime_support", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

policy = getattr(module, "directory_acl_is_absent_or_protective", None)
if policy is None:
    raise AssertionError("native ACL policy is unavailable")
for operation in (
    module.DEFAULT_FILE_SYSTEM.has_extended_acl,
    module.DEFAULT_FILE_SYSTEM.clear_extended_acl,
    lambda descriptor: policy(descriptor, allow_protective=True),
):
    try:
        operation(0)
    except OSError as error:
        if error.errno != errno.ENOTSUP:
            raise
    else:
        raise AssertionError("unsupported ACL operation did not fail closed")

with tempfile.TemporaryDirectory() as temporary:
    private_parent = Path(temporary) / "private"
    private_parent.mkdir(mode=0o700)
    environment_path = private_parent / "runtime.env"
    environment_path.write_bytes(b"ANTHROPIC_API_KEY=synthetic-value\n")
    environment_path.chmod(0o600)
    try:
        module.parse_runtime_environment(environment_path)
    except module.RuntimeConfigurationError as error:
        if "synthetic-value" in str(error):
            raise AssertionError("unsupported ACL error exposed configuration data")
    else:
        raise AssertionError("default unsupported ACL boundary did not fail closed")
    injected = dataclasses.replace(
        module.DEFAULT_FILE_SYSTEM,
        has_extended_acl=lambda descriptor: False,
        clear_extended_acl=lambda descriptor: None,
    )
    parsed = module.parse_runtime_environment(environment_path, filesystem=injected)
    if parsed != {"ANTHROPIC_API_KEY": "synthetic-value"}:
        raise AssertionError("injected ACL filesystem boundary was not honored")
'''

        for scenario in ("non-darwin", "missing-symbols"):
            with self.subTest(scenario=scenario):
                result = subprocess.run(
                    [sys.executable, "-c", script, str(module_path), scenario],
                    cwd=repository,
                    env={"PYTHONPATH": str(repository)},
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stderr.decode("utf-8", errors="replace"),
                )
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")

    def test_directory_acl_policy_accepts_only_the_macos_protective_entry(
        self,
    ) -> None:
        if sys.platform != "darwin":
            self.skipTest("macOS extended ACL integration test")
        support = support_module()
        policy = support.directory_acl_is_absent_or_protective
        for protected_path in (
            Path.home().resolve(),
            Path.home().resolve() / "Documents",
        ):
            with self.subTest(protected_path=protected_path):
                descriptor = self.open_search(protected_path)
                try:
                    self.assertTrue(
                        policy(
                            descriptor,
                            allow_protective=True,
                        )
                    )
                    self.assertFalse(
                        policy(
                            descriptor,
                            allow_protective=False,
                        )
                    )
                finally:
                    os.close(descriptor)

        plain = self.root / "plain-acl-directory"
        plain.mkdir(mode=0o700)
        descriptor = self.open_search(plain)
        try:
            self.assertTrue(
                policy(
                    descriptor,
                    allow_protective=False,
                )
            )
        finally:
            os.close(descriptor)

        invalid_entries = {
            "allow writes": ["everyone allow add_file,add_subdirectory,delete_child"],
            "extra deny permission": ["everyone deny delete,delete_child"],
            "inherit flag": ["everyone deny delete,file_inherit"],
            "extra entry": ["everyone deny delete", "everyone deny read"],
        }
        for name, entries in invalid_entries.items():
            with self.subTest(name=name):
                directory = self.root / name.replace(" ", "-")
                directory.mkdir(mode=0o700)
                for entry in entries:
                    self.add_acl(directory, entry)
                descriptor = self.open_search(directory)
                try:
                    self.assertFalse(
                        policy(
                            descriptor,
                            allow_protective=True,
                        )
                    )
                finally:
                    os.close(descriptor)

    def test_directory_acl_policy_frees_qualifier_and_acl_exactly_once(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("macOS extended ACL ABI test")
        support = support_module()
        policy = support.directory_acl_is_absent_or_protective
        qualifier = (support.ctypes.c_ubyte * 16)(*range(16))

        class SyntheticAclLibrary:
            def __init__(self) -> None:
                self.entries = 0
                self.freed: list[int] = []

            def acl_get_fd(self, descriptor):
                return 101

            def acl_get_entry(self, acl, entry_id, output):
                if self.entries:
                    support.ctypes.set_errno(support.errno.EINVAL)
                    return -1
                self.entries += 1
                output._obj.value = 202
                return 0

            def acl_get_tag_type(self, entry, output):
                output._obj.value = 2
                return 0

            def acl_get_qualifier(self, entry):
                return support.ctypes.addressof(qualifier)

            def acl_get_permset_mask_np(self, entry, output):
                output._obj.value = 0x10
                return 0

            def acl_get_flagset_np(self, value, output):
                output._obj.value = 303
                return 0

            def acl_get_flag_np(self, flagset, flag):
                return 0

            def acl_free(self, value):
                pointer = value if isinstance(value, int) else value.value
                self.freed.append(pointer)
                return 0

        library = SyntheticAclLibrary()
        with mock.patch.object(support, "_LIBC", library), mock.patch.object(
            support,
            "_everyone_group_uuid",
            return_value=bytes(qualifier),
        ):
            self.assertTrue(
                policy(
                    99,
                    allow_protective=True,
                )
            )

        self.assertEqual(
            library.freed,
            [support.ctypes.addressof(qualifier), 101],
        )

    def test_parser_rejects_invalid_assignment_syntax_without_leaking_values(
        self,
    ) -> None:
        support = support_module()
        marker = "sensitive-marker-must-not-appear"
        invalid_contents = {
            "duplicate key": (
                f"ANTHROPIC_API_KEY={marker}\nANTHROPIC_API_KEY=second\n"
            ).encode(),
            "unknown key": f"UNKNOWN_RUNTIME_KEY={marker}\n".encode(),
            "invalid key": f"lower_case={marker}\n".encode(),
            "missing equals": f"ANTHROPIC_API_KEY-{marker}\n".encode(),
            "nul": f"ANTHROPIC_API_KEY={marker}\x00tail\n".encode(),
            "tab control": f"ANTHROPIC_API_KEY={marker}\ttail\n".encode(),
            "carriage return": f"ANTHROPIC_API_KEY={marker}\r\n".encode(),
            "export syntax": f"export ANTHROPIC_API_KEY={marker}\n".encode(),
            "single quotes": f"ANTHROPIC_API_KEY='{marker}'\n".encode(),
            "double quotes": f'ANTHROPIC_API_KEY="{marker}"\n'.encode(),
            "command substitution": f"ANTHROPIC_API_KEY=$({marker})\n".encode(),
            "variable substitution": f"ANTHROPIC_API_KEY=${{{marker}}}\n".encode(),
            "bare variable": f"ANTHROPIC_API_KEY=${marker}\n".encode(),
            "backticks": f"ANTHROPIC_API_KEY=`{marker}`\n".encode(),
            "command separator": f"ANTHROPIC_API_KEY={marker};true\n".encode(),
            "pipe": f"ANTHROPIC_API_KEY={marker}|true\n".encode(),
            "background command": f"ANTHROPIC_API_KEY={marker}&true\n".encode(),
            "redirection": f"ANTHROPIC_API_KEY={marker}>file\n".encode(),
            "shell comment": f"ANTHROPIC_API_KEY={marker} # comment\n".encode(),
            "invalid utf8": b"ANTHROPIC_API_KEY=\xff\n",
        }

        for name, content in invalid_contents.items():
            with self.subTest(name=name):
                self.write_environment(content)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    stderr
                ):
                    with self.assertRaises(support.RuntimeConfigurationError) as raised:
                        support.parse_runtime_environment(self.environment_path)
                public_text = (
                    stdout.getvalue() + stderr.getvalue() + str(raised.exception)
                )
                self.assertNotIn(marker, public_text)

    def test_component_environments_are_fixed_minimal_and_secret_isolated(self) -> None:
        support = support_module()
        repository = self.root / "repo"
        home = self.root / "home"
        temporary = self.root / "tmp"
        ca_bundle = self.root / "python" / "certifi" / "cacert.pem"
        for path in (repository, home, temporary, ca_bundle.parent):
            path.mkdir(parents=True, exist_ok=True)
        ca_bundle.write_text("synthetic certificate bundle", encoding="utf-8")

        common = {
            "HOME": str(home),
            "PATH": (
                "/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:"
                "/usr/bin:/bin:/usr/sbin:/sbin"
            ),
            "TMPDIR": str(temporary),
        }
        python_common = {
            **common,
            "PYTHONUNBUFFERED": "1",
            "REQUESTS_CA_BUNDLE": str(ca_bundle),
            "SSL_CERT_FILE": str(ca_bundle),
        }
        expected = {
            "market-loopback": {
                **python_common,
                "MOOMOO_GATEWAY_HOST": "127.0.0.1",
                "MOOMOO_GATEWAY_PORT": "8765",
                "PYTHONPATH": ":".join(
                    (
                        str(repository / "services/market_gateway/src"),
                        str(repository / "services/analysis_core"),
                    )
                ),
            },
            "market-lan": {
                **python_common,
                "MOOMOO_GATEWAY_ALLOW_LAN": "1",
                "MOOMOO_GATEWAY_HOST": "0.0.0.0",
                "MOOMOO_GATEWAY_PORT": "8766",
                "MOOMOO_GATEWAY_TOKEN": SYNTHETIC_ENVIRONMENT["MOOMOO_GATEWAY_TOKEN"],
                "MOOMOO_GATEWAY_ALLOWED_CLIENTS": SYNTHETIC_ENVIRONMENT[
                    "MOOMOO_GATEWAY_ALLOWED_CLIENTS"
                ],
                "PYTHONPATH": ":".join(
                    (
                        str(repository / "services/market_gateway/src"),
                        str(repository / "services/analysis_core"),
                    )
                ),
            },
            "analysis-api": {
                **python_common,
                "ANALYSIS_API_ALLOW_LAN": "1",
                "ANALYSIS_API_HOST": "0.0.0.0",
                "ANALYSIS_API_PORT": "8770",
                "ANALYSIS_API_ALLOWED_CLIENTS": SYNTHETIC_ENVIRONMENT[
                    "ANALYSIS_API_ALLOWED_CLIENTS"
                ],
                "ANALYSIS_API_GATEWAY_URL": "http://127.0.0.1:8765",
                "ANTHROPIC_API_KEY": SYNTHETIC_ENVIRONMENT["ANTHROPIC_API_KEY"],
                "DEVICE_AUTH_DATABASE": str(
                    home / ".us-stock-helper/state/devices.sqlite3"
                ),
                "ANALYSIS_API_COORDINATOR_STATE": str(
                    home / ".us-stock-helper/state/coordinator.json"
                ),
                "PYTHONPATH": ":".join(
                    str(repository / relative)
                    for relative in (
                        "services/analysis_api/src",
                        "services/analysis_core",
                        "services/information_layer",
                        "services/adviser_layer",
                        "services/decision_engine",
                        "services/device_auth/src",
                        "services/adviser_llm/src",
                    )
                ),
                "US_STOCK_HELPER_CONTACT_EMAIL": SYNTHETIC_ENVIRONMENT[
                    "US_STOCK_HELPER_CONTACT_EMAIL"
                ],
            },
            "metro": {
                **common,
                "EXPO_PUBLIC_INITIAL_DEMO_MODE": "false",
            },
        }

        actual = {
            component: support.build_component_environment(
                component,
                SYNTHETIC_ENVIRONMENT,
                repository=repository,
                home=home,
                temporary_directory=temporary,
                ca_bundle=ca_bundle,
            )
            for component in expected
        }

        self.assertEqual(actual, expected)
        self.assertEqual(
            [
                name
                for name, environment in actual.items()
                if "ANTHROPIC_API_KEY" in environment
            ],
            ["analysis-api"],
        )
        self.assertEqual(
            [
                name
                for name, environment in actual.items()
                if "MOOMOO_GATEWAY_TOKEN" in environment
            ],
            ["market-lan"],
        )

    def test_component_builder_rejects_unknown_component_and_relative_paths(
        self,
    ) -> None:
        support = support_module()
        absolute = self.root.resolve()

        with self.assertRaises(support.RuntimeConfigurationError):
            support.build_component_environment(
                "unknown-component",
                SYNTHETIC_ENVIRONMENT,
                repository=absolute,
                home=absolute,
                temporary_directory=absolute,
                ca_bundle=absolute / "cacert.pem",
            )
        with self.assertRaises(support.RuntimeConfigurationError):
            support.build_component_environment(
                "metro",
                SYNTHETIC_ENVIRONMENT,
                repository=Path("relative-repository"),
                home=absolute,
                temporary_directory=absolute,
                ca_bundle=absolute / "cacert.pem",
            )

    def test_component_builder_reports_missing_required_key_without_other_values(
        self,
    ) -> None:
        support = support_module()
        values = dict(SYNTHETIC_ENVIRONMENT)
        values.pop("MOOMOO_GATEWAY_TOKEN")

        with self.assertRaises(support.RuntimeConfigurationError) as raised:
            support.build_component_environment(
                "market-lan",
                values,
                repository=self.root,
                home=self.root,
                temporary_directory=self.root,
                ca_bundle=self.root / "cacert.pem",
            )

        message = str(raised.exception)
        self.assertIn("MOOMOO_GATEWAY_TOKEN", message)
        for value in SYNTHETIC_ENVIRONMENT.values():
            self.assertNotIn(value, message)

    def test_private_path_helpers_create_and_repair_exact_modes_silently(self) -> None:
        support = support_module()
        runtime_directory = self.root / "runtime"
        log_directory = runtime_directory / "logs"
        log_file = log_directory / "market-loopback.log"
        marker = b"synthetic-private-file-value"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            support.ensure_private_directory(runtime_directory)
            support.ensure_private_directory(log_directory)
            support.ensure_private_file(log_file)
            runtime_directory.chmod(0o755)
            log_file.chmod(0o644)
            support.ensure_private_directory(runtime_directory)
            support.ensure_private_file(log_file)
            support.atomic_write_private_file(log_file, marker)

        self.assertEqual(stat.S_IMODE(runtime_directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(log_directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
        self.assertEqual(log_file.read_bytes(), marker)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            [path.name for path in log_directory.iterdir()],
            ["market-loopback.log"],
        )

    def test_private_path_helpers_clear_extended_acl(self) -> None:
        support = support_module()
        runtime_directory = self.root / "runtime"
        runtime_directory.mkdir(mode=0o700)
        log_file = self.private_parent / "runtime.log"
        log_file.write_bytes(b"existing")
        log_file.chmod(0o600)
        self.add_acl(runtime_directory, "everyone allow search")
        self.add_acl(log_file, "everyone allow read")

        support.ensure_private_directory(runtime_directory)
        support.ensure_private_file(log_file)

        self.assert_extended_acl(runtime_directory, False)
        self.assert_extended_acl(log_file, False)

    def test_private_file_restricts_mode_before_clearing_acl(self) -> None:
        support = support_module()
        log_file = self.private_parent / "runtime.log"
        log_file.write_bytes(b"existing")
        log_file.chmod(0o644)
        real_fstat = support.DEFAULT_FILE_SYSTEM.fstat
        events: list[str] = []

        def tracked_fchmod(descriptor: int, mode: int) -> None:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("fchmod")
            os.fchmod(descriptor, mode)

        def tracked_acl_clear(descriptor: int) -> None:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("clear_acl")
            support.DEFAULT_FILE_SYSTEM.clear_extended_acl(descriptor)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fchmod=tracked_fchmod,
            clear_extended_acl=tracked_acl_clear,
        )

        support.ensure_private_file(log_file, filesystem=filesystem)

        self.assertEqual(events, ["fchmod", "clear_acl"])

    def test_private_file_does_not_clear_acl_when_restrictive_chmod_fails(
        self,
    ) -> None:
        support = support_module()
        log_file = self.private_parent / "runtime.log"
        log_file.write_bytes(b"existing")
        log_file.chmod(0o644)
        real_fstat = support.DEFAULT_FILE_SYSTEM.fstat
        events: list[str] = []
        deny_acl_present = True

        def failing_fchmod(descriptor: int, mode: int) -> None:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("fchmod")
                raise OSError("synthetic chmod failure")
            os.fchmod(descriptor, mode)

        def tracked_acl_clear(descriptor: int) -> None:
            nonlocal deny_acl_present
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("clear_acl")
                deny_acl_present = False
            support.DEFAULT_FILE_SYSTEM.clear_extended_acl(descriptor)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fchmod=failing_fchmod,
            clear_extended_acl=tracked_acl_clear,
        )

        with self.assertRaises(support.RuntimeConfigurationError):
            support.ensure_private_file(log_file, filesystem=filesystem)

        self.assertEqual(events, ["fchmod"])
        self.assertTrue(deny_acl_present)

    def test_private_path_helpers_refuse_foreign_owned_managed_objects(self) -> None:
        support = support_module()
        runtime_directory = self.root / "runtime"
        runtime_directory.mkdir(mode=0o700)
        log_file = self.private_parent / "runtime.log"
        log_file.write_bytes(b"existing")
        log_file.chmod(0o600)
        real_fstat = support.DEFAULT_FILE_SYSTEM.fstat
        runtime_inode = runtime_directory.stat().st_ino

        for foreign_kind, operation in (
            (
                "directory",
                lambda fs: support.ensure_private_directory(
                    runtime_directory, filesystem=fs
                ),
            ),
            (
                "file",
                lambda fs: support.ensure_private_file(log_file, filesystem=fs),
            ),
        ):
            with self.subTest(foreign_kind=foreign_kind):
                def synthetic_fstat(descriptor: int):
                    metadata = real_fstat(descriptor)
                    is_target = (
                        foreign_kind == "directory"
                        and metadata.st_ino == runtime_inode
                    ) or (
                        foreign_kind == "file" and stat.S_ISREG(metadata.st_mode)
                    )
                    if not is_target:
                        return metadata
                    values = list(metadata)
                    values[4] = support.DEFAULT_FILE_SYSTEM.geteuid() + 1
                    return os.stat_result(values)

                filesystem = dataclasses.replace(
                    support.DEFAULT_FILE_SYSTEM, fstat=synthetic_fstat
                )
                with self.assertRaises(support.RuntimeConfigurationError):
                    operation(filesystem)

    def test_atomic_write_clears_inherited_acl_before_secret_bytes(self) -> None:
        support = support_module()
        inherited_parent = self.root / "inherited"
        inherited_parent.mkdir(mode=0o700)
        self.add_acl(
            inherited_parent,
            "everyone allow read,file_inherit,only_inherit",
        )
        destination = inherited_parent / "secret.env"
        marker = b"synthetic-secret-bytes"
        real_fstat = support.DEFAULT_FILE_SYSTEM.fstat
        events: list[str] = []

        def record_fchmod(descriptor: int, mode: int) -> None:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("fchmod")
            os.fchmod(descriptor, mode)

        def record_acl_clear(descriptor: int) -> None:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("clear_acl")
            support.DEFAULT_FILE_SYSTEM.clear_extended_acl(descriptor)

        def record_acl_check(descriptor: int) -> bool:
            metadata = real_fstat(descriptor)
            if stat.S_ISREG(metadata.st_mode):
                events.append("check_acl")
            return support.DEFAULT_FILE_SYSTEM.has_extended_acl(descriptor)

        def guarded_write(descriptor: int, content: bytes) -> int:
            if events != ["fchmod", "clear_acl", "check_acl"]:
                raise AssertionError("secret bytes were written before ACL removal")
            events.append("write")
            return os.write(descriptor, content)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fchmod=record_fchmod,
            clear_extended_acl=record_acl_clear,
            has_extended_acl=record_acl_check,
            write_fd=guarded_write,
        )

        support.atomic_write_private_file(destination, marker, filesystem=filesystem)

        self.assertEqual(destination.read_bytes(), marker)
        self.assertEqual(
            events,
            ["fchmod", "clear_acl", "check_acl", "write", "check_acl"],
        )
        self.assert_extended_acl(destination, False)

    def test_private_path_helpers_refuse_symlinks_and_non_private_parents(self) -> None:
        support = support_module()
        public_directory = self.root / "public"
        public_directory.mkdir(mode=0o755)
        target = self.root / "target.log"
        target.write_text("target", encoding="utf-8")
        target.chmod(0o600)
        linked = public_directory / "linked.log"
        linked.symlink_to(target)

        with self.assertRaises(support.RuntimeConfigurationError):
            support.ensure_private_file(linked)
        with self.assertRaises(support.RuntimeConfigurationError):
            support.atomic_write_private_file(public_directory / "new.log", b"value")


if __name__ == "__main__":
    unittest.main()
