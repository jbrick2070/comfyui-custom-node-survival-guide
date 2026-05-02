"""Round-robin runner: probe → prune → call each provider → synthesize.

Inputs the runner is happy with:

  - a question (str) and a topic name (str, used in output filenames),
  - a config-loaded ladders dict and any --needs filter,
  - a per-provider ``fetcher`` callable (for tests; defaults call urllib),
  - a per-provider API-key resolver.

Outputs:

  - per-round markdown files written to ``output_dir`` (00_question.md,
    01_<provider>.md, …, NN_synthesis.md, transcript.json)
  - returned ``RoundResult`` objects so a programmatic caller (e.g.
    a ComfyUI node, a custom AI agent) can decide what to do next.

This module is deliberately UI-agnostic — the CLI in ``__main__.py``
is one caller, but the runner can be imported from a ComfyUI node, a
test, or a CI script.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .config import Ladder
from .errors import ConsultError, LadderExhausted, TransportError
from .probe import LiveProbe, probe_provider, prune_ladder
from .providers import call_gemini, call_nvidia, call_openai


SYSTEM_PROMPT_DEFAULT = (
    "You are a senior systems architect helping a developer who is "
    "building or maintaining a ComfyUI custom node pack. Be candid; "
    "flag uncertainty rather than bluffing. Cite specific files / "
    "line numbers when relevant. Prefer the smallest change with the "
    "largest payoff."
)


# Lookup table: provider name → (caller function, env var, expected key prefix)
_PROVIDERS = {
    "openai": (call_openai, "OPENAI_API_KEY", "sk-"),
    "gemini": (call_gemini, "GEMINI_API_KEY", None),
    "nvidia": (call_nvidia, "NVIDIA_API_KEY", None),
}


@dataclasses.dataclass(frozen=True)
class RoundResult:
    """One provider's outcome.

    ``ok=True`` → ``model`` and ``response`` are populated.
    ``ok=False`` → ``error`` describes why the whole ladder failed.
    ``attempts`` lists the typed errors for each rung that fell through
    before the successful (or final-failed) one.
    """

    provider: str
    ok: bool
    model: str
    response: str
    elapsed_sec: float
    pruned_dropped: tuple[str, ...]  # rungs the probe dropped
    attempts: tuple[ConsultError, ...]  # rungs this run dropped
    error: str = ""


class RoundRobinRunner:
    """Carries config, ladders, probes, and writes per-round files.

    Reusable; create one and call ``run`` once per question. The
    runner does not retain state between runs (each ``run`` call is
    independent).
    """

    def __init__(
        self,
        ladders: Mapping[str, Ladder],
        *,
        api_keys: Mapping[str, str],
        system_prompt: str = SYSTEM_PROMPT_DEFAULT,
        output_dir: str | Path = ".",
        config_warnings: Iterable[str] = (),
        probe_fetcher: Callable | None = None,
        call_fetchers: Mapping[str, Callable] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.ladders = dict(ladders)
        self.api_keys = dict(api_keys)
        self.system_prompt = system_prompt
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config_warnings = tuple(config_warnings)
        self._probe_fetcher = probe_fetcher
        self._call_fetchers = dict(call_fetchers or {})
        self._log = log or _default_logger

    # ----- public API ----------------------------------------------

    def run(
        self,
        question: str,
        *,
        topic: str | None = None,
        needs: Iterable[str] | None = None,
        skip_providers: Iterable[str] = (),
    ) -> list[RoundResult]:
        """Run the round-robin and write outputs.

        Returns the list of ``RoundResult``s in the order providers were
        tried (currently: openai, gemini, nvidia for any present in
        ``self.ladders``).
        """
        for warn in self.config_warnings:
            self._log(f"[config] {warn}")
        today = datetime.date.today().isoformat()
        topic = topic or _slugify(question)
        prefix = (
            topic
            if re.match(r"^\d{4}-\d{2}-\d{2}", topic)
            else f"{today}-{topic}"
        )
        self._write_md(prefix, "00_question.md", f"# Question — {today}\n\n{question}\n")

        skip = set(skip_providers)
        results: list[RoundResult] = []
        prior_responses: list[tuple[str, str]] = []
        for idx, name in enumerate(self._provider_order()):
            if name in skip:
                self._log(f"[round] skip {name} (--skip-{name} or no key)")
                continue
            ladder = self.ladders[name]
            api_key = self.api_keys.get(name, "")
            if not api_key:
                self._log(f"[round] skip {name} (no API key)")
                continue
            result = self._run_one(
                name,
                ladder,
                api_key,
                question,
                needs=needs,
                prior_responses=prior_responses,
            )
            results.append(result)
            slot = f"{idx + 1:02d}_{name}.md"
            if result.ok:
                self._write_md(
                    prefix,
                    slot,
                    f"# Round {idx + 1} — {name} ({result.model}) "
                    f"elapsed={result.elapsed_sec:.1f}s\n\n{result.response}\n",
                )
                prior_responses.append((result.model, result.response))
            else:
                self._write_md(
                    prefix,
                    slot,
                    f"# Round {idx + 1} — {name} FAILED\n\n{result.error}\n",
                )

        # synthesis
        self._write_md(
            prefix,
            f"{len(results) + 1:02d}_synthesis.md",
            _synthesis_text(question, results, today),
        )
        # machine-readable transcript
        transcript = {
            "question": question,
            "topic": topic,
            "date": today,
            "rounds": [_result_to_dict(r) for r in results],
        }
        (self.output_dir / f"{prefix}__transcript.json").write_text(
            json.dumps(transcript, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return results

    # ----- internals -----------------------------------------------

    def _provider_order(self) -> list[str]:
        """Stable order: openai → gemini → nvidia → other (alphabetical)."""
        canonical = ["openai", "gemini", "nvidia"]
        present = [p for p in canonical if p in self.ladders]
        extras = sorted(p for p in self.ladders if p not in canonical)
        return present + extras

    def _run_one(
        self,
        name: str,
        ladder: Ladder,
        api_key: str,
        question: str,
        *,
        needs: Iterable[str] | None,
        prior_responses: list[tuple[str, str]],
    ) -> RoundResult:
        # 1. capability filter
        filtered = ladder.filter_for_needs(needs)
        if not filtered.models:
            return RoundResult(
                provider=name,
                ok=False,
                model="",
                response="",
                elapsed_sec=0.0,
                pruned_dropped=(),
                attempts=(),
                error=(
                    f"no rungs in {name} ladder satisfy needs={list(needs or ())!r}"
                ),
            )
        # 2. probe + prune
        probe = probe_provider(filtered, api_key, fetcher=self._probe_fetcher)
        pruned, dropped = prune_ladder(filtered, probe)
        if probe.ok:
            self._log(
                f"[probe {name}] live={len(probe.live_ids)} "
                f"kept={[m.id for m in pruned.models]} "
                f"dropped={[m.id for m in dropped]}"
            )
        else:
            self._log(f"[probe {name}] FAILED ({probe.error}) — using configured ladder unchanged")
            pruned = filtered
            dropped = []
        if not pruned.models:
            return RoundResult(
                provider=name,
                ok=False,
                model="",
                response="",
                elapsed_sec=0.0,
                pruned_dropped=tuple(m.id for m in dropped),
                attempts=(),
                error=(
                    "after probe-prune the ladder is empty; the API key "
                    "doesn't have access to any rung. Re-check the key "
                    "and bump last_reviewed in ladders.yaml."
                ),
            )
        # 3. build prompt with prior-round context
        prompt = _build_prompt_with_priors(question, prior_responses)
        # 4. call
        caller = _PROVIDERS[name][0]
        fetcher = self._call_fetchers.get(name)
        t0 = time.time()
        try:
            model_id, text, attempts = caller(
                list(pruned.models), prompt, self.system_prompt, api_key,
                fetcher=fetcher,
            )
        except LadderExhausted as e:
            elapsed = time.time() - t0
            return RoundResult(
                provider=name,
                ok=False,
                model="",
                response="",
                elapsed_sec=elapsed,
                pruned_dropped=tuple(m.id for m in dropped),
                attempts=tuple(e.attempts),
                error=str(e),
            )
        except TransportError as e:
            elapsed = time.time() - t0
            return RoundResult(
                provider=name,
                ok=False,
                model="",
                response="",
                elapsed_sec=elapsed,
                pruned_dropped=tuple(m.id for m in dropped),
                attempts=(e,),
                error=str(e),
            )
        elapsed = time.time() - t0
        # log per-attempt typed reasons so a flaky run is auditable
        for att in attempts:
            self._log(f"[{name}] {att.model}: {att}")
        self._log(f"[{name}] OK on {model_id} in {elapsed:.1f}s")
        return RoundResult(
            provider=name,
            ok=True,
            model=model_id,
            response=text,
            elapsed_sec=elapsed,
            pruned_dropped=tuple(m.id for m in dropped),
            attempts=tuple(attempts),
        )

    def _write_md(self, prefix: str, basename: str, content: str) -> None:
        path = self.output_dir / f"{prefix}__{basename}"
        path.write_text(content, encoding="utf-8")


# ----- helpers ------------------------------------------------------

def _default_logger(line: str) -> None:
    print(line, file=sys.stderr)


def _slugify(s: str, max_len: int = 40) -> str:
    out: list[str] = []
    last_dash = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            last_dash = False
        elif not last_dash and out:
            out.append("-")
            last_dash = True
    slug = "".join(out).strip("-")
    return slug[:max_len] or "consultation"


def _build_prompt_with_priors(
    question: str, priors: list[tuple[str, str]]
) -> str:
    if not priors:
        return question
    lines = [f"## Original question\n\n{question}\n"]
    for i, (model, response) in enumerate(priors, start=1):
        lines.append(f"## Prior round {i} ({model}) answered\n\n{response}\n")
    lines.append(
        "## Your task\n\n"
        "1. State whether you AGREE, PARTIALLY AGREE, or DISAGREE "
        "with the prior answer(s) in one sentence.\n"
        "2. List any FACTUAL ERRORS or hallucinated APIs / file paths "
        "in the prior answer(s).\n"
        "3. List anything IMPORTANT THAT WAS OMITTED.\n"
        "4. Give your own short recommendation (3-6 bullets).\n"
        "5. Note any items where you are uncertain and want verification.\n"
    )
    return "\n".join(lines)


def _synthesis_text(
    question: str, results: list[RoundResult], today: str
) -> str:
    parts = [
        f"# Synthesis — {today}\n",
        f"**Question:** {question}\n",
    ]
    for r in results:
        if r.ok:
            parts.append(
                f"---\n\n## {r.provider} ({r.model}, {r.elapsed_sec:.1f}s)\n\n"
                f"{r.response}\n"
            )
        else:
            parts.append(
                f"---\n\n## {r.provider} — FAILED\n\n{r.error}\n"
            )
    parts.append(
        "---\n\n## To decide (operator / next agent)\n\n"
        "- [ ] Where all rounds agree:\n"
        "- [ ] Two-vs-one splits:\n"
        "- [ ] Facts to verify:\n"
        "- [ ] Final grounded recommendation:\n"
    )
    return "\n".join(parts)


def _result_to_dict(r: RoundResult) -> dict:
    return {
        "provider": r.provider,
        "ok": r.ok,
        "model": r.model,
        "response": r.response,
        "elapsed_sec": round(r.elapsed_sec, 2),
        "pruned_dropped": list(r.pruned_dropped),
        "attempts": [
            {
                "provider": a.provider,
                "model": a.model,
                "http_code": a.http_code,
                "type": type(a).__name__,
                "message": str(a),
            }
            for a in r.attempts
        ],
        "error": r.error,
    }
