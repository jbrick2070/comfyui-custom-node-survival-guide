# Survival Guide Roadmap

**Repo:** `comfyui-custom-node-survival-guide` | **Owner:** Jeffrey A. Brick | **Last refactored:** 2026-05-02

Forward-only plan for **v2.2**. Single target — no v2.3+ horizon section. v2.1 shipped with 153 entries + the addon + schema validator. v2.2 adds the next batch of class lessons from accumulated dogfooding bug logs plus the tooling improvements below.

---

## When v2.2 work starts

**Trigger:** dogfooding repos accumulate a meaningful batch of `Bible candidate: yes` + `[FIXED]` + production-verified entries worth promoting. No firm count, but rough rule: 15-20 promotable entries is enough to justify a v2.2 cut.

**Primary input:** OTR's `docs/BUG_LOG.md` (the bible's main dogfooding source). Any other custom-node author who wants their bug log mined for class lessons can submit theirs as input too — that's how this repo grows.

**Output:** v2.2 release with the new entries + tooling improvements below.

---

## v2.2 scope

### Bible scale ergonomics — `tools/grep_symptom.py`

153 entries is the scale where "skim `symptom:` fields" stops being skimming. The README's agent prompt currently tells the AI agent to load `BUG_BIBLE.yaml` into context and match the user's symptom — at 153 entries, that's a haystack.

**Build:** stdlib-only Python script that takes a search string (and optionally `--phase` / `--tag` filters) and returns matching entry IDs + 1-line summaries. Fuzzy-match across `symptom`, `cause`, and `tags`. Top-N output.

**Acceptance:**
- `python tools/grep_symptom.py "vram leak threadpool"` returns the matching Phase 12 entry's ID + 1-line summary.
- No extra deps — AI agents can call it without `pip install`.
- README's agent prompt updated to recommend `grep_symptom.py` as the FIRST step before loading the YAML into context.

### New class lesson: "static analysis can confidently prescribe wrong fixes"

Surfaced 2026-04-15 in OTR work — captured as memory but never promoted to the bible. The class lesson: ComfyUI STRING type is permissive; a type-tag match in static analysis doesn't mean "this is the right input shape." AI-agent QA tools that read the graph statically and prescribe rewires can be confidently wrong. Always read the source of the target node's output before applying a rewiring suggestion.

**Where it fits:** Phase 4 (widget / type) most likely; Phase 12 (regression / handoff) as fallback.

**Acceptance:**
- New YAML entry following the schema: `id`, `phase`, `area`, `symptom`, `cause`, `fix`, `verify`, `tags`.
- Static-analysis-checkable subset (if any) added to `tests/bug_bible_regression.py`.
- README entry count bumped (154+).
- Three-file contract honored.

### Promote accumulated bug-log candidates

Walk every `Bible candidate: yes` + `[FIXED]` entry in the dogfooding bug logs (OTR primary, plus any external submissions). For each:

1. Confirm the fix held in production (≥1 clean real-run after the fix landed).
2. Generalize the symptom / cause / fix into class-lesson form. NO project-specific names, NO project-specific file paths in the wording. Test: would a custom-node author with no knowledge of the source project understand the lesson?
3. Add YAML entry to `BUG_BIBLE.yaml`.
4. If statically checkable, add regression test to `tests/bug_bible_regression.py`.
5. Update README entry count + coverage table.
6. Run `python tools/reload_bug_bible.py` to validate.

**Acceptance:** every promoted entry passes the "class lesson, not project narrative" test. Three-file contract honored on each. Source bug logs annotated with the new bible IDs in the `Bible candidate:` field for traceability back to the originating fix.

### Audit v2.1 entries for class-lesson compliance

The v2.1 push promoted 40 entries fast (2-week sprint). Spot-check before any further work piles on so the bible's "class lesson" promise holds. Highest-risk-of-project-narrative-leak candidates:

- Phase 12 dedup foreign-key — verify wording is "when a merge step removes a row in any pipeline with referencing tables," NOT "when <project>'s assembler removes a row."
- Phase 11 length-prompt floor+ceiling — verify wording is generic ("for short LLM targets, write..."), not project-specific.
- Phase 11 parser narration-leak — confirm symptom is generic, not project-character-named.
- Phase 4 widget drift batch (7 entries) — confirm none reference project-specific widget names.
- Phase 7 motion-onset pad — already reads generic; just confirm.

**Acceptance:** every v2.1 entry passes a one-line test: "would a custom-node author with NO knowledge of the source project understand the class lesson?" Any failures get rewritten in place; YAML revalidates.

### Auto-generate regression-test stubs from new YAML entries

Three-file contract currently requires manually mirroring each new entry → test stub. Lower the contribution friction with a scaffolding tool.

**Build:** `tools/scaffold_test.py` reads a YAML entry by ID, parses the `verify:` field, and emits a stub `def test_bug_<id>_<short_slug>(pack_dir):` block in `tests/bug_bible_regression.py` (commented-out body with the verify text + a TODO marker). Author fills in the assertion logic.

**Why:** when v2.2 promotes a batch of bug-log entries, scaffolding the test stubs in one pass is faster than hand-writing each. Also lowers the friction for community PRs.

**Acceptance:**
- `python tools/scaffold_test.py --id 11.27` appends a stub test to the right phase block in `bug_bible_regression.py`.
- Stub fails by default (so it can't ghost-pass) — body is `pytest.skip("verify: <text> — fill in assertion")`.
- README's three-file-contract section updated to mention the scaffolding tool.

### Bonus folder placement cleanup

`docs/bonus_normalization_experiment/` is currently mentioned in the README and `reddit_post_v2_1.md`. It dilutes the pitch — research curiosity, not the headline. Keep the folder (it's interesting), but:

- Remove from README's main flow.
- Omit from any v2.2 Reddit push.
- If posting separately, give it its own small Reddit post on a different week ("here's how three frontier models handled the same YAML refactor task — comparison harness inside").

**Acceptance:** README no longer references the bonus folder in the main quick-start flow. Folder still ships, with its own README explaining context.

---

## v2.2 Reddit push strategy (when v2.2 ships)

Three angles drafted in `reddit_post_v2_1.md`. v2.2 will be a smaller bump — pick one strong angle, don't repeat all three.

- **Lead with angle 2 (addon-first → r/LocalLLaMA / r/ChatGPTCoding / r/cursor)** — fresh audience, addon stands alone as a shipping artifact, class lesson (silent stale-fallback rotation in hardcoded ladders) is universal.
- **Optional follow-up: angle 3 abridged ("what shipping a 16 GB Blackwell custom-node pack taught me")** to r/comfyui — only if v2.2 has a strong cross-pack dogfooding angle (not currently planned for v2.2).
- **Skip angle 1** — r/comfyui already saw v2.1; v2.2 doesn't need a phase-by-phase rehash.

---

## Maintenance rules (do not relitigate)

- Three-file contract: README + YAML + tests. Every update touches all three.
- `python tools/reload_bug_bible.py` after every edit. Schema validator is the gate.
- Class lesson, not project narrative. Every entry must be applicable to ANY custom-node author, not just OTR.
- Promote bibliography candidates from external repos ONLY after the originating fix is verified in production AND the lesson has been confirmed generalizable (not just "it worked once for me").
- Never use the word "dummy" in YAML, tests, or docs. Use `placeholder` / `stub` / descriptive name.
- MIT license — never vendor GPL code into this repo.
- Do NOT push from the AI agent's shell session — Windows credential manager hangs (BUG-12.34). Always hand a PowerShell block with `cd` first.

---

## References

- `BUG_BIBLE.yaml` — 153-entry machine-readable bible (v2.1 baseline)
- `tests/bug_bible_regression.py` — static-analysis pytest suite
- `llm_round_robin/` — drop-in consult addon
- `tools/reload_bug_bible.py` — schema validator
- `docs/llm_round_robin_explainer.md` — addon design rationale
- `reddit_post_v2_1.md` — Reddit post drafts (3 angles, v2.1 baseline)
- Primary dogfooding source: OTR repo (https://github.com/jbrick2070/ComfyUI-OldTimeRadio) — `docs/BUG_LOG.md` is the main input to the v2.2 promotion pass
- External dogfooding submissions welcome — any custom-node author with `Bible candidate: yes` entries can submit their bug log for class-lesson promotion
