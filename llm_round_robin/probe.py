"""Probe ``GET /v1/models`` (or provider equivalent) and prune the
configured ladder to what the API key actually has access to.

Why probe at all? Because the ladder file you maintain is your *intent*,
not the truth. The truth changes silently — providers deprecate models,
your account loses access, regions roll out new variants. Probing once
at startup lets us:

  - drop dead rungs before we even try them (saves a round-trip per
    failed call), and
  - log the live set, so the operator can see which models the consult
    will actually use.

If the probe call itself fails (network down, key expired, transient
500), we DO NOT throw the ladder away — we fall back to the configured
ladder and warn loudly. A flaky probe shouldn't break a consult that
might still work on a known-good model.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.request
from typing import Callable

from .config import Ladder, ModelEntry


PROBE_TIMEOUT_SEC = 10


@dataclasses.dataclass(frozen=True)
class LiveProbe:
    """Outcome of one probe call.

    ``ok=True`` and ``live_ids`` populated → the runner can prune.
    ``ok=False`` and ``error`` populated → the runner should fall back
    to the configured ladder and log the error.
    """

    provider: str
    ok: bool
    live_ids: frozenset[str]
    error: str = ""


def probe_provider(
    ladder: Ladder,
    api_key: str,
    *,
    fetcher: Callable[[urllib.request.Request], bytes] | None = None,
) -> LiveProbe:
    """Hit the provider's models-listing endpoint and return a LiveProbe.

    ``fetcher`` is injected for tests so we can stub HTTP. In production
    leave it ``None`` to use ``urllib.request.urlopen``.
    """
    fetcher = fetcher or _default_fetcher
    if ladder.provider == "openai":
        return _probe_openai(ladder, api_key, fetcher)
    if ladder.provider == "gemini":
        return _probe_gemini(ladder, api_key, fetcher)
    if ladder.provider == "nvidia":
        return _probe_nvidia(ladder, api_key, fetcher)
    return LiveProbe(
        provider=ladder.provider,
        ok=False,
        live_ids=frozenset(),
        error=f"no probe implemented for provider {ladder.provider!r}",
    )


def _default_fetcher(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_SEC) as resp:
        return resp.read()


def _probe_openai(
    ladder: Ladder,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> LiveProbe:
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        body = fetcher(req)
    except urllib.error.HTTPError as e:
        return LiveProbe(
            provider="openai",
            ok=False,
            live_ids=frozenset(),
            error=f"HTTP {e.code} from /v1/models",
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return LiveProbe(
            provider="openai",
            ok=False,
            live_ids=frozenset(),
            error=f"{type(e).__name__}: {e}",
        )
    return _parse_openai_compatible(body, "openai")


def _probe_nvidia(
    ladder: Ladder,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> LiveProbe:
    req = urllib.request.Request(
        "https://integrate.api.nvidia.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        body = fetcher(req)
    except urllib.error.HTTPError as e:
        return LiveProbe(
            provider="nvidia",
            ok=False,
            live_ids=frozenset(),
            error=f"HTTP {e.code} from /v1/models",
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return LiveProbe(
            provider="nvidia",
            ok=False,
            live_ids=frozenset(),
            error=f"{type(e).__name__}: {e}",
        )
    return _parse_openai_compatible(body, "nvidia")


def _parse_openai_compatible(body: bytes, provider: str) -> LiveProbe:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return LiveProbe(
            provider=provider,
            ok=False,
            live_ids=frozenset(),
            error=f"could not parse /v1/models body: {e}",
        )
    items = data.get("data") or []
    ids = []
    for item in items:
        if isinstance(item, dict) and "id" in item:
            ids.append(str(item["id"]))
    if not ids:
        return LiveProbe(
            provider=provider,
            ok=False,
            live_ids=frozenset(),
            error="/v1/models returned an empty list",
        )
    return LiveProbe(
        provider=provider,
        ok=True,
        live_ids=frozenset(ids),
    )


def _probe_gemini(
    ladder: Ladder,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> LiveProbe:
    # Gemini's discovery endpoint returns models with a "name" field
    # like "models/gemini-3.1-pro-preview" — strip the prefix to match
    # our ladder entries.
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models?"
        f"key={api_key}"
    )
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        body = fetcher(req)
    except urllib.error.HTTPError as e:
        return LiveProbe(
            provider="gemini",
            ok=False,
            live_ids=frozenset(),
            error=f"HTTP {e.code} from /v1beta/models",
        )
    except (urllib.error.URLError, TimeoutError) as e:
        return LiveProbe(
            provider="gemini",
            ok=False,
            live_ids=frozenset(),
            error=f"{type(e).__name__}: {e}",
        )
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return LiveProbe(
            provider="gemini",
            ok=False,
            live_ids=frozenset(),
            error=f"could not parse /v1beta/models body: {e}",
        )
    items = data.get("models") or []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        if name.startswith("models/"):
            ids.append(name[len("models/") :])
        elif name:
            ids.append(name)
    if not ids:
        return LiveProbe(
            provider="gemini",
            ok=False,
            live_ids=frozenset(),
            error="/v1beta/models returned an empty list",
        )
    return LiveProbe(
        provider="gemini",
        ok=True,
        live_ids=frozenset(ids),
    )


def prune_ladder(ladder: Ladder, probe: LiveProbe) -> tuple[Ladder, list[ModelEntry]]:
    """Intersect the configured ladder with the probe's live set.

    Returns ``(pruned_ladder, dropped_entries)`` where ``dropped_entries``
    is the list of rungs the probe said are not available — useful for
    the runner to log so the operator sees what was pruned.

    If ``probe.ok`` is False, returns the ladder unchanged. The runner
    should warn but proceed.
    """
    if not probe.ok:
        return ladder, []
    kept: list[ModelEntry] = []
    dropped: list[ModelEntry] = []
    for m in ladder.models:
        if m.id in probe.live_ids:
            kept.append(m)
        else:
            dropped.append(m)
    pruned = dataclasses.replace(ladder, models=tuple(kept))
    return pruned, dropped
