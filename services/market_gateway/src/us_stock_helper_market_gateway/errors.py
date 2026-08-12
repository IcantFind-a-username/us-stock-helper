from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SDK_UNAVAILABLE = "SDK_UNAVAILABLE"
    OPEND_OFFLINE = "OPEND_OFFLINE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    STALE_DATA = "STALE_DATA"
    MALFORMED_PROVIDER_DATA = "MALFORMED_PROVIDER_DATA"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CLIENT_NOT_ALLOWED = "CLIENT_NOT_ALLOWED"
    ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"
    AUTH_REQUIRED = "AUTH_REQUIRED"


ERROR_SESSION = {
    ErrorCode.INVALID_ARGUMENT: "invalid-argument",
    ErrorCode.SDK_UNAVAILABLE: "sdk-unavailable",
    ErrorCode.OPEND_OFFLINE: "offline",
    ErrorCode.LOGIN_REQUIRED: "login-required",
    ErrorCode.PERMISSION_DENIED: "permission-denied",
    ErrorCode.QUOTA_EXCEEDED: "quota-exceeded",
    ErrorCode.STALE_DATA: "stale",
    ErrorCode.MALFORMED_PROVIDER_DATA: "malformed",
    ErrorCode.PROVIDER_ERROR: "provider-error",
    ErrorCode.UNSUPPORTED_CAPABILITY: "unsupported-capability",
    ErrorCode.PATH_NOT_ALLOWED: "path-not-allowed",
    ErrorCode.METHOD_NOT_ALLOWED: "method-not-allowed",
    ErrorCode.CLIENT_NOT_ALLOWED: "client-not-allowed",
    ErrorCode.ORIGIN_NOT_ALLOWED: "origin-not-allowed",
    ErrorCode.AUTH_REQUIRED: "auth-required",
}


class GatewayError(Exception):
    """An operational failure with a deliberately safe public representation."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retriable = retriable
        self.details = details or {}

    @property
    def session(self) -> str:
        return ERROR_SESSION[self.code]

    def public_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retriable": self.retriable,
        }


class PointInTimeViolation(GatewayError):
    """Data that claims to exist after the moment being decided for.

    Kept apart from ordinary malformed data because the handling differs: a
    broken or absent feed may degrade one section of a snapshot to
    "unavailable", while data from the future invalidates the snapshot's
    point-in-time claim outright and must never be softened into an absence.
    Its public representation is identical, so callers see no new error code.
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.MALFORMED_PROVIDER_DATA, message)
