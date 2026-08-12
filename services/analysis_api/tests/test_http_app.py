from __future__ import annotations

import unittest
from datetime import UTC, datetime

from us_stock_helper_analysis_api.http_app import AnalysisApplication

from test_analysis_service import AS_OF, Provider, service


def app() -> AnalysisApplication:
    return AnalysisApplication(service(Provider()), clock=lambda: AS_OF)


class HttpBoundaryTests(unittest.TestCase):
    def test_a_decision_is_served_over_get(self) -> None:
        status, headers, body = app().handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["symbol"], "NVDA")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_write_methods_fail_closed(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, _, body = app().handle(
                    method, "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
                )

                self.assertEqual(status, 405)
                self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_paths_outside_the_allowlist_are_refused(self) -> None:
        for path in ("/orders", "/decision/../secrets", "/"):
            with self.subTest(path=path):
                status, _, body = app().handle("GET", path, {})

                self.assertEqual(status, 404)
                self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_a_missing_or_repeated_parameter_is_a_client_error(self) -> None:
        for query in (
            {},
            {"symbol": ["NVDA"]},
            {"symbol": ["NVDA", "TSLA"], "horizon": ["short"]},
        ):
            with self.subTest(query=query):
                status, _, body = app().handle("GET", "/decision", query)

                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

    def test_an_unknown_horizon_is_a_client_error_not_a_crash(self) -> None:
        status, _, body = app().handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["forever"]}
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

    def test_an_internal_failure_does_not_leak_its_details(self) -> None:
        class Exploding:
            def bars_for(self, symbol: str, interval: str) -> tuple[()]:
                raise RuntimeError("account=123 token=secret")

            def evidence_for(self, symbol: str) -> tuple[()]:
                return ()

        from us_stock_helper_analysis_api.service import AnalysisService

        failing = AnalysisApplication(
            AnalysisService(Exploding(), clock=lambda: AS_OF),  # type: ignore[arg-type]
            clock=lambda: AS_OF,
        )

        status, _, body = failing.handle(
            "GET", "/decision", {"symbol": ["NVDA"], "horizon": ["short"]}
        )

        self.assertEqual(status, 500)
        self.assertNotIn("secret", repr(body))
        self.assertNotIn("account", repr(body))

    def test_the_health_path_reports_readiness_without_data(self) -> None:
        status, _, body = app().handle("GET", "/health", {})

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ready")
        self.assertTrue(body["asOf"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
