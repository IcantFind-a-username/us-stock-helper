from __future__ import annotations

import dataclasses
import errno
import importlib
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


EXPECTED_COMPONENTS = {
    "market-loopback": "com.franz.us-stock-helper.market-loopback",
    "market-lan": "com.franz.us-stock-helper.market-lan",
    "analysis-api": "com.franz.us-stock-helper.analysis-api",
    "metro": "com.franz.us-stock-helper.metro",
}
EXPECTED_BRANCH = "feature/iphone-demo"
NODE_22 = "/opt/homebrew/opt/node@22/bin/node"
SYNTHETIC_GATEWAY_SECRET = "synthetic-gateway-secret-000000000002"
SYNTHETIC_ANTHROPIC_SECRET = "synthetic-anthropic-secret-000000000002"


def launcher_module():
    try:
        return importlib.import_module("scripts.local_runtime_launch")
    except ModuleNotFoundError as error:
        if error.name != "scripts.local_runtime_launch":
            raise
        raise AssertionError(
            "scripts.local_runtime_launch is not implemented"
        ) from error


def support_module():
    return importlib.import_module("scripts.local_runtime_support")


class LocalRuntimePlistTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.repository = Path(__file__).resolve().parents[2]
        self.account_home = Path.home().resolve()
        self.home = self.root / "home"
        self.private_root = self.home / ".us-stock-helper"
        self.temporary = self.private_root / "tmp"
        self.logs = self.private_root / "logs"
        for directory in (self.home, self.private_root, self.temporary, self.logs):
            directory.mkdir(mode=0o700)
        self.environment_file = self.private_root / "lan.env"
        self.environment_file.write_text(
            "\n".join(
                (
                    f"MOOMOO_GATEWAY_TOKEN={SYNTHETIC_GATEWAY_SECRET}",
                    "MOOMOO_GATEWAY_ALLOWED_CLIENTS=192.0.2.0/24",
                    "ANALYSIS_API_ALLOWED_CLIENTS=198.51.100.0/24",
                    "US_STOCK_HELPER_CONTACT_EMAIL=runtime@example.test",
                    f"ANTHROPIC_API_KEY={SYNTHETIC_ANTHROPIC_SECRET}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        self.environment_file.chmod(0o600)
        self.ca_bundle = next(
            (self.repository / "services/market_gateway/.venv/lib").glob(
                "python*/site-packages/certifi/cacert.pem"
            )
        )

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

    def render_all(self) -> dict[str, tuple[bytes, dict[str, object]]]:
        launcher = launcher_module()
        rendered = {}
        for component in EXPECTED_COMPONENTS:
            payload = launcher.render_launch_agent(
                component,
                repository=self.repository,
                home=self.home,
                environment_file=self.environment_file,
                temporary_directory=self.temporary,
                log_directory=self.logs,
                ca_bundle=self.ca_bundle,
            )
            rendered[component] = (payload, plistlib.loads(payload))
        return rendered

    def test_exactly_four_templates_render_as_valid_macos_plists(self) -> None:
        template_directory = self.repository / "runtime/launchagents"
        templates = sorted(template_directory.glob("*.plist.in"))
        self.assertEqual(
            [path.name for path in templates],
            sorted(f"{label}.plist.in" for label in EXPECTED_COMPONENTS.values()),
        )

        for component, (payload, document) in self.render_all().items():
            with self.subTest(component=component):
                self.assertEqual(document["Label"], EXPECTED_COMPONENTS[component])
                output = self.root / f"{component}.plist"
                output.write_bytes(payload)
                result = subprocess.run(
                    ["/usr/bin/plutil", "-lint", str(output)],
                    capture_output=True,
                    check=False,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_rendered_plists_enforce_the_fixed_absolute_launch_contract(self) -> None:
        expected_keys = {
            "Label",
            "ProgramArguments",
            "WorkingDirectory",
            "RunAtLoad",
            "KeepAlive",
            "ThrottleInterval",
            "Umask",
            "StandardOutPath",
            "StandardErrorPath",
        }
        venv_python = str(self.repository / "services/market_gateway/.venv/bin/python")
        launcher_path = str(self.repository / "scripts/local_runtime_launch.py")
        expo_cli = str(self.repository / "apps/mobile/node_modules/expo/bin/cli")
        seen_logs: set[str] = set()

        for component, (payload, document) in self.render_all().items():
            with self.subTest(component=component):
                self.assertEqual(set(document), expected_keys)
                self.assertIs(document["RunAtLoad"], True)
                self.assertIs(document["KeepAlive"], True)
                self.assertIs(type(document["ThrottleInterval"]), int)
                self.assertGreaterEqual(document["ThrottleInterval"], 5)
                self.assertIs(type(document["Umask"]), int)
                self.assertEqual(document["Umask"], 63)

                working_directory = document["WorkingDirectory"]
                expected_working_directory = (
                    self.repository / "apps/mobile"
                    if component == "metro"
                    else self.repository
                )
                self.assertEqual(working_directory, str(expected_working_directory))
                self.assertTrue(Path(working_directory).is_absolute())

                arguments = document["ProgramArguments"]
                self.assertIs(type(arguments), list)
                self.assertEqual(arguments[:3], [venv_python, launcher_path, component])
                self.assertEqual(arguments[0], venv_python)
                self.assertNotIn("/bin/sh", arguments)
                self.assertNotIn("/bin/zsh", arguments)
                self.assertNotIn("-c", arguments)
                self.assertNotIn("EnvironmentVariables", document)
                self.assertNotIn("Program", document)

                path_flags = {
                    "--repository",
                    "--home",
                    "--environment-file",
                    "--temporary-directory",
                    "--ca-bundle",
                }
                for index, argument in enumerate(arguments[:-1]):
                    if argument in path_flags:
                        self.assertTrue(
                            Path(arguments[index + 1]).is_absolute(),
                            f"{argument} was not followed by an absolute path",
                        )

                if component in {"market-lan", "analysis-api"}:
                    self.assertIn("--environment-file", arguments)
                else:
                    self.assertNotIn("--environment-file", arguments)
                if component == "metro":
                    self.assertNotIn("--ca-bundle", arguments)

                stdout_path = document["StandardOutPath"]
                stderr_path = document["StandardErrorPath"]
                self.assertTrue(Path(stdout_path).is_absolute())
                self.assertTrue(Path(stderr_path).is_absolute())
                self.assertNotEqual(stdout_path, stderr_path)
                self.assertNotIn(stdout_path, seen_logs)
                seen_logs.add(stdout_path)
                self.assertNotIn(stderr_path, seen_logs)
                seen_logs.add(stderr_path)

                rendered_text = payload.decode("utf-8")
                self.assertNotIn(SYNTHETIC_GATEWAY_SECRET, rendered_text)
                self.assertNotIn(SYNTHETIC_ANTHROPIC_SECRET, rendered_text)
                self.assertNotIn("__RUNTIME_", rendered_text)
                self.assertNotIn("${", rendered_text)

        self.assertEqual(len(seen_logs), 8)
        metro_arguments = self.render_all()["metro"][1]["ProgramArguments"]
        self.assertEqual(metro_arguments[:3], [venv_python, launcher_path, "metro"])

        invocation = launcher_module().prepare_launch(
            "metro",
            repository=self.repository,
            home=self.account_home,
            environment_file=None,
            temporary_directory=self.temporary,
            ca_bundle=None,
        )
        self.assertEqual(
            list(invocation.arguments),
            [NODE_22, expo_cli, "start", "--dev-client", "--lan", "--port", "8088"],
        )
        self.assertEqual(invocation.executable, NODE_22)
        self.assertEqual(invocation.working_directory, self.repository / "apps/mobile")

    def test_renderer_rejects_unknown_components_and_relative_paths(self) -> None:
        launcher = launcher_module()
        common = {
            "repository": self.repository,
            "home": self.home,
            "environment_file": self.environment_file,
            "temporary_directory": self.temporary,
            "log_directory": self.logs,
            "ca_bundle": self.ca_bundle,
        }
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.render_launch_agent("unknown", **common)

        for key in common:
            invalid = dict(common)
            invalid[key] = Path("relative/path")
            with self.subTest(relative=key):
                with self.assertRaises(launcher.RuntimeConfigurationError):
                    launcher.render_launch_agent("metro", **invalid)

    def test_launcher_builds_exact_commands_with_secret_isolation(self) -> None:
        launcher = launcher_module()
        market_python = str(
            self.repository / "services/market_gateway/.venv/bin/python"
        )
        expected = {
            "market-loopback": [
                market_python,
                "-m",
                "us_stock_helper_market_gateway",
            ],
            "market-lan": [
                market_python,
                "-m",
                "us_stock_helper_market_gateway",
            ],
            "analysis-api": [
                market_python,
                "-m",
                "us_stock_helper_analysis_api",
            ],
        }

        invocations = {}
        for component in EXPECTED_COMPONENTS:
            invocation = launcher.prepare_launch(
                component,
                repository=self.repository,
                home=self.account_home,
                environment_file=(
                    self.environment_file
                    if component in {"market-lan", "analysis-api"}
                    else None
                ),
                temporary_directory=self.temporary,
                ca_bundle=self.ca_bundle if component != "metro" else None,
            )
            invocations[component] = invocation
            self.assertEqual(invocation.executable, invocation.arguments[0])
            if component in expected:
                self.assertEqual(list(invocation.arguments), expected[component])

        loopback_environment = invocations["market-loopback"].environment
        metro_environment = invocations["metro"].environment
        lan_environment = invocations["market-lan"].environment
        analysis_environment = invocations["analysis-api"].environment
        for environment in (loopback_environment, metro_environment):
            self.assertNotIn("MOOMOO_GATEWAY_TOKEN", environment)
            self.assertNotIn("ANTHROPIC_API_KEY", environment)
        self.assertEqual(
            lan_environment["MOOMOO_GATEWAY_TOKEN"], SYNTHETIC_GATEWAY_SECRET
        )
        self.assertNotIn("ANTHROPIC_API_KEY", lan_environment)
        self.assertEqual(
            analysis_environment["ANTHROPIC_API_KEY"], SYNTHETIC_ANTHROPIC_SECRET
        )
        self.assertNotIn("MOOMOO_GATEWAY_TOKEN", analysis_environment)

    def test_loopback_and_metro_never_require_or_parse_the_secret_file(self) -> None:
        launcher = launcher_module()
        missing_environment = self.private_root / "does-not-exist.env"
        for component in ("market-loopback", "metro"):
            with self.subTest(component=component):
                invocation = launcher.prepare_launch(
                    component,
                    repository=self.repository,
                    home=self.account_home,
                    environment_file=None,
                    temporary_directory=self.temporary,
                    ca_bundle=self.ca_bundle if component != "metro" else None,
                )
                self.assertNotIn(str(missing_environment), invocation.arguments)

    def test_launcher_accepts_the_current_macos_account_home(self) -> None:
        launcher = launcher_module()
        account_home = Path.home().resolve()
        try:
            invocation = launcher.prepare_launch(
                "metro",
                repository=self.repository,
                home=account_home,
                environment_file=None,
                temporary_directory=self.temporary,
                ca_bundle=None,
            )
        except launcher.RuntimeConfigurationError:
            self.fail("the current macOS account home was rejected")
        self.assertEqual(invocation.environment["HOME"], str(account_home))

    def test_directory_chain_accepts_real_and_synthetic_trusted_paths(self) -> None:
        launcher = launcher_module()
        validate_chain = launcher.validate_runtime_directory_chain
        synthetic = self.root / "trusted" / "nested"
        synthetic.mkdir(parents=True, mode=0o700)
        expected = (
            self.account_home,
            self.account_home / "Documents",
            self.account_home / "Library",
            self.account_home / "Library/LaunchAgents",
            self.repository,
            synthetic,
        )
        for path in expected:
            with self.subTest(path=path):
                self.assertEqual(
                    validate_chain(path),
                    path,
                )

    def test_directory_chain_rejects_group_write_for_root_owned_directory(
        self,
    ) -> None:
        launcher = launcher_module()
        validate_chain = launcher.validate_runtime_directory_chain
        support = support_module()
        repository_metadata = self.repository.stat()
        real_fstat = os.fstat

        def root_group_writable(descriptor):
            metadata = real_fstat(descriptor)
            if (
                metadata.st_dev == repository_metadata.st_dev
                and metadata.st_ino == repository_metadata.st_ino
            ):
                fields = list(metadata)
                fields[0] |= stat.S_IWGRP
                fields[4] = 0
                return os.stat_result(fields)
            return metadata

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=root_group_writable,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            validate_chain(
                self.repository,
                filesystem=filesystem,
            )

    def test_directory_chain_rejects_symlink_and_nonprotective_acl_ancestors(
        self,
    ) -> None:
        launcher = launcher_module()
        validate_chain = launcher.validate_runtime_directory_chain
        real_parent = self.root / "real-parent"
        leaf = real_parent / "leaf"
        leaf.mkdir(parents=True, mode=0o700)
        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            validate_chain(linked_parent / "leaf")

        unsafe_parent = self.root / "unsafe-parent"
        unsafe_leaf = unsafe_parent / "leaf"
        unsafe_leaf.mkdir(parents=True, mode=0o700)
        self.add_acl(
            unsafe_parent,
            "everyone allow add_file,add_subdirectory,delete_child",
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            validate_chain(unsafe_leaf)

        unrelated_protective = self.root / "unrelated-protective"
        unrelated_protective.mkdir(mode=0o700)
        self.add_acl(unrelated_protective, "everyone deny delete")
        with self.assertRaises(launcher.RuntimeConfigurationError):
            validate_chain(unrelated_protective)

    def test_directory_chain_closes_every_open_descriptor_on_success_and_failure(
        self,
    ) -> None:
        launcher = launcher_module()
        validate_chain = launcher.validate_runtime_directory_chain
        support = support_module()
        target = self.root / "descriptor-chain" / "leaf"
        target.mkdir(parents=True, mode=0o700)
        active: set[int] = set()

        def tracked_open(*args, **kwargs):
            descriptor = os.open(*args, **kwargs)
            if descriptor in active:
                raise AssertionError("descriptor was reopened before close")
            active.add(descriptor)
            return descriptor

        def tracked_close(descriptor):
            if descriptor not in active:
                raise AssertionError("descriptor was closed without ownership")
            active.remove(descriptor)
            os.close(descriptor)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            open_fd=tracked_open,
            close_fd=tracked_close,
        )
        validate_chain(target, filesystem=filesystem)
        self.assertEqual(active, set())

        linked = self.root / "descriptor-link"
        linked.symlink_to(target, target_is_directory=True)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            validate_chain(
                linked,
                filesystem=filesystem,
            )
        self.assertEqual(active, set())

    def test_directory_chain_closes_child_when_parent_close_fails(self) -> None:
        launcher = launcher_module()
        support = support_module()
        target = self.root / "close-failure" / "leaf"
        target.mkdir(parents=True, mode=0o700)
        active: set[int] = set()
        failed_once = False

        def tracked_open(*args, **kwargs):
            descriptor = os.open(*args, **kwargs)
            active.add(descriptor)
            return descriptor

        def fail_one_parent_close(descriptor):
            nonlocal failed_once
            if not failed_once and len(active) == 2:
                failed_once = True
                active.remove(descriptor)
                os.close(descriptor)
                raise OSError(errno.EIO, "synthetic close failure")
            active.remove(descriptor)
            os.close(descriptor)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            open_fd=tracked_open,
            close_fd=fail_one_parent_close,
        )
        try:
            with self.assertRaises(launcher.RuntimeConfigurationError):
                launcher.validate_runtime_directory_chain(
                    target,
                    filesystem=filesystem,
                )
            self.assertEqual(active, set())
        finally:
            for descriptor in tuple(active):
                os.close(descriptor)

    def test_runtime_symlink_root_reopen_failure_does_not_double_close(self) -> None:
        launcher = launcher_module()
        support = support_module()
        active: set[int] = set()
        root_opens = 0

        def fail_second_root_open(*args, **kwargs):
            nonlocal root_opens
            if args[0] == Path("/"):
                root_opens += 1
                if root_opens == 2:
                    raise OSError(errno.EIO, "synthetic root reopen failure")
            descriptor = os.open(*args, **kwargs)
            active.add(descriptor)
            return descriptor

        def tracked_close(descriptor):
            if descriptor not in active:
                raise AssertionError("descriptor was closed twice")
            active.remove(descriptor)
            os.close(descriptor)

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            open_fd=fail_second_root_open,
            close_fd=tracked_close,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                Path(NODE_22),
                executable=True,
                allowed_symlinks=(Path("/opt/homebrew/opt/node@22"),),
                trusted_external=True,
                filesystem=filesystem,
            )
        self.assertEqual(active, set())

    def test_final_descriptor_close_failure_is_sanitized_without_retry(self) -> None:
        launcher = launcher_module()
        support = support_module()
        target = self.root / "final-close-failure"
        target.mkdir(mode=0o700)
        target_metadata = target.stat()
        active: set[int] = set()
        final_close_failures = 0

        def tracked_open(*args, **kwargs):
            descriptor = os.open(*args, **kwargs)
            active.add(descriptor)
            return descriptor

        def fail_after_final_close(descriptor):
            nonlocal final_close_failures
            if descriptor not in active:
                raise AssertionError("descriptor close was retried")
            metadata = os.fstat(descriptor)
            active.remove(descriptor)
            os.close(descriptor)
            if (
                metadata.st_dev == target_metadata.st_dev
                and metadata.st_ino == target_metadata.st_ino
            ):
                final_close_failures += 1
                raise OSError(errno.EIO, "synthetic final close failure")

        filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            open_fd=tracked_open,
            close_fd=fail_after_final_close,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_directory_chain(
                target,
                filesystem=filesystem,
            )
        self.assertEqual(final_close_failures, 1)
        self.assertEqual(active, set())

    def test_runtime_file_validator_supports_private_installed_plists(self) -> None:
        launcher = launcher_module()
        launch_agents = self.root / "private-launch-agents"
        launch_agents.mkdir(mode=0o700)
        plist = launch_agents / "com.example.runtime.plist"
        plist.write_text("synthetic plist", encoding="utf-8")
        plist.chmod(0o600)
        self.assertEqual(
            launcher.validate_runtime_file(
                plist,
                executable=False,
                required_mode=0o600,
            ),
            plist,
        )
        plist.chmod(0o644)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                plist,
                executable=False,
                required_mode=0o600,
            )

    def test_external_group_write_exceptions_are_exact_and_group_bound(self) -> None:
        launcher = launcher_module()
        support = support_module()
        node_opt = Path("/opt/homebrew/opt")
        node_opt_metadata = node_opt.stat()

        def untrusted_homebrew_group(descriptor):
            metadata = os.fstat(descriptor)
            if (
                metadata.st_dev == node_opt_metadata.st_dev
                and metadata.st_ino == node_opt_metadata.st_ino
            ):
                fields = list(metadata)
                fields[5] = node_opt_metadata.st_gid + 1
                return os.stat_result(fields)
            return metadata

        untrusted_homebrew_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=untrusted_homebrew_group,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                Path(NODE_22),
                executable=True,
                allowed_symlinks=(Path("/opt/homebrew/opt/node@22"),),
                trusted_external=True,
                filesystem=untrusted_homebrew_filesystem,
            )

        python_target = Path(
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
        )
        self.assertEqual(
            launcher.validate_runtime_file(
                python_target,
                executable=True,
                trusted_external=True,
            ),
            python_target,
        )

        target_metadata = python_target.stat()

        def untrusted_python_group(descriptor):
            metadata = os.fstat(descriptor)
            if (
                metadata.st_dev == target_metadata.st_dev
                and metadata.st_ino == target_metadata.st_ino
            ):
                fields = list(metadata)
                fields[5] = 20
                return os.stat_result(fields)
            return metadata

        untrusted_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=untrusted_python_group,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                python_target,
                executable=True,
                trusted_external=True,
                filesystem=untrusted_filesystem,
            )

        lookalike = self.root / "Python.framework/Versions/3.11/bin/python3.11"
        lookalike.parent.mkdir(parents=True, mode=0o755)
        lookalike.write_text("synthetic", encoding="utf-8")
        lookalike.chmod(0o755)
        lookalike_metadata = lookalike.stat()

        def root_wheel_group_write(descriptor):
            metadata = os.fstat(descriptor)
            if (
                metadata.st_dev == lookalike_metadata.st_dev
                and metadata.st_ino == lookalike_metadata.st_ino
            ):
                fields = list(metadata)
                fields[0] |= stat.S_IWGRP
                fields[4] = 0
                fields[5] = 0
                return os.stat_result(fields)
            return metadata

        lookalike_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=root_wheel_group_write,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                lookalike,
                executable=True,
                trusted_external=True,
                filesystem=lookalike_filesystem,
            )

    def test_explicit_runtime_symlinks_cannot_escape_canonical_prefix(self) -> None:
        launcher = launcher_module()
        escaped_root = self.root / "escaped-node"
        escaped_binary = escaped_root / "bin/node"
        escaped_binary.parent.mkdir(parents=True, mode=0o755)
        escaped_binary.write_text("synthetic executable", encoding="utf-8")
        escaped_binary.chmod(0o555)

        with mock.patch.object(
            launcher.os,
            "readlink",
            return_value=str(escaped_root),
        ):
            with self.assertRaises(launcher.RuntimeConfigurationError):
                launcher.validate_runtime_file(
                    Path(NODE_22),
                    executable=True,
                    allowed_symlinks=(Path("/opt/homebrew/opt/node@22"),),
                    trusted_external=True,
                )

    def test_launcher_rejects_unknown_component_before_filesystem_or_exec(self) -> None:
        launcher = launcher_module()
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.prepare_launch(
                "unknown",
                repository=Path("relative-repository"),
                home=Path("relative-home"),
                environment_file=self.private_root / "missing.env",
                temporary_directory=Path("relative-temporary"),
                ca_bundle=Path("relative-ca"),
            )

    def test_launcher_rejects_wrong_worktree_and_branch(self) -> None:
        launcher = launcher_module()
        support = support_module()
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_repository_identity(self.repository.parent)

        def wrong_branch_run(command, **kwargs):
            if command[-2:] == ["--show-toplevel"]:
                stdout = f"{self.repository}\n"
            else:
                stdout = "main\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        wrong_branch_runner = dataclasses.replace(
            support.DEFAULT_PROCESS_RUNNER,
            run=wrong_branch_run,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_repository_identity(
                self.repository,
                process_runner=wrong_branch_runner,
            )

    def test_launcher_rejects_missing_nonexecutable_or_unsafe_runtime_files(
        self,
    ) -> None:
        launcher = launcher_module()
        support = support_module()
        missing = self.root / "missing"
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(missing, executable=True)

        nonexecutable = self.root / "nonexecutable"
        nonexecutable.write_text("#!/bin/false\n", encoding="utf-8")
        nonexecutable.chmod(0o600)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(nonexecutable, executable=True)

        owner_without_owner_execute = self.root / "owner-without-owner-execute"
        owner_without_owner_execute.write_text("synthetic", encoding="utf-8")
        owner_without_owner_execute.chmod(0o601)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                owner_without_owner_execute,
                executable=True,
            )

        git_metadata = Path("/usr/bin/git").stat()

        def root_owner_only_execute(descriptor):
            metadata = os.fstat(descriptor)
            if (
                metadata.st_dev == git_metadata.st_dev
                and metadata.st_ino == git_metadata.st_ino
            ):
                fields = list(metadata)
                fields[0] = stat.S_IFREG | stat.S_IXUSR
                fields[4] = 0
                fields[5] = 0
                return os.stat_result(fields)
            return metadata

        root_owner_only_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=root_owner_only_execute,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                Path("/usr/bin/git"),
                executable=True,
                filesystem=root_owner_only_filesystem,
            )

        world_writable = self.root / "world-writable"
        world_writable.write_text("data", encoding="utf-8")
        world_writable.chmod(0o606)
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(world_writable, executable=False)

        root_group_writable = self.root / "root-group-writable"
        root_group_writable.write_text("data", encoding="utf-8")
        root_group_writable.chmod(0o640)
        root_group_metadata = root_group_writable.stat()

        def synthetic_root_group_write(descriptor):
            metadata = os.fstat(descriptor)
            if (
                metadata.st_dev == root_group_metadata.st_dev
                and metadata.st_ino == root_group_metadata.st_ino
            ):
                fields = list(metadata)
                fields[0] |= stat.S_IWGRP
                fields[4] = 0
                return os.stat_result(fields)
            return metadata

        root_group_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=synthetic_root_group_write,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                root_group_writable,
                executable=False,
                filesystem=root_group_filesystem,
            )

        real_stat = os.fstat

        def foreign_owner(descriptor):
            metadata = real_stat(descriptor)
            fields = list(metadata)
            fields[4] = support.DEFAULT_FILE_SYSTEM.geteuid() + 1000
            return os.stat_result(fields)

        foreign_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            fstat=foreign_owner,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                self.ca_bundle,
                executable=False,
                filesystem=foreign_filesystem,
            )

        acl_filesystem = dataclasses.replace(
            support.DEFAULT_FILE_SYSTEM,
            has_extended_acl=lambda descriptor: True,
        )
        with self.assertRaises(launcher.RuntimeConfigurationError):
            launcher.validate_runtime_file(
                self.ca_bundle,
                executable=False,
                filesystem=acl_filesystem,
            )

    def test_launcher_rejects_unsafe_environment_mode_without_leaking_values(
        self,
    ) -> None:
        launcher = launcher_module()
        self.environment_file.chmod(0o644)
        with self.assertRaises(launcher.RuntimeConfigurationError) as raised:
            launcher.prepare_launch(
                "market-lan",
                repository=self.repository,
                home=self.account_home,
                environment_file=self.environment_file,
                temporary_directory=self.temporary,
                ca_bundle=self.ca_bundle,
            )
        public_text = str(raised.exception)
        self.assertNotIn(SYNTHETIC_GATEWAY_SECRET, public_text)
        self.assertNotIn(SYNTHETIC_ANTHROPIC_SECRET, public_text)

    def test_execve_replaces_launcher_once_with_exact_cwd_argv_and_environment(
        self,
    ) -> None:
        launcher = launcher_module()
        support = support_module()

        class ExecObserved(Exception):
            pass

        observed = []

        def observe_execve(executable, arguments, environment):
            observed.append(
                (executable, tuple(arguments), dict(environment), Path.cwd())
            )
            raise ExecObserved

        runner = dataclasses.replace(
            support.DEFAULT_PROCESS_RUNNER,
            execve=observe_execve,
        )
        original_cwd = Path.cwd()
        try:
            with self.assertRaises(ExecObserved):
                launcher.launch_component(
                    "metro",
                    repository=self.repository,
                    home=self.account_home,
                    environment_file=None,
                    temporary_directory=self.temporary,
                    ca_bundle=None,
                    process_runner=runner,
                )
        finally:
            os.chdir(original_cwd)

        self.assertEqual(len(observed), 1)
        executable, arguments, environment, cwd = observed[0]
        self.assertEqual(executable, NODE_22)
        self.assertEqual(executable, arguments[0])
        self.assertEqual(cwd, self.repository / "apps/mobile")
        self.assertEqual(environment["EXPO_PUBLIC_INITIAL_DEMO_MODE"], "false")
        self.assertNotIn("MOOMOO_GATEWAY_TOKEN", environment)
        self.assertNotIn("ANTHROPIC_API_KEY", environment)

    def test_direct_script_errors_are_sanitized(self) -> None:
        script = self.repository / "scripts/local_runtime_launch.py"
        marker = "sensitive-marker-must-not-appear"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "unknown-component",
                "--repository",
                marker,
                "--home",
                marker,
                "--temporary-directory",
                marker,
            ],
            cwd=self.root,
            env={"PATH": "/usr/bin:/bin"},
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "runtime launch failed\n")
        self.assertNotIn(marker, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
