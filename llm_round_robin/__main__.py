"""CLI entry: ``python -m llm_round_robin --question file.md --topic xyz``.

Typical usage from inside a ComfyUI custom-node project::

    python -m llm_round_robin \\
        --question docs/question.md \\
        --topic vram-budget \\
        --needs reasoning+tools \\
        --output-dir docs/consults \\
        --config llm_round_robin/config/ladders.yaml

Common knobs:

  --question PATH        question text in a markdown file
  --question-text STR    inline question text (alternative to --question)
  --topic NAME           kebab-case slug used in output filenames
  --needs CSV            comma- or plus-separated capability list
                         (e.g. "reasoning+tools" or "vision,reasoning")
  --skip-openai|--skip-gemini|--skip-nvidia
                         opt-out per provider
  --config PATH          path to ladders.yaml (default: bundled)
  --output-dir PATH      where to write output md files (default: cwd)
  --staleness-days N     warn if last_reviewed is older than N days (default 60)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_STALENESS_DAYS, load_ladders
from .env import read_env_var
from .runner import RoundRobinRunner


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm_round_robin",
        description=(
            "Round-robin design / bug-fix consult against ChatGPT, "
            "Gemini, and NVIDIA NIM. Probes /v1/models at startup so "
            "stale ladder entries never get dialed."
        ),
    )
    p.add_argument(
        "--question",
        type=str,
        help="Path to a markdown file containing the question.",
    )
    p.add_argument(
        "--question-text",
        type=str,
        help="Inline question text (alternative to --question).",
    )
    p.add_argument(
        "--topic",
        type=str,
        help="Kebab-case slug used in output filenames (default: derived from question).",
    )
    p.add_argument(
        "--needs",
        type=str,
        default=None,
        help=(
            "Capability filter, comma- or plus-separated. Example: "
            "'reasoning+tools' or 'vision,reasoning'. Models that don't "
            "satisfy every named capability are skipped."
        ),
    )
    p.add_argument("--skip-openai", action="store_true")
    p.add_argument("--skip-gemini", action="store_true")
    p.add_argument("--skip-nvidia", action="store_true")
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to ladders.yaml (default: bundled config/ladders.yaml).",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Where to write output md / json files (default: current directory).",
    )
    p.add_argument(
        "--staleness-days",
        type=int,
        default=DEFAULT_STALENESS_DAYS,
        help=f"Warn if ladders.yaml last_reviewed is older than N days (default {DEFAULT_STALENESS_DAYS}).",
    )
    p.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        help="Override the default system prompt with a literal string.",
    )
    p.add_argument(
        "--system-prompt-file",
        type=str,
        default=None,
        help="Override the default system prompt with the contents of this file.",
    )
    return p


def _resolve_question(args: argparse.Namespace) -> str:
    if args.question_text:
        return args.question_text.strip()
    if args.question:
        return Path(args.question).read_text(encoding="utf-8").strip()
    print(
        "Enter your question. Finish with Ctrl-D (Linux/Mac) or "
        "Ctrl-Z then Enter (Windows):",
        file=sys.stderr,
    )
    return sys.stdin.read().strip()


def _parse_needs(s: str | None) -> list[str] | None:
    if not s:
        return None
    parts = [x.strip() for x in s.replace("+", ",").split(",")]
    return [p for p in parts if p]


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    question = _resolve_question(args)
    if not question:
        print("ERROR: empty question.", file=sys.stderr)
        return 1
    needs = _parse_needs(args.needs)

    try:
        ladders, warnings = load_ladders(
            args.config,
            staleness_days=args.staleness_days,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    skip = set()
    if args.skip_openai:
        skip.add("openai")
    if args.skip_gemini:
        skip.add("gemini")
    if args.skip_nvidia:
        skip.add("nvidia")

    api_keys: dict[str, str] = {}
    for name, (_caller, env_name, prefix) in {
        "openai": (None, "OPENAI_API_KEY", "sk-"),
        "gemini": (None, "GEMINI_API_KEY", None),
        "nvidia": (None, "NVIDIA_API_KEY", None),
    }.items():
        if name in skip or name not in ladders:
            continue
        try:
            api_keys[name] = read_env_var(env_name, expected_prefix=prefix)
        except RuntimeError as e:
            print(f"[round-robin] skipping {name}: {e}", file=sys.stderr)

    if not api_keys:
        print(
            "ERROR: no provider keys available — set at least one of "
            "OPENAI_API_KEY / GEMINI_API_KEY / NVIDIA_API_KEY, or pass "
            "--skip-* for the ones you don't have.",
            file=sys.stderr,
        )
        return 2

    system_prompt = None
    if args.system_prompt:
        system_prompt = args.system_prompt
    elif args.system_prompt_file:
        system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")

    runner_kwargs: dict = {
        "ladders": ladders,
        "api_keys": api_keys,
        "output_dir": args.output_dir,
        "config_warnings": warnings,
    }
    if system_prompt is not None:
        runner_kwargs["system_prompt"] = system_prompt
    runner = RoundRobinRunner(**runner_kwargs)
    results = runner.run(
        question,
        topic=args.topic,
        needs=needs,
        skip_providers=skip,
    )
    fail_count = sum(1 for r in results if not r.ok)
    print(
        f"[round-robin] done — {len(results)} rounds, {fail_count} failed. "
        f"Outputs under {args.output_dir}.",
        file=sys.stderr,
    )
    return 0 if fail_count == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
