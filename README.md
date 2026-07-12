# ComfyUI Custom Node Survival Guide

**By Jeffrey A. Brick** · April–May 2026

An AI-agent QA harness for ComfyUI custom-node authoring. v2.1 — 197 bible entries + LLM round-robin consult addon.

---

### What this catches

BOM corruption, ghost registrations, widget drift, workflow-JSON link rot, VRAM leaks (including ThreadPoolExecutor orphan-thread cases), ffmpeg pipe deadlocks, audio-contract violations, motion-onset / lip-sync drift in audio-driven video, three-tier LLM-output resilience gaps, regex sentinel-word collisions, stale LLM-API ladders silently rotating to deprecated models, and 180+ more class lessons.

### Who should use it

Any ComfyUI custom-node author who lets an AI coding agent (Claude Code, Cowork, Cursor, ChatGPT in agent mode, etc.) work on their pack. The bible tells the agent *what to check for*; the round-robin addon gives the agent *reliable second opinions* on hard calls.

### How to run it

Paste the prompt under "Vibe-coder pledge" below into your AI agent. The agent handles install, clone, and execution. Or jump to "Manual mode" if you'd rather run commands yourself.

### What problems it prevents

The "AI agent confidently shipped a broken fix" failure mode. Static analysis catches the regression in under 2 seconds; the round-robin catches design-level mistakes before they land. Three-File Contract (README + YAML + tests) keeps the bible from rotting into "the doc says one thing, the code checks another."

---

## What's in the kit

1. **`BUG_BIBLE.yaml` + `tests/bug_bible_regression.py`** — a 197-entry, machine-readable bug bible plus an automated pytest suite that turns the bible's `verify` fields into executable assertions. Point the suite at any custom-node pack and get a pass/fail report in under 2 seconds. No ComfyUI runtime, no model downloads, no manual grepping.

2. **`llm_round_robin/`** — a drop-in addon that lets your AI agent call ChatGPT, Gemini, and NVIDIA NIM for second opinions, with probe-first ladder pruning, endpoint-aware dispatch, and capability-tag routing so the agent never silently lands on a stale fallback model. See [`docs/llm_round_robin_explainer.md`](./docs/llm_round_robin_explainer.md).

Same audience for both: an AI coding agent doing QA on a custom-node pack. Versioning them together keeps the agent's bibliography and consult tool in sync.

## Vibe-coder pledge: paste this into your AI coding agent

You don't need to run any commands yourself. If you use Claude Code, Cowork,
Cursor, or ChatGPT in agent mode — paste the prompt below into a fresh agent
session and let the agent install what it needs, clone this repo if it isn't
already on disk, and run the bible against your custom-node pack.

Replace `<your-pack-path>` with the absolute path to the custom-node pack you
want checked. If you don't know the path, paste the prompt anyway and ask the
agent to help you find it.

```
You are helping me check a ComfyUI custom-node pack at <your-pack-path>
against the ComfyUI Custom Node Survival Guide
(https://github.com/jbrick2070/comfyui-custom-node-survival-guide).

PHASE 0 - SETUP (run this first, before any other work):

0. Open `BUG_BIBLE.yaml` now. Keep the relevant `symptom:`, `fix:`, and
   `verify:` rules in context before proposing or changing code.

1. Confirm you can run shell commands on my machine:
   - Cowork: workspace bash or Desktop Commander is already available - good.
   - Claude Code: confirm a shell-access MCP is installed (Desktop Commander
     or Windows MCP are the common ones). If neither is configured, tell me
     exactly what to install and pause until I confirm.
   - Cursor / ChatGPT in agent mode: confirm your terminal / shell tool is
     enabled.

2. Check whether the survival guide is already cloned somewhere on disk.
   If not, clone it to a sensible location (next to my custom-node pack
   works fine):
       git clone https://github.com/jbrick2070/comfyui-custom-node-survival-guide

3. Confirm pytest is installed in the Python that runs my ComfyUI. If
   missing, install it (`pip install pytest`).

PHASE 1 - RUN THE BIBLE REGRESSION:

4. cd into <your-pack-path> and run:
       python -m pytest <survival-guide-path>/tests/bug_bible_regression.py \
           -v --pack-dir .

5. Read the output. For each failure, open BUG_BIBLE.yaml at the matching
   entry and walk me through symptom / cause / fix / verify so I can decide
   whether to apply the fix or mark it out-of-scope.

6. AFTER any code change, re-run the regression suite. Don't say "done"
   until it's green (or you've explained any remaining red).

PHASE 2 - STUCK ON A DESIGN CALL?

7. Write the question to a markdown file. From the survival-guide directory:
       python -m llm_round_robin \
           --question docs/q.md \
           --topic <kebab-slug> \
           --needs reasoning+tools \
           --output-dir docs/consults

   Read the synthesis markdown to absorb the consensus / disagreement
   between ChatGPT, Gemini, and NVIDIA NIM. Probe-first ladder pruning
   keeps the consult from silently landing on a stale fallback model.

PHASE 3 - FOUND A NEW CLASS OF BUG?

8. Add a new Bible entry only after the bug has failed in a real production,
   headless, smoke, soak, or published-artifact run. A review finding or
   invented fixture may verify that known incident, but must never create a
   synthetic Bible entry. Record the live incident first, then add a YAML entry
   following the schema (id, phase, area, symptom, cause, fix, verify, tags).
   Cause/fix must be a CLASS LESSON generalisable to any custom-node author,
   not project-narrative form. Update README.md's entry count and add a
   regression test in tests/bug_bible_regression.py if the verify step is
   static-analysis-checkable. Run
       python <survival-guide-path>/tools/reload_bug_bible.py
   to validate the schema before committing.

GROUND RULES:

- Don't run `git push` from your shell session - Windows credential
  manager hangs on AI shells (BUG-12.34). If commits need pushing, hand
  me a PowerShell block with `cd` first, ASCII quotes, and explicit
  branch names. One push attempt max, then hand off.
- Don't invent fixes for bugs already catalogued in BUG_BIBLE.yaml -
  apply the bible's `fix:` directly.
- After every code change, re-run the regression suite. It runs in
  under 2 seconds.

Now - START with PHASE 0. Tell me what's already installed before
running anything.
```

That's it. Paste once at the start of a session, then state your task. The
agent handles setup, walks you through any failures, and reaches for the
round-robin when it's truly stuck.

If you'd rather run the commands yourself, see "Manual mode" below.

## Manual mode (run commands yourself)

For users who'd rather drive this directly instead of pasting a prompt into an AI agent. Replace `<path-to-survival-guide>` with the absolute path to your local clone of this repo, and `<your-pack-path>` with the absolute path to the custom-node pack you're checking.

### 1. Run the bible regression suite against your pack

```bash
cd <your-pack-path>
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

### Privacy / security note for the round-robin addon

The round-robin sends the contents of your question markdown file to whichever LLM providers you've configured (ChatGPT, Gemini, NVIDIA NIM). **Treat consult questions like outbound API requests, because that's what they are.** Do NOT paste secrets, private API keys, customer data, full sensitive logs, or proprietary IP into a consult markdown file unless you have permission to send that content to those providers. The saved synthesis / transcript files in `docs/consults/` contain the raw question and the providers' responses — review and redact before committing them anywhere public.

### 3. Validate the bible after edits

```bash
python tools/reload_bug_bible.py
```

Catches missing keys, duplicate IDs, malformed tags, and deprecated mapping-form
entries. Exits non-zero on issues so it's easy to wire into a pre-commit hook.

## What the regression suite checks

197 bible entries across 12 phases; the pytest suite encodes the static-
analysis-checkable subset as executable assertions.

Entries may carry additive `xref-XX.YY` tags (cross-reference to an
overlapping entry) and `xphase-NN` tags (content also belongs to phase NN;
ids are immutable), added by the 2026-07-12 consistency audit.

| Phase | Coverage | Sample bug IDs |
|---|---|---|
| 01 Bootstrap & Discovery        | Path safety, no dirname chains, folder_paths usage | 01.02, 01.03 |
| 02 Environment & Dependencies   | UTF-8 no BOM, no mojibake, no zero-byte files; boot launchers force UTF-8 stdio; SD 1.5 .ckpt offline-load | 02.11, 02.12, 02.14, 02.15 |
| 03 Registration & Loading       | Isolated per-node loading, namespaced IDs, no ghost registrations | 03.01, 03.03, 12.23 |
| 04 INPUT_TYPES & Widgets        | Widget positional stability; workflow JSON integrity; preserved-vs-stripped auto-sense; socket-only types | 04.01, 04.02, 04.07–04.13 |
| 05 Execution Model              | Coordination, migration, list outputs, interrupts, completion checks; feature-flag/role-policy decoupling | 05.05, 05.06, 05.08, 05.09 |
| 06 Caching & IS_CHANGED         | Stale outputs, signature stability, leaks; model-platform empirical compat | 06.01–06.06 |
| 07 Tensors, Audio, Video        | VRAM, dtype, audio contracts, motion-onset pad, sample-rate, composite layer ordering | 07.01–07.22 |
| 08 I/O & Output Nodes           | Headless API, intermediates, preview thumbnails, OUTPUT_NODE discipline | 08.01–08.08 |
| 09 Subprocess & Network         | Pipe deadlocks, asyncio, offline fallbacks, cloud-API contracts | 09.02, 09.05, 09.06 |
| 10 Safety, Pools, RNG           | Content filters, pool sizing, RNG correctness | 10.01–10.07 |
| 11 LLM-Specific                 | Token budgets, prompt-detector contracts, format normalisers, three-tier resilience, typed repair ladders | 11.01–11.50 |
| 12 Regression, Git, Handoff     | Repo hygiene, AST parse, workflow JSON link integrity, dedup foreign keys, ledger write-back, stale-LLM-API ladder | 12.02, 12.06, 12.07, 12.35, 12.39, 12.52 |

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

## Sibling Project

Some of these patterns generalize beyond ComfyUI to any long-form LLM pipeline — multi-pass revision, arc scoring, token budgets matching reality. Hoisted out into a separate repo for the people who'd never search "comfyui" but need the same patterns: **[long-form-llm-survival-guide](https://github.com/jbrick2070/long-form-llm-survival-guide)**. Same voice, same Three-File Contract discipline, same MIT terms.

## License

MIT. Use freely. If an entry helped you, the cost of admission is sending a new
bug back as a YAML PR.
