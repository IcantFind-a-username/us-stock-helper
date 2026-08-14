#!/usr/bin/env python3
"""Render and execute the four fixed local LaunchAgent components."""

from __future__ import annotations

import argparse
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
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        FileSystemRunner,
        ProcessRunner,
        RuntimeConfigurationError,
        build_component_environment,
        parse_runtime_environment,
    )
else:
    from local_runtime_support import (  # type: ignore[no-redef]
        DEFAULT_FILE_SYSTEM,
        DEFAULT_PROCESS_RUNNER,
        FIXED_PATH,
        PRIVATE_DIRECTORY_MODE,
        FileSystemRunner,
        ProcessRunner,
        RuntimeConfigurationError,
        build_component_environment,
        parse_runtime_environment,
    )


EXPECTED_BRANCH = "feature/iphone-demo"
GIT_EXECUTABLE = Path("/usr/bin/git")
NODE_22_EXECUTABLE = Path("/opt/homebrew/opt/node@22/bin/node")
LAUNCH_THROTTLE_SECONDS = 10

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
    try:
        canonical_repository = repository_path.resolve(strict=True)
    except OSError:
        raise RuntimeConfigurationError(
            "runtime repository identity is invalid"
        ) from None
    launcher_repository = Path(__file__).resolve().parents[1]
    if (
        canonical_repository != repository_path
        or canonical_repository != launcher_repository
    ):
        raise RuntimeConfigurationError("runtime repository identity is invalid")
    _validate_runtime_directory(repository_path, private=False)

    git_file = repository_path / ".git"
    validate_runtime_file(git_file, executable=False, allow_symlink=False)
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
    _validate_runtime_directory(git_directory, private=False)

    validate_runtime_file(GIT_EXECUTABLE, executable=True, allow_symlink=False)
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
        allow_symlink=False,
    )
    return repository_path


def validate_runtime_file(
    path: os.PathLike[str] | str,
    *,
    executable: bool,
    allow_symlink: bool = True,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> Path:
    """Validate a trusted regular file while preserving an allowed venv symlink."""

    file_path = _absolute_path(path)
    try:
        link_metadata = filesystem.lstat(file_path)
        if stat.S_ISLNK(link_metadata.st_mode):
            if not allow_symlink or link_metadata.st_uid not in {
                0,
                filesystem.geteuid(),
            }:
                raise RuntimeConfigurationError("runtime file is unsafe")
            resolved_path = file_path.resolve(strict=True)
        else:
            resolved_path = file_path
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = filesystem.open_fd(resolved_path, flags)
    except (OSError, RuntimeConfigurationError):
        raise RuntimeConfigurationError("runtime file is unsafe") from None
    try:
        metadata = filesystem.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeConfigurationError("runtime file is unsafe")
        if metadata.st_uid not in {0, filesystem.geteuid()}:
            raise RuntimeConfigurationError("runtime file is unsafe")
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & 0o002 or (metadata.st_uid != 0 and mode & 0o020):
            raise RuntimeConfigurationError("runtime file is unsafe")
        if executable and (mode & 0o111 == 0 or not os.access(resolved_path, os.X_OK)):
            raise RuntimeConfigurationError("runtime file is unsafe")
        if filesystem.has_extended_acl(descriptor):
            raise RuntimeConfigurationError("runtime file is unsafe")
    except OSError:
        raise RuntimeConfigurationError("runtime file is unsafe") from None
    finally:
        filesystem.close_fd(descriptor)
    return file_path


def _validate_runtime_directory(
    path: os.PathLike[str] | str,
    *,
    private: bool,
    allow_acl: bool = False,
    filesystem: FileSystemRunner = DEFAULT_FILE_SYSTEM,
) -> Path:
    directory = _absolute_path(path)
    descriptor: int | None = None
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_DIRECTORY", 0)
        )
        descriptor = filesystem.open_fd(directory, flags)
        metadata = filesystem.fstat(descriptor)
        mode = stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeConfigurationError("runtime directory is unsafe")
        if metadata.st_uid not in {0, filesystem.geteuid()} or mode & 0o002:
            raise RuntimeConfigurationError("runtime directory is unsafe")
        if private and mode != PRIVATE_DIRECTORY_MODE:
            raise RuntimeConfigurationError("runtime directory is unsafe")
        if not allow_acl and filesystem.has_extended_acl(descriptor):
            raise RuntimeConfigurationError("runtime directory is unsafe")
    except (OSError, RuntimeConfigurationError):
        raise RuntimeConfigurationError("runtime directory is unsafe") from None
    finally:
        if descriptor is not None:
            filesystem.close_fd(descriptor)
    return directory


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
    return _validate_runtime_directory(
        home,
        private=False,
        allow_acl=True,
        filesystem=filesystem,
    )


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
    temporary_path = _validate_runtime_directory(temporary_directory, private=True)

    if component in SECRET_COMPONENTS:
        if environment_file is None:
            raise RuntimeConfigurationError("runtime environment is unavailable")
        parsed_environment = parse_runtime_environment(_absolute_path(environment_file))
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
            allow_symlink=False,
        )
        market_python = validate_runtime_file(
            repository_path / "services/market_gateway/.venv/bin/python",
            executable=True,
            allow_symlink=True,
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
        validate_runtime_file(entrypoint, executable=False, allow_symlink=False)
        executable_path = market_python
        arguments = (str(market_python), "-m", module)
        working_directory = repository_path
    else:
        if ca_bundle is not None:
            raise RuntimeConfigurationError("runtime CA bundle is not allowed")
        executable_path = validate_runtime_file(
            NODE_22_EXECUTABLE,
            executable=True,
            allow_symlink=False,
        )
        expo_cli = validate_runtime_file(
            repository_path / "apps/mobile/node_modules/expo/bin/cli",
            executable=False,
            allow_symlink=False,
        )
        validate_runtime_file(
            repository_path / "apps/mobile/package.json",
            executable=False,
            allow_symlink=False,
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
        working_directory = _validate_runtime_directory(
            repository_path / "apps/mobile",
            private=False,
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
