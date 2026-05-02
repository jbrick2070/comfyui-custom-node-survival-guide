# llm_round_robin

A drop-in addon for ComfyUI custom-node authors who let an AI coding agent
(Claude Code, Codex, Cursor, ChatGPT in agent mode, etc.) call ChatGPT /
Gemini / NVIDIA NIM for second opinions on their code.

The problem this addon solves is documented as a class lesson in
`BUG_BIBLE.yaml` under `12.39` (legacy id `BUG-LOCAL-133`): hardcoded
LLM model lists go stale silently. Providers rename and deprecate
models on a months-not-years cadence. Without probing, your AI agent
will burn its consult budget on rungs that 4xx and silently land on a
weaker fallback model nobody noticed.

## What this addon gives you

- `python -m llm_round_robin --question file.md --topic xyz` round-robin
  consult that hits each provider in order, walks per-provider model
  ladders, and synthesizes a markdown summary the calling agent can
  read back.
- **Probe-first prune.** At startup, hits `GET /v1/models` (or the
  provider equivalent) for each provider, intersects the response with
  the configured ladder, and prunes dead rungs before any consult.
- **Endpoint-aware dispatch.** Each ladder entry tags itself
  `responses | chat | both | generate_content`. The runner sends each
  call to the right URL — newer OpenAI `gpt-5.x` models are scoped to
  `/v1/responses` and 4xx silently on `/v1/chat/completions`.
- **Capability tags + `--needs` flag.** Tag each model with `text`,
  `vision`, `tools`, `reasoning`. Callers express a need (`--needs
  reasoning+tools`), the runner filters the ladder by capability — no
  hand-maintained "use this model for this task" branching.
- **Typed error logging.** Every fall-through is classified as
  `ModelNotFound | EndpointMismatch | PermissionDenied | RateLimited |
  TransportError | AuthError`. The transcript shows the operator
  exactly why each rung was skipped.
- **Ladder-staleness alarm.** `last_reviewed:` date in
  `config/ladders.yaml`; the runner warns at startup if it's older
  than `--staleness-days` (default 60).
- **Cross-platform.** The OTR-internal version used `winreg` directly
  to read fresh User-scope env vars. This addon tries `winreg` on
  Windows and falls back to `os.environ` everywhere else.

## Install

This addon ships as a single Python package. Drop the `llm_round_robin/`
directory next to your custom-node pack (or anywhere on `PYTHONPATH`)
and you can call it with `python -m llm_round_robin`.

```
your-custom-node-pack/
├── __init__.py
├── nodes/
├── llm_round_robin/         ← copied or vendored from this repo
│   ├── __init__.py
│   ├── __main__.py
│   ├── config/
│   │   └── ladders.yaml
│   └── ...
└── requirements.txt
```

PyYAML is recommended (`pip install pyyaml`) but not required — there's
a stdlib fallback parser for the documented config shape.

## 5-step quickstart for an AI coding agent

1. Copy `llm_round_robin/` next to your project, and make sure
   `config/ladders.yaml` is present (you can edit the bundled one in
   place, or pass `--config /your/path/ladders.yaml`).
2. Set at least one provider key as a User env var:
   - Windows: `setx OPENAI_API_KEY "sk-…"` then open a fresh shell
   - Linux/Mac: `export OPENAI_API_KEY="sk-…"` (or stash in `.env`)
3. Smoke-test the install with `python -m llm_round_robin --skip-gemini
   --skip-nvidia --question-text "Hello, are you reachable?" --topic
   smoke --output-dir ./consults`. The first lines of stderr should
   show `[probe openai] live=…` followed by `[openai] OK on …`.
4. From your AI coding agent, when you want a second opinion on the
   user's code, write the question to a markdown file and call:

   ```bash
   python -m llm_round_robin \
       --question docs/question.md \
       --topic vram-budget \
       --needs reasoning+tools \
       --output-dir docs/consults
   ```

   The agent then reads `docs/consults/<date>-vram-budget__04_synthesis.md`
   and `…__transcript.json` to absorb the consensus / disagreement
   between the providers.
5. Re-verify `last_reviewed:` in `config/ladders.yaml` whenever you
   notice the staleness alarm fire (every ~60 days). Update model ids
   per the provider's current docs and commit the bumped date.

## Maintenance — keeping the ladder live

The bundled `config/ladders.yaml` was last reviewed against provider
docs on the date you'll see at the top of the file. When the staleness
alarm fires:

1. Open each provider's docs (`platform.openai.com/docs/models`,
   `ai.google.dev/gemini-api/docs/models`, `build.nvidia.com/explore/discover`).
2. Drop deprecated rungs. Add any new flagship variants you want to
   bias toward.
3. Decide whether the new variant needs a different `endpoint:` (newer
   OpenAI flagships are `/v1/responses`-only) or `capabilities:` tag.
4. Run a smoke consult with `--skip-*` for the providers you didn't
   change. Confirm the probe lists the new variant in `kept=[…]` and
   the consult returns text from it.
5. Bump `last_reviewed:` to today and commit.

## Programmatic use

The runner is UI-agnostic — you can call it from a ComfyUI node, a
test, or a CI script:

```python
from llm_round_robin import RoundRobinRunner, load_ladders, read_env_var

ladders, warnings = load_ladders("path/to/ladders.yaml")
runner = RoundRobinRunner(
    ladders=ladders,
    api_keys={"openai": read_env_var("OPENAI_API_KEY", expected_prefix="sk-")},
    output_dir="./consults",
    config_warnings=warnings,
)
results = runner.run("Why is my VRAM ceiling getting hit?", topic="vram-budget", needs=["reasoning"])
for r in results:
    if r.ok:
        print(r.provider, r.model, r.elapsed_sec)
```

## Why this lives in the survival guide

The bug bible's job is to capture class lessons that any custom-node
author can apply to their own pack. The round-robin consult is a tool
for an AI agent debugging a custom node — same audience. Shipping it
in the same repo lets the agent's bibliography (`BUG_BIBLE.yaml`) and
its consult tool stay versioned together. See
`docs/llm_round_robin_explainer.md` for the design rationale.
