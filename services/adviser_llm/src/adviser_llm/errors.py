"""Failure modes of the adviser layer, kept distinct so callers can react."""

from __future__ import annotations


class AdviserLlmError(RuntimeError):
    """Base class for every refusal this layer can raise."""


class MissingCredentialError(AdviserLlmError):
    """The API key environment variable is absent or blank."""


class LlmUnavailableError(AdviserLlmError):
    """The model could not be reached, or answered nothing usable.

    Carries the attempt count so the caller can tell a single transport blip
    from a sustained outage instead of guessing from the message text.
    """

    def __init__(self, reason: str, *, attempts: int) -> None:
        if attempts < 0:
            raise ValueError("attempts cannot be negative")
        super().__init__(f"{reason}（已尝试 {attempts} 次）")
        self.reason = reason
        self.attempts = attempts


class TraceabilityError(AdviserLlmError):
    """A conclusion cannot be pointed back at a frozen evidence entry."""


class FabricatedFactError(AdviserLlmError):
    """A conclusion asserts something the supplied evidence does not contain."""
