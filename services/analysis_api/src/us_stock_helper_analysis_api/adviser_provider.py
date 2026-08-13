"""The optional model layer, held at arm's length from the decision chain.

Three constraints shape this file.

The model costs money — roughly ten cents for one council brief — so nothing
here runs unless the request asked for it, and whatever it spends comes back
in the answer as a measurement rather than an estimate.

The SDK is optional. ``adviser_llm`` imports ``anthropic``, which a deployment
may not have installed and which a lockdown may not allow. Every import of it
is deferred into the request path, so a service that cannot load it still
starts, still serves every deterministic route, and reports the adviser as
unavailable instead of failing to come up at all.

Degradation is stated, never implied. "The model was unreachable" and "the
council looked and found nothing" are different claims, and a null with no
reason attached lets a reader mistake the first for the second.

Read-only by construction: this dials out to a text API and has no path to a
broker or an account.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence


# The three states a block can be in. They are kept apart all the way to the
# screen because the phone renders each of them differently.
NOT_REQUESTED = "not-requested"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"

NOT_REQUESTED_REASON = (
    "本次请求没有调用模型；只有用户对单只股票明确点击后才会调用。"
)
NEWS_ONLY_COUNCIL_REASON = (
    "本次仅请求新闻解读，没有召开 13 席顾问会诊，因此没有产生会诊 token。"
)
NO_DECISION_REASON = (
    "The decision chain reached no conclusion, so no council was convened and "
    "nothing was spent."
)
_SDK_MISSING_REASON = (
    "The adviser layer is not installed on this deployment (the model SDK "
    "could not be imported), so no interpretation was produced."
)
_UNEXPECTED_FAILURE_REASON = (
    "The adviser layer failed in a way this service will not repeat verbatim, "
    "because such messages can carry the outbound credential. No "
    "interpretation was produced."
)

# What a credential looks like once it has escaped into a message. Matching on
# the prefix rather than on the configured value catches a key this process was
# never handed — a proxy's, say — which is exactly the case a whitelist of
# known secrets would miss.
_CREDENTIAL_MARKERS = ("sk-ant", "x-api-key", "authorization")


class AdviserSource(Protocol):
    """What the analysis service is allowed to ask of the model layer."""

    def brief(
        self,
        *,
        symbol: str,
        horizon: str,
        as_of: datetime,
        evidence: Sequence[Any],
        baseline_score: float,
        baseline_direction: str,
        hard_gates: Sequence[Any],
        mode: str = "full",
    ) -> "AdviserBriefing": ...


@dataclass(frozen=True, slots=True)
class AdviserBriefing:
    """Two blocks and a receipt, each already shaped for the wire.

    ``news`` and ``council`` always carry a status and a reason; only their
    ``value`` may be null. That is the whole point: a block with no value and
    no reason is indistinguishable from a model that had nothing to say.
    """

    news: dict[str, Any]
    council: dict[str, Any]
    usage: dict[str, Any] | None
    notes: tuple[str, ...] = ()


def _block(
    status: str, reason: str | None, value: dict[str, Any] | None
) -> dict[str, Any]:
    # Every reason leaving this module goes through one redaction point. Some
    # of them are built out of text this service did not write — model output,
    # SDK failures — and a second, unredacted exit would be enough.
    return {
        "status": status,
        "reason": None if reason is None else redact(reason),
        "value": value,
    }


def not_requested() -> AdviserBriefing:
    """The default answer: nothing was called, and the reader is told so."""

    return AdviserBriefing(
        news=_block(NOT_REQUESTED, NOT_REQUESTED_REASON, None),
        council=_block(NOT_REQUESTED, NOT_REQUESTED_REASON, None),
        usage=None,
    )


def unavailable(reason: str) -> AdviserBriefing:
    return AdviserBriefing(
        news=_block(UNAVAILABLE, reason, None),
        council=_block(UNAVAILABLE, reason, None),
        usage=None,
    )


def _news_only_council() -> dict[str, Any]:
    return _block(NOT_REQUESTED, NEWS_ONLY_COUNCIL_REASON, None)


def unavailable_for_mode(mode: str, reason: str) -> AdviserBriefing:
    if mode == "news":
        return AdviserBriefing(
            news=_block(UNAVAILABLE, reason, None),
            council=_news_only_council(),
            usage=None,
        )
    return unavailable(reason)


def redact(reason: str) -> str:
    """Withhold any message that looks like it is carrying a credential.

    Blanking the whole message rather than the matched substring: a partial
    redaction still publishes the surrounding text, and the surrounding text of
    an authentication failure is where the header lives.
    """

    lowered = reason.casefold()
    if any(marker in lowered for marker in _CREDENTIAL_MARKERS):
        return _UNEXPECTED_FAILURE_REASON
    return reason


@dataclass(frozen=True, slots=True)
class LlmAdviserProvider:
    """Builds the adviser on demand and turns its answer into JSON.

    ``client`` exists so a test can drive the real adviser without a network,
    and ``environ`` so it can drive the real credential check without touching
    the process environment. Neither is a production seam: the deployed path
    passes neither and reads ANTHROPIC_API_KEY from the environment, where the
    value stays — it is never logged, never put in an exception, and never put
    in a response.
    """

    client: Any | None = None
    config: Any | None = None
    environ: Mapping[str, str] | None = None
    sleep: Callable[[float], None] = time.sleep

    def brief(
        self,
        *,
        symbol: str,
        horizon: str,
        as_of: datetime,
        evidence: Sequence[Any],
        baseline_score: float,
        baseline_direction: str,
        hard_gates: Sequence[Any],
        mode: str = "full",
    ) -> AdviserBriefing:
        if mode not in {"news", "full"}:
            raise ValueError("adviser mode must be news or full")
        try:
            # Deferred on purpose. See the module docstring: a top-level import
            # of the SDK would take the whole service down on a deployment that
            # does not have it.
            import adviser_llm
        except ImportError:
            return unavailable_for_mode(mode, _SDK_MISSING_REASON)

        try:
            packet, skipped = _build_packet(
                adviser_llm,
                symbol=symbol,
                horizon=horizon,
                as_of=as_of,
                evidence=evidence,
            )
        except ValueError as error:
            return unavailable_for_mode(
                mode,
                "No citable evidence was available at the decision cutoff, so "
                f"the model was not asked to interpret anything: {error}"
            )

        notes: list[str] = []
        if skipped:
            # Silently dropping them would let a thin packet look like a quiet
            # news window, which is the one thing the evidence layer exists to
            # prevent.
            notes.append(
                f"{skipped} evidence item(s) carried no quotable text or no "
                "usable link and were left out of the adviser's packet."
            )

        try:
            service = self._adviser(adviser_llm)
            news = service.interpret_news(packet)
            council = (
                service.convene_council(
                    packet,
                    baseline_score=baseline_score,
                    baseline_direction=baseline_direction,
                    hard_gates=tuple(hard_gates),
                )
                if mode == "full"
                else None
            )
            usage = _usage(service.usage, _model_name(service))
        except Exception:  # noqa: BLE001 - see the reason constant
            # The adviser degrades its own known failures into an outcome; what
            # is left here is the unexpected kind, whose message may quote the
            # request that carried the credential. It is replaced, not
            # forwarded, and never logged.
            return AdviserBriefing(
                news=_block(UNAVAILABLE, _UNEXPECTED_FAILURE_REASON, None),
                council=(
                    _block(UNAVAILABLE, _UNEXPECTED_FAILURE_REASON, None)
                    if mode == "full"
                    else _news_only_council()
                ),
                usage=None,
                notes=tuple(notes),
            )

        return AdviserBriefing(
            news=_outcome_block(news, _interpretation),
            council=(
                _outcome_block(council, _verdict)
                if council is not None
                else _news_only_council()
            ),
            usage=usage,
            notes=tuple(notes),
        )

    def _adviser(self, adviser_llm: Any) -> Any:
        config = self.config or adviser_llm.AdviserLlmConfig()
        if self.client is not None:
            return adviser_llm.AdviserLlm(self.client, config, sleep=self.sleep)
        return adviser_llm.AdviserLlm.from_environment(
            config, environ=self.environ, sleep=self.sleep
        )


def provider_from_environment() -> AdviserSource:
    """The deployed adviser. Constructing it imports nothing by itself."""

    return LlmAdviserProvider()


def _model_name(service: Any) -> str | None:
    config = getattr(service, "config", None)
    model = getattr(config, "model", None)
    return model if isinstance(model, str) and model.strip() else None


def _outcome_block(
    outcome: Any, render: Callable[[Any], dict[str, Any]]
) -> dict[str, Any]:
    if not outcome.available:
        return _block(
            UNAVAILABLE,
            outcome.unavailable_reason or _UNEXPECTED_FAILURE_REASON,
            None,
        )
    return _block(AVAILABLE, None, render(outcome.value))


def _build_packet(
    adviser_llm: Any,
    *,
    symbol: str,
    horizon: str,
    as_of: datetime,
    evidence: Sequence[Any],
) -> tuple[Any, int]:
    """Freeze the collected evidence into the only thing the model may read.

    An event this cannot represent — no summary to quote, a link that is not a
    plain HTTP(S) URL — is counted and dropped rather than patched up. Inventing
    a body would hand the model a quotable sentence nobody published.
    """

    items = []
    skipped = 0
    for event in evidence:
        try:
            items.append(_evidence_item(adviser_llm, event))
        except (ValueError, TypeError, AttributeError):
            skipped += 1
    packet = adviser_llm.build_packet(
        symbol=symbol, horizon=horizon, as_of=as_of, items=items
    )
    return packet, skipped


def _evidence_item(adviser_llm: Any, event: Any) -> Any:
    return adviser_llm.EvidenceItem(
        id=event.event_id,
        headline=event.headline,
        body=event.summary,
        url=event.provenance.canonical_url,
        publisher=event.provenance.publisher_name,
        available_at=event.available_at,
        received_at=event.retrieved_at,
        symbols=tuple(symbol for symbol, _relevance in event.symbol_relevance),
    )


def _citation(citation: Any) -> dict[str, Any]:
    return {
        "evidenceId": citation.evidence_id,
        # The quote is the model's, verified to appear verbatim in the source;
        # every other field here is read back off our own frozen record, so a
        # fabricated link cannot reach the screen.
        "quote": citation.quote,
        "url": citation.url,
        "publisher": citation.publisher,
        "availableAt": _iso(citation.available_at),
        "isCounterEvidence": citation.is_counter_evidence,
    }


def _conclusion(conclusion: Any) -> dict[str, Any]:
    return {
        "statement": conclusion.statement,
        "confidence": conclusion.confidence,
        "citations": [_citation(item) for item in conclusion.citations],
        "counterEvidence": [_citation(item) for item in conclusion.counter_evidence],
    }


def _interpretation(interpretation: Any) -> dict[str, Any]:
    return {
        "headlineSummary": interpretation.headline_summary,
        "crossSourceReading": interpretation.cross_source_reading,
        "investmentImpact": [
            _conclusion(item) for item in interpretation.investment_impact
        ],
        "unknowns": list(interpretation.unknowns),
    }


def _verdict(verdict: Any) -> dict[str, Any]:
    return {
        "summary": verdict.brief.summary,
        "opinions": [
            {
                "frameworkId": opinion.framework_id,
                "displayName": opinion.display_name,
                "stance": opinion.stance,
                "blindSpot": opinion.blind_spot_note,
                "conclusions": [
                    _conclusion(item) for item in opinion.conclusions
                ],
            }
            for opinion in verdict.brief.opinions
        ],
        "baselineScore": verdict.baseline_score,
        "adjustedScore": verdict.adjusted_score,
        "scoreAdjustment": verdict.score_adjustment,
        # The council never overrides the objective call; it moves the score
        # inside a published cap and is voided entirely by any hard gate.
        "objectiveDirection": verdict.objective_direction,
        "actionable": verdict.actionable,
        "blockedBy": [gate.value for gate in verdict.blocked_by],
        "disclaimer": verdict.disclaimer,
    }


def _usage(usage: Any, model: str | None) -> dict[str, Any] | None:
    # None means no call reported what it spent. Zeros would claim a call was
    # measured and cost nothing, which is a different statement.
    if usage is None:
        return None
    return {
        "model": model,
        "inputTokens": usage.input_tokens,
        "outputTokens": usage.output_tokens,
        "cacheCreationInputTokens": usage.cache_creation_input_tokens,
        "cacheReadInputTokens": usage.cache_read_input_tokens,
        # Six decimals is a ten-thousandth of a cent: enough to add up honestly
        # over a month, short of publishing float noise as precision.
        "costUsd": round(usage.cost_usd(), 6),
    }


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
