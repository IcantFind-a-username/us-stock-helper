from __future__ import annotations

import importlib
import math
import socket
from contextlib import contextmanager
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Iterator, cast

from .errors import ErrorCode, GatewayError
from .models import ProviderBatch, SessionHealth
from .time_utils import US_EASTERN, iso_z, parse_exchange_time, require_utc, utc_now


def _load_moomoo_sdk() -> Any:
    return importlib.import_module("moomoo")


def _probe_tcp(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        return None


class MoomooOpenDProvider:
    """Minimal quote-only adapter. It never constructs a trading context."""

    _INTERVALS = {
        "1m": ("K_1M", timedelta(minutes=1)),
        "5m": ("K_5M", timedelta(minutes=5)),
        "15m": ("K_15M", timedelta(minutes=15)),
        "30m": ("K_30M", timedelta(minutes=30)),
        "60m": ("K_60M", timedelta(minutes=60)),
        "day": ("K_DAY", None),
        "week": ("K_WEEK", None),
    }

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 11111,
        sdk_loader: Callable[[], Any] = _load_moomoo_sdk,
        connectivity_probe: Callable[[str, int, float], None] = _probe_tcp,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._host = host
        self._port = port
        self._sdk_loader = sdk_loader
        self._connectivity_probe = connectivity_probe
        self._clock = clock

    def health(self) -> SessionHealth:
        try:
            with self._quote_context() as (sdk, context):
                ret, payload = context.get_global_state()
                self._require_ok(sdk, ret, payload)
                state = self._record(payload)
                checked_at = require_utc(self._clock(), "clock")
                if "qot_logined" not in state:
                    raise GatewayError(
                        ErrorCode.MALFORMED_PROVIDER_DATA,
                        "OpenD health response is malformed",
                    )
                if state["qot_logined"] is not True:
                    return SessionHealth(
                        "login_required",
                        checked_at,
                        "moomoo",
                        ErrorCode.LOGIN_REQUIRED,
                    )
                return SessionHealth("healthy", checked_at, "moomoo")
        except GatewayError as error:
            return SessionHealth(
                error.session.replace("-", "_"),
                require_utc(self._clock(), "clock"),
                "moomoo",
                error.code,
            )
        except Exception as exc:
            provider_error = self._classify_provider_error(str(exc))
            return SessionHealth(
                provider_error.session.replace("-", "_"),
                require_utc(self._clock(), "clock"),
                "moomoo",
                provider_error.code,
            )

    def watchlist(self, group: str | None = None) -> ProviderBatch:
        with self._quote_context() as (sdk, context):
            group_name = group
            if not group_name:
                method = self._quote_capability(
                    context,
                    "get_user_security_group",
                )
                ret, payload = self._invoke_optional(method)
                self._require_ok(sdk, ret, payload)
                groups = self._records(payload)
                if not groups or not groups[0].get("group_name"):
                    raise GatewayError(
                        ErrorCode.MALFORMED_PROVIDER_DATA,
                        "OpenD watchlist groups are malformed",
                    )
                group_name = str(groups[0]["group_name"])
            ret, payload = context.get_user_security(group_name=group_name)
            self._require_ok(sdk, ret, payload)
            securities = [
                row
                for row in self._records(payload)
                if str(row.get("code", "")).startswith("US.")
                and str(row.get("stock_type", "")) in {"STOCK", "ETF"}
            ]
            codes = [str(row.get("code", "")) for row in securities]
            if not codes:
                received_at = require_utc(self._clock(), "clock")
                return ProviderBatch("moomoo", received_at, [])
            snapshot_rows, unavailable_codes = self._watchlist_snapshots(
                sdk,
                context,
                codes,
            )
            if not snapshot_rows:
                raise GatewayError(
                    ErrorCode.PROVIDER_ERROR,
                    "No watchlist symbols have available quotes",
                    retriable=True,
                )
            snapshots = {
                str(row.get("code")): row for row in snapshot_rows
            }

        items = []
        for security in securities:
            code = str(security.get("code", ""))
            snapshot = snapshots.get(code)
            if snapshot is None:
                if code in unavailable_codes:
                    continue
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "Watchlist snapshot is incomplete",
                )
            quote = self._quote_item(snapshot)
            quote["name"] = str(security.get("name", ""))
            items.append(quote)
        received_at = require_utc(self._clock(), "clock")
        return ProviderBatch("moomoo", received_at, items)

    def _watchlist_snapshots(
        self,
        sdk: Any,
        context: Any,
        codes: list[str],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        ret, payload = context.get_market_snapshot(codes)
        if ret == sdk.RET_OK:
            return self._records(payload), set()

        error = self._classify_provider_error(str(payload))
        if error.code is not ErrorCode.PROVIDER_ERROR:
            raise error
        if len(codes) == 1:
            return [], {codes[0]}

        midpoint = len(codes) // 2
        left_rows, left_unavailable = self._watchlist_snapshots(
            sdk,
            context,
            codes[:midpoint],
        )
        right_rows, right_unavailable = self._watchlist_snapshots(
            sdk,
            context,
            codes[midpoint:],
        )
        rows = left_rows + right_rows
        unavailable = left_unavailable | right_unavailable
        return rows, unavailable

    def quotes(self, codes: list[str]) -> ProviderBatch:
        with self._quote_context() as (sdk, context):
            ret, payload = context.get_market_snapshot(codes)
            self._require_ok(sdk, ret, payload)
            rows = self._records(payload)
        items = [self._quote_item(row) for row in rows]
        received_at = require_utc(self._clock(), "clock")
        return ProviderBatch(
            "moomoo",
            received_at,
            items,
        )

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        interval = self._INTERVALS.get(timeframe)
        if interval is None:
            raise GatewayError(
                ErrorCode.INVALID_ARGUMENT,
                "Unsupported candle interval",
            )
        requested_at = require_utc(self._clock(), "clock")
        sdk_name, duration = interval
        with self._quote_context() as (sdk, context):
            sdk_interval = getattr(sdk.KLType, sdk_name)
            start, end = self._history_range(requested_at, timeframe, count)
            rows: list[dict[str, Any]] = []
            page_key: object = None
            seen_page_keys: set[object] = set()
            for _ in range(20):
                result = context.request_history_kline(
                    code=code,
                    start=start,
                    end=end,
                    ktype=sdk_interval,
                    autype=sdk.AuType.QFQ,
                    max_count=1000,
                    page_req_key=page_key,
                )
                if not isinstance(result, tuple) or len(result) < 2:
                    raise GatewayError(
                        ErrorCode.MALFORMED_PROVIDER_DATA,
                        "OpenD candle response is malformed",
                    )
                ret, payload = result[0], result[1]
                self._require_ok(sdk, ret, payload)
                rows.extend(self._records(payload))
                next_page_key = result[2] if len(result) > 2 else None
                if next_page_key is None:
                    break
                if next_page_key in seen_page_keys:
                    raise GatewayError(
                        ErrorCode.MALFORMED_PROVIDER_DATA,
                        "OpenD candle pagination repeated a page",
                    )
                seen_page_keys.add(next_page_key)
                page_key = next_page_key
            else:
                raise GatewayError(
                    ErrorCode.QUOTA_EXCEEDED,
                    "Historical candle request exceeded its page safety limit",
                    retriable=True,
                )

        response_at = require_utc(self._clock(), "clock")
        items = [
            self._candle_item(row, timeframe, duration, response_at) for row in rows
        ]
        for previous, current in zip(items, items[1:]):
            if str(current["timestamp"]) <= str(previous["timestamp"]):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD candle rows are out of chronological order",
                )
        received_at = require_utc(self._clock(), "clock")
        return ProviderBatch("moomoo", received_at, items[-count:])

    def capital_flow(self, code: str) -> ProviderBatch:
        with self._quote_context() as (sdk, context):
            method = self._quote_capability(context, "get_capital_flow")
            ret, payload = self._invoke_optional(method, code)
            self._require_ok(sdk, ret, payload)
            rows = self._records(payload)
        received_at = require_utc(self._clock(), "clock")
        items = []
        for row in rows:
            if str(row.get("code", code)) != code:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD capital-flow row does not match the requested code",
                )
            try:
                timestamp = parse_exchange_time(
                    row["capital_flow_item_time"],
                    "capital_flow_item_time",
                )
                items.append(
                    {
                        "code": code,
                        "timestamp": iso_z(timestamp),
                        "available_at": iso_z(received_at),
                        "session": timestamp.astimezone(US_EASTERN).date().isoformat(),
                        "total_net": float(row["in_flow"]),
                        "super_net": float(row.get("super_in_flow", 0.0)),
                        "big_net": float(row.get("big_in_flow", 0.0)),
                        "mid_net": float(row.get("mid_in_flow", 0.0)),
                        "small_net": float(row.get("sml_in_flow", 0.0)),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD capital-flow response is malformed",
                ) from exc
        for previous, current in zip(items, items[1:]):
            if str(current["timestamp"]) <= str(previous["timestamp"]):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD capital-flow rows are out of chronological order",
                )
        return ProviderBatch("moomoo", received_at, items)

    def capital_distribution(self, code: str) -> ProviderBatch:
        with self._quote_context() as (sdk, context):
            method = self._quote_capability(context, "get_capital_distribution")
            ret, payload = self._invoke_optional(method, code)
            self._require_ok(sdk, ret, payload)
            rows = self._records(payload)
        items = []
        for row in rows:
            try:
                available_at = parse_exchange_time(
                    row["update_time"],
                    "capital distribution update_time",
                )
                items.append(
                    {
                        "code": code,
                        "available_at": iso_z(available_at),
                        "super_in": float(row.get("capital_in_super", 0.0)),
                        "super_out": float(row.get("capital_out_super", 0.0)),
                        "big_in": float(row["capital_in_big"]),
                        "big_out": float(row["capital_out_big"]),
                        "mid_in": float(row["capital_in_mid"]),
                        "mid_out": float(row["capital_out_mid"]),
                        "small_in": float(row["capital_in_small"]),
                        "small_out": float(row["capital_out_small"]),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD capital distribution response is malformed",
                ) from exc
        received_at = require_utc(self._clock(), "clock")
        return ProviderBatch("moomoo", received_at, items)

    def options_flow(self, code: str) -> ProviderBatch:
        with self._quote_context() as (sdk, context):
            method = self._quote_capability(context, "get_option_chain")
            ret, payload = self._invoke_optional(method, code)
            self._require_ok(sdk, ret, payload)
            rows = self._records(payload)
        received_at = require_utc(self._clock(), "clock")
        items = []
        for row in rows:
            if str(row.get("code", code)) != code:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD options-chain row does not match the requested code",
                )
            try:
                items.append(
                    {
                        "code": code,
                        "available_at": iso_z(received_at),
                        "contract_code": str(row["option_code"]),
                        "strike": float(row["strike_price"]),
                        "expiry": str(row["strike_time"]),
                        "option_type": str(row["option_type"]),
                        "volume": float(row.get("volume", 0.0)),
                        "open_interest": float(row.get("open_interest", 0.0)),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD options-chain response is malformed",
                ) from exc
        return ProviderBatch("moomoo", received_at, items)

    def institutional_holdings(self, code: str) -> ProviderBatch:
        rows: list[dict[str, Any]] = []
        with self._quote_context() as (sdk, context):
            method = self._quote_capability(
                context,
                "get_shareholders_institutional",
            )
            next_key: str | None = None
            for _ in range(20):
                kwargs: dict[str, Any] = {"num": 50}
                if next_key is not None:
                    kwargs["next_key"] = next_key
                ret, payload = self._invoke_optional(method, code, **kwargs)
                self._require_ok(sdk, ret, payload)
                page_rows = self._records(payload)
                rows.extend(page_rows)
                raw_next = getattr(payload, "attrs", {}).get("next_key")
                if raw_next in (None, "") and page_rows:
                    raw_next = page_rows[0].get("next_key")
                if raw_next in (None, "", "-1"):
                    break
                next_key = str(raw_next)
            else:
                raise GatewayError(
                    ErrorCode.QUOTA_EXCEEDED,
                    "Institutional disclosure pagination exceeded its safety limit",
                    retriable=True,
                )
        items = []
        for row in rows:
            try:
                period = str(row["period_text"])
                reported_at = self._quarter_end(period)
                available_at = parse_exchange_time(
                    row["update_time_str"],
                    "institutional update_time_str",
                )
                items.append(
                    {
                        "code": code,
                        "period": period,
                        "reported_at": iso_z(reported_at),
                        "available_at": iso_z(available_at),
                        "institution_count": int(row["institution_quantity"]),
                        "institution_count_change": int(
                            row["institution_quantity_change"]
                        ),
                        "shares_held": float(row["holder_quantity"]),
                        "shares_held_change": float(
                            row["holder_quantity_change"]
                        ),
                        "holding_percent": float(row["holder_pct"]),
                        "holding_percent_change": float(
                            row["holder_pct_change"]
                        ),
                        "source": "moomoo-delayed-institutional-disclosure",
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD institutional disclosure is malformed",
                ) from exc
        for previous, current in zip(items, items[1:]):
            if str(current["available_at"]) >= str(previous["available_at"]):
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD institutional disclosure rows are out of chronological order",
                )
        received_at = require_utc(self._clock(), "clock")
        return ProviderBatch("moomoo", received_at, items)

    @staticmethod
    def _history_range(
        now: datetime,
        timeframe: str,
        count: int,
    ) -> tuple[str, str]:
        local_date = now.astimezone(US_EASTERN).date()
        bars_per_day = {
            "1m": 390,
            "5m": 78,
            "15m": 26,
            "30m": 13,
            "60m": 7,
        }
        if timeframe in bars_per_day:
            trading_days = math.ceil(count / bars_per_day[timeframe]) + 2
            calendar_days = math.ceil(trading_days * 7 / 5) + 4
        elif timeframe == "day":
            calendar_days = math.ceil(count * 7 / 5) + 10
        else:
            calendar_days = count * 7 + 21
        return (
            (local_date - timedelta(days=calendar_days)).isoformat(),
            local_date.isoformat(),
        )

    @staticmethod
    def _quarter_end(period: str) -> datetime:
        try:
            year_text, quarter_text = period.split("/Q", 1)
            year = int(year_text)
            quarter = int(quarter_text)
            month_day = {
                1: (3, 31),
                2: (6, 30),
                3: (9, 30),
                4: (12, 31),
            }[quarter]
        except (ValueError, KeyError) as exc:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "Institutional reporting period is malformed",
            ) from exc
        return datetime(
            year,
            month_day[0],
            month_day[1],
            16,
            0,
            tzinfo=US_EASTERN,
        ).astimezone(timezone.utc)

    @contextmanager
    def _quote_context(self) -> Iterator[tuple[Any, Any]]:
        try:
            self._connectivity_probe(self._host, self._port, 1.0)
        except OSError as exc:
            raise GatewayError(
                ErrorCode.OPEND_OFFLINE,
                "moomoo OpenD is offline",
                retriable=True,
            ) from exc
        try:
            sdk = self._sdk_loader()
        except (ModuleNotFoundError, ImportError) as exc:
            raise GatewayError(
                ErrorCode.SDK_UNAVAILABLE,
                "moomoo OpenAPI SDK is not installed",
            ) from exc
        try:
            context = sdk.OpenQuoteContext(host=self._host, port=self._port)
        except Exception as exc:
            raise self._classify_provider_error(str(exc)) from exc
        try:
            yield sdk, context
        finally:
            try:
                context.close()
            except Exception:
                pass

    def _quote_item(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            price = float(row["last_price"])
            previous_close = float(row["prev_close_price"])
            change_percent = (
                ((price - previous_close) / previous_close) * 100
                if previous_close > 0
                else 0.0
            )
            available_at = parse_exchange_time(
                row["update_time"],
                "quote update_time",
            )
            return {
                "code": str(row["code"]),
                "price": price,
                "change_percent": change_percent,
                "available_at": iso_z(available_at),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "OpenD quote response is malformed",
            ) from exc

    def _candle_item(
        self,
        row: dict[str, Any],
        timeframe: str,
        duration: timedelta | None,
        now: datetime,
    ) -> dict[str, Any]:
        try:
            bar_open = parse_exchange_time(row["time_key"], "candle time_key")
            bar_close = self._bar_available_at(bar_open, timeframe, duration)
            return {
                "code": str(row["code"]),
                "timeframe": timeframe,
                "timestamp": iso_z(bar_close),
                # `now` is the gateway's own receive-clock reading, taken
                # right after the OpenD response landed. A replay must never
                # be able to act on this row before this gateway actually
                # held it, so available_at/received_at track the receive
                # clock -- never the bar's theoretical close time, which can
                # be earlier (stale data) or later (an in-progress bar).
                "available_at": iso_z(now),
                "received_at": iso_z(now),
                # OpenD is queried with forward adjustment, so a corporate
                # action rewrites every earlier price in this series.
                "price_adjustment": "forward-adjusted",
                "complete": bar_close <= now,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayError(
                ErrorCode.MALFORMED_PROVIDER_DATA,
                "OpenD candle response is malformed",
            ) from exc

    @staticmethod
    def _bar_available_at(
        timestamp: datetime,
        timeframe: str,
        duration: timedelta | None,
    ) -> datetime:
        if duration is not None:
            return timestamp + duration
        local_day = timestamp.astimezone(US_EASTERN).date()
        if timeframe == "week":
            local_day = local_day + timedelta(days=4 - local_day.weekday())
        local_close = datetime.combine(local_day, time(16, 0), US_EASTERN)
        return local_close.astimezone(timestamp.tzinfo)

    @staticmethod
    def _require_ok(sdk: Any, ret: object, payload: object) -> None:
        if ret != sdk.RET_OK:
            raise MoomooOpenDProvider._classify_provider_error(str(payload))

    @staticmethod
    def _classify_provider_error(message: str) -> GatewayError:
        lowered = message.lower()
        if any(word in lowered for word in ("login", "登录", "登錄", "登入")):
            return GatewayError(
                ErrorCode.LOGIN_REQUIRED,
                "moomoo OpenD login is required",
            )
        if any(
            word in lowered
            for word in ("permission", "authority", "right", "权限", "權限")
        ):
            return GatewayError(
                ErrorCode.PERMISSION_DENIED,
                "Quote permission is unavailable",
            )
        if any(
            word in lowered
            for word in (
                "quota",
                "frequency",
                "limit",
                "额度",
                "額度",
                "频率",
                "頻率",
                "上限",
            )
        ):
            return GatewayError(
                ErrorCode.QUOTA_EXCEEDED,
                "Provider quota exceeded",
                retriable=True,
            )
        if any(
            word in lowered
            for word in (
                "connection",
                "refused",
                "timeout",
                "timed out",
                "offline",
                "连接",
                "連接",
                "超时",
                "超時",
                "离线",
                "離線",
            )
        ):
            return GatewayError(
                ErrorCode.OPEND_OFFLINE,
                "moomoo OpenD is offline",
                retriable=True,
            )
        return GatewayError(
            ErrorCode.PROVIDER_ERROR,
            "moomoo OpenD returned an unexpected error",
            retriable=True,
        )

    @staticmethod
    def _quote_capability(context: object, name: str) -> Callable[..., Any]:
        method = getattr(context, name, None)
        if not callable(method):
            raise GatewayError(
                ErrorCode.UNSUPPORTED_CAPABILITY,
                "OpenD SDK does not expose this quote capability",
            )
        return cast(Callable[..., Any], method)

    @staticmethod
    def _invoke_optional(
        method: Callable[..., Any],
        *args: object,
        **kwargs: object,
    ) -> Any:
        try:
            return method(*args, **kwargs)
        except TypeError as exc:
            raise GatewayError(
                ErrorCode.UNSUPPORTED_CAPABILITY,
                "OpenD SDK quote capability has an incompatible version",
            ) from exc

    @staticmethod
    def _records(payload: object) -> list[dict[str, Any]]:
        if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
            return payload
        if hasattr(payload, "to_dict"):
            try:
                records = payload.to_dict("records")
            except Exception as exc:
                raise GatewayError(
                    ErrorCode.MALFORMED_PROVIDER_DATA,
                    "OpenD tabular response is malformed",
                ) from exc
            if isinstance(records, list) and all(
                isinstance(row, dict) for row in records
            ):
                return records
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            "OpenD tabular response is malformed",
        )

    @staticmethod
    def _record(payload: object) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        records = MoomooOpenDProvider._records(payload)
        if len(records) == 1:
            return records[0]
        raise GatewayError(
            ErrorCode.MALFORMED_PROVIDER_DATA,
            "OpenD health response is malformed",
        )
