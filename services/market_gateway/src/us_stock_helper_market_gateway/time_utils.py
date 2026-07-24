from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .errors import ErrorCode, GatewayError


UTC = timezone.utc
US_EASTERN = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def require_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            f"{label} is missing timezone information",
        )
    return value.astimezone(UTC)


def parse_aware(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        return require_utc(value, label)
    if not isinstance(value, str) or not value.strip():
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            f"{label} is not a timestamp",
        )
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            f"{label} is not a valid timestamp",
        ) from exc
    return require_utc(parsed, label)


def parse_exchange_time(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError as exc:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                f"{label} is not a valid exchange timestamp",
            ) from exc
    else:
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            f"{label} is not a timestamp",
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=US_EASTERN)
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")
