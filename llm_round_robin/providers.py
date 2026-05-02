"""Provider call adapters: OpenAI, Gemini, NVIDIA NIM.

Each ``call_<provider>`` function:

  - takes the rung-list (already ladder-pruned and capability-filtered),
    the prompt, the system prompt, the API key, and an injectable
    ``fetcher`` for tests,
  - walks the ladder, dispatching to the right endpoint for each
    rung based on its ``endpoint`` tag,
  - on each failure, raises a typed error from ``errors.py``,
  - returns ``(model_id, response_text, attempts)`` on first success.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from .config import ModelEntry
from .errors import (
    AuthError,
    ConsultError,
    EndpointMismatch,
    LadderExhausted,
    ModelNotFound,
    PermissionDenied,
    RateLimited,
    TransportError,
)


CALL_TIMEOUT_SEC = 180

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _default_fetcher(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_SEC) as resp:
        return resp.read()


# ----- OpenAI -------------------------------------------------------

def _extract_responses_text(data: dict) -> str:
    """Pull assistant text out of an OpenAI Responses API body.

    Tries the convenience ``output_text`` first; falls back to walking
    the structured ``output[].content[]`` list for ``output_text`` /
    ``text`` parts. Returns ``""`` if nothing usable found.
    """
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("output_text", "text"):
                txt = part.get("text")
                if isinstance(txt, str):
                    chunks.append(txt)
    return "\n".join(c for c in chunks if c)


def _classify_openai_error(
    code: int, body_lower: str, model: str
) -> ConsultError:
    # Endpoint-mismatch hints are checked FIRST because the body
    # often mentions "model" alongside the endpoint complaint
    # (e.g. "this model is not supported on the chat/completions
    # endpoint"). A naive "model substring" match would otherwise
    # mis-classify endpoint mismatches as ModelNotFound.
    if code == 400 and (
        "endpoint" in body_lower
        or "/responses" in body_lower
        or "chat/completions" in body_lower
        or "not supported on" in body_lower
    ):
        return EndpointMismatch(
            "openai",
            model,
            f"HTTP {code}: model is scoped to a different endpoint",
            http_code=code,
        )
    if code in (404, 400) and (
        "model" in body_lower
        or "not_found" in body_lower
        or "does not exist" in body_lower
    ):
        return ModelNotFound(
            "openai",
            model,
            f"HTTP {code}: model not recognized",
            http_code=code,
        )
    if code == 401:
        return AuthError(
            "openai",
            model,
            f"HTTP {code}: bad/expired API key",
            http_code=code,
        )
    if code == 403:
        return PermissionDenied(
            "openai",
            model,
            f"HTTP {code}: account lacks access to this model",
            http_code=code,
        )
    if code == 429:
        return RateLimited(
            "openai",
            model,
            f"HTTP {code}: rate limit / quota",
            http_code=code,
        )
    return ConsultError(
        "openai",
        model,
        f"HTTP {code}: unhandled (body: {body_lower[:140]!r})",
        http_code=code,
    )


def call_openai(
    rungs: list[ModelEntry],
    prompt: str,
    system: str,
    api_key: str,
    *,
    fetcher: Callable[[urllib.request.Request], bytes] | None = None,
) -> tuple[str, str, list[ConsultError]]:
    """Walk ``rungs`` and return ``(model_id, text, attempts)``.

    For each rung, dispatch by ``rung.endpoint``:

      * ``responses`` or ``both`` â†’ POST ``/v1/responses`` with a
        ``reasoning.effort`` knob set on gpt-5.x / codex variants
      * ``chat`` â†’ POST ``/v1/chat/completions`` (legacy schema)

    Raises ``LadderExhausted`` if every rung fails. Raises
    ``TransportError`` / ``AuthError`` immediately (next rung won't
    help).
    """
    fetcher = fetcher or _default_fetcher
    attempts: list[ConsultError] = []
    for rung in rungs:
        try:
            text = _call_openai_one(rung, prompt, system, api_key, fetcher)
            return rung.id, text, attempts
        except (ModelNotFound, EndpointMismatch, PermissionDenied, RateLimited) as err:
            attempts.append(err)
            continue
        except (TransportError, AuthError):
            raise
        except ConsultError as err:
            # Unhandled HTTP code or empty response â€” log and bail; the
            # next rung might also be wrong but at least we've exposed it.
            attempts.append(err)
            continue
    raise LadderExhausted("openai", attempts)


def _call_openai_one(
    rung: ModelEntry,
    prompt: str,
    system: str,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> str:
    use_responses = rung.endpoint in ("responses", "both")
    if use_responses:
        body_dict: dict = {
            "model": rung.id,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        # Reasoning models accept the reasoning.effort knob; older
        # models accept temperature.
        if "reasoning" in rung.capabilities:
            body_dict["reasoning"] = {"effort": "medium"}
        else:
            body_dict["temperature"] = 0.4
        url = OPENAI_RESPONSES_URL
    else:
        body_dict = {
            "model": rung.id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 4096,
        }
        url = OPENAI_CHAT_URL
    body = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        raw = fetcher(req)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise _classify_openai_error(e.code, body_text.lower(), rung.id) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TransportError(
            "openai", rung.id, f"{type(e).__name__}: {e}"
        ) from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ConsultError(
            "openai",
            rung.id,
            f"could not parse response body: {e}",
        ) from e
    if use_responses:
        text = _extract_responses_text(data)
    else:
        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise ConsultError(
            "openai",
            rung.id,
            "empty response (parser couldn't find text)",
        )
    return text


# ----- Gemini -------------------------------------------------------

def call_gemini(
    rungs: list[ModelEntry],
    prompt: str,
    system: str,
    api_key: str,
    *,
    fetcher: Callable[[urllib.request.Request], bytes] | None = None,
) -> tuple[str, str, list[ConsultError]]:
    fetcher = fetcher or _default_fetcher
    attempts: list[ConsultError] = []
    for rung in rungs:
        try:
            text = _call_gemini_one(rung, prompt, system, api_key, fetcher)
            return rung.id, text, attempts
        except (ModelNotFound, RateLimited, PermissionDenied) as err:
            attempts.append(err)
            continue
        except TransportError:
            raise
        except ConsultError as err:
            attempts.append(err)
            continue
    raise LadderExhausted("gemini", attempts)


def _call_gemini_one(
    rung: ModelEntry,
    prompt: str,
    system: str,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> str:
    url = GEMINI_URL_TEMPLATE.format(model=rung.id, key=api_key)
    body = json.dumps(
        {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 8192,
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        raw = fetcher(req)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        bl = body_text.lower()
        if e.code in (404, 400) and (
            "model" in bl or "not found" in bl
        ):
            raise ModelNotFound(
                "gemini", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        if e.code == 429:
            raise RateLimited(
                "gemini", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        if e.code == 403:
            raise PermissionDenied(
                "gemini", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        raise ConsultError(
            "gemini", rung.id, f"HTTP {e.code}: {body_text[:140]}"
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TransportError(
            "gemini", rung.id, f"{type(e).__name__}: {e}"
        ) from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ConsultError(
            "gemini", rung.id, f"could not parse body: {e}"
        ) from e
    cands = data.get("candidates") or []
    if not cands:
        raise ConsultError(
            "gemini", rung.id, "empty candidates in response"
        )
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ConsultError("gemini", rung.id, "empty text in response")
    return text


# ----- NVIDIA -------------------------------------------------------

def call_nvidia(
    rungs: list[ModelEntry],
    prompt: str,
    system: str,
    api_key: str,
    *,
    fetcher: Callable[[urllib.request.Request], bytes] | None = None,
) -> tuple[str, str, list[ConsultError]]:
    fetcher = fetcher or _default_fetcher
    attempts: list[ConsultError] = []
    for rung in rungs:
        try:
            text = _call_nvidia_one(rung, prompt, system, api_key, fetcher)
            return rung.id, text, attempts
        except (ModelNotFound, RateLimited, PermissionDenied) as err:
            attempts.append(err)
            continue
        except TransportError:
            raise
        except ConsultError as err:
            attempts.append(err)
            continue
    raise LadderExhausted("nvidia", attempts)


def _call_nvidia_one(
    rung: ModelEntry,
    prompt: str,
    system: str,
    api_key: str,
    fetcher: Callable[[urllib.request.Request], bytes],
) -> str:
    body = json.dumps(
        {
            "model": rung.id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 4096,
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        NVIDIA_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        raw = fetcher(req)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        bl = body_text.lower()
        if e.code in (400, 404) and (
            "model" in bl or "not_found" in bl or "not found" in bl
        ):
            raise ModelNotFound(
                "nvidia", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        if e.code == 429:
            raise RateLimited(
                "nvidia", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        if e.code == 403:
            raise PermissionDenied(
                "nvidia", rung.id, f"HTTP {e.code}", http_code=e.code
            ) from e
        raise ConsultError(
            "nvidia", rung.id, f"HTTP {e.code}: {body_text[:140]}"
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TransportError(
            "nvidia", rung.id, f"{type(e).__name__}: {e}"
        ) from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ConsultError(
            "nvidia", rung.id, f"could not parse body: {e}"
        ) from e
    choices = data.get("choices") or []
    if not choices:
        raise ConsultError(
            "nvidia", rung.id, "empty choices in response"
        )
    content = (choices[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise ConsultError("nvidia", rung.id, "empty content in response")
    return content
