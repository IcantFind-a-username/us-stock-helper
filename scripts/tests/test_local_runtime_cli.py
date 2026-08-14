from __future__ import annotations

import contextlib
import importlib
import io
import json
import plistlib
import subprocess
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path
from unittest import mock


SYNTHETIC_SECRET = "synthetic-secret-that-must-never-be-rendered"


def runtime_module():
    try:
        return importlib.import_module("scripts.local_runtime")
    except ModuleNotFoundError as error:
        if error.name != "scripts.local_runtime":
            raise
        raise AssertionError("scripts.local_runtime is not implemented") from error


def metro_deep_link_module():
    try:
        return importlib.import_module("scripts.metro_deep_link")
    except ModuleNotFoundError as error:
        if error.name != "scripts.metro_deep_link":
            raise
        raise AssertionError("scripts.metro_deep_link is not implemented") from error


class MetroDeepLinkTestCase(unittest.TestCase):
    ACTUAL_EXPO_JSON = (
        b'{"scheme":"exp+us-stock-helper","availableRuntimes":["custom"],'
        b'"runtime":"custom","url":"exp+us-stock-helper://'
        b'expo-development-client/?url=http%3A%2F%2F192.168.0.59%3A8088",'
        b'"appId":"com.franz.usstockhelper.dev"}'
    )

    def payload_with(self, **replacements) -> bytes:
        document = json.loads(self.ACTUAL_EXPO_JSON)
        document.update(replacements)
        return json.dumps(document, separators=(",", ":")).encode("utf-8")

    def test_fetch_rechecks_the_shared_deadline_for_slow_drip_headers(self) -> None:
        module = metro_deep_link_module()
        clock = [0.0]

        class SlowHeaderTransport:
            def __init__(self):
                self.timeouts = []
                self.closed = False

            def advance(self, timeout, delay):
                self.timeouts.append(timeout)
                clock[0] += min(timeout, delay)
                if timeout < delay:
                    raise TimeoutError

            def connect(self, host, port, timeout):
                self.host, self.port = host, port
                self.advance(timeout, 0.4)

            def send(self, payload, timeout):
                self.request = payload
                self.advance(timeout, 0.4)
                return len(payload)

            def receive(self, size, timeout):
                del size
                self.advance(timeout, 0.8)
                return b"H"

            def close(self):
                self.closed = True

        transport = SlowHeaderTransport()
        with self.assertRaises(TimeoutError):
            module.fetch_launcher_payload(
                transport=transport,
                monotonic=lambda: clock[0],
            )

        self.assertLessEqual(clock[0], 3.0)
        self.assertEqual((transport.host, transport.port), ("127.0.0.1", 8088))
        self.assertIn(
            b"GET /_expo/open?platform=ios&runtime=custom HTTP/1.1\r\n",
            transport.request,
        )
        self.assertTrue(transport.closed)
        self.assertGreater(len(transport.timeouts), 3)
        self.assertTrue(
            all(
                later < earlier
                for earlier, later in zip(
                    transport.timeouts,
                    transport.timeouts[1:],
                )
            )
        )

    def test_fetch_shares_one_deadline_across_connect_headers_and_body(self) -> None:
        module = metro_deep_link_module()
        clock = [10.0]
        header = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: 3\r\n\r\n{"
        )

        class SlowBodyTransport:
            def __init__(self):
                self.responses = [header, b"x", b"}"]
                self.timeouts = []
                self.closed = False

            def advance(self, timeout, delay):
                self.timeouts.append(timeout)
                clock[0] += min(timeout, delay)
                if timeout < delay:
                    raise TimeoutError

            def connect(self, host, port, timeout):
                self.host, self.port = host, port
                self.advance(timeout, 0.5)

            def send(self, payload, timeout):
                self.advance(timeout, 0.5)
                return len(payload)

            def receive(self, size, timeout):
                del size
                delay = 0.8 if len(self.responses) == 3 else 0.7
                self.advance(timeout, delay)
                return self.responses.pop(0)

            def close(self):
                self.closed = True

        transport = SlowBodyTransport()
        with self.assertRaises(TimeoutError):
            module.fetch_launcher_payload(
                transport=transport,
                monotonic=lambda: clock[0],
            )

        self.assertLessEqual(clock[0], 13.0)
        self.assertTrue(transport.closed)
        self.assertEqual(len(transport.responses), 1)
        self.assertGreater(transport.timeouts[0], transport.timeouts[-1])

    def test_extracts_only_the_url_from_the_actual_expo_8088_response(self) -> None:
        module = metro_deep_link_module()
        stdout = io.StringIO()
        stderr = io.StringIO()

        self.assertEqual(
            module.extract_launcher_url(self.ACTUAL_EXPO_JSON),
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088",
        )
        self.assertEqual(
            module.main(
                fetcher=lambda: self.ACTUAL_EXPO_JSON,
                stdout=stdout,
                stderr=stderr,
            ),
            0,
        )
        self.assertEqual(
            stdout.getvalue(),
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_rejects_a_launcher_url_outside_the_fixed_debug_contract(self) -> None:
        module = metro_deep_link_module()
        invalid_urls = (
            "EXP+US-STOCK-HELPER://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088",
            "usstockhelper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088",
            "exp+us-stock-helper://not-the-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088",
            "exp+us-stock-helper://expo-development-client/route"
            "?url=http%3A%2F%2F192.168.0.59%3A8088",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8081",
            "exp+us-stock-helper://expo-development-client/"
            "?url=https%3A%2F%2F192.168.0.59%3A8088",
            "exp+us-stock-helper://expo-development-client/"
            "?url=HTTP%3A%2F%2F192.168.0.59%3A8088",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2Fuser%40example.test%40192.168.0.59%3A8088",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088%2Fbundle",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088%3Ftoken%3Dsecret",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F8.8.8.8%3A8088",
            "exp+us-stock-helper://expo-development-client/"
            "?url=http%3A%2F%2F192.168.0.59%3A8088&extra=1",
        )

        for candidate in invalid_urls:
            with self.subTest(candidate=candidate), self.assertRaises(
                module.MetroDeepLinkError
            ):
                module.extract_launcher_url(self.payload_with(url=candidate))

    def test_rejects_inconsistent_expo_runtime_metadata(self) -> None:
        module = metro_deep_link_module()
        invalid_metadata = (
            {"scheme": "usstockhelper"},
            {"availableRuntimes": ["custom", "expo"]},
            {"availableRuntimes": []},
            {"runtime": "expo"},
            {"appId": "com.example.other"},
            {"unexpected": "field"},
        )

        for replacements in invalid_metadata:
            with self.subTest(replacements=replacements), self.assertRaises(
                module.MetroDeepLinkError
            ):
                module.extract_launcher_url(self.payload_with(**replacements))

    def test_cli_failure_is_fixed_and_does_not_render_the_response(self) -> None:
        module = metro_deep_link_module()
        fetchers = (
            lambda: b'{"url":"' + SYNTHETIC_SECRET.encode() + b'"}',
            lambda: (_ for _ in ()).throw(RuntimeError(SYNTHETIC_SECRET)),
        )

        for fetcher in fetchers:
            with self.subTest(fetcher=fetcher):
                stdout = io.StringIO()
                stderr = io.StringIO()
                code = module.main(
                    fetcher=fetcher,
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(
                    stderr.getvalue(), "managed Metro launcher URL unavailable\n"
                )
                self.assertNotIn(SYNTHETIC_SECRET, stderr.getvalue())


class FakeSystem:
    def __init__(self, runtime, paths) -> None:
        self.runtime = runtime
        self.paths = paths
        self.events: list[tuple] = []
        self.listeners: dict[int, tuple[int, ...]] = {}
        self.launchd = {
            spec.label: runtime.LaunchctlState(False, None)
            for spec in runtime.COMPONENTS.values()
        }
        self.identities = {}
        self.files: dict[Path, bytes] = {}
        self.http = {
            8765: runtime.HttpObservation(200, None, True),
            8766: runtime.HttpObservation(401, None),
            8770: runtime.HttpObservation(403, None),
            8088: runtime.HttpObservation(200, None),
        }
        self.bootstrap_failure: str | None = None
        self.preflight_failure = False
        self.target_failure: Path | None = None
        self.next_pid = 3000
        self.wait_failure: str | None = None
        self.bootout_failure: str | None = None
        self.wait_clear_failure: int | None = None
        self.remove_after_failure: str | None = None
        self.install_after_payload: bytes | None = None
        self.manifest_postcommit_failures: set[str] = set()

    def preflight_read_only(self, paths) -> None:
        self.events.append(("preflight",))
        if self.preflight_failure:
            raise self.runtime.RuntimeLifecycleError("unsafe_path")

    def preflight_management(self, paths) -> None:
        self.events.append(("preflight-management",))
        if self.preflight_failure:
            raise self.runtime.RuntimeLifecycleError("unsafe_path")

    def validate_installed_target(self, path: Path) -> None:
        self.events.append(("validate-target", path.name))
        if path == self.target_failure:
            raise self.runtime.RuntimeLifecycleError("unsafe_path")

    def prepare_private_paths(self, paths) -> None:
        self.events.append(("prepare-private",))

    def prepare_management_metadata(self, paths) -> None:
        self.events.append(("prepare-management",))

    def validate_component_launches(self, paths) -> None:
        self.events.append(("validate-launches",))

    def render_plist(self, component, paths) -> bytes:
        spec = self.runtime.COMPONENTS[component]
        self.events.append(("render", component))
        return plistlib.dumps(
            {
                "Label": spec.label,
                "ProgramArguments": list(spec.expected_command(paths)),
                "WorkingDirectory": str(spec.expected_cwd(paths)),
            }
        )

    def write_private(self, path: Path, payload: bytes) -> None:
        kind = "stage-write" if path.parent == self.paths.staging else "private-write"
        self.events.append((kind, path.name))
        self.files[path] = payload
        if path == self.paths.ownership_metadata:
            state = json.loads(payload.decode("utf-8"))["state"]
            if state in self.manifest_postcommit_failures:
                self.manifest_postcommit_failures.remove(state)
                raise self.runtime.RuntimeLifecycleError("command_failed")

    def confirm_private_write(self, path: Path, payload: bytes) -> None:
        self.events.append(("confirm-private-write", path.name))
        if self.files.get(path) != payload:
            raise self.runtime.RuntimeLifecycleError("ownership_manifest_mismatch")

    def confirm_trusted_write(self, path: Path, payload: bytes) -> None:
        self.events.append(("confirm-trusted-write", path.name))
        if self.files.get(path) != payload:
            raise self.runtime.RuntimeLifecycleError("ownership_manifest_mismatch")

    def confirm_file_absence(self, path: Path) -> None:
        self.events.append(("confirm-file-absence", path.name))
        if path in self.files:
            raise self.runtime.RuntimeLifecycleError("ownership_manifest_mismatch")

    def install_plist(
        self, path: Path, payload: bytes, expected_digest: str | None
    ) -> None:
        self.events.append(("install-plist", path.name))
        current = self.files.get(path)
        current_digest = (
            self.runtime.hashlib.sha256(current).hexdigest()
            if current is not None
            else None
        )
        if current_digest != expected_digest:
            raise self.runtime.RuntimeLifecycleError("ownership_manifest_mismatch")
        self.files[path] = payload
        if payload == self.install_after_payload:
            self.install_after_payload = None
            raise self.runtime.RuntimeLifecycleError("command_failed")

    def validate_staged_plist(self, path: Path, label: str) -> None:
        self.events.append(("validate-stage", path.name))
        document = plistlib.loads(self.files[path])
        if document["Label"] != label:
            raise self.runtime.RuntimeLifecycleError("invalid_plist")

    def read_optional_private(self, path: Path) -> bytes | None:
        self.events.append(("read", path.name))
        return self.files.get(path)

    def remove_exact_file(self, path: Path, expected_digest: str | None = None) -> None:
        self.events.append(("remove", path.name))
        current = self.files.get(path)
        if expected_digest is not None and (
            current is None
            or self.runtime.hashlib.sha256(current).hexdigest() != expected_digest
        ):
            raise self.runtime.RuntimeLifecycleError("ownership_manifest_mismatch")
        self.files.pop(path, None)
        if self.remove_after_failure == path.name:
            self.remove_after_failure = None
            raise self.runtime.RuntimeLifecycleError("command_failed")

    def launchctl_state(self, label: str):
        self.events.append(("launchctl-state", label))
        return self.launchd[label]

    def listener_pids(self, port: int):
        self.events.append(("listeners", port))
        return self.listeners.get(port, ())

    def wait_until_port_clear(self, port: int) -> None:
        self.events.append(("wait-clear", port))
        if self.wait_clear_failure == port:
            self.wait_clear_failure = None
            raise self.runtime.RuntimeLifecycleError("unknown_target_listener")
        if self.listeners.get(port):
            raise self.runtime.RuntimeLifecycleError("unknown_target_listener")

    def process_identity(self, pid: int):
        self.events.append(("identity", pid))
        return self.identities.get(pid)

    def wait_for_owned(self, specification, paths):
        self.events.append(("wait-owned", specification.name))
        if self.wait_failure == specification.name:
            raise self.runtime.RuntimeLifecycleError("bootstrap_failed")
        state = self.launchd[specification.label]
        identity = self.identities.get(state.pid)
        if (
            self.runtime.classify_listener_ownership(
                specification,
                paths,
                state=state,
                listener_pids=self.listeners.get(specification.port, ()),
                process_identity=identity,
            )
            != "owned"
        ):
            raise self.runtime.RuntimeLifecycleError("bootstrap_failed")
        return identity

    def bootstrap(self, label: str, path: Path) -> None:
        self.events.append(("bootstrap", label))
        if label == self.bootstrap_failure:
            raise self.runtime.RuntimeLifecycleError("bootstrap_failed")
        self.next_pid += 1
        component = next(
            name
            for name, specification in self.runtime.COMPONENTS.items()
            if specification.label == label
        )
        command = self.runtime.COMPONENTS[component].expected_command(self.paths)
        self.launchd[label] = self.runtime.LaunchctlState(
            True,
            self.next_pid,
            str(path),
            command[0],
            command,
        )
        specification = self.runtime.COMPONENTS[component]
        identity = self.runtime.expected_process_identity(
            specification,
            self.paths,
            pid=self.next_pid,
            start_time="2026-08-14T03:00:00Z",
        )
        self.listeners[specification.port] = (self.next_pid,)
        self.identities[self.next_pid] = identity

    def bootout(self, label: str) -> None:
        self.events.append(("bootout", label))
        if self.bootout_failure == label:
            raise self.runtime.RuntimeLifecycleError("command_failed")
        component = next(
            name
            for name, specification in self.runtime.COMPONENTS.items()
            if specification.label == label
        )
        self.listeners.pop(self.runtime.COMPONENTS[component].port, None)
        self.launchd[label] = self.runtime.LaunchctlState(False, None)

    def http_observation(self, specification):
        self.events.append(("http", specification.port))
        return self.http[specification.port]


class RuntimeCliTestCase(unittest.TestCase):
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
        self.system = FakeSystem(self.runtime, self.paths)
        self.controller = self.runtime.RuntimeController(self.paths, self.system)

    def installed_paths(self):
        return tuple(self.paths.plists.values())

    def make_owned(self, component: str, pid: int) -> None:
        specification = self.runtime.COMPONENTS[component]
        identity = self.runtime.expected_process_identity(
            specification,
            self.paths,
            pid=pid,
            start_time="2026-08-14T03:00:00Z",
        )
        command = specification.expected_command(self.paths)
        self.system.launchd[specification.label] = self.runtime.LaunchctlState(
            True,
            pid,
            str(self.paths.plists[component]),
            command[0],
            command,
        )
        self.system.listeners[specification.port] = (pid,)
        self.system.identities[pid] = identity

    def make_inactive(self, component: str) -> None:
        specification = self.runtime.COMPONENTS[component]
        command = specification.expected_command(self.paths)
        self.system.launchd[specification.label] = self.runtime.LaunchctlState(
            True,
            None,
            str(self.paths.plists[component]),
            command[0],
            command,
        )

    def seed_manifest(self, *, state: str = "installed") -> None:
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state=state,
            installed={
                component: payload
                for component, path in self.paths.plists.items()
                if (payload := self.system.files.get(path)) is not None
            },
            identities={
                component: self.system.identities[launch.pid]
                for component, specification in self.runtime.COMPONENTS.items()
                if (launch := self.system.launchd[specification.label]).pid
                in self.system.identities
            },
        )

    def managed_plist(self, component: str, marker: str) -> bytes:
        document = plistlib.loads(self.system.render_plist(component, self.paths))
        document["TestMarker"] = marker
        return plistlib.dumps(document)

    def test_unknown_target_listener_aborts_with_zero_write_bootstrap_bootout_or_signal(
        self,
    ) -> None:
        self.system.listeners[8765] = (9999,)

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "unknown_target_listener"
        ):
            self.controller.install()

        forbidden = {
            "prepare-private",
            "stage-write",
            "private-write",
            "install-plist",
            "bootstrap",
            "bootout",
            "remove",
            "signal",
        }
        self.assertFalse(
            forbidden.intersection(event[0] for event in self.system.events)
        )

    def test_reinstall_checks_all_target_listeners_before_any_bootout(self) -> None:
        self.make_owned("market-loopback", 4101)
        self.system.listeners[8770] = (9998,)

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.reinstall()

        self.assertNotIn("bootout", [event[0] for event in self.system.events])
        self.assertNotIn("install-plist", [event[0] for event in self.system.events])

    def test_exact_manifest_owned_inactive_service_can_be_reinstalled(self) -> None:
        component = "market-loopback"
        self.make_inactive(component)
        self.system.files[self.paths.plists[component]] = b"inactive-owned-plist"
        self.seed_manifest()

        self.controller.reinstall()

        self.assertIn(
            ("bootout", self.runtime.COMPONENTS[component].label),
            self.system.events,
        )

    def test_exact_manifest_owned_inactive_service_can_be_uninstalled(self) -> None:
        component = "analysis-api"
        self.make_inactive(component)
        self.system.files[self.paths.plists[component]] = b"inactive-owned-plist"
        self.seed_manifest()

        self.controller.uninstall()

        self.assertIn(
            ("bootout", self.runtime.COMPONENTS[component].label),
            self.system.events,
        )
        self.assertNotIn(self.paths.plists[component], self.system.files)

    def test_legacy_listeners_are_reported_and_never_mutated(self) -> None:
        self.system.listeners[8081] = (5101,)
        self.system.listeners[8083] = (5103,)

        status = self.controller.status()

        self.assertEqual(
            status["legacy"],
            [
                {"port": 8081, "listening": True, "pids": [5101]},
                {"port": 8083, "listening": True, "pids": [5103]},
            ],
        )
        self.assertNotIn("bootout", [event[0] for event in self.system.events])
        self.assertNotIn("remove", [event[0] for event in self.system.events])

    def test_all_targets_and_staged_plists_validate_before_first_bootstrap(
        self,
    ) -> None:
        self.controller.install()

        kinds = [event[0] for event in self.system.events]
        first_stage_write = kinds.index("stage-write")
        first_bootstrap = kinds.index("bootstrap")
        target_indexes = [
            index
            for index, event in enumerate(self.system.events)
            if event[0] == "validate-target"
        ]
        stage_validation_indexes = [
            index
            for index, event in enumerate(self.system.events)
            if event[0] == "validate-stage"
        ]
        self.assertEqual(len(target_indexes), 8)
        self.assertTrue(all(index < first_stage_write for index in target_indexes[:4]))
        self.assertTrue(all(index < first_bootstrap for index in target_indexes))
        self.assertEqual(len(stage_validation_indexes), 4)
        self.assertTrue(
            all(index < first_bootstrap for index in stage_validation_indexes)
        )
        listener_scans = [
            event for event in self.system.events if event[0] == "listeners"
        ]
        self.assertGreaterEqual(len(listener_scans), 4 + 4)
        self.assertEqual(
            [event[1] for event in self.system.events if event[0] == "wait-owned"],
            list(self.runtime.COMPONENTS),
        )

    def test_unsafe_target_chain_causes_zero_plist_write_or_bootstrap(self) -> None:
        self.system.target_failure = self.installed_paths()[2]

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        kinds = {event[0] for event in self.system.events}
        self.assertNotIn("stage-write", kinds)
        self.assertNotIn("install-plist", kinds)
        self.assertNotIn("bootstrap", kinds)

    def test_partial_bootstrap_rolls_back_only_labels_loaded_by_attempt_and_restores_plists(
        self,
    ) -> None:
        labels = [spec.label for spec in self.runtime.COMPONENTS.values()]
        self.system.bootstrap_failure = labels[2]

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "bootstrap_failed"
        ):
            self.controller.install()

        bootouts = [event[1] for event in self.system.events if event[0] == "bootout"]
        self.assertEqual(bootouts, labels[:2][::-1])
        self.assertFalse(
            any(path in self.system.files for path in self.installed_paths())
        )
        self.assertNotIn(
            self.paths.environment_file,
            [event[1] for event in self.system.events if event[0] == "remove"],
        )
        self.assertNotIn(
            self.paths.device_database,
            [event[1] for event in self.system.events if event[0] == "remove"],
        )
        self.assertFalse(
            any(
                event[0] == "remove" and event[1].endswith(".log")
                for event in self.system.events
            )
        )

    def test_keyboard_interrupt_after_manifest_and_first_plist_rolls_back(self) -> None:
        real_install = self.system.install_plist
        interrupted = False

        def interrupt_after_first(path: Path, payload: bytes, expected_digest):
            nonlocal interrupted
            real_install(path, payload, expected_digest)
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt

        self.system.install_plist = interrupt_after_first
        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "bootstrap_failed"
        ):
            self.controller.install()

        self.assertFalse(
            any(path in self.system.files for path in self.installed_paths())
        )
        self.assertNotIn(self.paths.ownership_metadata, self.system.files)

    def test_install_rollback_post_unlink_failures_converge_and_can_retry(
        self,
    ) -> None:
        targets = (
            self.paths.plists["metro"].name,
            self.paths.ownership_metadata.name,
        )
        for target_name in targets:
            with self.subTest(target=target_name):
                system = FakeSystem(self.runtime, self.paths)
                controller = self.runtime.RuntimeController(self.paths, system)
                system.bootstrap_failure = self.runtime.COMPONENTS["metro"].label
                system.remove_after_failure = target_name

                with self.assertRaises(self.runtime.RuntimeLifecycleError):
                    controller.install()

                self.assertFalse(
                    any(path in system.files for path in self.installed_paths())
                )
                self.assertNotIn(self.paths.ownership_metadata, system.files)
                self.assertFalse(any(state.loaded for state in system.launchd.values()))

                system.bootstrap_failure = None
                controller.install()
                manifest = json.loads(
                    system.files[self.paths.ownership_metadata].decode("utf-8")
                )
                self.assertEqual(manifest["state"], "installed")

    def test_reinstall_rollback_confirms_old_plist_committed_before_write_error(
        self,
    ) -> None:
        old_payloads = {}
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 12000 + index)
            payload = self.managed_plist(component, f"rollback-{component}")
            old_payloads[component] = payload
            self.system.files[self.paths.plists[component]] = payload
        self.seed_manifest()
        failure_label = self.runtime.COMPONENTS["analysis-api"].label
        real_bootstrap = self.system.bootstrap
        failed_once = False

        def fail_new_once(label: str, path: Path) -> None:
            nonlocal failed_once
            if label == failure_label and not failed_once:
                failed_once = True
                raise self.runtime.RuntimeLifecycleError("bootstrap_failed")
            real_bootstrap(label, path)

        self.system.bootstrap = fail_new_once
        self.system.install_after_payload = old_payloads["metro"]

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "bootstrap_failed"
        ):
            self.controller.reinstall()

        for component, payload in old_payloads.items():
            self.assertEqual(self.system.files[self.paths.plists[component]], payload)
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installed")
        self.assertIn(
            ("confirm-trusted-write", self.paths.plists["metro"].name),
            self.system.events,
        )

    def test_interrupted_installing_manifest_rolls_forward_from_staged_plists(
        self,
    ) -> None:
        rendered = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in rendered.items():
            stage = self.paths.staging / f"{self.runtime.COMPONENTS[name].label}.plist"
            self.system.files[stage] = payload
        first = next(iter(self.runtime.COMPONENTS))
        self.system.files[self.paths.plists[first]] = rendered[first]
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installing",
            installed=rendered,
            identities={},
        )
        self.system.events.clear()

        self.controller.install()

        for name, path in self.paths.plists.items():
            self.assertEqual(self.system.files[path], rendered[name])
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installed")

    def test_install_commit_gate_rejects_a_foreign_listener_without_any_bootout(
        self,
    ) -> None:
        self.system.manifest_postcommit_failures.add("rollback_required")
        real_wait_for_owned = self.system.wait_for_owned

        def replace_early_listener_after_last_start(specification, paths):
            identity = real_wait_for_owned(specification, paths)
            if specification.name == "metro":
                self.system.listeners[
                    self.runtime.COMPONENTS["market-loopback"].port
                ] = (9981,)
            return identity

        self.system.wait_for_owned = replace_early_listener_after_last_start

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        self.assertNotIn("bootout", [event[0] for event in self.system.events])
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "rollback_required")
        self.assertIn(
            ("confirm-private-write", self.paths.ownership_metadata.name),
            self.system.events,
        )

    def test_manifest_postcommit_failures_converge_for_install_and_uninstall(
        self,
    ) -> None:
        self.system.manifest_postcommit_failures.update({"installing", "installed"})

        self.controller.install()

        installed_manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(installed_manifest["state"], "installed")
        self.system.manifest_postcommit_failures.update({"uninstalling", "uninstalled"})

        self.controller.uninstall()

        uninstalled_manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(uninstalled_manifest["state"], "uninstalled")
        self.assertFalse(
            any(path in self.system.files for path in self.installed_paths())
        )
        confirmed_states = [
            event for event in self.system.events if event[0] == "confirm-private-write"
        ]
        self.assertEqual(len(confirmed_states), 4)

    def test_recovery_install_commit_gate_rejects_an_early_component_crash(
        self,
    ) -> None:
        rendered = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in rendered.items():
            self.system.files[
                self.paths.staging / f"{self.runtime.COMPONENTS[name].label}.plist"
            ] = payload
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installing",
            installed=rendered,
            identities={},
        )
        real_wait_for_owned = self.system.wait_for_owned

        def crash_early_component_after_last_start(specification, paths):
            identity = real_wait_for_owned(specification, paths)
            if specification.name == "metro":
                early = self.runtime.COMPONENTS["market-loopback"]
                self.system.listeners.pop(early.port, None)
                self.system.launchd[early.label] = self.runtime.LaunchctlState(
                    False, None
                )
            return identity

        self.system.wait_for_owned = crash_early_component_after_last_start
        self.system.events.clear()

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installing")

    def test_interrupted_mixed_plists_with_loaded_label_fail_closed(self) -> None:
        rendered = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in rendered.items():
            self.system.files[
                self.paths.staging / f"{self.runtime.COMPONENTS[name].label}.plist"
            ] = payload
        first = next(iter(self.runtime.COMPONENTS))
        self.system.files[self.paths.plists[first]] = rendered[first]
        self.make_owned(first, 9601)
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installing",
            installed=rendered,
            identities={},
        )
        self.system.events.clear()

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        self.assertNotIn("bootout", [event[0] for event in self.system.events])
        self.assertNotIn("install-plist", [event[0] for event in self.system.events])

    def test_interrupted_recovery_wrong_process_identity_gets_zero_action(self) -> None:
        rendered = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in rendered.items():
            self.system.files[self.paths.plists[name]] = payload
            self.system.files[
                self.paths.staging / f"{self.runtime.COMPONENTS[name].label}.plist"
            ] = payload
        first = next(iter(self.runtime.COMPONENTS))
        self.make_owned(first, 9701)
        identity = self.system.identities[9701]
        self.system.identities[9701] = self.runtime.ProcessIdentity(
            identity.pid,
            identity.start_time,
            "/tmp/foreign-process",
            identity.cwd,
            identity.command_fingerprint,
        )
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installing",
            installed=rendered,
            identities={},
        )
        self.system.events.clear()

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        self.assertFalse(
            {"bootout", "install-plist", "bootstrap", "remove"}.intersection(
                event[0] for event in self.system.events
            )
        )

    def test_interrupted_uninstalling_manifest_rolls_forward_to_uninstalled(
        self,
    ) -> None:
        installed = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in installed.items():
            self.system.files[self.paths.plists[name]] = payload
        first = next(iter(self.runtime.COMPONENTS))
        self.system.files.pop(self.paths.plists[first])
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="uninstalling",
            installed=installed,
            identities={},
        )
        self.system.events.clear()

        self.controller.uninstall()

        self.assertFalse(
            any(path in self.system.files for path in self.installed_paths())
        )
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "uninstalled")

    def test_recovery_uninstall_commit_gate_preserves_in_progress_on_new_listener(
        self,
    ) -> None:
        installed = {
            name: self.system.render_plist(name, self.paths)
            for name in self.runtime.COMPONENTS
        }
        for name, payload in installed.items():
            self.system.files[self.paths.plists[name]] = payload
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="uninstalling",
            installed=installed,
            identities={},
        )
        last_path = tuple(self.paths.plists.values())[-1]
        real_remove = self.system.remove_exact_file

        def add_listener_after_last_remove(path: Path, expected_digest=None):
            real_remove(path, expected_digest)
            if path == last_path:
                self.system.listeners[
                    self.runtime.COMPONENTS["market-loopback"].port
                ] = (9982,)

        self.system.remove_exact_file = add_listener_after_last_remove
        self.system.events.clear()

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.uninstall()

        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "uninstalling")
        self.assertNotIn("bootout", [event[0] for event in self.system.events])

    def test_uninstall_manages_only_four_exact_labels_and_plists_and_preserves_private_data(
        self,
    ) -> None:
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 6000 + index)
        for path in self.installed_paths():
            self.system.files[path] = b"installed"
        preserved = (
            self.paths.environment_file,
            self.paths.device_database,
            self.paths.logs / "analysis-api.stdout.log",
        )
        for path in preserved:
            self.system.files[path] = SYNTHETIC_SECRET.encode()
        self.seed_manifest()

        self.controller.uninstall()

        exact_labels = [spec.label for spec in self.runtime.COMPONENTS.values()]
        self.assertEqual(
            [event[1] for event in self.system.events if event[0] == "bootout"],
            exact_labels[::-1],
        )
        self.assertEqual(
            {event[1] for event in self.system.events if event[0] == "remove"},
            {path.name for path in self.installed_paths()},
        )
        for path in preserved:
            self.assertIn(path, self.system.files)

    def test_uninstall_of_empty_runtime_is_idempotent_and_creates_nothing(self) -> None:
        self.controller.uninstall()

        self.assertEqual(self.system.files, {})
        self.assertFalse(
            {
                "prepare-private",
                "prepare-management",
                "private-write",
                "install-plist",
                "bootstrap",
                "bootout",
                "remove",
            }.intersection(event[0] for event in self.system.events)
        )

    def test_status_reports_each_component_independently_with_fixed_sanitized_fields(
        self,
    ) -> None:
        self.make_owned("market-loopback", 7001)
        payload = b"owned-loopback-plist"
        self.system.files[self.paths.plists["market-loopback"]] = payload
        self.seed_manifest()
        self.system.launchd[self.runtime.COMPONENTS["market-lan"].label] = (
            self.runtime.LaunchctlState(True, None)
        )
        self.system.listeners[8770] = (7999,)

        status = self.controller.status()

        rows = {row["component"]: row for row in status["components"]}
        self.assertEqual(rows["market-loopback"]["state"], "running")
        self.assertEqual(rows["market-lan"]["state"], "loaded_without_pid")
        self.assertEqual(rows["analysis-api"]["state"], "unknown_listener")
        self.assertEqual(rows["metro"]["state"], "stopped")
        rendered = json.dumps(status, sort_keys=True)
        self.assertNotIn(SYNTHETIC_SECRET, rendered)
        self.assertNotIn("command", rendered.lower())
        self.assertNotIn("environment", rendered.lower())
        self.assertNotIn("response", rendered.lower())

    def test_health_checks_are_bounded_independent_and_body_free(self) -> None:
        self.system.http[8766] = self.runtime.HttpObservation(500, "unexpected_status")
        self.system.http[8770] = self.runtime.HttpObservation(None, "unreachable")

        health = self.controller.health()

        rows = {row["component"]: row for row in health["components"]}
        self.assertTrue(rows["market-loopback"]["healthy"])
        self.assertTrue(rows["market-lan"]["reachable"])
        self.assertFalse(rows["market-lan"]["healthy"])
        self.assertEqual(rows["market-lan"]["http_status"], 500)
        self.assertEqual(rows["market-lan"]["error"], "unexpected_status")
        self.assertEqual(rows["analysis-api"]["error"], "unreachable")
        self.assertTrue(rows["metro"]["reachable"])
        self.assertIsNone(rows["metro"]["healthy"])
        self.assertEqual(
            [event[1] for event in self.system.events if event[0] == "http"],
            [8765, 8766, 8770, 8088],
        )
        rendered = json.dumps(health, sort_keys=True)
        self.assertNotIn("body", rendered.lower())
        self.assertNotIn(SYNTHETIC_SECRET, rendered)

    def test_unauthenticated_lan_endpoints_are_protected_not_healthy(self) -> None:
        health = self.controller.health()
        rows = {row["component"]: row for row in health["components"]}
        for component, expected_status in (("market-lan", 401), ("analysis-api", 403)):
            with self.subTest(component=component):
                self.assertTrue(rows[component]["reachable"])
                self.assertTrue(rows[component]["protected"])
                self.assertIsNone(rows[component]["healthy"])
                self.assertEqual(rows[component]["http_status"], expected_status)

    def test_existing_plist_without_matching_manifest_is_never_overwritten(
        self,
    ) -> None:
        path = self.installed_paths()[0]
        self.system.files[path] = b"unowned-existing-plist"

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "ownership_manifest_mismatch"
        ):
            self.controller.install()

        self.assertFalse(
            {
                "prepare-private",
                "stage-write",
                "install-plist",
                "bootstrap",
                "bootout",
            }.intersection(event[0] for event in self.system.events)
        )

    def test_manifest_digest_with_missing_installed_plist_blocks_all_mutation(
        self,
    ) -> None:
        path = self.paths.plists["market-loopback"]
        self.system.files[path] = b"owned-before-removal"
        self.seed_manifest()
        self.system.files.pop(path)

        for command in (self.controller.reinstall, self.controller.uninstall):
            self.system.events.clear()
            with self.subTest(command=command.__name__):
                with self.assertRaises(self.runtime.RuntimeLifecycleError):
                    command()
                self.assertFalse(
                    {
                        "prepare-private",
                        "install-plist",
                        "bootstrap",
                        "bootout",
                        "remove",
                    }.intersection(event[0] for event in self.system.events)
                )

    def test_listener_race_before_bootstrap_aborts_without_signalling_unknown_pid(
        self,
    ) -> None:
        real_listener_pids = self.system.listener_pids
        calls = {8765: 0}

        def racing_listener_pids(port: int):
            if port == 8765:
                calls[port] += 1
                if calls[port] >= 2:
                    self.system.events.append(("listeners", port))
                    return (9876,)
            return real_listener_pids(port)

        self.system.listener_pids = racing_listener_pids
        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "unknown_target_listener"
        ):
            self.controller.install()

        self.assertNotIn("bootstrap", [event[0] for event in self.system.events])
        self.assertNotIn("bootout", [event[0] for event in self.system.events])

    def test_plist_replacement_after_port_wait_is_never_bootstrapped(self) -> None:
        real_wait_until_port_clear = self.system.wait_until_port_clear
        replaced = False

        def replace_plist_after_wait(port: int) -> None:
            nonlocal replaced
            real_wait_until_port_clear(port)
            if port == 8765 and not replaced:
                replaced = True
                self.system.files[self.paths.plists["market-loopback"]] = (
                    b"foreign-plist"
                )

        self.system.wait_until_port_clear = replace_plist_after_wait

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.install()

        self.assertNotIn("bootstrap", [event[0] for event in self.system.events])

    def test_failed_reinstall_restores_and_rebootstraps_the_old_manifest(self) -> None:
        old_payloads = {}
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 8100 + index)
            path = self.paths.plists[component]
            payload = self.managed_plist(component, f"old-{component}")
            self.system.files[path] = payload
            old_payloads[path] = payload
        self.seed_manifest()
        failure_label = self.runtime.COMPONENTS["analysis-api"].label
        failed_once = False
        real_bootstrap = self.system.bootstrap

        def fail_new_once(label: str, path: Path) -> None:
            nonlocal failed_once
            if label == failure_label and not failed_once:
                failed_once = True
                raise self.runtime.RuntimeLifecycleError("bootstrap_failed")
            real_bootstrap(label, path)

        self.system.bootstrap = fail_new_once
        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "bootstrap_failed"
        ):
            self.controller.reinstall()

        for path, payload in old_payloads.items():
            self.assertEqual(self.system.files[path], payload)
        bootstraps = [
            event[1] for event in self.system.events if event[0] == "bootstrap"
        ]
        self.assertEqual(
            bootstraps[-4:],
            [spec.label for spec in self.runtime.COMPONENTS.values()],
        )

    def test_reinstall_old_bootout_failure_restarts_only_services_already_stopped(
        self,
    ) -> None:
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 9000 + index)
            self.system.files[self.paths.plists[component]] = self.managed_plist(
                component, f"old-{component}"
            )
        self.seed_manifest()
        self.system.bootout_failure = self.runtime.COMPONENTS["market-lan"].label

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.reinstall()

        bootstraps = [
            event[1] for event in self.system.events if event[0] == "bootstrap"
        ]
        self.assertEqual(
            bootstraps,
            [
                self.runtime.COMPONENTS["analysis-api"].label,
                self.runtime.COMPONENTS["metro"].label,
            ],
        )
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installed")

    def test_reinstall_wait_clear_failure_restores_the_just_stopped_service(
        self,
    ) -> None:
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 9100 + index)
            self.system.files[self.paths.plists[component]] = self.managed_plist(
                component, f"old-{component}"
            )
        self.seed_manifest()
        self.system.wait_clear_failure = self.runtime.COMPONENTS["metro"].port

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.reinstall()

        self.assertEqual(
            [event[1] for event in self.system.events if event[0] == "bootstrap"],
            [self.runtime.COMPONENTS["metro"].label],
        )

    def test_loaded_but_unowned_uncertain_bootstrap_result_gets_no_bootout(
        self,
    ) -> None:
        original_bootstrap = self.system.bootstrap

        def load_wrong_then_fail(label: str, path: Path) -> None:
            original_bootstrap(label, path)
            state = self.system.launchd[label]
            self.system.launchd[label] = self.runtime.LaunchctlState(
                True,
                state.pid,
                "/tmp/foreign.plist",
                state.program,
                state.arguments,
            )
            raise self.runtime.RuntimeLifecycleError("bootstrap_failed")

        self.system.bootstrap = load_wrong_then_fail
        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "rollback_failed"
        ):
            self.controller.install()
        self.assertNotIn("bootout", [event[0] for event in self.system.events])
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "rollback_required")

    def test_status_rejects_noninstalled_manifest_even_when_process_matches(
        self,
    ) -> None:
        self.make_owned("market-loopback", 9201)
        payload = b"installing-plist"
        self.system.files[self.paths.plists["market-loopback"]] = payload
        self.seed_manifest(state="installing")

        status = self.controller.status()

        row = status["components"][0]
        self.assertEqual(row["state"], "unverified_runtime")
        self.assertIsNone(row["pid"])

    def test_uninstall_bootout_failure_restores_stopped_components_before_any_remove(
        self,
    ) -> None:
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 9300 + index)
            self.system.files[self.paths.plists[component]] = self.managed_plist(
                component, f"installed-{component}"
            )
        self.seed_manifest()
        failure = self.runtime.COMPONENTS["market-lan"].label
        self.system.bootout_failure = failure

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "uninstall_failed"
        ):
            self.controller.uninstall()

        self.assertNotIn("remove", [event[0] for event in self.system.events])
        bootstraps = [
            event[1] for event in self.system.events if event[0] == "bootstrap"
        ]
        self.assertEqual(
            bootstraps[-2:],
            [
                self.runtime.COMPONENTS["analysis-api"].label,
                self.runtime.COMPONENTS["metro"].label,
            ],
        )
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installed")

    def test_failed_uninstall_restoration_marks_manual_rollback_required(self) -> None:
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            self.make_owned(component, 9400 + index)
            self.system.files[self.paths.plists[component]] = (
                f"installed-{component}".encode()
            )
        self.seed_manifest()
        self.system.bootout_failure = self.runtime.COMPONENTS["market-lan"].label
        self.system.wait_failure = "analysis-api"

        with self.assertRaises(self.runtime.RuntimeLifecycleError):
            self.controller.uninstall()

        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "rollback_required")

    def test_uninstall_post_unlink_failure_restores_the_attempted_plist(self) -> None:
        installed = {}
        for component in self.runtime.COMPONENTS:
            payload = f"installed-{component}".encode()
            installed[component] = payload
            self.system.files[self.paths.plists[component]] = payload
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installed",
            installed=installed,
            identities={},
        )
        first_path = next(iter(self.paths.plists.values()))
        self.system.remove_after_failure = first_path.name

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "uninstall_failed"
        ):
            self.controller.uninstall()

        self.assertEqual(self.system.files[first_path], installed["market-loopback"])
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "installed")

    def test_uninstall_third_payload_during_restore_gets_zero_bootstrap_or_overwrite(
        self,
    ) -> None:
        installed = {}
        for index, component in enumerate(self.runtime.COMPONENTS, start=1):
            payload = self.managed_plist(component, f"old-{component}")
            installed[component] = payload
            self.system.files[self.paths.plists[component]] = payload
            self.make_owned(component, 11000 + index)
        self.seed_manifest()
        first_path = next(iter(self.paths.plists.values()))
        real_remove = self.system.remove_exact_file
        removal_count = 0

        def inject_third_payload_then_fail(path: Path, expected_digest=None):
            nonlocal removal_count
            real_remove(path, expected_digest)
            removal_count += 1
            if removal_count == 3:
                self.system.files[first_path] = b"third-party-payload"
                raise self.runtime.RuntimeLifecycleError("command_failed")

        self.system.remove_exact_file = inject_third_payload_then_fail
        self.system.events.clear()

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "uninstall_failed"
        ):
            self.controller.uninstall()

        self.assertEqual(self.system.files[first_path], b"third-party-payload")
        self.assertNotIn("bootstrap", [event[0] for event in self.system.events])
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "rollback_required")

    def test_uninstall_commit_gate_rejects_a_listener_appearing_after_removal(
        self,
    ) -> None:
        installed = {}
        for component in self.runtime.COMPONENTS:
            payload = f"installed-{component}".encode()
            installed[component] = payload
            self.system.files[self.paths.plists[component]] = payload
        self.system.files[self.paths.ownership_metadata] = self.runtime.render_manifest(
            self.paths,
            state="installed",
            installed=installed,
            identities={},
        )
        last_path = tuple(self.paths.plists.values())[-1]
        real_remove = self.system.remove_exact_file

        def add_listener_after_last_remove(path: Path, expected_digest=None):
            real_remove(path, expected_digest)
            if path == last_path:
                self.system.listeners[
                    self.runtime.COMPONENTS["market-loopback"].port
                ] = (9983,)

        self.system.remove_exact_file = add_listener_after_last_remove

        with self.assertRaisesRegex(
            self.runtime.RuntimeLifecycleError, "uninstall_failed"
        ):
            self.controller.uninstall()

        self.assertTrue(
            all(path in self.system.files for path in self.installed_paths())
        )
        manifest = json.loads(
            self.system.files[self.paths.ownership_metadata].decode("utf-8")
        )
        self.assertEqual(manifest["state"], "rollback_required")
        self.assertNotIn("bootout", [event[0] for event in self.system.events])

    def test_main_json_is_deterministic_and_all_failures_are_redacted(self) -> None:
        status = OrderedDict((("components", []), ("legacy", [])))
        fake_controller = mock.Mock()
        fake_controller.status.return_value = status
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            self.runtime, "build_default_controller", return_value=fake_controller
        ):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                first = self.runtime.main(["status", "--json"])
            first_output = stdout.getvalue()
            stdout.seek(0)
            stdout.truncate(0)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                second = self.runtime.main(["status", "--json"])
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(first_output, stdout.getvalue())

        fake_controller.install.side_effect = RuntimeError(
            f"{SYNTHETIC_SECRET} Authorization: Bearer pairing-code"
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            self.runtime, "build_default_controller", return_value=fake_controller
        ):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = self.runtime.main(["install"])
        self.assertEqual(result, 2)
        rendered = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(rendered, "local runtime command failed\n")
        self.assertNotIn(SYNTHETIC_SECRET, rendered)

    def test_retired_foreground_supervisor_is_a_fixed_fail_fast_migration_shim(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[2]
        script = repository / "scripts/run_local_dev_stack.sh"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            fake_bin = temporary_path / "bin"
            fake_bin.mkdir()
            environment_file = temporary_path / "hostile.env"
            probe = temporary_path / "environment-was-sourced"
            path_probe = temporary_path / "path-bash-was-executed"
            bash_env_probe = temporary_path / "bash-env-was-sourced"
            fake_bash = fake_bin / "bash"
            fake_bash.write_text(
                "#!/bin/sh\n"
                '/usr/bin/touch "${US_STOCK_HELPER_PATH_PROBE}"\n'
                'exec /bin/bash "$@"\n',
                encoding="utf-8",
            )
            fake_bash.chmod(0o755)
            bash_env = temporary_path / "hostile-bash-env"
            bash_env.write_text(
                '/usr/bin/touch "${US_STOCK_HELPER_BASH_ENV_PROBE}"\n',
                encoding="utf-8",
            )
            environment_file.write_text(
                '/usr/bin/touch "${US_STOCK_HELPER_TEST_PROBE}"\nexit 73\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(script), f"ignored-{SYNTHETIC_SECRET}"],
                cwd=repository,
                env={
                    "BASH_ENV": str(bash_env),
                    "ENV": str(bash_env),
                    "HOME": temporary,
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "US_STOCK_HELPER_BASH_ENV_PROBE": str(bash_env_probe),
                    "US_STOCK_HELPER_ENV_FILE": str(environment_file),
                    "US_STOCK_HELPER_PATH_PROBE": str(path_probe),
                    "US_STOCK_HELPER_TEST_PROBE": str(probe),
                },
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "run_local_dev_stack.sh is retired; the durable stack is managed by launchd.\n"
                "Run: python3 scripts/local_runtime.py install\n",
            )
            self.assertFalse(probe.exists())
            self.assertFalse(path_probe.exists())
            self.assertFalse(bash_env_probe.exists())
            self.assertNotIn(SYNTHETIC_SECRET, result.stderr)

    def test_direct_script_invalid_arguments_do_not_emit_raw_input(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                __import__("sys").executable,
                str(repository / "scripts/local_runtime.py"),
                f"unknown-{SYNTHETIC_SECRET}",
            ],
            cwd=repository,
            env={"PYTHONPATH": str(repository)},
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "local runtime command failed\n")
        self.assertNotIn(SYNTHETIC_SECRET, result.stderr)


if __name__ == "__main__":
    unittest.main()
