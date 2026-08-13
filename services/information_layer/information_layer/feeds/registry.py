"""Declare which real sources this system is allowed to poll, and on what terms.

Every entry here is a channel its publisher operates for syndication: US
government material that is public domain, and issuer newsrooms that publish
their own releases as a feed. Licensed wires and press-release distributors are
deliberately absent — polling them needs a contract, and a source we cannot
lawfully read is worse than no source, because its evidence would have to be
withdrawn later from decisions already taken on it.

Each entry states the terms rather than leaving them to the code that polls:
what kind of channel it is, how far it can be trusted, how often it may be
asked, and whether its publisher demands a User-Agent naming a contact address.
SEC EDGAR does, and its contact comes from the environment: an address baked
into this file would be wrong for whoever actually runs the deployment, and the
publisher would be unable to reach the operator it is rate-limiting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping
from urllib.parse import urlparse

from ..cik_registry import CikTickerRegistry
from ..models import ClaimStatus
from .generic import FeedConfig, GenericFeedAdapter, KeywordMapping
from .http import FeedAccessError, HttpTransport
from .sec import SecCurrentFilingsAdapter


CONTACT_EMAIL_VARIABLE = "US_STOCK_HELPER_CONTACT_EMAIL"
APPLICATION_TOKEN = "us-stock-helper/0.1"


class SourceKind(str, Enum):
    OFFICIAL_ANNOUNCEMENT = "official_announcement"
    REGULATORY_FILING = "regulatory_filing"
    MACRO_DATA = "macro_data"
    # No wire ships in this registry. The slot exists so adding one is a
    # deliberate act with a licence behind it, not an oversight.
    NEWS_WIRE = "news_wire"


# Floors, not settings: a publisher that considers itself hammered blocks the
# client, and a blocked client reports no evidence for reasons that have
# nothing to do with the market.
_MINIMUM_POLL_INTERVAL_SECONDS: Mapping[SourceKind, float] = {
    SourceKind.REGULATORY_FILING: 60.0,
    SourceKind.MACRO_DATA: 300.0,
    SourceKind.OFFICIAL_ANNOUNCEMENT: 300.0,
    SourceKind.NEWS_WIRE: 60.0,
}


def minimum_poll_interval_seconds(kind: SourceKind) -> float:
    return _MINIMUM_POLL_INTERVAL_SECONDS[kind]


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    kind: SourceKind
    publisher_id: str
    publisher_name: str
    allowed_hosts: tuple[str, ...]
    reliability: float
    poll_interval_seconds: float
    requires_contact_user_agent: bool
    robots_allows_polling: bool
    claim_status: ClaimStatus
    # An RSS or Atom endpoint, or an EDGAR form whose feed URL the filing
    # adapter builds itself. Exactly one of the two.
    feed_url: str | None = None
    sec_form_type: str | None = None
    symbol_mappings: tuple[KeywordMapping, ...] = ()
    entity_mappings: tuple[KeywordMapping, ...] = ()
    macro_mappings: tuple[KeywordMapping, ...] = ()
    geopolitical_mappings: tuple[KeywordMapping, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.source_id.strip()
            or not self.publisher_id.strip()
            or not self.publisher_name.strip()
        ):
            raise ValueError("a source needs an id and a named publisher")
        if not self.robots_allows_polling:
            raise FeedAccessError(
                f"{self.source_id} is disallowed by its publisher's robots policy"
            )
        if (self.feed_url is None) == (self.sec_form_type is None):
            raise FeedAccessError(
                "a source declares either a feed URL or an EDGAR form, not both"
            )
        if not 0.0 < self.reliability <= 1.0:
            raise ValueError("reliability must be in (0, 1]")
        floor = minimum_poll_interval_seconds(self.kind)
        if self.poll_interval_seconds < floor:
            raise ValueError(
                f"{self.source_id} may not be polled faster than {floor:.0f}s"
            )
        if self.sec_form_type is not None:
            self._validate_edgar()
        else:
            self._validate_endpoint()

    def _validate_edgar(self) -> None:
        if not self.requires_contact_user_agent:
            raise FeedAccessError(
                "EDGAR serves only clients whose User-Agent names a contact address"
            )
        if tuple(host.casefold() for host in self.allowed_hosts) != ("www.sec.gov",):
            raise FeedAccessError("an EDGAR source may only reach www.sec.gov")

    def _validate_endpoint(self) -> None:
        parsed = urlparse(self.feed_url or "")
        host = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
        ):
            raise FeedAccessError("only credential-free HTTPS feeds may be declared")
        if host not in {item.casefold() for item in self.allowed_hosts}:
            raise FeedAccessError(
                f"{self.source_id} points outside its own host allowlist"
            )


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    sources: tuple[SourceSpec, ...]

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError("a registry with no source declares nothing")
        identifiers = [item.source_id for item in self.sources]
        if len(set(identifiers)) != len(identifiers):
            # Two entries under one id would share the coordinator's published
            # record, and each would re-announce the other's items as new.
            raise ValueError("source ids must be unique within a registry")

    def requiring_contact(self) -> tuple[SourceSpec, ...]:
        return tuple(
            item for item in self.sources if item.requires_contact_user_agent
        )

    def of_kind(self, kind: SourceKind) -> tuple[SourceSpec, ...]:
        return tuple(item for item in self.sources if item.kind is kind)


_MACRO_MAPPINGS = (
    KeywordMapping(
        "MONETARY_POLICY",
        ("fomc", "federal funds", "monetary policy", "interest rate"),
        0.9,
    ),
    KeywordMapping(
        "INFLATION",
        ("inflation", "consumer price index", "producer price index"),
        0.9,
    ),
    KeywordMapping(
        "LABOR_MARKET",
        ("employment situation", "unemployment", "nonfarm payroll", "jobless"),
        0.9,
    ),
    KeywordMapping(
        "GROWTH",
        ("gross domestic product", "personal income", "consumer spending"),
        0.85,
    ),
)


PUBLIC_SOURCES = SourceRegistry(
    (
        SourceSpec(
            source_id="sec-current-8-k",
            kind=SourceKind.REGULATORY_FILING,
            publisher_id="sec-edgar",
            publisher_name="U.S. SEC EDGAR",
            sec_form_type="8-K",
            allowed_hosts=("www.sec.gov",),
            reliability=0.99,
            poll_interval_seconds=300.0,
            requires_contact_user_agent=True,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
        ),
        SourceSpec(
            source_id="sec-current-4",
            kind=SourceKind.REGULATORY_FILING,
            publisher_id="sec-edgar",
            publisher_name="U.S. SEC EDGAR",
            sec_form_type="4",
            allowed_hosts=("www.sec.gov",),
            reliability=0.99,
            poll_interval_seconds=300.0,
            requires_contact_user_agent=True,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
        ),
        SourceSpec(
            source_id="federal-reserve-press",
            kind=SourceKind.MACRO_DATA,
            publisher_id="federal-reserve",
            publisher_name="U.S. Federal Reserve Board",
            feed_url="https://www.federalreserve.gov/feeds/press_all.xml",
            allowed_hosts=("www.federalreserve.gov",),
            reliability=0.99,
            poll_interval_seconds=900.0,
            requires_contact_user_agent=False,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
            macro_mappings=_MACRO_MAPPINGS,
        ),
        SourceSpec(
            source_id="bls-news-releases",
            kind=SourceKind.MACRO_DATA,
            publisher_id="bls",
            publisher_name="U.S. Bureau of Labor Statistics",
            feed_url="https://www.bls.gov/feed/bls_latest.rss",
            allowed_hosts=("www.bls.gov",),
            reliability=0.99,
            poll_interval_seconds=1800.0,
            requires_contact_user_agent=False,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
            macro_mappings=_MACRO_MAPPINGS,
        ),
        SourceSpec(
            source_id="bea-news-releases",
            kind=SourceKind.MACRO_DATA,
            publisher_id="bea",
            publisher_name="U.S. Bureau of Economic Analysis",
            feed_url="https://apps.bea.gov/rss/rss.xml",
            allowed_hosts=("apps.bea.gov",),
            reliability=0.99,
            poll_interval_seconds=1800.0,
            requires_contact_user_agent=False,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
            macro_mappings=_MACRO_MAPPINGS,
        ),
        SourceSpec(
            source_id="apple-newsroom",
            kind=SourceKind.OFFICIAL_ANNOUNCEMENT,
            publisher_id="apple",
            publisher_name="Apple Newsroom",
            feed_url="https://www.apple.com/newsroom/rss-feed.rss",
            allowed_hosts=("www.apple.com",),
            reliability=0.95,
            poll_interval_seconds=900.0,
            requires_contact_user_agent=False,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
            # An issuer newsroom carries only that issuer's releases, but the
            # attribution still has to be earned from the text: a release that
            # never names the company gets no symbol rather than an assumed one.
            symbol_mappings=(KeywordMapping("AAPL", ("apple", "aapl"), 0.9),),
            entity_mappings=(KeywordMapping("Apple Inc.", ("apple",), 0.9),),
        ),
        SourceSpec(
            source_id="nvidia-newsroom",
            kind=SourceKind.OFFICIAL_ANNOUNCEMENT,
            publisher_id="nvidia",
            publisher_name="NVIDIA Newsroom",
            feed_url="https://nvidianews.nvidia.com/releases.xml",
            allowed_hosts=("nvidianews.nvidia.com",),
            reliability=0.95,
            poll_interval_seconds=900.0,
            requires_contact_user_agent=False,
            robots_allows_polling=True,
            claim_status=ClaimStatus.VERIFIED,
            symbol_mappings=(KeywordMapping("NVDA", ("nvidia", "nvda"), 0.9),),
            entity_mappings=(KeywordMapping("NVIDIA Corporation", ("nvidia",), 0.9),),
        ),
    )
)


def user_agent_for(contact_email: str | None = None) -> str:
    if contact_email is None or not contact_email.strip():
        return APPLICATION_TOKEN
    return f"{APPLICATION_TOKEN} ({_validated_contact(contact_email)})"


def contact_email_from_environment(
    environment: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environment is None else environment
    value = env.get(CONTACT_EMAIL_VARIABLE, "")
    if not value.strip():
        raise FeedAccessError(
            f"{CONTACT_EMAIL_VARIABLE} must name a reachable contact address"
        )
    return _validated_contact(value)


def build_adapters(
    *,
    transport: HttpTransport,
    contact_email: str | None = None,
    registry: SourceRegistry = PUBLIC_SOURCES,
    cik_registry: CikTickerRegistry | None = None,
) -> tuple[GenericFeedAdapter, ...]:
    contact = contact_email.strip() if contact_email else ""
    demanding = registry.requiring_contact()
    if demanding and not contact:
        listed = ", ".join(item.source_id for item in demanding)
        raise FeedAccessError(
            f"{listed} refuse to start until {CONTACT_EMAIL_VARIABLE} is set"
        )
    user_agent = user_agent_for(contact or None)
    return tuple(
        _adapter_for(
            item,
            transport=transport,
            user_agent=user_agent,
            cik_registry=cik_registry,
        )
        for item in registry.sources
    )


def _adapter_for(
    spec: SourceSpec,
    *,
    transport: HttpTransport,
    user_agent: str,
    cik_registry: CikTickerRegistry | None,
) -> GenericFeedAdapter:
    if spec.sec_form_type is not None:
        return SecCurrentFilingsAdapter(
            form_type=spec.sec_form_type,
            user_agent=user_agent,
            transport=transport,
            reliability=spec.reliability,
            minimum_poll_interval_seconds=spec.poll_interval_seconds,
            symbol_mappings=spec.symbol_mappings,
            entity_mappings=spec.entity_mappings,
            macro_mappings=spec.macro_mappings,
            geopolitical_mappings=spec.geopolitical_mappings,
            cik_registry=cik_registry,
        )
    return GenericFeedAdapter(
        FeedConfig(
            adapter_id=spec.source_id,
            feed_url=spec.feed_url or "",
            allowed_hosts=spec.allowed_hosts,
            publisher_id=spec.publisher_id,
            publisher_name=spec.publisher_name,
            source_type=spec.kind.value,
            reliability=spec.reliability,
            user_agent=user_agent,
            claim_status=spec.claim_status,
            robots_allowed=spec.robots_allows_polling,
            minimum_poll_interval_seconds=spec.poll_interval_seconds,
            symbol_mappings=spec.symbol_mappings,
            entity_mappings=spec.entity_mappings,
            macro_mappings=spec.macro_mappings,
            geopolitical_mappings=spec.geopolitical_mappings,
        ),
        transport,
    )


def _validated_contact(value: str) -> str:
    cleaned = value.strip()
    local, separator, domain = cleaned.partition("@")
    if not separator or not local or "." not in domain or " " in cleaned:
        raise FeedAccessError(
            f"{CONTACT_EMAIL_VARIABLE} must be a single email address"
        )
    return cleaned
