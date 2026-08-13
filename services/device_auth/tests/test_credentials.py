from __future__ import annotations

import unittest

from us_stock_helper_device_auth.credentials import (
    CODE_ALPHABET,
    DEFAULT_CODE_LENGTH,
    DEFAULT_SCRYPT,
    MAX_CODE_LENGTH,
    MIN_CODE_LENGTH,
    TOKEN_ALGORITHM,
    TOKEN_SECRET_BYTES,
    ScryptParameters,
    code_hash,
    format_code,
    format_token,
    generate_code,
    new_device_id,
    new_token_secret,
    normalize_code,
    split_token,
    token_hash,
)
from us_stock_helper_device_auth.errors import DeviceAuthError


class PairingCodeTests(unittest.TestCase):
    def test_the_alphabet_drops_characters_people_misread(self) -> None:
        for character in "01ILO":
            self.assertNotIn(character, CODE_ALPHABET)
        self.assertEqual(len(CODE_ALPHABET), len(set(CODE_ALPHABET)))

    def test_generated_codes_are_human_length_and_in_the_alphabet(self) -> None:
        self.assertEqual(DEFAULT_CODE_LENGTH, 8)
        self.assertEqual((MIN_CODE_LENGTH, MAX_CODE_LENGTH), (6, 8))
        for length in range(MIN_CODE_LENGTH, MAX_CODE_LENGTH + 1):
            code = generate_code(length)
            self.assertEqual(len(code), length)
            self.assertTrue(set(code).issubset(set(CODE_ALPHABET)))

    def test_generated_codes_do_not_repeat(self) -> None:
        self.assertEqual(len({generate_code() for _ in range(200)}), 200)

    def test_a_code_length_outside_the_readable_range_is_refused(self) -> None:
        for length in (0, 5, 9, 64):
            with self.subTest(length=length):
                with self.assertRaises(DeviceAuthError):
                    generate_code(length)

    def test_operator_formatting_survives_a_round_trip(self) -> None:
        code = generate_code(8)

        self.assertEqual(normalize_code(format_code(code)), code)
        self.assertEqual(normalize_code(f"  {code.lower()}\n"), code)
        self.assertEqual(normalize_code(code[:4] + " " + code[4:]), code)

    def test_input_outside_the_alphabet_is_refused_rather_than_hashed(self) -> None:
        for raw in ("", "SHORT", "ABCDEFGHI", "AAAA0AAA", "AAAAIAAA", "!!!!!!!!"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_code(raw))

    def test_non_ascii_input_is_refused_without_raising(self) -> None:
        # hmac.compare_digest and str.encode("ascii") both raise on non-ASCII
        # text; an unhandled raise on the pairing path would be a crash before
        # authentication rather than a refusal.
        for raw in ("配对码配对码配对", "ÄBCDEFGH", "\ud800ABCDEFG"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_code(raw))

    def test_a_lookalike_that_upper_cases_into_the_alphabet_is_still_refused(
        self,
    ) -> None:
        # Rejecting non-ASCII has to happen before the case fold, not after it:
        # "ſ".upper() is the ASCII "S" and "ﬀ".upper() is "FF", so a fold-first
        # parser would accept characters the operator's terminal never printed.
        self.assertEqual("ſ".upper(), "S")
        self.assertEqual("ﬀ".upper(), "FF")

        self.assertIsNone(normalize_code("ſTUVWXY2"))
        self.assertIsNone(normalize_code("ﬀTUVWXY"))


class ScryptParameterTests(unittest.TestCase):
    def test_the_shipped_cost_factor_is_not_a_toy(self) -> None:
        # A pairing code carries about 40 bits, so an attacker who steals the
        # database is only held back by the cost factor.
        self.assertGreaterEqual(DEFAULT_SCRYPT.n, 2**14)
        self.assertGreaterEqual(DEFAULT_SCRYPT.length, 32)

    def test_parameters_survive_the_round_trip_through_storage(self) -> None:
        parsed = ScryptParameters.parse(DEFAULT_SCRYPT.serialize())

        self.assertEqual(parsed, DEFAULT_SCRYPT)

    def test_an_unreadable_parameter_string_fails_closed(self) -> None:
        for serialized in ("", "argon2$n=1", "scrypt$n=abc,r=8,p=1,len=32", "scrypt"):
            with self.subTest(serialized=serialized):
                with self.assertRaises(DeviceAuthError):
                    ScryptParameters.parse(serialized)

    def test_a_stored_hash_verifies_against_its_own_recorded_parameters(self) -> None:
        weak = ScryptParameters(n=256, r=8, p=1)
        salt = b"\x01" * 16
        digest = code_hash("ABCDEFGH", salt, weak)

        self.assertEqual(
            code_hash("ABCDEFGH", salt, ScryptParameters.parse(weak.serialize())),
            digest,
        )
        self.assertNotEqual(code_hash("ABCDEFGH", salt, DEFAULT_SCRYPT), digest)
        self.assertNotEqual(code_hash("ABCDEFGJ", salt, weak), digest)
        self.assertNotEqual(code_hash("ABCDEFGH", b"\x02" * 16, weak), digest)


class DeviceTokenTests(unittest.TestCase):
    def test_a_token_secret_carries_at_least_thirty_two_random_bytes(self) -> None:
        self.assertGreaterEqual(TOKEN_SECRET_BYTES, 32)
        self.assertEqual(len({new_token_secret() for _ in range(200)}), 200)

    def test_a_device_id_is_safe_to_type_as_a_command_line_argument(self) -> None:
        # A device id that begins with "-" is read as an option by argparse, so
        # the one device an operator most wants to revoke becomes unrevokable
        # from the terminal.
        identifiers = {new_device_id() for _ in range(500)}

        self.assertEqual(len(identifiers), 500)
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                self.assertTrue(identifier.isalnum())
                self.assertGreaterEqual(len(identifier), 16)

    def test_a_token_splits_back_into_its_device_id_and_secret(self) -> None:
        device_id = new_device_id()
        secret = new_token_secret()

        self.assertEqual(
            split_token(format_token(device_id, secret)), (device_id, secret)
        )

    def test_a_malformed_token_is_refused_rather_than_parsed(self) -> None:
        for token in (
            "",
            ".",
            "nodot",
            ".secret",
            "device.",
            "a.b.c",
            "de vice.secret",
            "device.sec ret",
            "device.sec\x7fret",
            "device.sec\x00ret",
        ):
            with self.subTest(token=token):
                self.assertIsNone(split_token(token))

    def test_non_ascii_tokens_are_refused_without_raising(self) -> None:
        for token in ("dëvice.secret", "device.sëcret", "令牌.令牌", "d\ud800.s"):
            with self.subTest(token=token):
                self.assertIsNone(split_token(token))

    def test_a_token_padded_with_unicode_whitespace_is_refused(self) -> None:
        # str.strip removes U+00A0 and U+2028 as readily as a space, so a
        # trim-first parser would accept a token in a form nobody issued.
        self.assertTrue("\u00a0".isspace() and "\u2028".isspace())

        self.assertIsNone(split_token("\u00a0device.secret"))
        self.assertIsNone(split_token("device.secret\u2028"))

    def test_the_keyed_token_hash_depends_on_both_salt_and_secret(self) -> None:
        digest = token_hash(b"\x01" * 32, "secret", TOKEN_ALGORITHM)

        self.assertEqual(len(digest), 32)
        self.assertEqual(token_hash(b"\x01" * 32, "secret", TOKEN_ALGORITHM), digest)
        self.assertNotEqual(token_hash(b"\x02" * 32, "secret", TOKEN_ALGORITHM), digest)
        self.assertNotEqual(token_hash(b"\x01" * 32, "secrez", TOKEN_ALGORITHM), digest)

    def test_an_unknown_token_algorithm_fails_closed(self) -> None:
        with self.assertRaises(DeviceAuthError):
            token_hash(b"\x01" * 32, "secret", "rot13")


if __name__ == "__main__":
    unittest.main()
