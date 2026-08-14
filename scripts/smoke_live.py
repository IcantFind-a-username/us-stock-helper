#!/usr/bin/env python3
"""The live gate: walk the phone's own path against services that are running.

This exists because the in-process suites once certified a `/decision` route
that had never answered a real request. Every one of those tests injected a
provider, so nothing ever exercised the object the deployment actually builds,
and a missing method on it stayed invisible until a phone was in someone's
hand. A green suite is evidence about code; only this is evidence about the
deployment.

So nothing here is injected when it runs for real. It talks to the market
gateway and the analysis API over their own sockets, it earns a device token
the way the phone does — the operator terminal prints a pairing code, this
redeems it at `/v1/device-pairings` — and it reads `/decision` with that token
and nothing else. If any of that is faked, the gate is worth exactly as much as
the suite it exists to backstop.

Two rules shape the reporting. A failure is located with only a fixed local
stage, classification, and numeric HTTP status; response text, exception text,
credentials, environment values, and raw bodies never reach stdout, stderr, or
the JSON report. A field that was never measured is also never reported as a
zero: an indicator series that is empty because its warm-up has not elapsed is
a different fact from one that is empty because nothing computed it.

Read-only by construction: this reads two HTTP surfaces and runs the operator's
own pairing and revocation commands. There is no order path anywhere in it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
DEFAULT_ANALYSIS_URL = "http://192.168.0.59:8770"
DEFAULT_DEVICE_DATABASE = "~/.us-stock-helper/state/devices.sqlite3"
PAIRING_PATH = "/v1/device-pairings"
SNAPSHOT_PATHS = {
    "v2": "/stock-snapshot",
    "v3": "/v3/stock-snapshot",
}

V3_SECTION_NAMES = (
    "quote",
    "candles",
    "technical",
    "currentSessionFlow",
    "holdings",
    "fundamentals",
    "marketContext",
    "news",
    "forecastDecision",
)
V3_REQUESTED_SECTIONS = V3_SECTION_NAMES[:5]
V3_UNREQUESTED_SECTIONS = V3_SECTION_NAMES[5:]
V3_TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "status",
    "symbol",
    "interval",
    "count",
    "decisionCutoff",
    "requestedSections",
    "sections",
}
V3_ENVELOPE_FIELDS = {
    "availabilityStatus",
    "qualityStatus",
    "source",
    "asOf",
    "availableAt",
    "receivedAt",
    "data",
    "errorCode",
    "reason",
    "warnings",
    "anomalies",
    "methodVersion",
}
SAFE_SECTION_ERROR_CODES = frozenset(
    {
        "AUTH_REQUIRED",
        "CANDLES_UNAVAILABLE",
        "CLIENT_NOT_ALLOWED",
        "CURRENT_SESSION_FLOW_UNAVAILABLE",
        "HOLDINGS_UNAVAILABLE",
        "INVALID_ARGUMENT",
        "INVALID_NUMERIC_VALUE",
        "INVALID_REPORTING_PERIOD",
        "LOGIN_REQUIRED",
        "MALFORMED_PROVIDER_DATA",
        "METHOD_NOT_ALLOWED",
        "MISSING_REQUIRED_FIELD",
        "NOT_REQUESTED",
        "OPEND_OFFLINE",
        "ORIGIN_NOT_ALLOWED",
        "OUT_OF_ORDER_HOLDINGS_ROW",
        "PATH_NOT_ALLOWED",
        "PERMISSION_DENIED",
        "PROVIDER_ERROR",
        "QUOTA_EXCEEDED",
        "SDK_UNAVAILABLE",
        "SECTION_UNAVAILABLE",
        "STALE_DATA",
        "UNSUPPORTED_CAPABILITY",
        "WRONG_HOLDINGS_SOURCE",
        "FUTURE_HOLDINGS_ROW",
    }
)
SAFE_HOLDINGS_ANOMALY_CODES = frozenset(
    {
        "AGGREGATE_PERCENT_ABOVE_100",
        "FUTURE_HOLDINGS_ROW",
        "INVALID_NUMERIC_VALUE",
        "INVALID_REPORTING_PERIOD",
        "MISSING_REQUIRED_FIELD",
        "OUT_OF_ORDER_HOLDINGS_ROW",
        "WRONG_HOLDINGS_SOURCE",
    }
)
_US_WATCHLIST_CODE = re.compile(r"^US\.([A-Z][A-Z0-9.-]{0,9})$")
_STAGES = frozenset(
    {
        "gateway_health",
        "watchlist",
        "gateway_snapshot",
        "issue_pairing_code",
        "redeem_pairing_code",
        "analysis_health",
        "decision",
        "price_crosscheck",
        "phone_gateway_health",
        "phone_gateway_snapshot",
        "report_write",
        "report_path",
        "revoke_smoke_device",
    }
)
_CLASSIFICATIONS = frozenset(
    {
        "auth-failed",
        "contract-error",
        "http-error",
        "invalid-report-path",
        "io-error",
        "provider-quota",
        "service-unavailable",
        "stage-failed",
    }
)
_CLASSIFICATION_BY_SERVER_CODE = {
    "AUTH_REQUIRED": "auth-failed",
    "AUTH_UNAVAILABLE": "auth-failed",
    "CLIENT_NOT_ALLOWED": "auth-failed",
    "INVALID_PAIRING_CODE": "auth-failed",
    "PAIRING_UNAVAILABLE": "service-unavailable",
    "QUOTA_EXCEEDED": "provider-quota",
}

DIRECTIONS = frozenset({"bearish", "neutral", "bullish"})
# One snapshot of a thousand candles is well under a megabyte; the ceiling is
# here so a peer that never stops writing cannot exhaust this process.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# How far back a decision's price may sit in the candle series. The snapshot is
# read after the decision precisely so the decision cannot be ahead of it, and
# the only gap that remains is a bar or two closing between the two calls.
RECENT_CANDLES = 5

# Every drawable series, the fields it arrives in, and the number of candles
# below which it has nothing to say yet. The warm-ups are the published
# definitions of the indicators, and they are what separates "this could not be
# measured here" from "this was never measured" — the first is a note, the
# second fails the gate.
_SERIES_INDICATORS: dict[str, tuple[tuple[str, ...], int]] = {
    "ma5": (("series",), 5),
    "ma10": (("series",), 10),
    "ma20": (("series",), 20),
    "ma60": (("series",), 60),
    "rsi": (("series",), 15),
    "macd": (("lineSeries", "signalSeries", "histogramSeries"), 35),
}

# What each service's own error code means for whoever is reading the failure.
# The services deliberately sanitize their messages, so the pointer to where the
# real cause is written has to come from here.
_HINTS: dict[str, str] = {
    # Verified against the service rather than assumed: http_app turns every
    # provider exception into this code and silences the handler's own logging,
    # so there is no journal line to go and read. Sending the operator to look
    # for one wastes the trip; the only way to the traceback is to make the
    # same call in a process that does not swallow it.
    "ANALYSIS_FAILED": (
        "the analysis service converts every provider exception into this code"
        " and writes nothing to its own output, so no log holds the cause."
        " Reproduce it in-process with the deployment's own PYTHONPATH and"
        " ANALYSIS_API_* variables: AnalysisService(provider).decision(symbol,"
        " horizon), building the provider the way __main__ does"
    ),
    "AUTH_REQUIRED": (
        "a token this run had just been given was refused; check that the"
        " service's DEVICE_AUTH_DATABASE is the same file --device-database"
        " points at"
    ),
    "AUTH_UNAVAILABLE": (
        "the service cannot read its credential database; check ownership and"
        " mode of the file in DEVICE_AUTH_DATABASE"
    ),
    "PAIRING_UNAVAILABLE": (
        "the service cannot read its credential database, so no phone can pair"
        " with it right now"
    ),
    "CLIENT_NOT_ALLOWED": (
        "this machine's address is outside ANALYSIS_API_ALLOWED_CLIENTS"
    ),
    "PATH_NOT_ALLOWED": (
        "whatever answered on this port does not expose this route; confirm the"
        " port belongs to the service this stage is aimed at"
    ),
    "RATE_LIMITED": (
        "pairing attempts are throttled per caller; wait for the window to pass"
        " rather than retrying immediately"
    ),
    "INVALID_PAIRING_CODE": (
        "the code was refused; it is single use and short lived, so a rerun"
        " must issue a fresh one"
    ),
    "QUOTA_EXCEEDED": (
        "the upstream provider quota is spent, so the gateway has no candles to"
        " serve and everything that reads it fails with it. This is a rate"
        " problem, not a wiring problem: wait for the quota window rather than"
        " changing anything"
    ),
}

# Which stage to blame when several fail in one run, nearest the data first.
# A decision that cannot read candles fails because the gateway did, and a
# report that leads with the decision's own sanitized 500 sends the reader to
# the wrong service entirely — which is precisely how the quota exhaustion this
# ordering was written for got misread the first time.
_BLAME_ORDER = (
    "gateway_health",
    "gateway_snapshot",
    "issue_pairing_code",
    "redeem_pairing_code",
    "analysis_health",
    "decision",
    "price_crosscheck",
    "phone_gateway_health",
    "phone_gateway_snapshot",
    "revoke_smoke_device",
)


class StageFailure(Exception):
    """One named step with private diagnostics and a safe public rendering."""

    def __init__(
        self,
        stage: str,
        detail: str,
        *,
        url: str | None = None,
        http_status: int | None = None,
        server_code: str | None = None,
        server_message: str | None = None,
        cause: BaseException | None = None,
        hint: str | None = None,
        classification: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail
        self.url = url
        self.http_status = http_status
        self.server_code = server_code
        self.server_message = server_message
        self.cause = cause
        self.hint = hint or (_HINTS.get(server_code) if server_code else None)
        derived = _CLASSIFICATION_BY_SERVER_CODE.get(
            server_code or "",
            "http-error" if http_status is not None else "stage-failed",
        )
        selected = classification or derived
        self.classification = (
            selected if selected in _CLASSIFICATIONS else "stage-failed"
        )
        # Filled in when a run fails in more than one place. One stage is
        # raised, but the others have to travel with it: a reader who is told
        # only about the blamed stage will go and fix the wrong thing.
        self.also_failed: list[str] = []

    def summary(self) -> str:
        return (
            f"{self._safe_stage()} (classification {self.classification},"
            f" http_status {_stated(self.http_status)})"
        )

    def render(self) -> str:
        lines = [
            f"FAIL stage={self._safe_stage()}",
            f"  classification: {self.classification}",
            f"  http_status: {_stated(self.http_status)}",
        ]
        if self.also_failed:
            lines.append(f"  also_failed: {'; '.join(self.also_failed)}")
        return "\n".join(lines)

    def _safe_stage(self) -> str:
        return self.stage if self.stage in _STAGES else "unknown"


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    gateway_url: str = DEFAULT_GATEWAY_URL
    analysis_url: str = DEFAULT_ANALYSIS_URL
    symbol: str = "NVDA"
    interval: str = "day"
    horizon: str = "short"
    count: int = 200
    label: str | None = None
    gateway_token: str | None = None
    # The origin the app itself reads candles from, which is not the one the
    # analysis service reads: apps/mobile/.env points the phone at a LAN socket
    # with its own token, while the decision chain reads a loopback socket that
    # holds none. Both have to work for a phone to show a chart and a score,
    # and they can fail independently. Left unset this is reported as unchecked
    # rather than skipped in silence.
    phone_gateway_url: str | None = None
    phone_gateway_token: str | None = None
    all_watchlist: bool = False
    snapshot_version: str = "v2"
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SnapshotFacts:
    candle_count: int
    last_close: float
    recent_closes: tuple[float, ...]
    last_closed_at: datetime
    series_lengths: Mapping[str, int]
    notes: tuple[str, ...] = ()
    snapshot_status: str = "live"
    interval: str = ""
    section_statuses: Mapping[str, Mapping[str, str | None]] = field(
        default_factory=dict
    )
    holdings_quality: str | None = None
    holdings_anomalies: tuple[Mapping[str, Any], ...] = ()
    snapshot_version: str = "v2"


@dataclass(frozen=True, slots=True)
class DecisionFacts:
    score: float
    direction: str
    factor_coverage: float
    current_price: float | None
    cutoff: datetime
    interval: str = "day"


# --- the live transport ---------------------------------------------------


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        del new_url
        raise HTTPError(
            request.full_url,
            code,
            message,
            headers,
            file_pointer,
        )


def _strict_urlopen(request: Request, *, timeout: float) -> Any:
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def http_transport(
    *,
    timeout: float = 10.0,
    opener: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """A JSON call that fails with the reason rather than with a category.

    urllib raises the same class for a refused connection and a refused
    request, and the service's own error code lives in the body of an exception
    most callers never read. Reading it here is what makes a 500 from the
    analysis chain distinguishable from an unreachable port.
    """

    open_request = opener or _strict_urlopen

    def request(
        stage: str,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        prepared = Request(url, data=data, headers=headers, method=method)
        try:
            with open_request(prepared, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
        except HTTPError as error:
            code, message = _server_error(error)
            raise StageFailure(
                stage,
                f"the service refused this {method} request",
                url=url,
                http_status=error.code,
                server_code=code,
                server_message=message,
                cause=error,
            ) from error
        except (URLError, OSError) as error:
            raise StageFailure(
                stage,
                "the service could not be reached",
                url=url,
                cause=error,
            ) from error
        try:
            return json.loads(raw)
        except ValueError as error:
            raise StageFailure(
                stage,
                "the service answered with a body that is not JSON",
                url=url,
                cause=error,
            ) from error

    return request


def _server_error(error: HTTPError) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(error.read(MAX_RESPONSE_BYTES))
    except (OSError, ValueError):
        return None, None
    failure = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(failure, dict):
        return None, None
    code = failure.get("code")
    message = failure.get("message")
    return (
        code if isinstance(code, str) else None,
        message if isinstance(message, str) else None,
    )


# --- the operator terminal ------------------------------------------------


def operator_terminal(
    *,
    database: Path,
    repository_root: Path = REPOSITORY_ROOT,
    python: str = sys.executable,
    run: Callable[..., Any] = subprocess.run,
) -> tuple[Callable[[str], str], Callable[[str], None]]:
    """The two commands an operator would type, as callables.

    Pairing codes are printed to a terminal on the host and nowhere else, which
    is the whole point of the design, so the only honest way to obtain one is to
    run the command that prints it.
    """

    environment = {
        **os.environ,
        "PYTHONPATH": str(repository_root / "services/device_auth/src"),
    }

    def invoke(stage: str, arguments: Sequence[str]) -> str:
        command = [python, "-m", "us_stock_helper_device_auth", *arguments]
        try:
            completed = run(
                command,
                capture_output=True,
                text=True,
                env=environment,
                cwd=str(repository_root),
                timeout=30,
            )
        except OSError as error:
            raise StageFailure(
                stage,
                f"the device_auth command could not be run: {' '.join(command)}",
                cause=error,
            ) from error
        if completed.returncode != 0:
            raise StageFailure(
                stage,
                f"the device_auth terminal exited {completed.returncode}:"
                f" {' '.join(command)}",
                server_message=(completed.stderr or completed.stdout or "").strip()
                or None,
            )
        return completed.stdout or ""

    def issue(label: str) -> str:
        return parse_pairing_code(
            invoke(
                "issue_pairing_code",
                [
                    "pair",
                    "--database",
                    str(database),
                    "--label",
                    label,
                    # Short lived on purpose: the code is redeemed seconds later
                    # by the next stage, and a smoke run must not leave a usable
                    # code behind when it dies between the two.
                    "--ttl-minutes",
                    "5",
                ],
            )
        )

    def revoke(device_id: str) -> None:
        invoke(
            "revoke_smoke_device",
            [
                "revoke",
                "--database",
                str(database),
                device_id,
                "--reason",
                "issued by scripts/smoke_live.py and revoked at the end of the run",
            ],
        )

    return issue, revoke


def parse_pairing_code(printed: str) -> str:
    for line in printed.splitlines():
        if line.startswith("pairing-code:"):
            code = line.split(":", 1)[1].strip()
            if code:
                return code
    raise StageFailure(
        "issue_pairing_code",
        "the operator terminal printed no pairing code",
        # The command's own words are the diagnosis here, and they cannot
        # contain a code: this branch is reached only when no code line exists.
        server_message=printed.strip() or None,
    )


# --- what the live answers have to contain --------------------------------


def validate_gateway_health(payload: Any, *, stage: str = "gateway_health") -> None:
    health = _object(payload, stage, "health")
    if health.get("source") != "moomoo":
        raise StageFailure(stage, f"health names an unexpected source: {health.get('source')!r}")
    if health.get("session") != "healthy":
        raise StageFailure(
            stage,
            f"the gateway session is {health.get('session')!r} rather than healthy",
        )
    items = health.get("items")
    if not isinstance(items, list) or not items:
        raise StageFailure(stage, "health carries no per-connection items")
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("status") != "healthy":
            raise StageFailure(
                stage, f"health item {index} is {(item or {}).get('status')!r}"
            )


def validate_analysis_health(payload: Any) -> None:
    stage = "analysis_health"
    health = _object(payload, stage, "health")
    if health.get("status") != "ready":
        raise StageFailure(
            stage,
            f"the analysis service reports {health.get('status')!r} rather than ready",
        )


def validate_snapshot_v2(
    payload: Any,
    *,
    expected_symbol: str,
    expected_interval: str,
    stage: str = "gateway_snapshot",
) -> SnapshotFacts:
    """The candle series and every series drawn against it, or a named failure."""

    snapshot = _object(payload, stage, "snapshot")
    if snapshot.get("symbol") != expected_symbol.strip().upper():
        raise StageFailure(
            stage,
            f"the snapshot is for {snapshot.get('symbol')!r}, not"
            f" {expected_symbol.strip().upper()!r}",
        )
    if snapshot.get("interval") != expected_interval:
        raise StageFailure(
            stage,
            f"the snapshot interval is {snapshot.get('interval')!r}, not"
            f" {expected_interval!r}",
        )

    candles = snapshot.get("completedCandles")
    if not isinstance(candles, list):
        raise StageFailure(stage, "completedCandles is not an array")
    if not candles:
        raise StageFailure(
            stage,
            "completedCandles is empty: the gateway served no closed bar, so"
            " nothing downstream can be scored or drawn",
        )

    closes: list[float] = []
    previous: datetime | None = None
    for index, raw in enumerate(candles):
        label = f"completedCandles[{index}]"
        candle = _object(raw, stage, label)
        if candle.get("complete") is not True:
            raise StageFailure(stage, f"{label} is not complete")
        closed_at = _timestamp(candle.get("timestamp"), stage, f"{label}.timestamp")
        if previous is not None and closed_at <= previous:
            raise StageFailure(
                stage,
                f"{label} breaks the candle order: {closed_at.isoformat()} does not"
                f" follow {previous.isoformat()}",
            )
        close = _finite(candle.get("close"), stage, f"{label}.close")
        if close <= 0:
            raise StageFailure(stage, f"{label}.close is not positive: {close}")
        closes.append(close)
        previous = closed_at

    indicators = _object(snapshot.get("indicators"), stage, "indicators")
    lengths: dict[str, int] = {}
    notes: list[str] = []
    for name, (fields, warm_up) in _SERIES_INDICATORS.items():
        entry = indicators.get(name)
        if entry is None:
            raise StageFailure(
                stage, f"indicators.{name} is absent from the snapshot"
            )
        entry = _object(entry, stage, f"indicators.{name}")
        if entry.get("seriesAlignedTo") != "completedCandles":
            raise StageFailure(
                stage,
                f"indicators.{name} does not declare seriesAlignedTo="
                f"completedCandles (it says {entry.get('seriesAlignedTo')!r}), so"
                " no index in it can be tied to a bar",
            )
        for series_field in fields:
            values = entry.get(series_field)
            if not isinstance(values, list):
                raise StageFailure(
                    stage, f"indicators.{name}.{series_field} is not an array"
                )
            if len(values) != len(candles):
                raise StageFailure(
                    stage,
                    f"indicators.{name}.{series_field} carries {len(values)} values"
                    f" for {len(candles)} completed candles, so the chart would"
                    " draw it against the wrong bars",
                )
            measured = sum(1 for value in values if value is not None)
            lengths[f"{name}.{series_field}"] = len(values)
            if measured:
                continue
            # An empty series is either arithmetic that has not had enough bars
            # yet or an indicator nobody computed. Reporting both as "no data"
            # is exactly the confusion this gate exists to end.
            if len(candles) >= warm_up:
                raise StageFailure(
                    stage,
                    f"indicators.{name}.{series_field} holds no measured value"
                    f" across {len(candles)} candles, which is past its"
                    f" {warm_up}-candle warm-up: it was never computed",
                )
            notes.append(
                f"indicators.{name}.{series_field} is unmeasured at"
                f" {len(candles)} candles, below its {warm_up}-candle warm-up"
                " (not asserted, not treated as zero)"
            )

    return SnapshotFacts(
        candle_count=len(candles),
        last_close=closes[-1],
        recent_closes=tuple(closes[-RECENT_CANDLES:]),
        last_closed_at=previous or _timestamp(None, stage, "timestamp"),
        series_lengths=lengths,
        notes=tuple(notes),
    )


# Kept for callers of the original single-symbol smoke API.
validate_snapshot = validate_snapshot_v2


def validate_snapshot_v3(
    payload: Any,
    *,
    expected_symbol: str,
    expected_interval: str,
    expected_count: int,
    stage: str = "gateway_snapshot",
    now: datetime | None = None,
) -> SnapshotFacts:
    snapshot = _object(payload, stage, "snapshot")
    if set(snapshot) != V3_TOP_LEVEL_FIELDS:
        raise StageFailure(
            stage,
            "snapshot top-level fields mismatch",
            classification="contract-error",
        )
    if snapshot.get("schemaVersion") != "3":
        raise StageFailure(stage, "snapshot contract mismatch", classification="contract-error")
    symbol = expected_symbol.strip().upper()
    if snapshot.get("symbol") != symbol:
        raise StageFailure(stage, "snapshot symbol mismatch", classification="contract-error")
    if snapshot.get("interval") != expected_interval:
        raise StageFailure(stage, "snapshot interval mismatch", classification="contract-error")
    count = snapshot.get("count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count != expected_count
    ):
        raise StageFailure(stage, "snapshot count mismatch", classification="contract-error")
    cutoff = _timestamp(snapshot.get("decisionCutoff"), stage, "decisionCutoff")
    current_time = now or datetime.now(tz=timezone.utc)
    if cutoff > current_time:
        raise StageFailure(
            stage,
            "snapshot cutoff is in the future",
            classification="contract-error",
        )
    if snapshot.get("requestedSections") != list(V3_REQUESTED_SECTIONS):
        raise StageFailure(
            stage,
            "snapshot requested sections mismatch",
            classification="contract-error",
        )
    sections = _object(snapshot.get("sections"), stage, "sections")
    if set(sections) != set(V3_SECTION_NAMES):
        raise StageFailure(stage, "snapshot sections mismatch", classification="contract-error")

    section_statuses: dict[str, dict[str, str | None]] = {}
    envelopes: dict[str, dict[str, Any]] = {}
    for name in V3_SECTION_NAMES:
        envelope = _object(sections.get(name), stage, f"sections.{name}")
        if set(envelope) != V3_ENVELOPE_FIELDS:
            raise StageFailure(
                stage,
                "snapshot section envelope mismatch",
                classification="contract-error",
            )
        availability = envelope.get("availabilityStatus")
        quality = envelope.get("qualityStatus")
        if availability not in {"live", "delayed", "stale", "unavailable"}:
            raise StageFailure(stage, "snapshot availability invalid", classification="contract-error")
        if quality not in {"validated", "partial", "anomalous", "invalid"}:
            raise StageFailure(stage, "snapshot quality invalid", classification="contract-error")
        source = envelope.get("source")
        if source is not None and (
            not isinstance(source, str) or not source.strip()
        ):
            raise StageFailure(
                stage,
                "snapshot section source invalid",
                classification="contract-error",
            )
        method_version = envelope.get("methodVersion")
        if not isinstance(method_version, str) or not method_version.strip():
            raise StageFailure(
                stage,
                "snapshot section method invalid",
                classification="contract-error",
            )
        error_code = envelope.get("errorCode")
        if error_code is not None and (
            not isinstance(error_code, str) or not error_code.strip()
        ):
            raise StageFailure(stage, "snapshot error code invalid", classification="contract-error")
        if error_code is not None and error_code not in SAFE_SECTION_ERROR_CODES:
            raise StageFailure(stage, "snapshot error code unknown", classification="contract-error")
        reason = envelope.get("reason")
        if reason is not None and (
            not isinstance(reason, str) or not reason.strip()
        ):
            raise StageFailure(
                stage,
                "snapshot section reason invalid",
                classification="contract-error",
            )
        warnings = envelope.get("warnings")
        raw_anomalies = envelope.get("anomalies")
        if (
            not isinstance(warnings, list)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in warnings
            )
            or not isinstance(raw_anomalies, list)
        ):
            raise StageFailure(stage, "snapshot section arrays invalid", classification="contract-error")
        for anomaly in raw_anomalies:
            if not isinstance(anomaly, dict):
                raise StageFailure(
                    stage,
                    "snapshot section anomaly invalid",
                    classification="contract-error",
                )
            anomaly_code = anomaly.get("code")
            anomaly_reason = anomaly.get("reason")
            row_index = anomaly.get("rowIndex")
            if (
                not isinstance(anomaly_code, str)
                or not anomaly_code.strip()
                or not isinstance(anomaly_reason, str)
                or not anomaly_reason.strip()
                or (
                    "rowIndex" in anomaly
                    and (
                        isinstance(row_index, bool)
                        or not isinstance(row_index, (int, float))
                        or not math.isfinite(float(row_index))
                        or not float(row_index).is_integer()
                        or row_index < 0
                    )
                )
            ):
                raise StageFailure(
                    stage,
                    "snapshot section anomaly invalid",
                    classification="contract-error",
                )
        time_fields = ("asOf", "availableAt", "receivedAt")
        raw_times = {field: envelope.get(field) for field in time_fields}
        times = {
            field: _timestamp(value, stage, f"sections.{name}.{field}")
            for field, value in raw_times.items()
            if value is not None
        }
        if any(value > cutoff for value in times.values()):
            raise StageFailure(
                stage,
                "snapshot section time after cutoff",
                classification="contract-error",
            )
        if availability == "stale" and times:
            raise StageFailure(
                stage,
                "snapshot stale section time invalid",
                classification="contract-error",
            )
        if availability in {"live", "delayed"} and len(times) != len(time_fields):
            raise StageFailure(
                stage,
                "snapshot available section time incomplete",
                classification="contract-error",
            )
        for earlier, later in zip(time_fields, time_fields[1:]):
            if (
                earlier in times
                and later in times
                and times[earlier] > times[later]
            ):
                raise StageFailure(
                    stage,
                    "snapshot section time order invalid",
                    classification="contract-error",
                )
        data = envelope.get("data")
        state_invalid = False
        if availability in {"live", "delayed"}:
            state_invalid = (
                quality == "invalid"
                or source is None
                or len(times) != len(time_fields)
                or data is None
                or error_code is not None
                or reason is not None
            )
        elif availability == "stale":
            state_invalid = (
                quality != "invalid"
                or source is not None
                or bool(times)
                or data is not None
                or error_code is None
                or reason is None
            )
        else:
            state_invalid = (
                quality != "invalid"
                or (data is not None and data != [])
                or error_code is None
                or reason is None
            )
        if state_invalid:
            raise StageFailure(
                stage,
                "snapshot section availability state invalid",
                classification="contract-error",
            )
        envelopes[name] = envelope
        section_statuses[name] = {
            "availabilityStatus": availability,
            "qualityStatus": quality,
            "errorCode": error_code,
        }

    for name in V3_UNREQUESTED_SECTIONS:
        envelope = envelopes[name]
        if not (
            envelope["availabilityStatus"] == "unavailable"
            and envelope["qualityStatus"] == "invalid"
            and envelope["source"] is None
            and envelope["asOf"] is None
            and envelope["availableAt"] is None
            and envelope["receivedAt"] is None
            and envelope["data"] is None
            and envelope["errorCode"] == "NOT_REQUESTED"
            and envelope["warnings"] == []
            and envelope["anomalies"] == []
            and envelope["methodVersion"] == "unavailable-v1"
        ):
            raise StageFailure(stage, "unrequested section invalid", classification="contract-error")

    quote_price = _usable_v3_quote(envelopes["quote"], stage)
    quote = envelopes["quote"]
    if (
        quote["availabilityStatus"] in {"live", "delayed"}
        and quote["qualityStatus"] == "validated"
        and quote_price is None
    ):
        raise StageFailure(
            stage,
            "snapshot validated quote is unusable",
            classification="contract-error",
        )
    closes, last_closed_at = _usable_v3_candles(
        envelopes["candles"], cutoff, stage
    )
    holdings = envelopes["holdings"]
    if (
        holdings["availabilityStatus"] in {"live", "delayed"}
        and holdings["qualityStatus"] == "validated"
        and (
            not isinstance(holdings["data"], list)
            or not holdings["data"]
        )
    ):
        raise StageFailure(
            stage,
            "snapshot validated holdings are unusable",
            classification="contract-error",
        )
    if quote_price is None and not closes:
        raise StageFailure(stage, "snapshot has no usable price section", classification="contract-error")
    requested_valid = all(
        envelopes[name]["availabilityStatus"] in {"live", "delayed"}
        and envelopes[name]["qualityStatus"] == "validated"
        for name in V3_REQUESTED_SECTIONS
    ) and bool(closes)
    expected_status = "live" if requested_valid else "partial"
    if snapshot.get("status") != expected_status:
        raise StageFailure(stage, "snapshot status mismatch", classification="contract-error")

    anomalies: list[dict[str, Any]] = []
    for anomaly in holdings["anomalies"]:
        if not isinstance(anomaly, dict):
            raise StageFailure(stage, "holdings anomaly invalid", classification="contract-error")
        code = anomaly.get("code")
        row_index = anomaly.get("rowIndex")
        if not isinstance(code, str) or code not in SAFE_HOLDINGS_ANOMALY_CODES:
            raise StageFailure(stage, "holdings anomaly code invalid", classification="contract-error")
        safe = {"code": code}
        if row_index is not None:
            safe["rowIndex"] = int(row_index)
        anomalies.append(safe)

    price = closes[-1] if closes else quote_price
    assert price is not None
    return SnapshotFacts(
        candle_count=len(closes),
        last_close=price,
        recent_closes=tuple(closes[-RECENT_CANDLES:]),
        last_closed_at=last_closed_at or cutoff,
        series_lengths={},
        snapshot_status=expected_status,
        interval=expected_interval,
        section_statuses=section_statuses,
        holdings_quality=str(holdings["qualityStatus"]),
        holdings_anomalies=tuple(anomalies),
        snapshot_version="v3",
    )


def _usable_v3_quote(envelope: dict[str, Any], stage: str) -> float | None:
    if (
        envelope["availabilityStatus"] not in {"live", "delayed"}
        or envelope["qualityStatus"] != "validated"
        or not isinstance(envelope["data"], dict)
    ):
        return None
    try:
        price = _finite(envelope["data"].get("price"), stage, "quote.price")
    except StageFailure:
        return None
    return price if price > 0 else None


def _usable_v3_candles(
    envelope: dict[str, Any],
    cutoff: datetime,
    stage: str,
) -> tuple[list[float], datetime | None]:
    if (
        envelope["availabilityStatus"] not in {"live", "delayed"}
        or envelope["qualityStatus"] != "validated"
        or not isinstance(envelope["data"], dict)
    ):
        return [], None
    candles = envelope["data"].get("candles")
    if not isinstance(candles, list) or not candles:
        return [], None
    closes: list[float] = []
    previous: datetime | None = None
    for index, raw in enumerate(candles):
        candle = _object(raw, stage, f"sections.candles.data.candles[{index}]")
        if candle.get("complete") is not True:
            raise StageFailure(stage, "snapshot candle incomplete", classification="contract-error")
        closed_at = _timestamp(candle.get("timestamp"), stage, "candle.timestamp")
        if closed_at > cutoff or (previous is not None and closed_at <= previous):
            raise StageFailure(stage, "snapshot candle time invalid", classification="contract-error")
        close = _finite(candle.get("close"), stage, "candle.close")
        if close <= 0:
            raise StageFailure(stage, "snapshot candle close invalid", classification="contract-error")
        closes.append(close)
        previous = closed_at
    return closes, previous


def validate_watchlist(payload: Any) -> tuple[str, ...]:
    stage = "watchlist"
    watchlist = _object(payload, stage, "watchlist")
    if watchlist.get("schemaVersion") != "1" or watchlist.get("source") != "moomoo":
        raise StageFailure(stage, "watchlist envelope invalid", classification="contract-error")
    if watchlist.get("session") != "healthy":
        raise StageFailure(stage, "watchlist unavailable", classification="service-unavailable")
    items = watchlist.get("items")
    if not isinstance(items, list) or not items:
        raise StageFailure(stage, "watchlist is empty", classification="contract-error")
    symbols: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise StageFailure(stage, "watchlist item invalid", classification="contract-error")
        code = item.get("code")
        match = _US_WATCHLIST_CODE.fullmatch(code) if isinstance(code, str) else None
        if match is None or match.group(1) in seen:
            raise StageFailure(stage, "watchlist code invalid or duplicate", classification="contract-error")
        symbol = match.group(1)
        seen.add(symbol)
        symbols.append(symbol)
    return tuple(symbols)


def validate_decision(
    payload: Any,
    *,
    expected_symbol: str,
    expected_horizon: str,
    expected_interval: str | None = None,
) -> DecisionFacts:
    """The scored answer the phone renders, or a named failure."""

    stage = "decision"
    decision = _object(payload, stage, "decision")
    symbol = expected_symbol.strip().upper()
    if decision.get("symbol") != symbol:
        raise StageFailure(
            stage,
            f"the decision is for {decision.get('symbol')!r}, not {symbol!r}",
        )
    if decision.get("horizon") != expected_horizon:
        raise StageFailure(
            stage,
            f"the decision is for horizon {decision.get('horizon')!r}, not"
            f" {expected_horizon!r}",
        )
    interval = decision.get("interval")
    if expected_interval is not None and interval != expected_interval:
        raise StageFailure(
            stage,
            "the decision interval does not match the daily analysis basis",
            classification="contract-error",
        )

    status = decision.get("status")
    if status != "live":
        notes = decision.get("notes")
        stated = "; ".join(str(note) for note in notes) if isinstance(notes, list) else ""
        raise StageFailure(
            stage,
            f"the chain answered status={status!r} rather than live."
            f" It said: {stated or 'nothing'}",
            hint=(
                "an unavailable answer with a live gateway means the analysis"
                " service could not read candles from it; that link is the one"
                " no in-process test covers"
            ),
        )

    cutoff = _timestamp(decision.get("decisionCutoff"), stage, "decisionCutoff")
    score = decision.get("score")
    if not isinstance(score, dict):
        raise StageFailure(
            stage,
            "the decision carries no score block, so the phone has nothing to"
            f" show (score was {score!r})",
        )
    value = _finite(score.get("value"), stage, "score.value")
    direction = score.get("direction")
    if direction not in DIRECTIONS:
        raise StageFailure(
            stage,
            f"score.direction is {direction!r}, which is not one of"
            f" {sorted(DIRECTIONS)}",
        )
    coverage_raw = score.get("factorCoverage")
    if coverage_raw is None:
        raise StageFailure(
            stage,
            "score.factorCoverage was not measured, so how much of the model"
            " actually ran is unknown",
        )
    coverage = _finite(coverage_raw, stage, "score.factorCoverage")
    if not 0 < coverage <= 1:
        raise StageFailure(
            stage,
            f"score.factorCoverage is {coverage}: a decision scored on none of"
            " its factor weight is not a decision",
        )
    contributions = score.get("contributions")
    if not isinstance(contributions, list) or not contributions:
        raise StageFailure(
            stage,
            "score.contributions is empty, so the score cannot be explained or"
            " audited",
        )
    if not isinstance(score.get("methodVersion"), str) or not score["methodVersion"]:
        raise StageFailure(stage, "score.methodVersion is missing, so the answer is unversioned")
    if not isinstance(decision.get("baselineScore"), dict):
        raise StageFailure(
            stage,
            "baselineScore is absent, so an adjusted score cannot be compared"
            " with the objective one",
        )

    forecast = decision.get("forecast")
    current_price: float | None = None
    if isinstance(forecast, dict):
        current_price = _finite(forecast.get("currentPrice"), stage, "forecast.currentPrice")

    return DecisionFacts(
        score=value,
        direction=str(direction),
        factor_coverage=coverage,
        current_price=current_price,
        cutoff=cutoff,
        interval=str(interval or ""),
    )


def cross_check_price(decision: DecisionFacts, snapshot: SnapshotFacts) -> str:
    """Tie the decision's price back to a bar the gateway actually served.

    This is the one check a fixture cannot satisfy by accident. A decision that
    scores real candles prices itself off the last of them; one that is reading
    anything else will not land on a close the gateway is serving right now.
    """

    if decision.current_price is None:
        return (
            "price-crosscheck: not measured (the decision states no forecast, so"
            " it named no price to tie back to a candle)"
        )
    if not snapshot.recent_closes:
        return (
            "price-crosscheck: not measured (the snapshot has a usable quote but"
            " no completed candle to compare)"
        )
    for close in snapshot.recent_closes:
        if math.isclose(close, decision.current_price, rel_tol=1e-9, abs_tol=0.0):
            return (
                f"price-crosscheck: decision priced off {decision.current_price},"
                f" which is the close of a candle the gateway served"
            )
    raise StageFailure(
        "price_crosscheck",
        f"the decision priced off {decision.current_price}, which is not the"
        f" close of any of the last {len(snapshot.recent_closes)} completed"
        f" candles {list(snapshot.recent_closes)}",
        hint=(
            "the analysis service is not scoring the candles this gateway is"
            " serving; check ANALYSIS_API_GATEWAY_URL and the interval this"
            " script was run with"
        ),
    )


# --- the run --------------------------------------------------------------


def run_smoke(
    config: SmokeConfig,
    *,
    request: Callable[..., Any],
    issue_pairing_code: Callable[[str], str],
    revoke_device: Callable[[str], None],
    log: Callable[[str], None],
) -> None:
    report_path = _validated_report_path(config.report_path)
    if config.snapshot_version not in SNAPSHOT_PATHS:
        raise StageFailure(
            "gateway_snapshot",
            "snapshot version is unsupported",
            classification="contract-error",
        )
    gateway = _validated_origin(config.gateway_url, "gateway_health")
    analysis = _validated_origin(config.analysis_url, "analysis_health")
    phone_gateway = (
        _validated_origin(config.phone_gateway_url, "phone_gateway_health")
        if config.phone_gateway_url is not None
        else None
    )

    log(f"stage=gateway_health {gateway}/health")
    validate_gateway_health(
        request("gateway_health", "GET", f"{gateway}/health", token=config.gateway_token)
    )
    log("  gateway session: healthy")

    if config.all_watchlist:
        log(f"stage=watchlist {gateway}/watchlist")
        symbols = validate_watchlist(
            request(
                "watchlist",
                "GET",
                f"{gateway}/watchlist",
                token=config.gateway_token,
            )
        )
        log(f"  watchlist symbols: {len(symbols)}")
    else:
        symbols = (_canonical_request_symbol(config.symbol),)

    label = config.label or f"smoke-{_iso(datetime.now(tz=timezone.utc))}"
    log("stage=issue_pairing_code")
    code = issue_pairing_code(label)
    log("  pairing code issued (not printed here)")

    log(f"stage=redeem_pairing_code {analysis}{PAIRING_PATH}")
    pairing_reply = request(
        "redeem_pairing_code",
        "POST",
        f"{analysis}{PAIRING_PATH}",
        body={"pairingCode": code},
    )
    device_id = _device_id(pairing_reply)
    primary: BaseException | None = None
    cleanup: BaseException | None = None
    try:
        token = _device_token(pairing_reply)
        log("  paired device credential received")
        log(f"stage=analysis_health {analysis}/health")
        validate_analysis_health(
            request("analysis_health", "GET", f"{analysis}/health", token=token)
        )
        log("  analysis service: ready, and it accepted this device token")
        failures: list[StageFailure] = []
        report_items: list[dict[str, Any]] = []
        for symbol in symbols:
            decision_facts, decision_report = _read_decision(
                config,
                analysis,
                symbol,
                token,
                request,
                log,
                failures,
            )
            snapshot_facts, snapshot_report = _read_snapshot(
                config,
                gateway,
                symbol,
                request,
                log,
                failures,
            )
            if decision_facts is not None and snapshot_facts is not None:
                try:
                    result = cross_check_price(decision_facts, snapshot_facts)
                    log(f"  {result}")
                except StageFailure as error:
                    failures.append(error)
                    log(error.render())
            report_items.append(
                {
                    "symbol": symbol,
                    "snapshot": snapshot_report,
                    "decision": decision_report,
                }
            )

        if not config.all_watchlist:
            _check_phone_gateway(
                config,
                phone_gateway,
                request,
                log,
                failures,
            )

        if report_path is not None:
            _write_report(
                report_path,
                {
                    "schemaVersion": "1",
                    "snapshotVersion": config.snapshot_version,
                    "interval": config.interval,
                    "count": config.count,
                    "horizon": config.horizon,
                    "sourceCount": len(symbols),
                    "items": report_items,
                },
            )
            log(f"  report entries: {len(report_items)}")

        if failures:
            raise _blame(failures)
        log(
            f"PASS symbols={len(symbols)} horizon={config.horizon}"
            f" interval={config.interval} snapshot={config.snapshot_version}"
        )
    except BaseException as error:  # cleanup must also cover interrupts
        primary = error
    finally:
        cleanup = _revoke(device_id, revoke_device, log)

    if primary is not None:
        if isinstance(primary, StageFailure) and isinstance(cleanup, StageFailure):
            primary.also_failed.append(cleanup.summary())
        raise primary
    if cleanup is not None:
        raise cleanup


def _read_decision(
    config: SmokeConfig,
    analysis: str,
    symbol: str,
    token: str,
    request: Callable[..., Any],
    log: Callable[[str], None],
    failures: list[StageFailure],
) -> tuple[DecisionFacts | None, dict[str, Any]]:
    query = urlencode({"symbol": symbol, "horizon": config.horizon})
    log(f"stage=decision {analysis}/decision?{query}")
    try:
        facts = validate_decision(
            request("decision", "GET", f"{analysis}/decision?{query}", token=token),
            expected_symbol=symbol,
            expected_horizon=config.horizon,
            expected_interval="day",
        )
        log("  decision: live interval=day")
        return facts, {
            "httpStatus": 200,
            "status": "live",
            "score": facts.score,
            "factorCoverage": facts.factor_coverage,
            "interval": facts.interval,
        }
    except StageFailure as error:
        failures.append(error)
        log(error.render())
        return None, _failure_report(error)


def _read_snapshot(
    config: SmokeConfig,
    gateway: str,
    symbol: str,
    request: Callable[..., Any],
    log: Callable[[str], None],
    failures: list[StageFailure],
) -> tuple[SnapshotFacts | None, dict[str, Any]]:
    query = urlencode(
        {"symbol": symbol, "interval": config.interval, "count": config.count}
    )
    route = SNAPSHOT_PATHS[config.snapshot_version]
    url = f"{gateway}{route}?{query}"
    log(f"stage=gateway_snapshot {url}")
    try:
        payload = request(
            "gateway_snapshot",
            "GET",
            url,
            token=config.gateway_token,
        )
        if config.snapshot_version == "v3":
            facts = validate_snapshot_v3(
                payload,
                expected_symbol=symbol,
                expected_interval=config.interval,
                expected_count=config.count,
            )
        else:
            facts = validate_snapshot_v2(
                payload,
                expected_symbol=symbol,
                expected_interval=config.interval,
            )
        log(f"  completed candles: {facts.candle_count}")
        return facts, {
            "httpStatus": 200,
            "status": facts.snapshot_status,
            "interval": facts.interval,
            "candleCount": facts.candle_count,
            "sections": {
                name: dict(facts.section_statuses[name])
                for name in V3_SECTION_NAMES
                if name in facts.section_statuses
            },
            "holdings": {
                "qualityStatus": facts.holdings_quality,
                "anomalies": [dict(item) for item in facts.holdings_anomalies],
            },
        }
    except StageFailure as error:
        failures.append(error)
        log(error.render())
        return None, _failure_report(error)


def _failure_report(error: StageFailure) -> dict[str, Any]:
    return {
        "httpStatus": error.http_status,
        "classification": error.classification,
    }


def _validated_report_path(report_path: Path | None) -> Path | None:
    if report_path is None:
        return None
    resolved = report_path.expanduser().resolve(strict=False)
    tmp_root = Path("/tmp").resolve()
    if resolved == tmp_root or tmp_root not in resolved.parents:
        raise StageFailure(
            "report_path",
            "report must be written below /tmp",
            classification="invalid-report-path",
        )
    return resolved


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    previous_umask = os.umask(0o077)
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(report, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
    except (OSError, TypeError, ValueError) as error:
        raise StageFailure(
            "report_write",
            "the private report could not be written",
            cause=error,
            classification="io-error",
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.umask(previous_umask)


def _canonical_request_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.startswith("US."):
        normalized = normalized[3:]
    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized) is None:
        raise StageFailure(
            "gateway_snapshot",
            "request symbol is invalid",
            classification="contract-error",
        )
    return normalized


def _validated_origin(value: str, stage: str) -> str:
    if not isinstance(value, str) or not value or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise StageFailure(
            stage,
            "service origin is invalid",
            classification="contract-error",
        )
    normalized = value.rstrip("/")
    parsed = urlsplit(normalized)
    try:
        parsed.port
    except ValueError as error:
        raise StageFailure(
            stage,
            "service origin is invalid",
            classification="contract-error",
        ) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise StageFailure(
            stage,
            "service origin must be a credential-free HTTP(S) origin",
            classification="contract-error",
        )
    return normalized


def _blame(failures: list[StageFailure]) -> StageFailure:
    """The failure nearest the data, carrying the others with it."""

    ordered = sorted(
        failures,
        key=lambda item: (
            _BLAME_ORDER.index(item.stage) if item.stage in _BLAME_ORDER else len(_BLAME_ORDER)
        ),
    )
    primary, *rest = ordered
    primary.also_failed = [item.summary() for item in rest]
    return primary


def _check_phone_gateway(
    config: SmokeConfig,
    origin: str | None,
    request: Callable[..., Any],
    log: Callable[[str], None],
    failures: list[StageFailure],
) -> None:
    """Read candles from the origin the app reads them from, or say it was skipped.

    The decision chain and the phone reach the market gateway over different
    sockets with different credentials, so a chart can be empty on a real device
    while `/decision` answers perfectly. Leaving that leg unchecked is a
    defensible choice; leaving it unchecked quietly is the habit this gate
    exists to break, so the unchecked case is printed as loudly as a result.
    """

    if origin is None:
        log(
            "  phone-gateway: NOT CHECKED. The app reads candles from its own"
            " origin, which is a different socket from the one the analysis"
            " service reads. Pass the explicit phone gateway options to cover it."
        )
        return

    query = urlencode(
        {"symbol": config.symbol, "interval": config.interval, "count": config.count}
    )
    try:
        log(f"stage=phone_gateway_health {origin}/health")
        validate_gateway_health(
            request(
                "phone_gateway_health",
                "GET",
                f"{origin}/health",
                token=config.phone_gateway_token,
            ),
            stage="phone_gateway_health",
        )
        route = SNAPSHOT_PATHS[config.snapshot_version]
        log(f"stage=phone_gateway_snapshot {origin}{route}?{query}")
        payload = request(
            "phone_gateway_snapshot",
            "GET",
            f"{origin}{route}?{query}",
            token=config.phone_gateway_token,
        )
        if config.snapshot_version == "v3":
            facts = validate_snapshot_v3(
                payload,
                expected_symbol=config.symbol,
                expected_interval=config.interval,
                expected_count=config.count,
                stage="phone_gateway_snapshot",
            )
        else:
            facts = validate_snapshot_v2(
                payload,
                expected_symbol=config.symbol,
                expected_interval=config.interval,
                stage="phone_gateway_snapshot",
            )
        log(f"  completed candles the app would draw: {facts.candle_count}")
    except StageFailure as error:
        failures.append(error)
        log(error.render())


def _revoke(
    device_id: str,
    revoke_device: Callable[[str], None],
    log: Callable[[str], None],
) -> BaseException | None:
    log_failure = _cleanup_log(log, "stage=revoke_smoke_device")
    try:
        revoke_device(device_id)
    except StageFailure as error:
        _cleanup_log(log, error.render())
        return error
    except Exception as error:  # noqa: BLE001 - any failure here leaves a credential
        leftover = StageFailure(
            "revoke_smoke_device",
            f"the device this run paired ({device_id}) is still able to call the"
            " service; revoke it by hand",
            cause=error,
        )
        _cleanup_log(log, leftover.render())
        return leftover
    except BaseException as error:
        return error
    success_log_failure = _cleanup_log(log, "  paired smoke device revoked")
    return log_failure or success_log_failure


def _cleanup_log(
    log: Callable[[str], None],
    message: str,
) -> BaseException | None:
    try:
        log(message)
    except BaseException as error:  # revocation must not depend on its output sink
        return error
    return None


def _device_id(payload: Any) -> str:
    stage = "redeem_pairing_code"
    reply = _object(payload, stage, "pairing reply")
    device_id = reply.get("deviceId")
    if not isinstance(device_id, str) or not device_id.strip():
        raise StageFailure(stage, "the pairing reply carries no deviceId")
    return device_id


def _device_token(payload: Any) -> str:
    stage = "redeem_pairing_code"
    reply = _object(payload, stage, "pairing reply")
    token = reply.get("deviceToken")
    if not isinstance(token, str) or not token.strip():
        raise StageFailure(
            stage,
            "the pairing reply carries no deviceToken, so nothing can be"
            " authenticated with it",
        )
    return token


def _credential(payload: Any) -> tuple[str, str]:
    return _device_id(payload), _device_token(payload)


# --- entry point ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Walk the phone's path against the running services and fail if any"
            " part of it is not deliverable."
        )
    )
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--horizon", default="short", choices=("short", "swing", "long"))
    parser.add_argument(
        "--interval",
        default="day",
        help=(
            "must match the interval the analysis service scores, otherwise the"
            " price cross-check compares different bars"
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="candles to request; match the analysis service's configured count",
    )
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--analysis-url", default=DEFAULT_ANALYSIS_URL)
    parser.add_argument("--all-watchlist", action="store_true")
    parser.add_argument(
        "--snapshot-version",
        choices=("v2", "v3"),
        default="v2",
    )
    parser.add_argument("--report", default=None)
    parser.add_argument(
        "--phone-gateway-url",
        default=None,
        help=(
            "the origin the app reads candles from, which is not the one the"
            " analysis service reads; needs its private runtime token. Reported as"
            " NOT CHECKED when omitted"
        ),
    )
    parser.add_argument("--device-database", default=DEFAULT_DEVICE_DATABASE)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--label",
        default=None,
        help="how the paired device is listed; defaults to a timestamped name",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[..., None] = run_smoke,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    arguments = build_parser().parse_args(argv)
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    issue, revoke = operator_terminal(
        database=Path(arguments.device_database).expanduser()
    )
    config = SmokeConfig(
        gateway_url=arguments.gateway_url,
        analysis_url=arguments.analysis_url,
        symbol=arguments.symbol,
        interval=arguments.interval,
        horizon=arguments.horizon,
        count=arguments.count,
        label=arguments.label,
        gateway_token=os.environ.get("MOOMOO_GATEWAY_TOKEN") or None,
        phone_gateway_url=arguments.phone_gateway_url,
        phone_gateway_token=os.environ.get("MOOMOO_GATEWAY_TOKEN") or None,
        all_watchlist=arguments.all_watchlist,
        snapshot_version=arguments.snapshot_version,
        report_path=Path(arguments.report) if arguments.report else None,
    )
    try:
        runner(
            config,
            request=http_transport(timeout=arguments.timeout),
            issue_pairing_code=issue,
            revoke_device=revoke,
            # Flushed per line because the failure goes to stderr and the trail
            # leading to it goes to stdout. Left buffered, a redirected run
            # prints the verdict above the stages it came from, and the reader
            # has to reconstruct the order before they can trust either.
            log=lambda line: print(line, file=out, flush=True),
        )
    except StageFailure as failure:
        print(failure.render(), file=err, flush=True)
        return 1
    except KeyboardInterrupt:
        print(
            "FAIL stage=unknown\n  classification: stage-failed\n"
            "  http_status: none",
            file=err,
            flush=True,
        )
        return 1
    except Exception:
        print(
            "FAIL stage=unknown\n  classification: stage-failed\n"
            "  http_status: none",
            file=err,
            flush=True,
        )
        return 1
    return 0


# --- small readers --------------------------------------------------------


def _object(value: Any, stage: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StageFailure(stage, f"{label} is not a JSON object (it is {type(value).__name__})")
    return value


def _finite(value: Any, stage: str, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StageFailure(stage, f"{label} is not a number (got {value!r})")
    number = float(value)
    if not math.isfinite(number):
        raise StageFailure(stage, f"{label} is not finite (got {value!r})")
    return number


def _timestamp(value: Any, stage: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise StageFailure(stage, f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise StageFailure(
            stage, f"{label} is not an ISO-8601 timestamp (got {value!r})", cause=error
        ) from error
    if parsed.tzinfo is None:
        raise StageFailure(stage, f"{label} carries no timezone (got {value!r})")
    return parsed.astimezone(timezone.utc)


def _stated(value: Any) -> str:
    return "none" if value is None else str(value)


def _exception_text(error: BaseException | None) -> str:
    return "none" if error is None else f"{type(error).__name__}: {error}"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
