from __future__ import annotations

import unittest
from datetime import UTC, datetime

from information_layer.feeds import HttpRequest, HttpResponse
from us_stock_helper_analysis_api.factor_provider import (
    factor_provider_from_environment,
)


AS_OF = datetime(2026, 8, 14, 12, tzinfo=UTC)
CONTACT = {"US_STOCK_HELPER_CONTACT_EMAIL": "ops@example.test"}


class RoutingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def request(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if request.url.endswith("company_tickers.json"):
            body = (
                b'{"0":{"cik_str":1045810,"ticker":"NVDA",'
                b'"title":"NVIDIA CORP"}}'
            )
            status = 200
        else:
            body = b"source unavailable"
            status = 503
        return HttpResponse(
            status_code=status,
            headers=(),
            body=body,
            retrieved_at=AS_OF,
        )


class FactorProviderConfigTests(unittest.TestCase):
    def test_building_the_provider_performs_no_network_io(self) -> None:
        transport = RoutingTransport()

        factor_provider_from_environment(CONTACT, transport=transport)

        self.assertEqual(transport.requests, [])

    def test_the_sec_ticker_registry_is_loaded_lazily_and_cached(self) -> None:
        transport = RoutingTransport()
        provider = factor_provider_from_environment(CONTACT, transport=transport)

        first = provider.snapshot(symbol="NVDA", as_of=AS_OF)
        second = provider.snapshot(symbol="NVDA", as_of=AS_OF)

        ticker_requests = [
            request
            for request in transport.requests
            if request.url.endswith("company_tickers.json")
        ]
        self.assertEqual(len(ticker_requests), 1)
        self.assertIsNone(first.fundamentals.value)
        self.assertIsNone(second.fundamentals.value)

    def test_a_contact_address_is_required_before_any_sec_source_is_built(self) -> None:
        with self.assertRaises(Exception) as failure:
            factor_provider_from_environment({})

        self.assertIn("US_STOCK_HELPER_CONTACT_EMAIL", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
