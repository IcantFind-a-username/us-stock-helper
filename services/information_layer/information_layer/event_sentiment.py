"""Deterministic sentiment for one piece of financial text.

Generic sentiment tools mislabel financial writing — "liability", "charge" and
"tax" are ordinary accounting words, while "guidance cut" is the whole story —
so the lexicon here is financial only, listed in the open, and versioned so a
backtest can state which one it ran under.

The important distinction this makes is between *measured as neutral* and *not
measured at all*. Every real feed event used to carry a hardcoded 0.0, which the
aggregator could not tell apart from a genuinely balanced headline. A score of
None means the text contained nothing this lexicon knows how to read.

A language model is deliberately not used here. The product's rule is that
rule-based judgements stay rule-based and the model is reserved for
cross-source explanation; a scorer whose output changes between runs cannot be
backtested or audited, which is what this layer exists to support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


SENTIMENT_LEXICON_VERSION = "financial-lexicon-negation-v2"

# Weights are deliberately coarse. They express direction and rough strength,
# not calibrated probability, and must never be presented as one.
_POSITIVE = {
    "beat": 0.6,
    "beats": 0.6,
    "surged": 0.8,
    "surge": 0.7,
    "soared": 0.8,
    "jumped": 0.6,
    "rallied": 0.6,
    "raise": 0.6,
    "raised": 0.6,
    "raises": 0.6,
    "raising": 0.6,
    "lifts": 0.6,
    "lifted": 0.6,
    "rose": 0.5,
    "rises": 0.5,
    "climbed": 0.5,
    "gains": 0.5,
    "gained": 0.5,
    "wins": 0.5,
    "won": 0.5,
    "exceeds": 0.6,
    "exceeded": 0.6,
    "accelerates": 0.5,
    "accelerated": 0.5,
    "upgraded": 0.7,
    "upgrade": 0.6,
    "upgrades": 0.7,
    "profitability": 0.4,
    "outperform": 0.6,
    "record": 0.5,
    "profit": 0.4,
    "profitable": 0.5,
    "growth": 0.4,
    "strong": 0.4,
    "approval": 0.6,
    "approved": 0.6,
    "expanded": 0.4,
    "buyback": 0.5,
    "dividend": 0.3,
    "settled": 0.3,
    "resolved": 0.4,
}
_NEGATIVE = {
    "missed": -0.6,
    "misses": -0.6,
    "miss": -0.5,
    "plunged": -0.8,
    "plunge": -0.7,
    "slumped": -0.7,
    "tumbled": -0.7,
    "fell": -0.4,
    "falls": -0.4,
    "drops": -0.5,
    "dropped": -0.5,
    "sinks": -0.6,
    "sank": -0.6,
    "declines": -0.4,
    "declined": -0.4,
    "halts": -0.6,
    "sues": -0.5,
    "sued": -0.5,
    "recalls": -0.6,
    "warns": -0.5,
    "cut": -0.6,
    "cuts": -0.6,
    "lowered": -0.6,
    "lowers": -0.6,
    "slashed": -0.7,
    "slashes": -0.7,
    "downgraded": -0.7,
    "downgrades": -0.7,
    "downgrade": -0.6,
    "underperform": -0.6,
    "loss": -0.5,
    "losses": -0.5,
    "widening": -0.4,
    "weak": -0.4,
    "warning": -0.5,
    "warned": -0.5,
    "recall": -0.6,
    "probe": -0.5,
    "investigation": -0.5,
    "lawsuit": -0.5,
    "fraud": -0.9,
    "bankruptcy": -0.9,
    "delisting": -0.8,
    "halted": -0.6,
    "layoffs": -0.4,
    "dilution": -0.4,
    "default": -0.7,
    "restated": -0.6,
    "subpoena": -0.6,
}
_LEXICON = {**_POSITIVE, **_NEGATIVE}

# Phrases are matched before single words and consume the tokens they cover.
# Without them "cut costs" reads as badly as "cut guidance", and a headline
# about the shares falling is scored on whatever it fell in spite of.
_PHRASES: dict[tuple[str, ...], float] = {
    # A central-bank rate cut is not a company cutting its own outlook.
    ("cuts", "interest"): 0.5,
    ("cut", "interest"): 0.5,
    ("rate", "cut"): 0.5,
    ("rate", "cuts"): 0.5,
    ("cut", "costs"): 0.4,
    ("cuts", "costs"): 0.4,
    ("cost", "cuts"): 0.4,
    ("cutting", "costs"): 0.4,
    ("cut", "guidance"): -0.7,
    ("cuts", "guidance"): -0.7,
    ("lowered", "guidance"): -0.7,
    ("raised", "guidance"): 0.7,
    ("raises", "guidance"): 0.7,
    ("profit", "warning"): -0.8,
    ("beat", "and", "raised"): 0.9,
    ("beats", "and", "raises"): 0.9,
    # The market's own verdict on the stock, which outranks the item it reacted to.
    ("shares", "fell"): -0.9,
    ("shares", "plunged"): -0.95,
    ("shares", "slumped"): -0.9,
    ("shares", "tumbled"): -0.9,
    ("shares", "surged"): 0.9,
    ("shares", "soared"): 0.95,
    ("shares", "jumped"): 0.9,
    ("shares", "rallied"): 0.9,
    ("stock", "fell"): -0.9,
    ("stock", "plunged"): -0.95,
    ("stock", "surged"): 0.9,
    ("stock", "soared"): 0.95,
}
_MAX_PHRASE = max(len(phrase) for phrase in _PHRASES)

_NEGATORS = frozenset(
    {"not", "no", "never", "without", "fails", "failed", "unable", "denies", "denied"}
)
# How far a negator reaches. Wide enough for "did not manage to beat", narrow
# enough that one "not" early in a headline cannot invert a separate later
# clause.
_NEGATION_WINDOW = 3
_CLAUSE_BREAK = frozenset({";", ":", ".", ",", "—", "--"})
_TOKEN = re.compile(r"[a-z]+|[;:.,]|--|—")


@dataclass(frozen=True, slots=True)
class EventSentiment:
    """A sentiment reading, or an explicit statement that there was none."""

    score: float | None
    matched_terms: tuple[tuple[str, float], ...]
    method_version: str = SENTIMENT_LEXICON_VERSION

    @property
    def measured(self) -> bool:
        return self.score is not None

    def __post_init__(self) -> None:
        if self.score is not None and not -1.0 <= self.score <= 1.0:
            raise ValueError("sentiment score must be between -1 and 1")
        if (self.score is None) != (not self.matched_terms):
            raise ValueError("a score and its matched terms must agree")


def score_event_sentiment(text: str) -> EventSentiment:
    """Score one headline or summary against the versioned financial lexicon."""

    tokens = _TOKEN.findall(text.casefold())
    matched: list[tuple[str, float]] = []
    negation_countdown = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _CLAUSE_BREAK:
            negation_countdown = 0
            index += 1
            continue
        if token in _NEGATORS:
            negation_countdown = _NEGATION_WINDOW
            index += 1
            continue

        phrase_length, weight, label = _longest_phrase(tokens, index)
        if weight is None:
            weight = _LEXICON.get(token)
            label = token
            phrase_length = 1
        if weight is None:
            if negation_countdown:
                negation_countdown -= 1
            index += 1
            continue
        if negation_countdown:
            weight = _negate(weight)
            negation_countdown -= 1
        matched.append((label, weight))
        index += phrase_length

    if not matched:
        return EventSentiment(score=None, matched_terms=())
    # Weight each term by its own magnitude rather than averaging equally: a
    # decisive word should not be watered down by whatever mild vocabulary
    # happened to appear beside it, and a long article should still not
    # outscore a sharp headline by repeating itself.
    magnitude = sum(abs(weight) for _, weight in matched)
    score = sum(weight * abs(weight) for _, weight in matched) / magnitude
    return EventSentiment(
        score=max(-1.0, min(1.0, round(score, 6))),
        matched_terms=tuple(matched),
    )


def _negate(weight: float) -> float:
    """Apply a negator to a term without turning bad news into good news.

    Denying a positive claim is negative: "did not beat estimates" is a miss.
    Denying a negative one is not positive — a company that denies fraud is
    still a company answering fraud allegations — so the term is damped toward
    neutral instead of flipped. Flipping it made "denies fraud" the most
    bullish reading this lexicon could produce.
    """

    return -weight if weight > 0 else weight * 0.5


def _longest_phrase(
    tokens: list[str], index: int
) -> tuple[int, float | None, str]:
    for length in range(min(_MAX_PHRASE, len(tokens) - index), 1, -1):
        candidate = tuple(tokens[index : index + length])
        weight = _PHRASES.get(candidate)
        if weight is not None:
            return length, weight, " ".join(candidate)
    return 1, None, tokens[index]
