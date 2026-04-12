# ComfyUI Custom Node Bug Bible

**By Jeffrey A. Brick** · April 2026

---

## 🚀 Current Status: Testing Against OldTimeRadio v2.0

This regression suite is in active development and tested against [ComfyUI-OldTimeRadio v2.0 (v2.0-visual-engine branch)](https://github.com/jbrick2070/ComfyUI-OldTimeRadio/tree/v2.0-visual-engine) — a production multi-model LLM + TTS + video animation pipeline on RTX 5080, 16 GB VRAM, Windows. The 93-entry knowledge base and 23 automated tests were built from real failure modes hit in this pipeline.

**Latest regression run:** 21 passed, 2 xfailed, 0 failed (1.65s)

---

Automated regression testing for ComfyUI custom node packs. 23 pytest tests that catch ghost registrations, BOM corruption, VRAM leaks, pipe deadlocks, widget errors, and 18 other failure modes in under 2 seconds — no ComfyUI runtime required. Backed by a 93-entry knowledge base of real failure modes from shipping production pipelines.

## Read This

- **[tests/bug_bible_regression.py](./tests/bug_bible_regression.py)** — automated regression test suite. 23 machine-executable tests across 10 phases (including the new Three-File Contract enforcement). Point it at any custom node pack, get a pass/fail report in under 2 seconds. Pure static analysis—no ComfyUI runtime needed.
- **[BUG_BIBLE.yaml](./BUG_BIBLE.yaml)** — the reference knowledge base. 93 entries across 12 phases. Each entry: `id, phase, area, symptom, cause, fix, verify, tags`. Greppable, parseable. Use this for manual lookups or when building new tests.

## How To Use

**AI assistants building custom nodes:** Run the regression suite after every code change. It catches bugs before they ship.

```bash
cd your-custom-node-pack
pip install pytest
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir .
```

**Humans debugging a specific failure:** Open `BUG_BIBLE.yaml`, ctrl-F by `area:` (architecture, widgets, vram, transformers, git, workflow-json, llm, pool-sizing, etc.) or by `tags:` to find matching entries. Read the `cause` and `fix` fields.

**AI assistants without automated testing yet:** Load `BUG_BIBLE.yaml` at the start of a session. Match the user's symptom against `symptom:` fields, apply the `fix:`, then verify manually using the `verify:` field as a checklist.

## Automated Regression Testing — The Main Feature

The pytest suite encodes the Bug Bible's `verify` fields as executable assertions. Point it at any custom node pack directory. In under 2 seconds, you get a full pass/fail report. No ComfyUI runtime, no model downloads, no manual grepping.

### Quick Start

```bash
# From your custom node pack directory:
cd C:\Users\you\Documents\ComfyUI\custom_nodes\MyNodePack

# Run all checks:
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir .

# Run specific phase (e.g., encoding checks only):
python -m pytest <path-to-survival-guide>/tests/bug_bible_regression.py -v --pack-dir . -k "phase02"
```

### What It Checks

| Phase | Bugs Covered | What It Verifies |
|---|---|---|
| 01 | BUG-01.02, 01.03 | Path safety: no dirname chains, folder_paths or safe anchor usage |
| 02 | BUG-02.11, 02.12 | Encoding: UTF-8 no BOM, no mojibake, no 0-byte files |
| 03 | BUG-03.01, 03.03, 12.23 | Registration: isolated loading, namespaced IDs, no ghost nodes |
| 04 | BUG-04.01, 04.02, 12.06 | Widgets: valid INPUT_TYPES, workflow JSON integrity |
| 05 | BUG-05.05 | Execution order: passthrough enforcement on boundary nodes |
| 07 | BUG-07.01, 07.03 | VRAM: no module-scope loads, flush after unload |
| 09 | BUG-09.02 | Subprocess: Popen cleanup, no communicate() with video pipes |
| 11 | BUG-12.33 | LLM: prompt length guards on generate() calls |
| 12 | BUG-12.02, 12.06, 12.07, 12.35 | Repo hygiene: AST parse, workflow link integrity, stale imports, Three-File Contract sync |

### Requirements

- Python 3.10+
- pytest (`pip install pytest`)
- No ComfyUI runtime needed (pure static analysis)

### Example Output

```
tests/bug_bible_regression.py::TestPhase01Paths::test_no_deep_dirname_chains PASSED
tests/bug_bible_regression.py::TestPhase02Encoding::test_no_bom_signatures PASSED
tests/bug_bible_regression.py::TestPhase03Registration::test_no_ghost_node_registrations PASSED
tests/bug_bible_regression.py::TestPhase05Execution::test_memory_boundary_has_passthrough PASSED
tests/bug_bible_regression.py::TestPhase07VRAM::test_vram_flush_after_unload PASSED
tests/bug_bible_regression.py::TestPhase09Subprocess::test_popen_has_cleanup PASSED
tests/bug_bible_regression.py::TestPhase12Regression::test_all_py_files_parse PASSED
======================== 20 passed, 1 xfailed in 1.69s =========================
```

### Adding Your Own Checks

Each test maps to one or more Bug Bible entries. To add a new check, create a test method in the appropriate `TestPhaseNN` class. Name it after the bug ID and include the verify logic from the YAML entry. The `py_files`, `init_py`, `node_modules_dict`, and `workflow_jsons` fixtures give you access to the pack's files without boilerplate.

## Latest Regression Run

Tested against [ComfyUI-OldTimeRadio](https://github.com/jbrick2070/ComfyUI-OldTimeRadio) v2.0 branch (`abfc468`) on 2026-04-11. 27 node files, 5 workflow JSONs, 15 scripts.

```
TestPhase01Paths::test_no_deep_dirname_chains ..................... PASSED
TestPhase01Paths::test_output_nodes_use_folder_paths ............. PASSED
TestPhase02Encoding::test_no_bom_signatures ...................... PASSED
TestPhase02Encoding::test_no_mojibake_markers .................... PASSED
TestPhase02Encoding::test_no_zero_byte_files ..................... PASSED
TestPhase03Registration::test_isolated_loading ................... PASSED
TestPhase03Registration::test_no_ghost_node_registrations ........ PASSED
TestPhase03Registration::test_namespaced_node_ids ................ PASSED
TestPhase04Widgets::test_all_nodes_have_valid_input_types ........ PASSED
TestPhase04Widgets::test_workflow_widget_counts .................. PASSED
TestPhase05Execution::test_memory_boundary_has_passthrough ....... PASSED
TestPhase07VRAM::test_no_module_scope_model_loads ................ PASSED
TestPhase07VRAM::test_vram_flush_after_unload .................... PASSED
TestPhase09Subprocess::test_popen_has_cleanup .................... PASSED
TestPhase09Subprocess::test_no_communicate_for_video ............. PASSED
TestPhase12Regression::test_all_py_files_parse ................... PASSED
TestPhase12Regression::test_workflow_json_link_integrity ......... PASSED
TestPhase12Regression::test_no_stale_v2_imports .................. PASSED
TestPhase11LLM::test_generate_calls_have_length_guard ........... XFAIL
TestThreeFileContract::test_entry_count_matches_readme ........... PASSED
TestThreeFileContract::test_all_bible_ids_covered_in_tests ....... XFAIL
TestSummary::test_pack_has_init .................................. PASSED
TestSummary::test_pack_has_requirements .......................... PASSED
======================== 21 passed, 2 xfailed in 1.65s =========================
```

21 passed, 2 xfail (BUG-12.33 — LLM length guard is informational; BUG-12.35 — coverage gap on untested Bible entries), 0 failed.

---

## Maintenance Rule: The Three-File Contract

**Every update to this project must touch all three files.** No exceptions, even for small changes.

| Order | File | What To Update |
|---|---|---|
| 1 | `README.md` | Coverage areas, test table, entry count, any new instructions |
| 2 | `BUG_BIBLE.yaml` | Add/edit/remove the bug entry with all fields |
| 3 | `tests/bug_bible_regression.py` | Add/update the corresponding test assertion |

If you add a new bug to the Bible, add a matching test to the regression suite. If you fix a test, update the Bible's `verify` field. If either changes, update the README's test coverage table.

This rule exists because partial updates cause silent drift: the Bible says one thing, the tests check something else, and the README describes a third version. AI assistants should treat this as a pre-commit checklist.

### When To Add a New Test

Not every Bible entry needs an automated test. Tests work best for static analysis checks (encoding, registration, AST structure, file patterns). Entries that require runtime (e.g., "model loads without OOM") or human judgment (e.g., "substitutions feel natural") belong in the Bible but not the test suite.

A good rule: if the `verify` field can be checked by reading files without running ComfyUI, it should have a test.

## Coverage Areas

architecture · windows · powershell · git · huggingface · python · cuda · transformers · widgets · loading · coordination · migration · naming · hidden-inputs · validation · list-execution · lazy · interrupt · combo · asyncio · headless · execution-order · vram · model-class · tensors · audio · video · audio-contract · memory · caching · paths · network · data · metadata · telemetry · workflow-json · safety · pool-sizing · regression · rng · deps · ai-autonomy · testing · encoding · sandbox · subprocess · discovery · pipeline-sync · io · output_node · llm · ai-continuity · hygiene · procedural

## License

MIT. Use freely. If an entry helped you, the cost of admission is sending a new bug back as a YAML PR.
