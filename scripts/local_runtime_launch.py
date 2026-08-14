#!/usr/bin/env python3
"""Render and execute the four fixed local LaunchAgent components."""

from __future__ import annotations

import argparse
import errno
import grp
import os
import plistlib
import pwd
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NoReturn, Sequence

if __package__:
    from .local_runtime_support import (
        DEFAULT_FILE_SYSTEM,
        DEFAULT_PROCESS_RUNNER,
        COMPONENT_SPECS,
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        FileSystemRunner,
        ProcessRunner,
        RuntimeConfigurationError,
        build_component_environment,
        directory_acl_is_absent_or_protective,
        parse_runtime_environment,
    )
else:
    from local_runtime_support import (  # type: ignore[no-redef]
        DEFAULT_FILE_SYSTEM,
        DEFAULT_PROCESS_RUNNER,
        COMPONENT_SPECS,
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        FileSystemRunner,
        ProcessRunner,
        RuntimeConfigurationError,
        build_component_environment,
        directory_acl_is_absent_or_protective,
        parse_runtime_environment,
    )


EXPECTED_BRANCH = "feature/iphone-demo"
GIT_EXECUTABLE = Path("/usr/bin/git")
NODE_22_EXECUTABLE = Path("/opt/homebrew/opt/node@22/bin/node")
LAUNCH_THROTTLE_SECONDS = 10
_DARWIN_O_EXEC = 0x40000000
_DARWIN_O_SYMLINK = 0x00200000
_MAX_SYMLINK_HOPS = 8
_HOMEBREW_GROUP_WRITABLE_DIRECTORIES = frozenset(
    {Path("/opt/homebrew/opt"), Path("/opt/homebrew/Cellar")}
)
_PYTHON_GROUP_WRITABLE_PATHS = frozenset(
    {
        Path("/Library/Frameworks/Python.framework/Versions"),
        Path("/Library/Frameworks/Python.framework/Versions/3.11"),
        Path("/Library/Frameworks/Python.framework/Versions/3.11/bin"),
        Path("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"),
    }
)

COMPONENT_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "market-loopback": "com.franz.us-stock-helper.market-loopback",
        "market-lan": "com.franz.us-stock-helper.market-lan",
        "analysis-api": "com.franz.us-stock-helper.analysis-api",
        "metro": "com.franz.us-stock-helper.metro",
    }
)
SECRET_COMPONENTS = frozenset({"market-lan", "analysis-api"})
PYTHON_COMPONENTS = frozenset({"market-loopback", "market-lan", "analysis-api"})
TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[1] / "runtime/launchagents"


@dataclass(frozen=True, slots=True)
class LaunchInvocation:
    executable: str
    arguments: tuple[str, ...]
    environment: Mapping[str, str]
    working_directory: Path


def render_launch_agent(
    component: str,
    *,
    repository: os.PathLike[str] | str,
    home: os.PathLike[str] | str,
    environment_file: os.PathLike[str] | str,
    temporary_directory: os.PathLike[str] | str,
    log_directory: os.PathLike[str] | str,
    ca_bundle: os.PathLike[str] | str,
) -> bytes:
    """Render one fixed template through typed plist values, never raw XML."""

    label = COMPONENT_LABELS.get(component)
    if label is None:
        raise RuntimeConfigurationError("unknown runtime component")

    repository_path = _absolute_path(repository)
    home_path = _absolute_path(home)
    environment_path = _absolute_path(environment_file)
    temporary_path = _absolute_path(temporary_directory)
    log_path = _absolute_path(log_directory)
    ca_path = _absolute_path(ca_bundle)
    launcher_path = repository_path / "scripts/local_runtime_launch.py"
    venv_python = repository_path / "services/market_gateway/.venv/bin/python"
    working_directory = (
        repository_path / "apps/mobile" if component == "metro" else repository_path
    )
    stdout_path = log_path / f"{component}.stdout.log"
    stderr_path = log_path / f"{component}.stderr.log"

    replacements = {
        "__RUNTIME_LAUNCHER_INTERPRETER__": str(venv_python),
        "__RUNTIME_LAUNCHER_PATH__": str(launcher_path),
        "__RUNTIME_REPOSITORY__": str(repository_path),
        "__RUNTIME_HOME__": str(home_path),
        "__RUNTIME_ENVIRONMENT_FILE__": str(environment_path),
        "__RUNTIME_TEMPORARY_DIRECTORY__": str(temporary_path),
        "__RUNTIME_CA_BUNDLE__": str(ca_path),
        "__RUNTIME_WORKING_DIRECTORY__": str(working_directory),
        "__RUNTIME_STANDARD_OUT_PATH__": str(stdout_path),
        "__RUNTIME_STANDARD_ERROR_PATH__": str(stderr_path),
    }
    template_path = TEMPLATE_DIRECTORY / f"{label}.plist.in"
    try:
        template = plistlib.loads(template_path.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        raise RuntimeConfigurationError(
            "launch agent template is unavailable"
        ) from None
    rendered = _replace_plist_sentinels(template, replacements)
    expected = _expected_plist(
        component,
        label=label,
        venv_python=venv_python,
        launcher_path=launcher_path,
        repository=repository_path,
        home=home_path,
        environment_file=environment_path,
        temporary_directory=temporary_path,
        ca_bundle=ca_path,
        working_directory=working_directory,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    if rendered != expected or _contains_unresolved_sentinel(rendered):
        raise RuntimeConfigurationError("launch agent template has an invalid contract")
    return plistlib.dumps(rendered, fmt=plistlib.FMT_XML, sort_keys=False)


def _expected_plist(
    component: str,
    *,
    label: str,
    venv_python: Path,
    launcher_path: Path,
    repository: Path,
    home: Path,
    environment_file: Path,
    temporary_directory: Path,
    ca_bundle: Path,
    working_directory: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, object]:
    arguments = [
        str(venv_python),
        str(launcher_path),
        component,
        "--repository",
        str(repository),
        "--home",
        str(home),
        "--temporary-directory",
        str(temporary_directory),
    ]
    if component in SECRET_COMPONENTS:
        arguments.extend(("--environment-file", str(environment_file)))
    if component in PYTHON_COMPONENTS:
        arguments.extend(("--ca-bundle", str(ca_bundle)))
    return {
        "Label": label,
        "ProgramArguments": arguments,
        "WorkingDirectory": str(working_directory),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": LAUNCH_THROTTLE_SECONDS,
        "Umask": 63,
        "StandardOutPath": str(stdout_path),
        "StandardErrorPath": str(stderr_path),
    }


def _replace_plist_sentinels(value: object, replacements: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_plist_sentinels(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_plist_sentinels(item, replacements)
            for key, item in value.items()
        }
    return value


def _contains_unresolved_sentinel(value: object) -> bool:
    if isinstance(value, str):
        return "__RUNTIME_" in value or "${" in value
    if isinstance(value, list):
        return any(_contains_unresolved_sentinel(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_unresolved_sentinel(key) or _contains_unresolved_sentinel(item)
            for key, item in value.items()
        )
    return False


def validate_repository_identity(
    repository: os.PathLike[str] | str,
    *,
    process_runner: ProcessRunner = DEFAULT_PROCESS_RUNNER,
) -> Path:
    """Require this launcher's exact feature worktree and Git identity."""

    repository_path = _absolute_path(repository)
    launcher_repository = Path(__file__).resolve().parents[1]
    if repository_path != launcher_repository:
        raise RuntimeConfigurationError("runtime repository identity is invalid")
    validate_runtime_directory_chain(repository_path)

    git_file = repository_path / ".git"
    validate_runtime_file(git_file, executable=False)
    try:
        git_reference = git_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise RuntimeConfigurationError(
            "runtime repository identity is invalid"
        ) from None
    if git_reference.count("\n") > 1 or not git_reference.startswith("gitdir: "):
        raise RuntimeConfigurationError("runtime repository identity is invalid")
    git_directory = Path(git_reference.removeprefix("gitdir: ").strip())
    if not git_directory.is_absolute():
        raise RuntimeConfigurationError("runtime repository identity is invalid")
    validate_runtime_directory_chain(git_directory)

    validate_runtime_file(GIT_EXECUTABLE, executable=True)
    git_environment = {"PATH": FIXED_PATH, "LC_ALL": "C"}
    commands = (
        [
            str(GIT_EXECUTABLE),
            "-C",
            str(repository_path),
            "rev-parse",
            "--show-toplevel",
        ],
        [
            str(GIT_EXECUTABLE),
            "-C",
            str(repository_path),
            "symbolic-ref",
            "--short",
            "HEAD",
        ],
    )
    expected_outputs = (str(repository_path), EXPECTED_BRANCH)
    for command, expected_output in zip(commands, expected_outputs, strict=True):
        try:
            result = process_runner.run(
                command,
                cwd=str(repository_path),
                env=git_environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeConfigurationError(
                "runtime repository identity is invalid"
            ) from None
        if result.returncode != 0 or result.stdout.strip() != expected_output:
            raise RuntimeConfigurationError("runtime repository identity is invalid")

    validate_runtime_file(
        repository_path / "scripts/local_runtime_launch.py",
        executable=False,
    )
    return repository_path


def validate_runtime_directory_chain(
    path: os.PathLike[str] | str,
    *,
    required_mode: int | None = None,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> Path:
    """Validate every absolute directory component with fd-relative opens."""

    directory = _absolute_path(path)
    _validate_trusted_path(
        directory,
        final_kind="directory",
        allowed_symlinks=(),
        trusted_external=False,
        required_mode=required_mode,
        executable=False,
        filesystem=filesystem,
    )
    return directory


def validate_runtime_file(
    path: os.PathLike[str] | str,
    *,
    executable: bool,
    allowed_symlinks: Sequence[os.PathLike[str] | str] = (),
    trusted_external: bool = False,
    required_mode: int | None = None,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> Path:
    """Validate a file and its chain while preserving an explicitly trusted argv."""

    file_path = _absolute_path(path)
    _validate_trusted_path(
        file_path,
        final_kind="file",
        allowed_symlinks=allowed_symlinks,
        trusted_external=trusted_external,
        required_mode=required_mode,
        executable=executable,
        filesystem=filesystem,
    )
    return file_path


def _validate_trusted_path(
    path: Path,
    *,
    final_kind: str,
    allowed_symlinks: Sequence[os.PathLike[str] | str],
    trusted_external: bool,
    required_mode: int | None,
    executable: bool,
    filesystem: FileSystemRunner,
) -> Path:
    if final_kind not in {"directory", "file"} or any(
        part == ".." for part in path.parts
    ):
        raise RuntimeConfigurationError("runtime path is unsafe")
    allowed = frozenset(_absolute_path(candidate) for candidate in allowed_symlinks)
    queue = list(path.parts[1:])
    current_parts: list[str] = []
    descriptor: int | None = None
    pending_descriptor: int | None = None
    symlink_hops = 0
    try:
        descriptor = _open_root(filesystem)
        _validate_directory_descriptor(
            descriptor,
            Path("/"),
            trusted_external=trusted_external,
            required_mode=None,
            filesystem=filesystem,
        )
        if not queue:
            if final_kind != "directory":
                raise RuntimeConfigurationError("runtime path is unsafe")
            return Path("/")

        while queue:
            if descriptor is None:
                raise RuntimeConfigurationError("runtime path is unsafe")
            name = queue.pop(0)
            if not name or name in {".", ".."}:
                raise RuntimeConfigurationError("runtime path is unsafe")
            candidate = Path("/").joinpath(*current_parts, name)
            is_final = not queue
            flags = (
                _file_open_flags()
                if is_final and final_kind == "file"
                else _directory_open_flags()
            )
            try:
                child = filesystem.open_fd(name, flags, dir_fd=descriptor)
            except OSError as error:
                if (
                    error.errno not in {errno.ELOOP, errno.ENOTDIR}
                    or candidate not in allowed
                ):
                    raise RuntimeConfigurationError("runtime path is unsafe") from None
                symlink_hops += 1
                if symlink_hops > _MAX_SYMLINK_HOPS:
                    raise RuntimeConfigurationError("runtime path is unsafe")
                target = _read_trusted_symlink(
                    descriptor,
                    name,
                    filesystem=filesystem,
                )
                normalized_target = _normalize_symlink_target(current_parts, target)
                if not _runtime_symlink_target_is_allowed(
                    candidate,
                    normalized_target,
                ):
                    raise RuntimeConfigurationError("runtime symlink is unsafe")
                queue = normalized_target + queue
                owned_descriptor = descriptor
                descriptor = None
                filesystem.close_fd(owned_descriptor)
                descriptor = _open_root(filesystem)
                current_parts = []
                _validate_directory_descriptor(
                    descriptor,
                    Path("/"),
                    trusted_external=trusted_external,
                    required_mode=None,
                    filesystem=filesystem,
                )
                continue

            child_path = candidate
            pending_descriptor = child
            if is_final and final_kind == "file":
                _validate_file_descriptor(
                    child,
                    child_path,
                    trusted_external=trusted_external,
                    required_mode=required_mode,
                    executable=executable,
                    filesystem=filesystem,
                )
            else:
                _validate_directory_descriptor(
                    child,
                    child_path,
                    trusted_external=trusted_external,
                    required_mode=required_mode if is_final else None,
                    filesystem=filesystem,
                )
            owned_descriptor = descriptor
            descriptor = None
            filesystem.close_fd(owned_descriptor)
            descriptor = child
            pending_descriptor = None
            current_parts.append(name)
        return Path("/").joinpath(*current_parts)
    except (OSError, RuntimeConfigurationError, ValueError):
        raise RuntimeConfigurationError("runtime path is unsafe") from None
    finally:
        owned_descriptors = (pending_descriptor, descriptor)
        pending_descriptor = None
        descriptor = None
        close_failed = False
        for owned_descriptor in owned_descriptors:
            if owned_descriptor is None:
                continue
            try:
                filesystem.close_fd(owned_descriptor)
            except OSError:
                close_failed = True
        if close_failed:
            raise RuntimeConfigurationError("runtime path is unsafe") from None


def _open_root(filesystem: FileSystemRunner) -> int:
    return filesystem.open_fd(Path("/"), _directory_open_flags())


def _directory_open_flags() -> int:
    access = (
        _DARWIN_O_EXEC | getattr(os, "O_DIRECTORY", 0)
        if sys.platform == "darwin"
        else os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    return access | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)


def _file_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _read_trusted_symlink(
    parent_descriptor: int,
    name: str,
    *,
    filesystem: FileSystemRunner,
) -> str:
    descriptor: int | None = None
    try:
        descriptor = filesystem.open_fd(
            name,
            _DARWIN_O_SYMLINK | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        metadata = filesystem.fstat(descriptor)
        if not stat.S_ISLNK(metadata.st_mode) or metadata.st_uid not in {
            0,
            filesystem.geteuid(),
        }:
            raise RuntimeConfigurationError("runtime symlink is unsafe")
        target = os.readlink(name, dir_fd=parent_descriptor)
        if not target:
            raise RuntimeConfigurationError("runtime symlink is unsafe")
        return target
    except (OSError, RuntimeConfigurationError):
        raise RuntimeConfigurationError("runtime symlink is unsafe") from None
    finally:
        if descriptor is not None:
            filesystem.close_fd(descriptor)


def _normalize_symlink_target(parent_parts: Sequence[str], target: str) -> list[str]:
    target_path = Path(target)
    normalized = [] if target_path.is_absolute() else list(parent_parts)
    for part in target_path.parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if not normalized:
                raise RuntimeConfigurationError("runtime symlink is unsafe")
            normalized.pop()
        else:
            normalized.append(part)
    if not normalized:
        raise RuntimeConfigurationError("runtime symlink is unsafe")
    return normalized


def _runtime_symlink_target_is_allowed(
    link: Path,
    normalized_target: Sequence[str],
) -> bool:
    target = Path("/").joinpath(*normalized_target)
    repository = Path(__file__).resolve().parents[1]
    venv_bin = repository / "services/market_gateway/.venv/bin"
    exact_targets = {
        venv_bin / "python": venv_bin / "python3.11",
        venv_bin
        / "python3.11": Path(
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
        ),
    }
    if link in exact_targets:
        return target == exact_targets[link]
    if link == Path("/opt/homebrew/opt/node@22"):
        return target.is_relative_to(Path("/opt/homebrew/Cellar/node@22"))
    return False


def _validate_directory_descriptor(
    descriptor: int,
    path: Path,
    *,
    trusted_external: bool,
    required_mode: int | None,
    filesystem: FileSystemRunner,
) -> None:
    metadata = filesystem.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeConfigurationError("runtime directory is unsafe")
    _validate_owner_and_mode(
        path,
        metadata,
        trusted_external=trusted_external,
        required_mode=required_mode,
        filesystem=filesystem,
    )
    allow_protective = path in _protective_acl_paths(filesystem)
    if not directory_acl_is_absent_or_protective(
        descriptor,
        allow_protective=allow_protective,
    ):
        raise RuntimeConfigurationError("runtime directory is unsafe")


def _validate_file_descriptor(
    descriptor: int,
    path: Path,
    *,
    trusted_external: bool,
    required_mode: int | None,
    executable: bool,
    filesystem: FileSystemRunner,
) -> None:
    metadata = filesystem.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeConfigurationError("runtime file is unsafe")
    mode = _validate_owner_and_mode(
        path,
        metadata,
        trusted_external=trusted_external,
        required_mode=required_mode,
        filesystem=filesystem,
    )
    if executable and not _is_executable_by_effective_user(
        metadata,
        mode,
        filesystem=filesystem,
    ):
        raise RuntimeConfigurationError("runtime file is unsafe")
    if filesystem.has_extended_acl(descriptor):
        raise RuntimeConfigurationError("runtime file is unsafe")


def _validate_owner_and_mode(
    path: Path,
    metadata: os.stat_result,
    *,
    trusted_external: bool,
    required_mode: int | None,
    filesystem: FileSystemRunner,
) -> int:
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid not in {0, filesystem.geteuid()} or mode & 0o002:
        raise RuntimeConfigurationError("runtime path is unsafe")
    if mode & 0o020 and not _is_exact_trusted_external_group_write(
        path,
        metadata,
        trusted_external=trusted_external,
        filesystem=filesystem,
    ):
        raise RuntimeConfigurationError("runtime path is unsafe")
    if required_mode is not None and mode != required_mode:
        raise RuntimeConfigurationError("runtime path is unsafe")
    return mode


def _is_executable_by_effective_user(
    metadata: os.stat_result,
    mode: int,
    *,
    filesystem: FileSystemRunner,
) -> bool:
    effective_uid = filesystem.geteuid()
    if effective_uid == 0:
        return bool(mode & 0o111)
    if metadata.st_uid == effective_uid:
        return bool(mode & stat.S_IXUSR)
    effective_groups = {filesystem.getegid(), *filesystem.getgroups()}
    if metadata.st_gid in effective_groups:
        return bool(mode & stat.S_IXGRP)
    return bool(mode & stat.S_IXOTH)


def _is_exact_trusted_external_group_write(
    path: Path,
    metadata: os.stat_result,
    *,
    trusted_external: bool,
    filesystem: FileSystemRunner,
) -> bool:
    if not trusted_external or stat.S_IMODE(metadata.st_mode) != 0o775:
        return False
    try:
        admin_gid = grp.getgrnam("admin").gr_gid
        wheel_gid = grp.getgrnam("wheel").gr_gid
    except KeyError:
        return False
    if path in _HOMEBREW_GROUP_WRITABLE_DIRECTORIES:
        return metadata.st_uid == filesystem.geteuid() and metadata.st_gid == admin_gid
    if path in _PYTHON_GROUP_WRITABLE_PATHS:
        return metadata.st_uid == 0 and metadata.st_gid == wheel_gid
    return False


def _protective_acl_paths(filesystem: FileSystemRunner) -> frozenset[Path]:
    try:
        home = Path(pwd.getpwuid(filesystem.geteuid()).pw_dir).resolve(strict=True)
    except (KeyError, OSError):
        raise RuntimeConfigurationError("runtime home directory is unsafe") from None
    return frozenset({home, home / "Documents", home / "Library"})


def _validate_account_home(
    path: os.PathLike[str] | str,
    *,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> Path:
    """Accept only this account's home, including macOS's protective ACL."""

    home = _absolute_path(path)
    try:
        account_home = Path(pwd.getpwuid(filesystem.geteuid()).pw_dir).resolve(
            strict=True
        )
        canonical_home = home.resolve(strict=True)
    except (KeyError, OSError):
        raise RuntimeConfigurationError("runtime home directory is unsafe") from None
    if home != canonical_home or home != account_home:
        raise RuntimeConfigurationError("runtime home directory is unsafe")
    validate_runtime_directory_chain(home, filesystem=filesystem)
    return home


def prepare_launch(
    component: str,
    *,
    repository: os.PathLike[str] | str,
    home: os.PathLike[str] | str,
    environment_file: os.PathLike[str] | str | None,
    temporary_directory: os.PathLike[str] | str,
    ca_bundle: os.PathLike[str] | str | None,
    process_runner: ProcessRunner = DEFAULT_PROCESS_RUNNER,
) -> LaunchInvocation:
    """Validate one component and build the exact child invocation."""

    if component not in COMPONENT_LABELS:
        raise RuntimeConfigurationError("unknown runtime component")
    repository_path = validate_repository_identity(
        repository,
        process_runner=process_runner,
    )
    home_path = _validate_account_home(home)
    temporary_path = validate_runtime_directory_chain(
        temporary_directory,
        required_mode=PRIVATE_DIRECTORY_MODE,
    )

    if component in SECRET_COMPONENTS:
        if environment_file is None:
            raise RuntimeConfigurationError("runtime environment is unavailable")
        environment_path = _absolute_path(environment_file)
        validate_runtime_directory_chain(
            environment_path.parent,
            required_mode=PRIVATE_DIRECTORY_MODE,
        )
        parsed_environment = parse_runtime_environment(environment_path)
    else:
        if environment_file is not None:
            raise RuntimeConfigurationError("runtime environment is not allowed")
        parsed_environment = {}

    if component in PYTHON_COMPONENTS:
        if ca_bundle is None:
            raise RuntimeConfigurationError("runtime CA bundle is unavailable")
        ca_path = validate_runtime_file(
            _absolute_path(ca_bundle),
            executable=False,
        )
        market_python_path = (
            repository_path / "services/market_gateway/.venv/bin/python"
        )
        market_python = validate_runtime_file(
            market_python_path,
            executable=True,
            allowed_symlinks=(
                market_python_path,
                market_python_path.parent / "python3.11",
            ),
            trusted_external=True,
        )
        module = (
            "us_stock_helper_analysis_api"
            if component == "analysis-api"
            else "us_stock_helper_market_gateway"
        )
        entrypoint = repository_path / (
            "services/analysis_api/src/us_stock_helper_analysis_api/__main__.py"
            if component == "analysis-api"
            else "services/market_gateway/src/us_stock_helper_market_gateway/__main__.py"
        )
        validate_runtime_file(entrypoint, executable=False)
        for relative_path in COMPONENT_SPECS[component].python_paths:
            validate_runtime_directory_chain(repository_path / relative_path)
        executable_path = market_python
        arguments = (str(market_python), "-m", module)
        working_directory = repository_path
    else:
        if ca_bundle is not None:
            raise RuntimeConfigurationError("runtime CA bundle is not allowed")
        executable_path = validate_runtime_file(
            NODE_22_EXECUTABLE,
            executable=True,
            allowed_symlinks=(Path("/opt/homebrew/opt/node@22"),),
            trusted_external=True,
        )
        expo_cli = validate_runtime_file(
            repository_path / "apps/mobile/node_modules/expo/bin/cli",
            executable=False,
        )
        validate_runtime_file(
            repository_path / "apps/mobile/package.json",
            executable=False,
        )
        arguments = (
            str(executable_path),
            str(expo_cli),
            "start",
            "--dev-client",
            "--lan",
            "--port",
            "8088",
        )
        working_directory = validate_runtime_directory_chain(
            repository_path / "apps/mobile"
        )
        ca_path = repository_path  # Unused by the Metro component environment.

    environment = build_component_environment(
        component,
        parsed_environment,
        repository=repository_path,
        home=home_path,
        temporary_directory=temporary_path,
        ca_bundle=ca_path,
    )
    return LaunchInvocation(
        executable=str(executable_path),
        arguments=tuple(arguments),
        environment=MappingProxyType(environment),
        working_directory=working_directory,
    )


def launch_component(
    component: str,
    *,
    repository: os.PathLike[str] | str,
    home: os.PathLike[str] | str,
    environment_file: os.PathLike[str] | str | None,
    temporary_directory: os.PathLike[str] | str,
    ca_bundle: os.PathLike[str] | str | None,
    process_runner: ProcessRunner = DEFAULT_PROCESS_RUNNER,
) -> NoReturn:
    invocation = prepare_launch(
        component,
        repository=repository,
        home=home,
        environment_file=environment_file,
        temporary_directory=temporary_directory,
        ca_bundle=ca_bundle,
        process_runner=process_runner,
    )
    try:
        os.chdir(invocation.working_directory)
    except OSError:
        raise RuntimeConfigurationError(
            "runtime working directory is unavailable"
        ) from None
    if Path.cwd().resolve() != invocation.working_directory:
        raise RuntimeConfigurationError("runtime working directory is unavailable")
    process_runner.execve(
        invocation.executable,
        invocation.arguments,
        invocation.environment,
    )
    raise RuntimeConfigurationError("runtime process replacement failed")


def _absolute_path(path: os.PathLike[str] | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RuntimeConfigurationError("runtime path must be absolute")
    return candidate


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("component", nargs="?")
    parser.add_argument("--repository")
    parser.add_argument("--home")
    parser.add_argument("--environment-file")
    parser.add_argument("--temporary-directory")
    parser.add_argument("--ca-bundle")
    try:
        arguments, extras = parser.parse_known_args(argv)
    except argparse.ArgumentError:
        raise RuntimeConfigurationError(
            "runtime launch arguments are invalid"
        ) from None
    if (
        extras
        or arguments.component is None
        or arguments.repository is None
        or arguments.home is None
        or arguments.temporary_directory is None
    ):
        raise RuntimeConfigurationError("runtime launch arguments are invalid")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parse_arguments(argv)
        launch_component(
            arguments.component,
            repository=arguments.repository,
            home=arguments.home,
            environment_file=arguments.environment_file,
            temporary_directory=arguments.temporary_directory,
            ca_bundle=arguments.ca_bundle,
        )
    except (RuntimeConfigurationError, OSError, ValueError):
        print("runtime launch failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
