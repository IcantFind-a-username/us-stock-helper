from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import URLError

from us_stock_helper_analysis_api.gateway_provider import (
    MarketGatewayProvider,
    MarketGatewayUnavailable,
    provider_from_environment,
)


CLOSED_AT = datetime(2026, 7, 25, 15, 55, tzinfo=UTC)
OPENED_AT = datetime(2026, 7, 25, 15, 50, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 7, 25, 15, 55, 2, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 7, 25, 15, 55, 4, tzinfo=UTC)


def candle(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "timestamp": "2026-07-25T15:55:00Z",
        "complete": True,
        "open": 100.0,
        "high": 101.0,
        "low": 99.5,
        "close": 100.75,
        "volume": 1_000_000.0,
        "source": "moomoo",
        "asOf": "2026-07-25T15:55:00Z",
        "availableAt": "2026-07-25T15:55:02Z",
        "receivedAt": "2026-07-25T15:55:04Z",
        "priceAdjustment": "forward-adjusted",
        "methodVersion": "provider-completed-candle-v1",
        "qualityStatus": "live",
    }
    item.update(overrides)
    return item


def candle_envelope(
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "1",
        "source": "moomoo",
        "session": "healthy",
        "asOf": "2026-07-25T16:00:00Z",
        "availableAt": "2026-07-25T16:00:00Z",
        "symbol": "NVDA",
        "interval": "5m",
        "items": [candle()] if items is None else items,
    }
    payload.update(overrides)
    return payload


class Gateway:
    """A stand-in for the gateway's HTTP surface, recording what was asked."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        raises: Exception | None = None,
        body: bytes | None = None,
    ) -> None:
        self.payload = payload
        self.raises = raises
        self.body = body
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.raises is not None:
            raise self.raises
        if self.body is not None:
            return self.body
        return json.dumps(self.payload).encode("utf-8")


def provider(gateway: Gateway) -> MarketGatewayProvider:
    return MarketGatewayProvider(base_url="http://127.0.0.1:8765", fetch=gateway)


class CandleConversionTests(unittest.TestCase):
    def test_a_gateway_candle_becomes_a_bar_carrying_its_publication_time(
        self,
    ) -> None:
        bars = provider(Gateway(candle_envelope())).bars_for("NVDA", "5m")

        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar.symbol, "NVDA")
        self.assertEqual(bar.interval, "5m")
        self.assertEqual(bar.closed_at, CLOSED_AT)
        self.assertEqual(bar.opened_at, OPENED_AT)
        # availableAt is the exchange publication moment and is the instant the
        # decision chain is allowed to know the bar; receivedAt is the
        # gateway's own receipt and must never stand in for it.
        self.assertEqual(bar.available_at, PUBLISHED_AT)
        self.assertNotEqual(bar.available_at, RECEIVED_AT)
        self.assertEqual(bar.open, 100.0)
        self.assertEqual(bar.high, 101.0)
        self.assertEqual(bar.low, 99.5)
        self.assertEqual(bar.close, 100.75)
        self.assertEqual(bar.volume, 1_000_000.0)
        self.assertTrue(bar.complete)

    def test_envelope_availability_not_last_bar_time_is_the_read_cutoff(self) -> None:
        payload = candle_envelope(
            asOf="2026-07-25T15:55:02Z",
            availableAt="2026-07-25T16:00:00Z",
        )

        bars = provider(Gateway(payload)).bars_for("NVDA", "5m")

        self.assertEqual(len(bars), 1)

    def test_envelope_publication_after_availability_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(
                    candle_envelope(
                        [],
                        asOf="2026-07-25T16:00:01Z",
                        availableAt="2026-07-25T16:00:00Z",
                    )
                )
            ).bars_for("NVDA", "5m")

    def test_candle_publication_after_envelope_as_of_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(
                    candle_envelope(
                        [
                            candle(
                                availableAt="2026-07-25T16:00:01Z",
                                receivedAt="2026-07-25T16:00:02Z",
                            )
                        ],
                        asOf="2026-07-25T16:00:00Z",
                        availableAt="2026-07-25T16:00:05Z",
                    )
                )
            ).bars_for("NVDA", "5m")

    def test_bars_keep_the_order_the_gateway_published_them_in(self) -> None:
        second = candle(
            timestamp="2026-07-25T16:00:00Z",
            availableAt="2026-07-25T16:00:02Z",
            receivedAt="2026-07-25T16:00:04Z",
            close=101.5,
            high=102.0,
        )
        bars = provider(
            Gateway(
                candle_envelope(
                    [candle(), second],
                    asOf="2026-07-25T16:00:05Z",
                    availableAt="2026-07-25T16:00:05Z",
                )
            )
        ).bars_for("NVDA", "5m")

        self.assertEqual([bar.closed_at for bar in bars], [CLOSED_AT, CLOSED_AT.replace(hour=16, minute=0)])

    def test_a_candle_missing_either_point_in_time_field_is_refused(self) -> None:
        for field in ("availableAt", "receivedAt", "timestamp"):
            with self.subTest(field=field):
                incomplete = {
                    key: value
                    for key, value in candle().items()
                    if key != field
                }
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(Gateway(candle_envelope([incomplete]))).bars_for("NVDA", "5m")

    def test_a_blank_point_in_time_field_is_refused_rather_than_defaulted(
        self,
    ) -> None:
        for field in ("availableAt", "receivedAt"):
            with self.subTest(field=field):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(
                        Gateway(candle_envelope([candle(**{field: None})]))
                    ).bars_for("NVDA", "5m")

    def test_a_receipt_that_precedes_publication_is_a_temporal_defect(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(candle_envelope([candle(receivedAt="2026-07-25T15:55:01Z")]))
            ).bars_for("NVDA", "5m")

    def test_a_receipt_after_envelope_availability_is_a_temporal_defect(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(candle_envelope([candle(receivedAt="2026-07-25T16:00:01Z")]))
            ).bars_for("NVDA", "5m")

    def test_a_publication_after_envelope_as_of_is_a_temporal_defect(
        self,
    ) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(
                    candle_envelope(
                        [
                            candle(
                                availableAt="2026-07-25T16:00:01Z",
                                receivedAt="2026-07-25T16:00:02Z",
                            )
                        ]
                    )
                )
            ).bars_for("NVDA", "5m")

    def test_a_bar_the_domain_model_refuses_does_not_escape_as_a_crash(self) -> None:
        # closed_at after available_at breaks the model's own invariant, and
        # the boundary owes the caller its one failure type rather than a
        # ValueError from three layers down.
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(candle_envelope([candle(high=1.0)]))
            ).bars_for("NVDA", "5m")

    def test_an_incomplete_candle_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(candle_envelope([candle(complete=False)]))).bars_for(
                "NVDA", "5m"
            )

    def test_the_candle_envelope_must_answer_the_symbol_and_interval_that_were_asked(
        self,
    ) -> None:
        for override in ({"symbol": "TSLA"}, {"interval": "15m"}):
            with self.subTest(override=override):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(Gateway(candle_envelope(**override))).bars_for("NVDA", "5m")

    def test_an_interval_the_gateway_does_not_serve_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(candle_envelope())).bars_for("NVDA", "tick")

    def test_the_request_names_the_symbol_interval_and_count(self) -> None:
        gateway = Gateway(candle_envelope())

        provider(gateway).bars_for("NVDA", "5m")

        self.assertEqual(
            gateway.urls,
            ["http://127.0.0.1:8765/candles?symbol=NVDA&interval=5m&count=200"],
        )


class GatewayFailureTests(unittest.TestCase):
    def test_an_unreachable_gateway_fails_loudly_instead_of_reporting_no_bars(
        self,
    ) -> None:
        # An empty series reads as "the market produced nothing", which the
        # analysis service reports as a legitimate unavailable decision. A
        # transport failure must never be able to say that.
        for failure in (
            URLError("connection refused"),
            TimeoutError("read timed out"),
            OSError("network is unreachable"),
        ):
            with self.subTest(failure=type(failure).__name__):
                gateway = Gateway(raises=failure)

                with self.assertRaises(MarketGatewayUnavailable):
                    provider(gateway).bars_for("NVDA", "5m")

    def test_a_gateway_error_envelope_is_not_read_as_an_empty_series(self) -> None:
        envelope = candle_envelope(
            items=[],
            session="offline",
            error={
                "code": "OPEND_OFFLINE",
                "message": "moomoo OpenD is offline",
                "retriable": True,
            },
        )

        with self.assertRaises(MarketGatewayUnavailable) as raised:
            provider(Gateway(envelope)).bars_for("NVDA", "5m")

        # The code is what an operator needs; the upstream message is free to
        # describe its own provider and is deliberately not forwarded.
        self.assertIn("OPEND_OFFLINE", str(raised.exception))
        self.assertNotIn("OpenD is offline", str(raised.exception))

    def test_a_missing_candle_series_is_not_read_as_an_empty_series(self) -> None:
        payload = candle_envelope()
        del payload["items"]

        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(payload)).bars_for("NVDA", "5m")

    def test_a_body_that_is_not_the_candle_contract_is_refused(self) -> None:
        for body in (b"not json", b"[]", b'"NVDA"'):
            with self.subTest(body=body):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(Gateway(body=body)).bars_for("NVDA", "5m")

    def test_an_empty_candle_series_is_an_honest_zero(self) -> None:
        # Before the first bar of a session closes the gateway truly has no
        # completed candles, and that is data, not a failure.
        bars = provider(Gateway(candle_envelope([]))).bars_for("NVDA", "5m")

        self.assertEqual(bars, ())


def watchlist_envelope(
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "1",
        "source": "moomoo",
        "session": "healthy",
        "asOf": "2026-07-25T16:00:00Z",
        "availableAt": "2026-07-25T16:00:00Z",
        "items": (
            [{"code": "US.NVDA", "price": 173.4, "changePercent": 2.7, "availableAt": "2026-07-25T16:00:00Z"}]
            if items is None
            else items
        ),
    }
    payload.update(overrides)
    return payload


class WatchlistSymbolsTests(unittest.TestCase):
    def test_watchlist_items_become_plain_us_symbols(self) -> None:
        symbols = provider(
            Gateway(
                watchlist_envelope(
                    [
                        {"code": "US.NVDA", "price": 173.4, "changePercent": 2.7, "availableAt": "2026-07-25T16:00:00Z"},
                        {"code": "US.TSLA", "price": 250.0, "changePercent": -1.2, "availableAt": "2026-07-25T16:00:00Z"},
                    ]
                )
            )
        ).watchlist_symbols()

        self.assertEqual(symbols, ("NVDA", "TSLA"))

    def test_the_request_names_no_query_parameters(self) -> None:
        gateway = Gateway(watchlist_envelope())

        provider(gateway).watchlist_symbols()

        self.assertEqual(gateway.urls, ["http://127.0.0.1:8765/watchlist"])

    def test_duplicate_codes_are_collapsed_in_first_seen_order(self) -> None:
        symbols = provider(
            Gateway(
                watchlist_envelope(
                    [
                        {"code": "US.NVDA", "price": 173.4, "changePercent": 2.7, "availableAt": "2026-07-25T16:00:00Z"},
                        {"code": "US.NVDA", "price": 173.4, "changePercent": 2.7, "availableAt": "2026-07-25T16:00:00Z"},
                    ]
                )
            )
        ).watchlist_symbols()

        self.assertEqual(symbols, ("NVDA",))

    def test_an_empty_watchlist_is_an_honest_empty_tuple(self) -> None:
        symbols = provider(Gateway(watchlist_envelope([]))).watchlist_symbols()

        self.assertEqual(symbols, ())

    def test_an_unhealthy_session_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(
                    watchlist_envelope(
                        [],
                        session="offline",
                        error={"code": "OPEND_OFFLINE", "message": "offline"},
                    )
                )
            ).watchlist_symbols()

    def test_an_unreachable_gateway_fails_loudly(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(raises=URLError("connection refused"))).watchlist_symbols()

    def test_a_body_that_is_not_the_watchlist_contract_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(body=b"not json")).watchlist_symbols()

    def test_a_malformed_item_is_refused_not_silently_dropped(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(watchlist_envelope([{"price": 173.4}]))
            ).watchlist_symbols()


class EvidenceTests(unittest.TestCase):
    def test_the_gateway_boundary_does_not_answer_for_evidence(self) -> None:
        # It once returned an empty tuple, which read as "the market is quiet"
        # no matter what the evidence sources were doing. Evidence now has its
        # own provider, with its own failures.
        self.assertFalse(hasattr(provider(Gateway(candle_envelope())), "evidence_for"))


class ProviderConfigTests(unittest.TestCase):
    def test_the_default_endpoint_is_the_loopback_gateway(self) -> None:
        built = provider_from_environment({})

        self.assertEqual(built.base_url, "http://127.0.0.1:8765")
        self.assertEqual(built.count, 200)

    def test_a_credential_bearing_or_remote_gateway_url_is_refused(self) -> None:
        for url in (
            "ftp://127.0.0.1:8765",
            "file:///etc/passwd",
            "http://user@127.0.0.1:8765",
            "http://:secret@127.0.0.1:8765",
            "http://user:secret@127.0.0.1:8765",
            "http://127.0.0.1:8765?token=secret",
            "http://127.0.0.1:8765#token",
            "http://127.0.0.1:8765/api",
            "http://192.168.1.10:8765",
            "not a url",
            "",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    provider_from_environment({"ANALYSIS_API_GATEWAY_URL": url})

    def test_a_loopback_gateway_url_is_accepted_without_its_trailing_slash(
        self,
    ) -> None:
        built = provider_from_environment(
            {"ANALYSIS_API_GATEWAY_URL": "http://localhost:9000/"}
        )

        self.assertEqual(built.base_url, "http://localhost:9000")

    def test_the_candle_count_must_stay_inside_the_gateway_limit(self) -> None:
        for count in ("0", "1001", "many", "-5"):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    provider_from_environment({"ANALYSIS_API_CANDLE_COUNT": count})

        self.assertEqual(
            provider_from_environment({"ANALYSIS_API_CANDLE_COUNT": "300"}).count,
            300,
        )

    def test_the_gateway_read_must_carry_a_bounded_timeout(self) -> None:
        # Without a bound a hung gateway holds a request thread forever, and
        # the caller never learns that the answer is not coming.
        for timeout in ("0", "-1", "nan", "soon", "61"):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    provider_from_environment(
                        {"ANALYSIS_API_GATEWAY_TIMEOUT_SECONDS": timeout}
                    )


if __name__ == "__main__":
    unittest.main()


def two_candles() -> list[dict[str, Any]]:
    return [
        candle(
            timestamp="2026-07-25T15:50:00Z",
            availableAt="2026-07-25T15:50:00Z",
            receivedAt="2026-07-25T15:50:01Z",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
        ),
        candle(
            timestamp="2026-07-25T15:55:00Z",
            availableAt="2026-07-25T15:55:00Z",
            receivedAt="2026-07-25T15:55:01Z",
            open=123.0,
            high=124.0,
            low=122.5,
            close=123.6,
        ),
    ]


class BarOrderingTests(unittest.TestCase):
    def test_candles_out_of_order_are_refused_not_silently_mispriced(self) -> None:
        """The chain reads the last bar as the current price.

        A gateway that answered newest-first would hand the decision an old
        close as "now" — plausible, wrong, and with nothing to notice. The
        market gateway rejects this on its own side; so must this one.
        """

        rows = list(reversed(two_candles()))

        with self.assertRaisesRegex(MarketGatewayUnavailable, "order"):
            provider(Gateway(candle_envelope(rows))).bars_for("NVDA", "5m")

    def test_a_duplicated_close_time_is_refused(self) -> None:
        rows = two_candles()
        rows[1] = {**rows[1], "timestamp": rows[0]["timestamp"]}

        with self.assertRaisesRegex(MarketGatewayUnavailable, "order"):
            provider(Gateway(candle_envelope(rows))).bars_for("NVDA", "5m")

    def test_an_ascending_series_is_accepted(self) -> None:
        bars = provider(Gateway(candle_envelope(two_candles()))).bars_for("NVDA", "5m")

        self.assertGreater(len(bars), 1)
        for index in range(1, len(bars)):
            self.assertLess(bars[index - 1].closed_at, bars[index].closed_at)


# --- institutional-flow inputs (v3 snapshot: currentSessionFlow + candles + holdings) ---

AS_OF = datetime(2026, 7, 25, 16, tzinfo=UTC)


def flow_row(
    hour: int,
    minute: int,
    *,
    super_net: float,
    big_net: float,
    mid_net: float,
    small_net: float,
    session: str = "regular",
    available_at: str | None = None,
) -> dict[str, Any]:
    timestamp = f"2026-07-25T{hour:02d}:{minute:02d}:00Z"
    return {
        "timestamp": timestamp,
        "availableAt": available_at or timestamp,
        "session": session,
        "totalNetFlow": super_net + big_net + mid_net + small_net,
        "extraLargeOrderNetFlow": super_net,
        "largeOrderNetFlow": big_net,
        "mediumOrderNetFlow": mid_net,
        "smallOrderNetFlow": small_net,
        "largeOrderProxyNetFlow": super_net + big_net,
        "institutionalIdentity": False,
    }


def live_flow_rows() -> list[dict[str, Any]]:
    """Six one-minute points covering one 5m candle (15:50-15:55).

    Each minute's bucket deltas are (+10, +10, -5, -5) for
    (super, big, mid, small), so every consecutive pair contributes
    main_activity += 20, retail_activity += 10, net_flow += 10. Over five
    pairs: main_activity=100, retail_activity=50 (denominator 150), and
    net_flow=50, giving a clean proxy_raw of net_flow/denominator = 1/3.
    """

    return [
        flow_row(15, 50, super_net=0.0, big_net=0.0, mid_net=100.0, small_net=100.0),
        flow_row(15, 51, super_net=10.0, big_net=10.0, mid_net=95.0, small_net=95.0),
        flow_row(15, 52, super_net=20.0, big_net=20.0, mid_net=90.0, small_net=90.0),
        flow_row(15, 53, super_net=30.0, big_net=30.0, mid_net=85.0, small_net=85.0),
        flow_row(15, 54, super_net=40.0, big_net=40.0, mid_net=80.0, small_net=80.0),
        flow_row(15, 55, super_net=50.0, big_net=50.0, mid_net=75.0, small_net=75.0),
    ]


def flow_section(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    data = live_flow_rows() if rows is None else rows
    return {
        "availabilityStatus": "live",
        "qualityStatus": "validated" if data else "invalid",
        "source": "moomoo",
        "asOf": data[-1]["timestamp"] if data else None,
        "availableAt": data[-1]["availableAt"] if data else None,
        "receivedAt": AS_OF.isoformat().replace("+00:00", "Z"),
        "data": data,
        "errorCode": None,
        "reason": None,
        "warnings": [],
        "anomalies": [],
        "methodVersion": "provider-capital-flow-normalized-v1",
    }


def candles_section(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = [candle()] if items is None else items
    return {
        "availabilityStatus": "live",
        "qualityStatus": "validated",
        "source": "moomoo",
        "asOf": rows[-1]["asOf"] if rows else None,
        "availableAt": rows[-1]["availableAt"] if rows else None,
        "receivedAt": rows[-1]["receivedAt"] if rows else None,
        "data": {"candles": rows, "priceAdjustment": "forward-adjusted"},
        "errorCode": None,
        "reason": None,
        "warnings": [],
        "anomalies": [],
        "methodVersion": "provider-completed-candle-v1",
    }


def holding_row(
    *,
    reported_at: str = "2026-06-30T00:00:00Z",
    available_at: str = "2026-07-20T22:00:00Z",
    holding_percent: float = 62.0,
    holding_percent_change: float = 2.5,
    institution_count_change: int = 3,
) -> dict[str, Any]:
    return {
        "period": "2026/Q2",
        "reportedAt": reported_at,
        "reportedAtBasis": "reporting-period-end",
        "availableAt": available_at,
        "source": "moomoo-delayed-institutional-disclosure",
        "institutionCount": 120,
        "institutionCountChange": institution_count_change,
        "sharesHeld": 500_000_000.0,
        "sharesHeldChange": 10_000_000.0,
        "holdingPercent": holding_percent,
        "holdingPercentChange": holding_percent_change,
    }


def holdings_section(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    data = [holding_row()] if rows is None else rows
    return {
        "availabilityStatus": "delayed" if data else "unavailable",
        "qualityStatus": "validated" if data else "invalid",
        "source": "moomoo-delayed-institutional-disclosure",
        "asOf": data[0]["reportedAt"] if data else None,
        "availableAt": data[0]["availableAt"] if data else None,
        "receivedAt": AS_OF.isoformat().replace("+00:00", "Z"),
        "data": data,
        "errorCode": None if data else "HOLDINGS_UNAVAILABLE",
        "reason": None if data else "机构持仓数据不可用",
        "warnings": [],
        "anomalies": [],
        "methodVersion": "reported-holdings-v2-anomaly-aware",
    }


def v3_snapshot(
    *,
    symbol: str = "NVDA",
    flow: dict[str, Any] | None = None,
    candles: dict[str, Any] | None = None,
    holdings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "3",
        "status": "live",
        "symbol": symbol,
        "interval": "5m",
        "count": 12,
        "decisionCutoff": AS_OF.isoformat().replace("+00:00", "Z"),
        "requestedSections": [
            "quote",
            "candles",
            "technical",
            "currentSessionFlow",
            "holdings",
        ],
        "sections": {
            "quote": {"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
            "candles": candles_section() if candles is None else candles,
            "technical": {"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
            "currentSessionFlow": flow_section(None) if flow is None else flow,
            "holdings": holdings_section(None) if holdings is None else holdings,
            "marketContext": {"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
            "news": {"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
            "forecastDecision": {"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
        },
    }


class InstitutionalFlowInputsTests(unittest.TestCase):
    def test_the_request_names_the_symbol_interval_and_count(self) -> None:
        gateway = Gateway(v3_snapshot())

        provider(gateway).institutional_flow_inputs_for("NVDA", AS_OF)

        self.assertEqual(
            gateway.urls,
            ["http://127.0.0.1:8765/v3/stock-snapshot?symbol=NVDA&interval=5m&count=12"],
        )

    def test_a_live_participation_bar_and_a_holdings_row_both_arrive(self) -> None:
        inputs = provider(Gateway(v3_snapshot())).institutional_flow_inputs_for(
            "NVDA", AS_OF
        )

        self.assertEqual(len(inputs.participation_bars), 1)
        bar = inputs.participation_bars[0]
        self.assertEqual(bar.quality_status, "live")
        self.assertAlmostEqual(bar.main_activity, 100.0)
        self.assertAlmostEqual(bar.retail_activity, 50.0)
        self.assertAlmostEqual(bar.net_flow, 50.0)

        self.assertEqual(len(inputs.holdings), 1)
        self.assertAlmostEqual(inputs.holdings[0].holding_percent_change, 2.5)
        self.assertEqual(inputs.holdings[0].institution_count_change, 3)

    def test_a_holdings_row_exactly_at_the_cutoff_is_included(self) -> None:
        # Pins the PIT boundary as `<=`, not `<`: a mutation to strict-less
        # would silently drop a disclosure the decision was entitled to see.
        row = holding_row(available_at=AS_OF.isoformat().replace("+00:00", "Z"))

        inputs = provider(
            Gateway(v3_snapshot(holdings=holdings_section([row])))
        ).institutional_flow_inputs_for("NVDA", AS_OF)

        self.assertEqual(len(inputs.holdings), 1)

    def test_a_holdings_row_one_microsecond_after_the_cutoff_is_dropped(self) -> None:
        # Pins the same boundary from the other side: a mutation to `<=`
        # (or the check's removal) would leak a filing across the cutoff.
        future = AS_OF + timedelta(microseconds=1)
        row = holding_row(available_at=future.isoformat().replace("+00:00", "Z"))

        inputs = provider(
            Gateway(v3_snapshot(holdings=holdings_section([row])))
        ).institutional_flow_inputs_for("NVDA", AS_OF)

        self.assertEqual(inputs.holdings, ())

    def test_neither_ingredient_available_yields_two_honest_empty_tuples(self) -> None:
        empty_snapshot = v3_snapshot(
            flow={"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
            holdings={"availabilityStatus": "unavailable", "qualityStatus": "invalid"},
        )

        inputs = provider(Gateway(empty_snapshot)).institutional_flow_inputs_for(
            "NVDA", AS_OF
        )

        self.assertEqual(inputs.participation_bars, ())
        self.assertEqual(inputs.holdings, ())

    def test_flow_without_candles_yields_no_participation_bar(self) -> None:
        no_candles = v3_snapshot(
            candles={"availabilityStatus": "unavailable", "qualityStatus": "invalid"}
        )

        inputs = provider(Gateway(no_candles)).institutional_flow_inputs_for(
            "NVDA", AS_OF
        )

        self.assertEqual(inputs.participation_bars, ())
        # Holdings is a separate ingredient and must not be dragged down by
        # the other one's absence.
        self.assertEqual(len(inputs.holdings), 1)

    def test_a_row_claiming_institutional_identity_is_refused(self) -> None:
        rows = live_flow_rows()
        rows[0] = {**rows[0], "institutionalIdentity": True}

        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(v3_snapshot(flow=flow_section(rows)))
            ).institutional_flow_inputs_for("NVDA", AS_OF)

    def test_a_malformed_holdings_row_is_refused_not_silently_dropped(self) -> None:
        bad_row = {**holding_row(), "source": "some-other-source"}

        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(v3_snapshot(holdings=holdings_section([bad_row])))
            ).institutional_flow_inputs_for("NVDA", AS_OF)

    def test_an_unsupported_schema_version_is_refused(self) -> None:
        payload = v3_snapshot()
        payload["schemaVersion"] = "2"

        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(payload)).institutional_flow_inputs_for("NVDA", AS_OF)

    def test_an_answer_for_a_different_symbol_is_refused(self) -> None:
        payload = v3_snapshot(symbol="TSLA")

        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(payload)).institutional_flow_inputs_for("NVDA", AS_OF)

    def test_an_unreachable_gateway_fails_loudly(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(raises=URLError("connection refused"))
            ).institutional_flow_inputs_for("NVDA", AS_OF)
