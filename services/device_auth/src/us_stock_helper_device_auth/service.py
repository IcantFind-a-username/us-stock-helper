"""Pairing, verification and revocation.

The flow this implements is deliberately asymmetric. Issuing a pairing code is
a server-side act by someone already on the box, so it is a command-line call
that prints to the operator's terminal. Redeeming one is a call from the open
internet, so it is rate limited, single use, short lived, and tells the caller
nothing beyond "no".

Read-only by construction: a verified device id is the whole output of this
layer. Nothing here names an account, a broker or a position, and no field on
any result can carry one.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from .credentials import (
    DEFAULT_CODE_LENGTH,
    DEFAULT_SCRYPT,
    TOKEN_ALGORITHM,
    ScryptParameters,
    code_hash,
    format_code,
    format_token,
    generate_code,
    new_code_salt,
    new_device_id,
    new_token_salt,
    new_token_secret,
    normalize_code,
    split_token,
    token_hash,
)
from .errors import DeviceAuthError, ErrorCode
from .store import DeviceStore, PairingCodeRow
from .time_utils import from_storage, optional_from_storage, utc_now


MAX_CODE_TTL = timedelta(hours=1)
MAX_LIVE_CODES = 5

# One message for every way a pairing code can fail. Separating "already used"
# from "never existed" would tell an attacker which of their guesses were once
# real codes; the operator gets that distinction from the audit rows instead.
CODE_REFUSED = "the pairing code is not valid"
CODE_THROTTLED = "too many pairing attempts from this client"
TOKEN_REFUSED = "the device token is not valid"

# Compared against when no device row exists, so an unknown device id costs the
# same work as a wrong secret rather than answering measurably sooner.
_DECOY_SALT = new_token_salt()
_DECOY_DIGEST = secrets.token_bytes(32)


class AttemptOutcome(str, Enum):
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REUSED = "reused"
    UNKNOWN = "unknown"
    MALFORMED = "malformed"


class RevocationResult(str, Enum):
    REVOKED = "revoked"
    ALREADY_REVOKED = "already-revoked"
    UNKNOWN_DEVICE = "unknown-device"


@dataclass(frozen=True, slots=True)
class IssuedPairingCode:
    """The one moment the plaintext code exists; it is never stored or logged."""

    code: str
    label: str
    expires_at: datetime

    @property
    def formatted(self) -> str:
        return format_code(self.code)


@dataclass(frozen=True, slots=True)
class PairingOutcome:
    token: str | None
    device_id: str | None
    reason: str | None
    retry_after_seconds: int | None


@dataclass(frozen=True, slots=True)
class TokenVerification:
    device_id: str | None
    reason: str | None

    @property
    def authorized(self) -> bool:
        return self.device_id is not None


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: str
    name: str
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None


@dataclass(frozen=True, slots=True)
class PairingAttemptRecord:
    client_id: str
    attempted_at: datetime
    outcome: AttemptOutcome


@dataclass(frozen=True, slots=True)
class DeviceAuthService:
    store: DeviceStore
    clock: Callable[[], datetime] = utc_now
    code_ttl: timedelta = timedelta(minutes=10)
    code_length: int = DEFAULT_CODE_LENGTH
    pairing_attempt_limit: int = 5
    pairing_attempt_window: timedelta = timedelta(minutes=1)
    attempt_retention: timedelta = timedelta(days=1)
    code_retention: timedelta = timedelta(hours=1)
    scrypt: ScryptParameters = DEFAULT_SCRYPT

    # --- operator side ----------------------------------------------------

    def issue_pairing_code(self, *, label: str) -> IssuedPairingCode:
        if not timedelta(0) < self.code_ttl <= MAX_CODE_TTL:
            raise DeviceAuthError(
                ErrorCode.INVALID_ARGUMENT,
                "a pairing code lifetime must be positive and at most one hour",
            )
        checked = _require_text(label, "label", 64)
        now = self.clock()
        code = generate_code(self.code_length)
        salt = new_code_salt()
        self.store.insert_pairing_code(
            code_id=new_device_id(),
            salt=salt,
            digest=code_hash(code, salt, self.scrypt),
            kdf=self.scrypt.serialize(),
            label=checked,
            created_at=now,
            expires_at=now + self.code_ttl,
            live_code_limit=MAX_LIVE_CODES,
            retain_codes_for=self.code_retention,
        )
        return IssuedPairingCode(
            code=code, label=checked, expires_at=now + self.code_ttl
        )

    def revoke_device(self, device_id: str, *, reason: str) -> RevocationResult:
        checked_reason = _require_text(reason, "reason", 120)
        exists, changed = self.store.revoke_device(
            device_id=device_id, now=self.clock(), reason=checked_reason
        )
        if not exists:
            return RevocationResult.UNKNOWN_DEVICE
        return RevocationResult.REVOKED if changed else RevocationResult.ALREADY_REVOKED

    def devices(self) -> tuple[DeviceRecord, ...]:
        return tuple(
            DeviceRecord(
                device_id=row[0],
                name=row[1],
                created_at=from_storage(row[2], "created_at"),
                last_seen_at=optional_from_storage(row[3], "last_seen_at"),
                revoked_at=optional_from_storage(row[4], "revoked_at"),
                revoked_reason=row[5],
            )
            for row in self.store.all_devices()
        )

    def recent_pairing_attempts(
        self, client_id: str | None = None, *, limit: int = 50
    ) -> tuple[PairingAttemptRecord, ...]:
        return tuple(
            PairingAttemptRecord(
                client_id=row[0],
                attempted_at=from_storage(row[1], "attempted_at"),
                outcome=_read_outcome(row[2]),
            )
            for row in self.store.recent_attempts(client_id=client_id, limit=limit)
        )

    # --- device side ------------------------------------------------------

    def redeem_pairing_code(self, code: object, *, client_id: str) -> PairingOutcome:
        now = self.clock()
        slot = self.store.reserve_pairing_attempt(
            client_id=_require_text(client_id, "client_id", 100),
            now=now,
            limit=self.pairing_attempt_limit,
            window=self.pairing_attempt_window,
            retain_attempts_for=self.attempt_retention,
            # A crash between reserving the slot and recording the result must
            # leave the attempt counted as a failure, never as unused budget.
            pending_outcome=AttemptOutcome.UNKNOWN.value,
        )
        if slot.attempt_id is None:
            return PairingOutcome(None, None, CODE_THROTTLED, slot.retry_after_seconds)

        normalized = normalize_code(code)
        if normalized is None:
            return self._refuse(slot.attempt_id, AttemptOutcome.MALFORMED)

        matched = self._match_code(normalized, now)
        if matched is None:
            return self._refuse(slot.attempt_id, AttemptOutcome.UNKNOWN)
        if matched.consumed_at is not None:
            return self._refuse(slot.attempt_id, AttemptOutcome.REUSED)
        if from_storage(matched.expires_at, "expires_at") <= now:
            return self._refuse(slot.attempt_id, AttemptOutcome.EXPIRED)

        device_id = new_device_id()
        secret = new_token_secret()
        salt = new_token_salt()
        claimed = self.store.consume_code_and_register_device(
            code_id=matched.code_id,
            now=now,
            device_id=device_id,
            # The operator names the device when issuing the code, so no string
            # chosen by the caller ever reaches an operator listing.
            name=matched.label,
            salt=salt,
            digest=token_hash(salt, secret, TOKEN_ALGORITHM),
            algorithm=TOKEN_ALGORITHM,
        )
        if not claimed:
            return self._refuse(slot.attempt_id, AttemptOutcome.REUSED)

        self.store.record_attempt_outcome(
            slot.attempt_id, AttemptOutcome.ACCEPTED.value
        )
        return PairingOutcome(format_token(device_id, secret), device_id, None, None)

    def verify_token(self, token: object) -> TokenVerification:
        now = self.clock()
        parsed = split_token(token)
        if parsed is None:
            return TokenVerification(None, TOKEN_REFUSED)
        device_id, secret = parsed

        found = self.store.device_secret(device_id)
        salt = _DECOY_SALT if found is None else _require_blob(found.salt, "salt")
        expected = (
            _DECOY_DIGEST
            if found is None
            else _require_blob(found.token_hash, "token_hash")
        )
        algorithm = TOKEN_ALGORITHM if found is None else found.algorithm

        presented = token_hash(salt, secret, algorithm)
        # Both arguments are bytes: hmac.compare_digest raises TypeError on
        # non-ASCII str input, and a raise on this path is a crashed request
        # thread rather than a refusal.
        recognized = hmac.compare_digest(presented, expected)

        if found is None or not recognized or found.revoked_at is not None:
            return TokenVerification(None, TOKEN_REFUSED)
        self.store.touch_device(device_id, now)
        return TokenVerification(device_id, None)

    # --- internals --------------------------------------------------------

    def _refuse(self, attempt_id: int, outcome: AttemptOutcome) -> PairingOutcome:
        self.store.record_attempt_outcome(attempt_id, outcome.value)
        return PairingOutcome(None, None, CODE_REFUSED, None)

    def _match_code(self, normalized: str, now: datetime) -> PairingCodeRow | None:
        """Find the row this code belongs to, hashing every candidate either way.

        The loop does not stop early: returning as soon as a match is found
        would make the answer arrive measurably sooner for codes stored near
        the front of the table.
        """
        found = None
        for row in self.store.candidate_pairing_codes(
            now=now, retain_codes_for=self.code_retention
        ):
            digest = code_hash(
                normalized,
                _require_blob(row.salt, "salt"),
                ScryptParameters.parse(row.kdf),
            )
            if hmac.compare_digest(digest, _require_blob(row.code_hash, "code_hash")):
                found = row
        return found


def _require_text(value: object, label: str, max_length: int) -> str:
    """Reject anything that could rewrite the terminal it is printed to."""
    if not isinstance(value, str):
        raise DeviceAuthError(ErrorCode.INVALID_ARGUMENT, f"{label} must be text")
    stripped = value.strip()
    if not stripped or len(stripped) > max_length:
        raise DeviceAuthError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be 1-{max_length} characters",
        )
    if not stripped.isascii() or not stripped.isprintable():
        raise DeviceAuthError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be printable ASCII",
        )
    return stripped


def _require_blob(value: object, label: str) -> bytes:
    if not isinstance(value, bytes):
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            f"stored {label} is not a blob",
        )
    return value


def _read_outcome(value: object) -> AttemptOutcome:
    try:
        return AttemptOutcome(value)
    except ValueError as exc:
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            "a stored pairing attempt has an outcome this build cannot read",
        ) from exc
