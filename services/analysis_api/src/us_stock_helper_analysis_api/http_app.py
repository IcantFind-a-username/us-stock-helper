"""The HTTP surface for the decision chain.

Deliberately narrow: two GET paths, an explicit allowlist, and write methods
that fail closed. This service reads and explains; nothing here can act, and
the shape of the surface should make that obvious to anyone auditing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .service import AnalysisService


_PATHS = {"/health", "/decision"}
_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


@dataclass(frozen=True, slots=True)
class AnalysisApplication:
    service: AnalysisService
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc)

    def handle(
        self,
        method: str,
        path: str,
        query: Mapping[str, list[str]],
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        headers = dict(_HEADERS)
        if path not in _PATHS:
            return 404, headers, _error(
                "PATH_NOT_ALLOWED", "Path is not exposed by this read-only service"
            )
        if method != "GET":
            headers["Allow"] = "GET"
            return 405, headers, _error(
                "METHOD_NOT_ALLOWED", "Only read-only GET requests are supported"
            )
        if path == "/health":
            return 200, headers, {
                "status": "ready",
                "asOf": _iso(self.clock()),
            }

        try:
            symbol = _one(query, "symbol")
            horizon = _one(query, "horizon")
        except ValueError as error:
            return 400, headers, _error("INVALID_ARGUMENT", str(error))

        try:
            payload = self.service.decision(symbol, horizon)
        except ValueError as error:
            return 400, headers, _error("INVALID_ARGUMENT", str(error))
        except Exception:
            # Provider failures can carry credentials in their text; replace
            # the message rather than forwarding it.
            return 500, headers, _error(
                "ANALYSIS_FAILED", "The decision chain could not be evaluated"
            )
        return 200, headers, payload


def _one(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    if len(values) != 1 or not values[0].strip():
        raise ValueError(f"{key} must appear exactly once")
    return values[0].strip()


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
