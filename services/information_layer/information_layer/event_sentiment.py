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


SENTIMENT_LEXICON_VERSION = "financial-lexicon-negation-v1"

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
    "raised": 0.6,
    "raises": 0.6,
    "upgraded": 0.7,
    "upgrade": 0.6,
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
    "cut": -0.6,
    "cuts": -0.6,
    "lowered": -0.6,
    "downgraded": -0.7,
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
    for token in tokens:
        if token in _CLAUSE_BREAK or token == "--" or token == "—":
            negation_countdown = 0
            continue
        if token in _NEGATORS:
            negation_countdown = _NEGATION_WINDOW
            continue
        weight = _LEXICON.get(token)
        if weight is None:
            if negation_countdown:
                negation_countdown -= 1
            continue
        if negation_countdown:
            weight = -weight
            negation_countdown = 0
        matched.append((token, weight))

    if not matched:
        return EventSentiment(score=None, matched_terms=())
    total = sum(weight for _, weight in matched)
    # Average rather than sum: a long article should not outscore a decisive
    # headline merely by repeating itself.
    score = total / len(matched)
    return EventSentiment(
        score=max(-1.0, min(1.0, round(score, 6))),
        matched_terms=tuple(matched),
    )
