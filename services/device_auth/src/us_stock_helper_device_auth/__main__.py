"""The operator terminal.

A pairing code is only meaningful to someone who is already on the host, so it
is printed here and nowhere else. Device tokens are never printed: the phone
receives its token once, in the reply to its own redemption, and the operator
never needs to see it.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import IO, Sequence

from .errors import DeviceAuthError
from .service import DeviceAuthService, RevocationResult
from .store import DeviceStore
from .time_utils import to_storage


DATABASE_ENVIRONMENT_VARIABLE = "DEVICE_AUTH_DATABASE"
DEFAULT_DATABASE = "~/.us-stock-helper/device-auth.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--database",
        default=None,
        help=(
            "path to the credential file"
            f" (default: ${DATABASE_ENVIRONMENT_VARIABLE} or {DEFAULT_DATABASE})"
        ),
    )

    parser = argparse.ArgumentParser(
        prog="us-stock-helper-device-auth",
        description="Pair a phone with this host, list paired phones, or revoke one.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    pair = commands.add_parser(
        "pair",
        parents=[common],
        help="print a single-use pairing code for one new phone",
    )
    pair.add_argument("--label", required=True, help="how this phone is listed later")
    pair.add_argument(
        "--ttl-minutes",
        type=int,
        default=10,
        help="minutes before the printed code stops working (default: 10)",
    )

    commands.add_parser("devices", parents=[common], help="list the paired phones")

    revoke = commands.add_parser(
        "revoke", parents=[common], help="refuse one paired phone from now on"
    )
    revoke.add_argument("device_id", help="the identifier shown by the devices command")
    revoke.add_argument("--reason", required=True, help="why, for the record")

    attempts = commands.add_parser(
        "attempts", parents=[common], help="show recent pairing attempts"
    )
    attempts.add_argument("--client", default=None, help="limit to one caller")
    attempts.add_argument("--limit", type=int, default=50)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    arguments = build_parser().parse_args(argv)

    database = arguments.database or os.environ.get(
        DATABASE_ENVIRONMENT_VARIABLE, DEFAULT_DATABASE
    )
    try:
        service = DeviceAuthService(store=DeviceStore(Path(database).expanduser()))
        if arguments.command == "pair":
            return _pair(service, arguments, out)
        if arguments.command == "devices":
            return _devices(service, out)
        if arguments.command == "revoke":
            return _revoke(service, arguments, out, err)
        return _attempts(service, arguments, out)
    except DeviceAuthError as error:
        print(f"{error.code.value}: {error.message}", file=err)
        return 2


def _pair(
    service: DeviceAuthService, arguments: argparse.Namespace, out: IO[str]
) -> int:
    issued = DeviceAuthService(
        store=service.store,
        clock=service.clock,
        code_ttl=timedelta(minutes=arguments.ttl_minutes),
    ).issue_pairing_code(label=arguments.label)
    print(f"pairing-code: {issued.formatted}", file=out)
    print(f"label: {issued.label}", file=out)
    print(f"expires-utc: {to_storage(issued.expires_at)}", file=out)
    print(
        "note: single use, one phone, and typed into the phone by hand",
        file=out,
    )
    return 0


def _devices(service: DeviceAuthService, out: IO[str]) -> int:
    records = service.devices()
    if not records:
        print("no phones are paired with this host", file=out)
        return 0
    for record in records:
        state = "active" if record.revoked_at is None else "revoked"
        # "never" rather than a blank or an invented timestamp: a phone that has
        # not called yet is a fact worth reading off the line.
        last_seen = (
            "never" if record.last_seen_at is None else to_storage(record.last_seen_at)
        )
        print(
            f"device-id: {record.device_id}"
            f"  label: {record.name}"
            f"  created-utc: {to_storage(record.created_at)}"
            f"  last-seen-utc: {last_seen}"
            f"  state: {state}"
            + (f" ({record.revoked_reason})" if record.revoked_at is not None else ""),
            file=out,
        )
    return 0


def _revoke(
    service: DeviceAuthService,
    arguments: argparse.Namespace,
    out: IO[str],
    err: IO[str],
) -> int:
    result = service.revoke_device(arguments.device_id, reason=arguments.reason)
    if result is RevocationResult.REVOKED:
        print(f"revoked: {arguments.device_id}", file=out)
        return 0
    print(f"{result.value}: {arguments.device_id}", file=err)
    return 1


def _attempts(
    service: DeviceAuthService, arguments: argparse.Namespace, out: IO[str]
) -> int:
    records = service.recent_pairing_attempts(arguments.client, limit=arguments.limit)
    if not records:
        print("no pairing attempts are on record", file=out)
        return 0
    for record in records:
        print(
            f"attempted-utc: {to_storage(record.attempted_at)}"
            f"  client: {record.client_id}"
            f"  outcome: {record.outcome.value}",
            file=out,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
