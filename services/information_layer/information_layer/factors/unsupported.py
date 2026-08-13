"""The two factors this system refuses to guess at, and the reasons why.

Both readings here are permanently unavailable. That is a decision, not a
gap waiting to be closed by whoever next has an afternoon, and it is recorded
in code so that the "why is coverage not 100%" question has an answer at the
point where the answer is needed rather than in a document nobody opens.

An abstention is deliberately shaped exactly like a failed fetch: no value at
all. The alternative — a plausible-looking number with a weak source behind
it — is worse than a hole, because a hole is visible in ``factor_coverage``
and a bad number is not.
"""

from __future__ import annotations

from datetime import datetime

from .base import (
    FACTOR_GEOPOLITICS,
    FACTOR_INSTITUTIONAL_FLOW,
    FactorReading,
    FactorUnavailable,
)


INSTITUTIONAL_FLOW_ABSTENTION_VERSION = "institutional-flow-abstained-v1"
GEOPOLITICS_ABSTENTION_VERSION = "geopolitics-abstained-v1"

_INSTITUTIONAL_FLOW_DETAIL = (
    "No free source reports institutional flow on a timescale this system "
    "trades on. SEC Form 13F is the only public holdings disclosure, and it "
    "is quarterly with a 45 day filing deadline: by the time a position "
    "appears it is between 45 and 135 days old, and it says what a manager "
    "held on one date, not what they were doing. Feeding that into a "
    "short-horizon score would attach a stale quarterly snapshot to a signal "
    "read as current. FINRA's daily short-sale volume is timely but measures "
    "market-maker hedging as much as directional conviction, so labelling it "
    "institutional flow would be a mislabelled number rather than a missing "
    "one. This factor stays unavailable until a same-week flow source exists, "
    "or until the scorer can accept a factor that declares its own horizon."
)

_GEOPOLITICS_DETAIL = (
    "No free, structured, machine-readable source turns geopolitical events "
    "into a number this system could defend. The candidates are news text, "
    "and scoring headline counts or keyword sentiment would produce a "
    "confident-looking series driven by how much a topic was written about "
    "rather than what happened. Geopolitical events already reach the score "
    "through cited evidence and market sentiment, where they carry their "
    "source and can be read; a separate synthetic index would double-count "
    "them and hide their provenance."
)


def institutional_flow_reading(*, as_of: datetime) -> FactorReading:
    return FactorReading.unavailable(
        factor=FACTOR_INSTITUTIONAL_FLOW,
        method_version=INSTITUTIONAL_FLOW_ABSTENTION_VERSION,
        as_of=as_of,
        reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
        detail=_INSTITUTIONAL_FLOW_DETAIL,
    )


def geopolitics_reading(*, as_of: datetime) -> FactorReading:
    return FactorReading.unavailable(
        factor=FACTOR_GEOPOLITICS,
        method_version=GEOPOLITICS_ABSTENTION_VERSION,
        as_of=as_of,
        reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
        detail=_GEOPOLITICS_DETAIL,
    )
