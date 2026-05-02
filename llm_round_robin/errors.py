"""Typed errors so the runner can decide whether to fall through or bail.

Generic ``RuntimeError("model unavailable, trying next...")`` swallows
critical signal. With these typed errors the runner can:

  - keep walking the ladder on ``ModelNotFound`` / ``EndpointMismatch`` /
    ``PermissionDenied`` / ``RateLimited`` (next rung is the right move),
  - bail loudly on ``TransportError`` (DNS / TLS / connection refused
    won't be fixed by a different model), and
  - log the typed reason so a human reading the transcript knows whether
    the consult landed on a fallback model because of stale ladder
    entries or because the upstream provider is having a bad day.
"""

from __future__ import annotations


class ConsultError(RuntimeError):
    """Base class for all round-robin consult errors.

    Carries the provider, model that was attempted, and the raw error
    body (truncated) so transcripts can show the operator what actually
    happened on each rung.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        message: str,
        http_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.http_code = http_code
        super().__init__(f"[{provider}] {model} -> {message}")


class ModelNotFound(ConsultError):
    """The provider does not know this model name.

    Typical body hints: ``"model"``, ``"not_found"``. Falls through to
    the next rung in the ladder.
    """


class EndpointMismatch(ConsultError):
    """The model exists but is scoped to a different endpoint.

    Common case: newer OpenAI ``gpt-5.x`` / ``-pro`` / reasoning models
    are scoped to ``/v1/responses`` only and 4xx on ``/v1/chat/completions``.
    Body hints: ``"endpoint"``, ``"responses"``, ``"support"``.
    Falls through; the runner should log the hint so the operator can
    update the ladder entry's ``endpoint`` tag.
    """


class PermissionDenied(ConsultError):
    """HTTP 403 — account does not have access to this model.

    Falls through. Operator either upgrades the plan or removes the
    rung from the ladder.
    """


class RateLimited(ConsultError):
    """HTTP 429 — try the next (cheaper) rung."""


class TransportError(ConsultError):
    """DNS / TLS / connection refused / timeout.

    The runner should NOT walk to the next rung — a different model on
    the same provider hits the same network. Re-raise.
    """


class AuthError(ConsultError):
    """HTTP 401 — bad/expired API key. Re-raise; next rung won't help."""


class LadderExhausted(RuntimeError):
    """Every rung in the ladder failed; nothing more to try."""

    def __init__(self, provider: str, attempts: list[ConsultError]) -> None:
        self.provider = provider
        self.attempts = attempts
        super().__init__(
            f"[{provider}] every rung exhausted ({len(attempts)} attempts)"
        )
