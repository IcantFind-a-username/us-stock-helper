from __future__ import annotations

import unittest

import anthropic

try:
    import httpx  # anthropic < 1.0 depends on httpx for its transport
except ModuleNotFoundError:  # anthropic >= 1.0 renamed the dependency to httpx2
    import httpx2 as httpx  # type: ignore[import-not-found,no-redef]

from adviser_llm import AdviserLlmConfig, LlmUnavailableError, call_with_retry


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _timeout() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=_request())


def _connection() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_request())


def _overloaded() -> anthropic.InternalServerError:
    return anthropic.InternalServerError(
        "overloaded",
        response=httpx.Response(529, request=_request()),
        body=None,
    )


class _Recorder:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RetryPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slept: list[float] = []

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def test_a_timeout_is_retried_up_to_the_configured_limit(self) -> None:
        config = AdviserLlmConfig(max_attempts=3, retry_backoff_seconds=0.5)
        recorder = _Recorder([_timeout()])
        with self.assertRaises(LlmUnavailableError):
            call_with_retry(recorder, config=config, sleep=self._sleep)
        self.assertEqual(recorder.calls, 3)

    def test_retries_stop_at_the_limit_and_never_loop_forever(self) -> None:
        config = AdviserLlmConfig(max_attempts=2, retry_backoff_seconds=0.1)
        recorder = _Recorder([_connection()])
        with self.assertRaises(LlmUnavailableError):
            call_with_retry(recorder, config=config, sleep=self._sleep)
        self.assertEqual(recorder.calls, 2)
        self.assertEqual(len(self.slept), 1)

    def test_backoff_grows_between_attempts(self) -> None:
        config = AdviserLlmConfig(max_attempts=3, retry_backoff_seconds=0.5)
        with self.assertRaises(LlmUnavailableError):
            call_with_retry(
                _Recorder([_overloaded()]), config=config, sleep=self._sleep
            )
        self.assertEqual(self.slept, [0.5, 1.0])

    def test_a_recovered_call_returns_its_value(self) -> None:
        config = AdviserLlmConfig(max_attempts=3, retry_backoff_seconds=0.1)
        recorder = _Recorder([_timeout(), "ok"])
        self.assertEqual(
            call_with_retry(recorder, config=config, sleep=self._sleep), "ok"
        )
        self.assertEqual(recorder.calls, 2)

    def test_a_bad_request_is_not_retried(self) -> None:
        config = AdviserLlmConfig(max_attempts=3, retry_backoff_seconds=0.1)
        failure = anthropic.BadRequestError(
            "bad schema",
            response=httpx.Response(400, request=_request()),
            body=None,
        )
        recorder = _Recorder([failure])
        with self.assertRaises(LlmUnavailableError):
            call_with_retry(recorder, config=config, sleep=self._sleep)
        self.assertEqual(recorder.calls, 1)
        self.assertEqual(self.slept, [])

    def test_the_failure_reports_how_many_attempts_were_spent(self) -> None:
        config = AdviserLlmConfig(max_attempts=2, retry_backoff_seconds=0.1)
        with self.assertRaises(LlmUnavailableError) as raised:
            call_with_retry(
                _Recorder([_timeout()]), config=config, sleep=self._sleep
            )
        self.assertEqual(raised.exception.attempts, 2)
        self.assertIn("2", str(raised.exception))


class TimeoutWiringTest(unittest.TestCase):
    def test_the_two_workloads_carry_different_deadlines(self) -> None:
        config = AdviserLlmConfig()
        self.assertGreater(
            config.council_timeout_seconds, config.request_timeout_seconds
        )

    def test_every_deadline_is_finite(self) -> None:
        config = AdviserLlmConfig()
        for value in (
            config.request_timeout_seconds,
            config.council_timeout_seconds,
        ):
            self.assertTrue(0 < value < float("inf"))


if __name__ == "__main__":
    unittest.main()
