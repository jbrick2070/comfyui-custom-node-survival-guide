# `llm_round_robin` — keeping your AI agent's LLM consults from rotting silently

Audience: a ComfyUI custom-node author looking at this repo, deciding whether to
drop the addon into their own project.

## The class of problem

Your AI coding agent (Claude Code, Codex, Cursor, ChatGPT in agent mode) is
already smart enough to know when it should ask for a second opinion. So you
hand it a script that calls ChatGPT, Gemini, and an NVIDIA NIM model in
round-robin and synthesises the answers.

That script will rot in a way you cannot see by reading its output. The agent
will keep getting "valid" answers, the markdown transcripts will keep landing
on disk, and you will keep believing the round-robin is doing its job — while
the consults silently fall through to weaker fallback models that nobody
intended to land on. Months later, after a tough debug session leaves you
suspicious of the answers, you finally read the transcripts and realise round
A landed on `gpt-4o`, round B on `gemini-2.5-pro`, round C on a model that was
deprecated last quarter. Every consult was burning your API budget on the
wrong rung.

## Three convergent failure modes

The reason this happens is that hardcoded model lists go stale on a
months-not-years cadence, and three classes of drift compound silently:

1. **Model name drift.** Providers rename, deprecate, and replace models on a
   months-not-years cadence. `gpt-5.1-codex-max` becomes `gpt-5.3-codex`.
   `gemini-3-pro-preview` is shut down. Your hardcoded list still names them.
   Calls 4xx, the script logs "model unavailable, trying next..." with no
   information about *what kind* of unavailable, and walks the ladder to
   something older.
2. **Endpoint drift.** Newer flagship models are scoped to specific endpoints.
   OpenAI `gpt-5.x` and `-pro` variants only work on `/v1/responses`; calling
   them on `/v1/chat/completions` returns a 400 that's hard to distinguish
   from "model not found" in the response body. Without endpoint-aware
   dispatch the script silently falls to a chat-completion-only model.
3. **Aliasing pitfalls.** `gemini-pro-latest` resolves to whatever the
   provider currently considers "latest," which can change without notice and
   silently land on a different tier than intended.

Compounded by generic untyped error logging that hides
`model_not_found` vs `endpoint_mismatch` vs `permission_denied` vs
`rate_limited`, you have no signal that anything's wrong.

## Fix architecture

The addon is a clean-room reimplementation of these defenses, extracted from a
production ComfyUI custom-node sprint and generalised so any author can drop it
in:

- **Probe-first prune.** At startup, hits `GET /v1/models` (or the provider
  equivalent) for each provider, intersects with the configured ladder, and
  prunes dead rungs. The runner logs the live set so you can see exactly which
  rungs are eligible BEFORE any consult fires.
- **Typed errors.** Every fall-through is classified as `ModelNotFound |
  EndpointMismatch | PermissionDenied | RateLimited | TransportError |
  AuthError`. The transcript shows the operator exactly why each rung was
  skipped. Falls through on the first four; re-raises on the last two
  (different model on the same provider hits the same network).
- **Ladder externalised to YAML.** Maintain `config/ladders.yaml` — one
  per-provider list of `id` + `endpoint` + `capabilities`. Adding a model is
  a one-entry edit; no Python changes, no rebuild.
- **Capability tags + `--needs` flag.** Tag each model with `text`, `vision`,
  `tools`, `reasoning`. Callers express a need (`--needs reasoning+tools`)
  and the runner filters the ladder by capability — no hand-maintained "use
  this model for this task" branching, and no fall-through to a model that
  can't do the job.
- **Endpoint-aware dispatch.** Each ladder entry tags itself
  `responses | chat | both | generate_content`. The runner sends each call
  to the right URL — no more silent endpoint-mismatch 400s.
- **Ladder-staleness alarm.** `last_reviewed:` date in the YAML. The runner
  warns at startup if the date is older than 60 days (configurable). When
  you see the alarm, you know it's time to verify the ladder against
  provider docs.

## 5-step quickstart

1. Copy `llm_round_robin/` next to your custom-node pack. PyYAML is
   recommended (`pip install pyyaml`) but not required — there's a stdlib
   fallback parser for the documented config shape.
2. Set at least one provider key as a User env var. Windows:
   `setx OPENAI_API_KEY "sk-…"` then open a fresh shell. Linux/Mac:
   `export OPENAI_API_KEY="sk-…"`.
3. Smoke-test the install with `python -m llm_round_robin --skip-gemini
   --skip-nvidia --question-text "Hello, are you reachable?" --topic smoke
   --output-dir ./consults`. Stderr should show
   `[probe openai] live=…` followed by `[openai] OK on …`.
4. From your AI coding agent, write a question to a markdown file and run
   `python -m llm_round_robin --question docs/q.md --topic <slug> --needs
   reasoning+tools --output-dir docs/consults`. The agent reads the synthesis
   markdown to absorb the consensus / disagreement.
5. Re-verify `last_reviewed:` in `config/ladders.yaml` whenever the
   staleness alarm fires (~every 60 days). Update model ids per the
   provider's current docs and commit the bumped date.

The class lesson is in `BUG_BIBLE.yaml` under `12.39` (legacy id
`BUG-LOCAL-133`). If the addon helps your project, the cost of admission is
sending a new generalisable bug back as a YAML PR.
