from __future__ import annotations

import re

from .errors import ErrorCode, GatewayError


_US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def to_moomoo_code(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise GatewayError(ErrorCode.INVALID_ARGUMENT, "US symbol is required")
    normalized = symbol.strip().upper()
    if normalized.startswith("US."):
        normalized = normalized[3:]
    elif "." in normalized and normalized.split(".", 1)[0] in {"HK", "SH", "SZ"}:
        raise GatewayError(
            ErrorCode.INVALID_ARGUMENT,
            "Only US market symbols are supported",
        )
    if not _US_SYMBOL.fullmatch(normalized):
        raise GatewayError(
            ErrorCode.INVALID_ARGUMENT,
            "US symbol has an unsupported format",
        )
    return f"US.{normalized}"


def from_moomoo_code(code: str) -> str:
    normalized = to_moomoo_code(code)
    return normalized[3:]
