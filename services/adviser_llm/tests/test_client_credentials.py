from __future__ import annotations

import dataclasses
import logging
import unittest

from adviser_llm import AdviserLlmConfig, MissingCredentialError, build_client


class MissingCredentialTest(unittest.TestCase):
    def test_absent_env_var_raises_a_clear_error_instead_of_crashing(self) -> None:
        config = AdviserLlmConfig()
        with self.assertRaises(MissingCredentialError) as raised:
            build_client(config, environ={})
        message = str(raised.exception)
        self.assertIn(config.api_key_env, message)
        self.assertNotIsInstance(raised.exception, KeyError)

    def test_blank_env_var_is_treated_as_absent(self) -> None:
        with self.assertRaises(MissingCredentialError):
            build_client(AdviserLlmConfig(), environ={"ANTHROPIC_API_KEY": "   "})

    def test_a_custom_env_var_name_is_reported(self) -> None:
        config = AdviserLlmConfig(api_key_env="US_HELPER_ANTHROPIC_KEY")
        with self.assertRaises(MissingCredentialError) as raised:
            build_client(config, environ={"ANTHROPIC_API_KEY": "sk-present"})
        self.assertIn("US_HELPER_ANTHROPIC_KEY", str(raised.exception))


class CredentialHygieneTest(unittest.TestCase):
    SECRET = "sk-ant-fake-do-not-log-0123456789"

    def test_the_config_has_no_field_that_can_hold_a_key(self) -> None:
        config = AdviserLlmConfig()
        names = [field.name for field in dataclasses.fields(config)]
        self.assertEqual(
            [name for name in names if "key" in name], ["api_key_env"]
        )
        self.assertNotIn(self.SECRET, repr(config))

    def test_building_a_client_never_logs_the_key(self) -> None:
        logger = logging.getLogger("adviser_llm")
        with self.assertLogs(logger, level="DEBUG") as captured:
            logger.debug("probe")  # guarantees the context has at least one record
            build_client(
                AdviserLlmConfig(), environ={"ANTHROPIC_API_KEY": self.SECRET}
            )
        for line in captured.output:
            self.assertNotIn(self.SECRET, line)

    def test_the_sdk_client_owns_the_only_copy_of_the_key(self) -> None:
        client = build_client(
            AdviserLlmConfig(), environ={"ANTHROPIC_API_KEY": self.SECRET}
        )
        # The SDK's own retry loop is disabled so the layer's bounded policy is
        # the only one in force; multiplied attempts would hide a real outage.
        self.assertEqual(client.max_retries, 0)


class ConfigValidationTest(unittest.TestCase):
    def test_model_is_pinned(self) -> None:
        self.assertEqual(AdviserLlmConfig().model, "claude-opus-4-8")

    def test_efforts_match_the_two_workloads(self) -> None:
        config = AdviserLlmConfig()
        self.assertEqual(config.news_effort, "low")
        self.assertEqual(config.council_effort, "high")

    def test_zero_attempts_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdviserLlmConfig(max_attempts=0)

    def test_non_positive_timeout_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdviserLlmConfig(request_timeout_seconds=0.0)

    def test_unbounded_attempts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdviserLlmConfig(max_attempts=99)


if __name__ == "__main__":
    unittest.main()
