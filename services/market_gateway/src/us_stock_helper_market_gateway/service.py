from __future__ import annotations

import math
import time
from concurrent.futures import (
    Executor,
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable

from . import snapshot as snapshot_v2
from .errors import ErrorCode, GatewayError, PointInTimeViolation
from .models import ProviderBatch, QuoteProvider, SessionHealth
from .snapshot import assemble_stock_snapshot
from .snapshot_v3 import (
    SnapshotSection,
    assemble_stock_snapshot_v3,
    normalize_holdings_v3,
)
from .symbols import from_moomoo_code, to_moomoo_code
from .time_utils import iso_z, parse_aware, require_utc, utc_now


SNAPSHOT_SOURCE_TIMEOUT_SECONDS = 5.0
SNAPSHOT_DEADLINE_SECONDS = 12.0
SNAPSHOT_MAX_PROVIDER_OPERATIONS = 4

_SNAPSHOT_INTERVALS = {"1m", "5m", "15m", "30m", "60m", "day", "week"}
_UNREQUESTED_V3_SECTIONS = (
    "fundamentals",
    "marketContext",
    "news",
    "forecastDecision",
)


class MarketGatewayService:
    """Validates point-in-time provider data and emits the mobile JSON contract."""

    def __init__(
        self,
        provider: QuoteProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
        session_max_age: timedelta = timedelta(seconds=15),
        response_max_age: timedelta = timedelta(seconds=30),
        monotonic: Callable[[], float] = time.monotonic,
        source_timeout_seconds: float = SNAPSHOT_SOURCE_TIMEOUT_SECONDS,
        snapshot_deadline_seconds: float = SNAPSHOT_DEADLINE_SECONDS,
        executor_factory: Callable[[int], Executor] = ThreadPoolExecutor,
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._session_max_age = session_max_age
        self._response_max_age = response_max_age
        self._monotonic = monotonic
        self._source_timeout_seconds = source_timeout_seconds
        self._snapshot_deadline_seconds = snapshot_deadline_seconds
        self._executor_factory = executor_factory

    def health(self) -> dict[str, Any]:
        started_at = require_utc(self._clock(), "clock")
        health = self._safe_health(started_at)
        observed_at = require_utc(self._clock(), "clock")
        state = self._health_state(health, observed_at)
        response = self._envelope(
            session=state,
            as_of=health.checked_at,
            available_at=max(observed_at, health.checked_at),
            items=[{"status": state}],
        )
        if state != "healthy":
            code = health.error_code or self._code_for_health_state(state)
            response["error"] = GatewayError(
                code,
                self._message_for_code(code),
                retriable=code
                in {
                    ErrorCode.OPEND_OFFLINE,
                    ErrorCode.QUOTA_EXCEEDED,
                    ErrorCode.STALE_DATA,
                },
            ).public_dict()
        return response

    def watchlist(self, group: str | None = None) -> dict[str, Any]:
        return self._execute(
            lambda: self._provider.watchlist(group),
            self._normalize_quotes,
        )

    def quotes(self, symbols: list[str]) -> dict[str, Any]:
        try:
            if not symbols or len(symbols) > 100:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Provide between 1 and 100 US symbols",
                )
            codes = [to_moomoo_code(symbol) for symbol in symbols]
        except GatewayError as error:
            return self._error_envelope(error)
        return self._execute(
            lambda: self._provider.quotes(codes),
            self._normalize_quotes,
        )

    def candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
            if timeframe not in {"1m", "5m", "15m", "30m", "60m", "day", "week"}:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Unsupported candle interval",
                )
            if not isinstance(count, int) or not 1 <= count <= 1000:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Candle count must be between 1 and 1000",
                )
        except GatewayError as error:
            return self._error_envelope(error)

        response = self._execute(
            lambda: self._provider.candles(code, timeframe, count),
            self._normalize_candles,
        )
        response["symbol"] = from_moomoo_code(code)
        response["interval"] = timeframe
        return response

    def capital_flow(self, symbol: str) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
        except GatewayError as error:
            return self._error_envelope(error)
        response = self._execute(
            lambda: self._provider.capital_flow(code),
            lambda items, now: self._normalize_capital_flow(
                items, now, expected_code=code
            ),
        )
        response.update(
            {
                "symbol": from_moomoo_code(code),
                "semantics": "large-order-flow-proxy",
                "institutionalIdentity": False,
            }
        )
        return response

    def capital_distribution(self, symbol: str) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
        except GatewayError as error:
            return self._error_envelope(error)
        response = self._execute(
            lambda: self._provider.capital_distribution(code),
            self._normalize_capital_distribution,
        )
        response.update(
            {
                "symbol": from_moomoo_code(code),
                "semantics": "order-size-distribution-proxy",
                "institutionalIdentity": False,
            }
        )
        return response

    def institutional_holdings(self, symbol: str) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
        except GatewayError as error:
            return self._error_envelope(error)
        response = self._execute(
            lambda: self._provider.institutional_holdings(code),
            self._normalize_institutional_holdings,
        )
        response.update(
            {
                "symbol": from_moomoo_code(code),
                "semantics": "delayed-reported-holdings",
            }
        )
        return response

    def stock_snapshot(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
            if timeframe not in {"1m", "5m", "15m", "30m", "60m", "day", "week"}:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Unsupported candle interval",
                )
            if not isinstance(count, int) or not 1 <= count <= 1000:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Candle count must be between 1 and 1000",
                )
        except GatewayError as error:
            return self._snapshot_error(error, symbol=symbol, interval=timeframe)

        started_at = require_utc(self._clock(), "clock")
        health = self._safe_health(started_at)
        observed_at = require_utc(self._clock(), "clock")
        state = self._health_state(health, observed_at)
        if state != "healthy":
            code_for_state = health.error_code or self._code_for_health_state(state)
            return self._snapshot_error(
                GatewayError(
                    code_for_state,
                    self._message_for_code(code_for_state),
                    retriable=code_for_state
                    in {
                        ErrorCode.OPEND_OFFLINE,
                        ErrorCode.QUOTA_EXCEEDED,
                        ErrorCode.STALE_DATA,
                    },
                ),
                symbol=from_moomoo_code(code),
                interval=timeframe,
                now=observed_at,
            )

        try:
            quote_batch = self._provider.quotes([code])
            candle_batch = self._provider.candles(code, timeframe, count)
            flow_batch = self._provider.capital_flow(code)
            holding_batch = self._provider.institutional_holdings(code)
        except GatewayError as error:
            return self._snapshot_error(
                GatewayError(
                    error.code,
                    self._message_for_code(error.code),
                    retriable=error.retriable,
                ),
                symbol=from_moomoo_code(code),
                interval=timeframe,
            )
        except Exception:
            return self._snapshot_error(
                GatewayError(
                    ErrorCode.PROVIDER_ERROR,
                    "Market data provider request failed",
                    retriable=True,
                ),
                symbol=from_moomoo_code(code),
                interval=timeframe,
            )

        completed_at = require_utc(self._clock(), "clock")
        try:
            self._validate_batch(quote_batch, completed_at)
            self._validate_batch(candle_batch, completed_at)
            self._validate_batch(holding_batch, completed_at)
            # A stale, absent or malformed capital-flow feed degrades that one
            # section to unavailable. Data from after the cutoff does not: it
            # voids the snapshot's point-in-time claim and must surface.
            try:
                flow_received = self._validate_batch(flow_batch, completed_at)
            except PointInTimeViolation:
                raise
            except GatewayError:
                flow_received = None
            decision_cutoff = completed_at
            quote_items = self._normalize_quotes(quote_batch.items, decision_cutoff)
            candle_items = self._normalize_candles(candle_batch.items, decision_cutoff)
            holding_items = self._normalize_institutional_holdings(
                holding_batch.items,
                decision_cutoff,
            )
            try:
                flow_items = (
                    self._normalize_capital_flow(
                        flow_batch.items,
                        decision_cutoff,
                        expected_code=code,
                    )
                    if flow_received is not None
                    else []
                )
            except PointInTimeViolation:
                raise
            except GatewayError:
                flow_items = []
            return assemble_stock_snapshot(
                symbol=from_moomoo_code(code),
                interval=timeframe,
                decision_cutoff=decision_cutoff,
                quote_items=quote_items,
                candle_items=candle_items,
                flow_items=flow_items,
                holding_items=holding_items,
            )
        except GatewayError as error:
            return self._snapshot_error(
                GatewayError(
                    error.code,
                    self._message_for_code(
                        error.code, "Market data failed point-in-time validation"
                    ),
                    retriable=error.retriable,
                ),
                symbol=from_moomoo_code(code),
                interval=timeframe,
                now=completed_at,
            )
        except (TypeError, ValueError):
            return self._snapshot_error(
                GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Market data could not be assembled safely",
                ),
                symbol=from_moomoo_code(code),
                interval=timeframe,
                now=completed_at,
            )

    def stock_snapshot_v3(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> dict[str, Any]:
        try:
            code = to_moomoo_code(symbol)
            if timeframe not in _SNAPSHOT_INTERVALS:
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Unsupported candle interval",
                )
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or not 1 <= count <= 1000
            ):
                raise GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Candle count must be between 1 and 1000",
                )
        except GatewayError as error:
            return self._snapshot_error(error, symbol=symbol, interval=timeframe)

        started_at = require_utc(self._clock(), "clock")
        health = self._safe_health(started_at)
        observed_at = require_utc(self._clock(), "clock")
        health_state = self._health_state(health, observed_at)
        normalized_symbol = from_moomoo_code(code)
        if health_state != "healthy":
            health_code = health.error_code or self._code_for_health_state(health_state)
            return assemble_stock_snapshot_v3(
                normalized_symbol,
                timeframe,
                count,
                observed_at,
                self._unhealthy_snapshot_v3_sections(health_code),
            )

        requested_at = self._monotonic()
        batches, failures = self._collect_snapshot_v3_batches(
            code,
            timeframe,
            count,
            requested_at,
        )
        try:
            decision_cutoff = require_utc(self._clock(), "clock")
        except (AttributeError, GatewayError, TypeError):
            return self._snapshot_error(
                GatewayError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Decision cutoff must include timezone information",
                ),
                symbol=normalized_symbol,
                interval=timeframe,
                now=observed_at,
            )

        sections = self._snapshot_v3_sections(
            normalized_symbol,
            code,
            timeframe,
            decision_cutoff,
            batches,
            failures,
        )
        return assemble_stock_snapshot_v3(
            normalized_symbol,
            timeframe,
            count,
            decision_cutoff,
            sections,
        )

    def _collect_snapshot_v3_batches(
        self,
        code: str,
        timeframe: str,
        count: int,
        requested_at: float,
    ) -> tuple[dict[str, ProviderBatch], dict[str, str]]:
        operations: tuple[tuple[str, Callable[[], ProviderBatch]], ...] = (
            ("quote", lambda: self._provider.quotes([code])),
            ("candles", lambda: self._provider.candles(code, timeframe, count)),
            ("flow", lambda: self._provider.capital_flow(code)),
            ("holdings", lambda: self._provider.institutional_holdings(code)),
        )
        executor = self._executor_factory(SNAPSHOT_MAX_PROVIDER_OPERATIONS)
        submitted: list[tuple[str, float, Future[ProviderBatch]]] = []
        batches: dict[str, ProviderBatch] = {}
        failures: dict[str, str] = {}
        completion_times: dict[str, float] = {}
        completion_lock = Lock()
        try:
            for name, operation in operations:
                submitted_at = self._monotonic()

                def timed_operation(
                    operation: Callable[[], ProviderBatch] = operation,
                    name: str = name,
                ) -> ProviderBatch:
                    try:
                        return operation()
                    finally:
                        completed_at = self._monotonic()
                        with completion_lock:
                            completion_times[name] = completed_at

                future = executor.submit(timed_operation)
                submitted.append((name, submitted_at, future))

            overall_deadline = requested_at + self._snapshot_deadline_seconds
            for name, submitted_at, future in submitted:
                now = self._monotonic()
                source_deadline = submitted_at + self._source_timeout_seconds
                completion_deadline = min(source_deadline, overall_deadline)
                remaining = completion_deadline - now
                if remaining <= 0 and not future.done():
                    failures[name] = ErrorCode.PROVIDER_ERROR.value
                    continue
                try:
                    batch = future.result(timeout=max(0.0, remaining))
                except FutureTimeoutError:
                    failures[name] = ErrorCode.PROVIDER_ERROR.value
                    continue
                except GatewayError as error:
                    failure_code = error.code.value
                except Exception:
                    failure_code = ErrorCode.PROVIDER_ERROR.value
                else:
                    failure_code = None
                with completion_lock:
                    completed_at = completion_times.get(name)
                if completed_at is None or completed_at > completion_deadline:
                    failures[name] = ErrorCode.PROVIDER_ERROR.value
                elif failure_code is not None:
                    failures[name] = failure_code
                else:
                    batches[name] = batch
        finally:
            for _, _, future in submitted:
                if not future.done():
                    future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        return batches, failures

    def _snapshot_v3_sections(
        self,
        symbol: str,
        code: str,
        timeframe: str,
        decision_cutoff: datetime,
        batches: dict[str, ProviderBatch],
        failures: dict[str, str],
    ) -> dict[str, SnapshotSection]:
        sections = {
            name: self._not_requested_snapshot_v3_section()
            for name in _UNREQUESTED_V3_SECTIONS
        }
        sections["quote"] = self._snapshot_v3_source_section(
            "quote",
            failures,
            lambda: self._quote_snapshot_v3_section(
                symbol,
                batches["quote"],
                decision_cutoff,
            ),
        )
        sections["candles"] = self._snapshot_v3_source_section(
            "candles",
            failures,
            lambda: self._candles_snapshot_v3_section(
                symbol,
                timeframe,
                batches["candles"],
                decision_cutoff,
            ),
        )
        sections["technical"] = self._technical_snapshot_v3_section(
            symbol,
            timeframe,
            sections["candles"],
            decision_cutoff,
        )
        sections["currentSessionFlow"] = self._snapshot_v3_source_section(
            "flow",
            failures,
            lambda: self._flow_snapshot_v3_section(
                code,
                batches["flow"],
                decision_cutoff,
            ),
        )
        sections["holdings"] = self._snapshot_v3_source_section(
            "holdings",
            failures,
            lambda: self._holdings_snapshot_v3_section(
                batches["holdings"],
                decision_cutoff,
            ),
        )
        return sections

    def _snapshot_v3_source_section(
        self,
        name: str,
        failures: dict[str, str],
        build: Callable[[], SnapshotSection],
    ) -> SnapshotSection:
        if name in failures:
            return self._unavailable_snapshot_v3_section(name, failures[name])
        try:
            return build()
        except GatewayError as error:
            return self._unavailable_snapshot_v3_section(name, error.code.value)
        except (KeyError, TypeError, ValueError):
            return self._unavailable_snapshot_v3_section(
                name,
                ErrorCode.MALFORMED_PROVIDER_DATA.value,
            )
        except Exception:
            return self._unavailable_snapshot_v3_section(
                name,
                ErrorCode.PROVIDER_ERROR.value,
            )

    def _quote_snapshot_v3_section(
        self,
        symbol: str,
        batch: ProviderBatch,
        decision_cutoff: datetime,
    ) -> SnapshotSection:
        received_at = self._validate_batch(batch, decision_cutoff)
        items = self._normalize_quotes(batch.items, decision_cutoff)
        quote = snapshot_v2._quote(symbol, items, decision_cutoff)
        as_of = parse_aware(quote["asOf"], "quote asOf")
        available_at = parse_aware(quote["availableAt"], "quote availableAt")
        return SnapshotSection(
            availability_status="live",
            quality_status="validated",
            source="moomoo",
            as_of=as_of,
            available_at=available_at,
            received_at=received_at,
            data=quote,
            error_code=None,
            reason=None,
            method_version="provider-quote-v1",
        )

    def _candles_snapshot_v3_section(
        self,
        symbol: str,
        timeframe: str,
        batch: ProviderBatch,
        decision_cutoff: datetime,
    ) -> SnapshotSection:
        received_at = self._validate_batch(batch, decision_cutoff)
        normalized = self._normalize_candles(batch.items, decision_cutoff)
        candles = snapshot_v2._candles(
            symbol,
            timeframe,
            normalized,
            decision_cutoff,
        )
        as_of = (
            parse_aware(candles[-1]["asOf"], "candle asOf") if candles else received_at
        )
        available_at = max(
            (
                parse_aware(item["availableAt"], "candle availableAt")
                for item in candles
            ),
            default=received_at,
        )
        return SnapshotSection(
            availability_status="live",
            quality_status="validated",
            source="moomoo",
            as_of=as_of,
            available_at=available_at,
            received_at=received_at,
            data={
                "candles": candles,
                "priceAdjustment": snapshot_v2._price_adjustment(candles),
            },
            error_code=None,
            reason=None,
            method_version="provider-completed-candle-v1",
        )

    def _technical_snapshot_v3_section(
        self,
        symbol: str,
        timeframe: str,
        candle_section: SnapshotSection,
        decision_cutoff: datetime,
    ) -> SnapshotSection:
        candle_data = candle_section.data
        candles = (
            candle_data.get("candles")
            if candle_section.quality_status == "validated"
            and isinstance(candle_data, dict)
            else None
        )
        if not isinstance(candles, list) or not candles:
            return self._unavailable_snapshot_v3_section(
                "technical",
                "CANDLES_UNAVAILABLE",
            )
        try:
            bars = snapshot_v2._analysis_bars(symbol, timeframe, candles)
            all_indicators = snapshot_v2._indicators(
                candles,
                decision_cutoff,
                bars,
            )
            magic_nine = all_indicators["magicNine"]
            indicators = {
                name: value
                for name, value in all_indicators.items()
                if name != "magicNine"
            }
            as_of = parse_aware(candles[-1]["asOf"], "technical asOf")
        except (GatewayError, KeyError, TypeError, ValueError):
            return self._unavailable_snapshot_v3_section(
                "technical",
                "CANDLES_UNAVAILABLE",
            )
        return SnapshotSection(
            availability_status="live",
            quality_status="validated",
            source="analysis-core",
            as_of=as_of,
            available_at=decision_cutoff,
            received_at=decision_cutoff,
            data={
                "indicators": indicators,
                "magicNine": magic_nine,
            },
            error_code=None,
            reason=None,
            method_version="analysis-core-indicators-v1",
        )

    def _flow_snapshot_v3_section(
        self,
        code: str,
        batch: ProviderBatch,
        decision_cutoff: datetime,
    ) -> SnapshotSection:
        received_at = self._validate_batch(batch, decision_cutoff)
        flow_items = self._normalize_capital_flow(
            batch.items,
            decision_cutoff,
            expected_code=code,
        )
        if not flow_items:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Current-session flow is unavailable",
            )
        return SnapshotSection(
            availability_status="live",
            quality_status="validated",
            source="moomoo",
            as_of=max(
                parse_aware(item["timestamp"], "flow timestamp")
                for item in flow_items
            ),
            available_at=max(
                parse_aware(item["availableAt"], "flow availableAt")
                for item in flow_items
            ),
            received_at=received_at,
            data=flow_items,
            error_code=None,
            reason=None,
            method_version="provider-capital-flow-normalized-v1",
        )

    def _holdings_snapshot_v3_section(
        self,
        batch: ProviderBatch,
        decision_cutoff: datetime,
    ) -> SnapshotSection:
        received_at = self._validate_holdings_snapshot_v3_batch(
            batch,
            decision_cutoff,
        )
        return normalize_holdings_v3(
            batch.items,
            decision_cutoff,
            received_at,
        )

    def _validate_holdings_snapshot_v3_batch(
        self,
        batch: ProviderBatch,
        decision_cutoff: datetime,
    ) -> datetime:
        if not isinstance(batch, ProviderBatch) or batch.source != "moomoo":
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Live response did not identify moomoo as its source",
            )
        received_at = require_utc(batch.received_at, "holdings received_at")
        if received_at > decision_cutoff:
            raise PointInTimeViolation(
                "Provider holdings response is timestamped in the future"
            )
        if decision_cutoff - received_at > self._response_max_age:
            raise GatewayError(
                ErrorCode.STALE_DATA,
                "Market data response is stale",
                retriable=True,
            )
        if not isinstance(batch.items, list):
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Provider items are malformed",
            )
        return received_at

    def _unhealthy_snapshot_v3_sections(
        self,
        error_code: ErrorCode,
    ) -> dict[str, SnapshotSection]:
        sections = {
            name: self._not_requested_snapshot_v3_section()
            for name in _UNREQUESTED_V3_SECTIONS
        }
        sections["quote"] = self._unavailable_snapshot_v3_section(
            "quote", error_code.value
        )
        sections["candles"] = self._unavailable_snapshot_v3_section(
            "candles", error_code.value
        )
        sections["technical"] = self._unavailable_snapshot_v3_section(
            "technical", "CANDLES_UNAVAILABLE"
        )
        sections["currentSessionFlow"] = self._unavailable_snapshot_v3_section(
            "flow", error_code.value
        )
        sections["holdings"] = self._unavailable_snapshot_v3_section(
            "holdings", error_code.value
        )
        return sections

    @staticmethod
    def _unavailable_snapshot_v3_section(
        name: str,
        error_code: str,
    ) -> SnapshotSection:
        public_error_code = (
            "CURRENT_SESSION_FLOW_UNAVAILABLE" if name == "flow" else error_code
        )
        reason = {
            "quote": "实时报价不可用",
            "candles": "已完成蜡烛图数据不可用",
            "technical": "技术指标需要已验证的蜡烛图数据",
            "flow": "当前交易时段资金流数据不可用",
            "holdings": "机构持仓数据不可用",
        }[name]
        return SnapshotSection(
            availability_status=(
                "stale" if error_code == ErrorCode.STALE_DATA.value else "unavailable"
            ),
            quality_status="invalid",
            source=None,
            as_of=None,
            available_at=None,
            received_at=None,
            data=None,
            error_code=public_error_code,
            reason=reason,
        )

    @staticmethod
    def _not_requested_snapshot_v3_section() -> SnapshotSection:
        return SnapshotSection(
            availability_status="unavailable",
            quality_status="invalid",
            source=None,
            as_of=None,
            available_at=None,
            received_at=None,
            data=None,
            error_code="NOT_REQUESTED",
            reason="此切片未请求该数据",
        )

    def _execute(
        self,
        operation: Callable[[], ProviderBatch],
        normalizer: Callable[[list[dict[str, Any]], datetime], list[dict[str, Any]]],
    ) -> dict[str, Any]:
        started_at = require_utc(self._clock(), "clock")
        health = self._safe_health(started_at)
        observed_at = require_utc(self._clock(), "clock")
        state = self._health_state(health, observed_at)
        if state != "healthy":
            code = health.error_code or self._code_for_health_state(state)
            return self._error_envelope(
                GatewayError(
                    code,
                    self._message_for_code(code),
                    retriable=code
                    in {
                        ErrorCode.OPEND_OFFLINE,
                        ErrorCode.QUOTA_EXCEEDED,
                        ErrorCode.STALE_DATA,
                    },
                ),
                now=observed_at,
            )

        try:
            batch = operation()
        except GatewayError as error:
            return self._error_envelope(error)
        except Exception:
            return self._error_envelope(
                GatewayError(
                    ErrorCode.PROVIDER_ERROR,
                    "Unexpected market data provider failure",
                    retriable=True,
                )
            )

        completed_at = require_utc(self._clock(), "clock")
        try:
            received_at = self._validate_batch(batch, completed_at)
            items = normalizer(batch.items, completed_at)
            item_times = [
                parse_aware(item["availableAt"], "item.availableAt")
                for item in items
            ]
            as_of = max(item_times, default=received_at)
            if as_of > received_at:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider item arrived after its response",
                )
            return self._envelope(
                session="healthy",
                as_of=as_of,
                available_at=received_at,
                items=items,
            )
        except GatewayError as error:
            return self._error_envelope(error, now=completed_at)
        except Exception:
            return self._error_envelope(
                GatewayError(
                    ErrorCode.PROVIDER_ERROR,
                    "Unexpected market data provider failure",
                    retriable=True,
                ),
                now=completed_at,
            )

    def _validate_batch(self, batch: ProviderBatch, now: datetime) -> datetime:
        if not isinstance(batch, ProviderBatch) or batch.source != "moomoo":
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Live response did not identify moomoo as its source",
            )
        received_at = require_utc(batch.received_at, "provider received_at")
        if received_at > now:
            raise PointInTimeViolation(
                "Provider response is timestamped in the future"
            )
        if now - received_at > self._response_max_age:
            raise GatewayError(
                ErrorCode.STALE_DATA,
                "Market data response is stale",
                retriable=True,
            )
        if not isinstance(batch.items, list):
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Provider items are malformed",
            )
        return received_at

    def _normalize_quotes(
        self,
        items: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        normalized = []
        seen: set[str] = set()
        for item in items:
            try:
                code = to_moomoo_code(item["code"])
                price = self._number(item["price"], "price")
                change = self._number(item["change_percent"], "change_percent")
                available_at = parse_aware(item["available_at"], "available_at")
            except (KeyError, TypeError, GatewayError) as exc:
                if isinstance(exc, GatewayError):
                    raise GatewayError(
                        ErrorCode.MALFORMED_PROVIDER_DATA,
                        "Provider quote is malformed",
                    ) from exc
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider quote is missing required fields",
                ) from exc
            if code in seen or price <= 0 or available_at > now:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider quote failed point-in-time validation",
                )
            seen.add(code)
            normalized.append(
                {
                    "code": code,
                    "price": price,
                    "changePercent": change,
                    "availableAt": iso_z(available_at),
                }
            )
        return normalized

    def _normalize_candles(
        self,
        items: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        previous: datetime | None = None
        for item in items:
            try:
                complete = item["complete"]
                timestamp = parse_aware(item["timestamp"], "timestamp")
                available_at = parse_aware(item["available_at"], "available_at")
                open_price = self._number(item["open"], "open")
                high = self._number(item["high"], "high")
                low = self._number(item["low"], "low")
                close = self._number(item["close"], "close")
                volume = self._number(item["volume"], "volume")
            except (KeyError, TypeError, GatewayError) as exc:
                if isinstance(exc, GatewayError):
                    raise
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider candle is missing required fields",
                ) from exc
            if not isinstance(complete, bool):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider candle completion state is malformed",
                )
            if not complete:
                continue
            if available_at > now:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider candle failed point-in-time validation",
                )
            if (
                timestamp > available_at
                or (previous is not None and timestamp <= previous)
                or min(open_price, high, low, close) <= 0
                or volume < 0
                or high < max(open_price, close)
                or low > min(open_price, close)
                or high < low
            ):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider candle failed point-in-time validation",
                )
            # No fallback: substituting availableAt would invent the earliest,
            # most permissive receipt time and disable the cutoff check for any
            # provider that simply omits the field.
            received_at = parse_aware(item["received_at"], "received_at")
            if received_at < available_at or received_at > now:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider candle receipt time failed point-in-time validation",
                )
            previous = timestamp
            normalized.append(
                {
                    "timestamp": iso_z(timestamp),
                    "availableAt": iso_z(available_at),
                    "receivedAt": iso_z(received_at),
                    "priceAdjustment": self._adjustment(item),
                    "complete": True,
                    "code": item.get("code"),
                    "timeframe": item.get("timeframe"),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
        return normalized

    def _normalize_capital_flow(
        self,
        items: list[dict[str, Any]],
        now: datetime,
        *,
        expected_code: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized = []
        previous: datetime | None = None
        for item in items:
            try:
                timestamp = parse_aware(item["timestamp"], "timestamp")
                available_at = parse_aware(item["available_at"], "available_at")
                session = item["session"]
                total = self._number(item["total_net"], "total_net")
                super_net = self._number(item["super_net"], "super_net")
                big_net = self._number(item["big_net"], "big_net")
                mid_net = self._number(item["mid_net"], "mid_net")
                small_net = self._number(item["small_net"], "small_net")
            except (KeyError, TypeError, GatewayError) as exc:
                if isinstance(exc, GatewayError):
                    raise
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital-flow row is missing required fields",
                ) from exc
            if not isinstance(session, str) or not session.strip():
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital-flow row is missing session metadata",
                )
            if expected_code is not None and item.get("code") != expected_code:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital-flow row does not match the requested symbol",
                )
            if available_at > now:
                raise PointInTimeViolation(
                    "Provider capital-flow row is available after the decision cutoff"
                )
            if timestamp > available_at or (
                previous is not None and timestamp <= previous
            ):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital-flow row failed point-in-time validation",
                )
            previous = timestamp
            normalized.append(
                {
                    "timestamp": iso_z(timestamp),
                    "availableAt": iso_z(available_at),
                    "session": session,
                    "totalNetFlow": total,
                    "extraLargeOrderNetFlow": super_net,
                    "largeOrderNetFlow": big_net,
                    "mediumOrderNetFlow": mid_net,
                    "smallOrderNetFlow": small_net,
                    "largeOrderProxyNetFlow": super_net + big_net,
                    "institutionalIdentity": False,
                }
            )
        return normalized

    def _normalize_capital_distribution(
        self,
        items: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        normalized = []
        for item in items:
            try:
                available_at = parse_aware(item["available_at"], "available_at")
                super_in = self._number(item["super_in"], "super_in")
                super_out = self._number(item["super_out"], "super_out")
                big_in = self._number(item["big_in"], "big_in")
                big_out = self._number(item["big_out"], "big_out")
                mid_in = self._number(item["mid_in"], "mid_in")
                mid_out = self._number(item["mid_out"], "mid_out")
                small_in = self._number(item["small_in"], "small_in")
                small_out = self._number(item["small_out"], "small_out")
            except (KeyError, TypeError, GatewayError) as exc:
                if isinstance(exc, GatewayError):
                    raise
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital distribution is missing required fields",
                ) from exc
            if available_at > now or min(
                super_in,
                super_out,
                big_in,
                big_out,
                mid_in,
                mid_out,
                small_in,
                small_out,
            ) < 0:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Provider capital distribution failed validation",
                )
            normalized.append(
                {
                    "availableAt": iso_z(available_at),
                    "extraLargeOrderInflow": super_in,
                    "extraLargeOrderOutflow": super_out,
                    "extraLargeOrderNetFlow": super_in - super_out,
                    "largeOrderInflow": big_in,
                    "largeOrderOutflow": big_out,
                    "largeOrderNetFlow": big_in - big_out,
                    "mediumOrderInflow": mid_in,
                    "mediumOrderOutflow": mid_out,
                    "mediumOrderNetFlow": mid_in - mid_out,
                    "smallOrderInflow": small_in,
                    "smallOrderOutflow": small_out,
                    "smallOrderNetFlow": small_in - small_out,
                    "institutionalIdentity": False,
                }
            )
        return normalized

    def _normalize_institutional_holdings(
        self,
        items: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        normalized = []
        previous_available: datetime | None = None
        for item in items:
            try:
                period = item["period"]
                reported_at = parse_aware(item["reported_at"], "reported_at")
                available_at = parse_aware(item["available_at"], "available_at")
                source = item["source"]
                institution_count = self._number(
                    item["institution_count"],
                    "institution_count",
                )
                institution_change = self._number(
                    item["institution_count_change"],
                    "institution_count_change",
                )
                shares = self._number(item["shares_held"], "shares_held")
                shares_change = self._number(
                    item["shares_held_change"],
                    "shares_held_change",
                )
                holding_percent = self._number(
                    item["holding_percent"],
                    "holding_percent",
                )
                holding_percent_change = self._number(
                    item["holding_percent_change"],
                    "holding_percent_change",
                )
            except (KeyError, TypeError, GatewayError) as exc:
                if isinstance(exc, GatewayError):
                    raise
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Institutional disclosure is missing required fields",
                ) from exc
            if (
                not isinstance(period, str)
                or not period
                or source != "moomoo-delayed-institutional-disclosure"
                or reported_at > available_at
                or available_at > now
                or institution_count < 0
                or shares < 0
                or not 0 <= holding_percent <= 100
                or (
                    previous_available is not None
                    and available_at > previous_available
                )
            ):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Institutional disclosure failed point-in-time validation",
                )
            previous_available = available_at
            normalized.append(
                {
                    "period": period,
                    "reportedAt": iso_z(reported_at),
                    "reportedAtBasis": "reporting-period-end",
                    "availableAt": iso_z(available_at),
                    "source": source,
                    "institutionCount": int(institution_count),
                    "institutionCountChange": int(institution_change),
                    "sharesHeld": shares,
                    "sharesHeldChange": shares_change,
                    "holdingPercent": holding_percent,
                    "holdingPercentChange": holding_percent_change,
                }
            )
        return normalized

    def _safe_health(self, now: datetime) -> SessionHealth:
        try:
            health = self._provider.health()
            if not isinstance(health, SessionHealth):
                raise TypeError("health contract")
            return SessionHealth(
                state=health.state,
                checked_at=require_utc(health.checked_at, "health checked_at"),
                source=health.source,
                error_code=health.error_code,
            )
        except GatewayError as error:
            return SessionHealth(
                state=error.session.replace("-", "_"),
                checked_at=now,
                source="moomoo",
                error_code=error.code,
            )
        except Exception:
            return SessionHealth(
                state="malformed",
                checked_at=now,
                source="moomoo",
                error_code=ErrorCode.MALFORMED_PROVIDER_DATA,
            )

    def _health_state(self, health: SessionHealth, now: datetime) -> str:
        state = health.state.replace("_", "-")
        if health.source != "moomoo":
            return "malformed"
        if health.checked_at > now:
            return "malformed"
        if now - health.checked_at > self._session_max_age:
            return "stale"
        if state not in {
            "healthy",
            "offline",
            "login-required",
            "permission-denied",
            "quota-exceeded",
            "sdk-unavailable",
            "malformed",
            "stale",
        }:
            return "malformed"
        return state

    def _error_envelope(
        self,
        error: GatewayError,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = require_utc(now or self._clock(), "clock")
        response = self._envelope(
            session=error.session,
            as_of=timestamp,
            available_at=timestamp,
            items=[],
        )
        response["error"] = error.public_dict()
        return response

    def _snapshot_error(
        self,
        error: GatewayError,
        *,
        symbol: str,
        interval: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = require_utc(now or self._clock(), "clock")
        return {
            "schemaVersion": "2",
            "source": "moomoo",
            "sourceStatus": "unavailable",
            "symbol": symbol.strip().upper(),
            "interval": interval,
            "decisionCutoff": iso_z(timestamp),
            "quote": {},
            "completedCandles": [],
            "participationBars": [],
            "indicators": {},
            "institutionalHoldings": [],
            "provenance": [],
            "warnings": [],
            "error": error.public_dict(),
        }

    @staticmethod
    def _envelope(
        *,
        session: str,
        as_of: datetime,
        available_at: datetime,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": session,
            "asOf": iso_z(as_of),
            "availableAt": iso_z(available_at),
            "items": items,
        }

    @staticmethod
    def _adjustment(item: dict[str, Any]) -> str:
        basis = item.get("price_adjustment")
        if basis not in {"forward-adjusted", "unadjusted"}:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Provider candle does not declare a price adjustment basis",
            )
        return basis

    @staticmethod
    def _number(value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                f"{label} is not numeric",
            )
        result = float(value)
        if not math.isfinite(result):
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                f"{label} is not finite",
            )
        return result

    @staticmethod
    def _code_for_health_state(state: str) -> ErrorCode:
        return {
            "offline": ErrorCode.OPEND_OFFLINE,
            "login-required": ErrorCode.LOGIN_REQUIRED,
            "permission-denied": ErrorCode.PERMISSION_DENIED,
            "quota-exceeded": ErrorCode.QUOTA_EXCEEDED,
            "sdk-unavailable": ErrorCode.SDK_UNAVAILABLE,
            "stale": ErrorCode.STALE_DATA,
        }.get(state, ErrorCode.MALFORMED_PROVIDER_DATA)

    @staticmethod
    def _message_for_code(
        code: ErrorCode,
        default: str = "moomoo OpenD returned malformed health data",
    ) -> str:
        """Replace provider text with a message we authored.

        ``default`` exists because the same code covers two very different
        failures: a health check that returned nonsense, and market data that
        failed validation. Describing the second as the first sends the reader
        to the wrong place.
        """

        return {
            ErrorCode.OPEND_OFFLINE: "moomoo OpenD is offline",
            ErrorCode.LOGIN_REQUIRED: "moomoo OpenD login is required",
            ErrorCode.PERMISSION_DENIED: "Quote permission is unavailable",
            ErrorCode.QUOTA_EXCEEDED: "Provider quota exceeded",
            ErrorCode.SDK_UNAVAILABLE: "moomoo OpenAPI SDK is not installed",
            ErrorCode.STALE_DATA: "moomoo OpenD health is stale",
        }.get(code, default)
