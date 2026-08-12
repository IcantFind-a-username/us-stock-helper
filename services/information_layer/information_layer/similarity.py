"""Decide whether two reports describe the same event.

Corroboration is the gate that separates an actionable claim from an
unconfirmed one, and it was unreachable in practice: two outlets covering the
same announcement arrive with different URLs and different wording, so exact
matching on either filed them as two unrelated single-source claims.

Merging too eagerly is the worse error — it would invent corroboration between
unrelated stories and let one inherit the other's source count — so the rule
here is conservative on every axis: the reports must concern the same symbol,
land close together in time, and share most of their meaningful words.

Deterministic and versioned, because a cluster boundary that moves between runs
makes every downstream count unreproducible.
"""

from __future__ import annotations

import re
from datetime import timedelta

from .models import EvidenceEvent


SIMILARITY_VERSION = "headline-jaccard-window-v1"

# Companies repeat the same phrasing every quarter, so identical wording months
# apart is a new event, not a second source for the old one.
_TIME_WINDOW = timedelta(hours=36)
_MINIMUM_OVERLAP = 0.6
_MINIMUM_TOKENS = 3

_WORD = re.compile(r"[a-z0-9]+")
# Words that carry no topic. Kept small and explicit: an aggressive stop list
# starts deciding which stories are "the same" on its own.
_FILLER = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "but",
        "as", "at", "by", "from", "with", "after", "before", "its", "it",
        "is", "was", "were", "be", "been", "has", "have", "had", "will",
        "that", "this", "than", "then", "over", "into", "amid", "says",
        "said", "year", "full", "up", "down", "new", "more", "most",
    }
)


def headline_tokens(text: str) -> frozenset[str]:
    """Meaningful words of a headline, lowercased and stripped of filler."""

    return frozenset(
        word
        for word in _WORD.findall((text or "").casefold())
        # Digits survive at any length: the "1" in Q1 and the "5" in "up 5%"
        # are often the only thing separating two events.
        if word not in _FILLER and (word.isdigit() or len(word) > 1)
    )


def same_story(left: EvidenceEvent, right: EvidenceEvent) -> bool:
    """Whether two reports describe one event, by a conservative rule."""

    if not _shares_symbol(left, right):
        return False
    if abs(left.published_at - right.published_at) > _TIME_WINDOW:
        return False
    left_tokens = headline_tokens(left.headline)
    right_tokens = headline_tokens(right.headline)
    if min(len(left_tokens), len(right_tokens)) < _MINIMUM_TOKENS:
        # Too little text to judge; treating it as a match would merge on
        # almost no evidence.
        return False
    if _numbers_disagree(left_tokens, right_tokens):
        return False
    union = left_tokens | right_tokens
    if not union:
        return False
    return len(left_tokens & right_tokens) / len(union) >= _MINIMUM_OVERLAP


def _numbers_disagree(left: frozenset[str], right: frozenset[str]) -> bool:
    """Numbers usually are the distinguishing detail in this register.

    "first-quarter revenue of 30 billion" and "…of 44 billion" share almost
    every word and describe different facts. One side quoting a figure the
    other omits is ordinary coverage, so the rule only applies when both do.
    """

    left_numbers = {token for token in left if token.isdigit()}
    right_numbers = {token for token in right if token.isdigit()}
    if not left_numbers or not right_numbers:
        return False
    return not (left_numbers & right_numbers)


def _shares_symbol(left: EvidenceEvent, right: EvidenceEvent) -> bool:
    left_symbols = {symbol for symbol, _ in left.symbol_relevance}
    right_symbols = {symbol for symbol, _ in right.symbol_relevance}
    if not left_symbols or not right_symbols:
        return False
    return bool(left_symbols & right_symbols)
