#!/usr/bin/env python3
"""Print the one validated Expo development-client URL for managed Metro."""

from __future__ import annotations

import ipaddress
import json
import re
import sys
import time
from collections.abc import Callable
from typing import IO
from urllib.parse import parse_qsl, quote, urlsplit

if __package__:
    from .local_runtime import HttpTransport, SocketHttpTransport
else:
    from local_runtime import HttpTransport, SocketHttpTransport  # type: ignore


_HOST = "127.0.0.1"
_PORT = 8088
_PATH = "/_expo/open?platform=ios&runtime=custom"
_TIMEOUT_SECONDS = 3
_MAX_HEADER_BYTES = 16 * 1024
_MAX_BODY_BYTES = 16 * 1024
_MAX_URL_CHARACTERS = 2048
_EXPECTED_SCHEME = "exp+us-stock-helper"
_EXPECTED_AUTHORITY = "expo-development-client"
_EXPECTED_APP_ID = "com.franz.usstockhelper.dev"
_EXPECTED_RESPONSE_FIELDS = frozenset(
    {"scheme", "availableRuntimes", "runtime", "url", "appId"}
)
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class MetroDeepLinkError(RuntimeError):
    """A fixed-detail launcher contract failure safe for the CLI boundary."""


def _fail() -> MetroDeepLinkError:
    return MetroDeepLinkError("invalid_launcher_contract")


def fetch_launcher_payload(
    *,
    transport: HttpTransport | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> bytes:
    """Fetch the bounded loopback-only Expo launcher response."""

    client = transport or SocketHttpTransport()
    deadline = monotonic() + _TIMEOUT_SECONDS

    def remaining() -> float:
        value = deadline - monotonic()
        if value <= 0:
            raise TimeoutError
        return value

    try:
        client.connect(_HOST, _PORT, remaining())
        request = (
            f"GET {_PATH} HTTP/1.1\r\n"
            f"Host: {_HOST}:{_PORT}\r\n"
            "Connection: close\r\n"
            "Accept: application/json\r\n\r\n"
        ).encode("ascii")
        sent = 0
        while sent < len(request):
            written = client.send(request[sent:], remaining())
            if written <= 0:
                raise _fail()
            sent += written

        response = bytearray()
        header_end = -1
        while header_end < 0:
            chunk = client.receive(4096, remaining())
            if not chunk:
                raise _fail()
            response.extend(chunk)
            header_end = response.find(b"\r\n\r\n")
            if (header_end < 0 and len(response) > _MAX_HEADER_BYTES) or (
                header_end > _MAX_HEADER_BYTES
            ):
                raise _fail()

        header_bytes = bytes(response[:header_end])
        body = bytearray(response[header_end + 4 :])
        try:
            lines = header_bytes.decode("iso-8859-1").split("\r\n")
            version, status_text, _reason = lines[0].split(" ", 2)
        except (UnicodeError, ValueError):
            raise _fail() from None
        if version not in {"HTTP/1.0", "HTTP/1.1"} or status_text != "200":
            raise _fail()

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if line[:1].isspace() or ":" not in line:
                raise _fail()
            key, value = line.split(":", 1)
            if not re.fullmatch(r"[A-Za-z0-9-]+", key):
                raise _fail()
            normalized = key.lower()
            if normalized in headers:
                raise _fail()
            headers[normalized] = value.strip()
        length_text = headers.get("content-length")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip()
        if (
            length_text is None
            or not length_text.isdecimal()
            or int(length_text) > _MAX_BODY_BYTES
            or content_type.lower() != "application/json"
            or "transfer-encoding" in headers
        ):
            raise _fail()
        content_length = int(length_text)
        if len(body) > content_length:
            raise _fail()

        remaining()
        while len(body) < content_length:
            chunk = client.receive(
                min(4096, content_length - len(body)),
                remaining(),
            )
            if not chunk:
                raise _fail()
            body.extend(chunk)
            if len(body) > content_length:
                raise _fail()
        remaining()
        return bytes(body)
    finally:
        client.close()


def extract_launcher_url(payload: bytes) -> str:
    """Return a launcher URL only when every fixed Debug contract agrees."""

    if not isinstance(payload, bytes) or len(payload) > _MAX_BODY_BYTES:
        raise _fail()
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _fail() from None
    if (
        not isinstance(document, dict)
        or set(document) != _EXPECTED_RESPONSE_FIELDS
        or document["scheme"] != _EXPECTED_SCHEME
        or document["availableRuntimes"] != ["custom"]
        or document["runtime"] != "custom"
        or document["appId"] != _EXPECTED_APP_ID
    ):
        raise _fail()
    candidate = document["url"]
    if (
        not isinstance(candidate, str)
        or not candidate.isascii()
        or not 1 <= len(candidate) <= _MAX_URL_CHARACTERS
    ):
        raise _fail()

    try:
        outer = urlsplit(candidate)
        query = parse_qsl(
            outer.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError:
        raise _fail() from None
    if (
        outer.scheme != _EXPECTED_SCHEME
        or outer.netloc != _EXPECTED_AUTHORITY
        or outer.path != "/"
        or outer.fragment
        or outer.username is not None
        or outer.password is not None
        or len(query) != 1
        or query[0][0] != "url"
    ):
        raise _fail()

    manifest_text = query[0][1]
    encoded_manifest = quote(manifest_text, safe="")
    expected_candidate = (
        f"{_EXPECTED_SCHEME}://{_EXPECTED_AUTHORITY}/?url={encoded_manifest}"
    )
    if outer.query != f"url={encoded_manifest}" or candidate != expected_candidate:
        raise _fail()
    try:
        manifest = urlsplit(manifest_text)
        address = ipaddress.ip_address(manifest.hostname or "")
        manifest_port = manifest.port
    except ValueError:
        raise _fail() from None
    if (
        manifest.scheme != "http"
        or manifest_port != _PORT
        or manifest.path
        or manifest.query
        or manifest.fragment
        or manifest.username is not None
        or manifest.password is not None
        or not isinstance(address, ipaddress.IPv4Address)
        or not any(address in network for network in _PRIVATE_NETWORKS)
        or manifest.netloc != f"{address}:{_PORT}"
        or manifest_text != f"http://{address}:{_PORT}"
    ):
        raise _fail()
    return candidate


def main(
    *,
    fetcher: Callable[[], bytes] = fetch_launcher_payload,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Print exactly one URL, or one fixed error with no response detail."""

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    try:
        launcher_url = extract_launcher_url(fetcher())
    except Exception:
        # The CLI is a redaction boundary: neither local response bytes nor an
        # exception message may reach a terminal or automation log.
        print("managed Metro launcher URL unavailable", file=err)
        return 1
    print(launcher_url, file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
