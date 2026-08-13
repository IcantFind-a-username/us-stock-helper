from __future__ import annotations

import os
import sqlite3
import unittest
from datetime import timedelta
from pathlib import Path

from us_stock_helper_device_auth.credentials import split_token
from us_stock_helper_device_auth.errors import DeviceAuthError
from us_stock_helper_device_auth.service import DeviceAuthService, RevocationResult

from support import StoreCase

CLIENT = "198.51.100.4"


class TokenVerificationTests(StoreCase):
    def paired(self) -> tuple[DeviceAuthService, str, str]:
        service = self.service()
        issued = service.issue_pairing_code(label="franz-iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None and outcome.device_id is not None
        return service, outcome.token, outcome.device_id

    def test_a_freshly_issued_token_identifies_its_device(self) -> None:
        service, token, device_id = self.paired()

        verified = service.verify_token(token)

        self.assertEqual(verified.device_id, device_id)
        self.assertIsNone(verified.reason)
        self.assertTrue(verified.authorized)

    def test_verification_records_when_the_device_was_last_seen(self) -> None:
        service, token, _ = self.paired()
        self.clock.advance(timedelta(hours=3))

        service.verify_token(token)

        self.assertEqual(service.devices()[0].last_seen_at, self.clock())

    def test_a_token_survives_a_restart(self) -> None:
        _, token, device_id = self.paired()

        self.assertEqual(self.service().verify_token(token).device_id, device_id)

    def test_a_tampered_token_is_refused(self) -> None:
        service, token, device_id = self.paired()
        parsed = split_token(token)
        assert parsed is not None
        _, secret = parsed

        rejected = [
            token[:-1] + ("A" if token[-1] != "A" else "B"),
            f"{device_id}.{secret[:-1]}",
            f"{device_id}.",
            f".{secret}",
            f"unknown-device.{secret}",
            secret,
            "",
            "   ",
        ]
        for candidate in rejected:
            with self.subTest(candidate=candidate[:12]):
                verified = service.verify_token(candidate)
                self.assertIsNone(verified.device_id)
                self.assertFalse(verified.authorized)
                self.assertIsNotNone(verified.reason)

    def test_a_token_from_one_device_never_authenticates_another(self) -> None:
        service, first_token, first_id = self.paired()
        second = service.issue_pairing_code(label="ipad")
        second_outcome = service.redeem_pairing_code(second.code, client_id=CLIENT)
        assert second_outcome.token is not None
        second_parsed = split_token(second_outcome.token)
        assert second_parsed is not None
        second_id, _ = second_parsed
        first_parsed = split_token(first_token)
        assert first_parsed is not None
        _, first_secret = first_parsed

        crossed = service.verify_token(f"{second_id}.{first_secret}")

        self.assertIsNone(crossed.device_id)
        self.assertNotEqual(first_id, second_id)

    def test_non_ascii_tokens_are_refused_rather_than_crashing(self) -> None:
        service, _, device_id = self.paired()

        # hmac.compare_digest raises TypeError on non-ASCII str input, which
        # would take down the handler thread before authentication resolves.
        candidates = ("令牌.令牌", f"{device_id}.sëcret", "d\ud800.s", "Ünicöde")
        for candidate in candidates:
            with self.subTest(candidate=candidate[:8]):
                verified = service.verify_token(candidate)
                self.assertIsNone(verified.device_id)
                self.assertIsNotNone(verified.reason)


class RevocationTests(StoreCase):
    def test_a_revoked_token_stops_working_immediately(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None and outcome.device_id is not None
        self.assertTrue(service.verify_token(outcome.token).authorized)

        result = service.revoke_device(outcome.device_id, reason="phone lost")

        self.assertEqual(result, RevocationResult.REVOKED)
        after = service.verify_token(outcome.token)
        self.assertIsNone(after.device_id)
        self.assertFalse(after.authorized)
        self.assertIsNotNone(after.reason)

    def test_revocation_outlives_a_restart(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None and outcome.device_id is not None
        service.revoke_device(outcome.device_id, reason="phone lost")

        self.assertFalse(self.service().verify_token(outcome.token).authorized)

    def test_revocation_is_recorded_for_the_operator(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.device_id is not None
        self.clock.advance(timedelta(days=2))

        service.revoke_device(outcome.device_id, reason="phone lost")

        device = service.devices()[0]
        self.assertEqual(device.revoked_at, self.clock())
        self.assertEqual(device.revoked_reason, "phone lost")

    def test_revoking_twice_or_revoking_a_stranger_is_stated_not_guessed(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.device_id is not None

        self.assertEqual(
            service.revoke_device(outcome.device_id, reason="lost"),
            RevocationResult.REVOKED,
        )
        self.assertEqual(
            service.revoke_device(outcome.device_id, reason="lost again"),
            RevocationResult.ALREADY_REVOKED,
        )
        self.assertEqual(
            service.revoke_device("no-such-device", reason="lost"),
            RevocationResult.UNKNOWN_DEVICE,
        )

    def test_revoking_one_device_leaves_the_others_working(self) -> None:
        service = self.service()
        tokens = []
        for name in ("iphone", "ipad"):
            issued = service.issue_pairing_code(label=name)
            outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
            assert outcome.token is not None and outcome.device_id is not None
            tokens.append((outcome.device_id, outcome.token))

        service.revoke_device(tokens[0][0], reason="lost")

        self.assertFalse(service.verify_token(tokens[0][1]).authorized)
        self.assertTrue(service.verify_token(tokens[1][1]).authorized)


class StoredSecretTests(StoreCase):
    def test_nothing_recoverable_is_written_to_the_database(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="franz-iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None
        parsed = split_token(outcome.token)
        assert parsed is not None
        _, secret = parsed

        blob = self.stored_bytes()

        for plaintext in (issued.code, issued.formatted, outcome.token, secret):
            for variant in (plaintext, plaintext.lower(), plaintext.upper()):
                with self.subTest(variant=variant[:12]):
                    self.assertNotIn(variant.encode("ascii"), blob)
        # The operator-chosen label is not a secret and must stay legible.
        self.assertIn(b"franz-iphone", blob)

    def test_the_stored_device_row_cannot_be_replayed_as_a_token(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.device_id is not None

        with sqlite3.connect(self.database) as connection:
            salt, token_hash = connection.execute(
                "SELECT salt, token_hash FROM devices WHERE device_id = ?",
                (outcome.device_id,),
            ).fetchone()

        for stolen in (salt, token_hash):
            candidate = f"{outcome.device_id}.{stolen.hex()}"
            with self.subTest(candidate=candidate[:16]):
                self.assertFalse(service.verify_token(candidate).authorized)


class CorruptStorageTests(StoreCase):
    def test_a_corrupt_database_refuses_rather_than_admitting_anyone(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.database) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        self.database.write_bytes(b"not a database" * 512)
        os.chmod(self.database, 0o600)

        with self.assertRaises(DeviceAuthError):
            service.verify_token(outcome.token)

    def test_a_truncated_database_refuses_rather_than_admitting_anyone(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TABLE devices")

        with self.assertRaises(DeviceAuthError):
            service.verify_token(outcome.token)

    def test_an_unreadable_hash_algorithm_refuses_rather_than_guessing(self) -> None:
        service = self.service()
        issued = service.issue_pairing_code(label="iphone")
        outcome = service.redeem_pairing_code(issued.code, client_id=CLIENT)
        assert outcome.token is not None
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE devices SET algorithm = 'rot13'")

        with self.assertRaises(DeviceAuthError):
            service.verify_token(outcome.token)


if __name__ == "__main__":
    unittest.main()
