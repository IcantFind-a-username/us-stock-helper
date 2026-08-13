"""The credential primitives: what a pairing code is, what a token is, and how
either becomes an unreadable row.

Two secrets with two different threat models meet here. A pairing code is
short enough for a person to read off a terminal and type into a phone, so it
carries roughly forty bits and has to be slowed down with a memory-hard KDF
before it is ever compared. A device token is machine-generated and carries a
full thirty-two random bytes, so a keyed hash is enough and, unlike scrypt, is
cheap enough to run on every request.

Nothing in this module accepts or returns a plaintext secret that it also
writes down.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from dataclasses import dataclass

from .errors import DeviceAuthError, ErrorCode


# "0/O" and "1/I/L" are the pairs people transcribe wrong when reading a code
# off one screen and typing it into another, so the alphabet drops them.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
MIN_CODE_LENGTH = 6
MAX_CODE_LENGTH = 8
DEFAULT_CODE_LENGTH = 8
_CODE_SALT_BYTES = 16
# ASCII only, and that is not a limitation: input containing anything else is
# refused before this set is ever consulted.
_CODE_SEPARATORS = frozenset(" -\t\r\n")

TOKEN_ALGORITHM = "hmac-sha256"
TOKEN_SECRET_BYTES = 32
TOKEN_SALT_BYTES = 32
DEVICE_ID_BYTES = 12
_TOKEN_SEPARATOR = "."
_TOKEN_CHARACTERS = frozenset(string.ascii_letters + string.digits + "-_")


@dataclass(frozen=True, slots=True)
class ScryptParameters:
    """The cost of one pairing-code comparison, recorded next to every hash.

    Verification reads the parameters from the row rather than from this
    module, so raising the cost later leaves already-issued codes verifiable
    instead of silently rejecting every one of them.
    """

    n: int = 2**14
    r: int = 8
    p: int = 1
    length: int = 32

    def serialize(self) -> str:
        return f"scrypt$n={self.n},r={self.r},p={self.p},len={self.length}"

    @classmethod
    def parse(cls, serialized: object) -> "ScryptParameters":
        if not isinstance(serialized, str):
            raise DeviceAuthError(
                ErrorCode.SCHEMA_UNSUPPORTED, "stored KDF parameters are not text"
            )
        name, separator, body = serialized.partition("$")
        if not separator or name != "scrypt":
            raise DeviceAuthError(
                ErrorCode.SCHEMA_UNSUPPORTED,
                "stored KDF is not one this build can compute",
            )
        fields: dict[str, int] = {}
        for part in body.split(","):
            key, field_separator, value = part.partition("=")
            if not field_separator or not value.isdigit():
                raise DeviceAuthError(
                    ErrorCode.SCHEMA_UNSUPPORTED,
                    "stored KDF parameters are unreadable",
                )
            fields[key] = int(value)
        if set(fields) != {"n", "r", "p", "len"}:
            raise DeviceAuthError(
                ErrorCode.SCHEMA_UNSUPPORTED,
                "stored KDF parameters are incomplete",
            )
        return cls(n=fields["n"], r=fields["r"], p=fields["p"], length=fields["len"])


DEFAULT_SCRYPT = ScryptParameters()


def generate_code(length: int = DEFAULT_CODE_LENGTH) -> str:
    if not MIN_CODE_LENGTH <= length <= MAX_CODE_LENGTH:
        raise DeviceAuthError(
            ErrorCode.INVALID_ARGUMENT,
            f"a pairing code must be {MIN_CODE_LENGTH}-{MAX_CODE_LENGTH} characters",
        )
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def format_code(code: str) -> str:
    """Group the code so an operator can read it aloud without losing their place."""
    return f"{code[:4]}-{code[4:]}" if len(code) > 4 else code


def normalize_code(raw: object) -> str | None:
    """Fold operator formatting away, or refuse.

    Returning None rather than raising keeps every rejected shape on the same
    path as a wrong guess, so a caller cannot tell "not a code" from "not the
    code". Non-ASCII input is refused here rather than reaching str.encode or
    hmac.compare_digest, both of which raise on it.
    """
    if not isinstance(raw, str) or not raw.isascii():
        return None
    condensed = "".join(
        character for character in raw.upper() if character not in _CODE_SEPARATORS
    )
    if not MIN_CODE_LENGTH <= len(condensed) <= MAX_CODE_LENGTH:
        return None
    if not set(condensed).issubset(CODE_ALPHABET):
        return None
    return condensed


def new_code_salt() -> bytes:
    return secrets.token_bytes(_CODE_SALT_BYTES)


def code_hash(code: str, salt: bytes, parameters: ScryptParameters) -> bytes:
    try:
        return hashlib.scrypt(
            code.encode("ascii"),
            salt=salt,
            n=parameters.n,
            r=parameters.r,
            p=parameters.p,
            dklen=parameters.length,
            maxmem=128 * parameters.r * (parameters.n + parameters.p + 2) + (1 << 20),
        )
    except ValueError as exc:
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            "stored KDF parameters cannot be computed by this build",
        ) from exc


def new_device_id() -> str:
    # Hex rather than base64url: a device id is typed back into the terminal to
    # revoke it, and an identifier that can begin with "-" is read as an option
    # instead of an argument.
    return secrets.token_hex(DEVICE_ID_BYTES)


def new_token_secret() -> str:
    return secrets.token_urlsafe(TOKEN_SECRET_BYTES)


def new_token_salt() -> bytes:
    return secrets.token_bytes(TOKEN_SALT_BYTES)


def format_token(device_id: str, secret: str) -> str:
    return f"{device_id}{_TOKEN_SEPARATOR}{secret}"


def split_token(token: object) -> tuple[str, str] | None:
    """Separate the lookup half from the secret half, or refuse.

    The device id travels inside the token so verification can fetch one row
    and one salt instead of hashing the secret against every device on file.
    """
    if not isinstance(token, str) or not token.isascii():
        return None
    device_id, separator, secret = token.strip().partition(_TOKEN_SEPARATOR)
    if not separator or not device_id or not secret:
        return None
    if not _TOKEN_CHARACTERS.issuperset(device_id):
        return None
    if not _TOKEN_CHARACTERS.issuperset(secret):
        return None
    return device_id, secret


def token_hash(salt: bytes, secret: str, algorithm: str) -> bytes:
    if algorithm != TOKEN_ALGORITHM:
        raise DeviceAuthError(
            ErrorCode.SCHEMA_UNSUPPORTED,
            "stored token algorithm is not one this build can compute",
        )
    return hmac.new(salt, secret.encode("ascii"), hashlib.sha256).digest()
