"""The one write this service accepts, and the credential it hands back.

Everything here is about a single path. It is the only route on the whole
surface that changes state, the only one that answers without a credential, and
therefore the only one an anonymous caller can reach at all — so the tests are
written from the outside, over a real socket, in the shapes an attacker would
actually send: a replayed code, an expired one, a rotated forwarded-for header,
a body that is not a pairing attempt at all.

Two properties are asserted repeatedly and on purpose. A refusal must look the
same whichever way the code was wrong, and the attempt counter must be the one
in the database rather than one in memory, because a limiter a restart clears
is a limiter an attacker restarts.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError

from us_stock_helper_device_auth import (
    DeviceAuthError,
    DeviceAuthService,
    DeviceStore,
    ErrorCode,
    ScryptParameters,
    format_code,
)

from us_stock_helper_analysis_api.device_gate import MAX_PAIRING_BODY_BYTES, DeviceGate
from us_stock_helper_analysis_api.http_app import (
    PAIRING_PATH,
    AnalysisServerConfig,
    build_server,
)

from test_analysis_service import Provider, service


# The shipped cost factor is tens of milliseconds per candidate code, which the
# rate-limit tests would pay five times over per request. device_auth pins the
# real default in its own suite; nothing here is asserting the cost.
FAST_SCRYPT = ScryptParameters(n=256, r=8, p=1)

START = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)

# Eight characters from the code alphabet that no test ever issues.
WRONG_CODE = "ZZZZZZZZ"

# device_auth allows five attempts per client per minute.
ATTEMPT_LIMIT = 5


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def call(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: bytes | None = None,
    forwarded_for: str | None = None,
) -> tuple[int, dict[str, str], Any]:
    request = urllib.request.Request(url, method=method, data=body)
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    if forwarded_for is not None:
        request.add_header("X-Forwarded-For", forwarded_for)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return (
                response.status,
                dict(response.headers.items()),
                json.loads(response.read()),
            )
    except HTTPError as error:
        return error.code, dict(error.headers.items()), json.loads(error.read())


class PairingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="analysis-api-pairing-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.database = self.directory / "device-auth.sqlite3"
        self.clock = Clock()

    # Every helper opens its own service on the same file: that is how the
    # operator's command line and the HTTP boundary meet in the deployment, and
    # a test that shared one object in memory would not notice if they stopped.
    def auth(self) -> DeviceAuthService:
        return DeviceAuthService(
            store=DeviceStore(self.database), clock=self.clock, scrypt=FAST_SCRYPT
        )

    def gate(self) -> DeviceGate:
        return DeviceGate(self.auth())

    def issue(self, label: str = "operator iPhone") -> str:
        return self.auth().issue_pairing_code(label=label).code

    def config(self, **overrides: Any) -> AnalysisServerConfig:
        defaults: dict[str, Any] = {
            "host": "127.0.0.1",
            "port": 0,
            "allow_lan": False,
            "trust_proxy": False,
            "device_database": str(self.database),
            "allowed_client_networks": ("127.0.0.0/8", "::1/128"),
        }
        return AnalysisServerConfig(**{**defaults, **overrides})

    @contextmanager
    def running(
        self, config: AnalysisServerConfig | None = None, gate: DeviceGate | None = None
    ) -> Iterator[str]:
        resolved = self.config() if config is None else config
        if gate is None and resolved.device_database is not None:
            gate = self.gate()
        server = build_server(service(Provider()), resolved, gate=gate)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://{server.server_address[0]}:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def redeem(
        self,
        base: str,
        code: object,
        *,
        forwarded_for: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        payload: dict[str, Any] = dict(extra or {})
        if code is not None:
            payload["pairingCode"] = code
        return call(
            f"{base}{PAIRING_PATH}",
            method="POST",
            body=json.dumps(payload).encode("utf-8"),
            forwarded_for=forwarded_for,
        )


class PairingExchangeTests(PairingCase):
    def test_a_pairing_code_is_exchanged_for_a_working_device_token(self) -> None:
        code = self.issue()

        with self.running() as base:
            status, headers, body = self.redeem(base, code)

            self.assertEqual(status, 200)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertTrue(body["deviceId"])
            # The app refuses anything shorter as malformed, so the boundary
            # has to hand back the whole token device_auth minted.
            self.assertGreaterEqual(len(body["deviceToken"]), 32)
            self.assertTrue(body["deviceToken"].startswith(f"{body['deviceId']}."))
            # Null is a fact, not a gap: device tokens are revoked, not expired.
            self.assertIsNone(body["expiresAt"])

            self.assertEqual(call(f"{base}/health", token=body["deviceToken"])[0], 200)

    def test_the_code_is_accepted_in_the_shape_the_operator_reads_aloud(self) -> None:
        code = self.issue()

        with self.running() as base:
            status, _, body = self.redeem(base, format_code(code).lower())

        self.assertEqual(status, 200)
        self.assertTrue(body["deviceToken"])

    def test_the_caller_cannot_name_the_device_it_is_pairing(self) -> None:
        """The operator labels the phone when issuing the code; the phone does not.

        A caller-chosen string would land in the operator's `devices` listing,
        which is read on a terminal — a name the attacker writes and the
        operator reads.
        """
        code = self.issue(label="operator iPhone")

        with self.running() as base:
            status, _, _ = self.redeem(
                base, code, extra={"deviceName": "[2Jowned"}
            )

        self.assertEqual(status, 200)
        self.assertEqual(
            [record.name for record in self.auth().devices()], ["operator iPhone"]
        )

    def test_pairing_needs_no_credential_but_everything_else_does(self) -> None:
        code = self.issue()

        with self.running() as base:
            status, _, body = self.redeem(base, code)
            self.assertEqual(status, 200)
            token = body["deviceToken"]

            for path in ("/health", "/decision?symbol=NVDA&horizon=short"):
                with self.subTest(path=path):
                    self.assertEqual(call(f"{base}{path}")[0], 401)
                    self.assertEqual(call(f"{base}{path}", token="0" * 64)[0], 401)
                    self.assertEqual(call(f"{base}{path}", token=token)[0], 200)

    def test_a_refused_token_is_never_echoed_back(self) -> None:
        with self.running() as base:
            status, _, body = call(f"{base}/health", token="0" * 64)

        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "AUTH_REQUIRED")
        self.assertNotIn("0" * 64, repr(body))


class PairingRefusalTests(PairingCase):
    """Every wrong code is refused with the same words.

    Separating "already used" from "expired" from "never existed" would let
    someone guessing learn which of their guesses had once been real codes. The
    operator gets that distinction from the audit rows on the host instead.
    """

    def test_a_redeemed_code_cannot_be_redeemed_again(self) -> None:
        code = self.issue()

        with self.running() as base:
            self.assertEqual(self.redeem(base, code)[0], 200)
            replayed = self.redeem(base, code)
            unknown = self.redeem(base, WRONG_CODE)

        self.assertEqual(replayed[0], 400)
        self.assertEqual((replayed[0], replayed[2]), (unknown[0], unknown[2]))

    def test_an_expired_code_is_refused_without_saying_it_expired(self) -> None:
        code = self.issue()
        self.clock.advance(timedelta(minutes=11))

        with self.running() as base:
            expired = self.redeem(base, code)
            unknown = self.redeem(base, WRONG_CODE)

        self.assertEqual(expired[0], 400)
        self.assertEqual((expired[0], expired[2]), (unknown[0], unknown[2]))

    def test_a_code_of_the_wrong_shape_is_refused_like_any_other(self) -> None:
        with self.running() as base:
            unknown = self.redeem(base, WRONG_CODE)
            for shape in ("", "short", 12345678, "中文代码"):
                with self.subTest(shape=shape):
                    refused = self.redeem(base, shape)

                    self.assertEqual(
                        (refused[0], refused[2]), (unknown[0], unknown[2])
                    )

    def test_a_refused_pairing_hands_back_nothing_that_could_be_a_credential(
        self,
    ) -> None:
        with self.running() as base:
            status, _, body = self.redeem(base, WRONG_CODE)

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "INVALID_PAIRING_CODE")
        self.assertNotIn("deviceToken", body)
        self.assertNotIn("deviceId", body)


class PairingBodyTests(PairingCase):
    def test_a_body_that_is_not_a_pairing_attempt_spends_no_attempt(self) -> None:
        """Malformed input must not be able to lock the operator out.

        A JSON object counts as an attempt even when it carries no code,
        because that is indistinguishable from a wrong guess. Something that is
        not an object at all cannot be a guess, so it costs nothing — otherwise
        a few bytes of garbage would deny the operator their own pairing window.
        """
        code = self.issue()

        with self.running() as base:
            for raw in (b"", b"not json at all", b"[]", b'"pairing"', b"null", b"7"):
                with self.subTest(raw=raw):
                    status, _, body = call(
                        f"{base}{PAIRING_PATH}", method="POST", body=raw
                    )

                    self.assertEqual(status, 400)
                    self.assertEqual(body["error"]["code"], "INVALID_ARGUMENT")

            self.assertEqual(self.redeem(base, code)[0], 200)

    def test_an_object_without_a_code_is_an_attempt_like_any_other(self) -> None:
        with self.running() as base:
            missing = self.redeem(base, None)
            unknown = self.redeem(base, WRONG_CODE)

        self.assertEqual(missing[0], 400)
        self.assertEqual(missing[2], unknown[2])

    def test_a_body_larger_than_the_boundary_reads_is_refused_unread(self) -> None:
        oversized = json.dumps(
            {"pairingCode": "A" * (MAX_PAIRING_BODY_BYTES * 2)}
        ).encode("utf-8")
        self.assertGreater(len(oversized), MAX_PAIRING_BODY_BYTES)
        code = self.issue()

        with self.running() as base:
            status, _, body = call(
                f"{base}{PAIRING_PATH}", method="POST", body=oversized
            )
            self.assertEqual(status, 413)
            self.assertEqual(body["error"]["code"], "PAYLOAD_TOO_LARGE")

            # And it did not cost the operator their attempt budget either.
            self.assertEqual(self.redeem(base, code)[0], 200)


class PairingRateLimitTests(PairingCase):
    def exhaust(self, base: str, *, forwarded_for: str | None = None) -> None:
        for attempt in range(ATTEMPT_LIMIT):
            status, _, _ = self.redeem(base, WRONG_CODE, forwarded_for=forwarded_for)
            self.assertEqual(status, 400, f"attempt {attempt} was not refused")

    def test_guessing_is_throttled_at_the_boundary_with_a_retry_hint(self) -> None:
        with self.running() as base:
            self.exhaust(base)
            status, headers, body = self.redeem(base, WRONG_CODE)

        self.assertEqual(status, 429)
        self.assertEqual(body["error"]["code"], "RATE_LIMITED")
        self.assertGreaterEqual(int(headers["Retry-After"]), 1)

    def test_the_limit_holds_even_for_the_correct_code(self) -> None:
        """The counter is consulted before the code is, or it is not a limit.

        A limiter that only counted wrong guesses would let an attacker who
        finally hit the right code through on the attempt after the lockout.
        """
        code = self.issue()

        with self.running() as base:
            self.exhaust(base)
            status, _, _ = self.redeem(base, code)

        self.assertEqual(status, 429)

    def test_the_attempt_count_survives_a_restart_of_the_service(self) -> None:
        with self.running() as base:
            self.exhaust(base)

        # A new server, a new gate, a new sqlite connection — the same file.
        with self.running() as restarted:
            status, _, body = self.redeem(restarted, WRONG_CODE)

        self.assertEqual(status, 429)
        self.assertEqual(body["error"]["code"], "RATE_LIMITED")

    def test_the_window_releases_the_operator_once_it_passes(self) -> None:
        code = self.issue()

        with self.running() as base:
            self.exhaust(base)
            self.assertEqual(self.redeem(base, WRONG_CODE)[0], 429)
            self.clock.advance(timedelta(minutes=2))
            status, _, _ = self.redeem(base, code)

        self.assertEqual(status, 200)

    def test_each_phone_behind_the_proxy_has_its_own_budget(self) -> None:
        code = self.issue()

        with self.running(self.config(trust_proxy=True)) as base:
            self.exhaust(base, forwarded_for="203.0.113.7")
            self.assertEqual(
                self.redeem(base, WRONG_CODE, forwarded_for="203.0.113.7")[0], 429
            )
            status, _, _ = self.redeem(base, code, forwarded_for="198.51.100.9")

        self.assertEqual(status, 200)

    def test_a_forwarded_address_buys_nothing_where_no_proxy_is_declared(self) -> None:
        """Without a proxy the header is a client-supplied string.

        Honouring it there would hand every attacker an unlimited supply of
        identities, which is the same as having no limiter at all.
        """
        with self.running(self.config(trust_proxy=False)) as base:
            for index in range(ATTEMPT_LIMIT):
                status, _, _ = self.redeem(
                    base, WRONG_CODE, forwarded_for=f"203.0.113.{index}"
                )
                self.assertEqual(status, 400)
            status, _, _ = self.redeem(base, WRONG_CODE, forwarded_for="203.0.113.99")

        self.assertEqual(status, 429)

    def test_only_the_address_this_hosts_proxy_appended_is_believed(self) -> None:
        """Caddy appends to whatever the caller sent, so the last entry is ours.

        A caller who prefixes their own addresses is writing history, not
        identity: reading the first entry would let them rotate through as many
        buckets as they can type.
        """
        with self.running(self.config(trust_proxy=True)) as base:
            self.exhaust(base, forwarded_for="203.0.113.7")
            status, _, _ = self.redeem(
                base, WRONG_CODE, forwarded_for="9.9.9.9, 198.51.100.4, 203.0.113.7"
            )

        self.assertEqual(status, 429)

    def test_a_forwarded_header_that_is_not_an_address_falls_back_to_the_peer(
        self,
    ) -> None:
        with self.running(self.config(trust_proxy=True)) as base:
            self.exhaust(base, forwarded_for="not-an-address")
            status, _, _ = self.redeem(base, WRONG_CODE, forwarded_for="unknown")

        self.assertEqual(status, 429)


class RevocationTests(PairingCase):
    def test_a_revoked_device_is_refused_on_its_very_next_request(self) -> None:
        code = self.issue()

        with self.running() as base:
            status, _, body = self.redeem(base, code)
            self.assertEqual(status, 200)
            token, device_id = body["deviceToken"], body["deviceId"]
            self.assertEqual(call(f"{base}/health", token=token)[0], 200)

            # The operator revokes from the command line, in another process,
            # against the same file. Nothing restarts.
            self.auth().revoke_device(device_id, reason="phone lost")

            status, _, body = call(f"{base}/health", token=token)

        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["code"], "AUTH_REQUIRED")

    def test_revoking_one_phone_leaves_the_other_working(self) -> None:
        first, second = self.issue(label="phone one"), self.issue(label="phone two")

        with self.running() as base:
            one = self.redeem(base, first)[2]
            two = self.redeem(base, second)[2]
            self.auth().revoke_device(one["deviceId"], reason="phone lost")

            self.assertEqual(call(f"{base}/health", token=one["deviceToken"])[0], 401)
            self.assertEqual(call(f"{base}/health", token=two["deviceToken"])[0], 200)


class NarrownessTests(PairingCase):
    def test_the_pairing_path_answers_no_method_but_post(self) -> None:
        with self.running() as base:
            for method in ("GET", "PUT", "PATCH", "DELETE", "OPTIONS"):
                with self.subTest(method=method):
                    status, headers, body = call(f"{base}{PAIRING_PATH}", method=method)

                    self.assertEqual(status, 405)
                    self.assertEqual(headers["Allow"], "POST")
                    self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_every_other_path_still_refuses_every_write(self) -> None:
        code = self.issue()

        with self.running() as base:
            token = self.redeem(base, code)[2]["deviceToken"]
            for path in ("/health", "/decision?symbol=NVDA&horizon=short"):
                for method in ("POST", "PUT", "PATCH", "DELETE"):
                    with self.subTest(path=path, method=method):
                        status, headers, body = call(
                            f"{base}{path}", method=method, token=token
                        )

                        self.assertEqual(status, 405)
                        self.assertEqual(headers["Allow"], "GET")
                        self.assertEqual(body["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_a_write_to_a_neighbouring_path_is_not_a_second_write(self) -> None:
        code = self.issue()

        with self.running() as base:
            token = self.redeem(base, code)[2]["deviceToken"]
            for path in ("/orders", "/v1/device-pairings/extra", "/v1", "/"):
                with self.subTest(path=path):
                    status, _, body = call(f"{base}{path}", method="POST", token=token)

                    self.assertEqual(status, 404)
                    self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

    def test_an_unauthenticated_caller_learns_nothing_but_the_pairing_path(
        self,
    ) -> None:
        with self.running() as base:
            for path in ("/health", "/decision", "/orders"):
                with self.subTest(path=path):
                    self.assertEqual(call(f"{base}{path}")[0], 401)

    def test_a_deployment_without_a_device_store_serves_no_pairing_path(self) -> None:
        """No store, no pairing route, and no unauthenticated write anywhere.

        This is the developer's own laptop: loopback, nothing in front of it,
        no credential database. Serving the route there would mean a write path
        with no rate limiter behind it.
        """
        with self.running(self.config(device_database=None)) as base:
            status, _, body = call(f"{base}{PAIRING_PATH}", method="POST", body=b"{}")
            self.assertEqual(status, 404)
            self.assertEqual(body["error"]["code"], "PATH_NOT_ALLOWED")

            self.assertEqual(call(f"{base}/health")[0], 200)


class UnreadableStoreTests(PairingCase):
    """A store this process cannot read is a server fault, not a bad credential.

    Answering 401 there would tell a phone with a perfectly good token that it
    had been revoked, and would send the user to re-pair against a host that
    cannot pair. Answering 200 would be worse.
    """

    class Unreadable:
        MESSAGE = "/var/lib/us-stock-helper/device-auth.sqlite3 could not be read"

        def redeem_pairing_code(self, code: object, *, client_id: str) -> Any:
            raise DeviceAuthError(ErrorCode.STORAGE_UNREADABLE, self.MESSAGE)

        def verify_token(self, token: object) -> Any:
            raise DeviceAuthError(ErrorCode.STORAGE_UNREADABLE, self.MESSAGE)

    def test_pairing_reports_a_server_fault_without_naming_the_file(self) -> None:
        gate = DeviceGate(self.Unreadable())  # type: ignore[arg-type]

        with self.running(gate=gate) as base:
            status, _, body = self.redeem(base, WRONG_CODE)

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "PAIRING_UNAVAILABLE")
        self.assertNotIn("var/lib", repr(body))

    def test_a_read_reports_a_server_fault_rather_than_refusing_the_token(self) -> None:
        gate = DeviceGate(self.Unreadable())  # type: ignore[arg-type]

        with self.running(gate=gate) as base:
            status, _, body = call(f"{base}/health", token="0" * 64)

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "AUTH_UNAVAILABLE")
        self.assertNotIn("var/lib", repr(body))


class PairingConfigurationTests(unittest.TestCase):
    DATABASE = "/var/lib/us-stock-helper/device-auth.sqlite3"

    def test_a_proxied_deployment_must_name_a_credential_database(self) -> None:
        # The rule this replaces is the most load-bearing line of the
        # deployment: behind Caddy every request arrives from loopback, so
        # without a credential the whole decision chain is public.
        with self.assertRaisesRegex(ValueError, "DEVICE_AUTH_DATABASE"):
            AnalysisServerConfig.from_environment({"ANALYSIS_API_TRUST_PROXY": "1"})

        config = AnalysisServerConfig.from_environment(
            {"ANALYSIS_API_TRUST_PROXY": "1", "DEVICE_AUTH_DATABASE": self.DATABASE}
        )

        self.assertEqual(config.device_database, self.DATABASE)
        self.assertTrue(config.trust_proxy)
        self.assertEqual(config.host, "127.0.0.1")

    def test_lan_mode_must_name_a_credential_database_too(self) -> None:
        complete = {
            "ANALYSIS_API_ALLOW_LAN": "1",
            "ANALYSIS_API_HOST": "0.0.0.0",
            "ANALYSIS_API_ALLOWED_CLIENTS": "192.168.50.0/24",
            "DEVICE_AUTH_DATABASE": self.DATABASE,
        }
        for broken in ({}, {"DEVICE_AUTH_DATABASE": "   "}):
            with self.subTest(broken=broken):
                environment = {
                    key: value
                    for key, value in complete.items()
                    if key != "DEVICE_AUTH_DATABASE"
                }
                with self.assertRaisesRegex(ValueError, "DEVICE_AUTH_DATABASE"):
                    AnalysisServerConfig.from_environment({**environment, **broken})

        config = AnalysisServerConfig.from_environment(complete)
        self.assertTrue(config.allow_lan)
        self.assertEqual(config.device_database, self.DATABASE)

    def test_a_static_bearer_token_is_refused_rather_than_ignored(self) -> None:
        """The variable is gone, so a deployment still setting it must stop.

        Ignoring it would leave the operator believing a token they issued is
        being checked, while the only credential that opens the service is one
        they have never heard of.
        """
        with self.assertRaisesRegex(ValueError, "ANALYSIS_API_TOKEN"):
            AnalysisServerConfig.from_environment(
                {
                    "ANALYSIS_API_TRUST_PROXY": "1",
                    "DEVICE_AUTH_DATABASE": self.DATABASE,
                    "ANALYSIS_API_TOKEN": "0" * 64,
                }
            )
        with self.assertRaisesRegex(ValueError, "ANALYSIS_API_TOKEN"):
            AnalysisServerConfig.from_environment({"ANALYSIS_API_TOKEN": ""})

    def test_a_developer_loopback_deployment_needs_no_database(self) -> None:
        config = AnalysisServerConfig.from_environment({})

        self.assertIsNone(config.device_database)
        self.assertFalse(config.trust_proxy)

    def test_a_configured_database_is_never_discarded(self) -> None:
        config = AnalysisServerConfig.from_environment(
            {"DEVICE_AUTH_DATABASE": self.DATABASE}
        )

        self.assertEqual(config.device_database, self.DATABASE)


if __name__ == "__main__":
    unittest.main()
