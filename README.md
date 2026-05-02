# ComfyUI Custom Node Survival Guide

**By Jeffrey A. Brick** · April–May 2026

A survival kit for ComfyUI custom-node authors who want their AI coding agent
(Claude Code, Codex, Cursor, ChatGPT in agent mode, etc.) to do better QA, design
review, and LLM-driven debugging on the user's own custom-node pack.

Two products live in this repo:

1. **`BUG_BIBLE.yaml` + `tests/bug_bible_regression.py`** — a 153-entry,
   machine-readable bug bible plus an automated pytest suite that turns the
   bible's `verify` fields into executable assertions. Point the suite at any
   custom-node pack and get a pass/fail report in under 2 seconds. No ComfyUI
   runtime, no model downloads, no manual grepping.
2. **`llm_round_robin/`** — a drop-in addon that lets your AI agent call
   ChatGPT, Gemini, and NVIDIA NIM for second opinions, with probe-first ladder
   pruning, endpoint-aware dispatch, and capability-tag routing so the agent
   never silently lands on a stale fallback model. See
   [docs/llm_round_robin_explainer.md](./docs/llm_round_robin_explainer.md).

## Why both live in the same repo

Same audience: an AI coding agent doing QA on a user's custom-node pack. The
bible tells the agent *what to check for*; the round-robin addon gives the agent
*reliable second opinions* on hard calls. Versioning them together keeps the
agent's bibliography and consult tool in sync.

## Quick start

### 1. Run the bible regression suite against your pack

```bash
cd C:\Users\you\Documents\ComfyUI\custom_nodes\MyNodePack
pip install pytest
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir .
```

Specific phase only (e.g. encoding checks):

```bash
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir . -k "phase02"
```

### 2. Drop the round-robin addon next to your pack

```text
your-custom-node-pack/
├── __init__.py
├── nodes/
└── llm_round_robin/         ← copy from this repo
    ├── __init__.py
    ├── __main__.py
    └── config/ladders.yaml
```

Set at least one provider key as a User env var, then:

```bash
python -m llm_round_robin \
    --question docs/question.md \
    --topic vram-budget \
    --needs reasoning+tools \
    --output-dir docs/consults
```

The agent reads `docs/consults/<date>-vram-budget__NN_synthesis.md` to absorb
the consensus / disagreement between providers.

See [`llm_round_robin/README.md`](./llm_round_robin/README.md) for the full
setup and 5-step quickstart.

### 3. Validate the bible after edits

```bash
python tools/reload_bug_bible.py
```

Catches missing keys, duplicate IDs, malformed tags, and deprecated mapping-form
entries. Exits non-zero on issues so it's easy to wire into a pre-commit hook.

## What the regression suite checks

153 Bible entries across 12 phases; the pytest suite encodes the static-
analysis-checkable subset as executable assertions.

| Phase | Coverage | Sample bug IDs |
|---|---|---|
| 01 Bootstrap & Discovery        | Path safety, no dirname chains, folder_paths usage | 01.02, 01.03 |
| 02 Environment & Dependencies   | UTF-8 no BOM, no mojibake, no zero-byte files; SD 1.5 .ckpt offline-load | 02.11, 02.12, 02.14 |
| 03 Registration & Loading       | Isolated per-node loading, namespaced IDs, no ghost registrations | 03.01, 03.03, 12.23 |
| 04 INPUT_TYPES & Widgets        | Widget positional stability; workflow JSON integrity; preserved-vs-stripped auto-sense; socket-only types | 04.01, 04.02, 04.07–04.13 |
| 05 Execution Model              | Coordination, migration, list outputs, interrupts, completion checks; feature-flag/role-policy decoupling | 05.05, 05.06, 05.08, 05.09 |
| 06 Caching & IS_CHANGED         | Stale outputs, signature stability, leaks; model-platform empirical compat | 06.01–06.06 |
| 07 Tensors, Audio, Video        | VRAM, dtype, audio contracts, motion-onset pad, sample-rate, composite layer ordering | 07.01–07.15 |
| 08 I/O & Output Nodes           | Headless API, intermediates, preview thumbnails, OUTPUT_NODE discipline | 08.01–08.06 |
| 09 Subprocess & Network         | Pipe deadlocks, asyncio, offline fallbacks | 09.02 |
| 10 Safety, Pools, RNG           | Content filters, pool sizing, RNG correctness | 10.01–10.07 |
| 11 LLM-Specific                 | Token budgets, prompt-detector contracts, format normalisers, three-tier resilience | 11.01–11.25 |
| 12 Regression, Git, Handoff     | Repo hygiene, AST parse, workflow JSON link integrity, dedup foreign keys, ledger write-back, stale-LLM-API ladder | 12.02, 12.06, 12.07, 12.35, 12.39 |

## How an AI coding agent uses this kit

**Pattern 1 — open the bible at the start of a session.** Load `BUG_BIBLE.yaml`
into context. Match the user's symptom against `symptom:` fields, apply the
`fix:`, verify using the `verify:` field as a checklist.

**Pattern 2 — run the regression suite after every code change.** Pure static
analysis; no ComfyUI runtime needed. Catches BOM corruption, ghost registrations,
widget drift, VRAM leaks, pipe deadlocks before they ship.

**Pattern 3 — call the round-robin for second opinions on tough calls.** When
the agent is choosing between architectures, evaluating a refactor, or stuck on
a non-trivial bug, it writes the question to a markdown file and runs:

```bash
python -m llm_round_robin --question q.md --topic <slug> --needs reasoning+tools
```

Probe-first ladder pruning means the agent never silently lands on a stale
fallback model.

## Maintenance Rule: The Three-File Contract

**Every update must touch all three files.** No exceptions.

| Order | File | What To Update |
|---|---|---|
| 1 | `README.md`                            | Coverage table, entry count, instructions |
| 2 | `BUG_BIBLE.yaml`                       | Add/edit/remove the bug entry with all fields |
| 3 | `tests/bug_bible_regression.py`        | Add/update the matching assertion (where statically checkable) |

Run `python tools/reload_bug_bible.py` to validate after every edit.

If the bible's `verify` field can be checked by reading files without running
ComfyUI, it should have a corresponding test. Entries that require runtime
(e.g. "model loads without OOM") or human judgment (e.g. "substitutions feel
natural") belong in the Bible but not the test suite — they're documented as
exclusions inline.

## Coverage Areas

architecture · windows · powershell · git · huggingface · python · cuda ·
transformers · widgets · loading · coordination · migration · naming ·
hidden-inputs · validation · list-execution · lazy · interrupt · combo ·
asyncio · headless · execution-order · vram · model-class · tensors · audio ·
video · audio-contract · memory · caching · paths · network · data · metadata ·
telemetry · workflow-json · safety · pool-sizing · regression · rng · deps ·
ai-autonomy · testing · encoding · sandbox · subprocess · discovery ·
pipeline-sync · io · output_node · llm · ai-continuity · hygiene · procedural ·
llm-routing · ledger

## Bonus — three-version YAML normalization experiment

`docs/bonus_normalization_experiment/` is an optional, run-it-yourself
experiment for readers curious about how different AI models handle the
same "clean up this YAML" task. It snapshots the bible before and after
a Claude (Opus class) normalization pass, prepares a question for the
round-robin addon, and ships a comparison script that diffs the three
versions. Nothing in there is authoritative — see the folder's README for
context. Skip it if you're just here to use the bible + addon.

## License

MIT. Use freely. If an entry helped you, the cost of admission is sending a new
bug back as a YAML PR.
