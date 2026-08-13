from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from us_stock_helper_device_auth import DeviceAuthService, DeviceStore, ScryptParameters


# Real scrypt parameters cost tens of milliseconds per candidate code, which
# turns the rate-limit and concurrency tests into minute-long runs. The cost
# factor is not what those tests are asserting, so they lower it; one test in
# test_credentials.py pins the shipped default instead.
FAST_SCRYPT = ScryptParameters(n=256, r=8, p=1)

START = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


class MovableClock:
    """A clock the tests advance by hand, so expiry is tested without sleeping."""

    def __init__(self, start: datetime = START) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class StoreCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="device-auth-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.database = self.directory / "device-auth.sqlite3"
        self.clock = MovableClock()

    def store(self) -> DeviceStore:
        return DeviceStore(self.database)

    def service(self, **overrides: Any) -> DeviceAuthService:
        defaults: dict[str, Any] = {
            "store": self.store(),
            "clock": self.clock,
            "scrypt": FAST_SCRYPT,
        }
        return DeviceAuthService(**{**defaults, **overrides})

    def stored_bytes(self) -> bytes:
        """Everything SQLite may be holding this database in, including sidecars."""
        blob = b""
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(str(self.database) + suffix)
            if candidate.exists():
                blob += candidate.read_bytes()
        return blob
