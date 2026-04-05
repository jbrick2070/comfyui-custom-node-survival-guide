# ComfyUI Custom Node & Workflow JSON Development Best Practices

**By Jeffrey A. Brick** · SIGNAL LOST Edition · April 2026

> Battle-tested guidance for building ComfyUI custom nodes, maintaining workflow JSONs, and keeping GPU-heavy pipelines stable. Every section here exists because of a specific class of "ghost bug" that cost real hours to diagnose — usually rooted in ComfyUI's import lifecycle, execution caching, or workflow serialization rules.

> **Full disclosure:** I am not a coder. Every line of code in my ComfyUI node packs was written by Claude (Anthropic's AI). The v1.0 guide was built across several weeks of Claude Code sessions. The v1.1 SIGNAL LOST Edition was built in a single Claude Cowork session. I brought the creative vision and domain knowledge; Claude brought the code. The bugs and lessons are real regardless of who typed them.

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

Ten high-leverage habits that prevent most custom-node failures.

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

**This is the single most under-documented gotcha in ComfyUI:** workflow JSON stores widget values by **position index**, not by name. Add or reorder widgets in `INPUT_TYPES` and old workflows silently map prior values onto the wrong widget. Treat input changes like database schema migrations, not casual edits.

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

Most "this makes no sense" bugs fall into three buckets. Classify fast, fix fast.

### Stale code — import didn't change

You edited Python but behavior didn't change. The running process hasn't imported your new code.

**Fix:** Restart ComfyUI. If you're copying across directories or switching branches, delete `__pycache__/` first.

### Stale state — node didn't execute

Breakpoints don't hit, logs don't appear. ComfyUI skipped your node because output caching decided nothing changed.

**Fix:** Implement `IS_CHANGED`. During development, return `float("NaN")` to force execution. Replace with deterministic logic before shipping.

### Stale UI mapping — workflow loads but values are wrong

Your node executes but gets nonsensical parameters — wrong booleans, shifted strings. Widget values in saved workflow JSON are mapped by position index.

**Fix:** Check whether you've added, removed, or reordered widgets since the workflow was saved. If so, the workflow JSON is out of sync. Update it or implement migration logic.

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
