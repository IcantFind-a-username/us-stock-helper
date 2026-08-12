from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
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


def snapshot(
    candles: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": "2",
        "source": "moomoo",
        "sourceStatus": "live",
        "symbol": "NVDA",
        "interval": "5m",
        "decisionCutoff": "2026-07-25T16:00:00Z",
        "priceAdjustment": "forward-adjusted",
        "quote": {},
        "completedCandles": [candle()] if candles is None else candles,
        "participationBars": [],
        "indicators": {},
        "institutionalHoldings": [],
        "provenance": [],
        "warnings": [],
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
        bars = provider(Gateway(snapshot())).bars_for("NVDA", "5m")

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
                snapshot(
                    [candle(), second],
                    decisionCutoff="2026-07-25T16:00:05Z",
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
                    provider(Gateway(snapshot([incomplete]))).bars_for("NVDA", "5m")

    def test_a_blank_point_in_time_field_is_refused_rather_than_defaulted(
        self,
    ) -> None:
        for field in ("availableAt", "receivedAt"):
            with self.subTest(field=field):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(
                        Gateway(snapshot([candle(**{field: None})]))
                    ).bars_for("NVDA", "5m")

    def test_a_receipt_that_precedes_publication_is_a_temporal_defect(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(snapshot([candle(receivedAt="2026-07-25T15:55:01Z")]))
            ).bars_for("NVDA", "5m")

    def test_a_receipt_after_the_decision_cutoff_is_a_temporal_defect(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(snapshot([candle(receivedAt="2026-07-25T16:00:01Z")]))
            ).bars_for("NVDA", "5m")

    def test_a_publication_after_the_decision_cutoff_is_a_temporal_defect(
        self,
    ) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(
                Gateway(
                    snapshot(
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
                Gateway(snapshot([candle(high=1.0)]))
            ).bars_for("NVDA", "5m")

    def test_an_incomplete_candle_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(snapshot([candle(complete=False)]))).bars_for(
                "NVDA", "5m"
            )

    def test_the_snapshot_must_answer_the_symbol_and_interval_that_were_asked(
        self,
    ) -> None:
        for override in ({"symbol": "TSLA"}, {"interval": "15m"}):
            with self.subTest(override=override):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(Gateway(snapshot(**override))).bars_for("NVDA", "5m")

    def test_an_interval_the_gateway_does_not_serve_is_refused(self) -> None:
        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(snapshot())).bars_for("NVDA", "tick")

    def test_the_request_names_the_symbol_interval_and_count(self) -> None:
        gateway = Gateway(snapshot())

        provider(gateway).bars_for("NVDA", "5m")

        self.assertEqual(
            gateway.urls,
            ["http://127.0.0.1:8765/stock-snapshot?symbol=NVDA&interval=5m&count=200"],
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
        envelope = {
            "schemaVersion": "1",
            "source": "moomoo",
            "session": "offline",
            "asOf": "2026-07-25T16:00:00Z",
            "availableAt": "2026-07-25T16:00:00Z",
            "items": [],
            "error": {
                "code": "OPEND_OFFLINE",
                "message": "moomoo OpenD is offline",
                "retriable": True,
            },
        }

        with self.assertRaises(MarketGatewayUnavailable) as raised:
            provider(Gateway(envelope)).bars_for("NVDA", "5m")

        # The code is what an operator needs; the upstream message is free to
        # describe its own provider and is deliberately not forwarded.
        self.assertIn("OPEND_OFFLINE", str(raised.exception))
        self.assertNotIn("OpenD is offline", str(raised.exception))

    def test_a_missing_candle_series_is_not_read_as_an_empty_series(self) -> None:
        payload = snapshot()
        del payload["completedCandles"]

        with self.assertRaises(MarketGatewayUnavailable):
            provider(Gateway(payload)).bars_for("NVDA", "5m")

    def test_a_body_that_is_not_the_snapshot_contract_is_refused(self) -> None:
        for body in (b"not json", b"[]", b'"NVDA"'):
            with self.subTest(body=body):
                with self.assertRaises(MarketGatewayUnavailable):
                    provider(Gateway(body=body)).bars_for("NVDA", "5m")

    def test_an_empty_candle_series_is_an_honest_zero(self) -> None:
        # Before the first bar of a session closes the gateway truly has no
        # completed candles, and that is data, not a failure.
        bars = provider(Gateway(snapshot([]))).bars_for("NVDA", "5m")

        self.assertEqual(bars, ())


class EvidenceTests(unittest.TestCase):
    def test_evidence_has_no_feed_and_says_so_by_returning_nothing(self) -> None:
        self.assertEqual(provider(Gateway(snapshot())).evidence_for("NVDA"), ())


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
            provider(Gateway(snapshot(rows))).bars_for("NVDA", "5m")

    def test_a_duplicated_close_time_is_refused(self) -> None:
        rows = two_candles()
        rows[1] = {**rows[1], "timestamp": rows[0]["timestamp"]}

        with self.assertRaisesRegex(MarketGatewayUnavailable, "order"):
            provider(Gateway(snapshot(rows))).bars_for("NVDA", "5m")

    def test_an_ascending_series_is_accepted(self) -> None:
        bars = provider(Gateway(snapshot(two_candles()))).bars_for("NVDA", "5m")

        self.assertGreater(len(bars), 1)
        for index in range(1, len(bars)):
            self.assertLess(bars[index - 1].closed_at, bars[index].closed_at)
