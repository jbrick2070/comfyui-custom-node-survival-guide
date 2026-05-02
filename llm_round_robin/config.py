"""Ladder + capability tagging loaded from ``config/ladders.yaml``.

The config file is the single place a user maintains. Adding a new
model means editing one YAML entry — no Python edits, no rebuild,
no restart of the calling agent.

Schema (``config/ladders.yaml``)::

    last_reviewed: 2026-05-01      # ISO-8601 date; staleness alarm
    providers:
      openai:
        endpoint_default: responses
        models:
          - id: gpt-5.5
            endpoint: responses     # responses | chat | both
            capabilities: [text, tools, reasoning]
          - id: gpt-4o-mini
            endpoint: chat
            capabilities: [text]
      gemini:
        endpoint_default: generate_content
        models:
          - id: gemini-3.1-pro-preview
            capabilities: [text, vision, tools, reasoning]
      nvidia:
        endpoint_default: chat
        models:
          - id: nvidia/llama-3.3-nemotron-super-49b-v1.5
            capabilities: [text, tools, reasoning]

If PyYAML isn't installed, a tiny built-in parser handles the documented
shape (no anchors, no fancy YAML). Fail-soft so the addon works on
fresh / minimal Python installs.
"""

from __future__ import annotations

import dataclasses
import datetime
import os
import re
from pathlib import Path
from typing import Any, Iterable


# ----- canonical capability vocabulary ------------------------------

CAPABILITIES = ("text", "vision", "tools", "reasoning")
ENDPOINTS = ("responses", "chat", "both", "generate_content")

DEFAULT_STALENESS_DAYS = 60


# ----- dataclasses --------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ModelEntry:
    """One rung of one provider's ladder."""

    id: str
    endpoint: str
    capabilities: tuple[str, ...]

    def supports(self, needs: Iterable[str]) -> bool:
        """True if every needed capability is present in this model."""
        return all(n in self.capabilities for n in needs)


@dataclasses.dataclass(frozen=True)
class Ladder:
    """All rungs for one provider, in fall-through order."""

    provider: str
    endpoint_default: str
    models: tuple[ModelEntry, ...]

    def filter_for_needs(self, needs: Iterable[str] | None) -> "Ladder":
        """Return a copy of the ladder containing only rungs that meet
        every capability in ``needs``. Order is preserved.

        ``needs=None`` (or empty) returns the ladder unchanged.
        """
        nlist = list(needs or ())
        if not nlist:
            return self
        kept = tuple(m for m in self.models if m.supports(nlist))
        return dataclasses.replace(self, models=kept)


class LadderStaleError(RuntimeWarning):
    """Raised (as a warning) when ``last_reviewed`` is older than the
    staleness threshold. The runner emits this at startup and continues
    so the consult still happens — but the operator gets a loud signal
    that the ladder needs a re-review.
    """


# ----- YAML loader (with stdlib fallback) ---------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse our ladders YAML.

    Tries PyYAML first; falls back to a tiny hand-rolled parser that
    only handles the documented shape (no anchors, no flow-style, only
    block scalars, lists, dicts of strings/dates/lists).
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _mini_yaml_parse(text)


def _mini_yaml_parse(text: str) -> dict[str, Any]:
    """A deliberately tiny YAML subset parser.

    Supports: top-level mapping, nested mappings, lists of strings,
    lists of mappings, scalars (strings, ints, ISO dates, bracketed
    lists like ``[text, tools]``). Preserves indentation. No flow-style
    mappings, no anchors, no merge keys.

    Why? We don't want to depend on PyYAML for a single config file.
    Most distros ship with PyYAML, so this fallback is very rarely hit;
    when it is, the file shape is constrained and known.
    """
    lines = [ln for ln in text.splitlines() if not _is_blank_or_comment(ln)]
    root: dict[str, Any] = {}
    _parse_block(lines, 0, 0, root)
    return root


_BLANK_OR_COMMENT = re.compile(r"^\s*(#.*)?$")


def _is_blank_or_comment(line: str) -> bool:
    return bool(_BLANK_OR_COMMENT.match(line))


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if not s:
        return ""
    if s.startswith("[") and s.endswith("]"):
        # bracketed flow list of bare scalars
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in inner.split(",")]
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return datetime.date.fromisoformat(s)
        except ValueError:
            return s
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "~", ""):
        return None
    return s


def _parse_block(
    lines: list[str], idx: int, indent: int, out: dict[str, Any]
) -> int:
    """Parse a mapping block at ``indent``. Returns next-index."""
    while idx < len(lines):
        line = lines[idx]
        if _indent_of(line) < indent:
            return idx
        if _indent_of(line) > indent:
            # shouldn't happen at this level
            idx += 1
            continue
        m = re.match(r"^(\s*)([^:#]+?):\s*(.*?)\s*$", line)
        if not m:
            idx += 1
            continue
        key = m.group(2).strip()
        value = m.group(3)
        if value:
            out[key] = _parse_scalar(value)
            idx += 1
            continue
        # block child — could be mapping or list
        idx += 1
        if idx >= len(lines):
            out[key] = {}
            return idx
        child_indent = _indent_of(lines[idx])
        if child_indent <= indent:
            out[key] = {}
            continue
        if lines[idx].lstrip().startswith("- "):
            seq: list[Any] = []
            idx = _parse_seq(lines, idx, child_indent, seq)
            out[key] = seq
        else:
            child: dict[str, Any] = {}
            idx = _parse_block(lines, idx, child_indent, child)
            out[key] = child
    return idx


def _parse_seq(
    lines: list[str], idx: int, indent: int, out: list[Any]
) -> int:
    while idx < len(lines):
        line = lines[idx]
        cur_indent = _indent_of(line)
        if cur_indent < indent:
            return idx
        stripped = line.lstrip()
        if not stripped.startswith("- "):
            return idx
        body = stripped[2:].rstrip()
        if ":" in body:
            # mapping element. Treat the rest of the line as the first
            # key of the mapping.
            entry: dict[str, Any] = {}
            head_match = re.match(r"^([^:#]+?):\s*(.*?)\s*$", body)
            if head_match:
                k = head_match.group(1).strip()
                v = head_match.group(2)
                entry[k] = _parse_scalar(v) if v else None
            idx += 1
            # subsequent indented lines (deeper than `- `) belong to
            # this entry. The element body indent is `indent + 2`.
            entry_indent = indent + 2
            while idx < len(lines):
                nxt = lines[idx]
                if _indent_of(nxt) < entry_indent:
                    break
                if nxt.lstrip().startswith("- "):
                    break
                idx = _parse_block(lines, idx, entry_indent, entry)
                break_now = False
                if idx < len(lines):
                    if _indent_of(lines[idx]) < entry_indent:
                        break_now = True
                    elif lines[idx].lstrip().startswith("- "):
                        break_now = True
                if break_now:
                    break
            out.append(entry)
        else:
            out.append(_parse_scalar(body))
            idx += 1
    return idx


# ----- public API ---------------------------------------------------

def load_ladders(
    config_path: str | os.PathLike | None = None,
    *,
    staleness_days: int = DEFAULT_STALENESS_DAYS,
) -> tuple[dict[str, Ladder], list[str]]:
    """Load + validate ``config/ladders.yaml``.

    Returns ``(ladders, warnings)`` where ``ladders`` is a mapping
    ``provider -> Ladder`` and ``warnings`` is a list of human-readable
    strings (empty when everything checks out, otherwise things like
    "ladder may be stale" or "model 'foo' has unknown capability").

    The runner is expected to print the warnings to stderr.
    """
    if config_path is None:
        config_path = (
            Path(__file__).resolve().parent / "config" / "ladders.yaml"
        )
    p = Path(config_path)
    if not p.is_file():
        raise FileNotFoundError(
            f"ladders config not found at {p!s}. Copy "
            f"config/ladders.yaml.example next to your install and "
            f"point --config at it."
        )
    raw = _load_yaml(p)
    warnings: list[str] = []

    last_reviewed = raw.get("last_reviewed")
    if isinstance(last_reviewed, datetime.date):
        age = (datetime.date.today() - last_reviewed).days
        if age > staleness_days:
            warnings.append(
                f"ladders.yaml last_reviewed={last_reviewed.isoformat()} "
                f"is {age} days old (>{staleness_days}). Re-verify model "
                f"names against provider docs and bump last_reviewed."
            )
    elif last_reviewed is None:
        warnings.append(
            "ladders.yaml has no `last_reviewed:` date — add one so the "
            "staleness alarm can warn you when the ladder rots."
        )

    providers_raw = raw.get("providers") or {}
    if not isinstance(providers_raw, dict):
        raise ValueError(
            "ladders.yaml must have a top-level `providers:` mapping."
        )

    ladders: dict[str, Ladder] = {}
    for provider_name, provider_block in providers_raw.items():
        if not isinstance(provider_block, dict):
            raise ValueError(
                f"providers.{provider_name} must be a mapping, got "
                f"{type(provider_block).__name__}."
            )
        endpoint_default = str(
            provider_block.get("endpoint_default") or "chat"
        )
        if endpoint_default not in ENDPOINTS:
            warnings.append(
                f"providers.{provider_name}.endpoint_default="
                f"{endpoint_default!r} is not in the canonical "
                f"vocabulary {ENDPOINTS}; treating as opaque string."
            )
        models_raw = provider_block.get("models") or []
        models: list[ModelEntry] = []
        for entry in models_raw:
            if not isinstance(entry, dict) or "id" not in entry:
                warnings.append(
                    f"providers.{provider_name}.models has a malformed "
                    f"entry without `id:` — skipping."
                )
                continue
            mid = str(entry["id"]).strip()
            endpoint = str(
                entry.get("endpoint") or endpoint_default
            ).strip()
            caps = entry.get("capabilities") or ["text"]
            if isinstance(caps, str):
                caps = [caps]
            cleaned: list[str] = []
            for c in caps:
                cs = str(c).strip()
                if cs not in CAPABILITIES:
                    warnings.append(
                        f"providers.{provider_name} model {mid!r} has "
                        f"unknown capability {cs!r}; keeping it but "
                        f"--needs filters won't match it."
                    )
                cleaned.append(cs)
            models.append(
                ModelEntry(
                    id=mid,
                    endpoint=endpoint,
                    capabilities=tuple(cleaned),
                )
            )
        if not models:
            warnings.append(
                f"providers.{provider_name} has zero models — provider "
                f"will be skipped at runtime."
            )
        ladders[provider_name] = Ladder(
            provider=provider_name,
            endpoint_default=endpoint_default,
            models=tuple(models),
        )

    return ladders, warnings


def needs_match(
    ladder: Ladder, needs: Iterable[str] | None
) -> Ladder:
    """Convenience wrapper for ``ladder.filter_for_needs``."""
    return ladder.filter_for_needs(needs)
