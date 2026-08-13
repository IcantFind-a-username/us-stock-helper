from __future__ import annotations

import threading
import unittest
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

from us_stock_helper_device_auth.credentials import (
    MAX_CODE_LENGTH,
    MIN_CODE_LENGTH,
    ScryptParameters,
)
from us_stock_helper_device_auth.errors import DeviceAuthError, ErrorCode
from us_stock_helper_device_auth.service import AttemptOutcome, PairingOutcome
from us_stock_helper_device_auth.store import MAX_CANDIDATE_CODES, DeviceStore

from support import StoreCase

CLIENT = "198.51.100.4"


class IssuingPairingCodeTests(StoreCase):
    def test_an_issued_code_is_human_readable_and_short_lived(self) -> None:
        service = self.service()

        issued = service.issue_pairing_code(label="franz-iphone")

        self.assertTrue(MIN_CODE_LENGTH <= len(issued.code) <= MAX_CODE_LENGTH)
        self.assertEqual(issued.label, "franz-iphone")
        self.assertEqual(issued.expires_at, self.clock() + timedelta(minutes=10))

    def test_the_lifetime_is_configurable_and_must_stay_short(self) -> None:
        service = self.service(code_ttl=timedelta(minutes=2))

        self.assertEqual(
            service.issue_pairing_code(label="iphone").expires_at,
            self.clock() + timedelta(minutes=2),
        )

        for ttl in (timedelta(0), timedelta(seconds=-1), timedelta(hours=2)):
            with self.subTest(ttl=ttl):
                with self.assertRaises(DeviceAuthError):
                    self.service(code_ttl=ttl).issue_pairing_code(label="iphone")

    def test_a_naive_clock_is_refused_rather_than_read_as_utc(self) -> None:
        # The clock is injectable so tests can move it; that is also how a host
        # configured with a local-time clock would silently store the wrong
        # expiry, so an unaware datetime has to stop the call.
        local = self.service(clock=lambda: datetime(2026, 8, 12, 17, 0))

        with self.assertRaises(DeviceAuthError) as caught:
            local.issue_pairing_code(label="iphone")

        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_a_label_that_could_rewrite_the_operator_terminal_is_refused(self) -> None:
        service = self.service()

        for label in ("", "   ", "a" * 65, "iphone\x1b[2J", "iphone\nrm -rf /"):
            with self.subTest(label=label):
                with self.assertRaises(DeviceAuthError) as caught:
                    service.issue_pairing_code(label=label)
                self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_the_number_of_live_codes_is_capped(self) -> None:
        service = self.service()
        for index in range(5):
            service.issue_pairing_code(label=f"phone-{index}")

        with self.assertRaises(DeviceAuthError) as caught:
            service.issue_pairing_code(label="one-too-many")
        self.assertEqual(caught.exception.code, ErrorCode.TOO_MANY_PAIRING_CODES)

        # Expiry, not restart, is what frees the slots.
        self.clock.advance(timedelta(minutes=11))
        self.assertTrue(service.issue_pairing_code(label="after-expiry").code)


class RedeemingPairingCodeTests(StoreCase):
    def test_a_valid_code_yields_a_token_bound_to_a_named_device(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="franz-iphone")

        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)

        self.assertIsNotNone(outcome.token)
        self.assertIsNotNone(outcome.device_id)
        self.assertIsNone(outcome.reason)
        self.assertIsNone(outcome.retry_after_seconds)
        devices = service.devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].device_id, outcome.device_id)
        # The operator names the device when issuing the code; the phone never
        # supplies a string that later shows up in an operator listing.
        self.assertEqual(devices[0].name, "franz-iphone")
        self.assertIsNone(devices[0].last_seen_at)
        self.assertIsNone(devices[0].revoked_at)

    def test_the_operator_formatting_of_the_code_is_accepted(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")

        outcome = service.redeem_pairing_code(
            issued.formatted.lower(), client_id=CLIENT
        )

        self.assertIsNotNone(outcome.token)

    def test_a_code_works_exactly_once(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")

        first = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        second = service.redeem_pairing_code(issued.code, client_id="198.51.100.5")

        self.assertIsNotNone(first.token)
        self.assertIsNone(second.token)
        self.assertIsNone(second.device_id)
        self.assertIsNotNone(second.reason)
        self.assertEqual(len(service.devices()), 1)
        self.assertEqual(
            service.recent_pairing_attempts("198.51.100.5")[0].outcome,
            AttemptOutcome.REUSED,
        )

    def test_a_code_stops_working_when_it_expires(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")

        self.clock.advance(timedelta(minutes=10, seconds=1))
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)

        self.assertIsNone(outcome.token)
        self.assertEqual(service.devices(), ())
        self.assertEqual(
            service.recent_pairing_attempts(CLIENT)[0].outcome, AttemptOutcome.EXPIRED
        )

    def test_a_code_still_works_on_the_last_second_before_expiry(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")

        self.clock.advance(timedelta(minutes=9, seconds=59))

        self.assertIsNotNone(
            service.redeem_pairing_code(issued.code, client_id=CLIENT).token
        )

    def test_a_code_outlives_a_change_of_hashing_cost(self) -> None:
        # Raising the cost factor must not silently invalidate the code an
        # operator is in the middle of reading out.
        issued = self.service().issue_pairing_code(label="iphone")

        stronger = self.service(scrypt=ScryptParameters(n=512, r=8, p=1))

        self.assertIsNotNone(
            stronger.redeem_pairing_code(issued.code, client_id=CLIENT).token
        )

    def test_the_work_one_guess_costs_is_bounded(self) -> None:
        # Every attempt hashes every candidate row, and scrypt is deliberately
        # slow, so an unbounded scan would let one guess cost as much CPU as
        # the operator has issued codes this hour.
        for _ in range(8):
            for index in range(5):
                self.service().issue_pairing_code(label=f"phone-{index}")
            self.clock.advance(timedelta(minutes=11))

        candidates = self.store().candidate_pairing_codes(
            now=self.clock(), retain_codes_for=timedelta(hours=1)
        )

        self.assertLessEqual(len(candidates), MAX_CANDIDATE_CODES)
        # The bound must never cost the operator the code they just read out.
        issued = self.service().issue_pairing_code(label="iphone")
        self.assertIsNotNone(
            self.service().redeem_pairing_code(issued.code, client_id=CLIENT).token
        )

    def test_a_wrong_code_yields_nothing_and_says_so(self) -> None:
        service = self.service()
        service.issue_pairing_code(label="iphone")

        outcome = service.redeem_pairing_code("22222222", client_id=CLIENT)

        self.assertIsNone(outcome.token)
        self.assertIsNone(outcome.device_id)
        self.assertIsNotNone(outcome.reason)
        self.assertEqual(service.devices(), ())

    def test_the_public_refusal_does_not_say_why_the_code_failed(self) -> None:
        # Telling a caller "already used" apart from "wrong" hands an attacker
        # a probe for which guesses were once real codes; the distinction stays
        # in the operator-visible audit rows instead.
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        service.redeem_pairing_code(issued.code, client_id=CLIENT)
        self.clock.advance(timedelta(minutes=1))
        expired = service.issue_pairing_code(label="iphone")
        self.clock.advance(timedelta(minutes=11))

        reasons = {
            service.redeem_pairing_code(issued.code, client_id="198.51.100.6").reason,
            service.redeem_pairing_code(expired.code, client_id="198.51.100.7").reason,
            service.redeem_pairing_code("22222222", client_id="198.51.100.8").reason,
            service.redeem_pairing_code("!!!", client_id="198.51.100.9").reason,
        }
        self.assertEqual(len(reasons), 1)
        self.assertNotIn(None, reasons)

    def test_non_ascii_input_is_refused_rather_than_crashing(self) -> None:
        service = self.service()
        service.issue_pairing_code(label="iphone")

        for code in ("配对码配对码配对", "ÄBCDEFGH", "\ud800ABCDEFG"):
            with self.subTest(code=code):
                outcome = service.redeem_pairing_code(code, client_id=CLIENT)
                self.assertIsNone(outcome.token)

    def test_an_oversized_client_identifier_is_refused(self) -> None:
        service = self.service()

        with self.assertRaises(DeviceAuthError):
            service.redeem_pairing_code("22222222", client_id="x" * 200)
        with self.assertRaises(DeviceAuthError):
            service.redeem_pairing_code("22222222", client_id="")


class RateLimitTests(StoreCase):
    def test_guessing_is_capped_per_client_and_per_minute(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")

        for index in range(5):
            with self.subTest(attempt=index):
                refused = service.redeem_pairing_code("22222222", client_id=CLIENT)
                self.assertIsNone(refused.token)
                self.assertIsNone(refused.retry_after_seconds)

        blocked = service.redeem_pairing_code(issued.code, client_id=CLIENT)

        self.assertIsNone(blocked.token)
        self.assertIsNotNone(blocked.retry_after_seconds)
        assert blocked.retry_after_seconds is not None
        self.assertTrue(0 < blocked.retry_after_seconds <= 60)
        self.assertEqual(service.devices(), ())

    def test_a_throttled_client_does_not_block_another_one(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        for _ in range(6):
            service.redeem_pairing_code("22222222", client_id=CLIENT)

        self.assertIsNotNone(
            service.redeem_pairing_code(issued.code, client_id="203.0.113.1").token
        )

    def test_the_window_slides_rather_than_locking_out_forever(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        for _ in range(6):
            service.redeem_pairing_code("22222222", client_id=CLIENT)

        self.clock.advance(timedelta(seconds=61))

        self.assertIsNotNone(
            service.redeem_pairing_code(issued.code, client_id=CLIENT).token
        )

    def test_a_blocked_attempt_does_not_extend_its_own_lockout(self) -> None:
        service = self.service()
        for _ in range(5):
            service.redeem_pairing_code("22222222", client_id=CLIENT)

        self.clock.advance(timedelta(seconds=30))
        for _ in range(20):
            self.assertIsNotNone(
                service.redeem_pairing_code(
                    "22222222", client_id=CLIENT
                ).retry_after_seconds
            )

        self.clock.advance(timedelta(seconds=31))
        issued = service.issue_pairing_code(label="iphone")
        self.assertIsNotNone(
            service.redeem_pairing_code(issued.code, client_id=CLIENT).token
        )

    def test_the_failure_count_survives_a_restart(self) -> None:
        for _ in range(5):
            self.service().redeem_pairing_code("22222222", client_id=CLIENT)

        restarted = self.service()
        issued = restarted.issue_pairing_code(label="iphone")

        self.assertIsNotNone(
            restarted.redeem_pairing_code(
                issued.code, client_id=CLIENT
            ).retry_after_seconds
        )

    def test_brute_force_never_reaches_the_hash_comparison(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        guesses = [
            "".join(("23456789ABCDEFGH"[(index >> shift) % 16]) for shift in range(8))
            for index in range(400)
        ]

        outcomes = [
            service.redeem_pairing_code(guess, client_id=CLIENT) for guess in guesses
        ]

        self.assertTrue(all(outcome.token is None for outcome in outcomes))
        evaluated = [
            outcome for outcome in outcomes if outcome.retry_after_seconds is None
        ]
        self.assertEqual(len(evaluated), 5)
        self.assertLessEqual(len(service.recent_pairing_attempts(CLIENT)), 5)
        self.assertIsNotNone(
            service.redeem_pairing_code(issued.code, client_id="203.0.113.2").token
        )


class ConcurrentPairingTests(StoreCase):
    def test_one_code_produces_exactly_one_device_under_concurrency(self) -> None:
        # One service instance across every thread, which is how it is used
        # behind a threading HTTP server: the store holds no connection of its
        # own, so each call opens and closes one.
        #
        # Every thread is held at the moment it has matched the code and is
        # about to claim it. Waiting for that overlap to happen by luck catches
        # a missing single-use guard only sometimes; forcing it means only the
        # store's own transaction can decide who wins.
        workers = 8
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcomes: list[PairingOutcome] = []
        lock = threading.Lock()
        start = threading.Barrier(workers)
        claiming = threading.Barrier(workers)
        claim = DeviceStore.consume_code_and_register_device

        def synchronized(store: DeviceStore, **fields: Any) -> bool:
            claiming.wait(timeout=30)
            return claim(store, **fields)

        def redeem(index: int) -> None:
            start.wait(timeout=30)
            outcome = service.redeem_pairing_code(
                issued.code, client_id=f"203.0.113.{index}"
            )
            with lock:
                outcomes.append(outcome)

        with mock.patch.object(
            DeviceStore, "consume_code_and_register_device", synchronized
        ):
            threads = [
                threading.Thread(target=redeem, args=(index,))
                for index in range(workers)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)

        self.assertEqual(len(outcomes), workers)
        winners = [outcome for outcome in outcomes if outcome.token is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(service.devices()), 1)
        self.assertTrue(
            all(outcome.retry_after_seconds is None for outcome in outcomes)
        )

    def test_concurrent_issuing_never_exceeds_the_live_code_cap(self) -> None:
        # The count and the insert have to be one transaction. Enough writers
        # start at once that a deferred transaction, which lets two of them read
        # the same count, shows up as a refusal nobody asked for.
        writers = 24
        service = self.service()
        issued: list[str] = []
        refused: list[DeviceAuthError] = []
        lock = threading.Lock()
        start = threading.Barrier(writers)

        def issue(index: int) -> None:
            start.wait(timeout=30)
            try:
                code = service.issue_pairing_code(label=f"phone-{index}")
            except DeviceAuthError as error:
                with lock:
                    refused.append(error)
            else:
                with lock:
                    issued.append(code.code)

        threads = [
            threading.Thread(target=issue, args=(index,)) for index in range(writers)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(len(issued) + len(refused), writers)
        self.assertEqual(len(set(issued)), len(issued))
        self.assertLessEqual(len(issued), 5)
        self.assertEqual(
            {error.code for error in refused}, {ErrorCode.TOO_MANY_PAIRING_CODES}
        )


if __name__ == "__main__":
    unittest.main()
