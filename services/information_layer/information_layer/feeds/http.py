from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPMessage
from typing import IO, Protocol, runtime_checkable
from urllib.parse import urlparse


class FeedError(Exception):
    pass


class FeedAccessError(FeedError):
    pass


class ResponseTooLargeError(FeedError):
    pass


class FeedParseError(FeedError):
    pass


@dataclass(frozen=True, slots=True)
class HttpRequest:
    url: str
    allowed_hosts: tuple[str, ...]
    headers: tuple[tuple[str, str], ...]
    timeout_seconds: float
    max_response_bytes: int

    def header(self, name: str) -> str | None:
        target = name.casefold()
        return next(
            (value for key, value in self.headers if key.casefold() == target),
            None,
        )


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    retrieved_at: datetime

    def header(self, name: str) -> str | None:
        target = name.casefold()
        return next(
            (value for key, value in self.headers if key.casefold() == target),
            None,
        )


@runtime_checkable
class HttpTransport(Protocol):
    def request(self, request: HttpRequest) -> HttpResponse:
        ...


def validate_request(request: HttpRequest) -> None:
    parsed = urlparse(request.url)
    host = (parsed.hostname or "").casefold()
    allowed = {item.casefold() for item in request.allowed_hosts}
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise FeedAccessError("only credential-free HTTPS URLs are allowed")
    if host not in allowed:
        raise FeedAccessError(f"host {host!r} is not allowlisted")
    if request.timeout_seconds <= 0 or request.max_response_bytes <= 0:
        raise FeedAccessError("timeout and response byte limit must be positive")
    if not request.header("User-Agent"):
        raise FeedAccessError("an explicit User-Agent is required")
    forbidden = {"authorization", "cookie", "proxy-authorization"}
    if any(key.casefold() in forbidden for key, _ in request.headers):
        raise FeedAccessError("credentials are forbidden for public-feed transport")


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: tuple[str, ...]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        redirected = HttpRequest(
            url=newurl,
            allowed_hosts=self._allowed_hosts,
            headers=tuple(req.header_items()),
            timeout_seconds=1.0,
            max_response_bytes=1,
        )
        validate_request(redirected)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibHttpsTransport:
    """Small synchronous transport for public feeds; adapters remain injectable."""

    def request(self, request: HttpRequest) -> HttpResponse:
        validate_request(request)
        raw_request = urllib.request.Request(
            request.url,
            headers=dict(request.headers),
            method="GET",
        )
        opener = urllib.request.build_opener(
            _AllowlistedRedirectHandler(request.allowed_hosts)
        )
        try:
            response = opener.open(
                raw_request,
                timeout=request.timeout_seconds,
            )
        except urllib.error.HTTPError as error:
            response = error

        final_url = response.geturl()
        validate_request(
            HttpRequest(
                url=final_url,
                allowed_hosts=request.allowed_hosts,
                headers=request.headers,
                timeout_seconds=request.timeout_seconds,
                max_response_bytes=request.max_response_bytes,
            )
        )
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > request.max_response_bytes:
            response.close()
            raise ResponseTooLargeError("response exceeds configured byte limit")
        body = response.read(request.max_response_bytes + 1)
        response.close()
        if len(body) > request.max_response_bytes:
            raise ResponseTooLargeError("response exceeds configured byte limit")
        return HttpResponse(
            status_code=response.status,
            headers=tuple(response.headers.items()),
            body=body,
            retrieved_at=datetime.now(timezone.utc),
        )
