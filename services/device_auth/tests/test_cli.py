from __future__ import annotations

import contextlib
import io
import unittest
from datetime import timedelta

from us_stock_helper_device_auth.__main__ import main
from us_stock_helper_device_auth.service import DeviceAuthService
from us_stock_helper_device_auth.time_utils import from_storage, utc_now

from support import StoreCase

CLIENT = "198.51.100.4"


class CommandLineTests(StoreCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        status = main(
            [*arguments, "--database", str(self.database)], stdout=out, stderr=err
        )
        return status, out.getvalue(), err.getvalue()

    def full_service(self) -> DeviceAuthService:
        # The command line hashes with the shipped scrypt parameters, so a test
        # that redeems its output has to pay the same cost.
        return DeviceAuthService(store=self.store(), clock=self.clock)

    def field(self, out: str, name: str) -> str:
        for line in out.splitlines():
            if line.startswith(f"{name}:"):
                return line.split(":", 1)[1].strip()
        raise AssertionError(f"no {name} in output: {out!r}")

    def printed_code(self, out: str) -> str:
        return self.field(out, "pairing-code")

    def paired(self, label: str = "franz-iphone") -> tuple[DeviceAuthService, str, str]:
        _, out, _ = self.run_cli("pair", "--label", label)
        service = self.full_service()
        outcome = service.redeem_pairing_code(self.printed_code(out), client_id=CLIENT)
        assert outcome.token is not None and outcome.device_id is not None
        return service, outcome.token, outcome.device_id

    def test_pairing_prints_a_code_the_phone_can_actually_use(self) -> None:
        status, out, err = self.run_cli("pair", "--label", "franz-iphone")

        self.assertEqual(status, 0)
        self.assertEqual(err, "")
        outcome = self.full_service().redeem_pairing_code(
            self.printed_code(out), client_id=CLIENT
        )
        self.assertIsNotNone(outcome.token)

    def test_the_printed_code_carries_its_label_and_deadline(self) -> None:
        # The command line runs on the wall clock on purpose, so the deadline is
        # bracketed rather than compared to a fixed instant.
        before = utc_now()

        status, out, _ = self.run_cli(
            "pair", "--label", "franz-iphone", "--ttl-minutes", "3"
        )

        self.assertEqual(status, 0)
        self.assertIn("label: franz-iphone", out)
        expires = from_storage(self.field(out, "expires-utc"))
        self.assertGreaterEqual(expires, before + timedelta(minutes=3))
        self.assertLessEqual(expires, utc_now() + timedelta(minutes=3))

    def test_an_unusable_label_is_reported_rather_than_stored(self) -> None:
        status, out, err = self.run_cli("pair", "--label", "iphone\x1b[2J")

        self.assertNotEqual(status, 0)
        self.assertEqual(out, "")
        self.assertNotEqual(err, "")
        self.assertEqual(self.service().devices(), ())

    def test_listing_devices_never_prints_a_token(self) -> None:
        _, token, device_id = self.paired()

        status, listing, _ = self.run_cli("devices")

        self.assertEqual(status, 0)
        self.assertIn(device_id, listing)
        self.assertIn("franz-iphone", listing)
        self.assertNotIn(token, listing)
        self.assertNotIn(token.split(".", 1)[1], listing)

    def test_listing_an_empty_database_says_so_rather_than_printing_nothing(
        self,
    ) -> None:
        status, listing, _ = self.run_cli("devices")

        self.assertEqual(status, 0)
        self.assertNotEqual(listing.strip(), "")

    def test_revoking_from_the_command_line_kills_the_token(self) -> None:
        service, token, device_id = self.paired()

        status, out, _ = self.run_cli("revoke", device_id, "--reason", "phone lost")

        self.assertEqual(status, 0)
        self.assertIn(device_id, out)
        self.assertFalse(service.verify_token(token).authorized)

    def test_revoking_an_unknown_device_is_an_error_not_a_shrug(self) -> None:
        status, out, err = self.run_cli("revoke", "no-such-device", "--reason", "lost")

        self.assertNotEqual(status, 0)
        self.assertNotEqual(err, "")
        self.assertEqual(out, "")

    def test_revoking_twice_reports_that_it_changed_nothing(self) -> None:
        _, _, device_id = self.paired()
        self.run_cli("revoke", device_id, "--reason", "lost")

        status, _, err = self.run_cli("revoke", device_id, "--reason", "lost again")

        self.assertNotEqual(status, 0)
        self.assertNotEqual(err, "")

    def test_recent_pairing_attempts_are_visible_to_the_operator(self) -> None:
        self.service().redeem_pairing_code("22222222", client_id=CLIENT)

        status, listing, _ = self.run_cli("attempts", "--client", CLIENT)

        self.assertEqual(status, 0)
        self.assertIn(CLIENT, listing)
        self.assertIn("unknown", listing)

    def test_a_corrupt_database_is_reported_instead_of_crashing_the_terminal(
        self,
    ) -> None:
        self.store()
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = self.database.with_name(self.database.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        self.database.write_bytes(b"not a database" * 512)

        status, out, err = self.run_cli("devices")

        self.assertNotEqual(status, 0)
        self.assertEqual(out, "")
        self.assertNotEqual(err, "")

    def test_an_unknown_command_fails_closed(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            self.run_cli("issue-something")

        self.assertNotEqual(caught.exception.code, 0)

    def test_the_command_line_offers_no_way_to_reach_a_broker(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(["--help"])

        helptext = out.getvalue().lower()
        self.assertNotEqual(helptext, "")
        for word in ("order", "trade", "broker", "account", "buy", "sell", "portfolio"):
            with self.subTest(word=word):
                self.assertNotIn(word, helptext)


if __name__ == "__main__":
    unittest.main()
