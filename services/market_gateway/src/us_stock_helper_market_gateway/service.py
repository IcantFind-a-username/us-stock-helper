from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Callable

from .errors import ErrorCode, GatewayError
from .models import ProviderBatch, QuoteProvider, SessionHealth
from .snapshot import assemble_stock_snapshot
from .symbols import from_moomoo_code, to_moomoo_code
from .time_utils import iso_z, parse_aware, require_utc, utc_now


class MarketGatewayService:
    """Validates point-in-time provider data and emits the mobile JSON contract."""

    def __init__(
        self,
        provider: QuoteProvider,
        *,
        clock: Callable[[], datetime] = utc_now,
        session_max_age: timedelta = timedelta(seconds=15),
        response_max_age: timedelta = timedelta(seconds=30),
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._session_max_age = session_max_age
        self._response_max_age = response_max_age

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
            try:
                flow_received = self._validate_batch(flow_batch, completed_at)
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
                    self._message_for_code(error.code),
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
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Provider response is timestamped in the future",
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
            previous = timestamp
            normalized.append(
                {
                    "timestamp": iso_z(timestamp),
                    "availableAt": iso_z(available_at),
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
            if (
                timestamp > available_at
                or available_at > now
                or (previous is not None and timestamp <= previous)
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
    def _message_for_code(code: ErrorCode) -> str:
        return {
            ErrorCode.OPEND_OFFLINE: "moomoo OpenD is offline",
            ErrorCode.LOGIN_REQUIRED: "moomoo OpenD login is required",
            ErrorCode.PERMISSION_DENIED: "Quote permission is unavailable",
            ErrorCode.QUOTA_EXCEEDED: "Provider quota exceeded",
            ErrorCode.SDK_UNAVAILABLE: "moomoo OpenAPI SDK is not installed",
            ErrorCode.STALE_DATA: "moomoo OpenD health is stale",
        }.get(code, "moomoo OpenD returned malformed health data")
