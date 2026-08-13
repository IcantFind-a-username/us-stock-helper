from __future__ import annotations

import os
import sqlite3
import stat
import threading
import unittest
from pathlib import Path
from unittest import mock

from us_stock_helper_device_auth.errors import DeviceAuthError, ErrorCode
from us_stock_helper_device_auth.store import SCHEMA_VERSION, DeviceStore

from support import StoreCase


def mode_of(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class DatabaseFilePermissionTests(StoreCase):
    def test_the_database_is_created_private_to_its_owner(self) -> None:
        self.store()

        self.assertTrue(self.database.exists())
        self.assertEqual(mode_of(self.database), 0o600)

    def test_the_containing_directory_is_created_private(self) -> None:
        nested = self.directory / "state" / "device-auth.sqlite3"

        DeviceStore(nested)

        self.assertEqual(mode_of(nested.parent), 0o700)
        self.assertEqual(mode_of(nested), 0o600)

    def test_sidecar_journals_are_private_while_they_exist(self) -> None:
        # SQLite deletes the write-ahead log when the last connection closes,
        # so a second connection has to be held open to observe it at all.
        self.store()
        holder = sqlite3.connect(self.database)
        self.addCleanup(holder.close)
        holder.execute("SELECT count(*) FROM devices").fetchone()

        self.service().issue_pairing_code(label="iphone")

        sidecars = [
            Path(str(self.database) + suffix)
            for suffix in ("-wal", "-shm", "-journal")
            if Path(str(self.database) + suffix).exists()
        ]
        self.assertTrue(sidecars, "expected SQLite to leave at least one sidecar")
        for sidecar in sidecars:
            with self.subTest(sidecar=sidecar.name):
                self.assertEqual(mode_of(sidecar) & 0o077, 0)

    def test_a_sidecar_readable_by_others_is_refused(self) -> None:
        self.store()
        sidecar = Path(str(self.database) + "-wal")
        sidecar.touch(mode=0o644)

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.STORAGE_INSECURE)

    def test_a_directory_others_can_write_to_is_refused(self) -> None:
        # The file mode alone does not help here: anyone who can write the
        # directory can move the database aside and put their own in its place,
        # which pairs a device of their choosing.
        nested = self.directory / "shared"
        nested.mkdir()
        os.chmod(nested, 0o777)

        with self.assertRaises(DeviceAuthError) as caught:
            DeviceStore(nested / "device-auth.sqlite3")

        self.assertEqual(caught.exception.code, ErrorCode.STORAGE_INSECURE)

    def test_a_directory_others_can_only_read_is_allowed(self) -> None:
        # Listing the filenames beside a 0600 database reveals nothing, so this
        # is not worth refusing to start over.
        nested = self.directory / "listable"
        nested.mkdir()
        os.chmod(nested, 0o755)

        self.assertTrue(DeviceStore(nested / "device-auth.sqlite3").path.exists())

    def test_a_database_readable_by_others_is_refused(self) -> None:
        self.store()
        os.chmod(self.database, 0o644)

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.STORAGE_INSECURE)


class SchemaVersionTests(StoreCase):
    def test_a_fresh_database_records_the_shipped_schema_version(self) -> None:
        self.store()

        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)

    def test_reopening_an_existing_database_keeps_its_rows(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = self.service().redeem_pairing_code(
            issued.code, client_id="198.51.100.4"
        )

        self.assertIsNotNone(outcome.token)
        self.assertEqual(len(self.service().devices()), 1)

    def test_a_newer_schema_version_is_refused_instead_of_guessed_at(self) -> None:
        self.store()
        with sqlite3.connect(self.database) as connection:
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.SCHEMA_UNSUPPORTED)

    def test_an_older_schema_version_is_refused_for_want_of_a_migration(self) -> None:
        self.store()
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 0")

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.SCHEMA_UNSUPPORTED)

    def test_a_missing_table_is_an_explicit_failure_not_an_empty_result(self) -> None:
        self.store()
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TABLE devices")

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.SCHEMA_UNSUPPORTED)

    def test_a_table_missing_a_column_is_an_explicit_failure(self) -> None:
        self.store()
        with sqlite3.connect(self.database) as connection:
            connection.execute("ALTER TABLE devices DROP COLUMN revoked_at")

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertEqual(caught.exception.code, ErrorCode.SCHEMA_UNSUPPORTED)


class ColdStartTests(StoreCase):
    def test_a_cold_database_opens_while_another_connection_holds_a_lock(self) -> None:
        # PRAGMA journal_mode needs an exclusive lock and does not wait on the
        # busy timeout, so two services opening a cold database at the same
        # moment — a host reboot — would both refuse to start over a setting
        # that is throughput, not correctness.
        self.store()
        with sqlite3.connect(self.database, isolation_level=None) as cold:
            cold.execute("PRAGMA journal_mode = DELETE")
        blocker = sqlite3.connect(self.database, isolation_level=None)
        self.addCleanup(blocker.close)
        blocker.execute("BEGIN")
        blocker.execute("SELECT count(*) FROM devices").fetchone()

        opened = DeviceStore(self.database, busy_timeout_seconds=0.2)

        self.assertEqual(opened.all_devices(), ())

    def test_the_schema_probe_reads_both_facts_in_one_snapshot(self) -> None:
        # user_version and the table list are two statements. Read outside a
        # transaction they can straddle another process committing the schema,
        # which comes back as "version 0, tables already present" and refuses
        # to start. The race is too narrow to catch by repetition alone, so the
        # invariant is observed directly: the probe runs inside a transaction.
        self.store()
        observed: list[bool] = []
        probe = DeviceStore._read_schema

        def watched(connection: sqlite3.Connection) -> tuple[int, set[str]]:
            observed.append(connection.in_transaction)
            return probe(connection)

        with mock.patch.object(DeviceStore, "_read_schema", staticmethod(watched)):
            DeviceStore(self.database)

        self.assertEqual(observed, [True])

    def test_many_writers_can_open_one_cold_database_at_once(self) -> None:
        # Two separate races live in this one moment: the journal-mode switch
        # and the schema probe. This is the integration check on both; the
        # deterministic detector for the second one is the test above.
        failures: list[str] = []
        lock = threading.Lock()

        def open_together(database: Path, writers: int) -> None:
            start = threading.Barrier(writers)

            def build() -> None:
                try:
                    start.wait(timeout=30)
                    DeviceStore(database)
                except BaseException as error:  # noqa: BLE001 - this is the report
                    with lock:
                        failures.append(repr(error))

            threads = [threading.Thread(target=build) for _ in range(writers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)

        for trial in range(12):
            open_together(self.directory / f"cold-{trial}.sqlite3", 12)

        self.assertEqual(failures, [])


class CorruptDatabaseTests(StoreCase):
    def corrupt(self) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.database) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        self.database.write_bytes(b"this is not a database" * 64)
        os.chmod(self.database, 0o600)

    def test_opening_a_corrupt_database_fails_loudly(self) -> None:
        self.store()
        self.corrupt()

        with self.assertRaises(DeviceAuthError) as caught:
            self.store()

        self.assertIn(
            caught.exception.code,
            {ErrorCode.STORAGE_UNREADABLE, ErrorCode.SCHEMA_UNSUPPORTED},
        )

    def test_a_directory_where_the_database_belongs_fails_loudly(self) -> None:
        occupied = self.directory / "occupied.sqlite3"
        occupied.mkdir()

        with self.assertRaises(DeviceAuthError):
            DeviceStore(occupied)


if __name__ == "__main__":
    unittest.main()
