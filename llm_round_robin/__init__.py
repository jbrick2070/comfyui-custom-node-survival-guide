"""llm_round_robin — keep your AI agent's LLM consults from rotting silently.

This package is a drop-in addon for ComfyUI custom-node authors who let an
AI coding agent (Claude Code, Codex, Cursor, ChatGPT in agent mode, etc.)
call out to ChatGPT / Gemini / NVIDIA NIM for second opinions on their code.

Hardcoded model lists go stale on a months-not-years cadence. The addon
solves three convergent failure modes (model name drift, endpoint drift,
aliasing pitfalls) by:

  - probing /v1/models at startup and pruning the configured ladder to
    what the API key actually has access to,
  - dispatching to the right endpoint per model (Responses vs Chat),
  - tagging each model with capability flags (text/vision/tools/reasoning)
    so callers can express a need instead of a vendor preference,
  - logging typed error reasons (model_not_found, endpoint_mismatch,
    permission, rate-limit) on every fall-through.

See ``README.md`` next to this file and the ``llm_round_robin_explainer.md``
under ``docs/`` for the full design rationale.
"""

from __future__ import annotations

from .config import (
    Ladder,
    ModelEntry,
    LadderStaleError,
    load_ladders,
    needs_match,
)
from .env import read_env_var
from .errors import (
    ConsultError,
    EndpointMismatch,
    ModelNotFound,
    PermissionDenied,
    RateLimited,
    TransportError,
)
from .probe import LiveProbe, probe_provider
from .runner import RoundRobinRunner, RoundResult

__all__ = [
    "Ladder",
    "ModelEntry",
    "LadderStaleError",
    "load_ladders",
    "needs_match",
    "read_env_var",
    "ConsultError",
    "EndpointMismatch",
    "ModelNotFound",
    "PermissionDenied",
    "RateLimited",
    "TransportError",
    "LiveProbe",
    "probe_provider",
    "RoundRobinRunner",
    "RoundResult",
]
