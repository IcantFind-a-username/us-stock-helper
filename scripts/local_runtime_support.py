"""Shared, secret-safe primitives for the durable local development runtime.

The environment parser deliberately understands less than a shell.  Runtime
credentials are data, never code, and component environments are assembled
from fixed allowlists instead of inheriting the launcher's environment.
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, NoReturn, Sequence


PathLike = str | os.PathLike[str]

PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
FIXED_PATH = (
    "/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:" "/usr/bin:/bin:/usr/sbin:/sbin"
)

RUNTIME_ENVIRONMENT_KEYS = frozenset(
    {
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
)

_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_SHELL_METACHARACTERS = frozenset("'\"`$;|&<>\\(){}*?!~#")


class RuntimeConfigurationError(ValueError):
    """A public, sanitized runtime configuration failure."""


@dataclass(frozen=True, slots=True)
class FileSystemRunner:
    """Injectable standard-library filesystem boundary."""

    lstat: Callable[[PathLike], os.stat_result]
    open_fd: Callable[..., int]
    fstat: Callable[[int], os.stat_result]
    read_fd: Callable[[int, int], bytes]
    write_fd: Callable[[int, bytes], int]
    fsync: Callable[[int], None]
    fchmod: Callable[[int, int], None]
    close_fd: Callable[[int], None]
    mkdir: Callable[[PathLike, int], None]
    chmod: Callable[[PathLike, int], None]
    replace: Callable[[PathLike, PathLike], None]
    unlink: Callable[[PathLike], None]
    mkstemp: Callable[..., tuple[int, str]]
    geteuid: Callable[[], int]
    has_extended_acl: Callable[[int], bool]
    clear_extended_acl: Callable[[int], None]


@dataclass(frozen=True, slots=True)
class ProcessRunner:
    """Injectable process boundary used by the absolute launcher and CLI."""

    execve: Callable[[str, Sequence[str], Mapping[str, str]], NoReturn]
    run: Callable[..., subprocess.CompletedProcess[str]]


def _load_acl_library() -> ctypes.CDLL | None:
    if sys.platform != "darwin":
        return None
    try:
        library = ctypes.CDLL(None, use_errno=True)
        library.acl_get_fd.argtypes = [ctypes.c_int]
        library.acl_get_fd.restype = ctypes.c_void_p
        library.acl_init.argtypes = [ctypes.c_int]
        library.acl_init.restype = ctypes.c_void_p
        library.acl_set_fd.argtypes = [ctypes.c_int, ctypes.c_void_p]
        library.acl_set_fd.restype = ctypes.c_int
        library.acl_free.argtypes = [ctypes.c_void_p]
        library.acl_free.restype = ctypes.c_int
    except (AttributeError, OSError):
        return None
    return library


_LIBC = _load_acl_library()


def _require_acl_library() -> ctypes.CDLL:
    if _LIBC is None:
        raise OSError(errno.ENOTSUP, "extended ACL operations are unavailable")
    return _LIBC


def _has_extended_acl(descriptor: int) -> bool:
    library = _require_acl_library()
    ctypes.set_errno(0)
    acl = library.acl_get_fd(descriptor)
    if not acl:
        error_number = ctypes.get_errno()
        if error_number == errno.ENOENT:
            return False
        raise OSError(error_number, "extended ACL could not be read")
    try:
        return True
    finally:
        if library.acl_free(acl) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, "extended ACL could not be released")


def _clear_extended_acl(descriptor: int) -> None:
    library = _require_acl_library()
    ctypes.set_errno(0)
    empty_acl = library.acl_init(1)
    if not empty_acl:
        error_number = ctypes.get_errno()
        raise OSError(error_number, "empty ACL could not be allocated")
    try:
        if library.acl_set_fd(descriptor, empty_acl) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, "extended ACL could not be cleared")
    finally:
        if library.acl_free(empty_acl) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, "empty ACL could not be released")


DEFAULT_FILE_SYSTEM = FileSystemRunner(
    lstat=os.lstat,
    open_fd=os.open,
    fstat=os.fstat,
    read_fd=os.read,
    write_fd=os.write,
    fsync=os.fsync,
    fchmod=os.fchmod,
    close_fd=os.close,
    mkdir=os.mkdir,
    chmod=os.chmod,
    replace=os.replace,
    unlink=os.unlink,
    mkstemp=tempfile.mkstemp,
    geteuid=os.geteuid,
    has_extended_acl=_has_extended_acl,
    clear_extended_acl=_clear_extended_acl,
)
DEFAULT_PROCESS_RUNNER = ProcessRunner(execve=os.execve, run=subprocess.run)


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    name: str
    copied_keys: frozenset[str]
    required_keys: frozenset[str]
    fixed_environment: Mapping[str, str]
    python_paths: tuple[str, ...]


def _component_spec(
    name: str,
    *,
    copied_keys: Sequence[str] = (),
    required_keys: Sequence[str] = (),
    fixed_environment: Mapping[str, str] | None = None,
    python_paths: Sequence[str] = (),
) -> ComponentSpec:
    return ComponentSpec(
        name=name,
        copied_keys=frozenset(copied_keys),
        required_keys=frozenset(required_keys),
        fixed_environment=MappingProxyType(dict(fixed_environment or {})),
        python_paths=tuple(python_paths),
    )


COMPONENT_SPECS: Mapping[str, ComponentSpec] = MappingProxyType(
    {
        "market-loopback": _component_spec(
            "market-loopback",
            fixed_environment={
                "MOOMOO_GATEWAY_HOST": "127.0.0.1",
                "MOOMOO_GATEWAY_PORT": "8765",
            },
            python_paths=(
                "services/market_gateway/src",
                "services/analysis_core",
            ),
        ),
        "market-lan": _component_spec(
            "market-lan",
            copied_keys=(
                "MOOMOO_GATEWAY_ALLOWED_CLIENTS",
                "MOOMOO_GATEWAY_TOKEN",
            ),
            required_keys=(
                "MOOMOO_GATEWAY_ALLOWED_CLIENTS",
                "MOOMOO_GATEWAY_TOKEN",
            ),
            fixed_environment={
                "MOOMOO_GATEWAY_ALLOW_LAN": "1",
                "MOOMOO_GATEWAY_HOST": "0.0.0.0",
                "MOOMOO_GATEWAY_PORT": "8766",
            },
            python_paths=(
                "services/market_gateway/src",
                "services/analysis_core",
            ),
        ),
        "analysis-api": _component_spec(
            "analysis-api",
            copied_keys=(
                "ANALYSIS_API_ALLOWED_CLIENTS",
                "ANTHROPIC_API_KEY",
                "US_STOCK_HELPER_CONTACT_EMAIL",
            ),
            required_keys=(
                "ANALYSIS_API_ALLOWED_CLIENTS",
                "US_STOCK_HELPER_CONTACT_EMAIL",
            ),
            fixed_environment={
                "ANALYSIS_API_ALLOW_LAN": "1",
                "ANALYSIS_API_GATEWAY_URL": "http://127.0.0.1:8765",
                "ANALYSIS_API_HOST": "0.0.0.0",
                "ANALYSIS_API_PORT": "8770",
            },
            python_paths=(
                "services/analysis_api/src",
                "services/analysis_core",
                "services/information_layer",
                "services/adviser_layer",
                "services/decision_engine",
                "services/device_auth/src",
                "services/adviser_llm/src",
            ),
        ),
        "metro": _component_spec(
            "metro",
            fixed_environment={"EXPO_PUBLIC_INITIAL_DEMO_MODE": "false"},
        ),
    }
)


def parse_runtime_environment(
    path: PathLike,
    *,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> dict[str, str]:
    """Parse a private UTF-8 ``KEY=VALUE`` file without shell semantics."""

    environment_path = Path(path)
    _require_private_directory(environment_path.parent, filesystem=filesystem)

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = filesystem.open_fd(environment_path, flags)
    except OSError:
        raise RuntimeConfigurationError("runtime environment is unavailable") from None
    try:
        metadata = filesystem.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeConfigurationError(
                "runtime environment must be a regular file"
            )
        if metadata.st_uid != filesystem.geteuid():
            raise RuntimeConfigurationError(
                "runtime environment must be owned by the current user"
            )
        if stat.S_IMODE(metadata.st_mode) != PRIVATE_FILE_MODE:
            raise RuntimeConfigurationError("runtime environment mode must be 0600")
        if filesystem.has_extended_acl(descriptor):
            raise RuntimeConfigurationError(
                "runtime environment must not have an extended ACL"
            )
        content = _read_all(descriptor, filesystem=filesystem)
    except OSError:
        raise RuntimeConfigurationError(
            "runtime environment could not be read"
        ) from None
    finally:
        filesystem.close_fd(descriptor)

    return _parse_assignments(content)


def _parse_assignments(content: bytes) -> dict[str, str]:
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise RuntimeConfigurationError("runtime environment must be UTF-8") from None

    if any(
        unicodedata.category(character) == "Cc" and character != "\n"
        for character in text
    ):
        raise RuntimeConfigurationError("runtime environment contains control data")

    parsed: dict[str, str] = {}
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line.strip(" ") or line.lstrip(" ").startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeConfigurationError(
                f"runtime environment line {line_number} is not an assignment"
            )
        key, value = line.split("=", 1)
        if not _KEY_PATTERN.fullmatch(key) or key not in RUNTIME_ENVIRONMENT_KEYS:
            raise RuntimeConfigurationError(
                f"runtime environment line {line_number} has an invalid key"
            )
        if key in parsed:
            raise RuntimeConfigurationError(
                f"runtime environment line {line_number} duplicates a key"
            )
        if value != value.strip() or any(character.isspace() for character in value):
            raise RuntimeConfigurationError(
                f"runtime environment line {line_number} contains shell syntax"
            )
        if any(character in _SHELL_METACHARACTERS for character in value):
            raise RuntimeConfigurationError(
                f"runtime environment line {line_number} contains shell syntax"
            )
        parsed[key] = value
    return parsed


def build_component_environment(
    component: str,
    parsed_environment: Mapping[str, str],
    *,
    repository: PathLike,
    home: PathLike,
    temporary_directory: PathLike,
    ca_bundle: PathLike,
) -> dict[str, str]:
    """Build one fixed environment without consulting or mutating ``os.environ``."""

    spec = COMPONENT_SPECS.get(component)
    if spec is None:
        raise RuntimeConfigurationError("unknown runtime component")
    if not set(parsed_environment).issubset(RUNTIME_ENVIRONMENT_KEYS):
        raise RuntimeConfigurationError("runtime environment contains an unknown key")

    repository_path = _absolute_path(repository, "repository")
    home_path = _absolute_path(home, "home")
    temporary_path = _absolute_path(temporary_directory, "temporary directory")
    ca_path = _absolute_path(ca_bundle, "CA bundle")

    for key in spec.required_keys:
        if not parsed_environment.get(key):
            raise RuntimeConfigurationError(f"runtime environment is missing {key}")

    environment = {
        "HOME": str(home_path),
        "PATH": FIXED_PATH,
        "TMPDIR": str(temporary_path),
    }
    if spec.python_paths:
        environment.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    str(repository_path / relative) for relative in spec.python_paths
                ),
                "PYTHONUNBUFFERED": "1",
                "REQUESTS_CA_BUNDLE": str(ca_path),
                "SSL_CERT_FILE": str(ca_path),
            }
        )
    for key in spec.copied_keys:
        value = parsed_environment.get(key)
        if value:
            environment[key] = value
    environment.update(spec.fixed_environment)
    if component == "analysis-api":
        environment["DEVICE_AUTH_DATABASE"] = str(
            home_path / ".us-stock-helper/state/devices.sqlite3"
        )
    return environment


def ensure_private_directory(
    path: PathLike,
    *,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> None:
    """Create a directory if absent and leave it at exactly ``0700``."""

    directory = Path(path)
    try:
        filesystem.lstat(directory)
    except FileNotFoundError:
        try:
            filesystem.mkdir(directory, PRIVATE_DIRECTORY_MODE)
        except OSError:
            raise RuntimeConfigurationError(
                "private directory could not be created"
            ) from None
    except OSError:
        raise RuntimeConfigurationError("private directory is unavailable") from None
    descriptor: int | None = None
    try:
        descriptor = _open_directory_descriptor(directory, filesystem=filesystem)
        _repair_private_descriptor(
            descriptor,
            expected="directory",
            mode=PRIVATE_DIRECTORY_MODE,
            filesystem=filesystem,
        )
    except OSError:
        raise RuntimeConfigurationError(
            "private directory mode could not be set"
        ) from None
    finally:
        if descriptor is not None:
            filesystem.close_fd(descriptor)


def ensure_private_file(
    path: PathLike,
    *,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> None:
    """Atomically create a regular file if absent and leave it at ``0600``."""

    file_path = Path(path)
    _prepare_private_parent(file_path.parent, filesystem=filesystem)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = filesystem.open_fd(file_path, flags, PRIVATE_FILE_MODE)
    except OSError:
        raise RuntimeConfigurationError("private file could not be opened") from None
    try:
        _repair_private_descriptor(
            descriptor,
            expected="file",
            mode=PRIVATE_FILE_MODE,
            filesystem=filesystem,
        )
    except OSError:
        raise RuntimeConfigurationError("private file mode could not be set") from None
    finally:
        filesystem.close_fd(descriptor)


def atomic_write_private_file(
    path: PathLike,
    content: bytes,
    *,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> None:
    """Replace a private regular file atomically without rendering its content."""

    file_path = Path(path)
    _prepare_private_parent(file_path.parent, filesystem=filesystem)
    try:
        filesystem.lstat(file_path)
    except FileNotFoundError:
        pass
    except OSError:
        raise RuntimeConfigurationError("private file is unavailable") from None
    else:
        _repair_existing_private_file(file_path, filesystem=filesystem)

    descriptor: int | None = None
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = filesystem.mkstemp(
            prefix=f".{file_path.name}.", dir=str(file_path.parent)
        )
        _repair_private_descriptor(
            descriptor,
            expected="file",
            mode=PRIVATE_FILE_MODE,
            filesystem=filesystem,
        )
        remaining = memoryview(content)
        while remaining:
            written = filesystem.write_fd(descriptor, remaining)
            if written <= 0:
                raise OSError("short private file write")
            remaining = remaining[written:]
        filesystem.fsync(descriptor)
        filesystem.replace(temporary_name, file_path)
        temporary_name = None
        _validate_private_descriptor(
            descriptor,
            expected="file",
            mode=PRIVATE_FILE_MODE,
            filesystem=filesystem,
        )
    except (OSError, TypeError, ValueError):
        raise RuntimeConfigurationError("private file could not be written") from None
    finally:
        if descriptor is not None:
            try:
                filesystem.close_fd(descriptor)
            except OSError:
                pass
        if temporary_name is not None:
            try:
                filesystem.unlink(temporary_name)
            except OSError:
                pass


def _read_all(
    descriptor: int,
    *,
    filesystem: FileSystemRunner,
) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = filesystem.read_fd(descriptor, 64 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _require_private_directory(
    path: PathLike,
    *,
    filesystem: FileSystemRunner,
) -> None:
    descriptor: int | None = None
    try:
        descriptor = _open_directory_descriptor(path, filesystem=filesystem)
        _validate_private_descriptor(
            descriptor,
            expected="directory",
            mode=PRIVATE_DIRECTORY_MODE,
            filesystem=filesystem,
        )
    except OSError:
        raise RuntimeConfigurationError("private directory is unavailable") from None
    finally:
        if descriptor is not None:
            filesystem.close_fd(descriptor)


def _prepare_private_parent(
    path: PathLike,
    *,
    filesystem: FileSystemRunner,
) -> None:
    """Validate a private parent and remove only inherited ACL access."""

    descriptor: int | None = None
    try:
        descriptor = _open_directory_descriptor(path, filesystem=filesystem)
        _repair_private_descriptor(
            descriptor,
            expected="directory",
            mode=PRIVATE_DIRECTORY_MODE,
            filesystem=filesystem,
            require_current_mode=True,
        )
    except OSError:
        raise RuntimeConfigurationError("private directory is unavailable") from None
    finally:
        if descriptor is not None:
            filesystem.close_fd(descriptor)


def _repair_existing_private_file(
    path: PathLike,
    *,
    filesystem: FileSystemRunner,
) -> None:
    flags = (
        os.O_WRONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = filesystem.open_fd(path, flags)
    except OSError:
        raise RuntimeConfigurationError("private file is unavailable") from None
    try:
        _repair_private_descriptor(
            descriptor,
            expected="file",
            mode=PRIVATE_FILE_MODE,
            filesystem=filesystem,
        )
    except OSError:
        raise RuntimeConfigurationError("private file is unavailable") from None
    finally:
        filesystem.close_fd(descriptor)


def _open_directory_descriptor(
    path: PathLike,
    *,
    filesystem: FileSystemRunner,
) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    return filesystem.open_fd(path, flags)


def _require_owned_descriptor(
    descriptor: int,
    *,
    expected: str,
    filesystem: FileSystemRunner,
) -> os.stat_result:
    metadata = filesystem.fstat(descriptor)
    if expected == "directory":
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeConfigurationError("private path must be a directory")
    elif not stat.S_ISREG(metadata.st_mode):
        raise RuntimeConfigurationError("private path must be a regular file")
    if metadata.st_uid != filesystem.geteuid():
        raise RuntimeConfigurationError(
            "private path must be owned by the current user"
        )
    return metadata


def _validate_private_descriptor(
    descriptor: int,
    *,
    expected: str,
    mode: int,
    filesystem: FileSystemRunner,
) -> None:
    metadata = _require_owned_descriptor(
        descriptor,
        expected=expected,
        filesystem=filesystem,
    )
    if stat.S_IMODE(metadata.st_mode) != mode:
        rendered_mode = "0700" if expected == "directory" else "0600"
        raise RuntimeConfigurationError(
            f"private {expected} mode must be {rendered_mode}"
        )
    if filesystem.has_extended_acl(descriptor):
        raise RuntimeConfigurationError(
            f"private {expected} must not have an extended ACL"
        )


def _repair_private_descriptor(
    descriptor: int,
    *,
    expected: str,
    mode: int,
    filesystem: FileSystemRunner,
    require_current_mode: bool = False,
) -> None:
    metadata = _require_owned_descriptor(
        descriptor,
        expected=expected,
        filesystem=filesystem,
    )
    if require_current_mode and stat.S_IMODE(metadata.st_mode) != mode:
        rendered_mode = "0700" if expected == "directory" else "0600"
        raise RuntimeConfigurationError(
            f"private {expected} mode must be {rendered_mode}"
        )
    filesystem.fchmod(descriptor, mode)
    filesystem.clear_extended_acl(descriptor)
    _validate_private_descriptor(
        descriptor,
        expected=expected,
        mode=mode,
        filesystem=filesystem,
    )


def _absolute_path(path: PathLike, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RuntimeConfigurationError(f"{label} path must be absolute")
    return candidate
