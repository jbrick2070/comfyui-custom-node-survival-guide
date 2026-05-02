# Round-robin normalization consult — BUG_BIBLE.yaml

## Context

This is a 153-entry knowledge base for ComfyUI custom-node authors at
`https://github.com/jbrick2070/comfyui-custom-node-survival-guide`. Each entry
is a class lesson generalized from real production bugs, in the canonical
schema:

```yaml
- id: "<phase>.<seq>"        # e.g. "04.07"
  phase: <int 1-12>
  area: <kebab- or snake_case area>
  symptom: |
    <what the author sees>
  cause: |
    <why it happens, generalized>
  fix: |
    <how to resolve, generalized>
  verify: |
    <how to confirm resolution>
  tags: [kebab-or-snake-case, ...]
  legacy_id: "BUG-LOCAL-NNN"   # or "" or older bare numeric "55"
```

Phases:
- 01 Bootstrap & Discovery
- 02 Environment & Dependencies
- 03 Registration & Loading
- 04 INPUT_TYPES & Widgets
- 05 Execution Model
- 06 Caching & IS_CHANGED
- 07 Tensors, Audio, Video
- 08 I/O & Output Nodes
- 09 Subprocess & Network
- 10 Safety, Pools, RNG
- 11 LLM-Specific
- 12 Regression, Git, Handoff

Entry counts by phase:
1:4, 2:14, 3:4, 4:13, 5:9, 6:6, 7:15, 8:6, 9:4, 10:7, 11:25, 12:46.

A schema validator (`tools/reload_bug_bible.py`) already enforces:
- required keys present
- no duplicate IDs
- tags are kebab-case OR snake_case (snake_case retained when the tag is a
  literal Python symbol like `output_node`, `is_changed`, `validate_inputs`)
- legacy_id matches `BUG-LOCAL-NNN`, `\d+(\.\d+)?`, `NEW`, or empty
- no deprecated mapping-form entries

A first normalization pass was applied (Claude / Opus class):
- N1 typo fixes
- N2 tag de-duplication within entries
- N3 `legacy_id: "NEW"` → `""`; bare-numeric legacy_ids quoted as strings
- N4 trailing whitespace stripped
- N6 area vocabulary normalization (e.g. `audio-engine` → `audio`)
- N8 collapsed runs of 3+ blank lines

## Your job

You are reviewing the YAML for a SECOND normalization pass that the first
pass missed. Your output should be implementable as a unified diff.

Specifically:

1. **Tag style audit.** Scan for tag-style inconsistencies. If two
   semantically-identical tags exist in different forms (e.g. `widget-default`
   on one entry and `widget_default` on another, or `bom` vs `bom-marker`),
   recommend one canonical form per concept. List `(canonical, list of variants
   to retire, list of entry IDs that need updating)`.

2. **Phase grouping.** Are there entries whose `phase:` value seems wrong
   given their content? List `(entry_id, current_phase, recommended_phase,
   one-line reason)`. Be conservative — only flag entries where the mismatch
   is obvious.

3. **Generalization audit.** Are there entries whose `symptom` / `cause` /
   `fix` text still contains OTR-specific narrative that escaped
   generalization? (Look for hardcoded OTR-specific names like `OTR_*`,
   `BatchHumoRender`, `SignalLost*`, references to specific episodes or runs,
   etc.) List `(entry_id, offending phrase, suggested generalization)`.

4. **Cross-link audit.** Are there entries that should reference each other
   in their `cause` or `fix` text? E.g. 04.07 + 04.09 + 04.12 + 04.13 are all
   about widget-drift mapping; if one mentions a class lesson that's covered
   in another, a "see also <id>" reference is helpful. List `(entry_id, "see
   also <other_id>", brief reason)`.

5. **Coverage gaps.** What classes of ComfyUI custom-node bugs that you've
   seen in the wild are NOT represented in this 153-entry bible? List
   candidate new entries as `(proposed_id_range, one-line title, why a custom-
   node author would hit this)`.

6. **Any other normalizations** the first pass missed that you'd recommend.

## Output format

Strict markdown sections matching the numbered list above. Be terse —
target 800-1500 words total, not an essay. Cite specific entry IDs. If
section 5 (coverage gaps) doesn't surface anything, say "no gaps spotted"
rather than padding.

Do NOT try to rewrite the whole bible. The goal is a focused, actionable
diff list.

## The bible to review

The file lives at `BUG_BIBLE.yaml` in the repo root. It's 153 entries and
~3000 lines, so I won't paste it inline — but you can reason about it from
the schema + counts above PLUS your knowledge of ComfyUI custom-node
authoring patterns (which you've trained on extensively). Where a specific
entry's content matters for your recommendation, cite the ID and your best
guess at what it covers; the operator will look it up in the file when
applying your suggestions.
