from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse

from ..event_sentiment import score_event_sentiment
from ..models import ClaimStatus, EvidenceEvent, SourceProvenance, _require_aware
from .http import (
    FeedAccessError,
    FeedParseError,
    HttpRequest,
    HttpResponse,
    HttpTransport,
    ResponseTooLargeError,
    validate_request,
)


@dataclass(frozen=True, slots=True)
class KeywordMapping:
    key: str
    keywords: tuple[str, ...]
    relevance: float

    def __post_init__(self) -> None:
        if (
            not self.key.strip()
            or not self.keywords
            or any(not keyword.strip() for keyword in self.keywords)
        ):
            raise ValueError("keyword mapping requires a key and keywords")
        if not 0.0 < self.relevance <= 1.0:
            raise ValueError("keyword relevance must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class FeedConfig:
    adapter_id: str
    feed_url: str
    allowed_hosts: tuple[str, ...]
    publisher_id: str
    publisher_name: str
    source_type: str
    reliability: float
    user_agent: str
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000
    summary_max_chars: int = 500
    symbol_mappings: tuple[KeywordMapping, ...] = ()
    entity_mappings: tuple[KeywordMapping, ...] = ()
    macro_mappings: tuple[KeywordMapping, ...] = ()
    geopolitical_mappings: tuple[KeywordMapping, ...] = ()
    claim_status: ClaimStatus = ClaimStatus.REPORTED
    robots_allowed: bool = False
    requires_auth: bool = False
    paywalled: bool = False
    minimum_poll_interval_seconds: float = 60.0
    base_backoff_seconds: float = 5.0
    max_backoff_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.adapter_id.strip() or not self.user_agent.strip():
            raise FeedAccessError("adapter_id and explicit User-Agent are required")
        if not self.robots_allowed:
            raise FeedAccessError("feed is disallowed by robots policy")
        if self.requires_auth or self.paywalled:
            raise FeedAccessError("login and paywalled sources are not supported")
        if self.summary_max_chars <= 0:
            raise ValueError("summary_max_chars must be positive")
        if (
            self.minimum_poll_interval_seconds <= 0
            or self.base_backoff_seconds <= 0
            or self.max_backoff_seconds <= 0
        ):
            raise ValueError("poll interval and backoff values must be positive")
        request = HttpRequest(
            url=self.feed_url,
            allowed_hosts=self.allowed_hosts,
            headers=(("User-Agent", self.user_agent),),
            timeout_seconds=self.timeout_seconds,
            max_response_bytes=self.max_response_bytes,
        )
        validate_request(request)


@dataclass(frozen=True, slots=True)
class CacheValidators:
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class FeedPollMetadata:
    status_code: int
    retrieved_at: datetime
    etag: str | None
    last_modified: str | None
    retry_after_seconds: float | None
    recommended_delay_seconds: float
    not_modified: bool
    future_entries_rejected: int


@dataclass(frozen=True, slots=True)
class FeedPollResult:
    events: tuple[EvidenceEvent, ...]
    metadata: FeedPollMetadata


@dataclass(frozen=True, slots=True)
class _ParsedEntry:
    identity: str
    title: str
    summary: str
    canonical_url: str
    published_at: datetime
    updated_at: datetime


class _PlainTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class GenericFeedAdapter:
    def __init__(self, config: FeedConfig, transport: HttpTransport) -> None:
        self.config = config
        self.adapter_id = config.adapter_id
        self._transport = transport

    def fetch(
        self,
        *,
        since: datetime,
        until: datetime,
    ) -> Iterable[EvidenceEvent]:
        return self.poll(since=since, until=until).events

    def poll(
        self,
        *,
        since: datetime,
        until: datetime,
        validators: CacheValidators = CacheValidators(),
        consecutive_failures: int = 0,
    ) -> FeedPollResult:
        _require_aware(since, "since")
        _require_aware(until, "until")
        if since > until:
            raise ValueError("since cannot be after until")
        if consecutive_failures < 0:
            raise ValueError("consecutive_failures cannot be negative")

        headers = [
            ("User-Agent", self.config.user_agent),
            ("Accept", "application/atom+xml, application/rss+xml, application/xml"),
        ]
        if validators.etag:
            headers.append(("If-None-Match", validators.etag))
        if validators.last_modified:
            headers.append(("If-Modified-Since", validators.last_modified))
        request = HttpRequest(
            url=self.config.feed_url,
            allowed_hosts=self.config.allowed_hosts,
            headers=tuple(headers),
            timeout_seconds=self.config.timeout_seconds,
            max_response_bytes=self.config.max_response_bytes,
        )
        validate_request(request)
        response = self._transport.request(request)
        _require_aware(response.retrieved_at, "retrieved_at")
        if len(response.body) > self.config.max_response_bytes:
            raise ResponseTooLargeError("response exceeds configured byte limit")

        metadata = self._metadata(response, consecutive_failures)
        if response.status_code == 304:
            return FeedPollResult(events=(), metadata=metadata)
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            return FeedPollResult(events=(), metadata=metadata)
        if not 200 <= response.status_code < 300:
            raise FeedAccessError(
                f"feed returned non-retryable HTTP {response.status_code}"
            )

        parsed, rejected = self._parse(
            response.body,
            retrieved_at=response.retrieved_at,
            since=since,
            until=until,
        )
        events = tuple(self._to_event(entry, response.retrieved_at) for entry in parsed)
        return FeedPollResult(
            events=events,
            metadata=FeedPollMetadata(
                status_code=metadata.status_code,
                retrieved_at=metadata.retrieved_at,
                etag=metadata.etag,
                last_modified=metadata.last_modified,
                retry_after_seconds=metadata.retry_after_seconds,
                recommended_delay_seconds=metadata.recommended_delay_seconds,
                not_modified=metadata.not_modified,
                future_entries_rejected=rejected,
            ),
        )

    def _parse(
        self,
        body: bytes,
        *,
        retrieved_at: datetime,
        since: datetime,
        until: datetime,
    ) -> tuple[tuple[_ParsedEntry, ...], int]:
        lowered = body.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise FeedParseError("DTD and entity declarations are forbidden")
        try:
            root = ET.fromstring(body)
        except ET.ParseError as error:
            raise FeedParseError("invalid RSS/Atom XML") from error

        entries = (
            self._parse_rss(root)
            if _local_name(root.tag) in {"rss", "rdf"}
            else self._parse_atom(root)
        )
        accepted: list[_ParsedEntry] = []
        future_rejected = 0
        knowledge_cutoff = min(retrieved_at, until)
        for entry in entries:
            if (
                entry.published_at > knowledge_cutoff
                or entry.updated_at > knowledge_cutoff
            ):
                future_rejected += 1
                continue
            if entry.updated_at < since:
                continue
            accepted.append(entry)
        return tuple(accepted), future_rejected

    def _parse_atom(self, root: ET.Element) -> tuple[_ParsedEntry, ...]:
        entries: list[_ParsedEntry] = []
        for node in _descendants(root, "entry"):
            identity = _child_text(node, "id")
            title = _clean_text(_child_text(node, "title"), 1_000)
            raw_summary = (
                _child_text(node, "summary")
                or _child_text(node, "content")
            )
            summary = _clean_text(raw_summary, self.config.summary_max_chars)
            canonical_url = _atom_link(node)
            published_text = (
                _child_text(node, "published")
                or _child_text(node, "updated")
            )
            updated_text = _child_text(node, "updated") or published_text
            if not identity:
                identity = canonical_url
            entry = self._validated_entry(
                identity=identity,
                title=title,
                summary=summary,
                canonical_url=canonical_url,
                published_text=published_text,
                updated_text=updated_text,
            )
            if entry is not None:
                entries.append(entry)
        return tuple(entries)

    def _parse_rss(self, root: ET.Element) -> tuple[_ParsedEntry, ...]:
        entries: list[_ParsedEntry] = []
        for node in _descendants(root, "item"):
            canonical_url = _child_text(node, "link")
            identity = _child_text(node, "guid") or canonical_url
            published_text = (
                _child_text(node, "pubDate")
                or _child_text(node, "date")
            )
            entry = self._validated_entry(
                identity=identity,
                title=_clean_text(_child_text(node, "title"), 1_000),
                summary=_clean_text(
                    _child_text(node, "description"),
                    self.config.summary_max_chars,
                ),
                canonical_url=canonical_url,
                published_text=published_text,
                updated_text=published_text,
            )
            if entry is not None:
                entries.append(entry)
        return tuple(entries)

    def _validated_entry(
        self,
        *,
        identity: str,
        title: str,
        summary: str,
        canonical_url: str,
        published_text: str,
        updated_text: str,
    ) -> _ParsedEntry | None:
        if not identity or not title or not canonical_url:
            return None
        parsed_link = urlparse(canonical_url)
        if (
            parsed_link.scheme != "https"
            or not parsed_link.hostname
            or parsed_link.username
            or parsed_link.password
        ):
            return None
        published_at = _parse_timestamp(published_text)
        updated_at = _parse_timestamp(updated_text)
        if published_at is None or updated_at is None:
            return None
        return _ParsedEntry(
            identity=identity,
            title=title,
            summary=summary,
            canonical_url=canonical_url,
            published_at=published_at,
            updated_at=updated_at,
        )

    def _to_event(
        self,
        entry: _ParsedEntry,
        retrieved_at: datetime,
    ) -> EvidenceEvent:
        claim_key = self._claim_key(entry)
        preview_hash = hashlib.sha256(
            f"{entry.title.casefold()}\n{entry.summary.casefold()}".encode("utf-8")
        ).hexdigest()
        event_id = (
            f"{self.adapter_id}:"
            f"{hashlib.sha256(f'{claim_key}|{preview_hash}'.encode()).hexdigest()[:20]}"
        )
        text = f"{entry.title}\n{entry.summary}".casefold()
        reading = score_event_sentiment(f"{entry.title} {entry.summary}")
        return EvidenceEvent.create(
            event_id=event_id,
            claim_key=claim_key,
            headline=entry.title,
            summary=entry.summary,
            provenance=SourceProvenance(
                source_id=self.adapter_id,
                publisher_id=self.config.publisher_id,
                publisher_name=self.config.publisher_name,
                canonical_url=entry.canonical_url,
                source_type=self.config.source_type,
                reliability=self.config.reliability,
            ),
            event_time=entry.published_at,
            published_at=entry.published_at,
            first_seen_at=retrieved_at,
            available_at=retrieved_at,
            retrieved_at=retrieved_at,
            claim_status=self.config.claim_status,
            sentiment=reading.score if reading.measured else 0.0,
            sentiment_measured=reading.measured,
            confidence=self.config.reliability,
            symbol_relevance=_match_keywords(
                text,
                self.config.symbol_mappings,
                uppercase=True,
            ),
            entity_relevance=_match_keywords(
                text,
                self.config.entity_mappings,
                uppercase=False,
            ),
            macro_tags=_match_tags(text, self.config.macro_mappings),
            geopolitical_tags=_match_tags(
                text,
                self.config.geopolitical_mappings,
            ),
            attributes=self._attributes(entry),
        )

    def _claim_key(self, entry: _ParsedEntry) -> str:
        identity_hash = hashlib.sha256(entry.identity.encode()).hexdigest()[:20]
        return f"feed|{self.adapter_id}|{identity_hash}"

    def _attributes(self, entry: _ParsedEntry) -> tuple[tuple[str, str], ...]:
        return (
            ("feed_entry_id", entry.identity),
            ("feed_updated_at", entry.updated_at.isoformat()),
        )

    def _metadata(
        self,
        response: HttpResponse,
        consecutive_failures: int,
    ) -> FeedPollMetadata:
        retry_after = _retry_after_seconds(
            response.header("Retry-After"),
            response.retrieved_at,
        )
        retryable = (
            response.status_code in {408, 425, 429}
            or response.status_code >= 500
        )
        backoff = (
            min(
                self.config.max_backoff_seconds,
                self.config.base_backoff_seconds * (2**consecutive_failures),
            )
            if retryable
            else 0.0
        )
        return FeedPollMetadata(
            status_code=response.status_code,
            retrieved_at=response.retrieved_at,
            etag=response.header("ETag"),
            last_modified=response.header("Last-Modified"),
            retry_after_seconds=retry_after,
            recommended_delay_seconds=max(
                self.config.minimum_poll_interval_seconds,
                backoff,
                retry_after or 0.0,
            ),
            not_modified=response.status_code == 304,
            future_entries_rejected=0,
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _descendants(root: ET.Element, name: str) -> tuple[ET.Element, ...]:
    target = name.casefold()
    return tuple(node for node in root.iter() if _local_name(node.tag) == target)


def _child_text(node: ET.Element, name: str) -> str:
    target = name.casefold()
    for child in node:
        if _local_name(child.tag) == target:
            return "".join(child.itertext()).strip()
    return ""


def _atom_link(node: ET.Element) -> str:
    fallback = ""
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if not href:
            continue
        fallback = fallback or href
        if child.attrib.get("rel", "alternate") == "alternate":
            return href
    return fallback


def _clean_text(raw: str, max_chars: int) -> str:
    parser = _PlainTextExtractor()
    parser.feed(html.unescape(raw))
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def _parse_timestamp(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if "T" in value
            else parsedate_to_datetime(value)
        )
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _match_keywords(
    text: str,
    mappings: Iterable[KeywordMapping],
    *,
    uppercase: bool,
) -> tuple[tuple[str, float], ...]:
    matches = []
    for mapping in mappings:
        if any(_keyword_matches(text, keyword) for keyword in mapping.keywords):
            key = mapping.key.upper() if uppercase else mapping.key
            matches.append((key, mapping.relevance))
    return tuple(sorted(matches))


def _keyword_matches(text: str, keyword: str) -> bool:
    normalized = keyword.strip().casefold()
    if normalized.replace(" ", "").isalnum():
        return bool(
            re.search(
                rf"(?<!\w){re.escape(normalized)}(?!\w)",
                text,
            )
        )
    return normalized in text


def _match_tags(
    text: str,
    mappings: Iterable[KeywordMapping],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                mapping.key.strip().upper()
                for mapping in mappings
                if any(
                    _keyword_matches(text, keyword)
                    for keyword in mapping.keywords
                )
            }
        )
    )


def _retry_after_seconds(
    value: str | None,
    retrieved_at: datetime,
) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None or retry_at.utcoffset() is None:
            return None
        return max(0.0, (retry_at - retrieved_at).total_seconds())
