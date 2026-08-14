from __future__ import annotations

import hashlib
import importlib
import os
import plistlib
import subprocess
import signal
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


EXPECTED = (
    ("market-loopback", "com.franz.us-stock-helper.market-loopback", 8765),
    ("market-lan", "com.franz.us-stock-helper.market-lan", 8766),
    ("analysis-api", "com.franz.us-stock-helper.analysis-api", 8770),
    ("metro", "com.franz.us-stock-helper.metro", 8088),
)


def runtime_module():
    try:
        return importlib.import_module("scripts.local_runtime")
    except ModuleNotFoundError as error:
        if error.name != "scripts.local_runtime":
            raise
        raise AssertionError("scripts.local_runtime is not implemented") from error


class OwnershipTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = runtime_module()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name).resolve()
        self.paths = self.runtime.RuntimePaths.for_testing(
            repository=Path(__file__).resolve().parents[2],
            home=root / "home",
            ca_bundle=root / "cacert.pem",
        )

    def identity(self, component: str, *, pid: int = 2101):
        specification = self.runtime.COMPONENTS[component]
        command = specification.expected_process_command(self.paths)
        return self.runtime.ProcessIdentity(
            pid=pid,
            start_time="2026-08-14T03:00:00Z",
            executable=command[0],
            cwd=str(specification.expected_cwd(self.paths)),
            command_fingerprint=hashlib.sha256(
                " ".join(command).encode("utf-8")
            ).hexdigest(),
        )

    def test_fixed_components_use_exact_labels_ports_and_expected_commands(
        self,
    ) -> None:
        self.assertEqual(
            tuple(
                (name, specification.label, specification.port)
                for name, specification in self.runtime.COMPONENTS.items()
            ),
            EXPECTED,
        )
        self.assertEqual(self.runtime.LEGACY_PORTS, (8081, 8083))
        self.assertEqual(
            self.runtime.COMPONENTS["metro"].expected_process_command(self.paths)[-4:],
            ("--dev-client", "--lan", "--port", "8088"),
        )

    def test_listener_is_owned_only_by_exact_launchd_pid_and_full_fingerprint(
        self,
    ) -> None:
        component = "market-loopback"
        identity = self.identity(component)
        specification = self.runtime.COMPONENTS[component]
        command = specification.expected_command(self.paths)
        state = self.runtime.LaunchctlState(
            loaded=True,
            pid=identity.pid,
            plist_path=str(self.paths.plists[component]),
            program=command[0],
            arguments=command,
        )

        owned = self.runtime.classify_listener_ownership(
            self.runtime.COMPONENTS[component],
            self.paths,
            state=state,
            listener_pids=(identity.pid,),
            process_identity=identity,
        )
        self.assertEqual(owned, "owned")
        self.assertNotEqual(
            specification.expected_command(self.paths)[0],
            specification.expected_process_command(self.paths)[0],
            "Python's macOS process executable must not be confused with plist argv0",
        )
        self.assertEqual(
            identity.command_fingerprint,
            hashlib.sha256(
                " ".join(specification.expected_process_command(self.paths)).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "process fingerprints must match the exact ps command representation",
        )

        mutations = (
            self.runtime.LaunchctlState(
                loaded=True,
                pid=identity.pid + 1,
                plist_path=state.plist_path,
                program=state.program,
                arguments=state.arguments,
            ),
            self.runtime.ProcessIdentity(
                pid=identity.pid,
                start_time=identity.start_time,
                executable="/tmp/not-the-runtime",
                cwd=identity.cwd,
                command_fingerprint=identity.command_fingerprint,
            ),
            self.runtime.ProcessIdentity(
                pid=identity.pid,
                start_time=identity.start_time,
                executable=identity.executable,
                cwd="/tmp/wrong-worktree",
                command_fingerprint=identity.command_fingerprint,
            ),
            self.runtime.ProcessIdentity(
                pid=identity.pid,
                start_time=identity.start_time,
                executable=identity.executable,
                cwd=identity.cwd,
                command_fingerprint="0" * 64,
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                if isinstance(mutation, self.runtime.LaunchctlState):
                    candidate_state = mutation
                    candidate_identity = identity
                else:
                    candidate_state = state
                    candidate_identity = mutation
                self.assertEqual(
                    self.runtime.classify_listener_ownership(
                        self.runtime.COMPONENTS[component],
                        self.paths,
                        state=candidate_state,
                        listener_pids=(identity.pid,),
                        process_identity=candidate_identity,
                    ),
                    "unknown",
                )

    def test_multiple_or_unloaded_target_listeners_are_never_owned(self) -> None:
        component = self.runtime.COMPONENTS["market-lan"]
        identity = self.identity("market-lan", pid=2301)
        cases = (
            (self.runtime.LaunchctlState(False, None), (identity.pid,)),
            (
                self.runtime.LaunchctlState(
                    True,
                    identity.pid,
                    str(self.paths.plists["market-lan"]),
                    identity.executable,
                    component.expected_command(self.paths),
                ),
                (identity.pid, 2302),
            ),
            (self.runtime.LaunchctlState(True, None), (identity.pid,)),
        )
        for state, listeners in cases:
            with self.subTest(state=state, listeners=listeners):
                self.assertEqual(
                    self.runtime.classify_listener_ownership(
                        component,
                        self.paths,
                        state=state,
                        listener_pids=listeners,
                        process_identity=identity,
                    ),
                    "unknown",
                )

    def test_parsers_fail_closed_on_malformed_tool_output(self) -> None:
        parsers_and_values = (
            (self.runtime.parse_launchctl_print, "pid = secret\npid = 22\n"),
            (self.runtime.parse_launchctl_print, "state = running\n"),
            (self.runtime.parse_lsof_pids, "p123\ncpython\n"),
            (self.runtime.parse_lsof_pids, "p0\n"),
            (self.runtime.parse_process_line, "not-enough-fields"),
        )
        for parser, value in parsers_and_values:
            with self.subTest(parser=parser.__name__):
                with self.assertRaises(self.runtime.RuntimeLifecycleError):
                    parser(value)

    def test_parsers_accept_the_narrow_macos_launchctl_and_lsof_fixtures(self) -> None:
        specification = self.runtime.COMPONENTS["market-loopback"]
        arguments = specification.expected_command(self.paths)
        launchctl_fixture = "\n".join(
            (
                f"gui/501/{specification.label} = {{",
                f"\tpath = {self.paths.plists['market-loopback']}",
                "\tstate = running",
                f"\tprogram = {arguments[0]}",
                "\targuments = {",
                *(f"\t\t{argument}" for argument in arguments),
                "\t}",
                "\tpid = 27049",
                "}",
            )
        )
        state = self.runtime.parse_launchctl_print(
            launchctl_fixture,
            expected_domain=f"gui/501/{specification.label}",
        )
        self.assertEqual(state.pid, 27049)
        self.assertEqual(state.arguments, arguments)
        without_pid = launchctl_fixture.replace(
            "\tstate = running", "\tstate = spawn scheduled"
        ).replace("\n\tpid = 27049", "")
        waiting = self.runtime.parse_launchctl_print(
            without_pid,
            expected_domain=f"gui/501/{specification.label}",
        )
        self.assertTrue(waiting.loaded)
        self.assertIsNone(waiting.pid)
        lsof_fixture = (
            b"p27049\x00\nf3\x00n127.0.0.1:8765\x00TST=LISTEN\x00"
            b"TQR=0\x00TQS=0\x00\n"
        )
        self.assertEqual(
            self.runtime.parse_lsof_pids(lsof_fixture, expected_port=8765),
            (27049,),
        )
        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.runtime.parse_lsof_pids(lsof_fixture, expected_port=8770)

    def test_ownership_metadata_contains_no_command_or_environment_values(self) -> None:
        identity = self.identity("analysis-api", pid=2401)
        payload = self.runtime.render_ownership_metadata(
            {"analysis-api": identity}, self.paths
        )
        document = plistlib.loads(plistlib.dumps({"payload": payload.decode("utf-8")}))
        rendered = document["payload"]
        self.assertIn(identity.command_fingerprint, rendered)
        self.assertNotIn("ProgramArguments", rendered)
        self.assertNotIn("MOOMOO_GATEWAY_TOKEN", rendered)
        self.assertNotIn("ANTHROPIC_API_KEY", rendered)
        self.assertNotIn("Authorization", rendered)

    def test_trusted_parent_writer_keeps_launchagents_parent_nonprivate(self) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.home / "Library" / "LaunchAgents"
        parent.mkdir(parents=True, mode=0o755)
        parent.chmod(0o755)
        target = parent / "com.franz.us-stock-helper.metro.plist"
        payload = b"private-plist"

        support.atomic_write_trusted_file(
            target,
            payload,
            expected_existing_digest=None,
        )

        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(parent.stat().st_mode & 0o777, 0o755)

        with self.assertRaises(support.RuntimeConfigurationError):
            support.atomic_write_trusted_file(
                target,
                b"replacement",
                expected_existing_digest="0" * 64,
            )
        self.assertEqual(target.read_bytes(), payload)

    def test_trusted_writer_never_overwrites_a_target_replaced_at_publish_time(
        self,
    ) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "owned-race.plist"
        old_payload = b"expected-old"
        foreign_payload = b"foreign-must-survive"
        target.write_bytes(old_payload)
        target.chmod(0o600)
        foreign = parent / "foreign-candidate"
        foreign.write_bytes(foreign_payload)
        foreign.chmod(0o600)
        raced = False
        real_replace = support.DEFAULT_FILE_SYSTEM.replace
        real_rename_exclusive = support.DEFAULT_FILE_SYSTEM.rename_exclusive

        def inject_before_replace(*args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                os.replace(foreign, target)
            return real_replace(*args, **kwargs)

        def inject_before_exclusive(
            source_directory, source, destination_directory, destination
        ):
            nonlocal raced
            if not raced and source == target.name:
                raced = True
                os.replace(foreign, target)
            return real_rename_exclusive(
                source_directory,
                source,
                destination_directory,
                destination,
            )

        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            replace=inject_before_replace,
            rename_exclusive=inject_before_exclusive,
        )

        with self.assertRaises(support.RuntimeConfigurationError):
            support.atomic_write_trusted_file(
                target,
                b"new-managed-payload",
                expected_existing_digest=hashlib.sha256(old_payload).hexdigest(),
                filesystem=filesystem,
            )

        self.assertEqual(target.read_bytes(), foreign_payload)

    def test_trusted_writer_exclusive_publish_preserves_a_new_target(self) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "absent-race.plist"
        foreign_payload = b"new-foreign-target"
        raced = False
        real_replace = support.DEFAULT_FILE_SYSTEM.replace
        real_rename_exclusive = support.DEFAULT_FILE_SYSTEM.rename_exclusive

        def inject_before_replace(*args, **kwargs):
            nonlocal raced
            if not raced:
                raced = True
                target.write_bytes(foreign_payload)
                target.chmod(0o600)
            return real_replace(*args, **kwargs)

        def inject_before_exclusive(
            source_directory, source, destination_directory, destination
        ):
            nonlocal raced
            if not raced and destination == target.name:
                raced = True
                target.write_bytes(foreign_payload)
                target.chmod(0o600)
            return real_rename_exclusive(
                source_directory,
                source,
                destination_directory,
                destination,
            )

        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            replace=inject_before_replace,
            rename_exclusive=inject_before_exclusive,
        )

        with self.assertRaises(support.RuntimeConfigurationError):
            support.atomic_write_trusted_file(
                target,
                b"new-managed-payload",
                expected_existing_digest=None,
                filesystem=filesystem,
            )

        self.assertEqual(target.read_bytes(), foreign_payload)

    def test_successful_trusted_replacements_leave_nonplist_bounded_tombstones(
        self,
    ) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "repeatable.plist"
        old_payload = b"managed-v1"
        target.write_bytes(old_payload)
        target.chmod(0o600)

        support.atomic_write_trusted_file(
            target,
            b"managed-v2",
            expected_existing_digest=hashlib.sha256(old_payload).hexdigest(),
        )
        support.atomic_write_trusted_file(
            target,
            b"managed-v3",
            expected_existing_digest=hashlib.sha256(b"managed-v2").hexdigest(),
        )

        tombstones = [
            path for path in parent.iterdir() if path.name.endswith(".tombstone")
        ]
        self.assertEqual(target.read_bytes(), b"managed-v3")
        self.assertEqual(len(tombstones), 2)
        self.assertTrue(all(not path.name.endswith(".plist") for path in tombstones))
        self.assertIn(old_payload, {path.read_bytes() for path in tombstones})

    def test_trusted_writer_fails_closed_at_per_target_artifact_cap(self) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "capped.plist"
        prefix = support._tombstone_prefix(target.name)
        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            listdir=lambda _descriptor: [
                f"{prefix}{index}.tombstone"
                for index in range(support._MAX_TRUSTED_ARTIFACTS_PER_TARGET)
            ],
        )

        with self.assertRaisesRegex(
            support.RuntimeConfigurationError,
            "quarantine is full",
        ):
            support.atomic_write_trusted_file(
                target,
                b"must-not-publish",
                expected_existing_digest=None,
                filesystem=filesystem,
            )

        self.assertFalse(target.exists())

    def test_trusted_writer_restores_capture_when_interrupted_before_publish(
        self,
    ) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "interrupt-write.plist"
        old_payload = b"managed-before-interrupt"
        target.write_bytes(old_payload)
        target.chmod(0o600)
        real_rename_exclusive = support.DEFAULT_FILE_SYSTEM.rename_exclusive
        interrupted = False

        def interrupt_after_capture(
            source_directory, source, destination_directory, destination
        ):
            nonlocal interrupted
            real_rename_exclusive(
                source_directory,
                source,
                destination_directory,
                destination,
            )
            if (
                source == target.name
                and destination.endswith(".tombstone")
                and not interrupted
            ):
                interrupted = True
                raise KeyboardInterrupt

        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            rename_exclusive=interrupt_after_capture,
        )

        with self.assertRaises(KeyboardInterrupt):
            support.atomic_write_trusted_file(
                target,
                b"managed-after-interrupt",
                expected_existing_digest=hashlib.sha256(old_payload).hexdigest(),
                filesystem=filesystem,
            )

        self.assertEqual(target.read_bytes(), old_payload)

    def test_trusted_remove_restores_capture_when_interrupted(self) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "interrupt-remove.plist"
        payload = b"managed-before-remove"
        target.write_bytes(payload)
        target.chmod(0o600)
        real_rename_exclusive = support.DEFAULT_FILE_SYSTEM.rename_exclusive
        interrupted = False

        def interrupt_after_capture(
            source_directory, source, destination_directory, destination
        ):
            nonlocal interrupted
            real_rename_exclusive(
                source_directory,
                source,
                destination_directory,
                destination,
            )
            if (
                source == target.name
                and destination.endswith(".tombstone")
                and not interrupted
            ):
                interrupted = True
                raise KeyboardInterrupt

        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            rename_exclusive=interrupt_after_capture,
        )

        with self.assertRaises(KeyboardInterrupt):
            support.quarantine_trusted_file(
                target,
                expected_existing_digest=hashlib.sha256(payload).hexdigest(),
                filesystem=filesystem,
            )

        self.assertEqual(target.read_bytes(), payload)

    def test_successful_trusted_remove_uses_nonplist_tombstone_and_can_reinstall(
        self,
    ) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "remove-then-install.plist"
        payload = b"managed-before-remove"
        target.write_bytes(payload)
        target.chmod(0o600)

        tombstone = support.quarantine_trusted_file(
            target,
            expected_existing_digest=hashlib.sha256(payload).hexdigest(),
        )

        self.assertFalse(target.exists())
        self.assertTrue(tombstone.name.endswith(".tombstone"))
        self.assertFalse(tombstone.name.endswith(".plist"))
        self.assertEqual(tombstone.read_bytes(), payload)

        support.atomic_write_trusted_file(
            target,
            b"managed-after-remove",
            expected_existing_digest=None,
        )
        self.assertEqual(target.read_bytes(), b"managed-after-remove")

    def test_trusted_remove_race_preserves_foreign_and_restore_conflict(self) -> None:
        support = importlib.import_module("scripts.local_runtime_support")
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "remove-race.plist"
        old_payload = b"expected-remove"
        foreign_payload = b"foreign-captured"
        competing_payload = b"foreign-at-canonical-path"
        target.write_bytes(old_payload)
        target.chmod(0o600)
        foreign = parent / "foreign-remove-candidate"
        foreign.write_bytes(foreign_payload)
        foreign.chmod(0o600)
        real_rename_exclusive = support.DEFAULT_FILE_SYSTEM.rename_exclusive
        captured = False

        def race_and_conflict(
            source_directory, source, destination_directory, destination
        ):
            nonlocal captured
            if source == target.name and not captured:
                captured = True
                os.replace(foreign, target)
                return real_rename_exclusive(
                    source_directory,
                    source,
                    destination_directory,
                    destination,
                )
            if source.endswith(".tombstone") and destination == target.name:
                target.write_bytes(competing_payload)
                target.chmod(0o600)
            return real_rename_exclusive(
                source_directory,
                source,
                destination_directory,
                destination,
            )

        filesystem = replace(
            support.DEFAULT_FILE_SYSTEM,
            rename_exclusive=race_and_conflict,
        )

        with self.assertRaises(support.RuntimeConfigurationError):
            support.quarantine_trusted_file(
                target,
                expected_existing_digest=hashlib.sha256(old_payload).hexdigest(),
                filesystem=filesystem,
            )

        self.assertEqual(target.read_bytes(), competing_payload)
        tombstones = [
            path for path in parent.iterdir() if path.name.endswith(".tombstone")
        ]
        self.assertTrue(all(not path.name.endswith(".plist") for path in tombstones))
        self.assertIn(foreign_payload, {path.read_bytes() for path in tombstones})

    def test_macos_remove_never_deletes_a_target_replaced_after_initial_read(
        self,
    ) -> None:
        parent = self.paths.launch_agents
        parent.mkdir(parents=True, mode=0o755)
        target = parent / "macos-remove-race.plist"
        old_payload = b"managed-before-race"
        foreign_payload = b"foreign-after-read"
        target.write_bytes(old_payload)
        target.chmod(0o600)
        foreign = parent / "macos-foreign-candidate"
        foreign.write_bytes(foreign_payload)
        foreign.chmod(0o600)
        system = self.runtime.MacOSSystem(self.paths)
        real_read = system.read_optional_private
        raced = False

        def read_then_replace(path: Path):
            nonlocal raced
            payload = real_read(path)
            if path == target and not raced:
                raced = True
                os.replace(foreign, target)
            return payload

        system.read_optional_private = read_then_replace

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            system.remove_exact_file(
                target,
                hashlib.sha256(old_payload).hexdigest(),
            )

        self.assertEqual(target.read_bytes(), foreign_payload)

    def test_launchctl_nonzero_is_unloaded_only_for_exact_not_found_contract(
        self,
    ) -> None:
        system = self.runtime.MacOSSystem(self.paths)
        label = self.runtime.COMPONENTS["metro"].label
        domain = f"gui/{__import__('os').geteuid()}/{label}"
        not_found = (
            "Bad request.\n"
            f'Could not find service "{label}" in domain for user gui: '
            f"{__import__('os').geteuid()}\n"
        )
        for returncode in (113, 5):
            with self.subTest(returncode=returncode):
                with mock.patch.object(
                    system,
                    "_run",
                    return_value=subprocess.CompletedProcess(
                        [], returncode, "", not_found
                    ),
                ):
                    self.assertEqual(
                        system.launchctl_state(label),
                        self.runtime.LaunchctlState(False, None),
                    )
        with mock.patch.object(
            system,
            "_run",
            return_value=subprocess.CompletedProcess([], 1, "", "permission denied"),
        ):
            with self.assertRaises(self.runtime.RuntimeLifecycleError):
                system.launchctl_state(label)

    def test_process_identity_requests_untruncated_ps_fields(self) -> None:
        system = self.runtime.MacOSSystem(self.paths)
        specification = self.runtime.COMPONENTS["market-loopback"]
        command = " ".join(specification.expected_process_command(self.paths))
        responses = iter(
            (
                subprocess.CompletedProcess([], 0, f"{command.split(' ')[0]}\n", ""),
                subprocess.CompletedProcess([], 0, "Thu Aug 14 03:00:00 2026\n", ""),
                subprocess.CompletedProcess([], 0, command + "\n", ""),
                subprocess.CompletedProcess(
                    [],
                    0,
                    f"p1234\x00\nn{self.paths.repository}\x00\n".encode(),
                    b"",
                ),
            )
        )
        commands = []

        def run(command, *, binary=False, timeout=None):
            del binary, timeout
            commands.append(tuple(command))
            return next(responses)

        with mock.patch.object(system, "_run", side_effect=run):
            identity = system.process_identity(1234)
        self.assertEqual(
            identity.executable, specification.expected_process_command(self.paths)[0]
        )
        ps_commands = [command for command in commands if command[0] == "/bin/ps"]
        self.assertIn("-ww", ps_commands[0])
        self.assertIn("-ww", ps_commands[2])

    def test_gateway_health_requires_moomoo_session_and_every_item_healthy(
        self,
    ) -> None:
        healthy = {
            "source": "moomoo",
            "session": "healthy",
            "items": [{"status": "healthy"}],
        }
        self.assertTrue(self.runtime.gateway_health_is_healthy(healthy))
        for mutation in (
            {**healthy, "source": "other"},
            {**healthy, "session": "degraded"},
            {**healthy, "items": []},
            {**healthy, "items": [{"status": "offline"}]},
            {**healthy, "items": "healthy"},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(self.runtime.gateway_health_is_healthy(mutation))

    def test_mutating_command_lock_is_nonblocking_and_process_exclusive(self) -> None:
        lock_target = self.paths.launch_agents
        lock_target.mkdir(parents=True, mode=0o755)
        other_worktree = self.runtime.RuntimePaths.for_testing(
            repository=self.paths.repository.parent / "another-worktree",
            home=self.paths.home,
            ca_bundle=self.paths.ca_bundle,
        )
        self.assertNotEqual(other_worktree.repository, self.paths.repository)
        self.assertEqual(other_worktree.launch_agents, lock_target)

        with self.runtime.runtime_command_lock(lock_target):
            with self.assertRaises(self.runtime.RuntimeLifecycleError):
                with self.runtime.runtime_command_lock(other_worktree.launch_agents):
                    self.fail("a concurrent mutation acquired the same lock")

        with self.runtime.runtime_command_lock(lock_target):
            pass

    def test_port_clear_wait_uses_one_total_wall_clock_deadline(self) -> None:
        system = self.runtime.MacOSSystem(self.paths)
        clock = [100.0]
        observed_timeouts: list[float | None] = []

        def listener_pids(port: int, *, timeout=None):
            del port
            observed_timeouts.append(timeout)
            clock[0] += min(4.9, timeout if timeout is not None else 4.9)
            return (9901,)

        system.listener_pids = listener_pids
        with mock.patch.object(
            self.runtime.time, "monotonic", side_effect=lambda: clock[0]
        ), mock.patch.object(
            self.runtime.time,
            "sleep",
            side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay),
        ):
            with self.assertRaises(self.runtime.RuntimeLifecycleError):
                system.wait_until_port_clear(8765)

        self.assertLessEqual(clock[0], 115.1)
        self.assertTrue(all(timeout is not None for timeout in observed_timeouts))
        self.assertEqual(observed_timeouts, sorted(observed_timeouts, reverse=True))

    def test_owned_wait_shares_deadline_across_all_process_probes(self) -> None:
        system = self.runtime.MacOSSystem(self.paths)
        specification = self.runtime.COMPONENTS["market-loopback"]
        command = specification.expected_command(self.paths)
        clock = [200.0]
        observed: list[float | None] = []

        def advance(timeout):
            observed.append(timeout)
            clock[0] += min(4.9, timeout if timeout is not None else 4.9)

        def launchctl_state(label: str, *, timeout=None):
            advance(timeout)
            return self.runtime.LaunchctlState(
                True,
                9902,
                str(self.paths.plists[specification.name]),
                command[0],
                command,
            )

        def listener_pids(port: int, *, timeout=None):
            del port
            advance(timeout)
            return (9902,)

        def process_identity(pid: int, *, deadline=None):
            del pid
            remaining = None if deadline is None else max(0.0, deadline - clock[0])
            advance(remaining)
            identity = self.identity(specification.name, pid=9902)
            return self.runtime.ProcessIdentity(
                identity.pid,
                identity.start_time,
                identity.executable,
                identity.cwd,
                "0" * 64,
            )

        system.launchctl_state = launchctl_state
        system.listener_pids = listener_pids
        system.process_identity = process_identity
        with mock.patch.object(
            self.runtime.time, "monotonic", side_effect=lambda: clock[0]
        ), mock.patch.object(
            self.runtime.time,
            "sleep",
            side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay),
        ):
            with self.assertRaises(self.runtime.RuntimeLifecycleError):
                system.wait_for_owned(specification, self.paths)

        self.assertLessEqual(clock[0], 230.1)
        self.assertTrue(all(timeout is not None for timeout in observed))

    def test_bootout_polling_has_one_total_wall_clock_deadline(self) -> None:
        system = self.runtime.MacOSSystem(self.paths)
        clock = [300.0]
        observed: list[float | None] = []

        def run(command, *, binary=False, timeout=None):
            del binary
            observed.append(timeout)
            clock[0] += min(4.9, timeout if timeout is not None else 4.9)
            return subprocess.CompletedProcess(command, 0, "", "")

        def launchctl_state(label: str, *, timeout=None):
            del label
            observed.append(timeout)
            clock[0] += min(4.9, timeout if timeout is not None else 4.9)
            return self.runtime.LaunchctlState(True, None)

        system._run = run
        system.launchctl_state = launchctl_state
        with mock.patch.object(
            self.runtime.time, "monotonic", side_effect=lambda: clock[0]
        ), mock.patch.object(
            self.runtime.time,
            "sleep",
            side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay),
        ):
            with self.assertRaises(self.runtime.RuntimeLifecycleError):
                system.bootout(self.runtime.COMPONENTS["market-loopback"].label)

        self.assertLessEqual(clock[0], 320.1)
        self.assertTrue(all(timeout is not None for timeout in observed))

    def test_http_probe_enforces_one_total_deadline_across_slow_drip_reads(
        self,
    ) -> None:
        clock = [0.0]

        class SlowDripTransport:
            def __init__(self):
                self.receives = 0

            def connect(self, host, port, timeout):
                self.host, self.port, self.timeout = host, port, timeout

            def send(self, payload, timeout):
                return len(payload)

            def receive(self, size, timeout):
                self.receives += 1
                clock[0] += 0.8
                return b"H"

            def close(self):
                pass

        transport = SlowDripTransport()
        observation = self.runtime.bounded_http_observation(
            self.runtime.COMPONENTS["market-loopback"],
            transport=transport,
            monotonic=lambda: clock[0],
        )
        self.assertEqual(observation.status, None)
        self.assertEqual(observation.error, "unreachable")
        self.assertLessEqual(transport.receives, 4)
        self.assertEqual(transport.host, "127.0.0.1")

    def test_transaction_signal_guard_ignores_repeat_signal_during_rollback(
        self,
    ) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        try:
            with self.runtime._transaction_signal_guard():
                handler = signal.getsignal(signal.SIGTERM)
                with self.assertRaises(KeyboardInterrupt):
                    handler(signal.SIGTERM, None)
                self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_IGN)
                self.assertIsNone(handler(signal.SIGTERM, None))
        finally:
            signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    unittest.main()
