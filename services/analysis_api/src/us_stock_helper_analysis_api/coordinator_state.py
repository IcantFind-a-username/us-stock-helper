"""Persist what each feed has already published, across process restarts.

`PollingCoordinator` can snapshot and restore itself, but `information_layer`
stays free of file I/O — the file lives here, at the process boundary that
owns the process's lifetime. Without this, every restart got an empty
coordinator and re-announced every item still inside each feed's lookback
window as brand-new, freshly stamped evidence.

The file is state, not truth: a malformed snapshot is rejected whole with a
named reason and a fresh coordinator (a partial load would silently replay
one feed's backlog), and a failed save degrades to exactly the pre-existing
behavior rather than failing the request that triggered it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from information_layer.feeds import PollingCoordinator


_PRIVATE_FILE_MODE = 0o600
_PRIVATE_DIRECTORY_MODE = 0o700


@dataclass(frozen=True, slots=True)
class CoordinatorStateStore:
    path: Path

    def load_coordinator(self) -> tuple[PollingCoordinator, str | None]:
        """A coordinator restored from disk, or a fresh one with the reason.

        Missing file is the ordinary first boot, not a fault; anything else
        that stops the restore is named so an operator can see why history
        was dropped.
        """

        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return PollingCoordinator(), None
        except OSError as error:
            return PollingCoordinator(), (
                f"coordinator state at {self.path} is unreadable"
                f" ({type(error).__name__}); starting with a fresh record"
            )
        try:
            snapshot = json.loads(raw)
            return PollingCoordinator.from_snapshot(snapshot), None
        except (json.JSONDecodeError, ValueError, TypeError) as error:
            return PollingCoordinator(), (
                f"coordinator state at {self.path} is malformed"
                f" ({error}); rejected whole, starting with a fresh record"
            )

    def save(self, coordinator: PollingCoordinator) -> str | None:
        """Write atomically (temp file + rename), mode 0600.

        Returns a named reason when the save could not happen; the caller's
        read must still be served — a persistence failure degrades to the
        old restart behavior, it must not take evidence offline.
        """

        try:
            self.path.parent.mkdir(
                mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True
            )
            payload = json.dumps(coordinator.snapshot())
            descriptor, temp_name = tempfile.mkstemp(
                dir=self.path.parent, prefix=".coordinator-", suffix=".tmp"
            )
            try:
                os.fchmod(descriptor, _PRIVATE_FILE_MODE)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(temp_name, self.path)
            except BaseException:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        except OSError as error:
            return (
                f"coordinator state at {self.path} could not be saved"
                f" ({type(error).__name__}); a restart will replay this window"
            )
        return None
