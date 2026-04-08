# ComfyUI Custom Node & Workflow JSON Development Best Practices

**By Jeffrey A. Brick** · SIGNAL LOST v1.2 Edition · April 2026

> Battle-tested guidance for building ComfyUI custom nodes, maintaining workflow JSONs, and keeping GPU-heavy pipelines stable. Every section here exists because of a specific class of "ghost bug" that cost real hours to diagnose — usually rooted in ComfyUI's import lifecycle, execution caching, workflow serialization, LLM token budgeting, or content-pipeline edge cases.

> **Full disclosure:** I am not a coder. Every line of code in my ComfyUI node packs was written by Claude (Anthropic's AI). The v1.0 guide was built across several weeks of Claude Code sessions. The v1.1 SIGNAL LOST Edition was built in a single Claude Cowork session. The v1.2 edition folds in lessons from shipping ComfyUI-OldTimeRadio v1.2.0 — narrative-engine bug fixes, token-budget decapitation traps, content-filter rotation patterns, fuzzy-match leak guards, statistical regression harnesses, GitHub lockstep verification protocol, and the discipline of writing roadmaps for the *next* AI session rather than just for humans. I brought the creative vision and domain knowledge; Claude brought the code. The bugs and lessons are real regardless of who typed them.

### Want to feed your AI assistant even more context?

Check out the **[Detailed Guide (60 sections)](DETAILED_GUIDE.md)** — a deep-dive companion to this README covering every lesson learned across the full development cycle. Fair warning: it's AI-assisted, opinionated, and the ComfyUI landscape moves fast, so take it with a grain of salt. But if it saves you even one three-hour debugging session, it paid (it's free anyway!)  for itself.

---

## Who this is for

- Custom node authors (first-time or experienced)
- Workflow JSON maintainers and pipeline builders
- Anyone debugging "it looks right but doesn't work" in ComfyUI

---

## Purpose and scope

ComfyUI loads custom nodes by scanning `custom_nodes/` at startup and importing each module's `__init__.py`. Nodes register when a module exports `NODE_CLASS_MAPPINGS`. That single architectural fact explains most "it still runs the old code" reports: if the running process hasn't re-imported your module, your change didn't take effect.

ComfyUI also caches node outputs and can skip execution when it decides outputs haven't changed. You can control this via `IS_CHANGED`. Workflow JSON follows a published schema, but real compatibility problems come from how node identity and widget state are serialized.

---

## Quick-start survival guide

Eighteen high-leverage habits that prevent most custom-node failures.

### 1. Treat `custom_nodes/` as a deployment target, not your workspace

ComfyUI discovers and imports from `custom_nodes/` at startup. Keep a separate source repo and sync into `custom_nodes/`. This makes rollbacks clean and prevents accidental live-tree edits.

### 2. Assume "no restart" means "no code change"

ComfyUI imports modules at startup. Changed Python code is not picked up until you restart the process. No exceptions.

### 3. Sync the whole node package, not just the file you touched

`__init__.py`, helper modules, JSON examples, UI assets — they all participate. A partial sync leaves mismatched modules that create failures indistinguishable from logic bugs.

### 4. Know what `__pycache__` is and when to nuke it

Python caches compiled bytecode in `__pycache__/` to speed imports. When copying files across directories, swapping branches, or moving packages between paths, stale `.pyc` files can make "it looks changed but behaves unchanged" your new reality. Delete `__pycache__/` when in doubt.

### 5. Install dependencies into the exact Python ComfyUI is running

On Windows Portable, ComfyUI ships with an embedded interpreter at `python_embeded/`. That's what runs the app. Use it for installs:

```bash
python_embeded/python.exe -m pip install your-package
```

System Python installs won't be visible to the runtime.

### 6. Treat `NODE_CLASS_MAPPINGS` keys as permanent public IDs

Those unique name strings are how ComfyUI identifies your node — and how every saved workflow references it. Change them after publishing and you break every workflow that used the old name.

### 7. Design widget evolution like a migration problem

**This is the single most under-documented gotcha in ComfyUI:** workflow JSON stores widget values by **position index**, not by name. Add or reorder widgets in `INPUT_TYPES` and old workflows silently map prior values onto the wrong widget. Treat input changes like database schema migrations, not casual edits. When you must add a widget, write a script that walks every workflow JSON in your repo and pads the `widgets_values` array for the affected node type at the exact insertion position. See "Workflow JSON stability" below for the full recipe.

### 8. Understand caching, or you'll debug "missing execution" forever

ComfyUI caches outputs and only re-executes nodes it believes might produce different results. If your node isn't running:

- Implement `IS_CHANGED` — it receives the same args as your `FUNCTION` and returns a value compared to the previous run.
- `float("NaN")` always compares as "not equal" and forces re-execution.
- Don't return a simple boolean — that doesn't behave the way you'd expect.

### 9. Honor ComfyUI datatype contracts exactly

Example: the `AUDIO` type is a `dict` with a `waveform` tensor shaped `[B, C, T]` and an integer `sample_rate`. Pass a raw tensor or invent your own structure and you'll break every downstream node that correctly follows the contract.

### 10. Be precise about what "free VRAM" means

`torch.cuda.empty_cache()` releases *unoccupied cached* memory from PyTorch's allocator. It does **not** free memory still referenced by live tensors or models, and it doesn't increase memory available to PyTorch — it mainly helps with fragmentation and `nvidia-smi` reporting.

In long-running sessions, you must delete references to GPU objects first, *then* call `empty_cache()`. The pattern is: load → run → delete references → `empty_cache()`.

### 11. Never share an RNG between reproducibility and variance

If your node calls `random.seed(x)` anywhere — commonly to make outputs reproducible from a fingerprint or user-supplied seed — **every subsequent `random.random()` call in the same process becomes deterministic**. Any probabilistic feature in the same execution (easter eggs, variance rolls, jitter, Monte Carlo noise) will silently freeze into an always-on or always-off state for any given input. The RNG is process-global; seeding it is not a local operation. Keep determinism and variance in separate RNG streams. See "RNG, determinism, and variance" below for the fix.

### 12. Priority reservation needs two-pass iteration

When you assign items from a shared pool (voice presets, GPU streams, ports, cache slots) and some recipients require **locked** assignments while others draw from the same pool, process the locked recipients first. A single-pass loop in dict-insertion order will let a regular recipient claim a locked item before the priority branch runs, causing a silent collision. Two-pass iteration — priority keys first, regular keys second — is the only safe pattern. See "Silent failure triage" below.

### 13. Size LLM revision tokens from draft length, not target params

If your pipeline has a critique-and-revise loop that re-runs an LLM over a generated draft, **size the revision token budget from the actual draft character count, not from the original `target_words` parameter**. The original target was an instruction; the draft is the reality. A revision pass budgeted at `target_words × 2` will silently truncate any draft that overshot the target — and creative LLMs routinely overshoot. The truncation lands inside the final scene because that's where the script ends, which is exactly where readers and listeners feel the damage.

Symptom: every reviewer tells you the same thing — *"the ending is weak"* — even after you fix the prompt, fix the structure, and fix the outline. The endings aren't weak. They're missing. The revision pass got decapitated mid-Scene 4.

Formula that works:

```python
draft_token_estimate = int(len(draft_text) / 3.5)   # ~3.5 chars/token English
revision_tokens = max(
    int(draft_token_estimate * 1.25),                # 25% headroom
    int(target_words * 2.0),                         # never below original budget
    2048,                                            # absolute floor
)
revision_tokens = min(revision_tokens, 8192)         # absolute ceiling
```

See "LLM token budgets and revision passes" below.

### 14. Replace `[BLEEP]` censors with rotating euphemism pools

A content filter that substitutes `[BLEEP]` (or any single sentinel string) into output is fine for moderation but ugly for narrative pipelines — it announces "this was censored" every time it fires. Replace it with a **rotating pool of period-appropriate euphemisms** and preserve capitalization style. For an old-time-radio pipeline you'd cycle through *Stars above*, *Jiminy*, *Great Scott*, *Gadzooks*, *Holy mackerel* — for a children's pipeline you'd cycle through *Gosh*, *Heck*, *Goodness*. The substitution disappears into the prose instead of breaking immersion. Same defensive value, zero narrative cost.

### 15. Use fuzzy-match leak guards instead of hardcoded blocklists

When an LLM occasionally types the wrong proper noun inside dialogue body — e.g. a character named VEX gets addressed as "Rex" because the model was pulled toward a stock-name attractor — the wrong fix is a hardcoded blocklist of stock names. The right fix is structural:

1. Extract the **real character roster** from your script's `[VOICE: NAME, ...]` tags (or whatever your authoritative character markup is).
2. Scan the dialogue body for capitalized direct-address tokens that aren't in the roster.
3. Use `difflib.get_close_matches(token.upper(), roster_list, n=1, cutoff=0.55)` to fuzzy-match each unknown token to the closest real character name.
4. Replace and log.

Zero hardcoded names anywhere in your codebase. The guard adapts automatically as cast pools grow. "Rex" becomes "Vex" without you ever telling the code that "Rex" exists. See "Procedural content with structural guards" below.

### 16. Pool sizing must exceed maximum simultaneous demand

When a procedural assignment pool (voice presets, port slots, cache shards, character names) draws from N distinct values and an episode/run can demand up to M assignments, **N must exceed M** or you'll silently produce duplicates. The hidden trap is that N often *does* exceed M for the average case but fails for the long tail — e.g., a TTS pipeline with 9 voice presets has plenty of headroom for a 4-character episode but breaks down as soon as a 4-female cast forces the gender-filtered pool to its limit.

Audit pool sizing per **filtered subset**, not per total. If you have 9 voice presets but only 2 are female-classified, your effective female pool is 2, not 9. A 3-female cast will collide. Reclassify androgynous slots, expand the pool, or accept (and explicitly log) duplication — but never let it happen silently.

### 17. Every randomized feature needs a statistical regression test

If your code has a probabilistic feature (an easter-egg trigger, a random selector, an A/B sampler, a coin flip) and you ever change anything near it — refactor an RNG, swap a library, edit a threshold constant — you must be able to *prove* the feature still fires at the rate you expect. Eyeballing a few runs is not enough. Build a tiny test harness:

```python
# tests/probability_check.py
from secrets import SystemRandom

TARGET_RATE = 0.11
N_TRIALS = 10_000
TOLERANCE = 0.015  # ±1.5%

def main():
    rng = SystemRandom()
    hits = sum(1 for _ in range(N_TRIALS) if rng.random() < TARGET_RATE)
    observed = hits / N_TRIALS
    delta = abs(observed - TARGET_RATE)
    print(f"Observed: {observed:.2%}  delta: {delta:.2%}")
    assert delta <= TOLERANCE, f"FAIL — delta {delta:.2%} exceeds {TOLERANCE:.1%}"

if __name__ == "__main__":
    main()
```

Run it before every commit that touches RNG-adjacent code. Dead simple, zero dependencies, catches RNG poisoning instantly.

### 18. Verify GitHub HEAD lockstep against local after every push

Pushing to a remote is not the same as the remote actually receiving your changes intact. Windows line-ending conversion (CRLF/LF), credential helper hangs, partial commits, branch/main confusion, and silent encoding corruption are all real, all common, and all invisible until a downstream user complains that your "fix" doesn't work because they pulled a corrupted file.

After every push, verify lockstep:

1. Fetch the remote branch
2. Diff remote HEAD against local HEAD — must be empty
3. Scan repo for 0-byte files (`find . -name "*.py" -size 0`)
4. Scan for BOM corruption at file starts (`head -c 3 *.py | hexdump`)
5. Verify the specific commit SHA you intended to push appears at remote HEAD
6. Confirm node registrations still resolve (`grep NODE_CLASS_MAPPINGS __init__.py`)

Bake this into a one-line PowerShell or bash function and run it every single time. Trust git but verify the wire.

---

## Mental model of ComfyUI execution

ComfyUI is a **cached dataflow graph executor**. It figures out which nodes might produce different output, executes only those (plus always-run "output" nodes), and reuses cached outputs when inputs appear unchanged.

This is a major performance feature, but it's surprising during development: "I clicked Queue again" is not the same as "my node executed again."

Three pillars matter for node authors:

**Import lifecycle is process-scoped.** ComfyUI scans `custom_nodes/`, imports modules, and runs `__init__.py` once at startup. If import fails, it logs the error and continues. This is why restarts are mandatory for code iteration.

**Caching is explicit and customizable.** `IS_CHANGED` receives the same arguments as your `FUNCTION` and returns a value compared to the previous run. Return `float("NaN")` to force re-execution. Return a deterministic hash when you want caching to work.

**Workflow serialization is fragile by design.** Node identity and widget state are stored in ways that break silently when you change inputs without migration logic.

---

## Silent failure triage

Most "this makes no sense" bugs fall into four buckets. Classify fast, fix fast.

### Stale code — import didn't change

You edited Python but behavior didn't change. The running process hasn't imported your new code.

**Fix:** Restart ComfyUI. If you're copying across directories or switching branches, delete `__pycache__/` first.

### Stale state — node didn't execute

Breakpoints don't hit, logs don't appear. ComfyUI skipped your node because output caching decided nothing changed.

**Fix:** Implement `IS_CHANGED`. During development, return `float("NaN")` to force execution. Replace with deterministic logic before shipping.

### Stale UI mapping — workflow loads but values are wrong

Your node executes but gets nonsensical parameters — wrong booleans, shifted strings. Widget values in saved workflow JSON are mapped by position index.

**Fix:** Check whether you've added, removed, or reordered widgets since the workflow was saved. If so, the workflow JSON is out of sync. Update it or implement migration logic. See "Workflow JSON stability" for the migration recipe.

### Stale allocation — two recipients share a pool resource

Your node runs, no errors are thrown, but downstream output shows two recipients with the same supposedly-unique resource — two characters with the same voice, two requests routed to the same port, two caches writing to the same slot. The pool allocator iterated in dict-insertion order, and a regular recipient drew the resource before a priority recipient's lock was applied.

**Fix:** Two-pass iteration. Process priority recipients first so their reservations land in the used-set, then process regular recipients:

```python
all_keys       = list(assignments.keys())
priority_keys  = [k for k in all_keys if is_priority(k)]
regular_keys   = [k for k in all_keys if not is_priority(k)]

used_pool = set()
for key in priority_keys + regular_keys:
    assign_from_pool(key, used_pool)
```

Never rely on dict ordering to enforce priority. Single-pass loops over shared pools are a recipe for silent collisions that only show up in final output, not in logs.

---

## RNG, determinism, and variance

ComfyUI custom nodes frequently want **both** reproducibility (same seed → same output) and **variance** (probabilistic features that stay genuinely random across repeated runs of the same config). These two goals are fundamentally incompatible if they share a single RNG stream.

### The trap

Python's module-level `random` is **process-global**. When your node calls `random.seed(fingerprint)` to make outputs reproducible from a seed or input hash, every subsequent call to `random.random()`, `random.choice()`, etc., anywhere in the same process — including inside unrelated easter eggs, variance rolls, jitter, and Monte Carlo features — becomes deterministic for that run. If the fingerprint is the same, the "random" probabilistic feature fires the same way every time. If the fingerprint differs, the feature still fires based on the sequence, not on genuine OS entropy.

The symptom is a probabilistic feature that appears **frozen** — either always on or always off — for any given widget configuration. You will chase this bug for hours thinking the logic is wrong. The logic is fine. The RNG is poisoned.

### The fix: separate RNG streams

For any probabilistic feature that must stay genuinely random across repeated runs of the same config, create a dedicated RNG stream using `random.SystemRandom()` at module level. It draws from OS entropy (`os.urandom`) and is completely immune to `random.seed()`:

```python
from random import SystemRandom

# Module-level, OS-backed entropy.
# Immune to random.seed() called anywhere else in the process.
_VARIANCE_RNG = SystemRandom()

def maybe_trigger_easter_egg():
    if _VARIANCE_RNG.random() < 0.11:
        return True
    return False
```

For reproducibility, keep using the seeded module-level `random` as you normally would. The two streams never interact.

### The general principle

Determinism and variance must live in separate RNG streams. If you want both, you need two RNGs. This applies beyond easter eggs — any time you mix reproducible generation with stochastic sampling (jitter, dropout, noise injection, A/B selection), audit your RNG sources and make sure the variance stream isn't being silently seeded upstream.

### Statistical regression harness for probabilistic features

The bug above is invisible to spot-checking. You will run your easter egg ten times, see it never fire, and assume the threshold is correct. The only way to catch RNG poisoning is to run the same probabilistic check thousands of times in a tight loop and assert the observed rate matches the target within tolerance.

Ship a test harness alongside any probabilistic feature:

```python
# tests/lemmy_rng_check.py
"""Lemmy RNG sanity check — verifies the 11% hit rate is statistically intact."""
from secrets import SystemRandom

LEMMY_RATE = 0.11
N_TRIALS = 10_000
TOLERANCE = 0.015  # ±1.5%

def main():
    rng = SystemRandom()
    hits = sum(1 for _ in range(N_TRIALS) if rng.random() < LEMMY_RATE)
    observed = hits / N_TRIALS
    delta = abs(observed - LEMMY_RATE)
    print(f"Lemmy RNG sanity check — {N_TRIALS:,} trials")
    print(f"  Target rate:   {LEMMY_RATE:.1%}")
    print(f"  Observed rate: {observed:.2%}  ({hits:,} hits)")
    print(f"  Delta:         {delta:.2%}  (tolerance {TOLERANCE:.1%})")
    if delta <= TOLERANCE:
        print("  STATUS: PASS")
        return 0
    print("  STATUS: FAIL — RNG is biased")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
```

Run it before every commit that touches RNG-adjacent code. Ten thousand trials runs in well under a second. The tolerance band (`±1.5%`) is wide enough to never false-positive on healthy RNG, narrow enough to catch a poisoned stream that's frozen at 0% or 100%. If the harness ever fails, you have proof the RNG is broken before downstream features misfire in production.

---

## LLM token budgets and revision passes

If your node pack uses an LLM in a generate-then-revise loop (script writers with self-critique, image-prompt expanders with refinement passes, structured-output extractors with validation retries), token budgeting for the **second** pass is the single most common source of silent quality regressions.

### The decapitation trap

The naive approach is to size the revision call from the same parameters as the original draft call:

```python
# WRONG
revision_tokens = max(int(target_words * 2.0), 1024)
```

This breaks every time the LLM overshoots its target word count — which creative LLMs do constantly. A draft told to produce ~1000 words may produce 1400 (or 1800, or 2200) because the prompt structure rewarded depth. The revision pass gets 2000 tokens. The draft is ~3500 tokens. The revision generates the first 2000 tokens of the revised script and then **stops mid-sentence**, usually inside the final scene.

The downstream pipeline cleanly accepts the truncated revision because the structural validators check things like "are there voice tags" and "does the script parse" — both true. The script that ships is missing its ending. Reviewers will tell you the ending is weak. They are wrong about the cause but right about the symptom.

### The fix: size from draft length, not target params

```python
# RIGHT
draft_token_estimate = int(len(draft_text) / 3.5)   # ~3.5 chars/token English
revision_tokens = max(
    int(draft_token_estimate * 1.25),                # 25% headroom
    int(target_words * 2.0),                         # never below original budget
    2048,                                            # absolute floor
)
revision_tokens = min(revision_tokens, 8192)         # absolute ceiling
log.info("[Revision] Token budget: %d (draft_est=%d, target_words=%d)",
         revision_tokens, draft_token_estimate, target_words)
```

Three things matter here:

1. **The estimate is based on the draft, not the prompt.** Whatever the draft actually produced is the floor for the revision.
2. **The 25% headroom absorbs LLM tokenizer variance** — different tokenizers split English at different rates, and the revision will rarely need *less* room than the draft.
3. **The log line** tells you exactly what budget got computed, so when you see truncation in production you can diff `draft_est` against the actual draft and find the math error in seconds instead of days.

### The general principle

Any LLM call that operates over previously-generated content needs to size its output budget from the **content**, not from the original generation params. The original params represent intent; the content represents reality. Budget for reality.

---

## Procedural content with structural guards

When a content pipeline assembles output from procedural pools (character names, location names, prop lists, slang vocabulary), the LLM step in the middle will occasionally leak the wrong proper noun into the wrong slot — mentioning a character by a name that isn't on the cast sheet, or referencing a location that wasn't in the world bible. The temptation is to add a hardcoded blocklist of "leaked" names. **Don't.** Blocklists rot, blocklists offend the procedural design, and blocklists multiply forever as new leaks are discovered.

The right pattern is structural fuzzy-matching against your authoritative roster:

```python
import difflib, re

# After LLM generates the script:
roster = set(re.findall(r'\[VOICE:\s*([A-Z][A-Z0-9_]+)\s*,', script_text))
roster_list = sorted(roster)
leaks_fixed = 0

# Match capitalized direct-address tokens in dialogue body
addr_pat = re.compile(r'(?<=[,\s])([A-Z][a-z]{2,7})(?=[.,!?\s])')

# Common English words that look like names but aren't
COMMON_WORDS = {
    "the", "and", "but", "for", "with", "from", "into", "that", "this",
    "then", "than", "when", "what", "will", "were", "been", "have", "just",
    "only", "some", "such", "very", "now", "yes", "no", "ok", "sir",
    "doctor", "captain", "commander", "listen", "look", "hey", "wait",
    "stop", "please", "thanks", "maybe", "never", "always",
}

def fix_leak(m):
    nonlocal leaks_fixed
    token = m.group(1)
    upper = token.upper()
    if upper in roster:
        return token  # legit
    if token.lower() in COMMON_WORDS:
        return token  # not a name
    match = difflib.get_close_matches(upper, roster_list, n=1, cutoff=0.55)
    if match:
        leaks_fixed += 1
        return match[0].title()
    return token

script_text = addr_pat.sub(fix_leak, script_text)
if leaks_fixed:
    log.warning("NameLeakGuard: repaired %d leak(s) — roster=%s", leaks_fixed, roster_list)
```

The cutoff value (`0.55`) matters: too low and you'll false-positive on real proper nouns; too high and you'll miss obvious typos. Tune by running on archived output and watching the warnings.

### Why this beats blocklists

- **Zero hardcoded names** in your codebase. Procedural design stays pure.
- **Adapts automatically** as cast pools grow. New names need no maintenance.
- **Logs the repair** so you can audit what the LLM was leaking and why.
- **Falls back gracefully** — if difflib finds no close match, the token passes through untouched, so you never corrupt legitimate proper nouns the LLM legitimately invented.

### The general principle

Whenever you would reach for a hardcoded blocklist, ask whether the *real* set you care about exists somewhere in your data already (a roster, a manifest, a schema). If it does, use it as a positive whitelist with fuzzy fallback for typos. The blocklist is almost always the wrong shape for the problem.

---

## Roadmaps as AI session continuity

This is a workflow lesson, not a code lesson, but it has saved more hours than any single bug fix in this guide.

When you build a node pack across multiple AI-assisted sessions — Claude Code, Claude Cowork, Cursor, Aider, whatever — your roadmap document is **not just for humans**. It's the handoff brief for the *next* AI conversation that opens your repo with no prior context. Every minute the next session spends rediscovering "where are we, what shipped, what's queued, what are the standing rules" is a minute of context budget burned on archaeology instead of work.

Write your `ROADMAP.md` (or equivalent) with a **NEW CONVERSATION HANDOFF** section at the top, structured for a cold-start AI:

```markdown
## 🤖 NEW CONVERSATION HANDOFF — READ THIS FIRST

If you are a fresh AI assistant opening this repo with no prior conversation
context, this section is your continuity brief. Read it before doing anything else.

### Where we are (end of session YYYY-MM-DD)
- Current shipped version + tag + commit SHA
- What landed in the most recent commits, with file paths and line refs
- Branch state (what's on main, what's on feature branches, what's merged)

### What's queued for next session
- Top priority feature with full design spec (not just a one-liner)
- Where in the codebase to plug it in (file + approximate line number)
- Any dependent items already scoped

### Standing rules (user preferences — DO NOT VIOLATE)
- Code style preferences
- Forbidden patterns (hardcoded lists, curse words, etc.)
- Operational constraints (always hand off PowerShell blocks, always
  verify GitHub lockstep, always run regression X before declaring done)

### First moves for next session
1. git status / git pull
2. Branch checkout
3. Specific build targets in order
4. Specific tests to run
5. Specific verification steps
```

The cost is ~10 minutes of writing at the end of a session. The savings on the next session's first 30 minutes is dramatic — instead of "let me explore the repo and figure out what's going on" you get straight to "I read the handoff, here's the PowerShell block to branch and start work." Treat the roadmap as a structured prompt for your future AI collaborator. It is one.

---

## Architecture and deployment workflow

Keep a clean separation between development source and ComfyUI runtime:

```
your-repo/
├── src/your_pack/          # Your working tree (what you edit)
├── sync.sh (or sync.bat)   # Copies into custom_nodes/your_pack/
├── example_workflows/       # Versioned JSON workflows
└── docs/                    # Node-specific help pages
```

### The disciplined change loop

1. Edit in your source tree.
2. Sync the **full package** into `custom_nodes/`.
3. Delete `__pycache__/` if you're seeing inconsistent behavior.
4. Restart ComfyUI.

On **Windows Portable**, always use the embedded interpreter (`python_embeded/python.exe`) for dependency installs. Installs into system Python won't affect the runtime.

---

## Workflow JSON stability and compatibility

`NODE_CLASS_MAPPINGS` keys are durable public identifiers. They're not just internal plumbing — every saved workflow references them. Treat them as permanent once published.

Widget evolution is the other major compatibility axis:

- **Widget values are stored by position index, not name.** Adding, removing, or reordering widgets is a breaking change for existing workflows.
- If you must refactor inputs, treat it like schema migration. Provide a migration path or version your node.

ComfyUI also supports hidden inputs (`PROMPT`, `EXTRA_PNGINFO`, `UNIQUE_ID`) via the `hidden` key in `INPUT_TYPES`. These are useful for caching namespacing, metadata embedding, and cross-node coordination — but they tie you to ComfyUI's server contract, so keep them stable.

### The widget migration recipe

Adding a single new widget to `INPUT_TYPES` shifts every subsequent widget's index by one. Every workflow JSON that references your node must have a new entry inserted into its `widgets_values` array at the exact insertion position, or the node will run with garbage inputs and no error — booleans passing through as strings, dropdowns reading the wrong slot, silent data corruption all the way through the pipeline.

The safe migration procedure:

1. **Add the widget to `INPUT_TYPES`** in the position you want it to occupy. Note the zero-based index.
2. **Write a migration script** that walks every workflow JSON in your `workflows/` directory (and any examples in `README.md` or docs), finds nodes with the target `type`/`class_type`, and inserts the new default value into each `widgets_values` array at the same index.
3. **Verify every workflow** by computing `expected = len(required) + len(optional)` from your `INPUT_TYPES` definition and asserting `len(widgets_values) == expected` for every affected node.
4. **Boot ComfyUI and load each workflow** to confirm no silent value shifts.

There is no such thing as a "safe additive" widget change once a workflow has been saved. `INPUT_TYPES` is a schema. Schema changes require data migrations.

### Test workflow discipline

If your node pack has optional expensive features (multi-pass LLM loops, self-critique, outline competitions, upscaling passes, quality boosters), **your test/QA workflows must explicitly disable them**. Don't inherit defaults — defaults change, and a test workflow that silently picks up a newly-enabled-by-default feature will blow its wall-time budget without anyone noticing until the next release.

Encode the purpose in the widget values, not just the filename:

- **`test.json`** → fastest possible run, every expensive feature explicitly OFF
- **`lite.json`** → one or two expensive features ON for quality validation
- **`full.json`** → all expensive features ON for final-quality output

Budget the wall time of each workflow and regression-check after every release. If `test.json` ever exceeds its budget, something drifted — either a default changed, a feature was added to the critical path, or an inference call quietly scaled up. Catch it immediately while the change is fresh.

This is not optional for node packs with LLM or diffusion stages. A "test" workflow that takes 40 minutes instead of 10 because `self_critique` and `open_close` defaulted to true is a real bug that burns real GPU hours and real user trust.

---

## Dependency and VRAM hygiene

### Environment targeting

Most "dependency problems" are actually environment-targeting problems. The Windows Portable install bundles its own Python in `python_embeded/`. Packages installed into any other interpreter won't be visible at runtime.

```bash
# Correct — targets the Portable runtime
python_embeded/python.exe -m pip install accelerate

# Wrong — installs into system Python
pip install accelerate
```

### Device placement and `device_map`

`device_map="auto"` in Transformers requires the `accelerate` package. If it's missing from ComfyUI's Python environment, you'll get explicit load-time errors.

Two safe patterns:

- **If you use `device_map`:** Ensure `accelerate` is installed in the same environment running ComfyUI.
- **If you can't guarantee that:** Skip `device_map` entirely, load models to CPU, then move to your target device explicitly.

### Transformers v5 compatibility

Transformers v5 removes deprecated pipeline classes including `SummarizationPipeline` and `TranslationPipeline`. If your node pack uses these, migrate to `TextGenerationPipeline` or modern chat-model patterns.

### Background thread noise from third-party libraries

Large ML libraries frequently spawn background threads at model-load time for housekeeping tasks — auto-conversion probes, telemetry, cache warming, safetensors checks. These threads can throw scary-looking exceptions into your logs when their HTTP calls fail, even though the model itself loads and runs fine.

A real example: `transformers` spawns `Thread-auto_conversion` on certain model loads to POST to a Hugging Face conversion endpoint and check for safetensors availability. If the endpoint returns HTML, nothing, or is blocked by a corporate proxy, the thread raises `json.decoder.JSONDecodeError` into the log. The model loads fine. The exception is cosmetic. But users will file bug reports, and you will waste hours convincing yourself your node is broken when it isn't.

**Fix pattern: mock the offending module at import time**, before any third-party library has a chance to spawn its thread:

```python
# At the very top of your node pack's __init__.py, before importing transformers:
import sys
import types as _types

_mock_sc = _types.ModuleType("transformers.safetensors_conversion")
_mock_sc.auto_conversion = lambda *args, **kwargs: None
sys.modules["transformers.safetensors_conversion"] = _mock_sc
```

Note that some model load paths (e.g., Bark) bypass this kind of mock by re-importing the real module or using a different code path. If the exception only appears for specific models, document it as known non-blocking log noise rather than chasing a fix that's worse than the problem.

**General principle:** when you see a scary exception in logs, first verify whether the operation that's supposedly failing actually affects output. If inference runs correctly and output is clean, the exception is likely from a background housekeeping thread and should be either mocked at import time or documented as tolerated noise — not debugged as a real failure.

### VRAM lifecycle management

Long-running sessions that load multiple large models need explicit lifecycle management:

```python
# The correct sequence:
output = model(input_tensor)     # 1. Run inference
del model                        # 2. Delete the reference
del input_tensor                 # 3. Delete tensors
torch.cuda.empty_cache()         # 4. NOW release cached memory
```

`empty_cache()` without deleting references first does effectively nothing for reclaiming model memory.

---

## Contributing

Found a bug pattern not covered here? Open an issue or PR. This guide exists because of accumulated community pain — your edge case is probably someone else's future three-hour debugging session.

---

## License

MIT
