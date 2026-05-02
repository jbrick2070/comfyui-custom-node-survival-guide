# Survival-guide commit + push block

## Verification panel (captured 2026-05-02)

```
── 1. AST parse — every Python file modified this session ──
  PASS  tests/bug_bible_regression.py           (974 lines, parses)
  PASS  tests/test_llm_round_robin.py           (30 tests defined)
  PASS  tools/reload_bug_bible.py
  PASS  llm_round_robin/__init__.py
  PASS  llm_round_robin/__main__.py
  PASS  llm_round_robin/config.py
  PASS  llm_round_robin/env.py
  PASS  llm_round_robin/errors.py
  PASS  llm_round_robin/probe.py
  PASS  llm_round_robin/providers.py
  PASS  llm_round_robin/runner.py
  PASS  docs/bonus_normalization_experiment/compare_passes.py

── 2. pytest --collect-only ──
  30 tests collected from tests/test_llm_round_robin.py
  26 tests collected from tests/bug_bible_regression.py
  0 collection errors

── 3. tests/bug_bible_regression.py against survival-guide repo ──
  16 passed, 7 skipped (pack-not-applicable), 3 xfailed (intentional)

── 4. tests/test_llm_round_robin.py ──
  30 passed, 0 failed

── 5. tools/reload_bug_bible.py against BUG_BIBLE.yaml ──
  Total entries: 153
  Phases: 1:4, 2:14, 3:4, 4:13, 5:9, 6:6, 7:15, 8:6, 9:4, 10:7, 11:25, 12:46
  STATUS: OK — schema clean

── 6. llm_round_robin importable + CLI works ──
  python -c "import llm_round_robin"   → imports OK
  python -m llm_round_robin --help     → returns clean usage block

── 7. Generalization audit — chunk-2 entries (this session) ──
  scanned for: OTR_*, BatchHumoRender, SignalLost*, BatchBark, Gemma4*,
               otr_v2, soak_operator, ScriptCritic, ScriptWriter,
               LLMDirector, _consult_round_robin, signal_lost*,
               Astrotech, Arcadia run
  result: 0 leaks across 40 chunk-2 entries
```

## Reviewer findings — disposition

1. **Syntax error in tests/bug_bible_regression.py at lines 975-999** —
   FIXED. The file is now 974 lines, parses clean, no duplicate-paste
   fragment. Confirmed via AST parse + pytest --collect-only above.

2. **PUSH_BLOCK should grow a verification checklist** — DONE (this
   document). Every claim above is reproducible by re-running the
   commands at the bottom of this block.

3. **OTR-narrative leakage in pre-existing entries** — FLAGGED, not
   fixed. Three entries (11.08, 11.09, 11.11) carry `ScriptWriter`,
   `BatchBark`, `LLMDirector` references in their symptom/verify text.
   These entries were promoted in a PRIOR session, not this one. The
   chunk-2 entries promoted this session are clean (audit point 7
   above). Decide separately whether to generalize 11.08/11.09/11.11
   in a follow-up commit — they're not blocking this push.

4. **Reddit post drafts** — UNTOUCHED. `reddit_post.md` and
   `reddit_post_regression.md` were not edited this session. They
   appear in `git status` because they had pre-existing modifications
   before the session started. The push block below explicitly
   excludes them from `git add` so they stay in your working tree
   for separate review.

5. **CHUNK 2 section header in BUG_BIBLE.yaml** — was previously
   `"OTR sprint"`, now reads `"a 2-week production custom-node
   sprint"` (audience-neutral phrasing).

## The push block

Paste into a fresh PowerShell window on Windows.

**Per CLAUDE.md PowerShell handoff rule:** uses bare `cd` (not `cd /d` —
that's cmd syntax), and uses the `py` launcher which ships with every
modern Windows Python install. If `py` isn't available either, the block
falls back to `python`. If neither works, set `$PY` to your Python path
manually (e.g. `$PY = "C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe"`)
before running the rest.

```powershell
# Pick the right Python invocation. `py` ships with the standard Windows
# Python installer; `python` works if Python is on PATH directly.
$PY = if (Get-Command py    -ErrorAction SilentlyContinue) { "py" }
      elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
      else { throw "No Python found on PATH. Install Python or set `$PY = '<path-to-python.exe>'` and re-run." }
Write-Host "Using Python: $PY"

# 1. cd to the repo (bare cd; /d is cmd-only, breaks in PowerShell)
cd C:\Users\jeffr\Documents\ComfyUI\comfyui-custom-node-survival-guide

# 2. Clean up sandbox markers
Remove-Item -Force -ErrorAction SilentlyContinue .sync_check_marker, .reload_clean

# 3. Re-validate locally — every line should match the verification panel above
& $PY -c "import ast; ast.parse(open('tests/bug_bible_regression.py').read()); print('AST: PARSES')"
& $PY -m pytest tests/ --collect-only -q
& $PY -m pytest tests/bug_bible_regression.py --pack-dir .
& $PY -m pytest tests/test_llm_round_robin.py
& $PY tools/reload_bug_bible.py
& $PY -c "import llm_round_robin; print('addon imports OK')"
& $PY -m llm_round_robin --help | Select-Object -First 3

# 4. Stage real changes (skip LICENSE / goofer_video_concat.py CRLF
#    phantom diff per BUG-12.14, and skip reddit_post*.md pre-existing
#    edits — those need a separate audience-reframe pass)
git add `
    .gitignore `
    BUG_BIBLE.yaml `
    README.md `
    PUSH_BLOCK.md `
    tools/ `
    docs/ `
    llm_round_robin/ `
    tests/bug_bible_regression.py `
    tests/test_llm_round_robin.py

# 5. Confirm what's staged before committing
git status

# 6. Commit
git commit -m "Promote 40 class lessons from production sprint; ship llm_round_robin addon

Bible (153 entries, +40 promoted with class lessons generalized for any
ComfyUI custom-node author). Generalization audit: 0 OTR-specific names
in any of the 40 promoted entries.

- Phase 4 widget-drift family (04.07-04.13)
- Phase 5 execution: feature-flag/role-policy decoupling (05.08-05.09)
- Phase 6 caching: empirical model-platform compatibility gate (06.06)
- Phase 7 audio/video (07.11-07.15)
- Phase 8 output_node discipline (08.06)
- Phase 11 LLM (11.12-11.25)
- Phase 12 regression/handoff (12.37-12.46)

Schema: normalized 12.23-12.32 mapping-form to canonical list form;
Pass A normalization (legacy_id quoting, NEW->'' cleanup, tag dedup);
tools/reload_bug_bible.py validator.

Regression suite: fixed four pre-existing dogfooding failures; 16 passed,
7 skipped, 3 xfailed; AST clean, pytest --collect-only reports 0 errors.

llm_round_robin addon: probe-first prune, endpoint-aware dispatch,
capability tags + --needs flag, typed errors, cross-platform env reader,
YAML config with last_reviewed staleness alarm, 30-test pytest suite.

Bonus: docs/bonus_normalization_experiment/ — three-version YAML
normalization comparison harness for readers curious about how different
AI models handle the same refactor task.

Cross-link to BUG-LOCAL-NNN preserved in legacy_id field on every
promoted entry."

# 7. Push main
git push origin main

# 8. Tag v2.1 — the 153-entry bible + llm_round_robin addon shipping point
git tag -a v2.1 -m "v2.1: 153 entries (113 + 40 promoted from production sprint), llm_round_robin addon, schema validator, regression suite green"
git push origin v2.1

# 9. Verify (HEAD lockstep)
git fetch origin main
git log --oneline origin/main -1
git diff HEAD origin/main
git tag -l v2.1
git ls-remote --tags origin v2.1
```

## After-push notes (non-blocking, for follow-up)

- **11.08 / 11.09 / 11.11 generalization** — three pre-existing entries
  cite `ScriptWriter`, `BatchBark`, `LLMDirector`. Future audit: rewrite
  symptom/verify text to use generic role names (e.g. "the writer node",
  "the TTS batch node", "the director node"). Low priority — the class
  lessons themselves are fine; only the example narrative carries the
  specific names.
- **reddit_post*.md** — pre-existing modifications in working tree;
  needs an audience-reframe pass (custom-node authors with AI agents,
  not the personal sprint narrative). Out of scope for this push.
- **`git push` red "NativeCommandError" block** — that's BUG-12.11.
  Look inside the block for the literal `<commit>..<commit>  main ->
  main` line; the push succeeded.
