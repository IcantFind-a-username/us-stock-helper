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

Two rules shape the reporting. A failure has to be locatable from the printed
output alone: the stage, the URL, the HTTP status, the service's own error code
and the local exception all go to stderr, because "smoke failed" sends the
reader back to a terminal to reproduce it. And a field that was never measured
is never reported as a zero: an indicator series that is empty because its
warm-up has not elapsed is a different fact from one that is empty because
nothing computed it, and the two are printed differently.

Read-only by construction: this reads two HTTP surfaces and runs the operator's
own pairing and revocation commands. There is no order path anywhere in it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
DEFAULT_ANALYSIS_URL = "http://192.168.0.59:8770"
DEFAULT_DEVICE_DATABASE = "~/.us-stock-helper/state/devices.sqlite3"
PAIRING_PATH = "/v1/device-pairings"

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
    """One named step of the live path, and everything known about why it failed.

    The fields are carried separately rather than folded into a message so that
    the renderer can state each one, including the ones that do not apply. A
    reader who sees `server_code: none` knows the service never answered; a
    reader who sees a message with no code cannot tell that from a code nobody
    bothered to print.
    """

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
        # Filled in when a run fails in more than one place. One stage is
        # raised, but the others have to travel with it: a reader who is told
        # only about the blamed stage will go and fix the wrong thing.
        self.also_failed: list[str] = []

    def summary(self) -> str:
        return (
            f"{self.stage} (http_status {_stated(self.http_status)},"
            f" server_code {_stated(self.server_code)})"
        )

    def render(self) -> str:
        lines = [
            f"FAIL stage={self.stage}",
            f"  detail: {self.detail}",
            f"  url: {_stated(self.url)}",
            f"  http_status: {_stated(self.http_status)}",
            f"  server_code: {_stated(self.server_code)}",
            f"  server_message: {_stated(self.server_message)}",
            f"  local_exception: {_exception_text(self.cause)}",
        ]
        if self.also_failed:
            lines.append(f"  also_failed: {'; '.join(self.also_failed)}")
        if self.hint:
            lines.append(f"  hint: {self.hint}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    gateway_url: str = DEFAULT_GATEWAY_URL
    analysis_url: str = DEFAULT_ANALYSIS_URL
    symbol: str = "NVDA"
    interval: str = "5m"
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


@dataclass(frozen=True, slots=True)
class SnapshotFacts:
    candle_count: int
    last_close: float
    recent_closes: tuple[float, ...]
    last_closed_at: datetime
    series_lengths: Mapping[str, int]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionFacts:
    score: float
    direction: str
    factor_coverage: float
    current_price: float | None
    cutoff: datetime


# --- the live transport ---------------------------------------------------


def http_transport(
    *,
    timeout: float = 10.0,
    opener: Callable[..., Any] = urlopen,
) -> Callable[..., Any]:
    """A JSON call that fails with the reason rather than with a category.

    urllib raises the same class for a refused connection and a refused
    request, and the service's own error code lives in the body of an exception
    most callers never read. Reading it here is what makes a 500 from the
    analysis chain distinguishable from an unreachable port.
    """

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
            with opener(prepared, timeout=timeout) as response:
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


def validate_snapshot(
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


def validate_decision(
    payload: Any,
    *,
    expected_symbol: str,
    expected_horizon: str,
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
    gateway = config.gateway_url.rstrip("/")
    analysis = config.analysis_url.rstrip("/")

    log(f"stage=gateway_health {gateway}/health")
    validate_gateway_health(
        request("gateway_health", "GET", f"{gateway}/health", token=config.gateway_token)
    )
    log("  gateway session: healthy")

    label = config.label or f"smoke-{_iso(datetime.now(tz=timezone.utc))}"
    log(f"stage=issue_pairing_code label={label}")
    code = issue_pairing_code(label)
    log("  pairing code issued (not printed here)")

    log(f"stage=redeem_pairing_code {analysis}{PAIRING_PATH}")
    device_id, token = _credential(
        request(
            "redeem_pairing_code",
            "POST",
            f"{analysis}{PAIRING_PATH}",
            body={"pairingCode": code},
        )
    )
    log(f"  paired device: {device_id}")

    failures: list[StageFailure] = []
    decision_facts: DecisionFacts | None = None
    snapshot_facts: SnapshotFacts | None = None

    try:
        log(f"stage=analysis_health {analysis}/health")
        validate_analysis_health(
            request("analysis_health", "GET", f"{analysis}/health", token=token)
        )
        log("  analysis service: ready, and it accepted this device token")

        query = urlencode({"symbol": config.symbol, "horizon": config.horizon})
        log(f"stage=decision {analysis}/decision?{query}")
        decision_facts = validate_decision(
            request("decision", "GET", f"{analysis}/decision?{query}", token=token),
            expected_symbol=config.symbol,
            expected_horizon=config.horizon,
        )
        log(
            f"  score: {decision_facts.score}"
            f"  direction: {decision_facts.direction}"
            f"  factorCoverage: {decision_facts.factor_coverage}"
        )
    except StageFailure as error:
        failures.append(error)
        log(error.render())

    # The gateway is read even after the decision failed. Which side broke is
    # the first question, and a report that says the decision was refused while
    # the gateway was serving candles answers it without a second run.
    snapshot_query = urlencode(
        {
            "symbol": config.symbol,
            "interval": config.interval,
            "count": config.count,
        }
    )
    try:
        log(f"stage=gateway_snapshot {gateway}/stock-snapshot?{snapshot_query}")
        snapshot_facts = validate_snapshot(
            request(
                "gateway_snapshot",
                "GET",
                f"{gateway}/stock-snapshot?{snapshot_query}",
                token=config.gateway_token,
            ),
            expected_symbol=config.symbol,
            expected_interval=config.interval,
        )
        log(f"  completed candles: {snapshot_facts.candle_count}")
        for name, length in snapshot_facts.series_lengths.items():
            log(f"  indicators.{name}: {length} values, candle-aligned")
        for note in snapshot_facts.notes:
            log(f"  note: {note}")
    except StageFailure as error:
        failures.append(error)
        log(error.render())

    _check_phone_gateway(config, request, log, failures)

    if not failures and decision_facts is not None and snapshot_facts is not None:
        try:
            log(f"  {cross_check_price(decision_facts, snapshot_facts)}")
        except StageFailure as error:
            failures.append(error)

    cleanup = _revoke(device_id, revoke_device, log)
    if cleanup is not None:
        failures.append(cleanup)

    if failures:
        raise _blame(failures)
    log(
        f"PASS symbol={config.symbol} horizon={config.horizon}"
        f" candles={snapshot_facts.candle_count if snapshot_facts else 0}"
        f" score={decision_facts.score if decision_facts else None}"
    )


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

    if not config.phone_gateway_url:
        log(
            "  phone-gateway: NOT CHECKED. The app reads candles from its own"
            " origin (see apps/mobile/.env), which is a different socket from"
            " the one the analysis service reads. Pass --phone-gateway-url and"
            " MOOMOO_GATEWAY_TOKEN to cover it."
        )
        return

    origin = config.phone_gateway_url.rstrip("/")
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
        log(f"stage=phone_gateway_snapshot {origin}/stock-snapshot?{query}")
        facts = validate_snapshot(
            request(
                "phone_gateway_snapshot",
                "GET",
                f"{origin}/stock-snapshot?{query}",
                token=config.phone_gateway_token,
            ),
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
) -> StageFailure | None:
    log(f"stage=revoke_smoke_device {device_id}")
    try:
        revoke_device(device_id)
    except StageFailure as error:
        log(error.render())
        return error
    except Exception as error:  # noqa: BLE001 - any failure here leaves a credential
        leftover = StageFailure(
            "revoke_smoke_device",
            f"the device this run paired ({device_id}) is still able to call the"
            " service; revoke it by hand",
            cause=error,
        )
        log(leftover.render())
        return leftover
    log(f"  revoked: {device_id}")
    return None


def _credential(payload: Any) -> tuple[str, str]:
    stage = "redeem_pairing_code"
    reply = _object(payload, stage, "pairing reply")
    device_id = reply.get("deviceId")
    token = reply.get("deviceToken")
    if not isinstance(device_id, str) or not device_id.strip():
        raise StageFailure(stage, "the pairing reply carries no deviceId")
    if not isinstance(token, str) or not token.strip():
        raise StageFailure(
            stage,
            "the pairing reply carries no deviceToken, so nothing can be"
            " authenticated with it",
        )
    return device_id, token


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
        default="5m",
        help=(
            "must match the interval the analysis service scores, otherwise the"
            " price cross-check compares different bars"
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="candles to request; match ANALYSIS_API_CANDLE_COUNT",
    )
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--analysis-url", default=DEFAULT_ANALYSIS_URL)
    parser.add_argument(
        "--phone-gateway-url",
        default=None,
        help=(
            "the origin the app reads candles from, which is not the one the"
            " analysis service reads; needs MOOMOO_GATEWAY_TOKEN. Reported as"
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
