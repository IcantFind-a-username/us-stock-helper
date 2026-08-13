"""The single-file credential store.

One SQLite file, mode 0600, one schema version, and no connection shared
between threads: every operation opens its own connection so the service can
sit behind a ThreadingHTTPServer without a lock of its own. The interesting
work here is the transaction boundaries — reserving a rate-limit slot and
consuming a pairing code both have to be atomic, or two racing phones pair
against one code.

Anything SQLite refuses to do becomes a DeviceAuthError. A read that cannot be
performed must never look like a read that returned nothing.
"""

from __future__ import annotations

import math
import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .errors import DeviceAuthError, ErrorCode
from .time_utils import from_storage, to_storage


SCHEMA_VERSION = 1

# A ceiling on how many rows one redemption attempt can be made to hash. Live
# codes are capped far below this, so the bound only ever discards rows that
# are already dead and kept for the audit trail — but without it, an operator
# who issued codes all afternoon would have made every guess more expensive.
MAX_CANDIDATE_CODES = 16

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

_TABLES = {
    "pairing_codes": {
        "code_id",
        "salt",
        "code_hash",
        "kdf",
        "label",
        "created_at",
        "expires_at",
        "consumed_at",
    },
    "devices": {
        "device_id",
        "name",
        "salt",
        "token_hash",
        "algorithm",
        "paired_from_code",
        "created_at",
        "last_seen_at",
        "revoked_at",
        "revoked_reason",
    },
    "pairing_attempts": {"attempt_id", "client_id", "attempted_at", "outcome"},
}

# Statements rather than one script: Connection.executescript commits whatever
# transaction is open before it runs, which would take the schema creation out
# of the BEGIN IMMEDIATE that makes two processes starting at once safe.
_SCHEMA_STATEMENTS = (
    """
CREATE TABLE IF NOT EXISTS pairing_codes (
    code_id     TEXT PRIMARY KEY,
    salt        BLOB NOT NULL,
    code_hash   BLOB NOT NULL,
    kdf         TEXT NOT NULL,
    label       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    consumed_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS devices (
    device_id        TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    salt             BLOB NOT NULL,
    token_hash       BLOB NOT NULL,
    algorithm        TEXT NOT NULL,
    paired_from_code TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    last_seen_at     TEXT,
    revoked_at       TEXT,
    revoked_reason   TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS pairing_attempts (
    attempt_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    outcome      TEXT NOT NULL
)
""",
    """
CREATE INDEX IF NOT EXISTS pairing_attempts_by_client
    ON pairing_attempts (client_id, attempted_at)
""",
)


@dataclass(frozen=True, slots=True)
class PairingCodeRow:
    code_id: str
    salt: bytes
    code_hash: bytes
    kdf: str
    label: str
    expires_at: str
    consumed_at: str | None


@dataclass(frozen=True, slots=True)
class DeviceSecretRow:
    device_id: str
    salt: bytes
    token_hash: bytes
    algorithm: str
    revoked_at: str | None


@dataclass(frozen=True, slots=True)
class AttemptSlot:
    """Either a reserved slot in the rate-limit window, or the wait to get one."""

    attempt_id: int | None
    retry_after_seconds: int | None


class DeviceStore:
    def __init__(self, path: str | Path, *, busy_timeout_seconds: float = 15.0) -> None:
        self.path = Path(path)
        self._busy_timeout_seconds = busy_timeout_seconds
        self._create_private_file()
        self._require_private()
        self._prepare_schema()
        self._require_private()

    # --- file and schema setup -------------------------------------------

    def _create_private_file(self) -> None:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(
                self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
            )
        except OSError as exc:
            raise DeviceAuthError(
                ErrorCode.STORAGE_UNREADABLE,
                "the device store file could not be opened",
            ) from exc
        os.close(descriptor)

    def _require_private(self) -> None:
        """Refuse a store any other user on the box could read or replace.

        Quietly repairing a mode would hide the window in which the hashes were
        exposed, so this stops and asks the operator to look instead. The
        directory is checked for write and not for read: listing the filenames
        next to a 0600 database reveals nothing, but writing the directory
        means moving the database aside and pairing a device of one's own.
        """
        directory = self._stat(self.path.parent, required=True)
        assert directory is not None
        if stat.S_IMODE(directory.st_mode) & 0o022:
            raise DeviceAuthError(
                ErrorCode.STORAGE_INSECURE,
                f"{self.path.parent} is writable beyond its owner; chmod 700 it",
            )
        candidates = [self.path] + [
            self.path.with_name(self.path.name + suffix)
            for suffix in _SIDECAR_SUFFIXES
        ]
        for candidate in candidates:
            # SQLite creates and removes its sidecars as it works, so one that
            # has already gone is not a finding. Asking whether it exists first
            # and stat-ing it afterwards would turn that into a false alarm.
            found = self._stat(candidate, required=False)
            if found is None:
                continue
            if stat.S_IMODE(found.st_mode) & 0o077:
                raise DeviceAuthError(
                    ErrorCode.STORAGE_INSECURE,
                    f"{candidate.name} is readable beyond its owner; chmod 600 it",
                )

    @staticmethod
    def _stat(path: Path, *, required: bool) -> os.stat_result | None:
        try:
            return os.stat(path)
        except FileNotFoundError:
            if not required:
                return None
            raise DeviceAuthError(
                ErrorCode.STORAGE_UNREADABLE, f"{path} does not exist"
            ) from None
        except OSError as exc:
            raise DeviceAuthError(
                ErrorCode.STORAGE_UNREADABLE, f"{path.name} could not be inspected"
            ) from exc

    def _prefer_write_ahead_log(self, connection: sqlite3.Connection) -> None:
        """Ask for WAL, but never refuse to start over it.

        Write-ahead logging keeps a reader from being locked out while a phone
        redeems a code, and the setting persists in the file, so it is worth
        asking for once. It is only worth asking, though: switching journal
        mode needs an exclusive lock, and losing that race raises rather than
        waiting out the busy timeout. Two services opening a cold database in
        the same second is a host reboot, and a rollback journal is correct
        there — merely less concurrent — while a service that will not start is
        not correct at all.
        """
        current = connection.execute("PRAGMA journal_mode").fetchone()[0]
        if str(current).lower() == "wal":
            return
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.OperationalError:
            # Only the lock is conceded here. A file SQLite cannot read at all
            # raises DatabaseError from the read above, outside this guard.
            return

    @staticmethod
    def _read_schema(connection: sqlite3.Connection) -> tuple[int, set[str]]:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        return version, tables

    def _prepare_schema(self) -> None:
        with self._connection() as connection:
            self._prefer_write_ahead_log(connection)
            # One snapshot for both facts. user_version and sqlite_master are
            # two statements, and outside a transaction they can straddle
            # another process committing the schema — which reads back as
            # "version 0, tables already present" and refuses to start.
            connection.execute("BEGIN")
            version, existing = self._read_schema(connection)
            connection.execute("COMMIT")
            if version == 0 and not (existing & set(_TABLES)):
                # Creating is the only branch that writes, so it is the only
                # one that takes a lock. Even a read-only IMMEDIATE transaction
                # needs the exclusive lock to commit, which would make every
                # service start contend with a phone that is mid-pairing.
                connection.execute("BEGIN IMMEDIATE")
                version, existing = self._read_schema(connection)
                if version == 0 and not (existing & set(_TABLES)):
                    for statement in _SCHEMA_STATEMENTS:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    version = SCHEMA_VERSION
                connection.execute("COMMIT")

        if version != SCHEMA_VERSION:
            raise DeviceAuthError(
                ErrorCode.SCHEMA_UNSUPPORTED,
                f"device store schema {version} has no migration to {SCHEMA_VERSION}",
            )
        self._require_columns()

    def _require_columns(self) -> None:
        with self._connection() as connection:
            for table, expected in _TABLES.items():
                found = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if not expected.issubset(found):
                    raise DeviceAuthError(
                        ErrorCode.SCHEMA_UNSUPPORTED,
                        f"device store table {table} is missing expected columns",
                    )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(
                self.path,
                isolation_level=None,
                timeout=self._busy_timeout_seconds,
            )
        except sqlite3.Error as exc:
            raise DeviceAuthError(
                ErrorCode.STORAGE_UNREADABLE, "the device store could not be opened"
            ) from exc
        try:
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        except DeviceAuthError:
            _rollback(connection)
            raise
        except sqlite3.Error as exc:
            _rollback(connection)
            raise DeviceAuthError(
                ErrorCode.STORAGE_UNREADABLE, "the device store could not be read"
            ) from exc
        finally:
            connection.close()

    # --- pairing codes ----------------------------------------------------

    def insert_pairing_code(
        self,
        *,
        code_id: str,
        salt: bytes,
        digest: bytes,
        kdf: str,
        label: str,
        created_at: datetime,
        expires_at: datetime,
        live_code_limit: int,
        retain_codes_for: timedelta,
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM pairing_codes WHERE expires_at < ?",
                (to_storage(created_at - retain_codes_for),),
            )
            live = connection.execute(
                "SELECT count(*) FROM pairing_codes"
                " WHERE consumed_at IS NULL AND expires_at > ?",
                (to_storage(created_at),),
            ).fetchone()[0]
            if live >= live_code_limit:
                connection.execute("ROLLBACK")
                raise DeviceAuthError(
                    ErrorCode.TOO_MANY_PAIRING_CODES,
                    f"{live} pairing codes are already live; wait for one to expire",
                )
            connection.execute(
                "INSERT INTO pairing_codes"
                " (code_id, salt, code_hash, kdf, label, created_at, expires_at,"
                "  consumed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    code_id,
                    salt,
                    digest,
                    kdf,
                    label,
                    to_storage(created_at),
                    to_storage(expires_at),
                ),
            )
            connection.execute("COMMIT")

    def candidate_pairing_codes(
        self, *, now: datetime, retain_codes_for: timedelta
    ) -> tuple[PairingCodeRow, ...]:
        """Every code recent enough to still explain a refusal, expired or not.

        Newest first, because the bound must never discard the code an operator
        is in the middle of reading out; the rows it does discard are old dead
        ones that could only have changed the wording of an audit entry.
        """
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT code_id, salt, code_hash, kdf, label, expires_at, consumed_at"
                " FROM pairing_codes WHERE expires_at >= ?"
                " ORDER BY created_at DESC, code_id DESC LIMIT ?",
                (to_storage(now - retain_codes_for), MAX_CANDIDATE_CODES),
            ).fetchall()
        return tuple(PairingCodeRow(*row) for row in rows)

    def consume_code_and_register_device(
        self,
        *,
        code_id: str,
        now: datetime,
        device_id: str,
        name: str,
        salt: bytes,
        digest: bytes,
        algorithm: str,
    ) -> bool:
        """Claim the code and create the device, or lose the race and claim nothing."""
        stamp = to_storage(now)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            claimed = connection.execute(
                "UPDATE pairing_codes SET consumed_at = ?"
                " WHERE code_id = ? AND consumed_at IS NULL AND expires_at > ?",
                (stamp, code_id, stamp),
            ).rowcount
            if claimed != 1:
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                "INSERT INTO devices"
                " (device_id, name, salt, token_hash, algorithm, paired_from_code,"
                "  created_at, last_seen_at, revoked_at, revoked_reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                (device_id, name, salt, digest, algorithm, code_id, stamp),
            )
            connection.execute("COMMIT")
        return True

    # --- rate limiting ----------------------------------------------------

    def reserve_pairing_attempt(
        self,
        *,
        client_id: str,
        now: datetime,
        limit: int,
        window: timedelta,
        retain_attempts_for: timedelta,
        pending_outcome: str,
    ) -> AttemptSlot:
        """Take one slot in the client's window, or report the wait.

        The row is inserted before the code is even looked at, so concurrent
        guesses cannot all pass a count taken a moment earlier. A throttled
        attempt is deliberately not recorded: counting it would extend the
        lockout for as long as an attacker keeps knocking, which is a denial of
        service against the one operator who needs to pair a phone.
        """
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM pairing_attempts WHERE attempted_at < ?",
                (to_storage(now - retain_attempts_for),),
            )
            count, oldest = connection.execute(
                "SELECT count(*), min(attempted_at) FROM pairing_attempts"
                " WHERE client_id = ? AND attempted_at > ?",
                (client_id, to_storage(now - window)),
            ).fetchone()
            if count >= limit:
                connection.execute("COMMIT")
                return AttemptSlot(None, _seconds_until_free(oldest, now, window))
            cursor = connection.execute(
                "INSERT INTO pairing_attempts (client_id, attempted_at, outcome)"
                " VALUES (?, ?, ?)",
                (client_id, to_storage(now), pending_outcome),
            )
            attempt_id = cursor.lastrowid
            connection.execute("COMMIT")
        return AttemptSlot(attempt_id, None)

    def record_attempt_outcome(self, attempt_id: int, outcome: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE pairing_attempts SET outcome = ? WHERE attempt_id = ?",
                (outcome, attempt_id),
            )

    def recent_attempts(
        self, *, client_id: str | None, limit: int
    ) -> tuple[tuple[str, str, str], ...]:
        query = (
            "SELECT client_id, attempted_at, outcome FROM pairing_attempts"
            f"{' WHERE client_id = ?' if client_id is not None else ''}"
            " ORDER BY attempted_at DESC, attempt_id DESC LIMIT ?"
        )
        parameters: tuple[Any, ...] = (
            (limit,) if client_id is None else (client_id, limit)
        )
        with self._connection() as connection:
            return tuple(connection.execute(query, parameters).fetchall())

    # --- devices ----------------------------------------------------------

    def device_secret(self, device_id: str) -> DeviceSecretRow | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT device_id, salt, token_hash, algorithm, revoked_at"
                " FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return None if row is None else DeviceSecretRow(*row)

    def touch_device(self, device_id: str, now: datetime) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE devices SET last_seen_at = ? WHERE device_id = ?",
                (to_storage(now), device_id),
            )

    def revoke_device(
        self, *, device_id: str, now: datetime, reason: str
    ) -> tuple[bool, bool]:
        """Returns whether the device exists and whether this call revoked it."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revoked_at FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                return False, False
            if row[0] is not None:
                connection.execute("ROLLBACK")
                return True, False
            connection.execute(
                "UPDATE devices SET revoked_at = ?, revoked_reason = ?"
                " WHERE device_id = ?",
                (to_storage(now), reason, device_id),
            )
            connection.execute("COMMIT")
        return True, True

    def all_devices(self) -> tuple[tuple[Any, ...], ...]:
        with self._connection() as connection:
            return tuple(
                connection.execute(
                    "SELECT device_id, name, created_at, last_seen_at, revoked_at,"
                    " revoked_reason FROM devices ORDER BY created_at, device_id"
                ).fetchall()
            )


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            # The transaction is already gone; the original failure is the one
            # worth reporting.
            pass


def _seconds_until_free(oldest: object, now: datetime, window: timedelta) -> int:
    """How long until the window releases a slot, never reported as zero.

    A zero would read as "try again now", which is exactly the advice that
    keeps a client hammering a limit it cannot yet pass.
    """
    ceiling = math.ceil(window.total_seconds())
    if not isinstance(oldest, str):
        return ceiling
    remaining = (from_storage(oldest) + window - now).total_seconds()
    return max(1, min(ceiling, math.ceil(remaining)))
