from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    STORAGE_INSECURE = "STORAGE_INSECURE"
    STORAGE_UNREADABLE = "STORAGE_UNREADABLE"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
    TOO_MANY_PAIRING_CODES = "TOO_MANY_PAIRING_CODES"


class DeviceAuthError(Exception):
    """An operational failure with a deliberately safe public representation.

    Every failure here is raised rather than returned as a falsy value, because
    the only alternative to a working credential store is refusing the request:
    an authentication layer that degrades to "allow" when its database is
    unreadable is worse than one that is simply down.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def public_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}
