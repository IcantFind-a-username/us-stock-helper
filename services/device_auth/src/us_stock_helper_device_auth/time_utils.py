from __future__ import annotations

from datetime import datetime, timezone

from .errors import DeviceAuthError, ErrorCode


UTC = timezone.utc

# Fixed-width, so the stored text sorts and compares in SQLite exactly as the
# instants do. datetime.isoformat drops the fractional part on a whole second,
# which would put "…T09:00:00Z" after "…T09:00:00.5Z" in the rate-limit window
# query and quietly hand an attacker extra attempts.
_STORAGE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def require_utc(value: datetime, label: str = "timestamp") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DeviceAuthError(
            ErrorCode.INVALID_ARGUMENT,
            f"{label} must be an aware datetime",
        )
    return value.astimezone(UTC)


def to_storage(value: datetime, label: str = "timestamp") -> str:
    return require_utc(value, label).strftime(_STORAGE_FORMAT)


def from_storage(value: object, label: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            f"{label} is not stored as text",
        )
    try:
        return datetime.strptime(value, _STORAGE_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            f"{label} is not a stored timestamp",
        ) from exc


def optional_from_storage(value: object, label: str = "timestamp") -> datetime | None:
    return None if value is None else from_storage(value, label)
