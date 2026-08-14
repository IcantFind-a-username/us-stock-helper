from __future__ import annotations

import copy
import unittest
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from us_stock_helper_market_gateway.errors import ErrorCode, GatewayError
from us_stock_helper_market_gateway.models import ProviderBatch, SessionHealth
from us_stock_helper_market_gateway.service import MarketGatewayService
from us_stock_helper_market_gateway.symbols import from_moomoo_code, to_moomoo_code


NOW = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self) -> None:
        self.health_result = SessionHealth(
            state="healthy",
            checked_at=NOW - timedelta(seconds=2),
            source="moomoo",
        )
        self.watchlist_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "name": "NVIDIA",
                    "price": 173.40,
                    "change_percent": 2.7,
                    "available_at": "2026-07-25T03:59:58+00:00",
                }
            ],
        )
        self.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.40,
                    "change_percent": 2.7,
                    "available_at": "2026-07-25T03:59:58+00:00",
                }
            ],
        )
        self.candles_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "timeframe": "5m",
                    "timestamp": "2026-07-25T03:50:00+00:00",
                    "available_at": "2026-07-25T03:55:00+00:00",
                    "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": True,
                    "open": 172.0,
                    "high": 174.0,
                    "low": 171.5,
                    "close": 173.4,
                    "volume": 1000,
                },
                {
                    "code": "US.NVDA",
                    "timeframe": "5m",
                    "timestamp": "2026-07-25T03:55:00+00:00",
                    "available_at": "2026-07-25T04:00:01+00:00",
                    "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": False,
                    "open": 173.4,
                    "high": 174.2,
                    "low": 173.0,
                    "close": 174.0,
                    "volume": 200,
                },
            ],
        )
        self.capital_flow_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "timestamp": "2026-07-25T03:58:00+00:00",
                    "available_at": "2026-07-25T03:59:00+00:00",
                    "session": "2026-07-24",
                    "total_net": 12_000.0,
                    "super_net": 5_000.0,
                    "big_net": 4_000.0,
                    "mid_net": 2_000.0,
                    "small_net": 1_000.0,
                }
            ],
        )
        self.capital_distribution_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "available_at": "2026-07-25T03:59:00+00:00",
                    "super_in": 10_000.0,
                    "super_out": 4_000.0,
                    "big_in": 8_000.0,
                    "big_out": 3_000.0,
                    "mid_in": 5_000.0,
                    "mid_out": 4_000.0,
                    "small_in": 2_000.0,
                    "small_out": 3_000.0,
                }
            ],
        )
        self.institutional_result = ProviderBatch(
            source="moomoo",
            received_at=NOW - timedelta(seconds=1),
            items=[
                {
                    "code": "US.NVDA",
                    "period": "2026/Q1",
                    "reported_at": "2026-03-31T20:00:00+00:00",
                    "available_at": "2026-05-16T14:00:00+00:00",
                    "institution_count": 863,
                    "institution_count_change": 12,
                    "shares_held": 4_192_178_205,
                    "shares_held_change": -3_105_448,
                    "holding_percent": 46.474,
                    "holding_percent_change": 0.03,
                    "source": "moomoo-delayed-institutional-disclosure",
                }
            ],
        )

    def health(self) -> SessionHealth:
        return self.health_result

    def watchlist(self, group: str | None = None) -> ProviderBatch:
        return self.watchlist_result

    def quotes(self, codes: list[str]) -> ProviderBatch:
        return self.quotes_result

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        return self.candles_result

    def capital_flow(self, code: str) -> ProviderBatch:
        return self.capital_flow_result

    def capital_distribution(self, code: str) -> ProviderBatch:
        return self.capital_distribution_result

    def institutional_holdings(self, code: str) -> ProviderBatch:
        return self.institutional_result


class IndependentProvider(FakeProvider):
    """Provider fake whose four snapshot operations fail independently."""

    def __init__(self) -> None:
        super().__init__()
        self.health_calls = 0
        self.source_calls: list[str] = []
        self.behaviors: dict[str, ProviderBatch | BaseException] = {
            "quote": self.quotes_result,
            "candles": self.candles_result,
            "flow": self.capital_flow_result,
            "holdings": self.institutional_result,
        }
        self.capital_flow_result.items[:] = [
            {
                "code": "US.NVDA",
                "timestamp": f"2026-07-25T03:{45 + index:02d}:00+00:00",
                "available_at": f"2026-07-25T03:{45 + index:02d}:00+00:00",
                "session": "2026-07-24",
                "total_net": 2_400.0 * index,
                "super_net": 1_000.0 * index,
                "big_net": 800.0 * index,
                "mid_net": 400.0 * index,
                "small_net": 200.0 * index,
            }
            for index in range(6)
        ]

    def health(self) -> SessionHealth:
        self.health_calls += 1
        return self.health_result

    def _resolve(self, name: str) -> ProviderBatch:
        self.source_calls.append(name)
        behavior = self.behaviors[name]
        if isinstance(behavior, BaseException):
            raise behavior
        return behavior

    def quotes(self, codes: list[str]) -> ProviderBatch:
        return self._resolve("quote")

    def candles(self, code: str, timeframe: str, count: int) -> ProviderBatch:
        return self._resolve("candles")

    def capital_flow(self, code: str) -> ProviderBatch:
        return self._resolve("flow")

    def institutional_holdings(self, code: str) -> ProviderBatch:
        return self._resolve("holdings")


class FakeMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ScriptedFuture:
    def __init__(
        self,
        operation: Callable[[], ProviderBatch],
        clock: FakeMonotonic,
        submitted_at: float,
        delay: float,
    ) -> None:
        self._operation = operation
        self._clock = clock
        self._completion_at = submitted_at + delay
        self._finished = False
        self._value: ProviderBatch | None = None
        self._error: BaseException | None = None
        self.result_timeouts: list[float | None] = []
        self.cancel_called = False

    def result(self, timeout: float | None = None) -> ProviderBatch:
        self.result_timeouts.append(timeout)
        remaining = max(0.0, self._completion_at - self._clock())
        if timeout is not None and remaining > timeout:
            self._clock.advance(timeout)
            raise FutureTimeoutError()
        self._clock.advance(remaining)
        if not self._finished:
            try:
                self._value = self._operation()
            except BaseException as error:
                self._error = error
            self._finished = True
        if self._error is not None:
            raise self._error
        assert self._value is not None
        return self._value

    def cancel(self) -> bool:
        self.cancel_called = True
        return not self._finished

    def done(self) -> bool:
        return self._finished or self._clock() >= self._completion_at


class ScriptedExecutor:
    def __init__(
        self,
        clock: FakeMonotonic,
        *,
        delays: list[float] | None = None,
        submit_latency: float = 0.0,
    ) -> None:
        self.clock = clock
        self.delays = delays or [0.0, 0.0, 0.0, 0.0]
        self.submit_latency = submit_latency
        self.max_workers: int | None = None
        self.futures: list[ScriptedFuture] = []
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def factory(self, max_workers: int) -> "ScriptedExecutor":
        self.max_workers = max_workers
        return self

    def submit(self, operation: Callable[[], ProviderBatch]) -> ScriptedFuture:
        index = len(self.futures)
        future = ScriptedFuture(
            operation,
            self.clock,
            self.clock(),
            self.delays[index],
        )
        self.futures.append(future)
        self.clock.advance(self.submit_latency)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class LateDoneExecutor(ScriptedExecutor):
    """Returns the first future only after its operation has completed late."""

    def submit(self, operation: Callable[[], ProviderBatch]) -> ScriptedFuture:
        if self.futures:
            return super().submit(operation)
        self.clock.advance(6.0)
        future = ScriptedFuture(operation, self.clock, self.clock(), 0.0)
        self.futures.append(future)
        try:
            future.result()
        except BaseException:
            pass
        return future


class SymbolNormalizationTests(unittest.TestCase):
    def test_us_symbol_round_trips_without_accepting_other_markets(self) -> None:
        self.assertEqual(to_moomoo_code(" nvda "), "US.NVDA")
        self.assertEqual(to_moomoo_code("US.NVDA"), "US.NVDA")
        self.assertEqual(from_moomoo_code("US.NVDA"), "NVDA")

        for bad in ("HK.00700", "NVDA/USD", "", "US."):
            with self.subTest(bad=bad):
                with self.assertRaises(GatewayError) as raised:
                    to_moomoo_code(bad)
                self.assertEqual(raised.exception.code, ErrorCode.INVALID_ARGUMENT)


class MarketGatewayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FakeProvider()
        self.service = MarketGatewayService(
            self.provider,
            clock=lambda: NOW,
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

    def test_health_reports_offline_without_claiming_live(self) -> None:
        self.provider.health_result = SessionHealth(
            state="offline",
            checked_at=NOW,
            source="moomoo",
            error_code=ErrorCode.OPEND_OFFLINE,
        )

        response = self.service.health()

        self.assertEqual(response["session"], "offline")
        self.assertEqual(response["items"][0]["status"], "offline")
        self.assertEqual(response["source"], "moomoo")

    def test_health_rejects_any_future_provider_check(self) -> None:
        self.provider.health_result = SessionHealth(
            state="healthy",
            checked_at=NOW + timedelta(milliseconds=1),
            source="moomoo",
        )

        response = self.service.health()

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_healthy_fresh_watchlist_is_normalized_and_live(self) -> None:
        response = self.service.watchlist("Technology")

        self.assertEqual(response["schemaVersion"], "1")
        self.assertEqual(response["source"], "moomoo")
        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["items"][0]["code"], "US.NVDA")
        self.assertEqual(response["items"][0]["price"], 173.40)
        self.assertEqual(response["items"][0]["changePercent"], 2.7)
        self.assertEqual(
            response["items"][0]["availableAt"],
            "2026-07-25T03:59:58Z",
        )
        self.assertLessEqual(response["asOf"], response["availableAt"])

    def test_sensitive_provider_fields_never_reach_response(self) -> None:
        self.provider.watchlist_result.items[0].update(
            {
                "password": "do-not-return",
                "token": "do-not-return",
                "cookie": "do-not-return",
            }
        )

        serialized = repr(self.service.watchlist()).lower()

        self.assertNotIn("do-not-return", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("cookie", serialized)

    def test_quotes_require_healthy_session(self) -> None:
        expected = {
            "offline": ErrorCode.OPEND_OFFLINE,
            "login_required": ErrorCode.LOGIN_REQUIRED,
            "permission_denied": ErrorCode.PERMISSION_DENIED,
            "quota_exceeded": ErrorCode.QUOTA_EXCEEDED,
            "sdk_unavailable": ErrorCode.SDK_UNAVAILABLE,
            "malformed": ErrorCode.MALFORMED_PROVIDER_DATA,
        }

        for state, code in expected.items():
            with self.subTest(state=state):
                self.provider.health_result = SessionHealth(
                    state=state,
                    checked_at=NOW,
                    source="moomoo",
                    error_code=code,
                )
                response = self.service.quotes(["NVDA"])
                self.assertEqual(response["session"], state.replace("_", "-"))
                self.assertEqual(response["error"]["code"], code.value)
                self.assertEqual(response["items"], [])

    def test_stale_or_non_moomoo_response_never_claims_live(self) -> None:
        cases = [
            ProviderBatch(
                source="moomoo",
                received_at=NOW - timedelta(minutes=1),
                items=self.provider.quotes_result.items,
            ),
            ProviderBatch(
                source="unknown",
                received_at=NOW,
                items=self.provider.quotes_result.items,
            ),
        ]

        for batch in cases:
            with self.subTest(source=batch.source, received_at=batch.received_at):
                self.provider.quotes_result = batch
                response = self.service.quotes(["NVDA"])
                self.assertNotEqual(response["session"], "healthy")
                self.assertIn(
                    response["error"]["code"],
                    {
                        ErrorCode.STALE_DATA.value,
                        ErrorCode.MALFORMED_PROVIDER_DATA.value,
                    },
                )

    def test_response_received_during_call_is_validated_against_completion_time(self) -> None:
        moments = iter(
            [
                NOW,
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=5),
            ]
        )
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(seconds=4),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "change_percent": 2.7,
                    "available_at": (NOW + timedelta(seconds=3)).isoformat(),
                }
            ],
        )
        service = MarketGatewayService(
            self.provider,
            clock=lambda: next(moments),
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

        response = service.quotes(["NVDA"])

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["availableAt"], "2026-07-25T04:00:04Z")

    def test_item_available_after_provider_receipt_is_rejected(self) -> None:
        moments = iter(
            [
                NOW,
                NOW + timedelta(seconds=1),
                NOW + timedelta(seconds=5),
            ]
        )
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(seconds=2),
            items=[
                {
                    "code": "US.NVDA",
                    "price": 173.4,
                    "change_percent": 2.7,
                    "available_at": (NOW + timedelta(seconds=3)).isoformat(),
                }
            ],
        )
        service = MarketGatewayService(
            self.provider,
            clock=lambda: next(moments),
        )

        response = service.quotes(["NVDA"])

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_rejects_future_provider_receipt_without_tolerance(self) -> None:
        self.provider.quotes_result = ProviderBatch(
            source="moomoo",
            received_at=NOW + timedelta(milliseconds=1),
            items=self.provider.quotes_result.items,
        )

        response = self.service.quotes(["NVDA"])

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )

    def test_future_completed_candle_rejects_the_entire_batch(self) -> None:
        self.provider.candles_result.items.append(
            {
                "code": "US.NVDA",
                "timeframe": "5m",
                "timestamp": (NOW + timedelta(minutes=5)).isoformat(),
                "available_at": (NOW + timedelta(milliseconds=1)).isoformat(),
                "price_adjustment": "forward-adjusted",
                    "received_at": NOW.isoformat(),
                "complete": True,
                "open": 174.0,
                "high": 175.0,
                "low": 173.5,
                "close": 174.5,
                "volume": 100,
            }
        )

        response = self.service.candles("NVDA", "5m", 200)

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(response["items"], [])

    def test_malformed_quote_is_structured_error(self) -> None:
        self.provider.quotes_result.items[0]["available_at"] = "not-a-time"

        response = self.service.quotes(["NVDA"])

        self.assertNotEqual(response["session"], "healthy")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.MALFORMED_PROVIDER_DATA.value,
        )
        self.assertNotIn("not-a-time", repr(response))

    def test_candles_return_only_completed_point_in_time_bars(self) -> None:
        response = self.service.candles("NVDA", "5m", 200)

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["symbol"], "NVDA")
        self.assertEqual(response["interval"], "5m")
        self.assertEqual(len(response["items"]), 1)
        candle = response["items"][0]
        self.assertTrue(candle["complete"])
        self.assertLessEqual(candle["availableAt"], response["asOf"])

    def test_snapshot_cutoff_is_the_completed_operation_time(self) -> None:
        response = self.service.stock_snapshot("NVDA", "5m", 200)

        self.assertEqual(response["decisionCutoff"], "2026-07-25T04:00:00Z")

    def test_provider_quota_failure_is_sanitized(self) -> None:
        def fail(codes: list[str]) -> ProviderBatch:
            raise GatewayError(
                ErrorCode.QUOTA_EXCEEDED,
                "Provider quota exceeded",
                retriable=True,
                details={"password": "secret", "raw": "account=123"},
            )

        self.provider.quotes = fail  # type: ignore[method-assign]
        response = self.service.quotes(["NVDA"])

        self.assertEqual(response["session"], "quota-exceeded")
        self.assertEqual(
            response["error"],
            {
                "code": "QUOTA_EXCEEDED",
                "message": "Provider quota exceeded",
                "retriable": True,
            },
        )
        self.assertNotIn("secret", repr(response))

    def test_capital_flow_is_large_order_proxy_not_institution_identity(self) -> None:
        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["symbol"], "NVDA")
        self.assertEqual(response["semantics"], "large-order-flow-proxy")
        self.assertFalse(response["institutionalIdentity"])
        self.assertEqual(response["items"][0]["largeOrderProxyNetFlow"], 9000.0)
        self.assertFalse(response["items"][0]["institutionalIdentity"])
        self.assertEqual(response["items"][0]["session"], "2026-07-24")

    def test_capital_flow_rejects_a_provider_symbol_mismatch_atomically(self) -> None:
        self.provider.capital_flow_result.items[0]["code"] = "US.TSLA"

        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "malformed")
        self.assertEqual(response["items"], [])

    def test_capital_distribution_keeps_order_size_buckets_explicit(self) -> None:
        response = self.service.capital_distribution("NVDA")

        self.assertEqual(response["session"], "healthy")
        self.assertEqual(response["semantics"], "order-size-distribution-proxy")
        self.assertEqual(response["items"][0]["extraLargeOrderNetFlow"], 6000.0)
        self.assertEqual(response["items"][0]["largeOrderNetFlow"], 5000.0)
        self.assertFalse(response["institutionalIdentity"])

    def test_institutional_holdings_are_delayed_and_point_in_time(self) -> None:
        response = self.service.institutional_holdings("NVDA")

        item = response["items"][0]
        self.assertEqual(response["semantics"], "delayed-reported-holdings")
        self.assertEqual(item["reportedAt"], "2026-03-31T20:00:00Z")
        self.assertEqual(item["reportedAtBasis"], "reporting-period-end")
        self.assertEqual(item["availableAt"], "2026-05-16T14:00:00Z")
        self.assertEqual(item["source"], "moomoo-delayed-institutional-disclosure")
        self.assertLess(item["reportedAt"], item["availableAt"])

    def test_unsupported_provider_capability_is_explicit(self) -> None:
        def unsupported(code: str) -> ProviderBatch:
            raise GatewayError(
                ErrorCode.UNSUPPORTED_CAPABILITY,
                "OpenD SDK does not expose this quote capability",
            )

        self.provider.capital_flow = unsupported  # type: ignore[method-assign]

        response = self.service.capital_flow("NVDA")

        self.assertEqual(response["session"], "unsupported-capability")
        self.assertEqual(
            response["error"]["code"],
            ErrorCode.UNSUPPORTED_CAPABILITY.value,
        )
        self.assertEqual(response["items"], [])


class StockSnapshotV3ServiceTests(unittest.TestCase):
    _SOURCE_INDEX = {"quote": 0, "candles": 1, "flow": 2, "holdings": 3}
    _SECTION_NAME = {
        "quote": "quote",
        "candles": "candles",
        "flow": "currentSessionFlow",
        "holdings": "holdings",
    }

    def _service(
        self,
        provider: IndependentProvider,
        *,
        delays: list[float] | None = None,
        submit_latency: float = 0.0,
        wall_clock: Callable[[], datetime] = lambda: NOW,
    ) -> tuple[MarketGatewayService, FakeMonotonic, ScriptedExecutor]:
        monotonic = FakeMonotonic()
        executor = ScriptedExecutor(
            monotonic,
            delays=delays,
            submit_latency=submit_latency,
        )
        service = MarketGatewayService(
            provider,
            clock=wall_clock,
            monotonic=monotonic,
            source_timeout_seconds=5.0,
            snapshot_deadline_seconds=12.0,
            executor_factory=executor.factory,  # type: ignore[arg-type]
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )
        return service, monotonic, executor

    def _assert_price_survives(
        self, payload: dict[str, Any], failed_source: str
    ) -> None:
        price_section = "candles" if failed_source == "quote" else "quote"
        self.assertEqual(
            payload["sections"][price_section]["qualityStatus"],
            "validated",
        )
        self.assertIn(payload["status"], {"live", "partial"})

    def test_valid_snapshot_collects_four_sections_after_one_health_check(
        self,
    ) -> None:
        provider = IndependentProvider()
        service, _, executor = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(payload["schemaVersion"], "3")
        self.assertEqual(payload["status"], "live")
        self.assertEqual(payload["count"], 200)
        self.assertEqual(provider.health_calls, 1)
        self.assertEqual(
            provider.source_calls,
            ["quote", "candles", "flow", "holdings"],
        )
        self.assertEqual(executor.max_workers, 4)
        self.assertEqual(len(executor.futures), 4)
        self.assertEqual(executor.shutdown_calls, [(False, True)])
        self.assertFalse(
            payload["sections"]["currentSessionFlow"]["data"][0][
                "institutionalIdentity"
            ]
        )
        for name in ("fundamentals", "marketContext", "news", "forecastDecision"):
            self.assertEqual(payload["sections"][name]["errorCode"], "NOT_REQUESTED")

    def test_each_source_exception_timeout_malformed_or_stale_is_isolated(
        self,
    ) -> None:
        faults = ("exception", "timeout", "malformed", "stale")
        for source in self._SOURCE_INDEX:
            for fault in faults:
                with self.subTest(source=source, fault=fault):
                    provider = IndependentProvider()
                    delays = [0.0, 0.0, 0.0, 0.0]
                    if fault == "exception":
                        provider.behaviors[source] = RuntimeError(
                            f"raw {source} provider secret"
                        )
                    elif fault == "timeout":
                        delays[self._SOURCE_INDEX[source]] = 6.0
                    else:
                        batch = provider.behaviors[source]
                        assert isinstance(batch, ProviderBatch)
                        provider.behaviors[source] = ProviderBatch(
                            source="unknown" if fault == "malformed" else "moomoo",
                            received_at=(
                                NOW - timedelta(minutes=1)
                                if fault == "stale"
                                else batch.received_at
                            ),
                            items=copy.deepcopy(batch.items),
                        )
                    service, _, executor = self._service(
                        provider,
                        delays=delays,
                    )

                    payload = service.stock_snapshot_v3("NVDA", "5m", 200)

                    section = payload["sections"][self._SECTION_NAME[source]]
                    self.assertEqual(
                        section["availabilityStatus"],
                        "stale" if fault == "stale" else "unavailable",
                    )
                    self.assertEqual(section["qualityStatus"], "invalid")
                    expected_code = {
                        "exception": "PROVIDER_ERROR",
                        "timeout": "PROVIDER_ERROR",
                        "malformed": "MALFORMED_PROVIDER_DATA",
                        "stale": "STALE_DATA",
                    }[fault]
                    self.assertEqual(
                        section["errorCode"],
                        (
                            "CURRENT_SESSION_FLOW_UNAVAILABLE"
                            if source == "flow"
                            else expected_code
                        ),
                    )
                    self._assert_price_survives(payload, source)
                    self.assertNotIn("provider secret", repr(payload))
                    self.assertEqual(len(executor.futures), 4)
                    self.assertEqual(executor.shutdown_calls, [(False, True)])
                    if fault == "timeout":
                        timed_out = executor.futures[self._SOURCE_INDEX[source]]
                        self.assertEqual(timed_out.result_timeouts, [5.0])

    def test_future_quote_candles_and_flow_invalidate_the_whole_source(self) -> None:
        item_key = {
            "quote": "available_at",
            "candles": "available_at",
            "flow": "available_at",
        }
        for source in ("quote", "candles", "flow"):
            with self.subTest(source=source):
                provider = IndependentProvider()
                batch = provider.behaviors[source]
                assert isinstance(batch, ProviderBatch)
                items = copy.deepcopy(batch.items)
                items[0][item_key[source]] = (NOW + timedelta(seconds=1)).isoformat()
                provider.behaviors[source] = ProviderBatch(
                    "moomoo",
                    batch.received_at,
                    items,
                )
                service, _, _ = self._service(provider)

                payload = service.stock_snapshot_v3("NVDA", "5m", 200)

                section = payload["sections"][self._SECTION_NAME[source]]
                self.assertEqual(section["availabilityStatus"], "unavailable")
                self.assertEqual(section["data"], None)
                self._assert_price_survives(payload, source)

    def test_future_holdings_rows_are_excluded_without_losing_a_valid_sibling(
        self,
    ) -> None:
        provider = IndependentProvider()
        batch = provider.behaviors["holdings"]
        assert isinstance(batch, ProviderBatch)
        future_row = copy.deepcopy(batch.items[0])
        future_row["available_at"] = (NOW + timedelta(seconds=1)).isoformat()
        provider.behaviors["holdings"] = ProviderBatch(
            "moomoo",
            batch.received_at,
            [copy.deepcopy(batch.items[0]), future_row],
        )
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        holdings = payload["sections"]["holdings"]
        self.assertEqual(holdings["availabilityStatus"], "delayed")
        self.assertEqual(holdings["qualityStatus"], "anomalous")
        self.assertEqual(len(holdings["data"]), 1)
        self.assertEqual(holdings["anomalies"][0]["code"], "FUTURE_HOLDINGS_ROW")
        self.assertEqual(payload["sections"]["quote"]["qualityStatus"], "validated")
        self.assertEqual(payload["sections"]["candles"]["qualityStatus"], "validated")

    def test_only_future_holdings_rows_make_the_section_unavailable(self) -> None:
        provider = IndependentProvider()
        batch = provider.behaviors["holdings"]
        assert isinstance(batch, ProviderBatch)
        future_row = copy.deepcopy(batch.items[0])
        future_row["available_at"] = (NOW + timedelta(seconds=1)).isoformat()
        provider.behaviors["holdings"] = ProviderBatch(
            "moomoo", batch.received_at, [future_row]
        )
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        holdings = payload["sections"]["holdings"]
        self.assertEqual(holdings["availabilityStatus"], "unavailable")
        self.assertEqual(holdings["errorCode"], "FUTURE_HOLDINGS_ROW")
        self.assertEqual(payload["sections"]["quote"]["qualityStatus"], "validated")

    def test_future_holdings_batch_provenance_rejects_nonempty_rows(self) -> None:
        provider = IndependentProvider()
        batch = provider.behaviors["holdings"]
        assert isinstance(batch, ProviderBatch)
        provider.behaviors["holdings"] = ProviderBatch(
            "moomoo",
            NOW + timedelta(seconds=1),
            copy.deepcopy(batch.items),
        )
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        holdings = payload["sections"]["holdings"]
        self.assertEqual(holdings["availabilityStatus"], "unavailable")
        self.assertEqual(holdings["qualityStatus"], "invalid")
        self.assertEqual(holdings["errorCode"], "MALFORMED_PROVIDER_DATA")
        self.assertIsNone(holdings["receivedAt"])
        self.assertIsNone(holdings["data"])

    def test_future_holdings_batch_provenance_rejects_an_empty_batch(self) -> None:
        provider = IndependentProvider()
        provider.behaviors["holdings"] = ProviderBatch(
            "moomoo",
            NOW + timedelta(seconds=1),
            [],
        )
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        holdings = payload["sections"]["holdings"]
        self.assertEqual(holdings["availabilityStatus"], "unavailable")
        self.assertEqual(holdings["qualityStatus"], "invalid")
        self.assertEqual(holdings["errorCode"], "MALFORMED_PROVIDER_DATA")
        self.assertIsNone(holdings["receivedAt"])
        self.assertIsNone(holdings["data"])

    def test_empty_candles_make_technical_explicitly_unavailable(self) -> None:
        provider = IndependentProvider()
        batch = provider.behaviors["candles"]
        assert isinstance(batch, ProviderBatch)
        provider.behaviors["candles"] = ProviderBatch("moomoo", batch.received_at, [])
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(payload["sections"]["candles"]["data"]["candles"], [])
        self.assertEqual(
            payload["sections"]["technical"]["errorCode"],
            "CANDLES_UNAVAILABLE",
        )
        self.assertEqual(payload["status"], "partial")

    def test_candle_failure_does_not_erase_validated_direct_flow(self) -> None:
        provider = IndependentProvider()
        provider.behaviors["candles"] = RuntimeError("raw candle failure")
        service, _, _ = self._service(provider)

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(
            payload["sections"]["candles"]["availabilityStatus"],
            "unavailable",
        )
        flow = payload["sections"]["currentSessionFlow"]
        self.assertEqual(flow["availabilityStatus"], "live")
        self.assertEqual(flow["qualityStatus"], "validated")
        self.assertEqual(flow["source"], "moomoo")
        self.assertEqual(flow["asOf"], "2026-07-25T03:50:00Z")
        self.assertEqual(flow["availableAt"], "2026-07-25T03:50:00Z")
        self.assertEqual(flow["receivedAt"], "2026-07-25T03:59:59Z")
        self.assertEqual(
            flow["methodVersion"],
            "provider-capital-flow-normalized-v1",
        )
        self.assertIsNone(flow["errorCode"])
        self.assertEqual(flow["data"][1]["largeOrderProxyNetFlow"], 1_800.0)
        self.assertFalse(flow["data"][1]["institutionalIdentity"])
        self.assertNotIn("coverage", flow["data"][1])

    def test_overall_deadline_stops_waiting_and_cancels_all_operations(self) -> None:
        provider = IndependentProvider()
        service, monotonic, executor = self._service(
            provider,
            delays=[30.0, 30.0, 30.0, 30.0],
            submit_latency=3.0,
        )

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(monotonic(), 12.0)
        self.assertEqual(len(executor.futures), 4)
        self.assertEqual(provider.source_calls, [])
        self.assertTrue(all(future.cancel_called for future in executor.futures))
        self.assertTrue(all(not future.result_timeouts for future in executor.futures))
        self.assertEqual(executor.shutdown_calls, [(False, True)])
        self.assertEqual(payload["status"], "unavailable")
        self.assertNotIn("error", payload)

    def test_done_future_completed_after_its_source_deadline_is_rejected(
        self,
    ) -> None:
        provider = IndependentProvider()
        monotonic = FakeMonotonic()
        executor = LateDoneExecutor(monotonic)
        service = MarketGatewayService(
            provider,
            clock=lambda: NOW,
            monotonic=monotonic,
            source_timeout_seconds=5.0,
            snapshot_deadline_seconds=12.0,
            executor_factory=executor.factory,  # type: ignore[arg-type]
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(
            payload["sections"]["quote"]["errorCode"],
            "PROVIDER_ERROR",
        )
        self.assertEqual(
            payload["sections"]["candles"]["qualityStatus"],
            "validated",
        )
        self.assertEqual(monotonic(), 6.0)

    def test_done_provider_error_completed_after_deadline_is_a_timeout(self) -> None:
        provider = IndependentProvider()
        provider.behaviors["quote"] = GatewayError(
            ErrorCode.OPEND_OFFLINE,
            "raw provider detail",
        )
        monotonic = FakeMonotonic()
        executor = LateDoneExecutor(monotonic)
        service = MarketGatewayService(
            provider,
            clock=lambda: NOW,
            monotonic=monotonic,
            source_timeout_seconds=5.0,
            snapshot_deadline_seconds=12.0,
            executor_factory=executor.factory,  # type: ignore[arg-type]
            session_max_age=timedelta(seconds=15),
            response_max_age=timedelta(seconds=15),
        )

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(
            payload["sections"]["quote"]["errorCode"],
            "PROVIDER_ERROR",
        )
        self.assertNotIn("raw provider detail", repr(payload))

    def test_overall_deadline_limits_the_last_source_wait_budget(self) -> None:
        provider = IndependentProvider()
        service, monotonic, executor = self._service(
            provider,
            delays=[30.0, 30.0, 30.0, 30.0],
            submit_latency=2.5,
        )

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(monotonic(), 12.0)
        self.assertEqual(
            [future.result_timeouts for future in executor.futures],
            [[], [], [], [2.0]],
        )
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(executor.shutdown_calls, [(False, True)])

    def test_invalid_request_fails_before_health_or_provider_calls(self) -> None:
        cases: tuple[tuple[Any, Any, Any], ...] = (
            ("", "5m", 200),
            ("NVDA", "tick", 200),
            ("NVDA", "5m", 0),
            ("NVDA", "5m", True),
        )
        for symbol, interval, count in cases:
            with self.subTest(symbol=symbol, interval=interval, count=count):
                provider = IndependentProvider()
                service, _, executor = self._service(provider)

                payload = service.stock_snapshot_v3(symbol, interval, count)

                self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
                self.assertEqual(provider.health_calls, 0)
                self.assertEqual(provider.source_calls, [])
                self.assertIsNone(executor.max_workers)

    def test_invalid_decision_cutoff_returns_a_boundary_error_not_a_v3_snapshot(
        self,
    ) -> None:
        provider = IndependentProvider()
        moments = iter((NOW, NOW, NOW.replace(tzinfo=None)))
        service, _, _ = self._service(provider, wall_clock=lambda: next(moments))

        payload = service.stock_snapshot_v3("NVDA", "5m", 200)

        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        self.assertNotEqual(payload.get("schemaVersion"), "3")


if __name__ == "__main__":
    unittest.main()
