# ComfyUI Custom Node & Workflow JSON Development — Best Practices & Lessons Learned

**Version 1.2 — SIGNAL LOST Edition**

Jeffrey A. Brick

April 2026

Every rule in this document was learned the hard way.

**How this guide was made:** I am not a coder. I am a healthcare IT project manager who builds AI creative tools as a side pursuit. Every single line of code in my ComfyUI node packs --- ComfyUI-Goofer and ComfyUI-OldTimeRadio (SIGNAL LOST) --- was written by Claude, Anthropic's AI assistant, across dozens of sessions. The v1.0 sections (1--52) were discovered over several weeks of building with Claude Code (Anthropic's command-line coding agent). The v1.1 sections (53--60) were discovered in a single intensive Claude Cowork session (Anthropic's desktop AI tool) while building the SIGNAL LOST audio-video pipeline. The v1.2 additions (sections 61--65, plus extensions to sections 7, 9, and 10) were discovered during the SIGNAL LOST v1.2.0 production cycle — narrative engine bug fixes, LLM token-budget decapitation traps, content-filter rotation patterns, fuzzy-match leak guards, statistical regression harnesses, GitHub lockstep verification protocol, and the discipline of writing roadmaps for the *next* AI session rather than just for humans. I never manually edited a workflow wire, typed a widget value, or wrote a line of Python. Every bug, every fix, every architectural pattern in this guide came from directing Claude to build, test, break, diagnose, and repair ComfyUI custom nodes on my behalf. If that changes how you read this document --- good. It should. This is what AI-assisted development actually looks like in practice: you bring the creative vision and domain knowledge, the AI brings the code, and the lessons learned are real regardless of who typed them.

## Table of Contents

## Part I: Core Architecture & Environment

-   Section 1: Project Architecture

-   Section 9: Windows & PowerShell Gotchas

-   Section 31: HuggingFace Cache & Windows Path Issues

-   Section 32: Python Environment Targeting

-   Section 41: Windows Portable CUDA Wheel Resolution

-   Section 44: prestartup_script.py & Environment Bootstrapping

-   Section 45: Dependency Conflict Resolution Across Node Packs

-   Section 47: transformers 5.0 Compatibility & Breaking Changes

-   Section 54: Git LFS Filter Hangs on Windows

-   Section 55: Windows Defender & Git Executable Blocking

-   Section 57: Output Path Resolution Pitfalls

## Part II: Node Design & Execution Mechanics

-   Section 2: Widget Architecture & The Sticky Widget Problem

-   Section 8: Safe Multi-Node Loading & Isolation

-   Section 13: Coordinated Node Behavior

-   Section 15: ComfyUI-Specific Patterns

-   Section 21: Workflow Migrations & Node Replacement API

-   Section 22: Node Identity & Naming

-   Section 23: Hidden Inputs (UNIQUE_ID, PROMPT, EXTRA_PNGINFO)

-   Section 24: VALIDATE_INPUTS Gotchas

-   Section 27: List Execution Model (OUTPUT_IS_LIST / INPUT_IS_LIST)

-   Section 28: Lazy Inputs & Conditional Execution

-   Section 29: Interrupt Handling & Progress Reporting

-   Section 33: Dynamic COMBO Dropdowns

-   Section 36: Graceful Asyncio & Event Loop Exception Handling

-   Section 46: Headless / API-Only Mode Validation

-   Section 50: Execution Order Dependencies via Dummy Links

-   Section 60: OUTPUT_NODE UI Results & Preview Thumbnails

## Part III: Models, Tensors, & VRAM

-   Section 3: Using Local LLMs in Custom Nodes

-   Section 4: Model Class Selection & the Silent Wrong-Model Bug

-   Section 5: Device & Dtype Alignment

-   Section 6: Batching & Tensor Dimension Handling

-   Section 11: Audio & Video Processing Patterns

-   Section 26: AUDIO Type Contract

-   Section 34: Memory Management & Bounded Caches

-   Section 40: Native VRAM Management & ComfyUI's LRU Model Registry

-   Section 49: trust_remote_code and Custom Model Code Compatibility

-   Section 53: ffmpeg Subprocess Pipe Deadlock

-   Section 56: CPU-Only Video Rendering in ComfyUI (Zero VRAM)

## Part IV: State, Caching, & I/O

-   Section 12: Cache Invalidation with IS_CHANGED

-   Section 25: IS_CHANGED Reliability Limits

-   Section 30: Output & Temp Path Discipline

-   Section 35: Cache-Signature Safety

-   Section 37: HTTP Fallback Chains & Offline Resilience

-   Section 38: External Data Registries & Config Files

-   Section 42: Audio Provenance & ID3v2 Metadata Embedding

-   Section 43: Server Telemetry via send_sync

-   Section 58: Audio-Reactive Pipeline Timing & Beat Duration Tuning

-   Section 59: WAV vs MP4 Output Strategy — Memory-Only Passthrough

## Part V: Workflow JSON Mastery

-   Section 17: Workflow JSON Overview

-   Section 18: Building Workflow JSON from Scratch

-   Section 19: Debugging Workflow JSON

-   Section 20: Workflow JSON Maintenance & Versioning

-   Section 51: Widget Value Desync After INPUT_TYPES Changes

## Part VI: Quality Assurance & Automation

-   Section 7: Content Safety & Filtering

-   Section 10: Regression Testing Checklist

-   Section 14: Removing a Dependency Cleanly

-   Section 16: AI Assistant Autonomy & Available Tools

-   Section 39: Testing Nodes Without ComfyUI Running

-   Section 48: Quick Reference Card

-   Section 52: Deployment Encoding Hygiene & Cross-Environment File Transfer

## Part I: Core Architecture & Environment

### Section 1: Project Architecture

ComfyUI custom nodes live in two places on disk, and keeping them in sync is the single biggest source of silent failures.

#### 1.1 The Dual-Directory Problem

ComfyUI reads nodes from its custom_nodes folder. Never edit files there directly — it's a deployment target, not a workspace. Maintain a separate source repo and sync to custom_nodes after every change.

> **Critical Paths (Example)**
>
> Source repo (edit here): C:\Users\you\Projects\MyNode\ Live custom_nodes: C:\Users\you\Documents\ComfyUI\custom_nodes\MyNode\ WRONG path (common mistake): C:\\...\ComfyUI_windows_portable\ComfyUI\custom_nodes\ We shipped code to the wrong custom_nodes path for multiple commits before catching it.

#### 1.2 Sync Protocol

After every edit, run a full sync — not just the file you changed. Partial syncs leave other files stale.

```
# PowerShell: sync ALL source files to custom_nodes $src = "C:\path\to\repo" $dst = "C:\path\to\custom_nodes\YourNode"
Get-ChildItem $src -Include *.py,*.md,*.txt -Recurse | ForEach-Object { $rel = $_.FullName.Substring($src.Length)
Copy-Item $_.FullName (Join-Path $dst $rel) -Force }
Copy-Item "$src\example_workflows\*.json" "$dst\example_workflows\" -Force
```

#### 1.3 Always Clear __pycache__

Python caches compiled bytecode in __pycache__. If you update a .py file but don't clear the cache, ComfyUI may load the old .pyc instead. Clear pycache in BOTH locations after every sync.

> **Restart Required**
>
> After syncing files AND clearing __pycache__, you MUST fully restart ComfyUI. Simply re-queuing a workflow does NOT reload Python modules. We lost hours debugging a "fixed" bug that persisted because ComfyUI still had the old module in memory.

#### 1.4 Hash Verification

Never assume a copy worked. After syncing, MD5-hash every file in both locations and compare. If any hash doesn't match, the sync failed silently.

```
# PowerShell: verify all .py files match
Get-ChildItem $src -Filter "*.py" | ForEach-Object { $rh = (Get-FileHash $_.FullName -Algorithm MD5).Hash $nh = (Get-FileHash (Join-Path $dst $_.Name) -Algorithm MD5).Hash
if ($rh -ne $nh) {
Write-Host "[STALE] $($_.Name)"; throw "MISMATCH" }
else {
Write-Host "[OK] $($_.Name)" } }
```

### Section 9: Windows & PowerShell Gotchas

#### 9.1 Git Hangs via Windows Credential Manager

Direct git commands in PowerShell hang indefinitely because Windows Credential Manager opens a GUI prompt the AI can't interact with. Wrap git in Start-Job with a timeout.

#### 9.2 PowerShell String Interpolation

PowerShell interpolates {} as variable references. If writing Python code with {style} via Set-Content, the braces get consumed. Write from the Linux mount path instead.

#### 9.3 PowerShell && and Encoding

Older PowerShell (5.x) doesn't support &&. Use semicolons. Also, PowerShell's default encoding can corrupt UTF-8 characters (especially emoji in README files). Write with Python using encoding='utf-8'.

> **Encoding Lesson**
>
> We pushed a README through PowerShell and all emoji headers turned into garbled bytes on GitHub. Fix: write files with Python using encoding=\'utf-8\', or avoid emoji entirely.

#### 9.4 PowerShell Treats Git's stderr as a Native Command Error

Git writes most of its normal status output (`To https://github.com/...`, `[new tag] v1.2.0 -> v1.2.0`, branch advance arrows) to **stderr**, not stdout. PowerShell sees any text on stderr from a native command and wraps it in a scary-looking error block:

```
git : To https://github.com/jbrick2070/Whatever.git
At line:18 char:1
+ git push origin v1.2.0
+ ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (...) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
```

**The push actually succeeded.** The error block is PowerShell editorializing on stderr text it doesn't understand. Look for the actual git output line — `[new tag] v1.2.0 -> v1.2.0` or `4b33563..7b67bae main -> main` — embedded inside the error block. That's the truth. The "NativeCommandError" wrapper is noise.

The mitigation is simple but counterintuitive: ignore the error block, look for the real git output, and verify with `git log --oneline -3` after every push to confirm the commit landed. Don't try to suppress stderr — you need to see real errors when they happen.

#### 9.5 The `git push origin main` From a Feature Branch Trap

This is the most expensive Windows-git mistake in the SIGNAL LOST development cycle. You're sitting on a feature branch (e.g., `v1.2-narrative-beta`), you've committed, you run `git push origin main`, and git says **"Everything up-to-date."** You believe the push worked. Hours later you discover nothing landed because there was nothing to push to `main` from your current position.

```
git push origin main          # WRONG — pushes nothing if you're not on main
git push origin <currentbr>   # RIGHT — pushes the branch you're actually on
```

The fix is to always use the explicit branch name in the push command, and to read git's output for the literal `branch -> branch` confirmation line. If the push command says "Everything up-to-date" and you expected commits to land, **you pushed the wrong branch**. Fix it before doing anything else.

Better yet: hand the user PowerShell blocks that include `git status` first so they can see what branch they're actually on before they push. Never assume the user is on the branch you think they are.

#### 9.6 Always Bake `cd` Into User-Facing PowerShell Blocks

When handing a non-developer user (or yourself in a different terminal) a PowerShell block to run, **always start with `cd <absolute path>`** even if you "know" they're already in the right directory. They aren't. They closed the previous terminal. They opened a new one in `C:\Users\<them>` by default. They were in a sibling repo. Bake the `cd` in. The cost is one line; the savings on "I ran your command and it said nothing happened" is enormous.

```powershell
cd C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio
git status
git add nodes/gemma4_orchestrator.py
git commit -m "..."
git push origin v1.2-narrative-beta    # explicit branch
git log --oneline -3                    # verify locally
```

Five lines, four safety nets, zero ambiguity.

### Section 31: HuggingFace Cache & Windows Path Issues

#### 31.1 The Symlink Problem on Windows

HuggingFace's default caching uses symlinks to deduplicate model files. On Windows, symlinks require Developer Mode or admin privileges. Without them, HuggingFace silently duplicates multi-GB model files, filling the system drive.

> **Symptoms**
>
> C: drive fills up despite having only one model downloaded Model download takes twice as long as expected (it's copying, not linking) Multiple identical 4+ GB files in .cache\huggingface\hub\

#### 31.2 Fix: Enable Developer Mode or Relocate Cache

```
# Option 1: Enable Developer Mode (Settings > Developer settings) # This allows symlinks without admin # Option 2: Set cache to a shorter path on a large drive set HF_HOME=D:\hf_cache set TRANSFORMERS_CACHE=D:\hf_cache\transformers # Option 3: In Python before any HF imports
import os os.environ["HF_HOME"] = "D:\\hf_cache"
```

#### 31.3 Windows Path Length (MAX_PATH = 260)

HuggingFace generates deep nested paths with long hashes. If your ComfyUI install is already in a deep directory tree, model downloads fail with WinError 206 "path too long" or mysterious .incomplete lock files.

-   Keep ComfyUI at a short path: C:\ComfyUI, not C:\Users\name\Documents\AI\Projects\ComfyUI\

-   Enable long paths in Windows: Settings > System > For developers > Enable Win32 long paths

-   Or set the registry key: HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1

### Section 32: Python Environment Targeting

This is the most common "it works for me but not in ComfyUI" bug. pip installed the package into the wrong Python.

> **We Hit This Exactly**
>
> We ran pip install accelerate and got a success message. ComfyUI still threw ModuleNotFoundError for accelerate. Reason: pip targeted the system Python, not ComfyUI's embedded Python.

#### 32.1 The Problem

ComfyUI portable installs use python_embeded (note the typo — it's intentional). Standard pip commands target whatever "python" is on PATH, which is often a different interpreter.

#### 32.2 Verification Protocol

```
# Step 1: Find which Python ComfyUI uses # Check run_nvidia_gpu.bat or run_cpu.bat
for the python path # Step 2: Install using THAT specific Python .\python_embeded\python.exe -m pip install accelerate # Step 3: Verify the install landed in the right place .\python_embeded\python.exe -c "import accelerate;
print(accelerate.__version__)"
```

#### 32.3 For AI Assistants

When installing packages for the user, always: (1) find the exact Python executable ComfyUI uses, (2) install with that executable, (3) verify the import works from that same executable. Never run bare "pip install".

### Section 41: Windows Portable CUDA Wheel Resolution

ComfyUI's Windows portable distribution uses an isolated python_embeded directory. Standard pip commands can silently install CPU-only PyTorch wheels, breaking CUDA support for the entire environment.

#### 41.1 The Trap

> **Real Scenario**
>
> You run: pip install torchaudio pip downloads the CPU-only wheel (no +cu130 suffix). torchaudio works but torch.cuda.is_available() now returns False. Every GPU model in ComfyUI breaks. The fix requires reinstalling torch+cuda.

#### 41.2 Safe Install Pattern

```
# ALWAYS specify the CUDA index URL when installing torch-related packages python_embeded\python.exe -m pip install torchaudio \ \--index-url https://download.pytorch.org/whl/cu130 # For non-torch packages, use the ComfyUI python directly python_embeded\python.exe -m pip install accelerate
```

#### 41.3 Verification After Any Install

```
# Always verify CUDA still works after installing anything python_embeded\python.exe -c "
import torch
print(\'CUDA available:\', torch.cuda.is_available())
print(\'CUDA version:\', torch.version.cuda)
print(\'Device:\', torch.cuda.get_device_name(0)
if torch.cuda.is_available()
else \'NONE\') "
```

### Section 44: prestartup_script.py & Environment Bootstrapping

By the time __init__.py runs, ComfyUI's Python environment is already initialized. If you need to set environment variables (HF_HOME, CUDA_VISIBLE_DEVICES, etc.), it's too late — libraries have already read their defaults.

#### 44.1 The Solution

Create a prestartup_script.py in your custom_nodes directory. ComfyUI executes these before importing any node modules.

```
# custom_nodes/ComfyUI-Goofer/prestartup_script.py
import os
import sys # Fix HuggingFace cache path to avoid MAX_PATH issues (Section 31)
if sys.platform == "win32" and "HF_HOME" not in os.environ: hf_path = "D:\\hf_cache" # short path on large drive os.makedirs(hf_path, exist_ok=True) os.environ["HF_HOME"] = hf_path os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1" # Suppress noisy deprecation warnings
import warnings warnings.filterwarnings("ignore", message=".*torch_dtype.*deprecated.*")
```

> **Key Rule**
>
> prestartup_script.py runs BEFORE node imports. It's the only place to reliably set env vars for the entire session. Keep it lightweight — no heavy imports, no model loading.

### Section 45: Dependency Conflict Resolution Across Node Packs

The ComfyUI ecosystem has no global dependency resolver. When multiple node packs declare conflicting requirements, pip silently breaks things.

#### 45.1 Common Conflicts

-   Node A pins transformers==4.44.0, Node B requires transformers>=5.0.0

-   Node A installs torch CPU wheel, overwriting your CUDA version

-   Node A's requirements.txt triggers a numpy downgrade that breaks everything

#### 45.2 Defensive Practices

-   Pin your requirements loosely: transformers>=4.40,\<6.0 instead of transformers==5.0.0

-   Never pin torch in requirements.txt — ComfyUI manages its own torch version

-   Test your node with both the minimum and latest version of each dependency

-   Use try/except around version-sensitive imports and provide fallback code paths

#### 45.3 Pre-Flight Check Script

```
# Add to __init__.py or prestartup_script.py
import importlib
def _check_deps(): issues = []
try:
import torch
if not torch.cuda.is_available(): issues.append("CUDA not available - check torch installation")
except ImportError: issues.append("torch not found")
try:
import transformers v = tuple(int(x)
for x in transformers.__version__.split(\'.\')[:2])
if v \< (4, 40): issues.append(f"transformers {transformers.__version__} too old, need >=4.40")
except ImportError: issues.append("transformers not found")
return issues
```

### Section 47: transformers 5.0 Compatibility & Breaking Changes

HuggingFace transformers 5.0 introduced several breaking changes that affect ComfyUI custom nodes. All of these were discovered during live debugging in the Goofer project.

> **We Hit All Three of These**
>
> Phi-3-mini fell back to Template mode because device_map broke under ComfyUI. The summarizer crashed because the 'summarization' pipeline task was removed. Both were fixed in a single session — details below.

#### 47.1 torch_dtype → dtype

The torch_dtype parameter in from_pretrained() is deprecated. Use dtype instead. While torch_dtype still works with a warning, some code paths in transformers 5.0 behave differently when the deprecated form is used.

# OLD (deprecated, may cause issues) model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float16) # NEW (correct for transformers 5.0+) model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.float16)

#### 47.2 device_map + ComfyUI's set_default_device Conflict

ComfyUI calls torch.set_default_device("cuda") before nodes load. In transformers 5.0, using device_map="auto" when set_default_device is active triggers a check that fails even if accelerate is installed. The error says "requires accelerate" but the real issue is the interaction between device_map and set_default_device.

# BROKEN in ComfyUI + transformers 5.0: model = AutoModelForCausalLM.from_pretrained( name, dtype=torch.float16, device_map="auto" # fails! ) # FIX: skip device_map, load to CUDA manually: model = AutoModelForCausalLM.from_pretrained( name, dtype=torch.float16 ).to("cuda").eval()

> **Key Insight**
>
> accelerate was installed correctly in the right venv. is_accelerate_available() returned True in standalone tests. The error only appeared INSIDE ComfyUI because of set_default_device. The fix: don't use device_map at all. Manual .to("cuda") works fine.

#### 47.3 Pipeline Task "summarization" Removed

transformers 5.0 removed the "summarization" task from the pipeline() API. If you use pipeline("summarization", \...), you get "Unknown task summarization."

```
# OLD (broken in transformers 5.0):
from transformers
import pipeline summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6") # FIX: use the model directly
from transformers
import AutoTokenizer, AutoModelForSeq2SeqLM
import torch tok = AutoTokenizer.from_pretrained("sshleifer/distilbart-cnn-6-6") mdl = AutoModelForSeq2SeqLM.from_pretrained("sshleifer/distilbart-cnn-6-6") mdl.eval()
def summarize(text, max_length=60): inputs = tok(text, return_tensors="pt", truncation=True, max_length=512) with torch.no_grad(): ids = mdl.generate(**inputs, max_length=max_length, num_beams=4)
return tok.decode(ids[0], skip_special_tokens=True)
```

#### 47.4 General Advice for Library Upgrades

-   Wrap all model-loading code in try/except — always have a fallback mode

-   Log the exact exception message — "Template mode" told us something was wrong; the exception told us what

-   Test model loading standalone (outside ComfyUI) first to isolate whether the issue is the library or ComfyUI's environment

-   Check for deprecated parameters in release notes before upgrading

## Part II: Node Design & Execution Mechanics

### Section 2: Widget Architecture & The Sticky Widget Problem

ComfyUI's widget system is the most common source of silent, confusing bugs in custom node development.

#### 2.1 How widgets_values Works

When you save a workflow as JSON, each node stores its widget state in a widgets_values array. This array maps to your INPUT_TYPES optional widgets BY POSITION INDEX — not by name.

> **Slot Connections vs. Widgets**
>
> Required inputs via SLOT CONNECTIONS (MODEL, IMAGE, AUDIO) do NOT appear in widgets_values. Only OPTIONAL inputs rendered as UI widgets are stored by position. If you convert a slot input to a widget or vice versa, the positional mapping shifts.

#### 2.2 The Sticky Widget Bug

You add a new optional widget between existing widgets. The saved workflow JSON still has the OLD widgets_values array. ComfyUI loads the workflow and maps values by position. Every widget after the insertion point gets the WRONG value. No error is thrown.

> **Real Example**
>
> GooferSanitizer had [true, ""] for [enabled, custom_blocklist]. We added banana_filter between them. Correct: [true, true, ""]. Without the fix, custom_blocklist received \'true\' (a boolean for a string field).

#### 2.3 The Rule

Every time you add, remove, or reorder an optional widget in INPUT_TYPES, you MUST update the widgets_values array in every saved workflow JSON.

---------------\-- ------------------------------------------------\--

> **Action**
>
> **Required Update**

Add a widget Insert default value at correct position

Remove a widget Remove value at that position

Reorder widgets Reorder widgets_values to match

Change default Update value if workflows should use new default

---------------\-- ------------------------------------------------\--

### Section 8: Safe Multi-Node Loading & Isolation

If one node has a broken dependency, the default __init__.py pattern (importing all nodes at module scope) crashes the entire package. Use isolated per-node loading instead.

```
# __init__.py - safe per-node loading
import traceback _NODE_MODULES = { "MyNode_Weather": (".nodes.weather", "WeatherNode"), "MyNode_Camera": (".nodes.camera", "CameraNode"), "MyNode_TTS": (".nodes.tts", "TTSNode"), } NODE_CLASS_MAPPINGS = {} NODE_DISPLAY_NAME_MAPPINGS = {}
for node_name, (module_path, class_name) in _NODE_MODULES.items():
try:
import importlib mod = importlib.import_module(module_path, package=__name__) cls = getattr(mod, class_name) NODE_CLASS_MAPPINGS[node_name] = cls NODE_DISPLAY_NAME_MAPPINGS[node_name] = node_name.replace("_", " ")
except Exception as e:
print(f"[WARNING] Failed to load \'{node_name}\': {e}") traceback.print_exc()
```

> **Key Benefit**
>
> Each node's failure is isolated. If TTS fails, Weather and Camera still work. The warning is printed to console so users know which node is broken and why.

#### 8.1 Lazy Heavy Imports

Even with isolated loading, avoid importing heavy libraries (torch, transformers, torchaudio) at module scope. Move them inside the node's execute method. The node registers instantly during startup and only pays the import cost when actually executed.

### Section 13: Coordinated Node Behavior

ComfyUI nodes execute independently. But sometimes multiple instances of the same node must coordinate — e.g., five camera nodes that should collectively show a specific mix of categories.

#### 13.1 The Shared-Seed Pattern

Pass the same seed to all node instances. Each uses the seed for deterministic results, then uses its own unique input (like category name) to differentiate. Because every node computes the same shuffled order, they agree on which slots swap — without any communication channel.

#### 13.2 Deterministic Camera Selection

When multiple nodes swap to the same category, hash each node's original category as an offset so they pick different cameras:

from hashlib import sha256 offset = int.from_bytes( sha256(original_category.encode()).digest()[:4], "little" ) selected = cameras[(seed + offset) % len(cameras)]

#### 13.3 Round-Robin with Thread Safety

For sequential selection modes, use a module-level dict protected by a threading lock to prevent race conditions.

### Section 15: ComfyUI-Specific Patterns

#### 15.1 Node Registration

Every node class needs CATEGORY, FUNCTION, RETURN_TYPES, RETURN_NAMES, and a classmethod INPUT_TYPES. The FUNCTION string must match the method name exactly.

class MyNode: CATEGORY = "MyPack" FUNCTION = "execute" RETURN_TYPES = ("IMAGE",) RETURN_NAMES = ("image",) \@classmethod def INPUT_TYPES(cls): return {"required": {"model": ("MODEL",)}, "optional": {"strength": ("FLOAT", {"default": 1.0})}} def execute(self, model, strength=1.0): # \...

#### 15.2 Custom Types

Use custom type strings (like "MY_DATA") to prevent incompatible connections. ComfyUI enforces type matching on slot connections.

#### 15.3 Error Handling

If your node raises an unhandled exception, ComfyUI aborts the entire workflow. Wrap risky operations in try/except and return sensible defaults.

#### 15.4 Workflow JSON Integrity

-   Output link IDs must match the connections in the links array

-   Node counter (last_node_id) must equal or exceed the highest node ID

-   Link counter (last_link_id) must equal or exceed the highest link ID

-   No duplicate link IDs anywhere in the file

### Section 21: Workflow Migrations & Node Replacement API

When you rename a node class or refactor its inputs, every saved workflow referencing the old name breaks with "node type not found." ComfyUI provides a migration mechanism to handle this gracefully.

#### 21.1 The Problem

You refactor GooferPromptGen into GooferLLMPromptGen for clarity. Every workflow JSON that references the old class name is now broken. Users see a red "missing node" box.

#### 21.2 The Solution: NODE_CLASS_MAPPINGS Aliases

Keep the old key in NODE_CLASS_MAPPINGS pointing to the new class. This costs one line of code and preserves backward compatibility forever.

# __init__.py NODE_CLASS_MAPPINGS = { "GooferLLMPromptGen": GooferLLMPromptGen, # new name "GooferPromptGen": GooferLLMPromptGen, # alias: old name }

#### 21.3 Input Renames

If you rename an input parameter (e.g., prompt_text → prompt), implement the MIGRATE_INPUT classmethod or accept both parameter names in your execute method with a fallback.

def execute(self, prompt=None, prompt_text=None, **kwargs): text = prompt or prompt_text or "" # \...

> **Rule**
>
> Never delete an old node name or input name without a migration path. One line of alias code saves every user from manual JSON surgery.

### Section 22: Node Identity & Naming

#### 22.1 Node ID Stability

The keys in NODE_CLASS_MAPPINGS are your node's permanent identity. Every saved workflow stores these IDs. Changing them breaks every workflow that uses your node. Treat them like a public API: once published, they're frozen forever.

> **The Mistake**
>
> You change the mapping key from "GooferSanitizer" to "Goofer_Text_Sanitizer" because it looks nicer. Every existing workflow now fails with "node type not found." If you must rename: keep the old key as an alias (see Section 21).

#### 22.2 Namespace Collision Prevention

Node IDs must be unique across ALL installed node packs. If two packs register the same ID string, one silently wins and the other disappears from the UI. No error is thrown.

-   Always prefix node IDs with your pack name: "Goofer_Sanitizer" not "Sanitizer"

-   Never use generic IDs like "PromptGenerator", "ImageLoader", "AudioOutput"

-   Check the ComfyUI node registry before publishing to avoid collisions

# BAD: generic, will collide NODE_CLASS_MAPPINGS = {"PromptGen": MyPromptGen} # GOOD: namespaced, unique NODE_CLASS_MAPPINGS = {"GooferPromptGen": MyPromptGen}

### Section 23: Hidden Inputs (UNIQUE_ID, PROMPT, EXTRA_PNGINFO)

ComfyUI passes several hidden values to nodes that don't appear in the UI but are essential for advanced patterns like caching, metadata embedding, and per-instance state.

#### 23.1 Declaring Hidden Inputs

\@classmethod def INPUT_TYPES(cls): return { "required": { \... }, "hidden": { "unique_id": "UNIQUE_ID", "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO", } }

#### 23.2 UNIQUE_ID for Cache Namespacing

If you have a module-level cache (for loaded models, LLM outputs, etc.), use UNIQUE_ID as the cache key. Without it, multiple instances of the same node in one workflow share the same cache entry and cross-contaminate results.

_cache = {} # module-level def execute(self, unique_id, **kwargs): if unique_id not in _cache: _cache[unique_id] = expensive_computation() return (_cache[unique_id],)

#### 23.3 EXTRA_PNGINFO for Metadata

Use EXTRA_PNGINFO to embed custom metadata into output PNGs. This is how workflow information gets stored in generated images.

### Section 24: VALIDATE_INPUTS Gotchas

VALIDATE_INPUTS lets you reject bad input before execute() runs. But it has a critical edge case.

#### 24.1 The None Problem

When a required input is connected via a slot (not typed into the widget), VALIDATE_INPUTS receives None for that input — even though at runtime, execute() would get the actual value from the upstream node.

> **Real Scenario**
>
> You add VALIDATE_INPUTS to reject empty strings for a required text input. A user connects a Primitive "String" node instead of using the widget. Validation receives None and rejects it. The workflow refuses to run. But at runtime, the Primitive would have supplied a valid string.

#### 24.2 The Fix

\@classmethod def VALIDATE_INPUTS(cls, text=None, **kwargs): # Connected inputs arrive as None during validation if text is None: return True # allow — runtime will get real value if isinstance(text, str) and text.strip() == "": return "Text input cannot be empty" return True

Rule: always check for None first and return True. Only validate values that are actually present.

### Section 27: List Execution Model (OUTPUT_IS_LIST / INPUT_IS_LIST)

ComfyUI has two different batching mechanisms, and confusing them causes subtle bugs.

#### 27.1 Tensor Batching vs. List Execution

------------------ ------------------------------- ------------------------------------------------------------\--

> **Mechanism**
>
> **What It Does** **When to Use**

Tensor batch dim B dimension in (B,C,H,W) Images, audio — GPU-parallel

OUTPUT_IS_LIST Python list of separate items Prompts, filenames, configs — run downstream once per item

------------------ ------------------------------- ------------------------------------------------------------\--

#### 27.2 OUTPUT_IS_LIST

Without OUTPUT_IS_LIST = (True,), if your node returns a Python list of 5 prompts, ComfyUI wraps it as a single payload. Downstream runs once, receiving the whole list. With OUTPUT_IS_LIST = (True,), downstream runs 5 times, once per prompt.

class PromptBatchNode: OUTPUT_IS_LIST = (True,) # each item triggers separate downstream execution RETURN_TYPES = ("STRING",) def execute(self, source_text): prompts = source_text.split("\n") return (prompts,) # list of strings

#### 27.3 INPUT_IS_LIST

The reverse: if a downstream node needs to receive ALL items at once (e.g., to concatenate or compare them), declare INPUT_IS_LIST = True. Without it, the node runs separately for each item and never sees the full set.

### Section 28: Lazy Inputs & Conditional Execution

By default, ComfyUI evaluates ALL upstream nodes before calling your execute(). For nodes with an "enabled" toggle, this means expensive upstream work happens even when the node is disabled.

#### 28.1 The Problem

GooferPromptGen has an "enabled" toggle. When disabled, it should skip LLM inference entirely. But without lazy evaluation, the upstream model-loading node still runs, consuming VRAM and time.

#### 28.2 Lazy Input Declaration

\@classmethod def INPUT_TYPES(cls): return { "required": { "enabled": ("BOOLEAN", {"default": True}), "model": ("MODEL", {"lazy": True}), "text": ("STRING", {"lazy": True}), } }

#### 28.3 check_lazy_status

When lazy inputs are declared, ComfyUI calls check_lazy_status() before execute(). Return a list of input names that are actually needed. If "enabled" is False, return an empty list — upstream nodes won't execute.

def check_lazy_status(self, enabled, model=None, text=None): if not enabled: return [] # nothing needed, skip upstream evaluation needed = [] if model is None: needed.append("model") if text is None: needed.append("text") return needed

#### 28.4 ExecutionBlocker

For completely stopping downstream execution (not just skipping upstream), return an ExecutionBlocker from execute(). This prevents the entire downstream chain from running.

from comfy.graph_utils import ExecutionBlocker def execute(self, enabled, **kwargs): if not enabled: return (ExecutionBlocker(None),) # blocks all downstream # \... normal processing \...

### Section 29: Interrupt Handling & Progress Reporting

#### 29.1 Interrupt Responsiveness

When a user hits Cancel in ComfyUI, the framework sets an interrupt flag. But tight Python loops don't check it. MusicGen generation, batch audio processing, or long post-processing loops run to completion even after Cancel is pressed.

from comfy.utils import ProgressBar import comfy.model_management def execute(self, audio_list): pbar = ProgressBar(len(audio_list)) results = [] for i, audio in enumerate(audio_list): # Check interrupt EVERY iteration comfy.model_management.throw_exception_if_processing_interrupted() result = process_audio(audio) results.append(result) pbar.update(1) return (results,)

#### 29.2 Progress Reporting

Without progress updates, the UI looks frozen during long operations. Users assume it crashed. Use ProgressBar to emit step updates.

> **Where to Add Interrupt Checks**
>
> Inside any loop that processes multiple items (audio clips, video frames, prompt batches) Inside chunked generation (MusicGen generating 30s in 5s chunks) Inside any operation that takes more than \~2 seconds per iteration

### Section 33: Dynamic COMBO Dropdowns

COMBO inputs (dropdowns) populated from the filesystem are a common source of validation failures.

#### 33.1 The Empty List Problem

Your node generates COMBO options from a directory listing (e.g., available models). On a fresh install, the directory is empty. COMBO with an empty list causes a crash during node registration.

\@classmethod def INPUT_TYPES(cls): models = cls._scan_models() if not models: models = ["(no models found)"] # always have at least one option return { "required": { "model_name": (models, {"default": models[0]}) } }

#### 33.2 Stale Saved Values

A user saves a workflow with model_name = "my_model_v2". Later they rename or delete that model. When they load the workflow, ComfyUI validates the saved value against the current COMBO list and fails with "Value not in list."

> **Mitigation**
>
> Use VALIDATE_INPUTS to gracefully handle stale values: If the saved value isn't in the current list, fall back to the first available option and log a warning instead of crashing.

### Section 36: Graceful Asyncio & Event Loop Exception Handling

On Windows, ComfyUI's ProactorEventLoop throws ConnectionResetError when a browser tab disconnects during execution. Without handling this, your node's output stage crashes even though the computation completed successfully.

#### 36.1 The Pattern

import sys, asyncio if sys.platform == "win32": # Suppress spurious ConnectionResetError on browser disconnect _orig_handler = asyncio.events.BaseDefaultEventLoopPolicy loop = asyncio.get_event_loop() if hasattr(loop, "set_exception_handler"): def _quiet_handler(loop, context): exc = context.get("exception") if isinstance(exc, ConnectionResetError): return # suppress loop.default_exception_handler(context) loop.set_exception_handler(_quiet_handler)

#### 36.2 Where to Put It

Add this in your __init__.py, after imports but before node registration. It affects the entire event loop, so only one node pack needs it. If you're writing a shared library, guard it with a module-level flag to prevent double-registration.

### Section 46: Headless / API-Only Mode Validation

ComfyUI can run without a browser attached (headless mode). Nodes that assume a connected frontend will fail silently in this mode.

#### 46.1 The Problem

Your node returns UI-specific data (preview images, text for frontend widgets) mixed with functional outputs. In API mode, no browser is listening. If your node's return format depends on a connected client, headless execution produces unexpected results or crashes.

#### 46.2 The Fix: Separate UI Data from Functional Output

class MyNode: RETURN_TYPES = ("STRING", "AUDIO") OUTPUT_NODE = True def execute(self, text, audio): # Functional outputs (always returned) result = process(text, audio) # UI data (only matters when browser is connected) return { "ui": {"text": [result.summary], "audio": [result.preview_path]}, "result": (result.text, result.audio) }

> **Testing for Headless**
>
> Always test your workflow via the /prompt API endpoint (curl or Python requests). If it works in the browser but fails via API, you have a UI/functional separation issue.

### Section 50: Execution Order Dependencies via Dummy Links

Execution order in ComfyUI workflows is determined by data dependencies. When two nodes have no data dependency (both independently read from a module cache), ComfyUI may execute them in any order. This caused BackgroundMusic to run before PromptGen, resulting in an empty cache for genre data.

> **Problem:**
>
> Both nodes read movie_data independently. No graph edge from PromptGen to BackgroundMusic meant the executor could run BackgroundMusic first, before Phi-3 genre inference cached its result.

> **The Fix:**
>
> Add an optional prompt_seed INT input to BackgroundMusic with forceInput=True, wired from PromptGen's live_seed output. This creates a fake data dependency that enforces execution order without transferring real data.

Code pattern:

INPUT_TYPES = {

"optional": {

"prompt_seed": ("INT", {"default": 0, "forceInput": True}),

}

}

Then wire PromptGen's live_seed output to BackgroundMusic's prompt_seed input.

> **Better Pattern (v2.5+):**
>
> Pass genre/mood data as actual graph output instead of global cache. This makes dependencies explicit and future-proof.

## Part III: Models, Tensors, & VRAM

### Section 3: Using Local LLMs in Custom Nodes

Local LLMs (Phi-3-mini, MusicGen, Flan-T5) require careful VRAM management when sharing a GPU with video generation models like LTX-Video.

#### 3.1 Lazy Loading & Explicit Unloading

Never load a model at import time. Use a lazy-load pattern: the model stays None until first needed, loads on demand, and gets explicitly unloaded before the next heavy model needs the GPU.

_model = None _tokenizer = None def _get_model(): global _model, _tokenizer if _model is None: from transformers import AutoModelForCausalLM, AutoTokenizer _tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct") _model = AutoModelForCausalLM.from_pretrained( "microsoft/Phi-3-mini-4k-instruct", torch_dtype=torch.float16, device_map="auto" # requires accelerate>=0.26.0 ) return _model, _tokenizer def _unload_model(): global _model, _tokenizer del _model, _tokenizer _model = _tokenizer = None torch.cuda.empty_cache()

#### 3.2 Model Sequencing on a Single GPU

With a single GPU (even an RTX 5080 with 16 GB), you cannot have Phi-3 (\~4 GB) and LTX-Video (\~8 GB) loaded simultaneously. Plan your pipeline so LLM work finishes and unloads before video generation starts.

#### 3.3 Cross-Node Data Sharing via Module Cache

When one node generates data another node needs later, use a module-level cache dictionary rather than reloading the model.

```
# In producer_node.py _cached_data: dict = {} # module-level # During generate(), while model is loaded: _cached_data[key] = inferred_value # In consumer_node.py
def _get_cached(key):
from .producer_node
import _cached_data
return _cached_data.get(key, "")
```

> **Circular Import Warning**
>
> The consumer imports from the producer, never the reverse. If both files imported from each other, Python raises ImportError at startup.

#### 3.4 Device-Change Cache Invalidation

If you cache a loaded model, detect when the target device changes. Without this check, you get device mismatch errors on the next forward pass.

_model_cache = {"model": None, "device": None} def _get_or_load(device): if (_model_cache["model"] is not None and str(_model_cache["device"]) != str(device)): _model_cache["model"] = None torch.cuda.empty_cache() if _model_cache["model"] is None: model = load_model().to(device) model.eval() # CRITICAL: always call .eval() _model_cache["model"] = model _model_cache["device"] = device return _model_cache["model"]

### Section 4: Model Class Selection & the Silent Wrong-Model Bug

This is the single most frustrating category of bug: you load a model, it runs without errors, but silently ignores your inputs and produces garbage output. The cause is almost always using the wrong model class from the transformers library.

> **Real Example: MusicGen-melody**
>
> MusicgenForConditionalGeneration = text-only base class (discards audio input_features) MusicgenMelodyForConditionalGeneration = melody-conditioned class (uses audio input_features) Both load from "facebook/musicgen-melody" without error. The base class silently ignores input_features and generates random music.

#### 4.1 How to Catch It

-   Read the model card: check which class the HuggingFace page recommends

-   Check generate() signature: if it warns about unused kwargs, you're using the wrong class

-   Verify output quality: if output doesn't reflect your conditioning input, suspect wrong class first

-   Log the class name: log.info("Loaded: %s", type(model).__name__) after loading

#### 4.2 Common Variants

StableDiffusionPipeline vs. StableDiffusionImg2ImgPipeline, CLIPModel vs. CLIPVisionModel, WhisperForConditionalGeneration vs. WhisperForAudioClassification. Always verify the class matches your use case.

### Section 5: Device & Dtype Alignment

The two most common GPU-related crashes in ComfyUI node development. The fix patterns are straightforward once you understand them.

#### 5.1 The Dtype Mismatch

> **The Error**
>
> RuntimeError: mat1 and mat2 must have the same dtype, but got Float and Half

This happens when a preprocessor outputs float32 tensors but the model is loaded in float16. Fix: cast inputs to the model's dtype.

model_dtype = next(model.parameters()).dtype inputs = {} for k, v in processor_output.items(): if hasattr(v, "to"): v = v.to(device) if v.is_floating_point(): v = v.to(model_dtype) inputs[k] = v

#### 5.2 The Device Mismatch

> **The Error**
>
> RuntimeError: Expected all tensors on same device, found cuda:0 and cpu!

Fix: always align device and dtype before any tensor math.

#### 5.3 Prevention Pattern

def align_tensors(reference, *tensors): """Align all tensors to reference device and dtype.""" result = [] for t in tensors: if t.device != reference.device: t = t.to(reference.device) if t.is_floating_point() and t.dtype != reference.dtype: t = t.to(reference.dtype) result.append(t) return result

### Section 6: Batching & Tensor Dimension Handling

Audio waveforms arrive as 1D, 2D, or 3D depending on the source. Video frames need NHWC or NCHW. Getting this wrong produces cryptic dimension errors.

#### 6.1 Audio Tensor Shapes

------------------ ---------\-- ---------------------------\--

> **Source**
>
> **Shape** **Meaning**

Raw waveform (T,) 1D: just samples

Mono loaded (C, T) 2D: channels x time

ComfyUI standard (B, C, T) 3D: batch x channels x time

------------------ ---------\-- ---------------------------\--

# Always normalize to 3D (B, C, T) before processing if waveform.dim() == 1: waveform = waveform.unsqueeze(0).unsqueeze(0) # (T,) -> (1, 1, T) elif waveform.dim() == 2: waveform = waveform.unsqueeze(0) # (C, T) -> (1, C, T)

#### 6.2 Video Frame Shapes

ComfyUI IMAGE type uses NHWC but PyTorch ops like F.interpolate expect NCHW. Always convert:

# NHWC -> NCHW for PyTorch ops img = frames.permute(0, 3, 1, 2) img = F.interpolate(img, size=(H, W), mode="bilinear", align_corners=False) # NCHW -> NHWC for ComfyUI frames = img.permute(0, 2, 3, 1)

#### 6.3 Spatial Dimension Mismatches in Video Concat

When concatenating video clips from different sources, resize to a reference before concatenation. Mismatched H/W causes torch.cat to crash.

### Section 11: Audio & Video Processing Patterns

#### 11.1 Audio Resampling: Polyphase vs. Linear

When converting between sample rates, use torchaudio's polyphase resampler. Simple F.interpolate with mode="linear" introduces high-frequency aliasing artifacts.

def _resample(tensor, from_sr, to_sr): if from_sr == to_sr: return tensor try: import torchaudio resampler = torchaudio.transforms.Resample(from_sr, to_sr) return resampler(tensor.float()).to(tensor.device) except ImportError: new_len = int(tensor.shape[-1] * to_sr / from_sr) return F.interpolate(tensor.float(), size=new_len, mode="linear", align_corners=False)

#### 11.2 Crossfade with Raised-Cosine

Use a raised-cosine curve instead of linear interpolation. Linear blending creates audible clicks in audio and visible seams in video.

fade = torch.linspace(0.0, 1.0, crossfade_samples) fade = 0.5 * (1.0 - torch.cos(fade * torch.pi)) fade_in = fade fade_out = 1.0 - fade

#### 11.3 Flexible VIDEO Object Extraction

ComfyUI has no single standardized VIDEO type. Different node packs return video as objects with get_components(), as dicts, as named tuples, or as plain tensors. Build a defensive extractor: try get_components() first, fall back to attribute access, then dict access, then dump available attributes to the log.

### Section 26: AUDIO Type Contract

ComfyUI's AUDIO type is a dict, not a tensor. Every audio node must respect this contract. For tensor dimension normalization (1D/2D/3D), see Section 6.

> **The Contract**
>
> AUDIO = {"waveform": Tensor[B, C, T], "sample_rate": int} Always accept this dict. Always return this dict. Never pass a raw tensor where AUDIO is expected.

#### 26.1 Common Mistake

# WRONG: passing raw tensor return (waveform,) # crashes downstream: \'Tensor\' has no attribute \'sample_rate\' # RIGHT: wrapping in dict return ({"waveform": waveform, "sample_rate": sample_rate},)

#### 26.2 Preserve Sample Rate Through Transforms

When you resample, apply effects, or trim audio, always update the sample_rate in the returned dict. A common bug: you resample from 32000 to 44100 Hz but return the original sample_rate of 32000. Downstream nodes (especially video muxing) interpret timing incorrectly, causing audio drift.

def execute(self, audio): waveform = audio["waveform"] sr = audio["sample_rate"] # \... process waveform, possibly resample \... new_sr = 44100 # if resampled return ({"waveform": processed, "sample_rate": new_sr},)

### Section 34: Memory Management & Bounded Caches

ComfyUI workflows can loop through hundreds of items. Without bounded caches, the Python process grows until it's killed.

#### 34.1 The Problem

Your node caches LLM outputs or generated audio in a module-level dict. Over a multi-hour session processing 500 prompts, the dict grows to several GB. torch.cuda.empty_cache() doesn't help because Python still holds references.

#### 34.2 Bounded Cache Pattern

from collections import OrderedDict class BoundedCache: def __init__(self, max_size=50): self._cache = OrderedDict() self._max_size = max_size def get(self, key, default=None): if key in self._cache: self._cache.move_to_end(key) return self._cache[key] return default def set(self, key, value): if key in self._cache: self._cache.move_to_end(key) self._cache[key] = value while len(self._cache) > self._max_size: self._cache.popitem(last=False) # evict oldest _llm_cache = BoundedCache(max_size=100)

#### 34.3 Explicit Clear Affordance

Provide a way to clear caches. This can be a widget toggle ("clear cache on next run"), a module-level function called by __init__.py, or simply documenting that restarting ComfyUI is the real reset.

> **Reality Check**
>
> torch.cuda.empty_cache() releases unused GPU memory back to the CUDA allocator. It does NOT free memory still referenced by Python objects. If your dict/list/cache still holds tensors, VRAM stays allocated. The only guaranteed full reset is restarting ComfyUI.

### Section 40: Native VRAM Management & ComfyUI's LRU Model Registry

ComfyUI maintains a global LRU model registry that dynamically moves models between system RAM and GPU VRAM. When you load models manually with .to("cuda"), you bypass this system entirely — ComfyUI doesn't know your model exists and can't evict it when VRAM is needed.

#### 40.1 The Problem

You load Phi-3-mini to CUDA manually. ComfyUI's memory manager doesn't see it. When LTX-Video needs VRAM, ComfyUI tries to evict models it knows about but your 4 GB Phi-3 is invisible. Result: CUDA out-of-memory, even though ComfyUI thinks it freed enough space.

#### 40.2 The Correct Pattern

import comfy.model_management as mm # Let ComfyUI know about your model def execute(self, \...): model = load_my_model() # load to CPU first # Tell ComfyUI to manage VRAM for this model mm.load_model_gpu(model) # \... use model on GPU \... # ComfyUI will evict it automatically when VRAM is needed

#### 40.3 Practical Compromise

If integrating with ComfyUI's model management is too complex (HuggingFace models don't expose the same interface), use the manual load/unload pattern from Section 3 — but always call torch.cuda.empty_cache() after unloading, and explicitly unload before the next heavy model needs VRAM. This is what Goofer does: Phi-3 loads, generates, unloads, empty_cache, then LTX-Video gets full VRAM.

### Section 49: trust_remote_code and Custom Model Code Compatibility

When using transformers, trust_remote_code=True loads custom modeling code from HuggingFace Hub. This caused Phi-3-mini to fail with TypeError('type') on transformers 5.0.0.

> **Root Cause:**
>
> Microsoft's custom modeling_phi3.py was written for transformers 4.x. The v5 API changed kwargs (dtype vs torch_dtype), causing the custom __init__ to crash.

> **The Fix:**
>
> Remove trust_remote_code=True entirely. Phi-3 is natively supported in transformers 5.0 without custom code.

> **Rule:**
>
> Never use trust_remote_code=True for models that are natively supported by your transformers version. Check the official transformers documentation for your version's supported models.

> **Better Diagnostics:**
>
> Use log.exception() instead of log.warning() to capture full tracebacks. This reveals the actual incompatibility instead of swallowing it.

Code pattern:

\- Instead of: AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)

\- Use: AutoModelForCausalLM.from_pretrained(model_id) --- let transformers handle native models natively

\- On failure, check: transformers.__version__ and model's documentation for that version

## Part IV: State, Caching, & I/O

### Section 12: Cache Invalidation with IS_CHANGED

ComfyUI aggressively caches node outputs. If inputs haven't changed, your execute method is skipped entirely. Great for performance, deadly for nodes that read live data.

#### 12.1 Always-Refresh Pattern

For data-fetch nodes (weather, API calls, live feeds), return the current timestamp:

\@classmethod def IS_CHANGED(cls, **kwargs): """Never cache: always re-fetch live data.""" return time.time()

#### 12.2 File-Modified Pattern

For nodes that read a config file, return the file's modification time. The node only re-executes when the file actually changes.

#### 12.3 When NOT to Use IS_CHANGED

Don't add IS_CHANGED to compute-heavy nodes (video generation, model inference) unless they genuinely need fresh execution. Unnecessary cache invalidation means re-running expensive operations for identical results.

### Section 25: IS_CHANGED Reliability Limits

Section 12 covers how to use IS_CHANGED. This section covers when it lies to you.

#### 25.1 Arguments May Be None

IS_CHANGED receives the same arguments as your execute() method — in theory. In practice, connected inputs (IMAGE, AUDIO, MODEL) often arrive as None. If your IS_CHANGED tries to hash a tensor, it crashes.

\@classmethod def IS_CHANGED(cls, audio=None, **kwargs): if audio is None: return float("nan") # force re-execute when we can't check # Only hash if we actually got a value return hash(audio["waveform"].shape) + audio["sample_rate"]

#### 25.2 Best-Effort, Not Guaranteed

Treat IS_CHANGED as a performance optimization hint, not a contract. If your node absolutely must re-execute every time, return float("nan") or time.time() unconditionally. Don't build correctness-critical logic on IS_CHANGED argument values.

### Section 30: Output & Temp Path Discipline

ComfyUI has designated output and temp directories. Writing files anywhere else causes problems.

#### 30.1 Always Use folder_paths

import folder_paths output_dir = folder_paths.get_output_directory() temp_dir = folder_paths.get_temp_directory() # Save audio import os path = os.path.join(output_dir, f"goofer_audio_{unique_id}.wav") torchaudio.save(path, waveform, sample_rate)

#### 30.2 Why Not Use Relative Paths?

-   Relative paths resolve to the CWD, which varies by launch method

-   Portable installs have different directory structures than standard installs

-   ComfyUI's file browser only shows files in recognized output directories

-   Security: ComfyUI blocks writes outside designated directories to prevent arbitrary file access

#### 30.3 Temp vs. Output

Use temp_dir for intermediate files (chunks, previews, processing artifacts). Use output_dir for final deliverables the user expects to keep. Temp files may be cleaned up by ComfyUI.

### Section 35: Cache-Signature Safety

ComfyUI builds cache signatures from your node's inputs to decide whether to skip execution. Advanced patterns can break this mechanism.

#### 35.1 The Risk

If your node passes non-standard Python objects (custom container proxies, dynamic prompt objects, graph-rewriting artifacts) as inputs, the signature builder may fail to hash them. This causes either constant re-execution (performance hit) or stuck caching (correctness bug).

#### 35.2 Keep Inputs "Prompt-Safe"

-   Inputs should be plain types: str, int, float, bool, list, dict, tuple

-   Tensor inputs (IMAGE, AUDIO, MODEL) are handled specially by ComfyUI — don't wrap them

-   If you must pass complex objects, convert them to a hashable representation first

#### 35.3 When You See Unexpected Re-execution

If a node re-executes every time despite identical inputs, check what's flowing through its inputs. A non-hashable object in the input chain will cause the signature to change on every run. Use IS_CHANGED logging to trace what ComfyUI sees.

### Section 37: HTTP Fallback Chains & Offline Resilience

Nodes that fetch external data (weather, APIs, model cards) should never hard-depend on a single HTTP library or assume the network is available.

#### 37.1 Library Fallback Pattern

def _fetch(url, timeout=10): """requests -> urllib fallback.""" try: import requests r = requests.get(url, timeout=timeout) r.raise_for_status() return r.json() except ImportError: import urllib.request, json with urllib.request.urlopen(url, timeout=timeout) as resp: return json.loads(resp.read().decode())

#### 37.2 Graceful Demo / Fallback Data

When the network is down or an API is unreachable, return demo data instead of crashing. This keeps the workflow running for development, offline testing, and demos. Ship a small JSON or dict of representative fallback values.

def execute(self, city): try: data = _fetch(f"https://api.weather.example/{city}") except Exception as e: log.warning("Weather API unreachable, using demo data: %s", e) data = {"temp": 72, "condition": "sunny", "city": city} return (data,)

> **Why This Matters**
>
> Several Goofer/DMM nodes use this pattern for weather, camera registries, and metadata lookups. Without it, a flaky WiFi connection kills the entire pipeline. Demo data also makes it possible to develop and test nodes without API keys.

### Section 38: External Data Registries & Config Files

When nodes depend on structured external data (camera lists, category mappings, distance metadata), use a dedicated JSON registry file instead of hardcoding values.

#### 38.1 Registry Pattern

import json, os _REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "data", "camera_registry.json") _registry_cache = None def _load_registry(): global _registry_cache if _registry_cache is None: with open(_REGISTRY_PATH, encoding="utf-8") as f: _registry_cache = json.load(f) return _registry_cache

#### 38.2 Registry Design Rules

-   Keep the JSON human-editable — users should be able to add entries without touching Python

-   Validate on load: check required fields, warn on missing optional fields

-   Cache in memory after first load — don't re-read the file on every execute()

-   Provide a "reload registry" widget or IS_CHANGED hook tied to the file's mtime

-   Ship a sensible default registry so the node works out of the box

#### 38.3 Healthcheck-Driven Updates

If your registry references external resources (URLs, file paths, model names), add a healthcheck that validates entries are still reachable. Log warnings for stale entries but don't crash — stale data is better than no data.

### Section 42: Audio Provenance & ID3v2 Metadata Embedding

ComfyUI embeds workflow metadata in PNG images automatically. For audio files, you must implement this yourself.

#### 42.1 Why It Matters

You generate a perfect 30-second soundtrack with MusicGen. A week later you want to reproduce it. Without embedded metadata, the seed, prompt, model, and generation parameters are lost forever. With metadata, you can reconstruct the exact state.

#### 42.2 WAV Metadata Pattern

import json def _embed_workflow_metadata(wav_path, workflow_info): """Embed workflow JSON as a WAV comment chunk.""" try: import mutagen from mutagen.wave import WAVE audio = WAVE(wav_path) # Store as INFO chunk comment audio["ICMT"] = json.dumps(workflow_info, separators=(\',\', \':\')) audio.save() except ImportError: # mutagen not installed — skip metadata pass

For MP3 output, use mutagen's ID3 interface to write to the TXXX (user-defined text) frame. This preserves the metadata through most audio editors and players.

### Section 43: Server Telemetry via send_sync

For long-running nodes (MusicGen, LLM inference), ProgressBar updates the progress bar but can't send custom data to the frontend. send_sync can.

#### 43.1 Basic Pattern

from server import PromptServer def execute(self, prompt, unique_id=None, **kwargs): # Send a custom status message to the frontend PromptServer.instance.send_sync( "goofer.status", {"node": unique_id, "message": "Generating audio\...", "progress": 0.0} ) # \... long operation \... PromptServer.instance.send_sync( "goofer.status", {"node": unique_id, "message": "Audio complete", "progress": 1.0} )

#### 43.2 When to Use send_sync vs ProgressBar

--------------------- ---------------\-- ------------------

> **Feature**
>
> **ProgressBar** **send_sync**

Progress percentage Yes (built-in) Manual

Custom messages No Yes

Arbitrary data No Yes (any JSON)

Frontend JS needed No Yes (to receive)

--------------------- ---------------\-- ------------------

Use ProgressBar for simple step counters. Use send_sync when you need to push custom data (generated text, waveform previews, status messages) to the UI during execution.

## Part V: Workflow JSON Mastery

### Section 17: Workflow JSON Overview

Sections 18\--20 cover building, debugging, and maintaining ComfyUI workflow JSON files. This was the single largest category of non-Python debugging time in the Goofer project. The sticky widget bug (Section 2), link integrity issues, and counter mismatches all live in the JSON layer.

> **Why Workflow JSON Gets Its Own Block**
>
> Python node code can be unit-tested and linted. Workflow JSON cannot. A single miscount in widgets_values silently maps every value to the wrong widget. Link cross-references must agree in three places — the links array, the source node, and the target node. Saved workflows drift every time you update INPUT_TYPES, and ComfyUI won't warn you.

### Section 18: Building Workflow JSON from Scratch

ComfyUI workflow files are large, deeply nested JSON documents. Building or editing them by hand is where the majority of non-Python debugging time goes. These rules were learned from real failures.

#### 18.1 Anatomy of a Workflow JSON

Every workflow JSON has two critical top-level counters and a nodes array plus a links array. Getting any of these wrong produces silent failures.

---------------- ---------------------------------------------------------------------------------------------------------

> **Field**
>
> **What It Does**

last_node_id Must equal or exceed the highest node ID in the nodes array

last_link_id Must equal or exceed the highest link ID in the links array

nodes[] Each node has a unique integer id, a type (must match NODE_CLASS_MAPPINGS key), and widgets_values

links[] Each link is [link_id, source_node_id, source_slot, target_node_id, target_slot, type_string]

---------------- ---------------------------------------------------------------------------------------------------------

#### 18.2 The Counter Trap

If last_node_id is lower than an actual node ID, ComfyUI may assign a duplicate ID to new nodes added in the UI. This corrupts the graph silently — two nodes share an ID, and only one gets executed.

> **Real Example**
>
> We manually added a node with id: 15 but forgot to update last_node_id from 12. When the user added a new node in the UI, ComfyUI assigned it id: 13 — fine. But the next one got id: 15, colliding with our manually-added node. The workflow ran but skipped one of the two nodes with no error.

#### 18.3 Link Array Structure

Each link is a 6-element array: [link_id, from_node, from_slot, to_node, to_slot, type]. Slots are zero-indexed and refer to the position in the node's outputs (for from_slot) or inputs (for to_slot).

// Link 7: node 3's output slot 0 -> node 5's input slot 1, type "STRING" [7, 3, 0, 5, 1, "STRING"] // The source node (3) must have outputs[0].links containing 7 // The target node (5) must have inputs[1].link = 7

> **Cross-Reference Rule**
>
> Every link_id that appears in the links[] array MUST also appear in: • The source node's outputs[slot].links array • The target node's inputs[slot].link field If any of these three don't agree, the connection is silently dropped.

#### 18.4 Building a New Workflow Programmatically

When generating workflow JSON in code (for testing, templating, or batch creation), use a builder pattern that auto-increments IDs:

class WorkflowBuilder: def __init__(self): self._node_id = 0 self._link_id = 0 self.nodes = [] self.links = [] def add_node(self, node_type, title, pos, widgets_values=None): self._node_id += 1 node = { "id": self._node_id, "type": node_type, "title": title, "pos": pos, "widgets_values": widgets_values or [], "inputs": [], "outputs": [], } self.nodes.append(node) return self._node_id def add_link(self, from_node, from_slot, to_node, to_slot, dtype): self._link_id += 1 self.links.append([self._link_id, from_node, from_slot, to_node, to_slot, dtype]) return self._link_id def export(self): return { "last_node_id": self._node_id, "last_link_id": self._link_id, "nodes": self.nodes, "links": self.links, }

### Section 19: Debugging Workflow JSON

When a workflow doesn't work, the problem is almost always in the JSON. Here's how to find it fast.

#### 19.1 The widgets_values Audit

This is the single most common workflow JSON bug. For every node in the workflow, count the optional widgets in INPUT_TYPES and compare to the length of widgets_values.

---------------\-- ------------------------------\-- ---------------------------- ------------

> **Node**
>
> **Optional Widgets** **widgets_values Length** **Match?**

GooferSanitizer 3 (enabled, banana, blocklist) 3 ✅

GooferPromptGen 1 (model_choice) 1 ✅

SaveAudio 2 (format, quality) 1 ❌ FIX

---------------\-- ------------------------------\-- ---------------------------- ------------

If the counts don't match, values are mapped to the wrong widgets by position. See Section 2 for the full explanation.

#### 19.2 Link Integrity Check

Write a script that validates every link has matching entries on both the source and target nodes:

import json def validate_links(workflow_path): with open(workflow_path) as f: wf = json.load(f) nodes = {n["id"]: n for n in wf["nodes"]} errors = [] for link in wf["links"]: lid, src, src_slot, dst, dst_slot, dtype = link # Check source node exists if src not in nodes: errors.append(f"Link {lid}: source node {src} not found") continue # Check target node exists if dst not in nodes: errors.append(f"Link {lid}: target node {dst} not found") continue # Check source output references this link src_node = nodes[src] if src_slot \< len(src_node.get("outputs", [])): if lid not in src_node["outputs"][src_slot].get("links", []): errors.append(f"Link {lid}: not in node {src} outputs[{src_slot}].links") # Check target input references this link dst_node = nodes[dst] if dst_slot \< len(dst_node.get("inputs", [])): if dst_node["inputs"][dst_slot].get("link") != lid: errors.append(f"Link {lid}: not in node {dst} inputs[{dst_slot}].link") return errors

#### 19.3 Common JSON Failure Modes

---------------------------\-- ---------------------------------------------- ------------------------------------

> **Symptom**
>
> **Cause** **Fix**

Node shows red "missing" type doesn't match NODE_CLASS_MAPPINGS key Check exact spelling and case

Connection line missing link_id mismatch between links[] and node Re-check cross-references

Widget shows wrong value widgets_values positional shift Audit widget count vs array length

"Value not in list" error Stale COMBO value in widgets_values Update to a current valid option

Duplicate node behavior last_node_id too low Set to max(node IDs) + 1

---------------------------\-- ---------------------------------------------- ------------------------------------

#### 19.4 The Nuclear Option: Rebuild from UI

If a workflow JSON is badly corrupted, sometimes the fastest fix is: (1) open ComfyUI with a blank canvas, (2) manually add nodes and connections, (3) set widget values, (4) save as new JSON, (5) diff against the broken version to find what was wrong. This "clean room" approach has saved us hours vs. hand-editing broken JSON.

### Section 20: Workflow JSON Maintenance & Versioning

Workflow JSONs drift. Every time you update a node's INPUT_TYPES, the saved JSONs become stale. Without a maintenance discipline, this drift accumulates.

#### 20.1 Version Your Workflows

Add a comment node (or metadata field) to every workflow JSON with the version and date. When a bug surfaces, you can immediately tell if the workflow predates a code change.

// Add a "Note" node with this content: // Workflow version: 1.3 | Last updated: 2026-03-16 // Compatible with: GooferSanitizer v2, GooferPromptGen v1

#### 20.2 Automated Widget Audit Script

Run this after every code change to catch widget count mismatches before they bite:

import json, ast, os def audit_widgets(node_dir, workflow_path): """Compare INPUT_TYPES optional widget count to widgets_values.""" # Parse each .py for INPUT_TYPES optional dict # Load workflow JSON # For each node in workflow: # Find matching .py class # Count optional widgets in INPUT_TYPES # Compare to len(widgets_values) # Report mismatches pass # implement per your project structure

#### 20.3 Workflow JSON in Git

Always commit workflow JSONs alongside code changes. If you add a widget in Python but don't update the workflow JSON in the same commit, anyone who checks out that commit gets a broken workflow. Atomic commits: code + workflow together.

> **Our Rule**
>
> Every git commit that touches INPUT_TYPES MUST also touch the workflow JSON. If you forget, the regression checklist (Section 10) will catch it. But it's cheaper to get it right the first time.

#### 20.4 Example Workflows as Test Fixtures

Ship example workflows in an example_workflows/ folder. These serve double duty: documentation for users, and regression test fixtures for developers. After every code change, load the example workflow in ComfyUI and verify it runs clean. If it doesn't, the workflow needs updating.

### Section 51: Widget Value Desync After INPUT_TYPES Changes

When you remove a widget from INPUT_TYPES, ComfyUI's saved workflow JSON still has the old widgets_values array. Since widgets_values is position-indexed (not named), removing an entry shifts all subsequent positions. Old workflow JSON maps stale values by their original positions into the new INPUT_TYPES shape, causing desync.

> **Real Example:**
>
> ProceduralClip originally had INPUT_TYPES = [fps, style, motion]. A workflow saved widgets_values = [25, "cinematic", "smooth"]. Later, fps was removed. New INPUT_TYPES = [style, motion]. ComfyUI loads the old workflow's [25, "cinematic", "smooth"] and maps it by position: 25 → style, "cinematic" → motion, "smooth" → LOST. The fps=25 integer now goes into the style dropdown.

> **Root Cause:**
>
> ComfyUI saves widget_values as positional arrays in workflow JSON, not named keys. This was a deliberate design choice for compactness but creates this desync problem.

> **The Fix:**
>
> Manually edit widgets_values in saved workflow JSON after any INPUT_TYPES removal, reordering, or type change. Ensure positions match the new INPUT_TYPES shape.

Rules:

1. Prefer append-only INPUT_TYPES changes (add new widgets at the end, never remove from middle)

2. If you remove widgets, always update all saved workflow JSON files' widgets_values arrays

3. Every git commit touching INPUT_TYPES MUST also commit updated workflow JSON files

4. Add a validation script that loads workflows and checks for position mismatches

This is a silent bug with no error message, so strict process discipline is required.

## Part VI: Quality Assurance & Automation

### Section 7: Content Safety & Filtering

If your node feeds user-supplied or scraped text into an AI model, you need content filtering before it reaches the model.

#### 7.1 Two-Layer Defense

Layer 1: keyword/regex blocklist (instant). Catches unambiguous explicit content. Layer 2: LLM system prompt refuses to generate unsafe content even if borderline input slips through. This layered approach means you don't need a separate AI judge model.

#### 7.2 Copyright Sanitization

Strip actor names, character names, studio names, and brand references. Key patterns: false-positive guards (words like "North" or "King" that look like names), Roman numeral cleanup after name stripping, and context-aware title replacement ("Batman kills" → "the character tickles").

#### 7.3 The Banana Filter

Replace all weapons with bananas. "Machine gun" → "bunch of bananas", "stabbed" → "poked with a banana". Sort replacements longest-first so "machine gun" matches before "gun".

#### 7.4 Rotating Euphemism Pools (Don't Ship `[BLEEP]`)

A content filter that substitutes a single sentinel like `[BLEEP]` into output works for moderation but breaks immersion in narrative pipelines — every substitution announces "this was censored." Replace the sentinel with a **rotating pool of period-appropriate euphemisms** and preserve the original word's capitalization style. The substitution disappears into the prose instead of breaking the fourth wall.

```python
_MINCED_OATHS = [
    # Golden-age radio
    "Golly", "Gee", "Gee whiz", "Jeepers", "Jiminy", "Jiminy Cricket",
    "Heavens", "Good heavens", "My stars", "Goodness gracious",
    "For Pete's sake", "By Jove", "Great Scott", "Cheese and crackers",
    # Pulp adventure
    "Blazes", "Thunderation", "Hot dog", "Holy smokes", "Holy mackerel",
    "Suffering succotash", "Leapin' lizards", "Good grief", "Gadzooks", "Zounds",
    # Sci-fi space-opera
    "Stars above", "By the stars", "Great galaxies", "Sweet cosmos",
    "Thundering comets", "Sputtering satellites",
]

def _content_filter(text: str) -> tuple:
    replacements = []
    cursor = [0]
    def _replace(match):
        word = match.group(0)
        replacements.append(word.lower())
        oath = _MINCED_OATHS[cursor[0] % len(_MINCED_OATHS)]
        cursor[0] += 1
        # Preserve original capitalization style
        if word.isupper():
            return oath.upper()
        if word[0].isupper():
            return oath
        return oath.lower()
    pattern = r'\b(?:' + '|'.join(re.escape(w) for w in sorted(_BLOCKED_WORDS, key=len, reverse=True)) + r')\b'
    cleaned = re.sub(pattern, _replace, text, flags=re.IGNORECASE)
    return cleaned, replacements
```

For child-safe pipelines, swap the pool for *Gosh*, *Heck*, *Goodness*, *Oh my*, *Cripes*. For sword-and-sorcery, swap for *By the Nine*, *Mother of dragons*, *Hells*, *Damnation* (period-flavor cursing). The mechanism is identical; the pool changes to match the genre.

#### 7.5 Procedural Name Leak Guards (Fuzzy-Match, Not Blocklists)

When an LLM occasionally types the wrong character name inside dialogue body — addressing a character as "Rex" when the cast sheet says "Vex" — the wrong fix is a hardcoded blocklist. The right fix is structural fuzzy-matching against your authoritative roster:

```python
import difflib, re

# Extract real cast from authoritative markup
roster = set(re.findall(r'\[VOICE:\s*([A-Z][A-Z0-9_]+)\s*,', script_text))
roster_list = sorted(roster)
leaks_fixed = 0

# Direct-address pattern: capitalized 3-8 char tokens not in roster
addr_pat = re.compile(r'(?<=[,\s])([A-Z][a-z]{2,7})(?=[.,!?\s])')

COMMON_WORDS = {  # English words that look like names
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
        return token
    if token.lower() in COMMON_WORDS:
        return token
    match = difflib.get_close_matches(upper, roster_list, n=1, cutoff=0.55)
    if match:
        leaks_fixed += 1
        return match[0].title()
    return token

script_text = addr_pat.sub(fix_leak, script_text)
if leaks_fixed:
    log.warning("[NameLeakGuard] repaired %d leak(s) — roster=%s",
                leaks_fixed, roster_list)
```

The cutoff value (`0.55`) is critical. Tune empirically: too low and you false-positive on real proper nouns the LLM legitimately invented; too high and you miss obvious typos. Run on archived output and tune until the warning log matches your gut judgment.

**Why this beats a blocklist:** zero hardcoded names, adapts as cast pools grow, logs every repair so you can audit what the LLM was leaking, and falls back gracefully when difflib finds no close match (the unknown token passes through untouched).

#### 7.6 Pool Sizing Per Filtered Subset

A pool with N entries does not have an effective size of N for every consumer — it has an effective size of N **per filter applied**. A TTS pipeline with 9 voice presets has plenty of headroom for a 4-character episode but may collapse to 2 effective presets once you apply a gender filter, then collapse to 0 after de-duplication when a 3-female cast walks in.

Audit pool sizing per filtered subset, not per total. Example: 9 voice presets, only 2 classified female → effective female pool = 2 → any cast with 3+ female characters will silently collide on the same preset and produce two characters who sound identical. The fix is one of:

1. **Reclassify androgynous slots** to fill the underserved subset (e.g., promote `en_speaker_7` from male to female to give a 3rd distinct female voice).
2. **Expand the underlying pool** with new entries.
3. **Accept duplication** and explicitly log it (`POOL_EXHAUSTED` warning) so the user can see the constraint.

Never let a per-subset pool collision happen silently. Log the warning even when you accept the duplication.

### Section 10: Regression Testing Checklist

Run this entire checklist after EVERY code change, before considering the work done. No step is optional.

### 1. Sync ALL changed files from source repo to custom_nodes (not just the file you edited)

### 2. Clear __pycache__ in BOTH the repo and custom_nodes directories

### 3. Hash-compare every .py file between repo and custom_nodes — all must match

### 4. Also hash-compare README.md, requirements.txt, and workflow JSONs

### 5. Run ast.parse on every .py file to catch syntax errors before startup

### 6. Grep for dead references (after removing a dependency, search for its name)

### 7. Verify cross-imports resolve (module cache import chains)

### 8. Widget audit: count INPUT_TYPES optional widgets vs widgets_values in all workflow JSONs

### 9. Verify workflow JSON internal consistency (output link IDs, node counters)

### 10. Commit and push (use Start-Job or batch file on Windows)

### 11. Verify push landed by checking git log on the remote

### 12. Restart ComfyUI fully (not just re-queue) and run the workflow end-to-end

### 13. Run the statistical RNG sanity harness if any RNG-adjacent code changed

### 14. Verify GitHub HEAD lockstep against local after every push (see 10.2)

### 15. Scan for 0-byte files, BOM corruption, and missing node registrations on the remote

#### 10.1 Structured Logging

Use Python's logging module with named loggers. Prefix messages with stage context so you can trace exactly where a regression occurs. When a bug hits, the structured log tells you which clip, which frame count, and which stage failed.

#### 10.2 GitHub HEAD Lockstep Verification

Pushing to a remote is not the same as the remote receiving your changes intact. Windows CRLF/LF conversion, credential helper hangs, partial commits, branch/main confusion, and silent encoding corruption are all real and all common. After every push, verify lockstep:

```bash
# Local checks (run before push)
find . -name "*.py" -size 0                  # Zero-byte files
head -c 3 nodes/*.py | hexdump | grep "ef bb bf"  # BOM markers
python -c "import ast; [ast.parse(open(f).read()) for f in glob.glob('nodes/*.py')]"
grep "NODE_CLASS_MAPPINGS" __init__.py       # Registration intact

# Remote checks (run after push)
git fetch origin <branch>
git log --oneline origin/<branch> -3         # Remote shows expected commits
git diff HEAD origin/<branch>                # Should be empty
```

The single most common failure mode on Windows is `git push origin main` from a feature branch silently doing nothing because there's nothing to push to `main` from the current branch tip — git reports "Everything up-to-date" and you assume success. Always check the actual branch name in `git log`'s output (`branch -> branch`) matches what you intended.

#### 10.3 Statistical RNG Sanity Harness

If your code has any probabilistic feature (easter egg, A/B sampler, jitter, coin flip, sampling threshold), ship a tiny test that runs the same probabilistic check 10,000 times and asserts the observed rate matches the target within tolerance. This is the only way to catch RNG poisoning — eyeballing a few runs is not enough.

```python
# tests/probability_check.py
"""Sanity check — verifies easter-egg fires at the documented rate."""
from secrets import SystemRandom

TARGET_RATE = 0.11
N_TRIALS = 10_000
TOLERANCE = 0.015  # ±1.5%

def main():
    rng = SystemRandom()
    hits = sum(1 for _ in range(N_TRIALS) if rng.random() < TARGET_RATE)
    observed = hits / N_TRIALS
    delta = abs(observed - TARGET_RATE)
    print(f"Sanity check — {N_TRIALS:,} trials")
    print(f"  Target:   {TARGET_RATE:.1%}")
    print(f"  Observed: {observed:.2%}  ({hits:,} hits)")
    print(f"  Delta:    {delta:.2%}  (tolerance {TOLERANCE:.1%})")
    if delta <= TOLERANCE:
        print("  STATUS: PASS")
        return 0
    print("  STATUS: FAIL — RNG is biased")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
```

Ten thousand trials runs in well under a second. The tolerance band (`±1.5%`) is wide enough to never false-positive on healthy RNG and narrow enough to catch a stream that's stuck at 0% or 100%. Make this part of your regression checklist (step 13 above) and run it before every commit that touches RNG-adjacent code.

### Section 14: Removing a Dependency Cleanly

When you replace one model/library with another, the removal is as important as the addition.

### 1. Remove all code references: imports, model loading, inference calls, unload functions

### 2. Remove from requirements.txt if no other node uses it

### 3. Update README sections that mentioned the old dependency

### 4. Grep the entire codebase for the old name (case-insensitive)

### 5. Distinguish code references (bugs) from comment/changelog references (OK to keep)

### 6. If a widget referenced the old model, remove the widget

### 7. If a widget was removed, update widgets_values in ALL workflow JSONs (see Section 2)

### 8. Test that the pipeline runs end-to-end without the old dependency installed

### Section 16: AI Assistant Autonomy & Available Tools

> **Core Principle**
>
> The AI assistant should ALWAYS think "Can I do this myself?" before asking the user. If it has the tools to install, fix, verify, or deploy — it should just do it. The user's time is the bottleneck, not the AI's compute.

#### 16.1 Install Things for the User

When a dependency is missing (like accelerate for Phi-3), the AI should install it immediately instead of saying "you need to run pip install accelerate." The AI has access to PowerShell, can run pip inside the correct venv, and can verify the install worked. The user should never have to copy-paste an install command.

> **Real Example**
>
> Phi-3-mini was falling back to Template mode because accelerate wasn't installed. The log said: "requires accelerate. You can install it with pip install accelerate". The AI should have immediately run the install and verified it, not relayed the message. Fix: pip install accelerate inside the ComfyUI venv via PowerShell Start-Job.

#### 16.2 Fix All Possible Errors Automatically

When the AI sees an error in a log or traceback, it should attempt to fix it before reporting. This includes: installing missing packages, fixing syntax errors, correcting file paths, updating stale workflow JSONs, clearing caches, and re-syncing files. Only escalate to the user if the fix requires a decision the AI can't make (like choosing between two incompatible features).

#### 16.3 Always Regression Test Before Reporting Done

The AI must never say "done" until it has run the full regression checklist from Section 10. This was the single biggest time-waster in the Goofer project: the AI would make a code change, say it was done, and the user would discover stale files, missing widgets, or wrong paths on the next ComfyUI restart. The regression test must be automatic, not something the user has to request.

#### 16.4 Available Tools — Use Them

A modern AI coding assistant typically has access to multiple tool surfaces. Use all of them proactively:

--------------------- ----------------------------------------------------------------------------------

> **Tool**
>
> **When to Use It**

Windows PowerShell Install packages, sync files, run git, check processes, manage services

Linux Bash Syntax checks (ast.parse), grep for dead refs, file editing, Python scripting

Browser Automation GitHub repo creation, checking CI status, reading docs, uploading files

File Read/Write Edit source code directly, update workflow JSONs, write configs

Windows App Control Open/close ComfyUI, switch windows, click buttons user can't reach from terminal

--------------------- ----------------------------------------------------------------------------------

#### 16.5 When to Ask the User for Help

Sometimes the AI hits a wall — a button that won't click, a browser that won't load, a permission it doesn't have. In those cases, ask the user to quickly intervene: "Can you open this URL for me?" or "Can you click the Authorize button?" This is much faster than the AI trying 10 different workarounds. The user has Windows MCP, Chrome browser tools, and can upload files — use those paths when direct access fails.

#### 16.6 Think in Batches, Not Steps

Instead of making one change, reporting it, waiting for confirmation, and then making the next change — batch related changes together. Edit the code, sync to custom_nodes, clear caches, hash-verify, syntax-check, update workflows, commit, and push — all in one pass. Report the summary at the end. This saves massive amounts of back-and-forth time.

#### 16.7 Update Nodes Proactively

When the AI notices a node's code needs updating (outdated API usage, deprecated function calls, missing error handling), it should fix these issues while it's already editing the file. Don't leave known problems for later. If you're in the file, fix everything you see.

> **The Golden Rule for AI Assistants**
>
> Ask yourself: "If I were a senior developer pair-programming with Jeffrey, would I ask him to run this command, or would I just do it myself?" If a senior dev would just do it — you should just do it.

### Section 39: Testing Nodes Without ComfyUI Running

You don't need to restart ComfyUI to catch most bugs. Separate testable logic from ComfyUI wiring.

#### 39.1 Syntax Checks with ast.parse

```
# Run
from bash or PowerShell after every edit
import ast, sys
for path in sys.argv[1:]:
try: with open(path) as f: ast.parse(f.read())
print(f"[OK] {path}")
except SyntaxError as e:
print(f"[FAIL] {path}: {e}") sys.exit(1)
```

#### 39.2 Extract Pure Functions

Move business logic out of execute() into standalone functions that can be tested with pytest. The execute method becomes a thin wrapper: unpack inputs, call pure functions, pack outputs.

```
# sanitizer_logic.py (no ComfyUI dependency)
def replace_weapons_with_bananas(text, replacements):
for weapon, banana in replacements: text = text.replace(weapon, banana)
return text # goofer_sanitizer.py (ComfyUI node)
from .sanitizer_logic
import replace_weapons_with_bananas
class GooferSanitizer:
def execute(self, text, banana_filter=True, **kwargs):
if banana_filter: text = replace_weapons_with_bananas(text, _BANANA_REPLACEMENTS)
return (text,)
```

#### 39.3 Standalone Test Without ComfyUI

```
# test_sanitizer.py
from sanitizer_logic
import replace_weapons_with_bananas
def test_sword_becomes_banana(): result = replace_weapons_with_bananas("He drew his sword", [("sword", "banana")]) assert result == "He drew his banana"
def test_no_partial_match(): result = replace_weapons_with_bananas("swordfish", [("sword", "banana")]) # Decide: should this match or not? Test both behaviors.
```

> **Key Insight**
>
> ast.parse catches syntax errors in 0.1 seconds. pytest catches logic errors in 1\--2 seconds. Restarting ComfyUI catches everything in 30\--60 seconds. Use the fast checks first. Only restart for integration testing.

### Section 48: Quick Reference Card

> **Before Every Commit**
>
> 1. Sync ALL files to custom_nodes (not just the one you changed) 2. Clear __pycache__ in both locations 3. Hash-compare all files between repo and custom_nodes 4. ast.parse every .py file 5. If you added/removed a widget: update widgets_values in workflow JSONs 6. If you removed a dependency: grep for leftover references 7. Restart ComfyUI fully, then run end-to-end

> **When Adding a Widget**
>
> 1. Add to INPUT_TYPES optional dict 2. Add parameter with default to the node's method signature 3. Insert default value at correct position in widgets_values (ALL workflow JSONs) 4. Update your widget audit table 5. Test by loading the workflow from JSON (not just running with current state)

> **When Hitting a Tensor Error**
>
> 1. dtype mismatch (Float vs Half): cast inputs to next(model.parameters()).dtype 2. device mismatch (cuda vs cpu): align with .to(reference.device) 3. dimension mismatch (2D vs 3D): normalize with unsqueeze/squeeze before the op 4. After ANY fix: restart ComfyUI fully (re-queue does NOT reload Python modules)

> **When Swapping a Model**
>
> 1. Verify the correct class name from the HuggingFace model card 2. Remove ALL old model code (loader, inference, unload, globals) 3. Remove from requirements.txt 4. Add new model with lazy-load pattern + device-change cache invalidation 5. Add .eval() after loading 6. Grep codebase for old model name 7. If the old model had a widget toggle, remove the widget + update workflow JSON

> **AUDIO Type Quick Check**
>
> 1. Accept: {"waveform": Tensor[B,C,T], "sample_rate": int} 2. Return the same dict structure — never a raw tensor 3. If you resample, update sample_rate in the returned dict 4. Normalize to 3D (B,C,T) before processing (see Section 6)

> **VALIDATE_INPUTS Quick Check**
>
> 1. Always check if input is None first → return True (it's slot-connected) 2. Only validate values that are actually present 3. Return True for valid, or an error string for invalid

> **Lazy Inputs Quick Check**
>
> 1. Add {"lazy": True} to expensive inputs in INPUT_TYPES 2. Implement check_lazy_status() to return list of actually-needed inputs 3. If disabled, return [] from check_lazy_status → upstream won't execute 4. For blocking downstream too: return ExecutionBlocker(None)

> **When Network Calls Fail**
>
> 1. Use requests → urllib fallback chain 2. Return demo/fallback data instead of crashing 3. Log the failure as a warning, not an error 4. Ship default registry data so nodes work offline

> **When Upgrading transformers or torch**
>
> 1. Check for deprecated params (torch_dtype → dtype) 2. Test model loading OUTSIDE ComfyUI first 3. If device_map fails, use manual .to("cuda").eval() instead 4. If a pipeline task fails, use the model class directly (AutoModelForSeq2SeqLM etc.) 5. Verify CUDA still works: torch.cuda.is_available() 6. Never pin torch in requirements.txt — ComfyUI manages its own version

> **VRAM Quick Check**
>
> 1. Load models to CPU first, let ComfyUI manage GPU placement 2. If manual .to("cuda"): always unload + empty_cache before next heavy model 3. ComfyUI's LRU manager can't see your manually-loaded models 4. Use torch.cuda.memory_summary() to diagnose VRAM leaks

### Section 52: Deployment Encoding Hygiene & Cross-Environment File Transfer

**52. Deployment Encoding Hygiene and Cross-Environment File Transfer Protocols**

During the iterative development and deployment of ComfyUI custom nodes, source files frequently traverse multiple execution environments: Linux-based sandboxes or containers, Windows host filesystems, PowerShell scripting layers, and Git repositories hosted on platforms such as GitHub. Each environment applies its own default encoding assumptions, and careless file transfers between them introduce silent corruption that does not manifest as syntax errors but instead produces garbled string literals, broken docstrings, and repository pollution that persists across clones.

**52.1 PowerShell Set-Content Destroys UTF-8**

The most destructive anti-pattern observed in practice involves using PowerShell's Set-Content cmdlet to write or modify Python source files. Set-Content applies the system's default encoding, which on Windows typically produces UTF-16LE or re-encodes multi-byte UTF-8 sequences. When a Python file contains legitimate Unicode characters --- em dashes (U+2014), arrows (U+2192), or non-ASCII quotation marks --- Set-Content triple-encodes the byte sequences, producing visible mojibake such as ÃƒÆ' in place of a simple ---. This corruption is cosmetically obvious in comments and docstrings but can also silently corrupt string literals used in LLM prompt templates, causing downstream model inference to produce degraded or nonsensical output.

Correct approach: Always use [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8) or WriteAllBytes instead. These write raw UTF-8 bytes without re-encoding and preserve all Unicode characters exactly as specified.

**52.2 UTF-8 BOM Injection**

PowerShell's Out-File and Set-Content cmdlets frequently prepend the UTF-8 Byte Order Mark (BOM, bytes EF BB BF) to files they create or overwrite. While many Windows applications tolerate or expect the BOM, Python's import machinery does not require it, and its presence in .py files violates PEP 263 expectations. When ComfyUI's custom node loader parses the __init__.py or any node module, a BOM-prefixed file may cause subtle import failures or trigger byte-level mismatches during automated integrity checks.

Correct approach: Use [System.IO.File]::WriteAllBytes($path, [System.Text.Encoding]::UTF8.GetBytes($content)) which writes exact bytes with no BOM. Verify with: head -c 3 file | xxd

**52.3 Sandbox-to-Windows Filesystem Mount Failures**

When a Linux sandbox mounts a Windows NTFS or OneDrive-backed directory via a network filesystem or FUSE layer, writes performed from within the sandbox may not propagate reliably to the Windows host. The sandbox process receives a successful write acknowledgment, but the Windows file explorer and Git clients observe no change. This one-directional visibility means that files edited in the sandbox must be explicitly transferred to the Windows host using a reliable mechanism rather than assuming the mounted path provides bidirectional consistency.

Correct approach: Base64-encode files in the sandbox, then decode with [System.IO.File]::WriteAllBytes() on the Windows side. This bypasses the filesystem mount entirely.

**52.4 Git Lock Files on Mounted Filesystems**

Git operations on mounted filesystems frequently fail with "Operation not permitted" errors when creating lock files (.git/index.lock). The assistant should maintain the authoritative Git repository on the sandbox's native filesystem and transfer finalized files to the mounted path only after committing. A fresh clone from the remote repository is the most reliable method to verify that the pushed state is clean.

**52.5 INPUT_TYPES Removal Requires widgets_values Cleanup**

When removing entries from a node's INPUT_TYPES dictionary, simultaneously update all bundled example workflow JSON files. ComfyUI's widgets_values array is strictly positional --- each index maps to the INPUT_TYPES entry at that same ordinal position. Removing a widget (such as fps, sample_rate, or fade_in_sec) without deleting the corresponding positional value from widgets_values causes all subsequent widget values to shift, loading the node with incorrect defaults.

**52.6 transformers 5.0 Migration: Remove trust_remote_code**

When upgrading the transformers library across major versions (e.g., 4.x to 5.x), audit all from_pretrained() calls for the trust_remote_code=True parameter. Models that previously required custom Hub-hosted code --- such as Microsoft's Phi-3-mini --- are natively supported in transformers 5.0. Retaining trust_remote_code=True causes the loader to fetch and execute deprecated remote Python files that are incompatible with the new library internals, producing cryptic AttributeError or TypeError exceptions during model initialization. The correct migration path is to remove the parameter entirely.

**52.7 Post-Transfer Verification Protocol**

After any file transfer to a Git-tracked directory, verify encoding integrity by: (1) checking for BOM bytes with head -c 3 file | xxd, (2) scanning for mojibake patterns with grep -P '[\x80-\xff]{4,}', and (3) confirming that transformers and other version-pinned dependencies in requirements.txt match the actual library API being called in the source code. A fresh clone from the remote is the only reliable final verification.

## Part VII: Building ComfyUI Node Packs with Claude Cowork (v1.1)

The following sections were added after building the entire ComfyUI-OldTimeRadio (SIGNAL LOST) node pack --- 12 nodes, two workflows, a live render monitor, and a procedural video engine --- using Claude Cowork as the primary development environment. Claude Cowork is Anthropic's desktop AI tool: it has a sandboxed Linux shell for running code, file tools (Read/Write/Edit) mounted to a workspace folder on the user's Windows machine, and a Windows MCP (Model Context Protocol) bridge for executing PowerShell commands on the host.

Every section below describes a specific problem encountered during this Cowork-driven build, how it was diagnosed using the tools available in Cowork, and what the fix was. The goal is to help other developers who are using Claude Cowork (or similar AI-assisted development tools) to build ComfyUI custom nodes avoid the same pitfalls.

### Section 53: ffmpeg Subprocess Pipe Deadlock (Diagnosed via Windows MCP Process Inspection)

**Context:** Claude Cowork wrote a video rendering node (SignalLostVideo) that pipes PIL-generated frames to ffmpeg's stdin for MP4 encoding. The first render queued via the ComfyUI API appeared to run --- the node started executing, ffmpeg launched --- but the pipeline never completed.

**How Cowork diagnosed it:** The Windows MCP's PowerShell tool ran `Get-Process python*` on the host machine. The ComfyUI Python process showed 0.046 seconds of cumulative CPU time after several minutes of wall-clock time. That is a dead giveaway: the process is alive but not computing. It is blocked on I/O.

The root cause was a classic subprocess pipe deadlock. The original code set both `stdout=subprocess.PIPE` and `stderr=subprocess.PIPE` on the ffmpeg Popen call. Python writes frame data to ffmpeg's stdin. ffmpeg writes encoding progress to stderr. The OS pipe buffer (64 KB on Linux, 4 KB on Windows) fills up because nobody is reading from those pipes while stdin writes are happening. Once full, ffmpeg blocks on its next stderr write. Python blocks on its next stdin write because ffmpeg stopped reading. Both processes wait on each other forever.

**The fix Cowork applied:**

```python
import subprocess
import tempfile as _tf

# stdout → DEVNULL (we never read it), stderr → temp file (read after encoding)
stderr_file = _tf.NamedTemporaryFile(mode="w+b", prefix="otr_ffmpeg_", suffix=".log", delete=False)

proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,   # never PIPE
    stderr=stderr_file,           # file descriptor, not PIPE
)

for frame in frame_generator():
    proc.stdin.write(frame)
proc.stdin.close()
proc.wait()

# Read ffmpeg's log output AFTER it exits
stderr_file.seek(0)
log_output = stderr_file.read().decode("utf-8", errors="replace")
stderr_file.close()
```

**Why not proc.communicate()?** communicate() buffers the entire stdin payload in memory before sending. For video encoding (thousands of 1080p frames), that means gigabytes of RAM. The temp-file approach lets ffmpeg write its logs without blocking while you stream frames incrementally.

**Cowork-specific lesson:** When Claude Cowork writes code that shells out to external processes, it cannot see the subprocess hang in real time the way a human watching a terminal would. The Windows MCP's process inspection (`Get-Process`, checking CPU time) is the primary diagnostic tool. If cumulative CPU time stops increasing while the process is still alive, suspect a pipe deadlock.

**Rule:** When calling any external process that reads from stdin AND writes to stdout/stderr simultaneously, never set both output pipes to PIPE. Use DEVNULL for the one you don't need and a temp file for the one you do.

### Section 54: Git LFS Filter + Windows Defender — A Compound Hang (Diagnosed via Elimination in Cowork)

**Context:** After Cowork finished writing all the node code and the README, the next step was committing and pushing to GitHub via the Windows MCP's PowerShell tool. Every single git command hung indefinitely --- including `git --version`, which takes no arguments and touches no repo.

**How Cowork diagnosed it:** This required systematic elimination, because there was no error message --- just silence. Cowork ran increasingly minimal commands through the Windows MCP:

1. `echo "test"` → instant. Shell works.
2. `where.exe git` → instant. Git is installed at `C:\Program Files\Git\cmd\git.exe`.
3. `git --version` → hangs. The problem is in git.exe itself, not a specific repo.
4. Read `~/.gitconfig` directly via `Get-Content` → found the culprit:

```ini
[filter "lfs"]
    clean = git-lfs clean -- %f
    smudge = git-lfs smudge -- %f
    process = git-lfs filter-process
    required = true
```

Git for Windows installs this global LFS filter by default. The `process = git-lfs filter-process` directive launches `git-lfs.exe` as a long-running filter for EVERY git operation, even on repos with zero LFS-tracked files. If `git-lfs.exe` hangs (as it did here), every git command inherits the hang.

**First fix — Cowork removed the LFS filter:**

```powershell
$cfg = Get-Content "$env:USERPROFILE\.gitconfig" -Raw
$cleaned = $cfg -replace '(?s)\[filter "lfs"\].*?(?=\[|$)', ''
$cleaned.Trim() | Set-Content "$env:USERPROFILE\.gitconfig" -Encoding utf8
```

But git STILL hung after removing LFS. Cowork then checked `Get-MpComputerStatus` and found Windows Defender Real-Time Protection was enabled. Defender scans every executable on launch. For git.exe --- which spawns child processes like `git-remote-https.exe`, `git-lfs.exe`, and `ssh.exe` --- Defender was holding file locks long enough to cause timeouts in the MCP's PowerShell session.

**Second fix — required the user to run from an Administrator terminal:**

```powershell
Add-MpPreference -ExclusionPath "C:\Program Files\Git"
```

After both fixes (LFS removal + Defender exclusion), git commands completed instantly.

**Cowork-specific lesson:** The Windows MCP's PowerShell tool has a 60-second timeout. When a command times out, Cowork sees `MCP server timed out` with no stderr, no partial output, nothing. This makes it impossible to distinguish "the command is slow" from "the command hung forever." The only diagnostic path is binary elimination: run simpler and simpler commands until you find the boundary between "works" and "hangs." Cowork ran ~20 progressively simpler git invocations before isolating the root cause.

**Important:** The MCP PowerShell session and an admin PowerShell window are separate processes. Defender exclusions added in one don't retroactively fix hung commands in the other. The user had to run the git commit/push from their own admin terminal after both fixes were applied.

**Rule for Cowork developers:** If git hangs through the Windows MCP, check `.gitconfig` for LFS filters first (read the file directly, don't run git), then check Defender status. Both must be resolved. Document Defender exclusions for git and ffmpeg in your node pack's installation guide.

### Section 55: Finding ComfyUI's Actual Install Location (Windows MCP Process Discovery)

**Context:** Cowork needed to find ComfyUI's workspace directory to read logs, check output files, and queue renders via the API. The user's ComfyUI was installed via the Desktop App, which doesn't use the standard `C:\Users\<name>\ComfyUI` path.

**How Cowork found it:** Standard path guesses failed. Cowork used the Windows MCP to inspect running processes:

```powershell
Get-Process python* | Select-Object Id, Path
```

This returned PID 31968 running from `C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe`. From that path, the workspace root was `C:\Users\jeffr\Documents\ComfyUI\`, the custom nodes were in `custom_nodes/`, and the server was confirmed on port 8000 (not the default 8188) by checking the log file at `user/comfyui_8000.log`.

**Cowork-specific lesson:** Never assume ComfyUI's install path. The Desktop App installs the launcher at `AppData\Local\Programs\ComfyUI\` but the workspace (models, custom_nodes, output) lives at `Documents\ComfyUI\`. These are different directories. The running Python process is the only reliable way to find the workspace.

**Rule:** When building automation (monitors, API scripts, OBS integrations) that needs to find ComfyUI's directories, use process inspection first. Hardcoded paths break across install methods.

### Section 56: CPU-Only Video Rendering in ComfyUI (Zero VRAM, Designed in Cowork)

**Context:** The SIGNAL LOST pipeline runs Gemma 4 (~8 GB VRAM) and Bark TTS (~4 GB VRAM) sequentially. Adding GPU-based video rendering would require either waiting for both models to unload or having a second GPU. Cowork designed the video engine to use zero VRAM by rendering entirely on CPU.

**Architecture Cowork built:** PIL (Pillow) for frame composition, numpy for per-frame FFT/RMS audio analysis, raw RGB bytes piped to ffmpeg (see Section 53). The visual elements --- circular frequency ring, orbiting particles, warping geometric grid, mirrored waveform, frequency-spectrum color bars, CRT scan lines, vignette overlay, and audio-reactive noise --- are all drawn with PIL's ImageDraw primitives (lines, arcs, polygons, rectangles).

**Audio analysis is pre-computed for the entire clip before rendering begins:**

```python
samples_per_frame = sample_rate // fps
for fi in range(total_frames):
    chunk = waveform_np[fi * samples_per_frame : (fi + 1) * samples_per_frame]
    volume[fi] = min(1.0, np.sqrt(np.mean(chunk ** 2)) * 5.0)    # RMS
    freqs[fi]  = np.abs(np.fft.rfft(chunk))[:64]                   # 64-bin FFT
    waves[fi]  = chunk[::step][:200]                                 # waveform slice
```

This makes the frame generator a pure function of `(frame_index, precomputed_arrays)` with no redundant computation.

**Performance (measured during actual SIGNAL LOST renders):** A 4-minute episode at 1080p 24fps renders in approximately 4.5 minutes on the user's Intel Core Ultra 9 275HX CPU. The NVIDIA RTX 5080 GPU sits idle during video rendering and is 100% available for the preceding LLM and TTS pipeline stages.

**Cowork-specific lesson:** When Cowork is building a multi-model pipeline, it needs to reason about VRAM as a shared resource across the entire workflow. The sequential unload pattern (Gemma → unload → Bark → unload → video) means video rendering must not touch the GPU at all, because Bark's VRAM cleanup may be incomplete (PyTorch memory fragmentation). CPU-only rendering eliminates this entire class of VRAM contention bugs.

**First version failed:** Cowork's initial video engine attempted to sync dialogue text and character cards to the audio timeline using word-count-based duration estimation (`words / 2.5 wps`). This didn't match Bark's actual output durations, so the text was visibly out of sync. The fix was to remove all script-synced text entirely and replace it with pure procedural audio-reactive art that doesn't need timing data --- only the raw audio waveform.

### Section 57: Output Path Resolution Pitfalls (Sandbox vs Windows Mount)

**Context:** Cowork operates in a sandboxed Linux environment with the user's Windows filesystem mounted at `/sessions/<id>/mnt/`. When Cowork writes code that constructs output paths, those paths must resolve correctly on the Windows host where ComfyUI actually runs --- not in the sandbox.

**The bug Cowork introduced:**

```python
# WRONG — Cowork wrote this, counting parent dirs from nodes/video_engine.py
output_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "output", "old_time_radio"
)
# On Windows at runtime: custom_nodes/ComfyUI-OldTimeRadio/output/old_time_radio/  (WRONG)
# Expected:              Documents/ComfyUI/output/old_time_radio/                    (RIGHT)
```

The `os.path.dirname()` x3 chain walks up from `nodes/video_engine.py` → `nodes/` → `ComfyUI-OldTimeRadio/` → `custom_nodes/`. That's only three levels, not four, so the output directory ended up inside the node pack instead of in ComfyUI's output folder.

**How Cowork caught it:** After the first successful render, the user asked "where's the file?" Cowork checked the expected output directory via Windows MCP and found nothing. Then checked the node pack directory itself and found the MP4 had been written there.

**The fix:**

```python
# CORRECT — matches the EpisodeAssembler pattern and Desktop App default
output_dir = os.path.join(
    os.path.expanduser("~"), "Documents", "ComfyUI", "output", "old_time_radio"
)
```

**Cowork-specific lesson:** Cowork's file tools show paths like `/sessions/lucid-serene-darwin/mnt/ComfyUI/...` which is the Linux mount path. But the code runs on Windows where the path is `C:\Users\jeffr\Documents\ComfyUI\...`. When writing path-construction logic, Cowork must think in terms of the runtime environment (Windows), not its own view of the filesystem (Linux mount). Use `os.path.expanduser("~")` or `folder_paths.get_output_directory()` --- never chain `os.path.dirname(__file__)`.

### Section 58: Audio-Reactive Pipeline Timing & Beat Duration Tuning

**Context:** After the first full pipeline render completed successfully (~33 minutes), the user listened to the output and said the beat pauses between dialogue lines felt too long --- "maybe 200ms?" The default was 800ms.

**The problem:** Beat/pause timing is controlled at three separate layers in the SIGNAL LOST pipeline, and all three had independent defaults:

1. **Parser default** (gemma4_orchestrator.py line 1026): When the script parser encounters `(beat)` in the raw LLM output, it creates a pause event with `duration_ms: 800`.
2. **Director pacing prompt** (gemma4_orchestrator.py line 1130): The Director node's system prompt tells Gemma 4 to use `"beat_pause_ms": 800` when planning production.
3. **Sequencer render** (scene_sequencer.py): The Scene Sequencer renders pauses using whatever duration the script specifies, with no cap.

800ms pauses sound fine in isolation, but a script with 20+ beats adds 16 seconds of dead air. After Bark TTS compression (Bark often produces slightly shorter audio than the word count would predict), the relative silence is even more noticeable.

**What Cowork changed:** All three layers were updated to 200ms:
1. Parser: `duration_ms: 200`
2. Director prompt: `"beat_pause_ms": 200`
3. Sequencer: Added a hard cap: `dur_ms = min(dur_ms, 200)`

The cap in layer 3 acts as a safety net --- even if the LLM hallucinates a 2000ms pause, the sequencer clamps it to 200ms.

**Cowork-specific lesson:** When Cowork builds a multi-stage pipeline where the same parameter appears at different layers (LLM prompt → parser → renderer), it must update ALL layers simultaneously. Cowork used the Grep tool to search for `800` and `beat_pause` across the entire codebase to find every instance before making changes. A partial update (changing the parser but not the Director prompt) would cause inconsistency between freshly-generated scripts and the rendering defaults.

**Rule:** Any timing parameter that appears in more than one layer must be synchronized. Grep for the value across the whole codebase before changing it.

### Section 59: WAV vs MP4 Output Strategy — Memory-Only Passthrough

**Context:** The user watched the pipeline produce both an `episode_001_*.wav` file and a `signal_lost_*.mp4` file every render. They only wanted the MP4 and asked to remove the WAV output.

**What Cowork changed:** The EpisodeAssembler node previously called `soundfile.write()` to save the assembled audio as a WAV file, then returned the AUDIO tensor for downstream nodes. Cowork removed the `sf.write()` call and the accompanying `_log.txt` file write. The node still returns the AUDIO tensor via ComfyUI's in-memory type system, so the SignalLostVideo node downstream receives the exact same data.

```python
# Before: sf.write(output_path, audio_np, sample_rate)  ← disk write removed
# After:
audio_out = {"waveform": episode_waveform, "sample_rate": sample_rate}
output_path = "(video-only — no WAV saved)"
```

The SignalLostVideo node writes a temporary WAV (for ffmpeg to mux with the video) and deletes it after encoding. The user only sees the final `.mp4`.

**Cowork-specific lesson:** When Cowork modifies a node's behavior (removing file output), it must verify that no downstream node depends on the file path string. Cowork checked the workflow JSON to confirm that only the AUDIO tensor output (slot 0) was wired to downstream nodes, not the output_path string (slot 1). The string output still exists for API compatibility but contains a placeholder message.

**Rule:** Only terminal output nodes (the last node in the pipeline) should write permanent files to disk. Intermediate nodes should pass data through ComfyUI's in-memory type system. This reduces I/O, eliminates filename collision bugs, and gives users a single clean deliverable.

### Section 60: OUTPUT_NODE UI Results & Preview Thumbnails

**Context:** After the video engine was working, Cowork added a preview thumbnail feature so users can see a representative frame from the rendered MP4 directly in the ComfyUI graph editor, without opening the file externally.

**The pattern:** ComfyUI nodes with `OUTPUT_NODE = True` can return a dict with `"ui"` and `"result"` keys instead of a plain tuple. The `"ui"` dict is sent to the frontend; the `"result"` tuple is the normal return value for downstream nodes. This is the same mechanism PreviewImage and SaveImage use.

```python
# Extract a frame at ~30% into the video as a representative thumbnail
thumb_path = out_path.replace(".mp4", "_thumb.png")
seek_sec = max(0.5, duration * 0.3)
subprocess.run([
    "ffmpeg", "-y", "-ss", f"{seek_sec:.2f}",
    "-i", out_path, "-frames:v", "1",
    "-q:v", "2", thumb_path,
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

return {
    "ui": {"images": [{"filename": fname, "subfolder": "", "type": "output"}]},
    "result": (out_path,),
}
```

**Key details:**
- Extract at ~30% into the video (not frame 0, which is often a black intro or title card).
- The thumbnail file must be in ComfyUI's output directory for the frontend to find it. The `"type": "output"` field tells the frontend which directory to look in.
- If thumbnail extraction fails (ffmpeg not found, timeout, etc.), return an empty images list. The node still works; it just won't show a preview. Thumbnail generation is advisory, not critical path.
- This adds ~0.5 seconds to the render --- negligible compared to the 4+ minute video encoding.

**Cowork-specific lesson:** When Cowork writes OUTPUT_NODE code, it should always consider whether a UI preview is appropriate. For image nodes this is obvious. For video and audio nodes, extracting a representative thumbnail or waveform image dramatically improves the user's experience in the graph editor. The `{"ui": ..., "result": ...}` return pattern is the standard way to do this and is well-documented in ComfyUI's SaveImage source code.

**Note:** This specific thumbnail implementation was written by Cowork but has not yet been verified in a live ComfyUI render at time of writing. The pattern matches ComfyUI's documented OUTPUT_NODE behavior, but edge cases (subfolder resolution, temp vs output directory) may need adjustment.

### Section 61: LLM Revision Pass Token Decapitation (Diagnosed Across Multiple Episodes in Cowork)

**Context:** SIGNAL LOST v1.2 added a critique-and-revise loop to the Gemma 4 script writer — the LLM generates a draft, critiques itself, then rewrites incorporating the critique. Across multiple test episodes, every external reviewer gave the same feedback: *"the ending is weak."* The opening was praised, the middle was praised, the dialogue was praised, but Scene 4 always landed flat. Cowork tried prompt-level fixes (ending discipline rules, paired bookend instructions, "commit to the bold beat" directives) and none of them moved the needle.

**The diagnosis:** Reading the actual ComfyUI logs showed the smoking gun. The revision pass was budgeted at `max(target_words * 2.0, 1024)` which gave ~2080 tokens for a typical 8-minute episode. But the draft was running ~10,000 characters (~2,500 tokens), and the revision was producing ~7,600 characters and then **stopping mid-word**:

```
[VOICE: KYLE, male, 40s, clipped, stressed] Impact. Small thing hit us.
Micro-meteorite. Hull breach minor near Manifold
[Gemma4] Inference complete in 536.0s.
[Critique] Revision pass complete (7600 chars)
[Critique] Checks & Critiques complete — revised script accepted (similarity=74.8%, length ratio=75%).
```

The revision pass was decapitating Scene 4 because the token budget was sized from the original `target_words` instruction, not from the actual draft length. The downstream similarity check (74.8%) and length-ratio check (75%) both passed because the truncation was inside acceptable bounds. The script that shipped was missing its ending. Reviewers were correct about the symptom but wrong about the cause — the writing wasn't weak, the writing was *missing*.

**The fix:** Size the revision token budget from the actual draft character count, not from the original `target_words` parameter:

```python
# WRONG — sizes from prompt intent, ignores draft reality
revision_tokens = max(int(target_words * 2.0), 1024)
revision_tokens = min(revision_tokens, 8192)

# RIGHT — sizes from draft length with safety floors and ceiling
draft_token_estimate = int(len(draft_text) / 3.5)   # ~3.5 chars/token English
revision_tokens = max(
    int(draft_token_estimate * 1.25),                # 25% headroom
    int(target_words * 2.0),                         # never below original
    2048,                                            # absolute floor
)
revision_tokens = min(revision_tokens, 8192)         # absolute ceiling
log.info("[Critique] Revision token budget: %d (draft_est=%d, target_words=%d)",
         revision_tokens, draft_token_estimate, target_words)
```

**Cowork-specific lesson:** When external reviewers consistently identify the same narrative weakness across multiple episodes, **read the actual generation logs before touching the prompt**. Prompt-level fixes for what is actually a token-budget bug will always fail and waste hours of iteration. The log line that gives away the bug is usually short and unremarkable — `[Critique] Revision pass complete (7600 chars)` does not look like a smoking gun until you compare it against the draft length.

**Rule:** Any LLM call that operates over previously-generated content must size its output budget from the **content**, not from the original generation params. The original params represent intent; the content represents reality. Budget for reality.

### Section 62: ROADMAP.md as AI Session Continuity Brief

**Context:** SIGNAL LOST v1.2 was built across multiple Cowork sessions over several weeks. Each session, the new Cowork instance had to spend 30+ minutes of context budget rediscovering "where are we, what shipped, what's queued, what are the standing rules" before any productive work could happen. Long sessions ran out of context not because the work was hard but because the context budget was burned on archaeology.

**The fix Cowork built:** Restructure `ROADMAP.md` with a `🤖 NEW CONVERSATION HANDOFF` section at the top, written specifically for a cold-start AI assistant rather than for humans. Include:

1. **Current shipped state** — version, tag, commit SHA, commit message of the most recent merge
2. **Recent commits with file paths and line numbers** — not just "fixed bug" but "FIX-2 (~line 234) replaced `[BLEEP]` with `_MINCED_OATHS` rotation in `_content_filter`"
3. **Next priority feature with full design spec** — phase-by-phase, where to plug it in, which file, approximate line range
4. **Standing rules (user preferences) — DO NOT VIOLATE** — code style, forbidden patterns, operational constraints, things that look like nice-to-haves but are actually hard rules
5. **First moves for next session** — `git status`, `git pull`, branch checkout, build targets, test commands, in order

```markdown
## 🤖 NEW CONVERSATION HANDOFF — READ THIS FIRST

If you are a fresh Claude opening this repo with no prior conversation context,
this section is your continuity brief. Read it before doing anything else.

### Where we are (end of session 2026-04-08)

**v1.2.0 is SHIPPED to main.** Tag `v1.2.0` exists. README is polished.

| Commit | What landed |
|--------|-------------|
| `ce07e70` | README v1.2 polish |
| `7b67bae` | Merge `v1.2-narrative-beta` → `main`, tagged `v1.2.0` |
| `d9a03f8` | v1.2.0.5 bug fixes (revision budget + minced oaths + female pool + leak guard) |

### What's queued for v1.3
[full spec with file paths, line refs, phase-by-phase implementation steps]

### Standing rules (DO NOT VIOLATE)
- No baked character names anywhere in code or comments
- No hardcoded blocklists for names — use difflib structural matching
- All git commands run manually in PowerShell with `cd` baked in
- Verify GitHub HEAD lockstep against local after every push
- Always run `python tests/lemmy_rng_check.py` before declaring done

### First moves for next session
1. git status (confirm clean main)
2. git pull origin main
3. git checkout -b v1.3-arc-enhancer
4. Build _arc_check_and_rewrite_bookends() per spec above
5. Run regression: AST parse + Lemmy RNG check
```

The cost is ~10 minutes of writing at the end of a session. The savings on the next session's first 30 minutes is dramatic — instead of "let me explore the repo and figure out what's going on" you get straight to "I read the handoff, here's the PowerShell block to branch and start work."

**Cowork-specific lesson:** Treat the roadmap as a **structured prompt for your future AI collaborator**. It is one. Write it in the imperative voice, with specific file paths and line numbers, with rules that read like constraints rather than suggestions. The next AI is going to read this cold and start making decisions immediately — give it everything it needs to make the right ones.

**Rule:** Any project that will span multiple AI sessions needs a continuity handoff doc, and the doc needs to be updated at the end of each session before the conversation closes. A roadmap that only describes ambitions is useless to the next session; a roadmap that describes state, queue, rules, and first moves is priceless.

### Section 63: Production Repo Hygiene — No Dev Artifacts in Public Trees

**Context:** SIGNAL LOST v1.2 development generated a lot of intermediate documentation: `BUG_FIX_GUIDE_v1.2.md`, `KICKOFF_v1.2.md`, `LEMMY_QA_GUIDE.md`, `v1.2-planning.md`, `QA_GUIDE_v1.2_beta.md`, `QA_SIGNOFF_v1.1.md`, `PEER_REVIEW_REQUEST_v1.2_beta.md`, `GEMINI_RNG_AUDIT.md`. All of them were useful during development. None of them belong in the shipped repository.

**The user's instruction:** *"no qa signoff just prod ready files and beat needed pdf files"* — translation: ship only the things a downstream user needs to install, run, and understand the node pack. Everything else is dev artifact and should live in your local notes, not in the public tree.

**The cleanup pattern Cowork applied:**

1. List all `.md` files in the repo
2. For each one, ask: "would a brand-new user who just installed this from ComfyUI Manager need this file?"
3. If the answer is no, `git rm` it
4. Verify only `README.md`, `ROADMAP.md`, `LICENSE`, and `CLAUDE.md` (per-repo project instructions) remain in markdown form
5. Test files belong in `tests/`, not in the repo root

**The git rm cascade gotcha:** Cowork ran into a real failure mode here. When deleting multiple files via `git rm file1.md file2.md file3.md`, if **any** of those files has already been deleted from the working tree (e.g., via Bash `rm` earlier in the session), git fails on the missing file and **does not stage the others** — fatal error, zero deletions land. The fix is to delete files one at a time, or to check `git status` first and only `git rm` files that are still present:

```powershell
git status                    # See which files git knows about
git rm file1.md               # Stage one at a time
git rm file2.md
git rm file3.md
git commit -m "cleanup: remove stale dev artifacts"
```

**Cowork-specific lesson:** When operating in a Cowork session that has both Bash and PowerShell tooling available, file operations done via Bash do not always synchronize cleanly with git operations done via PowerShell — they're separate processes with separate views of the working tree. Prefer one tool consistently for file ops within a single staging cycle, or use `git status` as the source of truth before every `git rm`.

**Rule:** Public node-pack repos should contain only what a brand-new user needs. Dev artifacts (planning docs, kickoff notes, peer review requests, QA signoffs, internal audits) belong in a separate private notes location. Ship narrow.

### Section 64: Cast Pool Combinatorics & Public Domain Safety

**Context:** SIGNAL LOST procedurally generates character names from first/last name pools. The v1.0 pools were small enough that name collisions across episodes were noticeable — listeners would recognize "the same cast" even though the per-episode RNG draws were unique. v1.2 expanded the pools to maximize uniqueness while staying defensible against trademark claims.

**The math Cowork applied:** With `N` first names and `M` last names, the combinatoric space is `N × M` unique full names. For a 4-character episode drawn from a pool that allows duplicates only at the per-episode level, you want `N × M ≫ 4`, ideally `N × M > 1000` for "feels random across hundreds of episodes." SIGNAL LOST v1.2 ships `154 × 54 = 8,316` unique combinations.

**The copyright safety filter Cowork applied:**

1. **Public domain only for franchise-flavored names** — pre-1931 in the United States (current public domain cutoff for character names tied to specific works). Sherlock Holmes, Allan Quatermain, Captain Nemo, Wendy Darling are safe. Indiana Jones, James Bond, Luke Skywalker are not.
2. **Generic given names from pop culture franchises are safe** — Homer, Bart, Marge, Lisa from The Simpsons are common given names with no character-specific trademark; "Bart Simpson" together is risky but "Bart" alone in a sci-fi context is fine. Same logic for Office characters (Michael, Pam, Kevin), Bradbury characters (Beatty, Spender, Eckels), and PKD-flavored generic names.
3. **Last names of public figures are safe** — Pryor, Williams, Carrey, O'Toole as last names cannot be trademarked; they're common surnames belonging to many real people.
4. **Strip franchise-specific compound names** — "Schrute," "Banzai," "Whorfin," "Krusty," "Wiggum," "Zarkov," "Skywalker," "Vader" all need to come out. Common-word last names that happen to also be franchise characters are case-by-case judgment calls.
5. **No actor names as full names** — "Steve Carell" is identifiable; "Steve" or "Carell" alone is fine.

**The single-token regex constraint:** SIGNAL LOST's `[VOICE: NAME, ...]` parser uses a single-token regex (`[A-Z][A-Z0-9_]+`), so name pool entries cannot contain spaces. "Perfect Tommy" must become "Tommy"; "Van Houten" must become "Houten". Always validate name pool entries against your downstream parser before adding them — a name with a space will silently break the cast assignment for that episode and you'll spend an hour wondering why one character is missing dialogue.

**Cowork-specific lesson:** When building procedural content pools, the math is the easy part. The legal hygiene and parser-compatibility validation are where the bugs hide. Ship a small validation script that asserts `N × M > THRESHOLD` and that no entry contains spaces, and run it in CI:

```python
# tests/cast_pool_check.py
from nodes.gemma4_orchestrator import _FIRST_NAMES, _LAST_NAMES

assert all(' ' not in n for n in _FIRST_NAMES), "First name with space breaks parser"
assert all(' ' not in n for n in _LAST_NAMES), "Last name with space breaks parser"
combos = len(_FIRST_NAMES) * len(_LAST_NAMES)
assert combos > 1000, f"Pool too small: {combos}"
print(f"Cast pool OK: {len(_FIRST_NAMES)} × {len(_LAST_NAMES)} = {combos:,} unique combinations")
```

**Rule:** Procedural content pools for shipped code need three safety nets — combinatoric size, parser compatibility, and copyright defensibility. Bake all three into a CI test.

### Section 65: TTS Voice Preset Pool Sizing Per Filtered Subset

**Context:** SIGNAL LOST v1.2 uses Bark TTS with `en_speaker_0` through `en_speaker_9` — 10 English-native voice presets. The pipeline classifies each preset by gender (male/female/androgynous) and the cast assignment logic enforces gender match between the script's `[VOICE: NAME, gender, ...]` markup and the assigned preset. v1.1 had this working for typical 4-character episodes; v1.2 broke when an episode generated a 3-female cast.

**The bug:** The `_VOICE_PROFILES` table classified only 2 presets as female (`en_speaker_4` and `en_speaker_9`). Episodes with 3 or more female characters would exhaust the female pool, the de-duplication loop would re-roll 10 times trying to find an unused female preset, fail, and accept the duplicate with a warning:

```
[Gemma4Director] CAST_GENDER_POOL_EXHAUSTED: ZARA (female) reusing preset v2/en_speaker_9
```

The pipeline kept running, the episode kept rendering, and two characters (VEX and ZARA) ended up with the same Bark voice. External reviewers consistently flagged this as "the female characters all sound the same" and Cowork initially diagnosed it as a writing problem (Pattern 5 vocal blueprints needing tightening) when it was actually a pool-sizing problem.

**The fix:** Reclassify `en_speaker_7` from male/androgynous to female. Bark labels this preset as androgynous in its documentation; in English it reads as a younger, lighter voice that fits naturally as a 20s-30s female slot. This brought the effective female pool from 2 to 3, which covers any realistic SIGNAL LOST cast.

```python
# BEFORE
("v2/en_speaker_7", "male",   "en", {"sharp", "anxious", "20s", "30s"}),  # androgynous but reads male

# AFTER
("v2/en_speaker_7", "female", "en", {"sharp", "anxious", "nervous", "20s", "30s"}),
# Reclassified to female to prevent CAST_GENDER_POOL_EXHAUSTED on 3-female episodes.
# Bark labels en_speaker_7 as androgynous — in English it reads soft/lighter so we
# use it as the "younger" female slot (20s, anxious/sharp). Gives us 3 distinct
# female presets (4, 7, 9) covering young/warm-adult/mature ranges.
```

**Cowork-specific lesson:** When a "writing quality" complaint maps to "two characters share an identifying attribute" (voice, name, color, costume), check the **assignment layer** before touching the writing layer. Pool exhaustion bugs masquerade as creative bugs because the symptom is on the surface — listeners hear identical voices and conclude "the writer didn't differentiate the characters" when the writer actually did and the pipeline collapsed two distinct characters onto one preset.

**The general rule:** Audit assignment pool sizing against the **maximum filtered subset demand**, not the total pool size. A pool of 10 with 2 female entries has an effective female pool of 2 — and any 3-female cast will collide. The fix is one of:

1. Reclassify ambiguous slots to fill the underserved subset
2. Expand the underlying pool with new entries
3. Accept duplication explicitly with a `POOL_EXHAUSTED` log warning

Never let a per-subset collision happen silently. Even when you accept the duplication, log it loudly enough that a reader of the production logs can see the constraint.

*End of Document — v1.2 (SIGNAL LOST Edition)*
