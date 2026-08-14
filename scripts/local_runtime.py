#!/usr/bin/env python3
"""Install and inspect the four fixed macOS local-development LaunchAgents.

The lifecycle is deliberately fail-closed.  A matching port or launchd label
is never ownership on its own; mutating commands require the installed plist,
private manifest, launchd record, listener PID, and process identity to agree.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import plistlib
import pwd
import re
import signal
import socket
import stat
import subprocess
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence, cast

if __package__:
    from .local_runtime_launch import (
        COMPONENT_LABELS,
        NODE_22_EXECUTABLE,
        prepare_launch,
        render_launch_agent,
        validate_repository_identity,
        validate_runtime_directory_chain,
        validate_runtime_file,
    )
    from .local_runtime_support import (
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        PRIVATE_FILE_MODE,
        RuntimeConfigurationError,
        atomic_write_private_file,
        atomic_write_trusted_file,
        ensure_private_directory,
        ensure_private_file,
        parse_runtime_environment,
        quarantine_trusted_file,
    )
else:
    from local_runtime_launch import (  # type: ignore[no-redef]
        COMPONENT_LABELS,
        NODE_22_EXECUTABLE,
        prepare_launch,
        render_launch_agent,
        validate_repository_identity,
        validate_runtime_directory_chain,
        validate_runtime_file,
    )
    from local_runtime_support import (  # type: ignore[no-redef]
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        PRIVATE_FILE_MODE,
        RuntimeConfigurationError,
        atomic_write_private_file,
        atomic_write_trusted_file,
        ensure_private_directory,
        ensure_private_file,
        parse_runtime_environment,
        quarantine_trusted_file,
    )


LAUNCHCTL = Path("/bin/launchctl")
LSOF = Path("/usr/sbin/lsof")
PLUTIL = Path("/usr/bin/plutil")
PS = Path("/bin/ps")
MANIFEST_VERSION = 1
LEGACY_PORTS = (8081, 8083)
_COMMAND_TIMEOUT_SECONDS = 5
_PORT_CLEAR_TIMEOUT_SECONDS = 15
_OWNERSHIP_WAIT_TIMEOUT_SECONDS = 30
_BOOTOUT_TIMEOUT_SECONDS = 20
_HTTP_CONNECT_TIMEOUT_SECONDS = 1
_HTTP_TOTAL_TIMEOUT_SECONDS = 3
_MAX_HEALTH_BODY_BYTES = 4096
_PYTHON_PROCESS_EXECUTABLE = Path(
    "/Library/Frameworks/Python.framework/Versions/3.11/Resources/"
    "Python.app/Contents/MacOS/Python"
)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_START_TIME_PATTERN = re.compile(r"[A-Za-z0-9:+. _-]{1,80}\Z")


class RuntimeLifecycleError(RuntimeError):
    """A fixed-code lifecycle error that is safe to handle without rendering."""

    _ALLOWED = frozenset(
        {
            "already_loaded",
            "bootstrap_failed",
            "command_failed",
            "health_failed",
            "invalid_manifest",
            "invalid_plist",
            "malformed_tool_output",
            "ownership_manifest_mismatch",
            "ownership_mismatch",
            "rollback_failed",
            "unsafe_path",
            "unknown_target_listener",
            "uninstall_failed",
        }
    )

    def __init__(self, code: str) -> None:
        super().__init__(code if code in self._ALLOWED else "command_failed")
        self.code = code if code in self._ALLOWED else "command_failed"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    repository: Path
    home: Path
    ca_bundle: Path
    launch_agents: Path
    runtime_root: Path
    environment_file: Path
    logs: Path
    temporary: Path
    state: Path
    staging: Path
    ownership_metadata: Path
    device_database: Path
    plists: Mapping[str, Path]

    @classmethod
    def for_testing(
        cls,
        *,
        repository: Path,
        home: Path,
        ca_bundle: Path,
    ) -> "RuntimePaths":
        if not all(path.is_absolute() for path in (repository, home, ca_bundle)):
            raise RuntimeLifecycleError("unsafe_path")
        runtime_root = home / ".us-stock-helper"
        launch_agents = home / "Library/LaunchAgents"
        plists = OrderedDict(
            (
                component,
                launch_agents / f"{label}.plist",
            )
            for component, label in COMPONENT_LABELS.items()
        )
        return cls(
            repository=repository,
            home=home,
            ca_bundle=ca_bundle,
            launch_agents=launch_agents,
            runtime_root=runtime_root,
            environment_file=runtime_root / "lan.env",
            logs=runtime_root / "logs",
            temporary=runtime_root / "tmp",
            state=runtime_root / "state",
            staging=runtime_root / "staging",
            ownership_metadata=runtime_root / "ownership.json",
            device_database=runtime_root / "state/devices.sqlite3",
            plists=MappingProxyType(plists),
        )

    @classmethod
    def default(cls) -> "RuntimePaths":
        repository = Path(__file__).resolve().parents[1]
        try:
            home = Path(pwd.getpwuid(os.geteuid()).pw_dir).resolve(strict=True)
        except (KeyError, OSError):
            raise RuntimeLifecycleError("unsafe_path") from None
        ca_bundle = (
            repository / "services/market_gateway/.venv/lib/python3.11/site-packages/"
            "certifi/cacert.pem"
        )
        return cls.for_testing(
            repository=repository,
            home=home,
            ca_bundle=ca_bundle,
        )


@dataclass(frozen=True, slots=True)
class ComponentRuntime:
    name: str
    label: str
    port: int
    health_path: str
    expected_http_status: int
    health_kind: str

    def expected_cwd(self, paths: RuntimePaths) -> Path:
        return (
            paths.repository / "apps/mobile"
            if self.name == "metro"
            else paths.repository
        )

    def expected_command(self, paths: RuntimePaths) -> tuple[str, ...]:
        """The exact launchd ProgramArguments (the validation launcher)."""

        python = paths.repository / "services/market_gateway/.venv/bin/python"
        arguments = [
            str(python),
            str(paths.repository / "scripts/local_runtime_launch.py"),
            self.name,
            "--repository",
            str(paths.repository),
            "--home",
            str(paths.home),
            "--temporary-directory",
            str(paths.temporary),
        ]
        if self.name in {"market-lan", "analysis-api"}:
            arguments.extend(("--environment-file", str(paths.environment_file)))
        if self.name != "metro":
            arguments.extend(("--ca-bundle", str(paths.ca_bundle)))
        return tuple(arguments)

    def expected_process_command(self, paths: RuntimePaths) -> tuple[str, ...]:
        """The exact post-exec process identity observed by macOS ``ps``."""

        if self.name == "metro":
            return (
                str(NODE_22_EXECUTABLE),
                str(paths.repository / "apps/mobile/node_modules/expo/bin/cli"),
                "start",
                "--dev-client",
                "--lan",
                "--port",
                "8088",
            )
        module = (
            "us_stock_helper_analysis_api"
            if self.name == "analysis-api"
            else "us_stock_helper_market_gateway"
        )
        return (str(_PYTHON_PROCESS_EXECUTABLE), "-m", module)


COMPONENTS: Mapping[str, ComponentRuntime] = MappingProxyType(
    OrderedDict(
        (
            (
                "market-loopback",
                ComponentRuntime(
                    "market-loopback",
                    COMPONENT_LABELS["market-loopback"],
                    8765,
                    "/health",
                    200,
                    "gateway",
                ),
            ),
            (
                "market-lan",
                ComponentRuntime(
                    "market-lan",
                    COMPONENT_LABELS["market-lan"],
                    8766,
                    "/health",
                    401,
                    "protected",
                ),
            ),
            (
                "analysis-api",
                ComponentRuntime(
                    "analysis-api",
                    COMPONENT_LABELS["analysis-api"],
                    8770,
                    "/health",
                    403,
                    "protected",
                ),
            ),
            (
                "metro",
                ComponentRuntime(
                    "metro", COMPONENT_LABELS["metro"], 8088, "/status", 200, "bundler"
                ),
            ),
        )
    )
)


@dataclass(frozen=True, slots=True)
class LaunchctlState:
    loaded: bool
    pid: int | None
    plist_path: str | None = None
    program: str | None = None
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    start_time: str
    executable: str
    cwd: str
    command_fingerprint: str


@dataclass(frozen=True, slots=True)
class HttpObservation:
    status: int | None
    error: str | None
    health_ok: bool | None = None


class HttpTransport(Protocol):
    def connect(self, host: str, port: int, timeout: float) -> None: ...
    def send(self, payload: bytes, timeout: float) -> int: ...
    def receive(self, size: int, timeout: float) -> bytes: ...
    def close(self) -> None: ...


class SocketHttpTransport:
    def __init__(self) -> None:
        self._socket: socket.socket | None = None

    def connect(self, host: str, port: int, timeout: float) -> None:
        self._socket = socket.create_connection((host, port), timeout=timeout)

    def send(self, payload: bytes, timeout: float) -> int:
        if self._socket is None:
            raise OSError("transport is not connected")
        self._socket.settimeout(timeout)
        return self._socket.send(payload)

    def receive(self, size: int, timeout: float) -> bytes:
        if self._socket is None:
            raise OSError("transport is not connected")
        self._socket.settimeout(timeout)
        return self._socket.recv(size)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None


def _fingerprint(arguments: Sequence[str]) -> str:
    return hashlib.sha256("\0".join(arguments).encode("utf-8")).hexdigest()


def _process_fingerprint(arguments: Sequence[str]) -> str:
    """Match the exact space-separated command representation returned by ps."""

    return hashlib.sha256(" ".join(arguments).encode("utf-8")).hexdigest()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def expected_process_identity(
    specification: ComponentRuntime,
    paths: RuntimePaths,
    *,
    pid: int,
    start_time: str,
) -> ProcessIdentity:
    command = specification.expected_process_command(paths)
    return ProcessIdentity(
        pid=pid,
        start_time=start_time,
        executable=command[0],
        cwd=str(specification.expected_cwd(paths)),
        command_fingerprint=_process_fingerprint(command),
    )


def _process_identity_matches_expected(
    specification: ComponentRuntime,
    paths: RuntimePaths,
    identity: ProcessIdentity,
) -> bool:
    expected = expected_process_identity(
        specification,
        paths,
        pid=identity.pid,
        start_time=identity.start_time,
    )
    return (
        identity.executable == expected.executable
        and identity.cwd == expected.cwd
        and identity.command_fingerprint == expected.command_fingerprint
    )


def classify_listener_ownership(
    specification: ComponentRuntime,
    paths: RuntimePaths,
    *,
    state: LaunchctlState,
    listener_pids: Sequence[int],
    process_identity: ProcessIdentity | None,
) -> str:
    if not listener_pids:
        return "none"
    expected_arguments = specification.expected_command(paths)
    if (
        len(listener_pids) != 1
        or not state.loaded
        or state.pid is None
        or listener_pids[0] != state.pid
        or state.plist_path != str(paths.plists[specification.name])
        or state.program != expected_arguments[0]
        or state.arguments != expected_arguments
        or process_identity is None
        or process_identity.pid != state.pid
        or not _process_identity_matches_expected(
            specification,
            paths,
            process_identity,
        )
    ):
        return "unknown"
    return "owned"


def _launchctl_contract_matches(
    specification: ComponentRuntime,
    paths: RuntimePaths,
    state: LaunchctlState,
) -> bool:
    arguments = specification.expected_command(paths)
    return (
        state.loaded
        and state.plist_path == str(paths.plists[specification.name])
        and state.program == arguments[0]
        and state.arguments == arguments
    )


def render_ownership_metadata(
    identities: Mapping[str, ProcessIdentity], paths: RuntimePaths
) -> bytes:
    return render_manifest(
        paths, state="installed", installed={}, identities=identities
    )


def render_manifest(
    paths: RuntimePaths,
    *,
    state: str,
    installed: Mapping[str, bytes],
    identities: Mapping[str, ProcessIdentity],
    previous: Mapping[str, bytes] | None = None,
) -> bytes:
    if state not in {
        "installing",
        "installed",
        "uninstalling",
        "uninstalled",
        "rollback_required",
    }:
        raise RuntimeLifecycleError("invalid_manifest")
    previous = previous or {}
    components: OrderedDict[str, object] = OrderedDict()
    for name, specification in COMPONENTS.items():
        identity = identities.get(name)
        payload = installed.get(name)
        old_payload = previous.get(name)
        components[name] = OrderedDict(
            (
                ("label", specification.label),
                ("port", specification.port),
                ("plist_path", str(paths.plists[name])),
                ("plist_sha256", _digest(payload) if payload is not None else None),
                (
                    "previous_sha256",
                    _digest(old_payload) if old_payload is not None else None,
                ),
                (
                    "launch_fingerprint",
                    _fingerprint(specification.expected_command(paths)),
                ),
                ("executable", identity.executable if identity else None),
                (
                    "cwd",
                    (
                        identity.cwd
                        if identity
                        else str(specification.expected_cwd(paths))
                    ),
                ),
                (
                    "command_fingerprint",
                    (
                        identity.command_fingerprint
                        if identity
                        else _process_fingerprint(
                            specification.expected_process_command(paths)
                        )
                    ),
                ),
                ("pid", identity.pid if identity else None),
                ("start_time", identity.start_time if identity else None),
            )
        )
    document = OrderedDict(
        (("version", MANIFEST_VERSION), ("state", state), ("components", components))
    )
    return (
        json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _parse_manifest(
    payload: bytes | None, paths: RuntimePaths
) -> dict[str, object] | None:
    if payload is None:
        return None
    if len(payload) > 64 * 1024:
        raise RuntimeLifecycleError("invalid_manifest")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeLifecycleError("invalid_manifest") from None
    if (
        type(document) is not dict
        or set(document) != {"version", "state", "components"}
        or document["version"] != MANIFEST_VERSION
        or document["state"]
        not in {
            "installing",
            "installed",
            "uninstalling",
            "uninstalled",
            "rollback_required",
        }
        or type(document["components"]) is not dict
        or tuple(document["components"]) != tuple(COMPONENTS)
    ):
        raise RuntimeLifecycleError("invalid_manifest")
    expected_keys = {
        "label",
        "port",
        "plist_path",
        "plist_sha256",
        "previous_sha256",
        "launch_fingerprint",
        "executable",
        "cwd",
        "command_fingerprint",
        "pid",
        "start_time",
    }
    for name, specification in COMPONENTS.items():
        entry = document["components"].get(name)
        if type(entry) is not dict or set(entry) != expected_keys:
            raise RuntimeLifecycleError("invalid_manifest")
        digests = (entry["plist_sha256"], entry["previous_sha256"])
        if any(
            value is not None
            and (type(value) is not str or not _HASH_PATTERN.fullmatch(value))
            for value in digests
        ):
            raise RuntimeLifecycleError("invalid_manifest")
        if (
            entry["label"] != specification.label
            or entry["port"] != specification.port
            or entry["plist_path"] != str(paths.plists[name])
            or entry["launch_fingerprint"]
            != _fingerprint(specification.expected_command(paths))
            or entry["cwd"] != str(specification.expected_cwd(paths))
            or entry["command_fingerprint"]
            != _process_fingerprint(specification.expected_process_command(paths))
            or (
                entry["executable"] is not None
                and entry["executable"]
                != specification.expected_process_command(paths)[0]
            )
            or (
                entry["pid"] is not None
                and (type(entry["pid"]) is not int or entry["pid"] <= 0)
            )
            or (
                entry["start_time"] is not None
                and (
                    type(entry["start_time"]) is not str
                    or not _START_TIME_PATTERN.fullmatch(entry["start_time"])
                )
            )
        ):
            raise RuntimeLifecycleError("invalid_manifest")
    return document


def parse_launchctl_print(
    output: str, *, expected_domain: str | None = None
) -> LaunchctlState:
    if "\x00" in output or len(output) > 128 * 1024:
        raise RuntimeLifecycleError("malformed_tool_output")
    lines = output.splitlines()
    if not lines or not lines[0].endswith(" = {") or not lines[0].startswith("gui/"):
        raise RuntimeLifecycleError("malformed_tool_output")
    domain = lines[0][:-4]
    if expected_domain is not None and domain != expected_domain:
        raise RuntimeLifecycleError("malformed_tool_output")

    def unique_value(key: str) -> str:
        prefix = f"\t{key} = "
        values = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
        if len(values) != 1 or not values[0]:
            raise RuntimeLifecycleError("malformed_tool_output")
        return values[0]

    path = unique_value("path")
    program = unique_value("program")
    state_value = unique_value("state")
    pid_prefix = "\tpid = "
    pid_values = [
        line[len(pid_prefix) :] for line in lines if line.startswith(pid_prefix)
    ]
    if len(pid_values) > 1:
        raise RuntimeLifecycleError("malformed_tool_output")
    pid: int | None = None
    if pid_values:
        pid_text = pid_values[0]
        if not pid_text.isascii() or not pid_text.isdecimal() or int(pid_text) <= 0:
            raise RuntimeLifecycleError("malformed_tool_output")
        pid = int(pid_text)
    elif state_value not in {"spawn scheduled", "waiting", "throttled", "exited"}:
        raise RuntimeLifecycleError("malformed_tool_output")
    argument_starts = [
        index for index, line in enumerate(lines) if line == "\targuments = {"
    ]
    if len(argument_starts) != 1:
        raise RuntimeLifecycleError("malformed_tool_output")
    start = argument_starts[0] + 1
    try:
        end = lines.index("\t}", start)
    except ValueError:
        raise RuntimeLifecycleError("malformed_tool_output") from None
    arguments = tuple(line[2:] for line in lines[start:end] if line.startswith("\t\t"))
    if (
        not arguments
        or end - start != len(arguments)
        or any(not value for value in arguments)
    ):
        raise RuntimeLifecycleError("malformed_tool_output")
    return LaunchctlState(True, pid, path, program, arguments)


def parse_lsof_pids(
    output: str | bytes,
    *,
    expected_port: int | None = None,
) -> tuple[int, ...]:
    raw = output.encode("utf-8") if isinstance(output, str) else output
    if len(raw) > 256 * 1024:
        raise RuntimeLifecycleError("malformed_tool_output")
    pids: set[int] = set()
    current_pid: int | None = None
    saw_file = False
    saw_name = False
    saw_listen = False

    def finish_record() -> None:
        if current_pid is not None and not (saw_file and saw_name and saw_listen):
            raise RuntimeLifecycleError("malformed_tool_output")

    for field in raw.split(b"\0"):
        field = field.strip(b"\r\n")
        if not field:
            continue
        prefix, value = field[:1], field[1:]
        if prefix == b"p":
            finish_record()
            if not value.isdigit() or int(value) <= 0:
                raise RuntimeLifecycleError("malformed_tool_output")
            current_pid = int(value)
            pids.add(current_pid)
            saw_file = saw_name = saw_listen = False
        elif prefix == b"f":
            if current_pid is None or not value:
                raise RuntimeLifecycleError("malformed_tool_output")
            saw_file = True
        elif prefix == b"n":
            if current_pid is None or not value:
                raise RuntimeLifecycleError("malformed_tool_output")
            if expected_port is not None and value.rsplit(b":", 1)[-1] != str(
                expected_port
            ).encode("ascii"):
                raise RuntimeLifecycleError("malformed_tool_output")
            saw_name = True
        elif prefix == b"T":
            if current_pid is None or not value:
                raise RuntimeLifecycleError("malformed_tool_output")
            if value == b"ST=LISTEN":
                saw_listen = True
        else:
            raise RuntimeLifecycleError("malformed_tool_output")
    finish_record()
    if raw and not pids:
        raise RuntimeLifecycleError("malformed_tool_output")
    return tuple(sorted(pids))


def parse_process_line(output: str) -> ProcessIdentity:
    parts = output.rstrip("\n").split("\t")
    if len(parts) != 5:
        raise RuntimeLifecycleError("malformed_tool_output")
    pid_text, executable, start_time, cwd, command = parts
    if (
        not pid_text.isdecimal()
        or int(pid_text) <= 0
        or not executable.startswith("/")
        or not cwd.startswith("/")
        or not command
        or not _START_TIME_PATTERN.fullmatch(start_time)
    ):
        raise RuntimeLifecycleError("malformed_tool_output")
    return ProcessIdentity(
        int(pid_text),
        start_time,
        executable,
        cwd,
        hashlib.sha256(command.encode("utf-8")).hexdigest(),
    )


def gateway_health_is_healthy(payload: object) -> bool:
    if (
        type(payload) is not dict
        or payload.get("source") != "moomoo"
        or payload.get("session") != "healthy"
    ):
        return False
    items = payload.get("items")
    return (
        type(items) is list
        and bool(items)
        and all(
            type(item) is dict and item.get("status") == "healthy" for item in items
        )
    )


def bounded_http_observation(
    specification: ComponentRuntime,
    *,
    transport: HttpTransport | None = None,
    monotonic=time.monotonic,
) -> HttpObservation:
    """Issue one fixed no-auth HTTP request under one wall-clock deadline."""

    client = transport or SocketHttpTransport()
    deadline = monotonic() + _HTTP_TOTAL_TIMEOUT_SECONDS

    def remaining() -> float:
        value = deadline - monotonic()
        if value <= 0:
            raise TimeoutError
        return value

    try:
        client.connect(
            "127.0.0.1",
            specification.port,
            min(_HTTP_CONNECT_TIMEOUT_SECONDS, remaining()),
        )
        request = (
            f"GET {specification.health_path} HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Connection: close\r\n"
            "Accept: application/json\r\n\r\n"
        ).encode("ascii")
        sent = 0
        while sent < len(request):
            written = client.send(request[sent:], remaining())
            if written <= 0:
                raise OSError("short HTTP write")
            sent += written

        response = bytearray()
        header_end = -1
        while header_end < 0:
            if len(response) > 16 * 1024:
                raise OSError("HTTP header is too large")
            chunk = client.receive(4096, remaining())
            if not chunk:
                raise OSError("HTTP response ended before headers")
            response.extend(chunk)
            header_end = response.find(b"\r\n\r\n")

        header_bytes = bytes(response[:header_end])
        body = bytearray(response[header_end + 4 :])
        try:
            header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
            version, status_text, _reason = header_lines[0].split(" ", 2)
            status = int(status_text)
        except (UnicodeError, ValueError):
            raise OSError("HTTP status is malformed") from None
        if version not in {"HTTP/1.0", "HTTP/1.1"} or not 100 <= status <= 599:
            raise OSError("HTTP status is malformed")

        headers: dict[str, str] = {}
        for line in header_lines[1:]:
            if ":" not in line:
                raise OSError("HTTP header is malformed")
            key, value = line.split(":", 1)
            normalized = key.strip().lower()
            if not normalized or normalized in headers:
                raise OSError("HTTP header is malformed")
            headers[normalized] = value.strip()

        if specification.health_kind != "gateway" or status != 200:
            return HttpObservation(status, None, None)
        content_length_text = headers.get("content-length")
        content_length: int | None = None
        if content_length_text is not None:
            if not content_length_text.isdecimal():
                return HttpObservation(status, "invalid_health", False)
            content_length = int(content_length_text)
            if content_length > _MAX_HEALTH_BODY_BYTES:
                return HttpObservation(status, "invalid_health", False)
        while len(body) < (
            content_length if content_length is not None else _MAX_HEALTH_BODY_BYTES + 1
        ):
            chunk = client.receive(
                min(4096, _MAX_HEALTH_BODY_BYTES + 1 - len(body)),
                remaining(),
            )
            if not chunk:
                break
            body.extend(chunk)
        if content_length is not None and len(body) != content_length:
            return HttpObservation(status, "invalid_health", False)
        if len(body) > _MAX_HEALTH_BODY_BYTES:
            return HttpObservation(status, "invalid_health", False)
        try:
            payload = json.loads(bytes(body).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return HttpObservation(status, "invalid_health", False)
        health_ok = gateway_health_is_healthy(payload)
        return HttpObservation(
            status,
            None if health_ok else "unhealthy",
            health_ok,
        )
    except (OSError, TimeoutError):
        return HttpObservation(None, "unreachable", None)
    finally:
        client.close()


@contextlib.contextmanager
def runtime_command_lock(path: Path):
    """Serialize every worktree on the shared trusted LaunchAgents directory."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode))
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise RuntimeLifecycleError("unsafe_path")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeLifecycleError("command_failed") from None
        yield
    except OSError:
        raise RuntimeLifecycleError("unsafe_path") from None
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)


@contextlib.contextmanager
def _transaction_signal_guard():
    previous = {}
    interrupted = False

    def interrupt_transaction(signum, frame):
        nonlocal interrupted
        del frame
        if interrupted:
            return
        interrupted = True
        # Rollback/finalization must not itself be interrupted by a second
        # bedtime terminal close or repeated Ctrl-C.
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signal_number, signal.SIG_IGN)
        del signum
        raise KeyboardInterrupt

    try:
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            previous[signal_number] = signal.signal(
                signal_number,
                interrupt_transaction,
            )
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


class SystemBoundary(Protocol):
    def preflight_read_only(self, paths: RuntimePaths) -> None: ...
    def preflight_management(self, paths: RuntimePaths) -> None: ...
    def validate_installed_target(self, path: Path) -> None: ...
    def prepare_private_paths(self, paths: RuntimePaths) -> None: ...
    def prepare_management_metadata(self, paths: RuntimePaths) -> None: ...
    def validate_component_launches(self, paths: RuntimePaths) -> None: ...
    def render_plist(self, component: str, paths: RuntimePaths) -> bytes: ...
    def write_private(self, path: Path, payload: bytes) -> None: ...
    def confirm_private_write(self, path: Path, payload: bytes) -> None: ...
    def confirm_trusted_write(self, path: Path, payload: bytes) -> None: ...
    def confirm_file_absence(self, path: Path) -> None: ...
    def install_plist(
        self, path: Path, payload: bytes, expected_digest: str | None
    ) -> None: ...
    def validate_staged_plist(self, path: Path, label: str) -> None: ...
    def read_optional_private(self, path: Path) -> bytes | None: ...
    def remove_exact_file(
        self, path: Path, expected_digest: str | None = None
    ) -> None: ...
    def launchctl_state(self, label: str) -> LaunchctlState: ...
    def listener_pids(self, port: int) -> tuple[int, ...]: ...
    def process_identity(self, pid: int) -> ProcessIdentity | None: ...
    def wait_until_port_clear(self, port: int) -> None: ...
    def wait_for_owned(
        self, specification: ComponentRuntime, paths: RuntimePaths
    ) -> ProcessIdentity: ...
    def bootstrap(self, label: str, path: Path) -> None: ...
    def bootout(self, label: str) -> None: ...
    def http_observation(self, specification: ComponentRuntime) -> HttpObservation: ...


class RuntimeController:
    def __init__(self, paths: RuntimePaths, system: SystemBoundary) -> None:
        self.paths = paths
        self.system = system

    def _write_manifest_intent(self, payload: bytes) -> None:
        """Resolve a possible post-replace error without overwriting a third value."""

        try:
            self.system.write_private(self.paths.ownership_metadata, payload)
        except BaseException:
            current = self.system.read_optional_private(self.paths.ownership_metadata)
            if current != payload:
                raise
            # The rename happened but its durability confirmation may have
            # failed.  Revalidate the exact bytes and fsync their parent.
            self.system.confirm_private_write(
                self.paths.ownership_metadata,
                payload,
            )

    def _install_plist_intent(
        self,
        path: Path,
        payload: bytes,
        expected_digest: str | None,
    ) -> None:
        """Resolve a no-clobber publish result by observing exact bytes."""

        for attempt in range(2):
            try:
                self.system.install_plist(path, payload, expected_digest)
                return
            except Exception:
                current = self.system.read_optional_private(path)
                if current == payload:
                    self.system.confirm_trusted_write(path, payload)
                    return
                current_digest = _digest(current) if current is not None else None
                if current_digest != expected_digest or attempt == 1:
                    raise
        raise RuntimeLifecycleError("ownership_manifest_mismatch")

    def _remove_exact_intent(self, path: Path, expected_payload: bytes) -> None:
        """Resolve an exact quarantine result without deleting a third value."""

        expected_digest = _digest(expected_payload)
        for attempt in range(2):
            try:
                self.system.remove_exact_file(path, expected_digest)
                return
            except Exception:
                current = self.system.read_optional_private(path)
                if current is None:
                    self.system.confirm_file_absence(path)
                    return
                if current != expected_payload or attempt == 1:
                    raise
        raise RuntimeLifecycleError("ownership_manifest_mismatch")

    def _read_existing(
        self,
    ) -> tuple[dict[str, bytes | None], bytes | None, dict[str, object] | None]:
        existing = {
            name: self.system.read_optional_private(path)
            for name, path in self.paths.plists.items()
        }
        manifest_payload = self.system.read_optional_private(
            self.paths.ownership_metadata
        )
        manifest = _parse_manifest(manifest_payload, self.paths)
        if manifest is None:
            if any(payload is not None for payload in existing.values()):
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
            return existing, manifest_payload, manifest
        for name, payload in existing.items():
            recorded_digest = manifest["components"][name]["plist_sha256"]  # type: ignore[index]
            actual_digest = _digest(payload) if payload is not None else None
            if recorded_digest != actual_digest:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        return existing, manifest_payload, manifest

    def _recovery_observations(
        self,
        final_payloads: Mapping[str, bytes | None],
    ) -> dict[str, LaunchctlState]:
        """Validate every target before an interrupted transaction is resumed."""

        states: dict[str, LaunchctlState] = {}
        for name, specification in COMPONENTS.items():
            state = self.system.launchctl_state(specification.label)
            listeners = self.system.listener_pids(specification.port)
            identity = self.system.process_identity(state.pid) if state.pid else None
            ownership = classify_listener_ownership(
                specification,
                self.paths,
                state=state,
                listener_pids=listeners,
                process_identity=identity,
            )
            if listeners and ownership != "owned":
                raise RuntimeLifecycleError("unknown_target_listener")
            if state.loaded and (
                not _launchctl_contract_matches(specification, self.paths, state)
                or final_payloads[name] is None
                or (listeners and ownership != "owned")
                or (state.pid is not None and identity is None)
                or (
                    identity is not None
                    and not _process_identity_matches_expected(
                        specification,
                        self.paths,
                        identity,
                    )
                )
            ):
                raise RuntimeLifecycleError("ownership_mismatch")
            states[name] = state
        return states

    def _recover_interrupted_state(self) -> str | None:
        manifest_payload = self.system.read_optional_private(
            self.paths.ownership_metadata
        )
        manifest = _parse_manifest(manifest_payload, self.paths)
        if manifest is None or manifest["state"] not in {
            "installing",
            "uninstalling",
        }:
            return None

        state_name = str(manifest["state"])
        if state_name == "installing":
            self.system.preflight_read_only(self.paths)
        else:
            self.system.preflight_management(self.paths)
        final_payloads = {
            name: self.system.read_optional_private(path)
            for name, path in self.paths.plists.items()
        }
        staged_payloads: dict[str, bytes] = {}
        for name, specification in COMPONENTS.items():
            entry = manifest["components"][name]  # type: ignore[index]
            current = final_payloads[name]
            current_digest = _digest(current) if current is not None else None
            if state_name == "installing":
                stage = self.paths.staging / f"{specification.label}.plist"
                staged = self.system.read_optional_private(stage)
                if staged is None or _digest(staged) != entry["plist_sha256"]:
                    raise RuntimeLifecycleError("ownership_manifest_mismatch")
                self.system.validate_staged_plist(stage, specification.label)
                staged_payloads[name] = staged
                if current_digest not in {
                    None,
                    entry["previous_sha256"],
                    entry["plist_sha256"],
                }:
                    raise RuntimeLifecycleError("ownership_manifest_mismatch")
            elif current_digest not in {None, entry["plist_sha256"]}:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")

        # Ownership for all four labels/listeners is established before the
        # first bootout, permission repair, plist write, or removal.
        states = self._recovery_observations(final_payloads)
        self._validate_recovery_reachability(
            manifest,
            final_payloads,
            states,
        )
        if state_name == "installing":
            self.system.prepare_private_paths(self.paths)
            self.system.validate_component_launches(self.paths)
        else:
            self.system.prepare_management_metadata(self.paths)

        for name in reversed(tuple(COMPONENTS)):
            current_payloads = {
                component: self.system.read_optional_private(path)
                for component, path in self.paths.plists.items()
            }
            current_states = self._recovery_observations(current_payloads)
            self._validate_recovery_reachability(
                manifest,
                current_payloads,
                current_states,
            )
            if current_states[name].loaded:
                self.system.bootout(COMPONENTS[name].label)
                self.system.wait_until_port_clear(COMPONENTS[name].port)

        if state_name == "installing":
            captured: dict[str, ProcessIdentity] = {}
            for name, payload in staged_payloads.items():
                current = self.system.read_optional_private(self.paths.plists[name])
                entry = manifest["components"][name]  # type: ignore[index]
                current_digest = _digest(current) if current is not None else None
                if current_digest not in {
                    None,
                    entry["previous_sha256"],
                    entry["plist_sha256"],
                }:
                    raise RuntimeLifecycleError("ownership_manifest_mismatch")
                if current != payload:
                    self._install_plist_intent(
                        self.paths.plists[name],
                        payload,
                        _digest(current) if current is not None else None,
                    )
            for name, specification in COMPONENTS.items():
                self._prepare_exact_bootstrap(name, staged_payloads[name])
                self.system.bootstrap(specification.label, self.paths.plists[name])
                captured[name] = self.system.wait_for_owned(
                    specification,
                    self.paths,
                )
            captured = self._installed_commit_snapshot(staged_payloads)
            self._write_manifest_intent(
                render_manifest(
                    self.paths,
                    state="installed",
                    installed=staged_payloads,
                    identities=captured,
                ),
            )
        else:
            manifest_components = cast(
                Mapping[str, Mapping[str, object]],
                manifest["components"],
            )
            for name in COMPONENTS:
                current_payload = self.system.read_optional_private(
                    self.paths.plists[name]
                )
                expected_digest = manifest_components[name]["plist_sha256"]
                if (
                    current_payload is not None
                    and _digest(current_payload) != expected_digest
                ):
                    raise RuntimeLifecycleError("ownership_manifest_mismatch")
                if current_payload is not None:
                    self.system.remove_exact_file(
                        self.paths.plists[name],
                        _digest(current_payload),
                    )
            self._uninstalled_commit_snapshot()
            self._write_manifest_intent(
                render_manifest(
                    self.paths,
                    state="uninstalled",
                    installed={},
                    identities={},
                ),
            )
        return state_name

    def _validate_recovery_reachability(
        self,
        manifest: Mapping[str, object],
        final_payloads: Mapping[str, bytes | None],
        states: Mapping[str, LaunchctlState],
    ) -> None:
        if not any(state.loaded for state in states.values()):
            return
        actual = {
            name: _digest(payload) if payload is not None else None
            for name, payload in final_payloads.items()
        }
        components = cast(
            Mapping[str, Mapping[str, object]],
            manifest["components"],
        )
        if manifest["state"] == "installing":
            all_new = all(
                actual[name] == components[name]["plist_sha256"] for name in COMPONENTS
            )
            all_previous = all(
                actual[name] == components[name]["previous_sha256"]
                for name in COMPONENTS
            )
            if not (all_new or all_previous):
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        elif any(
            actual[name] != components[name]["plist_sha256"] for name in COMPONENTS
        ):
            raise RuntimeLifecycleError("ownership_manifest_mismatch")

    def _inspect_targets(
        self, manifest: dict[str, object] | None, *, mutation: bool
    ) -> dict[str, tuple[LaunchctlState, tuple[int, ...], ProcessIdentity | None, str]]:
        observations = {}
        for name, specification in COMPONENTS.items():
            state = self.system.launchctl_state(specification.label)
            listeners = self.system.listener_pids(specification.port)
            identity = self.system.process_identity(state.pid) if state.pid else None
            ownership = classify_listener_ownership(
                specification,
                self.paths,
                state=state,
                listener_pids=listeners,
                process_identity=identity,
            )
            if listeners and ownership != "owned":
                raise RuntimeLifecycleError("unknown_target_listener")
            if state.loaded:
                inactive_owned = (
                    not listeners
                    and manifest is not None
                    and manifest["state"] == "installed"
                    and _launchctl_contract_matches(specification, self.paths, state)
                )
                if inactive_owned and identity is not None:
                    expected_identity = expected_process_identity(
                        specification,
                        self.paths,
                        pid=identity.pid,
                        start_time=identity.start_time,
                    )
                    inactive_owned = (
                        identity.executable == expected_identity.executable
                        and identity.cwd == expected_identity.cwd
                        and identity.command_fingerprint
                        == expected_identity.command_fingerprint
                    )
                if ownership != "owned" and not inactive_owned:
                    raise RuntimeLifecycleError("ownership_mismatch")
                if ownership == "owned":
                    if manifest is None or manifest["state"] != "installed":
                        raise RuntimeLifecycleError("ownership_mismatch")
                    entry = manifest["components"][name]  # type: ignore[index]
                    if (
                        identity is None
                        or entry["executable"] != identity.executable
                        or entry["cwd"] != identity.cwd
                        or entry["command_fingerprint"] != identity.command_fingerprint
                    ):
                        raise RuntimeLifecycleError("ownership_mismatch")
                else:
                    ownership = "owned_inactive"
            observations[name] = (state, listeners, identity, ownership)
        return observations

    def _active_owned_identity(self, name: str) -> ProcessIdentity:
        """Return the current exact identity or fail without mutating anything."""

        specification = COMPONENTS[name]
        state = self.system.launchctl_state(specification.label)
        listeners = self.system.listener_pids(specification.port)
        identity = self.system.process_identity(state.pid) if state.pid else None
        ownership = classify_listener_ownership(
            specification,
            self.paths,
            state=state,
            listener_pids=listeners,
            process_identity=identity,
        )
        if listeners and ownership != "owned":
            raise RuntimeLifecycleError("unknown_target_listener")
        if ownership != "owned" or identity is None:
            raise RuntimeLifecycleError("ownership_mismatch")
        return identity

    def _installed_commit_snapshot(
        self,
        expected_payloads: Mapping[str, bytes],
    ) -> dict[str, ProcessIdentity]:
        """Validate the four-component installed state just before commit."""

        for name, path in self.paths.plists.items():
            if self.system.read_optional_private(path) != expected_payloads[name]:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        return {name: self._active_owned_identity(name) for name in COMPONENTS}

    def _uninstalled_commit_snapshot(self) -> None:
        """Validate the four-component absent state just before commit."""

        for path in self.paths.plists.values():
            if self.system.read_optional_private(path) is not None:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        for specification in COMPONENTS.values():
            state = self.system.launchctl_state(specification.label)
            listeners = self.system.listener_pids(specification.port)
            if listeners:
                raise RuntimeLifecycleError("unknown_target_listener")
            if state.loaded:
                raise RuntimeLifecycleError("ownership_mismatch")

    def _restored_runtime_snapshot(
        self,
        expected_payloads: Mapping[str, bytes | None],
        originally_loaded: Sequence[str],
    ) -> None:
        """Prove rollback restored every plist and original service state."""

        for name, path in self.paths.plists.items():
            if self.system.read_optional_private(path) != expected_payloads[name]:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        loaded_names = set(originally_loaded)
        for name, specification in COMPONENTS.items():
            if name in loaded_names:
                self._active_owned_identity(name)
                continue
            state = self.system.launchctl_state(specification.label)
            listeners = self.system.listener_pids(specification.port)
            if listeners:
                raise RuntimeLifecycleError("unknown_target_listener")
            if state.loaded:
                raise RuntimeLifecycleError("ownership_mismatch")

    def _validate_bootstrap_payload(self, name: str, expected: bytes) -> None:
        current = self.system.read_optional_private(self.paths.plists[name])
        if current != expected:
            raise RuntimeLifecycleError("ownership_manifest_mismatch")
        try:
            document = plistlib.loads(current)
        except (ValueError, plistlib.InvalidFileException):
            raise RuntimeLifecycleError("invalid_plist") from None
        specification = COMPONENTS[name]
        if (
            type(document) is not dict
            or document.get("Label") != specification.label
            or document.get("ProgramArguments")
            != list(specification.expected_command(self.paths))
            or document.get("WorkingDirectory")
            != str(specification.expected_cwd(self.paths))
            or "Program" in document
        ):
            raise RuntimeLifecycleError("invalid_plist")

    def _prepare_exact_bootstrap(self, name: str, expected: bytes) -> None:
        """Close every known file/label/listener race immediately before launch."""

        specification = COMPONENTS[name]
        self._validate_bootstrap_payload(name, expected)
        state = self.system.launchctl_state(specification.label)
        if state.loaded:
            raise RuntimeLifecycleError("ownership_mismatch")
        if self.system.listener_pids(specification.port):
            raise RuntimeLifecycleError("unknown_target_listener")
        self.system.wait_until_port_clear(specification.port)
        # wait_until_port_clear may have taken time; repeat every read-only
        # ownership check directly adjacent to bootstrap.
        self._validate_bootstrap_payload(name, expected)
        state = self.system.launchctl_state(specification.label)
        if state.loaded:
            raise RuntimeLifecycleError("ownership_mismatch")
        if self.system.listener_pids(specification.port):
            raise RuntimeLifecycleError("unknown_target_listener")

    def _transaction_preflight(self):
        self.system.preflight_read_only(self.paths)
        for path in self.paths.plists.values():
            self.system.validate_installed_target(path)
        rendered = {
            name: self.system.render_plist(name, self.paths) for name in COMPONENTS
        }
        for name, payload in rendered.items():
            try:
                document = plistlib.loads(payload)
            except (ValueError, plistlib.InvalidFileException):
                raise RuntimeLifecycleError("invalid_plist") from None
            if document.get("Label") != COMPONENTS[name].label:
                raise RuntimeLifecycleError("invalid_plist")
        recovered = self._recover_interrupted_state()
        existing, manifest_payload, manifest = self._read_existing()
        observations = self._inspect_targets(manifest, mutation=True)
        return (
            rendered,
            existing,
            manifest_payload,
            manifest,
            observations,
            recovered,
        )

    def install(self) -> None:
        self._install(reinstall=False)

    def reinstall(self) -> None:
        self._install(reinstall=True)

    def _install(self, *, reinstall: bool) -> None:
        (
            rendered,
            existing,
            old_manifest_payload,
            manifest,
            observations,
            recovered,
        ) = self._transaction_preflight()
        if recovered == "installing" and not reinstall:
            return
        loaded_before = [
            name for name, observation in observations.items() if observation[0].loaded
        ]
        if loaded_before and not reinstall:
            raise RuntimeLifecycleError("already_loaded")

        self.system.prepare_private_paths(self.paths)
        self.system.validate_component_launches(self.paths)
        stage_paths: dict[str, Path] = {}
        for name, payload in rendered.items():
            stage = self.paths.staging / f"{COMPONENTS[name].label}.plist"
            stage_paths[name] = stage
            self.system.write_private(stage, payload)
        for name, stage in stage_paths.items():
            self.system.validate_staged_plist(stage, COMPONENTS[name].label)
        for path in self.paths.plists.values():
            self.system.validate_installed_target(path)

        # Revalidate every owned target immediately before the first mutation.
        observations = self._inspect_targets(manifest, mutation=True)
        loaded_before = [
            name for name, observation in observations.items() if observation[0].loaded
        ]
        if loaded_before and not reinstall:
            raise RuntimeLifecycleError("already_loaded")

        old_payloads = {
            name: payload for name, payload in existing.items() if payload is not None
        }
        installing_manifest = render_manifest(
            self.paths,
            state="installing",
            installed=rendered,
            identities={
                name: observation[2]
                for name, observation in observations.items()
                if observation[2] is not None
            },
            previous=old_payloads,
        )
        booted_out_old: list[str] = []
        installed_names: list[str] = []
        attempted_labels: list[str] = []
        loaded_attempt: list[str] = []
        captured: dict[str, ProcessIdentity] = {}
        installed_manifest: bytes | None = None
        try:
            self._write_manifest_intent(installing_manifest)
            if reinstall:
                for name in reversed(loaded_before):
                    current = self._inspect_targets(manifest, mutation=True)[name]
                    if not current[0].loaded or current[3] not in {
                        "owned",
                        "owned_inactive",
                    }:
                        raise RuntimeLifecycleError("ownership_mismatch")
                    self.system.bootout(COMPONENTS[name].label)
                    booted_out_old.append(name)
                    self.system.wait_until_port_clear(COMPONENTS[name].port)

            for name, payload in rendered.items():
                old = existing[name]
                installed_names.append(name)
                self._install_plist_intent(
                    self.paths.plists[name],
                    payload,
                    _digest(old) if old is not None else None,
                )

            for name, specification in COMPONENTS.items():
                attempted_labels.append(name)
                self._prepare_exact_bootstrap(name, rendered[name])
                self.system.bootstrap(specification.label, self.paths.plists[name])
                loaded_attempt.append(name)
                captured[name] = self.system.wait_for_owned(specification, self.paths)

            captured = self._installed_commit_snapshot(rendered)
            installed_manifest = render_manifest(
                self.paths,
                state="installed",
                installed=rendered,
                identities=captured,
            )
            self._write_manifest_intent(
                installed_manifest,
            )
        except BaseException as error:
            rollback_error = self._rollback_install(
                rendered=rendered,
                existing=existing,
                old_manifest_payload=old_manifest_payload,
                attempted_labels=attempted_labels,
                loaded_attempt=loaded_attempt,
                installed_names=installed_names,
                booted_out_old=booted_out_old,
                originally_loaded=loaded_before,
                installing_manifest=installing_manifest,
                installed_manifest=installed_manifest,
            )
            if rollback_error:
                try:
                    current_manifest = self.system.read_optional_private(
                        self.paths.ownership_metadata
                    )
                    if current_manifest in {
                        installing_manifest,
                        installed_manifest,
                        old_manifest_payload,
                    }:
                        self._write_manifest_intent(
                            render_manifest(
                                self.paths,
                                state="rollback_required",
                                installed=rendered,
                                identities=captured,
                                previous=old_payloads,
                            ),
                        )
                except Exception:
                    pass
                raise RuntimeLifecycleError("rollback_failed") from None
            if isinstance(error, RuntimeLifecycleError):
                raise
            raise RuntimeLifecycleError("bootstrap_failed") from None

    def _rollback_install(
        self,
        *,
        rendered: Mapping[str, bytes],
        existing: Mapping[str, bytes | None],
        old_manifest_payload: bytes | None,
        attempted_labels: Sequence[str],
        loaded_attempt: Sequence[str],
        installed_names: Sequence[str],
        booted_out_old: Sequence[str],
        originally_loaded: Sequence[str],
        installing_manifest: bytes,
        installed_manifest: bytes | None,
    ) -> bool:
        candidate_names = set(loaded_attempt)
        for name in attempted_labels:
            if name in candidate_names:
                continue
            try:
                state = self.system.launchctl_state(COMPONENTS[name].label)
            except Exception:
                return True
            if state.loaded:
                candidate_names.add(name)

        # Establish a global read-only snapshot before signalling even one
        # service.  A foreign listener or uncertain same-label process keeps
        # the installing manifest in place for manual recovery.
        live_candidates: list[str] = []
        try:
            for name, specification in COMPONENTS.items():
                state = self.system.launchctl_state(specification.label)
                listeners = self.system.listener_pids(specification.port)
                identity = (
                    self.system.process_identity(state.pid) if state.pid else None
                )
                ownership = classify_listener_ownership(
                    specification,
                    self.paths,
                    state=state,
                    listener_pids=listeners,
                    process_identity=identity,
                )
                if listeners and ownership != "owned":
                    return True
                if name not in candidate_names:
                    continue
                if not state.loaded:
                    continue
                payload = self.system.read_optional_private(self.paths.plists[name])
                if (
                    payload != rendered[name]
                    or not _launchctl_contract_matches(specification, self.paths, state)
                    or (
                        state.pid is not None
                        and (
                            identity is None
                            or not _process_identity_matches_expected(
                                specification,
                                self.paths,
                                identity,
                            )
                        )
                    )
                ):
                    return True
                live_candidates.append(name)
        except Exception:
            return True

        # Once an uncertain or foreign same-label process appears, rollback
        # becomes a fail-closed manual recovery.  It receives no bootout and
        # none of its backing files are changed.
        failed = False
        for name in reversed(live_candidates):
            try:
                state = self.system.launchctl_state(COMPONENTS[name].label)
                if not state.loaded:
                    continue
                payload = self.system.read_optional_private(self.paths.plists[name])
                if (
                    not _launchctl_contract_matches(COMPONENTS[name], self.paths, state)
                    or payload != rendered[name]
                ):
                    return True
                listeners = self.system.listener_pids(COMPONENTS[name].port)
                identity = (
                    self.system.process_identity(state.pid) if state.pid else None
                )
                if (
                    listeners
                    and classify_listener_ownership(
                        COMPONENTS[name],
                        self.paths,
                        state=state,
                        listener_pids=listeners,
                        process_identity=identity,
                    )
                    != "owned"
                ):
                    return True
                self.system.bootout(COMPONENTS[name].label)
                self.system.wait_until_port_clear(COMPONENTS[name].port)
            except Exception:
                return True
        for name in reversed(installed_names):
            try:
                current = self.system.read_optional_private(self.paths.plists[name])
                old = existing[name]
                if current == old:
                    continue
                if current != rendered[name]:
                    raise RuntimeLifecycleError("ownership_manifest_mismatch")
                if old is None:
                    self._remove_exact_intent(
                        self.paths.plists[name],
                        rendered[name],
                    )
                else:
                    self._install_plist_intent(
                        self.paths.plists[name],
                        old,
                        _digest(rendered[name]),
                    )
            except Exception:
                failed = True
        if booted_out_old and not failed:
            for name in reversed(booted_out_old):
                try:
                    old_payload = existing[name]
                    if old_payload is None:
                        raise RuntimeLifecycleError("ownership_manifest_mismatch")
                    self._prepare_exact_bootstrap(name, old_payload)
                    self.system.bootstrap(
                        COMPONENTS[name].label, self.paths.plists[name]
                    )
                    self.system.wait_for_owned(COMPONENTS[name], self.paths)
                except Exception:
                    failed = True
                    break
        if failed:
            return True
        try:
            self._restored_runtime_snapshot(existing, originally_loaded)
            current_manifest = self.system.read_optional_private(
                self.paths.ownership_metadata
            )
            known_transaction_manifests = {
                installing_manifest,
                old_manifest_payload,
            }
            if installed_manifest is not None:
                known_transaction_manifests.add(installed_manifest)
            if current_manifest not in known_transaction_manifests:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
            transaction_manifest_is_current = (
                current_manifest == installing_manifest
                or (
                    installed_manifest is not None
                    and current_manifest == installed_manifest
                )
            )
            if transaction_manifest_is_current:
                if old_manifest_payload is None:
                    if current_manifest is None:
                        raise RuntimeLifecycleError("ownership_manifest_mismatch")
                    self._remove_exact_intent(
                        self.paths.ownership_metadata,
                        current_manifest,
                    )
                else:
                    self._write_manifest_intent(old_manifest_payload)
        except Exception:
            return True
        return failed

    def uninstall(self) -> None:
        self.system.preflight_management(self.paths)
        for path in self.paths.plists.values():
            self.system.validate_installed_target(path)
        recovered = self._recover_interrupted_state()
        if recovered == "uninstalling":
            return
        existing, old_manifest_payload, manifest = self._read_existing()
        observations = self._inspect_targets(manifest, mutation=True)
        loaded = [name for name, value in observations.items() if value[0].loaded]
        if (
            not loaded
            and all(payload is None for payload in existing.values())
            and (manifest is None or manifest["state"] == "uninstalled")
        ):
            return
        self.system.prepare_management_metadata(self.paths)
        uninstalling_manifest = render_manifest(
            self.paths,
            state="uninstalling",
            installed={
                name: payload
                for name, payload in existing.items()
                if payload is not None
            },
            identities={
                name: value[2]
                for name, value in observations.items()
                if value[2] is not None
            },
        )
        stopped: list[str] = []
        try:
            self._write_manifest_intent(uninstalling_manifest)
            for name in reversed(loaded):
                current = self._inspect_targets(manifest, mutation=True)[name]
                if current[3] not in {"owned", "owned_inactive"}:
                    raise RuntimeLifecycleError("ownership_mismatch")
                self.system.bootout(COMPONENTS[name].label)
                stopped.append(name)
                self.system.wait_until_port_clear(COMPONENTS[name].port)
        except BaseException:
            restore_failed = False
            try:
                for name, path in self.paths.plists.items():
                    if self.system.read_optional_private(path) != existing[name]:
                        raise RuntimeLifecycleError("ownership_manifest_mismatch")
            except Exception:
                restore_failed = True
            for name in reversed(stopped) if not restore_failed else ():
                try:
                    payload = existing[name]
                    if payload is None:
                        raise RuntimeLifecycleError("ownership_manifest_mismatch")
                    self._prepare_exact_bootstrap(name, payload)
                    self.system.bootstrap(
                        COMPONENTS[name].label, self.paths.plists[name]
                    )
                    self.system.wait_for_owned(COMPONENTS[name], self.paths)
                except Exception:
                    restore_failed = True
                    break
            if not restore_failed:
                try:
                    self._restored_runtime_snapshot(existing, loaded)
                except Exception:
                    restore_failed = True
            if restore_failed:
                self._write_manifest_intent(
                    render_manifest(
                        self.paths,
                        state="rollback_required",
                        installed={
                            name: payload
                            for name, payload in existing.items()
                            if payload is not None
                        },
                        identities={
                            name: value[2]
                            for name, value in observations.items()
                            if value[2] is not None
                        },
                    ),
                )
            elif old_manifest_payload is not None:
                self._write_manifest_intent(old_manifest_payload)
            raise RuntimeLifecycleError("uninstall_failed") from None

        removal_attempts: list[str] = []
        try:
            for name, path in self.paths.plists.items():
                payload = existing[name]
                if payload is not None:
                    removal_attempts.append(name)
                    self.system.remove_exact_file(path, _digest(payload))
            self._uninstalled_commit_snapshot()
            self._write_manifest_intent(
                render_manifest(
                    self.paths,
                    state="uninstalled",
                    installed={},
                    identities={},
                ),
            )
        except BaseException:
            restore_failed = False
            for name in removal_attempts:
                payload = existing[name]
                if payload is not None:
                    try:
                        current_payload = self.system.read_optional_private(
                            self.paths.plists[name]
                        )
                        if current_payload == payload:
                            continue
                        if current_payload is not None:
                            restore_failed = True
                            continue
                        self._install_plist_intent(
                            self.paths.plists[name], payload, None
                        )
                    except Exception:
                        restore_failed = True
            try:
                for name, path in self.paths.plists.items():
                    if self.system.read_optional_private(path) != existing[name]:
                        restore_failed = True
            except Exception:
                restore_failed = True

            # Never launch from a path until all four original payloads have
            # been restored and re-read successfully.
            for name in loaded if not restore_failed else ():
                try:
                    payload = existing[name]
                    if payload is None:
                        raise RuntimeLifecycleError("ownership_manifest_mismatch")
                    self._prepare_exact_bootstrap(name, payload)
                    self.system.bootstrap(
                        COMPONENTS[name].label, self.paths.plists[name]
                    )
                    self.system.wait_for_owned(COMPONENTS[name], self.paths)
                except Exception:
                    restore_failed = True
                    break
            if not restore_failed:
                try:
                    self._restored_runtime_snapshot(existing, loaded)
                except Exception:
                    restore_failed = True
            if restore_failed:
                self._write_manifest_intent(
                    render_manifest(
                        self.paths,
                        state="rollback_required",
                        installed={
                            name: payload
                            for name, payload in existing.items()
                            if payload is not None
                        },
                        identities={
                            name: value[2]
                            for name, value in observations.items()
                            if value[2] is not None
                        },
                    ),
                )
            elif old_manifest_payload is not None:
                self._write_manifest_intent(old_manifest_payload)
            raise RuntimeLifecycleError("uninstall_failed") from None

    def status(self) -> OrderedDict[str, object]:
        verified_manifest_components: set[str] = set()
        try:
            manifest = _parse_manifest(
                self.system.read_optional_private(self.paths.ownership_metadata),
                self.paths,
            )
            if manifest is not None and manifest["state"] == "installed":
                manifest_components = cast(
                    Mapping[str, Mapping[str, object]],
                    manifest["components"],
                )
                for name, path in self.paths.plists.items():
                    payload = self.system.read_optional_private(path)
                    if payload is not None and manifest_components[name][
                        "plist_sha256"
                    ] == _digest(payload):
                        verified_manifest_components.add(name)
        except RuntimeLifecycleError:
            manifest = None
        rows = []
        for name, specification in COMPONENTS.items():
            try:
                state = self.system.launchctl_state(specification.label)
                listeners = self.system.listener_pids(specification.port)
                identity = (
                    self.system.process_identity(state.pid) if state.pid else None
                )
                ownership = classify_listener_ownership(
                    specification,
                    self.paths,
                    state=state,
                    listener_pids=listeners,
                    process_identity=identity,
                )
                if listeners and ownership != "owned":
                    rendered_state = "unknown_listener"
                elif state.loaded and state.pid is None:
                    rendered_state = "loaded_without_pid"
                elif (
                    state.loaded
                    and ownership == "owned"
                    and manifest is not None
                    and name in verified_manifest_components
                    and identity is not None
                    and manifest["components"][name]["executable"] == identity.executable  # type: ignore[index]
                    and manifest["components"][name]["cwd"] == identity.cwd  # type: ignore[index]
                    and manifest["components"][name]["command_fingerprint"] == identity.command_fingerprint  # type: ignore[index]
                ):
                    rendered_state = "running"
                elif state.loaded:
                    rendered_state = "unverified_runtime"
                else:
                    rendered_state = "stopped"
                pid = state.pid if rendered_state == "running" else None
                start_time = (
                    identity.start_time
                    if rendered_state == "running" and identity
                    else None
                )
            except Exception:
                rendered_state, pid, start_time = "indeterminate", None, None
            rows.append(
                OrderedDict(
                    (
                        ("component", name),
                        ("label", specification.label),
                        ("port", specification.port),
                        ("state", rendered_state),
                        ("pid", pid),
                        ("start_time", start_time),
                    )
                )
            )
        legacy = []
        for port in LEGACY_PORTS:
            try:
                pids = list(self.system.listener_pids(port))
                legacy.append(
                    OrderedDict(
                        (("port", port), ("listening", bool(pids)), ("pids", pids))
                    )
                )
            except Exception:
                legacy.append(
                    OrderedDict((("port", port), ("listening", None), ("pids", [])))
                )
        return OrderedDict((("components", rows), ("legacy", legacy)))

    def health(self) -> OrderedDict[str, object]:
        rows = []
        for name, specification in COMPONENTS.items():
            try:
                observation = self.system.http_observation(specification)
                reachable = observation.status is not None
                if specification.health_kind == "gateway":
                    healthy: bool | None = (
                        observation.status == 200 and observation.health_ok is True
                    )
                elif specification.health_kind == "bundler":
                    healthy = None
                else:
                    healthy = None
                protected = (
                    specification.health_kind == "protected"
                    and observation.status == specification.expected_http_status
                )
                error = observation.error
                if (
                    observation.status is not None
                    and observation.status != specification.expected_http_status
                ):
                    error = "unexpected_status"
            except Exception:
                observation = HttpObservation(None, "unreachable")
                reachable, healthy, protected, error = (
                    False,
                    False if specification.health_kind == "gateway" else None,
                    False,
                    "unreachable",
                )
            rows.append(
                OrderedDict(
                    (
                        ("component", name),
                        ("port", specification.port),
                        ("reachable", reachable),
                        ("protected", protected),
                        ("healthy", healthy),
                        ("http_status", observation.status),
                        ("error", error),
                    )
                )
            )
        return OrderedDict((("components", rows),))


class MacOSSystem:
    def __init__(self, paths: RuntimePaths) -> None:
        self.paths = paths
        self._command_environment = {"PATH": FIXED_PATH, "LC_ALL": "C"}

    @staticmethod
    def _exists(path: Path) -> bool:
        try:
            os.lstat(path)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def _run(
        self,
        command: Sequence[str],
        *,
        binary: bool = False,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess:
        if timeout is not None and timeout <= 0:
            raise RuntimeLifecycleError("command_failed")
        command_timeout = (
            _COMMAND_TIMEOUT_SECONDS
            if timeout is None
            else min(_COMMAND_TIMEOUT_SECONDS, timeout)
        )
        try:
            return subprocess.run(
                list(command),
                cwd=str(self.paths.repository),
                env=self._command_environment,
                capture_output=True,
                text=not binary,
                check=False,
                timeout=command_timeout,
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeLifecycleError("command_failed") from None

    def preflight_read_only(self, paths: RuntimePaths) -> None:
        try:
            validate_repository_identity(paths.repository)
            for directory in (
                paths.home,
                paths.home / "Library",
                paths.launch_agents,
                paths.repository,
            ):
                validate_runtime_directory_chain(directory)
            for private in (
                paths.runtime_root,
                paths.logs,
                paths.temporary,
                paths.state,
                paths.staging,
            ):
                if self._exists(private):
                    validate_runtime_directory_chain(private)
            validate_runtime_file(
                paths.environment_file,
                executable=False,
                required_mode=PRIVATE_FILE_MODE,
            )
            for executable in (LAUNCHCTL, LSOF, PLUTIL, PS):
                validate_runtime_file(executable, executable=True)
            validate_runtime_file(paths.ca_bundle, executable=False)
            validate_runtime_file(
                paths.repository / "scripts/local_runtime.py", executable=False
            )
            validate_runtime_file(
                paths.repository / "scripts/local_runtime_launch.py", executable=False
            )
            validate_runtime_file(
                paths.repository / "apps/mobile/node_modules/expo/bin/cli",
                executable=False,
            )
            validate_runtime_file(
                paths.repository / "apps/mobile/package.json", executable=False
            )
            market_python = (
                paths.repository / "services/market_gateway/.venv/bin/python"
            )
            validate_runtime_file(
                market_python,
                executable=True,
                allowed_symlinks=(market_python, market_python.parent / "python3.11"),
                trusted_external=True,
            )
            validate_runtime_file(
                NODE_22_EXECUTABLE,
                executable=True,
                allowed_symlinks=(Path("/opt/homebrew/opt/node@22"),),
                trusted_external=True,
            )
        except (RuntimeConfigurationError, OSError):
            raise RuntimeLifecycleError("unsafe_path") from None

    def preflight_management(self, paths: RuntimePaths) -> None:
        try:
            for directory in (
                paths.home,
                paths.home / "Library",
                paths.launch_agents,
            ):
                validate_runtime_directory_chain(directory)
            for executable in (LAUNCHCTL, LSOF, PS):
                validate_runtime_file(executable, executable=True)
            if self._exists(paths.runtime_root):
                validate_runtime_directory_chain(paths.runtime_root)
            if self._exists(paths.ownership_metadata):
                validate_runtime_file(
                    paths.ownership_metadata,
                    executable=False,
                    required_mode=PRIVATE_FILE_MODE,
                )
        except (RuntimeConfigurationError, OSError):
            raise RuntimeLifecycleError("unsafe_path") from None

    def validate_installed_target(self, path: Path) -> None:
        try:
            validate_runtime_directory_chain(path.parent)
            if self._exists(path):
                validate_runtime_file(
                    path, executable=False, required_mode=PRIVATE_FILE_MODE
                )
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def prepare_private_paths(self, paths: RuntimePaths) -> None:
        try:
            for directory in (
                paths.runtime_root,
                paths.logs,
                paths.temporary,
                paths.state,
                paths.staging,
            ):
                ensure_private_directory(directory)
            # Validate, but never print or rewrite, the operator's current env.
            parse_runtime_environment(paths.environment_file)
            if self._exists(paths.device_database):
                ensure_private_file(paths.device_database)
            for name in COMPONENTS:
                for suffix in ("stdout", "stderr"):
                    ensure_private_file(paths.logs / f"{name}.{suffix}.log")
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def prepare_management_metadata(self, paths: RuntimePaths) -> None:
        try:
            ensure_private_directory(paths.runtime_root)
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def validate_component_launches(self, paths: RuntimePaths) -> None:
        try:
            for name in COMPONENTS:
                prepare_launch(
                    name,
                    repository=paths.repository,
                    home=paths.home,
                    environment_file=(
                        paths.environment_file
                        if name in {"market-lan", "analysis-api"}
                        else None
                    ),
                    temporary_directory=paths.temporary,
                    ca_bundle=paths.ca_bundle if name != "metro" else None,
                )
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def render_plist(self, component: str, paths: RuntimePaths) -> bytes:
        try:
            return render_launch_agent(
                component,
                repository=paths.repository,
                home=paths.home,
                environment_file=paths.environment_file,
                temporary_directory=paths.temporary,
                log_directory=paths.logs,
                ca_bundle=paths.ca_bundle,
            )
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("invalid_plist") from None

    def write_private(self, path: Path, payload: bytes) -> None:
        try:
            atomic_write_private_file(path, payload)
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("unsafe_path") from None

    def confirm_private_write(self, path: Path, payload: bytes) -> None:
        descriptor: int | None = None
        try:
            if self.read_optional_private(path) != payload:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_DIRECTORY", 0)
            )
            descriptor = os.open(path.parent, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != PRIVATE_DIRECTORY_MODE
            ):
                raise RuntimeLifecycleError("unsafe_path")
            os.fsync(descriptor)
            if self.read_optional_private(path) != payload:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        except OSError:
            raise RuntimeLifecycleError("command_failed") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _confirm_trusted_state(
        self,
        path: Path,
        expected: bytes | None,
    ) -> None:
        descriptor: int | None = None
        try:
            if self.read_optional_private(path) != expected:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_DIRECTORY", 0)
            )
            descriptor = os.open(path.parent, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RuntimeLifecycleError("unsafe_path")
            os.fsync(descriptor)
            if self.read_optional_private(path) != expected:
                raise RuntimeLifecycleError("ownership_manifest_mismatch")
        except OSError:
            raise RuntimeLifecycleError("command_failed") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def confirm_trusted_write(self, path: Path, payload: bytes) -> None:
        self._confirm_trusted_state(path, payload)

    def confirm_file_absence(self, path: Path) -> None:
        self._confirm_trusted_state(path, None)

    def install_plist(
        self, path: Path, payload: bytes, expected_digest: str | None
    ) -> None:
        try:
            atomic_write_trusted_file(
                path, payload, expected_existing_digest=expected_digest
            )
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("ownership_manifest_mismatch") from None

    def validate_staged_plist(self, path: Path, label: str) -> None:
        try:
            validate_runtime_file(
                path, executable=False, required_mode=PRIVATE_FILE_MODE
            )
            document = plistlib.loads(path.read_bytes())
        except (
            RuntimeConfigurationError,
            OSError,
            ValueError,
            plistlib.InvalidFileException,
        ):
            raise RuntimeLifecycleError("invalid_plist") from None
        if document.get("Label") != label:
            raise RuntimeLifecycleError("invalid_plist")
        result = self._run((str(PLUTIL), "-lint", str(path)))
        if result.returncode != 0:
            raise RuntimeLifecycleError("invalid_plist")

    def read_optional_private(self, path: Path) -> bytes | None:
        if not self._exists(path):
            return None
        try:
            validate_runtime_file(
                path, executable=False, required_mode=PRIVATE_FILE_MODE
            )
            flags = (
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(path, flags)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 256 * 1024:
                    raise RuntimeLifecycleError("unsafe_path")
                chunks: list[bytes] = []
                while True:
                    chunk = os.read(descriptor, 64 * 1024)
                    if not chunk:
                        return b"".join(chunks)
                    chunks.append(chunk)
            finally:
                os.close(descriptor)
        except (OSError, RuntimeConfigurationError):
            raise RuntimeLifecycleError("unsafe_path") from None

    def remove_exact_file(self, path: Path, expected_digest: str | None = None) -> None:
        payload = self.read_optional_private(path)
        if payload is None:
            return
        observed_digest = _digest(payload)
        if expected_digest is not None and observed_digest != expected_digest:
            raise RuntimeLifecycleError("ownership_manifest_mismatch")
        try:
            quarantine_trusted_file(
                path,
                expected_existing_digest=(
                    expected_digest if expected_digest is not None else observed_digest
                ),
            )
        except RuntimeConfigurationError:
            raise RuntimeLifecycleError("ownership_manifest_mismatch") from None

    def _domain(self, label: str) -> str:
        return f"gui/{os.geteuid()}/{label}"

    def launchctl_state(
        self, label: str, *, timeout: float | None = None
    ) -> LaunchctlState:
        domain = self._domain(label)
        result = self._run((str(LAUNCHCTL), "print", domain), timeout=timeout)
        if result.returncode != 0:
            not_found = (
                "Bad request.\n"
                f'Could not find service "{label}" in domain for user gui: '
                f"{os.geteuid()}\n"
            )
            if result.stdout == "" and result.stderr == not_found:
                return LaunchctlState(False, None)
            raise RuntimeLifecycleError("command_failed")
        return parse_launchctl_print(result.stdout, expected_domain=domain)

    def listener_pids(
        self, port: int, *, timeout: float | None = None
    ) -> tuple[int, ...]:
        if port not in {spec.port for spec in COMPONENTS.values()} | set(LEGACY_PORTS):
            raise RuntimeLifecycleError("command_failed")
        result = self._run(
            (str(LSOF), "-nP", "-a", f"-iTCP:{port}", "-sTCP:LISTEN", "-F0pfnT"),
            binary=True,
            timeout=timeout,
        )
        if result.returncode == 1 and not result.stdout and not result.stderr:
            return ()
        if result.returncode != 0:
            raise RuntimeLifecycleError("command_failed")
        return parse_lsof_pids(result.stdout, expected_port=port)

    def process_identity(
        self,
        pid: int,
        *,
        deadline: float | None = None,
    ) -> ProcessIdentity | None:
        if type(pid) is not int or pid <= 0:
            raise RuntimeLifecycleError("command_failed")

        def remaining_timeout() -> float | None:
            if deadline is None:
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeLifecycleError("command_failed")
            return remaining

        def ps_value(field: str, *, wide: bool = False) -> str:
            command = [str(PS)]
            if wide:
                command.append("-ww")
            command.extend(("-p", str(pid), "-o", f"{field}="))
            result = self._run(command, timeout=remaining_timeout())
            if result.returncode != 0:
                return ""
            value = result.stdout.rstrip("\n")
            if not value or "\n" in value:
                raise RuntimeLifecycleError("malformed_tool_output")
            return value.strip() if field != "command" else value.lstrip()

        executable = ps_value("comm", wide=True)
        if not executable:
            return None
        start_time = ps_value("lstart")
        command = ps_value("command", wide=True)
        cwd_result = self._run(
            (str(LSOF), "-nP", "-a", "-p", str(pid), "-d", "cwd", "-F0pn"),
            binary=True,
            timeout=remaining_timeout(),
        )
        if cwd_result.returncode != 0:
            raise RuntimeLifecycleError("malformed_tool_output")
        fields = [
            field.strip(b"\r\n")
            for field in cwd_result.stdout.split(b"\0")
            if field.strip(b"\r\n")
        ]
        paths = [field[1:].decode("utf-8") for field in fields if field[:1] == b"n"]
        pids = [field[1:] for field in fields if field[:1] == b"p"]
        if len(paths) != 1 or pids != [str(pid).encode("ascii")]:
            raise RuntimeLifecycleError("malformed_tool_output")
        if not _START_TIME_PATTERN.fullmatch(start_time):
            raise RuntimeLifecycleError("malformed_tool_output")
        return ProcessIdentity(
            pid,
            start_time,
            executable,
            paths[0],
            hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )

    def wait_until_port_clear(self, port: int) -> None:
        deadline = time.monotonic() + _PORT_CLEAR_TIMEOUT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not self.listener_pids(port, timeout=remaining):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        raise RuntimeLifecycleError("unknown_target_listener")

    def wait_for_owned(
        self,
        specification: ComponentRuntime,
        paths: RuntimePaths,
    ) -> ProcessIdentity:
        deadline = time.monotonic() + _OWNERSHIP_WAIT_TIMEOUT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                state = self.launchctl_state(
                    specification.label,
                    timeout=remaining,
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                listeners = self.listener_pids(
                    specification.port,
                    timeout=remaining,
                )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                identity = (
                    self.process_identity(state.pid, deadline=deadline)
                    if state.pid
                    else None
                )
                if (
                    classify_listener_ownership(
                        specification,
                        paths,
                        state=state,
                        listener_pids=listeners,
                        process_identity=identity,
                    )
                    == "owned"
                ):
                    return identity  # type: ignore[return-value]
                if listeners and (
                    not _launchctl_contract_matches(specification, paths, state)
                    or state.pid is None
                    or tuple(listeners) != (state.pid,)
                ):
                    raise RuntimeLifecycleError("unknown_target_listener")
            except RuntimeLifecycleError as error:
                if error.code in {
                    "unknown_target_listener",
                    "command_failed",
                    "malformed_tool_output",
                }:
                    raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        raise RuntimeLifecycleError("bootstrap_failed")

    def bootstrap(self, label: str, path: Path) -> None:
        result = self._run(
            (str(LAUNCHCTL), "bootstrap", f"gui/{os.geteuid()}", str(path))
        )
        if result.returncode != 0:
            raise RuntimeLifecycleError("bootstrap_failed")

    def bootout(self, label: str) -> None:
        deadline = time.monotonic() + _BOOTOUT_TIMEOUT_SECONDS
        result = self._run(
            (str(LAUNCHCTL), "bootout", self._domain(label)),
            timeout=deadline - time.monotonic(),
        )
        if result.returncode != 0:
            raise RuntimeLifecycleError("command_failed")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not self.launchctl_state(label, timeout=remaining).loaded:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        raise RuntimeLifecycleError("command_failed")

    def http_observation(self, specification: ComponentRuntime) -> HttpObservation:
        return bounded_http_observation(specification)


def build_default_controller() -> RuntimeController:
    paths = RuntimePaths.default()
    return RuntimeController(paths, MacOSSystem(paths))


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("command", nargs="?")
    parser.add_argument("--json", action="store_true", dest="json_output")
    try:
        arguments, extras = parser.parse_known_args(argv)
    except argparse.ArgumentError:
        raise RuntimeLifecycleError("command_failed") from None
    if (
        arguments.command
        not in {"install", "status", "health", "reinstall", "uninstall"}
        or extras
    ):
        raise RuntimeLifecycleError("command_failed")
    if arguments.json_output and arguments.command not in {"status", "health"}:
        raise RuntimeLifecycleError("command_failed")
    return arguments


def _print_human(command: str, result: Mapping[str, object] | None) -> None:
    if command in {"install", "reinstall", "uninstall"}:
        print(f"local runtime {command} complete")
        return
    assert result is not None
    components = cast(list[Mapping[str, object]], result["components"])
    for row in components:
        if command == "status":
            print(f"{row['component']} port={row['port']} state={row['state']}")
        else:
            print(
                f"{row['component']} port={row['port']} reachable={str(row['reachable']).lower()} "
                f"healthy={str(row['healthy']).lower()} status={row['http_status'] or '-'}"
            )
    if command == "status":
        legacy = cast(list[Mapping[str, object]], result["legacy"])
        for row in legacy:
            print(
                f"legacy port={row['port']} listening={str(row['listening']).lower()}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parse_arguments(argv)
        controller = build_default_controller()
        result = None
        if arguments.command in {"install", "reinstall", "uninstall"}:
            validate_runtime_directory_chain(controller.paths.launch_agents)
            with runtime_command_lock(controller.paths.launch_agents):
                with _transaction_signal_guard():
                    if arguments.command == "install":
                        controller.install()
                    elif arguments.command == "reinstall":
                        controller.reinstall()
                    else:
                        controller.uninstall()
        elif arguments.command == "status":
            result = controller.status()
        else:
            result = controller.health()
        if arguments.json_output:
            print(
                json.dumps(
                    result, ensure_ascii=True, sort_keys=True, separators=(",", ":")
                )
            )
        else:
            _print_human(arguments.command, result)
        return 0
    except BaseException:
        print("local runtime command failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
