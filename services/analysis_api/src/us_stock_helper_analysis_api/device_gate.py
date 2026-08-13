"""The credential boundary in front of the read-only surface.

All of the security here belongs to `device_auth`; this module only decides
what an HTTP caller is told about its answers. Three rules shape it.

A refusal must not say which of the several ways a pairing code can be wrong
applies. `device_auth` already collapses "expired", "already used" and "never
existed" into one message so that a guesser cannot learn which of their guesses
had once been real, and that collapse survives only if this layer refrains from
mapping them back onto distinct status codes.

A store this process cannot read must never be reported as a credential that is
not valid. The first is a server fault and the second accuses the caller; a
phone told its good token was refused would be sent to re-pair against a host
that cannot pair.

And the throttle is the whole protection on the one unauthenticated route, so
the identity it counts against has to be the address this host's own proxy
observed — never one the caller chose for itself.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Protocol

from us_stock_helper_device_auth import (
    CODE_THROTTLED,
    DeviceAuthError,
    DeviceAuthService,
    DeviceStore,
    PairingOutcome,
    TokenVerification,
)


# A pairing body carries a code of at most eight characters and nothing else
# this service reads. The cap is what the boundary is willing to pull off the
# socket at all, so it is deliberately far below Caddy's own 4KB body limit.
MAX_PAIRING_BODY_BYTES = 1024

_PAIRING_CODE_FIELD = "pairingCode"


class DeviceAuthority(Protocol):
    """The two calls this boundary is allowed to make.

    Stated as a protocol rather than taking `DeviceAuthService` outright so
    that the narrowness is checkable: issuing a pairing code and revoking a
    device are operator acts, and nothing reachable from an HTTP request may
    call them.
    """

    def redeem_pairing_code(self, code: object, *, client_id: str) -> PairingOutcome: ...

    def verify_token(self, token: object) -> TokenVerification: ...


@dataclass(frozen=True, slots=True)
class DeviceGate:
    auth: DeviceAuthority

    @classmethod
    def open(cls, database: str) -> "DeviceGate":
        """Open the credential store, or raise.

        `DeviceStore` refuses a file or directory that any other account could
        read or replace, and that refusal is meant to reach the operator as a
        service that will not start. Nothing here softens it into a warning.
        """
        return cls(DeviceAuthService(store=DeviceStore(database)))

    # --- reads ------------------------------------------------------------

    def refusal(
        self, authorization: str | None
    ) -> tuple[int, dict[str, str], dict[str, Any]] | None:
        """None when this caller may proceed, otherwise the answer it gets."""
        prefix = "Bearer "
        token = (
            authorization[len(prefix) :]
            if authorization and authorization.startswith(prefix)
            else ""
        )
        try:
            verified = self.auth.verify_token(token)
        except DeviceAuthError:
            return _unavailable("AUTH_UNAVAILABLE", "authorization")
        if verified.authorized:
            return None
        return 401, {}, _error(
            "AUTH_REQUIRED", "A paired device token is required"
        )

    # --- the one write ----------------------------------------------------

    def redeem(
        self, body: bytes, *, client_id: str
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        attempt = _read_attempt(body)
        if attempt is _NOT_AN_ATTEMPT:
            # Not spending a rate-limit slot here is the point. Anything that
            # is not a JSON object cannot be a guess at a code, and counting it
            # would let a few bytes of garbage deny the operator the pairing
            # window they are standing at the terminal waiting for.
            return 400, {}, _error(
                "INVALID_ARGUMENT", "The pairing request body is not a JSON object"
            )

        try:
            outcome = self.auth.redeem_pairing_code(attempt, client_id=client_id)
        except DeviceAuthError:
            return _unavailable("PAIRING_UNAVAILABLE", "pairing")

        if outcome.token is None or outcome.device_id is None:
            if outcome.reason == CODE_THROTTLED:
                headers = (
                    {}
                    if outcome.retry_after_seconds is None
                    else {"Retry-After": str(outcome.retry_after_seconds)}
                )
                return 429, headers, _error("RATE_LIMITED", CODE_THROTTLED)
            # One status for every way the code was wrong, matching the single
            # message device_auth returns. Answering 409 for a replay and 410
            # for an expiry would rebuild exactly the distinction it refuses to
            # make.
            return 400, {}, _error("INVALID_PAIRING_CODE", outcome.reason or "")

        # 200 rather than 201: nothing addressable was created. A 201 promises
        # a resource, and this service exposes no device anywhere.
        return 200, {}, {
            "deviceId": outcome.device_id,
            "deviceToken": outcome.token,
            # Null is a fact and not a gap. A device token has no expiry; it
            # stops working when the operator revokes it and not before, and
            # the app must not invent a refresh schedule around a missing key.
            "expiresAt": None,
        }


_NOT_AN_ATTEMPT = object()


def _read_attempt(body: bytes) -> object:
    """The claimed pairing code, or the sentinel when this is not an attempt.

    A JSON object with no code in it is still an attempt: from the outside it
    is indistinguishable from a wrong guess, and treating it as free would be a
    way to guess without being counted.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _NOT_AN_ATTEMPT
    if not isinstance(payload, dict):
        return _NOT_AN_ATTEMPT
    # Only the code is read. `deviceName` arrives from the app and is dropped
    # on purpose: the operator names a phone when issuing its code, so no
    # string chosen by a caller reaches the listing an operator reads.
    return payload.get(_PAIRING_CODE_FIELD)


def rate_limit_identity(
    forwarded_for: str | None, peer_ip: str, *, trust_proxy: bool
) -> str:
    """Who this pairing attempt is counted against.

    Behind the reverse proxy every request arrives from 127.0.0.1, so counting
    the peer alone would put every phone in the world in one bucket and let any
    stranger lock the operator out of their own pairing window. The forwarded
    header is read only where a proxy was declared, and only its last entry:
    Caddy appends the address it observed to whatever the caller sent, so
    everything before that entry is the caller's own writing.
    """
    if not trust_proxy or forwarded_for is None:
        return peer_ip
    for candidate in reversed(forwarded_for.split(",")):
        stripped = candidate.strip()
        if not stripped:
            continue
        try:
            return str(ipaddress.ip_address(stripped))
        except ValueError:
            # A header the proxy did not write is not an identity. Falling back
            # to the peer collapses those callers into one bucket, which is the
            # safe direction to fail.
            return peer_ip
    return peer_ip


def _unavailable(code: str, subject: str) -> tuple[int, dict[str, str], dict[str, Any]]:
    # The underlying message names the database file, and a path in a public
    # response tells an attacker where to aim. The category is all the caller
    # gets; the operator gets the detail from the journal.
    return 503, {}, _error(code, f"The {subject} store cannot be read right now")


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}
