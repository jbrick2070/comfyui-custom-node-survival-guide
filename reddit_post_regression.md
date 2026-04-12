# Reddit Post Draft

## Headline

**I built an automated regression test suite for ComfyUI custom node packs — catches ghost registrations, BOM corruption, VRAM leaks, pipe deadlocks, and 17 other failure modes in under 2 seconds**

## Subreddit

r/comfyui

## Body

---

A few weeks ago I shared the [ComfyUI Custom Node Bug Bible](https://github.com/jbrick2070/comfyui-custom-node-survival-guide) — a YAML database of 67 real failure modes I hit shipping a production node pack (multi-model LLM + TTS + video pipeline on an RTX 5080, 16 GB VRAM, Windows).

The response was great, but the Bible had a problem: it was read-only. You had to manually cross-reference each bug against your code. AI assistants had to spend 5+ minutes reading YAML and grepping by hand, and they'd still miss things or hallucinate false positives.

So I built the machine-executable version: **`tests/bug_bible_regression.py`** — a pytest suite that encodes the `verify` field of each relevant bug as an automated assertion. Point it at any custom node pack directory, and in under 2 seconds you get a pass/fail report.

### What it catches (21 tests across 9 Bug Bible phases):

- **Path safety** — dirname chain miscounts, missing folder_paths usage
- **Encoding** — UTF-8 BOM injection from PowerShell, mojibake corruption, 0-byte files
- **Registration** — isolated loading, namespaced IDs, ghost node entries (class deleted but __init__.py still references it)
- **Widgets** — malformed INPUT_TYPES, workflow JSON duplicate node IDs
- **Execution order** — missing passthrough inputs on boundary nodes
- **VRAM** — module-scope model loads, unload without empty_cache
- **Subprocess** — Popen without cleanup (the classic ffmpeg pipe deadlock), communicate() on video streams
- **LLM** — generate() without prompt length guards (the silent 180s stall bug)
- **Repo hygiene** — AST parse every .py, workflow link integrity, stale v2/ imports

### How to use it

```bash
# From your custom node pack directory:
pip install pytest
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir .
```

No ComfyUI runtime needed. Pure static analysis. Works on any pack that follows standard ComfyUI conventions (__init__.py with NODE_CLASS_MAPPINGS).

### The Three-File Contract

The project now enforces a maintenance rule: every update must touch all three files (README, BUG_BIBLE.yaml, regression .py). If you add a bug to the Bible, you add a matching test. If you fix a test, you update the verify field. No drift.

### Example output against my own pack (27 node files, 5 workflow JSONs):

```
TestPhase01Paths::test_no_deep_dirname_chains PASSED
TestPhase02Encoding::test_no_bom_signatures PASSED
TestPhase03Registration::test_no_ghost_node_registrations PASSED
TestPhase05Execution::test_memory_boundary_has_passthrough PASSED
TestPhase07VRAM::test_vram_flush_after_unload PASSED
TestPhase09Subprocess::test_popen_has_cleanup PASSED
TestPhase12Regression::test_all_py_files_parse PASSED
======================== 20 passed, 1 xfailed in 1.69s =========================
```

Repo: https://github.com/jbrick2070/comfyui-custom-node-survival-guide

The regression suite is designed to be extended. Each test maps to a Bug Bible entry. If you hit a new failure mode, add a YAML entry + a test + update the README. PRs welcome.

If you're building custom nodes and your AI assistant keeps introducing the same bugs across sessions, point it at the Bible first and run the regression after every change. It's saved me hours.

---

*Jeffrey A. Brick — AI filmmaker, healthcare IT PM, custom node developer. Building an AI-powered sci-fi radio drama generator on ComfyUI.*
