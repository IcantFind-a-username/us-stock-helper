"""The one factor this system refuses to guess at, and the reason why.

This reading is permanently unavailable. That is a decision, not a gap
waiting to be closed by whoever next has an afternoon, and it is recorded in
code so that the "why is coverage not 100%" question has an answer at the
point where the answer is needed rather than in a document nobody opens.

An abstention is deliberately shaped exactly like a failed fetch: no value at
all. The alternative — a plausible-looking number with a weak source behind
it — is worse than a hole, because a hole is visible in ``factor_coverage``
and a bad number is not.

institutional_flow used to abstain here too, for exactly the reason
``_GEOPOLITICS_DETAIL``-style prose would have given: SEC Form 13F is
quarterly with a 45-day filing lag, and nothing free and timelier existed.
That stopped being true once the market gateway started serving intraday
order-size participation and dated holdings disclosures with their own
point-in-time boundaries — see
analysis_api/institutional_flow_provider.py, which blends the two with
their own honest-absence handling rather than through this module's
permanent "no" (2026-08-15, institutional-capital factor wiring).
"""

from __future__ import annotations

from datetime import datetime

from .base import (
    FACTOR_GEOPOLITICS,
    FactorReading,
    FactorUnavailable,
)


GEOPOLITICS_ABSTENTION_VERSION = "geopolitics-abstained-v1"

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


def geopolitics_reading(*, as_of: datetime) -> FactorReading:
    return FactorReading.unavailable(
        factor=FACTOR_GEOPOLITICS,
        method_version=GEOPOLITICS_ABSTENTION_VERSION,
        as_of=as_of,
        reason=FactorUnavailable.NO_QUALIFIED_SOURCE,
        detail=_GEOPOLITICS_DETAIL,
    )
