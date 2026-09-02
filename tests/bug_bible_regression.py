"""
Bug Bible Regression Test Suite
================================

Machine-executable verification of Bug Bible entries against a ComfyUI
custom node pack. Encodes the 'verify' field of each relevant bug as
an automated assertion that runs in < 5 seconds with pytest.

Usage:
    # From the custom node pack directory:
    python -m pytest <path>/tests/bug_bible_regression.py -v --pack-dir .

    # Or specify a pack directory:
    python -m pytest tests/bug_bible_regression.py -v --pack-dir /path/to/my/pack

    # Run specific bug category:
    python -m pytest tests/bug_bible_regression.py -v --pack-dir . -k "phase03"

Requirements:
    - Python 3.10+
    - pytest
    - No ComfyUI runtime needed (pure static analysis)

What it checks (by Bug Bible phase):
    Phase 01: Path safety (no dirname chains, folder_paths usage)
    Phase 02: Encoding (UTF-8 no BOM, no mojibake markers)
    Phase 03: Registration (isolated loading, no ghost nodes)
    Phase 04: Widget ordering (INPUT_TYPES structure); BUG-04.06 (title resolution)
    Phase 05: Execution order (passthrough enforcement); BUG-05.07 (scope NameError)
    Phase 07: VRAM discipline (unload/flush patterns)
    Phase 09: Subprocess safety (pipe deadlocks, cleanup)
    Phase 11: LLM patterns; BUG-11.08/11.09/11.10/11.11 (dialogue parser, JSON comments)
    Phase 12: Git/repo hygiene (0-byte files, workflow JSON integrity)

Entries marked for integration testing (not static):
    BUG-04.06: Title resolution multi-tier fallback (requires full script generation)
    BUG-05.07: Variable scope NameError (requires extension pass execution)
    BUG-11.08: TITLE false-positive in dialogue (requires parsing output)
    BUG-11.09: Bare NAME: format detection (requires script parsing)
    BUG-11.10: Markdown wrapper stripping (requires title extraction output)
    BUG-11.11: JSON comment stripping (requires Director JSON parsing)
"""

import ast
import json
import os
import re
import subprocess
import sys

import pytest


# ─────────────────────────────────────────────────────────────────
# FIXTURES AND CONFIGURATION
# ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def pack_dir(request):
    """Resolve and validate the pack directory."""
    path = os.path.abspath(request.config.getoption("--pack-dir"))
    if not os.path.isdir(path):
        pytest.skip(f"Pack directory not found: {path}")
    return path


@pytest.fixture(scope="session")
def py_files(pack_dir):
    """Collect all .py files in the pack (excluding __pycache__).

    BUG-12.36: Also explicitly excludes internal virtual environment
    folders like .venv.

    Also excludes:
      - the survival-guide's own ``tests/`` directory (the regression
        test file contains literal mojibake patterns,
        ``.get("completed", True)`` examples, and ``communicate()``
        / ``ffmpeg`` mentions inside docstrings — those are PATTERN
        DEFINITIONS, not violations);
      - the bundled ``llm_round_robin/`` addon (it's a tool, not a
        node pack file; tests for it live in ``tests/`` and run
        separately).
    """
    found = []
    excluded_dirs = (
        "__pycache__", ".git", ".venv", "venv", "tests", "llm_round_robin"
    )
    for root, dirs, files in os.walk(pack_dir):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for f in files:
            if f.endswith(".py"):
                found.append(os.path.join(root, f))
    return found


@pytest.fixture(scope="session")
def init_py(pack_dir):
    """Read the pack's __init__.py content."""
    init_path = os.path.join(pack_dir, "__init__.py")
    if not os.path.isfile(init_path):
        pytest.skip("No __init__.py found")
    with open(init_path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def init_tree(init_py):
    """Parse __init__.py into an AST."""
    return ast.parse(init_py)


@pytest.fixture(scope="session")
def node_modules_dict(init_py, pack_dir):
    """Extract the _NODE_MODULES or NODE_CLASS_MAPPINGS dict entries.

    Returns a list of (node_id, module_path, class_name) tuples.
    """
    # Pattern: "OTR_Name": (".module.path", "ClassName", ...)
    pattern = r'"(\w+)":\s*\(\s*"([^"]+)"\s*,\s*"(\w+)"'
    matches = re.findall(pattern, init_py)
    return matches


@pytest.fixture(scope="session")
def workflow_jsons(pack_dir):
    """Collect all workflow .json files."""
    found = []
    workflows_dir = os.path.join(pack_dir, "workflows")
    if os.path.isdir(workflows_dir):
        for f in os.listdir(workflows_dir):
            if f.endswith(".json"):
                found.append(os.path.join(workflows_dir, f))
    return found


# ─────────────────────────────────────────────────────────────────
# PHASE 01 — BOOTSTRAP & DISCOVERY
# BUG-01.02: Use folder_paths, not hand-rolled paths
# BUG-01.03: No dirname chain miscounts
# ─────────────────────────────────────────────────────────────────

class TestPhase01Paths:
    """Verify path construction safety (BUG-01.02, BUG-01.03)."""

    def test_no_deep_dirname_chains(self, py_files):
        """BUG-01.03: No os.path.dirname chains deeper than 3 levels.

        Chains of 4+ dirname() calls almost always miscount the
        directory depth and land in the wrong place.
        """
        violations = []
        # Match dirname(dirname(dirname(dirname(  — 4+ levels
        pattern = re.compile(
            r"os\.path\.dirname\s*\(\s*"
            r"os\.path\.dirname\s*\(\s*"
            r"os\.path\.dirname\s*\(\s*"
            r"os\.path\.dirname"
        )
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if pattern.search(content):
                violations.append(os.path.basename(fpath))

        assert not violations, (
            f"BUG-01.03: Deep dirname chains (4+) found in: "
            f"{', '.join(violations)}. Use folder_paths or a "
            f"module-level _REPO_ROOT anchor instead."
        )

    def test_output_nodes_use_folder_paths(self, py_files):
        """BUG-01.02: Nodes that write output files should use
        folder_paths.get_output_directory(), not hand-rolled paths.

        Checks files containing OUTPUT_NODE = True. Also the static
        half of BUG-08.06 (an OUTPUT_NODE must write a real artifact
        via a sanctioned path helper).
        """
        warnings = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if "OUTPUT_NODE" not in content:
                continue
            if "OUTPUT_NODE = True" in content or "OUTPUT_NODE=True" in content:
                # This is an output node — check for folder_paths usage
                # Also allow: _REPO_ROOT anchor, or user-supplied output_dir
                has_safe_path = (
                    "get_output_directory" in content or
                    "folder_paths" in content or
                    "_REPO_ROOT" in content or
                    "output_dir" in content or   # user-configurable path
                    "output_path" in content      # caller-supplied path
                )
                if not has_safe_path:
                    warnings.append(os.path.basename(fpath))

        assert not warnings, (
            f"BUG-01.02: Output nodes without folder_paths usage: "
            f"{', '.join(warnings)}"
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 02 — ENVIRONMENT & DEPENDENCIES
# BUG-02.11: No mojibake from PowerShell writes
# BUG-02.12: No BOM signatures
# ─────────────────────────────────────────────────────────────────

class TestPhase02Encoding:
    """Verify file encoding integrity (BUG-02.11, BUG-02.12)."""

    def test_no_bom_signatures(self, py_files):
        """BUG-02.12: No UTF-8 BOM (EF BB BF) in any Python file.

        BOM injected by PowerShell's Set-Content/Out-File causes
        subtle import failures and hash mismatches.
        """
        bom_files = []
        for fpath in py_files:
            with open(fpath, "rb") as f:
                head = f.read(3)
            if head == b"\xef\xbb\xbf":
                bom_files.append(os.path.basename(fpath))

        assert not bom_files, (
            f"BUG-02.12: BOM detected in: {', '.join(bom_files)}. "
            f"Use [System.IO.File]::WriteAllText() on Windows."
        )

    def test_no_mojibake_markers(self, py_files):
        """BUG-02.11: No mojibake sequences from encoding corruption.

        Common mojibake patterns: a]a (em dash), A(c) (e-acute),
        a]a' (right single quote). These appear when UTF-8 multi-byte
        sequences are re-encoded through a single-byte codepage.
        """
        mojibake_pattern = re.compile(
            r"\xc3\xa2\xe2\x82\xac"  # raw bytes of common mojibake
            r"|"
            r"\u00e2\u0080\u0093"     # Unicode codepoints of em-dash mojibake
            r"|"
            r"Ã¢â‚¬"                  # String-level mojibake
            r"|"
            r"â€"                     # Em-dash mojibake in text
            r"|"
            r"â€™"                    # Right single quote mojibake
            r"|"
            r"Ã©"                     # e-acute mojibake
        )
        corrupted = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if mojibake_pattern.search(content):
                corrupted.append(os.path.basename(fpath))

        assert not corrupted, (
            f"BUG-02.11: Mojibake detected in: {', '.join(corrupted)}"
        )

    def test_no_zero_byte_files(self, py_files):
        """BUG-12.16 adjacent: No 0-byte Python files in the pack."""
        empty = []
        for fpath in py_files:
            if os.path.getsize(fpath) == 0:
                empty.append(os.path.basename(fpath))

        assert not empty, (
            f"0-byte Python files found: {', '.join(empty)}"
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 03 — REGISTRATION & LOADING
# BUG-03.01: Isolated per-node loading
# BUG-03.03: Namespaced node IDs
# BUG-12.23: Ghost node registration
# ─────────────────────────────────────────────────────────────────

class TestPhase03Registration:
    """Verify node registration integrity."""

    def test_isolated_loading(self, init_py):
        """BUG-03.01: All node imports wrapped in try/except.

        Default __init__.py imports all nodes at module scope.
        One broken node should not crash the entire pack.
        """
        # Check for importlib pattern (preferred)
        has_importlib = "importlib.import_module" in init_py
        # Check for try/except wrapping
        has_try_except = "try:" in init_py and "except" in init_py

        assert has_importlib or has_try_except, (
            "BUG-03.01: __init__.py does not use isolated per-node "
            "loading. Wrap imports in try/except or use importlib."
        )

    def test_no_ghost_node_registrations(self, node_modules_dict, pack_dir):
        """BUG-12.23: Every registered node class must exist on disk.

        Consolidating or refactoring without updating _NODE_MODULES
        leaves ghost entries that fail at boot with 'has no attribute'.
        """
        ghosts = []
        for node_id, module_path, class_name in node_modules_dict:
            # Convert module path to file path
            file_path = module_path.replace(".", os.sep).lstrip(os.sep)
            file_path += ".py"
            full_path = os.path.join(pack_dir, file_path)

            if not os.path.isfile(full_path):
                ghosts.append(f"{node_id} -> {module_path} (file missing)")
                continue

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if f"class {class_name}" not in content:
                ghosts.append(
                    f"{node_id} -> {module_path}::{class_name} "
                    f"(class not found in file)"
                )

        assert not ghosts, (
            f"BUG-12.23: Ghost node registrations:\n  "
            + "\n  ".join(ghosts)
        )

    def test_namespaced_node_ids(self, node_modules_dict):
        """BUG-03.03: Node IDs should be namespaced to avoid collisions.

        At least 50% of node IDs should have a prefix (e.g., OTR_),
        matching the ratio asserted below.
        """
        if not node_modules_dict:
            pytest.skip("No node registrations found")

        has_prefix = sum(
            1 for node_id, _, _ in node_modules_dict
            if "_" in node_id and node_id.split("_")[0].isupper()
        )
        total = len(node_modules_dict)
        ratio = has_prefix / total if total > 0 else 0

        assert ratio >= 0.5, (
            f"BUG-03.03: Only {has_prefix}/{total} node IDs are "
            f"namespaced. Use PREFIX_NodeName to avoid collisions."
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 04 — INPUT_TYPES & WIDGETS
# BUG-04.01: Widget positional stability
# BUG-04.02: Widget removal shifts positions
# ─────────────────────────────────────────────────────────────────

class TestPhase04Widgets:
    """Verify INPUT_TYPES and widget contract integrity."""

    def test_all_nodes_have_valid_input_types(self, py_files, pack_dir):
        """BUG-04.01 adjacent: Every node class with INPUT_TYPES
        should return a dict with 'required' key.

        Malformed INPUT_TYPES cause silent widget misalignment.
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Find all INPUT_TYPES definitions
            if "def INPUT_TYPES" not in content:
                continue

            try:
                tree = ast.parse(content)
            except SyntaxError:
                issues.append(f"{os.path.basename(fpath)}: SyntaxError")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if (isinstance(item, ast.FunctionDef) and
                                item.name == "INPUT_TYPES"):
                            # Check it has a return statement
                            has_return = any(
                                isinstance(n, ast.Return)
                                for n in ast.walk(item)
                            )
                            if not has_return:
                                issues.append(
                                    f"{os.path.basename(fpath)}::"
                                    f"{node.name}: INPUT_TYPES has "
                                    f"no return statement"
                                )

        assert not issues, (
            f"BUG-04.01: INPUT_TYPES issues:\n  "
            + "\n  ".join(issues)
        )

    def test_workflow_widget_counts(self, workflow_jsons, node_modules_dict,
                                    pack_dir):
        """BUG-04.01/04.02: structural half of the widget contract.

        The full positional widgets_values-vs-INPUT_TYPES count audit
        needs live node imports and runs in OTR_WorkflowValidator at
        workflow load. Statically, this verifies the workflow JSONs
        parse and node structures are well-formed.
        """
        if not workflow_jsons:
            pytest.skip("No workflow JSONs found")

        # This is a structural check only — we verify that workflow
        # JSONs parse and have well-formed node structures
        for wf_path in workflow_jsons:
            with open(wf_path, "r", encoding="utf-8") as f:
                try:
                    wf = json.load(f)
                except json.JSONDecodeError as e:
                    pytest.fail(
                        f"Workflow JSON corrupt: {os.path.basename(wf_path)}"
                        f": {e}"
                    )

            # Check for duplicate node IDs
            if "nodes" in wf:
                node_ids = [n.get("id") for n in wf["nodes"] if "id" in n]
                dupes = [x for x in node_ids if node_ids.count(x) > 1]
                assert not dupes, (
                    f"BUG-12.06: Duplicate node IDs in "
                    f"{os.path.basename(wf_path)}: {set(dupes)}"
                )


# ─────────────────────────────────────────────────────────────────
# PHASE 05 — EXECUTION MODEL
# BUG-05.05: Execution order enforcement via passthrough
# ─────────────────────────────────────────────────────────────────

class TestPhase05Execution:
    """Verify execution order contracts."""

    def test_memory_boundary_has_passthrough(self, py_files):
        """BUG-05.05: MemoryBoundary nodes must have a required
        passthrough input to enforce ComfyUI execution order.

        Without it, the scheduler may run boundary AFTER the model
        load, producing non-deterministic OOMs.
        """
        for fpath in py_files:
            basename = os.path.basename(fpath)
            if "memory_boundary" not in basename:
                continue

            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Must have a class with INPUT_TYPES containing IMAGE or
            # another forced passthrough type in required
            if "class " in content and "INPUT_TYPES" in content:
                has_passthrough = (
                    '"IMAGE"' in content or
                    '"MODEL"' in content or
                    '"LATENT"' in content or
                    "forceInput" in content
                )
                assert has_passthrough, (
                    f"BUG-05.05: {basename} has no passthrough input. "
                    f"Add a required IMAGE/MODEL/LATENT input to enforce "
                    f"execution order."
                )


# ─────────────────────────────────────────────────────────────────
# PHASE 07 — TENSORS, AUDIO, VIDEO / VRAM
# BUG-07.01: Lazy load + explicit unload
# BUG-07.03: Use comfy.model_management or manual unload
# ─────────────────────────────────────────────────────────────────

class TestPhase07VRAM:
    """Verify VRAM discipline."""

    def test_no_module_scope_model_loads(self, py_files):
        """BUG-07.01/BUG-03.02: No heavy model loads at module scope.

        from_pretrained, torch.load, load_checkpoint at module scope
        (outside a function/class) cause slow startup and VRAM leak.
        """
        # BUG-07.01b (2026-06-07): detect ACTUAL heavy-loader CALLS at
        # module scope via the AST, not a substring scan of the source.
        # The prior substring check ("from_pretrained" in source segment)
        # false-positived on module-scope config dicts / docstrings that
        # merely MENTION the loader name as a string literal (e.g. an
        # adapter's documented ``assumed_call`` text), reporting a plain
        # data assignment as a VRAM violation. Matching real ``ast.Call``
        # nodes to ``*.from_pretrained(...)`` / ``torch.load(...)`` keeps
        # the exact detection scope of the old check while ignoring
        # strings -- a strict subset, so it can never newly flag code the
        # old substring scan would have passed.
        def _is_heavy_loader_call(call: ast.Call) -> bool:
            fn = call.func
            if isinstance(fn, ast.Attribute):
                if fn.attr == "from_pretrained":
                    return True
                if (fn.attr == "load" and isinstance(fn.value, ast.Name)
                        and fn.value.id == "torch"):
                    return True
            elif isinstance(fn, ast.Name) and fn.id == "from_pretrained":
                return True
            return False

        violations = []
        for fpath in py_files:
            try:
                tree = ast.parse(open(fpath, "r", encoding="utf-8").read())
            except SyntaxError:
                continue

            # Only module-scope statements (outside any function/class).
            for node in ast.iter_child_nodes(tree):
                if not isinstance(node, (ast.Expr, ast.Assign)):
                    continue
                if any(isinstance(sub, ast.Call) and _is_heavy_loader_call(sub)
                       for sub in ast.walk(node)):
                    violations.append(
                        f"{os.path.basename(fpath)}:L{node.lineno}"
                    )

        assert not violations, (
            f"BUG-07.01: Module-scope model loads found:\n  "
            + "\n  ".join(violations)
        )

    def test_vram_flush_after_unload(self, py_files):
        """BUG-07.03: Files that call unload_all_models should also
        call torch.cuda.empty_cache() to actually free VRAM.

        Dereferencing a model does not release VRAM. empty_cache() is
        required.
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if "unload_all_models" in content:
                if "empty_cache" not in content:
                    issues.append(os.path.basename(fpath))

        assert not issues, (
            f"BUG-07.03: unload_all_models without empty_cache: "
            f"{', '.join(issues)}"
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 09 — SUBPROCESS & NETWORK
# BUG-09.02: FFmpeg subprocess pipe deadlock prevention
# ─────────────────────────────────────────────────────────────────

class TestPhase09Subprocess:
    """Verify subprocess safety patterns."""

    def test_popen_has_cleanup(self, py_files):
        """BUG-09.02: Every subprocess.Popen must have cleanup logic.

        Popen without try/finally or context manager can leave zombie
        processes on error. FFmpeg pipe deadlock is the classic case.
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if "subprocess.Popen" not in content:
                continue

            # Check for cleanup patterns
            has_cleanup = (
                "finally:" in content or
                "proc.kill" in content or
                "proc.terminate" in content or
                "with subprocess" in content or  # context manager
                ".wait(" in content
            )

            if not has_cleanup:
                issues.append(os.path.basename(fpath))

        assert not issues, (
            f"BUG-09.02: Popen without cleanup in: "
            f"{', '.join(issues)}. Add try/finally with proc.kill()."
        )

    def test_no_communicate_for_video(self, py_files):
        """BUG-09.02 adjacent: proc.communicate() buffers everything
        in memory. For video streams, use proc.stdin.write() + wait().
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if "subprocess.Popen" not in content:
                continue

            # If file deals with video/ffmpeg AND uses communicate()
            if ("ffmpeg" in content.lower() or "rawvideo" in content):
                if ".communicate(" in content:
                    issues.append(os.path.basename(fpath))

        assert not issues, (
            f"BUG-09.02: communicate() used with ffmpeg in: "
            f"{', '.join(issues)}. Use stdin.write() + wait() instead."
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 12 — REGRESSION, GIT, HANDOFF
# BUG-12.06: Workflow JSON duplicate node IDs
# BUG-12.07: Workflow link cross-reference integrity
# BUG-12.05: Multi-layer parameter sync (runtime-only; see exclusion note)
# ─────────────────────────────────────────────────────────────────

class TestPhase12Regression:
    """Verify repo hygiene and workflow integrity."""

    def test_all_py_files_parse(self, py_files):
        """BUG-12.02 step 5: Every .py file must parse without
        SyntaxError.
        """
        broken = []
        for fpath in py_files:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    ast.parse(f.read(), filename=fpath)
            except SyntaxError as e:
                broken.append(
                    f"{os.path.basename(fpath)}:L{e.lineno}: {e.msg}"
                )

        assert not broken, (
            f"SyntaxError in:\n  " + "\n  ".join(broken)
        )

    def test_workflow_json_link_integrity(self, workflow_jsons):
        """BUG-12.07: Workflow JSON link cross-references must agree.

        Links must exist in: links[] array, source outputs[].links,
        and target inputs[].link. Any mismatch silently drops wires.
        """
        if not workflow_jsons:
            pytest.skip("No workflow JSONs found")

        for wf_path in workflow_jsons:
            with open(wf_path, "r", encoding="utf-8") as f:
                wf = json.load(f)

            if "links" not in wf:
                continue

            # Check last_node_id >= max node id (BUG-12.06)
            if "nodes" in wf and "last_node_id" in wf:
                max_id = max(
                    (n.get("id", 0) for n in wf["nodes"]),
                    default=0
                )
                assert wf["last_node_id"] >= max_id, (
                    f"BUG-12.06: last_node_id ({wf['last_node_id']}) < "
                    f"max node ID ({max_id}) in "
                    f"{os.path.basename(wf_path)}"
                )

            # Check last_link_id >= max link id
            if "last_link_id" in wf:
                max_link = max(
                    (link[0] for link in wf["links"]),
                    default=0
                )
                assert wf["last_link_id"] >= max_link, (
                    f"BUG-12.07: last_link_id ({wf['last_link_id']}) < "
                    f"max link ID ({max_link}) in "
                    f"{os.path.basename(wf_path)}"
                )

    def test_workflow_json_three_way_link_integrity(self, workflow_jsons):
        """BUG-12.07: every link must agree in all three places --
        the links[] row, the source node outputs[slot].links list,
        and the target node inputs[slot].link value. A mismatch
        silently drops the wire on load.
        """
        if not workflow_jsons:
            pytest.skip("No workflow JSONs found")

        for wf_path in workflow_jsons:
            with open(wf_path, "r", encoding="utf-8") as f:
                wf = json.load(f)
            if "links" not in wf or "nodes" not in wf:
                continue
            nodes = {n.get("id"): n for n in wf["nodes"]}
            problems = []
            for row in wf["links"]:
                if not isinstance(row, (list, tuple)) or len(row) < 6:
                    continue
                link_id, src_id, src_slot = row[0], row[1], row[2]
                dst_id, dst_slot = row[3], row[4]
                src = nodes.get(src_id)
                dst = nodes.get(dst_id)
                if src is None or dst is None:
                    problems.append(
                        "link %s: missing node %s" % (
                            link_id, src_id if src is None else dst_id))
                    continue
                outs = src.get("outputs") or []
                if (not isinstance(src_slot, int)
                        or not (0 <= src_slot < len(outs))
                        or link_id not in (outs[src_slot].get("links") or [])):
                    problems.append(
                        "link %s: absent from source %s outputs[%s].links"
                        % (link_id, src_id, src_slot))
                ins = dst.get("inputs") or []
                if (not isinstance(dst_slot, int)
                        or not (0 <= dst_slot < len(ins))
                        or ins[dst_slot].get("link") != link_id):
                    problems.append(
                        "link %s: target %s inputs[%s].link mismatch"
                        % (link_id, dst_id, dst_slot))
            assert not problems, (
                "BUG-12.07: link cross-reference breaks in %s:\n  %s"
                % (os.path.basename(wf_path), "\n  ".join(problems)))

    def test_no_stale_v2_imports(self, py_files, pack_dir):
        """Custom check: No leftover .v2. import paths after
        flattening a directory structure.
        """
        stale = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Look for imports referencing a v2/ subdirectory
            if re.search(r'from\s+\.v2\.', content):
                stale.append(os.path.basename(fpath))

        assert not stale, (
            f"Stale .v2. imports found in: {', '.join(stale)}. "
            f"Update to flat .nodes. imports."
        )


# ─────────────────────────────────────────────────────────────────
# PHASE 11 — LLM-SPECIFIC
# BUG-12.33: Oversized prompt pre-fill guard
# ─────────────────────────────────────────────────────────────────

class TestPhase11LLM:
    """Verify LLM safety patterns."""

    def test_verbatim_grounding_normalizes_whitespace(self, py_files):
        """BUG-11.26: A verbatim-grounding gate (a post-validator that
        substring-tests LLM-emitted terms against a source corpus, e.g.
        the original_radio "anchor A2" key_term gate) must whitespace-
        normalize BOTH sides of the test, or a phrase that wraps across
        a line break in the corpus can never match and the bounded
        retry ladder exhausts on output that was copied correctly.

        Static tripwire: any file that builds a "not grounded in the
        concept" rejection must also carry a whitespace-collapse
        normalizer (a str.join over str.split) somewhere in the file.
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if "not grounded in the concept" not in content:
                continue
            has_normalizer = ".join(" in content and ".split())" in content
            if not has_normalizer:
                issues.append(os.path.basename(fpath))
        assert not issues, (
            "BUG-11.26: verbatim-grounding gate without whitespace "
            "normalization in: " + ", ".join(issues)
        )

    def test_generate_calls_have_length_guard(self, py_files):
        """BUG-12.33: Files that call model.generate() should have
        prompt length checking/truncation nearby.

        Without it, oversized prompts cause silent VRAM spikes and
        60-180s stalls before the first token.
        """
        issues = []
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if ".generate(" not in content:
                continue

            # Check for any form of length guard
            has_guard = (
                "max_input_tokens" in content or
                "context_cap" in content or
                "truncat" in content or
                "max_length" in content or
                "max_new_tokens" in content or
                "input_ids.shape" in content
            )

            if not has_guard:
                issues.append(os.path.basename(fpath))

        # This is a warning, not a hard fail, since not all generate()
        # calls are LLM text generation
        if issues:
            pytest.xfail(
                f"BUG-12.33: .generate() without visible length guard "
                f"in: {', '.join(issues)}. Verify manually."
            )

    def test_title_extraction_and_dialogue_false_positives(self, py_files):
        """BUG-04.06, BUG-11.08, BUG-11.09: Title extraction must handle
        multiple formats; TITLE must be blacklisted from dialogue parser.

        BUG-04.06: Widget defaults override LLM output; multi-tier resolution.
        BUG-11.08: TITLE false-positive as speaking character.
        BUG-11.09: Bare NAME: format parsing gaps.
        """
        # BUG-11.08, BUG-11.09, BUG-11.10, BUG-11.11 require integration
        # testing. Here we check for evidence of the fixes.
        has_title_extraction = False
        has_false_positives = False

        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if "_extract_title" in content:
                has_title_extraction = True
            if "DIALOGUE_FALSE_POSITIVES" in content and "TITLE" in content:
                has_false_positives = True

        # These are design-level checks; runtime verification requires
        # full episode generation with assertion on output format
        if not (has_title_extraction and has_false_positives):
            pytest.xfail(
                "BUG-04.06/11.08: Title extraction and/or "
                "DIALOGUE_FALSE_POSITIVES handling incomplete. "
                "Requires integration test with full script generation."
            )


# ─────────────────────────────────────────────────────────────────
# THREE-FILE CONTRACT ENFORCEMENT
# ─────────────────────────────────────────────────────────────────

class TestThreeFileContract:
    """BUG-12.35: Bible, README, and test file must stay in sync."""

    # Static-only Bible entries (no integration test): BUG-07.16
    # (vram sysmem-spill / partial-load EXTRA_RESERVED_VRAM reserve),
    # BUG-12.47 (launcher env-hook orphan -> consume-once; harness
    # lifecycle; same BUG-LOCAL-415 incident as BUG-12.52, whose
    # consume-once assert IS statically tested in the phase-07-to-12
    # production regression catalog below).
    #
    # BUG-11.61 (an upstream plan names the entities, a downstream
    # assigner renames them, and a per-record prompt is handed both) has
    # no executable assertion YET, deliberately. Its verify clause is an
    # ARCHIVE SWEEP over produced record sets plus a known-bad artifact
    # pinned by row, and neither is reachable by static file analysis --
    # the header's maintenance rule scopes the test requirement to
    # exactly that. The one statically-checkable half is verify step (6),
    # asserting the per-record prompt builder receives RECONCILED
    # upstream text; that guard cannot be asserted until the
    # reconciliation exists, so it lands with the fix rather than with
    # the entry. Add it there -- an entry whose static half stays
    # unwritten is how a rule becomes decoration.

    def _repo_root(self):
        """Resolve the survival guide repo root (parent of tests/)."""
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _count_bible_entries(self):
        """Count entries in BUG_BIBLE.yaml by scanning '- id:' lines."""
        bible_path = os.path.join(self._repo_root(), "BUG_BIBLE.yaml")
        if not os.path.isfile(bible_path):
            return -1
        count = 0
        with open(bible_path, "r", encoding="utf-8") as f:
            for line in f:
                if re.match(r'^- id:\s', line):
                    count += 1
        return count

    def _extract_readme_count(self):
        """Extract the entry count cited in README.md."""
        readme_path = os.path.join(self._repo_root(), "README.md")
        if not os.path.isfile(readme_path):
            return -1
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Match patterns like "68 entries" or "68-entry"
        match = re.search(r'(\d+)[- ]entr(?:y|ies)', content)
        if match:
            return int(match.group(1))
        return -1

    def _collect_test_coverage(self):
        """Collect BUG IDs covered by tests or exclusion comments."""
        test_path = os.path.abspath(__file__)
        covered = set()
        with open(test_path, "r", encoding="utf-8") as f:
            for line in f:
                # Match test docstrings like "BUG-12.02" and exclusion
                # comments like "# BUG-12.34"
                for m in re.finditer(r'BUG-(\d+\.\d+)', line):
                    covered.add(m.group(1))
        return covered

    def _collect_bible_ids(self):
        """Collect all bug IDs from BUG_BIBLE.yaml."""
        bible_path = os.path.join(self._repo_root(), "BUG_BIBLE.yaml")
        ids = set()
        if not os.path.isfile(bible_path):
            return ids
        with open(bible_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.match(r'^- id:\s+"?(\d+\.\d+)"?', line)
                if match:
                    ids.add(match.group(1))
        return ids

    def test_entry_count_matches_readme(self):
        """BUG-12.35: YAML entry count must match README count."""
        bible_count = self._count_bible_entries()
        readme_count = self._extract_readme_count()
        assert bible_count > 0, "Could not count Bible entries"
        assert readme_count > 0, "Could not find entry count in README"
        assert bible_count == readme_count, (
            f"Three-File Contract violated: BUG_BIBLE.yaml has "
            f"{bible_count} entries but README.md cites {readme_count}"
        )

    def test_all_bible_ids_covered_in_tests(self):
        """BUG-12.35: Every Bible ID must have a test or exclusion note."""
        bible_ids = self._collect_bible_ids()
        test_coverage = self._collect_test_coverage()
        uncovered = bible_ids - test_coverage
        if uncovered:
            pytest.xfail(
                f"BUG-12.35: {len(uncovered)} Bible entries have no "
                f"test or exclusion comment: {sorted(uncovered)}"
            )


# ─────────────────────────────────────────────────────────────────
# SUMMARY REPORT
# ─────────────────────────────────────────────────────────────────

class TestPhase05CompletionCheck:
    """BUG-05.06: Automation scripts must not default completion to True."""

    def test_no_false_success_defaults(self, py_files):
        """BUG-05.06: No .get("completed", True) — defaulting to True
        causes automation scripts to declare success without checking
        actual output artifacts.

        This catches the pattern: status.get("completed", True) or
        data.get("completed", True) where a missing key is treated
        as success instead of failure.
        """
        violations = []
        pattern = re.compile(
            r'\.get\(\s*["\']completed["\']\s*,\s*True\s*\)'
        )
        for fpath in py_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if pattern.search(line):
                        violations.append(
                            f"{os.path.basename(fpath)}:{lineno}: {line.strip()}"
                        )
        assert not violations, (
            "BUG-05.06: Found .get('completed', True) — defaulting to True "
            "causes false success. Use .get('completed', False) instead.\n"
            + "\n".join(violations)
        )


class TestSummary:
    """Final summary assertions."""

    def test_pack_has_init(self, pack_dir):
        """Basic: Pack must have __init__.py.

        Skipped when ``--pack-dir`` points at the survival-guide repo
        itself: the repo is a knowledge-base / test harness, not a
        custom-node pack, so it has no top-level ``__init__.py``.
        Detection: the survival-guide repo contains a
        ``BUG_BIBLE.yaml`` at its root.
        """
        if os.path.isfile(os.path.join(pack_dir, "BUG_BIBLE.yaml")):
            pytest.skip(
                "pack-dir is the survival-guide repo (not a custom-node "
                "pack); no top-level __init__.py is expected here. "
                "Re-run against an actual custom-node directory."
            )
        assert os.path.isfile(os.path.join(pack_dir, "__init__.py")), (
            "No __init__.py in pack root"
        )

    def test_pack_has_requirements(self, pack_dir):
        """Basic: Pack should have requirements.txt or pyproject.toml."""
        has_req = (
            os.path.isfile(os.path.join(pack_dir, "requirements.txt")) or
            os.path.isfile(os.path.join(pack_dir, "pyproject.toml"))
        )
        if not has_req:
            pytest.xfail("No requirements.txt or pyproject.toml found")


# ─────────────────────────────────────────────────────────────────
class TestPhase02UtfLauncherGuard:
    """OTR-local static guard for the launcher-grep half of BUG-02.15.

    Any .cmd launcher under scripts/ that boots ComfyUI (references
    main.py) must force UTF-8 stdio, or a detached cmd inherits the
    cp1252 console codec and the boot dies on the first emoji print
    (exit 1, "SERVER DID NOT COME UP"). The boot half stays in the
    exclusion notes below.
    """

    def test_boot_launchers_force_utf8(self, pack_dir):
        scripts_dir = os.path.join(pack_dir, "scripts")
        if not os.path.isdir(scripts_dir):
            pytest.skip("BUG-02.15 guard: no scripts/ dir in this pack")
        launchers = []
        for fn in sorted(os.listdir(scripts_dir)):
            if not fn.lower().endswith(".cmd"):
                continue
            fpath = os.path.join(scripts_dir, fn)
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if "main.py" in content:
                launchers.append((fn, content))
        if not launchers:
            pytest.skip("BUG-02.15 guard: no ComfyUI boot launchers found")
        missing = []
        for fn, content in launchers:
            if "PYTHONUTF8=1" not in content:
                missing.append(fn + ": PYTHONUTF8=1")
            if "PYTHONIOENCODING=utf-8" not in content:
                missing.append(fn + ": PYTHONIOENCODING=utf-8")
        assert not missing, (
            "BUG-02.15: boot launcher(s) missing forced UTF-8 stdio "
            "(a detached cmd inherits cp1252 and dies on the first "
            "emoji print): " + ", ".join(missing))


# NOTES ON NON-TESTABLE BUG BIBLE ENTRIES
# ─────────────────────────────────────────────────────────────────
# BUG-01.04 (Electron wrapper process name): Runtime discovery issue, not a
#   code-level check. ComfyUI Desktop runs as ComfyUI.exe (Electron), not
#   python.exe. Killing python.exe hangs on CUDA handles. Must discover the
#   actual process name dynamically before writing restart logic. Not testable
#   via static analysis — requires runtime process inspection.
#
# BUG-12.34 (git push from sandbox): Workflow/process bug, not a code-level
#   issue. Verifies that AI assistants should execute git push from the user's
#   PowerShell instead of from sandboxed Bash (avoids lock timeouts). This is
#   a best-practice note for AI workflow, not a checkable property of the
#   custom node pack itself. Documented in BUG_BIBLE.yaml for reference.
#
# ─── OTR PROD_BUG_LOG fan-out (2026-07-11), 23 entries ────────────────────
# All 23 entries below originate from live/prod runs of one specific
# downstream project (ComfyUI-OldTimeRadio) and reference internal module
# functions, live soak/smoke telemetry, or LLM-output runtime behavior that
# cannot be checked by static analysis against an arbitrary --pack-dir.
# Each is documented in BUG_BIBLE.yaml with symptom/cause/fix/verify
# generalized for any custom-node author; none is faked into a no-op assert.
#
# BUG-02.15 (cp1252 headless boot crash): The launcher-grep half is now
#   statically guarded by TestPhase02UtfLauncherGuard above; the boot half
#   still requires a real detached-process boot with an inherited console
#   codec and stays runtime-only.
# BUG-07.17 (LTX-AV VRAM soak, disproven offload): Requires a live VRAM soak
#   measurement; the "verify" is a soak re-run, not a static property.
# BUG-11.27 (remote model KeyError, exact-match dict lookup): The verify
#   step requires invoking the live registry lookup with a non-curated
#   model handle; runtime behavior, not a static pattern generic to any pack.
# BUG-07.18 (visualizer soak 4-bug cluster): Requires a live visualizer
#   soak forcing 0-frame/silent/idle-scope beats; runtime integration test.
# BUG-08.07 (bars overlay read silent source): Requires a live render and
#   an amplitude-correlation check against the rendered artifact.
# BUG-05.10 (UnboundLocalError from shadowed import): Requires exercising
#   the specific heavy node's meta-stamp code path at runtime; the static
#   half (grep for shadowing local imports) is pack-specific enough that a
#   generic pattern would over- or under-match arbitrary custom-node code.
# BUG-07.19 (announcer role-coercion naming trap): Requires a live episode
#   render with the announcer keyed as an ordinary cast id; runtime check.
# BUG-07.20 (stage-direction-only line crash): Requires forcing a
#   degenerate dialogue row through the live TTS pipeline.
# BUG-09.05 (cloud API 422 duration floor): Requires a live cloud API call
#   at a sub-minimum duration; network-dependent, not static.
# BUG-09.06 (cloud node dict-vs-string contract): Requires a live call to
#   the specific cloud node; the dict-shape contract is per-node/per-vendor
#   and not inferable from a generic pack scan.
# BUG-07.21 (voice-id asset collision): Requires resolving N voice ids
#   live under allow_voice_reuse=False and hashing the resulting WAVs.
# BUG-11.28 (silent n_ctx downgrade truncation): Requires a live loader
#   call above a quant's actual capacity; runtime VRAM/context behavior.
# BUG-11.29 (jinja consecutive-user-message TemplateError): Requires
#   constructing a live reroll and feeding it through the actual chat
#   template; template object is project-specific.
# BUG-11.30 (token-budget truncation-then-salvage): Requires a live
#   near-ceiling structured call; token-budget behavior is model-specific.
# BUG-11.31 (word-band proportional-band-too-narrow): The underlying
#   `_word_band`-style function is project-internal; without its module
#   path in this repo, a generic unit test would be testing a
#   reimplementation, not the real code. Flagged for a project-local test
#   once the function's path is confirmed.
# BUG-11.32 (announcer silent mutation, ROOT CAUSE OPEN): Explicitly
#   non-testable per its own verify field — the root mutator is
#   unidentified; the obligation is a runtime trace, not a static check.
# BUG-11.33 (fictional character leak into real-news read): Requires a
#   live fixture through the read-pass gate.
# BUG-11.34 (CODA terminal punctuation false-kill): Requires a live
#   fixture through the pre-lex normalization and parser.
# BUG-11.35 (source-span mismatch validator halt): Requires a live
#   offset-span fixture through the repair ladder.
# BUG-11.36 (evidence-ID zero-padding drift): Requires a live fixture
#   returning unpadded IDs through the repair contract.
# BUG-11.37 (span-integrity offset repair): Requires a live offset-shifted
#   exact-quote fixture through the metadata-only repair module.
# BUG-11.38's cross-lane legacy Markdown/score-shape portion still requires
#   captured live prompts per lane. Its compact P4 literal/item-type and P1
#   bounded-authoring extensions have executable OTR coverage below.
# BUG-12.48 (refine-loop save race vs freeze cascade): Requires running
#   the refine loop repeatedly under load; a concurrency/timing property,
#   not a static one.
# BUG-12.49 (provenance-field ownership in shared orchestration): Requires
#   the live writer tail; producer-boundary ownership is runtime wiring,
#   not a static single-file property.
# BUG-12.50 (harness receipt lifecycle): Requires a live soak/smoke harness
#   run; receipt stamping order is runtime behavior.
# BUG-12.05 (multi-layer parameter sync): Requires live workflow reload
#   round-trips across UI/JSON/backend layers; no static property to
#   assert from a pack directory.
# BUG-10.05 (cast pool composition check): Correct pool classification
#   requires the live voice registry; the named cast_pool_check.py is a
#   pack-shipped CI artifact exercised by the pack's own suite when present.
# BUG-10.07 (probability distribution check): The named probability_check.py
#   runs 10,000 live trials; a statistical runtime property, not static.


class TestPhase11BoundedRepairContracts:
    """OTR-local executable guard for BUG-11.39, BUG-11.40, BUG-11.41,
    BUG-11.42, BUG-11.43, BUG-11.44, BUG-11.45.

    The portable Bible rules apply to any typed creative pipeline. This check
    activates only when the known OTR lane is present, where it verifies the
    concrete code + prompt-pack + pipeline wiring needed for the project-local
    regression tests to exercise those rules.
    """

    def test_otr_localized_repairs_are_typed_wired_and_covered(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_original_codex56sol.py")
        if not os.path.isfile(lane_path):
            pytest.skip("BUG-11.39..11.44 guard is OTR-local")

        with open(lane_path, "r", encoding="utf-8") as f:
            lane_source = f.read()
        lane_tree = ast.parse(lane_source)
        class_names = {
            node.name for node in ast.walk(lane_tree)
            if isinstance(node, ast.ClassDef)
        }
        function_names = {
            node.name for node in ast.walk(lane_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {"ScoreIntentPatch", "ScriptLinePatch"} <= class_names, (
            "BUG-11.42: OTR must keep typed score and script patch schemas"
        )
        assert "_call_grounded_script" in function_names, (
            "BUG-11.44: complete-script reauthoring must use one guarded boundary"
        )

        guarded_passes = set()
        for node in ast.walk(lane_tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "_call_grounded_script":
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "pass_id"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    guarded_passes.add(keyword.value.value)
        assert {"P6", "P8", "P8_optional", "P9_retake"} <= guarded_passes, (
            "BUG-11.44: every OTR complete-script reauthoring route must cross "
            "the guarded boundary"
        )

        prompt_path = os.path.join(
            pack_dir, "nodes", "story_packs", "original_codex56sol",
            "original_codex56sol_v1.json",
        )
        pipeline_path = os.path.join(pack_dir, "nodes", "story_packs", "pipelines.json")
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_pack = json.load(f)
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipelines = json.load(f)
        stages = prompt_pack["prompt_stages"]
        assert "Return ScoreIntentPatch JSON only" in stages["codex56_score_anchor_patch"]
        assert "targets is authoritative" in stages["codex56_score_anchor_patch"]
        assert "no other beat IDs" in stages["codex56_score_anchor_patch"]
        assert "Return ScriptLinePatch JSON only" in stages["codex56_script_anchor_patch"]
        assert "targets is authoritative" in stages["codex56_script_anchor_patch"]
        assert "no other line IDs" in stages["codex56_script_anchor_patch"]

        pipeline = next(
            row for row in pipelines["pipelines"]
            if row["story_pipeline_id"] == "acoustic_puzzle_v1"
        )
        seams_by_pass = {
            row["pass_id"]: set(row["seam_refs"])
            for row in pipeline["passes"]
        }
        assert "codex56_score_anchor_patch" in seams_by_pass["P5_broadcast_score"]
        for pass_id in ("P6_performance_script", "P8_broadcast_retake", "P9_retake"):
            assert "codex56_script_anchor_patch" in seams_by_pass[pass_id], (
                f"BUG-11.44: {pass_id} must declare its shared script patch seam"
            )

        runner_tests = os.path.join(
            pack_dir, "tests", "test_original_codex56sol_runner.py",
        )
        with open(runner_tests, "r", encoding="utf-8") as f:
            runner_test_source = f.read()
        for test_name in (
            "test_p5_missing_grounding_anchor_uses_small_intent_patch",
            "test_p5_intent_patch_preserves_anchor_already_valid_on_target",
            "test_p6_missing_grounding_anchor_uses_small_line_patch",
            "test_p8_retake_missing_anchor_uses_the_same_small_line_patch",
            "test_p6_line_patch_preserves_anchor_already_valid_on_target",
            "test_p3_repair_keeps_authoritative_top_level_and_removes_nested_extras",
            "test_p3_repair_lifts_missing_top_level_collection_verbatim",
            "test_p3_repair_fails_closed_on_unknown_or_graph_invalid_shapes",
            "test_p5_repair_keeps_authoritative_top_level_and_removes_nested_extras",
        ):
            assert f"def {test_name}(" in runner_test_source, (
                f"BUG-11.39..11.45: missing OTR behavior regression {test_name}"
            )

    def test_otr_compact_repairs_repeat_exact_small_artifact_contracts(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        test_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")
        if not os.path.isfile(lane_path) or not os.path.isfile(test_path):
            pytest.skip("BUG-11.38 compact P4 guard is OTR-local")

        with open(lane_path, "r", encoding="utf-8") as f:
            lane_source = f.read()
        with open(test_path, "r", encoding="utf-8") as f:
            test_source = f.read()

        assert "_STRUCTURE_REVIEW_CONTRACT_INSTRUCTION" in lane_source
        assert 'elif pass_id == "P4" and result_type is StructureReviewV4' in lane_source
        assert "never return fail" in lane_source
        assert "never objects" in lane_source
        assert (
            "test_p4_typed_repair_keeps_exact_review_shape_and_only_compact_failed_review"
            in test_source
        )
        assert 'elif pass_id == "P1" and result_type is DramaticQuestionV4' in lane_source
        assert "ending_direction at or below 90 characters" in lane_source
        assert "never copy it unchanged" in lane_source
        assert (
            "test_p1_typed_repair_uses_compact_exact_contract_and_safe_rewrite_margin"
            in test_source
        )
        assert "_radio_score_draft_topology_instruction" in lane_source
        assert "flattened total across every scenes[*].beats array" in lane_source
        assert "Each individual scene may contain at most" in lane_source
        assert "test_p3_base_and_repair_bind_locked_total_to_per_scene_cap" in test_source
        assert "safe ceilings: title <=48; premise <=108; setting <=60" in lane_source
        assert "env <=42; description <=54" in lane_source
        assert "description <=54 and visual_prompt <=90" in lane_source
        assert "intent <=48; arc_phase <=21" in lane_source
        assert "description <=60; generation_prompt <=90" in lane_source
        assert "preserve every other previous_draft prose leaf byte for byte" in lane_source
        assert "test_p3_compact_contract_names_nested_literal_values_on_base_and_repair" in test_source
        assert "test_p3_rewrite_rejects_structural_mutation_then_repairs_the_draft" in test_source

    def test_otr_spoken_hygiene_allows_only_source_grounded_acronyms(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        test_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")
        if not os.path.isfile(lane_path) or not os.path.isfile(test_path):
            pytest.skip("BUG-11.51 source-grounded acronym guard is OTR-local")

        with open(lane_path, "r", encoding="utf-8") as f:
            lane_source = f.read()
        with open(test_path, "r", encoding="utf-8") as f:
            test_source = f.read()

        assert "def _source_grounded_all_caps" in lane_source
        assert "_allowed_spoken_all_caps(p0, p2)" in lane_source
        assert "allowed_all_caps" in lane_source
        assert (
            "test_spoken_validator_allows_only_acronyms_grounded_in_accepted_fact_index"
            in test_source
        )

    def test_otr_cast_names_use_bounded_acronym_aware_grammar(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        test_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")
        if not os.path.isfile(lane_path) or not os.path.isfile(test_path):
            pytest.skip("BUG-11.52 acronym-aware cast-name guard is OTR-local")

        with open(lane_path, "r", encoding="utf-8") as f:
            lane_source = f.read()
        with open(test_path, "r", encoding="utf-8") as f:
            test_source = f.read()

        assert "_CAST_NAME_ACRONYM_RE = re.compile(r\"(?<![A-Za-z0-9])[A-Z]{2,3}(?![A-Za-z0-9])\")" in lane_source
        assert "acronym_count <= 1" in lane_source
        assert "One short 2-3 letter acronym token is allowed" in lane_source
        assert "digits and all-uppercase full labels are forbidden" in lane_source
        assert (
            "test_p2_repair_accepts_short_acronym_inside_title_case_character_name"
            in test_source
        )

    def test_otr_role_acronyms_flow_through_every_script_validation_boundary(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        test_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")
        if not os.path.isfile(lane_path) or not os.path.isfile(test_path):
            pytest.skip("BUG-11.53 role acronym guard is OTR-local")
        lane_source = open(lane_path, encoding="utf-8").read()
        test_source = open(test_path, encoding="utf-8").read()
        assert "def _allowed_spoken_all_caps" in lane_source
        assert "_allowed_spoken_all_caps(fact_index, cast)" in lane_source
        assert "_allowed_spoken_all_caps(p0, p2)" in lane_source
        assert "test_allowed_spoken_acronyms_include_only_bounded_short_cast_role_tokens" in test_source


class TestPhase07To12ProductionRegressionCatalog:
    """OTR-local guard for live-only BUG-07.22, BUG-07.23, BUG-08.08,
    BUG-11.46, BUG-11.47, BUG-11.48, BUG-11.49, BUG-11.50, BUG-12.51,
    BUG-12.52, BUG-12.54, BUG-12.55, BUG-12.56, BUG-12.57, BUG-12.58,
    BUG-12.59, BUG-12.60, BUG-12.61, BUG-12.62, BUG-12.63, BUG-12.64,
    BUG-12.65, BUG-12.66, BUG-12.67, BUG-12.68, BUG-12.69, BUG-12.70, BUG-12.71,
    BUG-05.11.

    These rules were admitted from dated smokes, published artifacts, or GPU
    runs. The project tests named below exercise their concrete behavior; this
    catalog guard makes loss of that coverage a Bible regression as well.
    """

    EXPECTED_TESTS = {
        "tests/test_production_ledger.py": (
            "test_update_line_text_clears_skip_state_on_recomposed_text",
            "test_update_line_text_preserves_skip_state_for_empty_text",
            "test_save_merges_schema_l3_fields_from_disk",
        ),
        "tests/test_source_payload_chunk3.py": (
            "test_resolve_inputs_uses_selected_link_not_differing_request",
        ),
        "tests/test_video_render_driver_perbeat_audio.py": (
            "test_episode_assembler_stamps_full_master_byte_identity",
            "test_master_audio_identity_rejects_non_sha_receipt",
        ),
        "tests/test_video_render_driver_additive.py": (
            "test_build_clip_manifest_positioned_timeline_uses_ledger_boundary",
        ),
        "tests/test_meta_paths.py": (
            "test_published_obs_filename_replaces_planned_alias",
            "test_invalid_published_obs_path_cannot_redirect_owner",
            "test_save_ledger_safe_synchronizes_terminal_obs_surfaces",
        ),
        "tests/test_video_render_path_cw4.py": (
            "test_master_audio_mux_terminal_stamp_owns_all_final_paths",
            "test_positioned_crossfades_partition_visible_timeline_without_duplication",
            "test_positioned_assemble_reconciles_oversized_manifest_down_to_master",
        ),
        "tests/test_video_ledger.py": (
            "test_post_audio_overlay_rehydrates_owned_sections_despite_existing_timing",
            "test_post_audio_overlay_rejects_cross_episode_freeze",
            "test_post_audio_hash_survives_image_dispatcher_wire_serialization",
        ),
        "tests/test_radio_editor_live_budget_lineage.py": (
            "test_requested_budget_counts_character_body_not_announcer_overhead",
            "test_announcer_still_owns_the_spoken_breath_cap",
            "test_validator_accepts_good_actual_despite_false_model_projection",
            "test_validator_rejects_bad_actual_despite_good_model_projection",
            "test_micro_repair_can_fix_a_row_during_advisory_episode_drift",
            "test_malformed_present_budget_skips_without_mutating_or_calling_llm",
            "test_split_child_keeps_parent_beat_and_syncs_retained_beat_membership",
            "test_repeated_split_pass_never_reuses_an_existing_child_line_id",
            "test_outline_initialization_materializes_the_durable_beat_collection",
            "test_common_integer_delivery_law_covers_180_and_320_words",
            "test_inline_fit_survives_failed_pair_then_repairs_one_row_only",
            "test_inline_fit_rejects_no_progress_until_typed_exhaustion",
            "test_word_fit_liveness_allows_more_than_eighteen_strict_progress_cycles",
            "test_inline_campaign_retires_candidates_and_alternates_complete_reroll",
            "test_outer_word_fit_campaign_fails_closed_at_default_ceiling",
            "test_outer_word_fit_campaign_respects_environment_ceiling",
            "test_outer_word_fit_campaign_can_accept_before_ceiling",
        ),
        "tests/test_news_coda_delivery_surface.py": (
            "test_live_b009_first_pass_keeps_exact_clean_sentence_and_never_rewrites_fact",
            "test_sentence_prefix_parser_never_splits_initials_or_versions",
            "test_finalizer_never_returns_an_unscored_emergency_sentence",
            "test_single_sentence_source_note_defers_intact_fact_to_credits",
            "test_dirty_old_coda_is_repaired_as_combined_surface_with_hash_receipt",
            "test_phase7_expansion_then_combined_coda_scour_is_clean",
            "test_row_local_failure_details_are_returned_for_phase_receipts",
            "test_content_owned_direct_scour_is_byte_identical",
        ),
        "tests/test_story_brief_c5a1.py": (
            "test_generic_role_labels_are_legal_visual_nouns",
            "test_all_six_bank_personal_name_shapes_stay_forbidden",
            "test_role_input_forms_preserve_one_identity_without_mapping_articles",
            "test_private_repair_detail_names_surface_but_public_code_stays_stable",
        ),
        "tests/test_brief_prompt_finishing.py": (
            "test_failed_brief_still_finishes_a_valid_non_authoring_visual_prompt",
        ),
        "tests/test_scifi_source_repair.py": (
            "test_repair_rehomes_exact_quote_only_when_field_label_is_wrong",
            "test_repair_drops_unsupported_fact_but_keeps_literal_fact",
            "test_repair_bounds_an_exact_oversized_quote_without_changing_the_claim",
            "test_repair_refuses_an_oversized_quote_that_is_not_literal_source_text",
            "test_json_parser_does_not_salvage_nested_child_from_broken_outer_object",
            "test_schema_instruction_contains_every_required_path_for_nested_radio_score",
        ),
        "tests/test_scifi_codex_lane.py": (
            "test_draft_compiler_derives_only_mechanical_score_metadata",
            "test_draft_compiler_rejects_unowned_or_invalid_runtime_decisions",
            "test_p3_semantic_repair_uses_minified_draft_and_bounded_receipts",
            "test_p3_compact_contract_names_nested_literal_values_on_base_and_repair",
            "test_p3_text_patch_gate_covers_each_author_owned_leaf",
            "test_p3_local_text_patch_repairs_one_leaf_with_one_bounded_call",
            "test_p3_rewrite_local_text_patch_preserves_locked_structure",
            "test_p3_text_patch_preflight_falls_back_for_hidden_compiler_defect",
            "test_p3_malformed_text_patch_fails_without_a_third_reroll",
            "test_p3_text_patch_contract_rejects_missing_duplicate_unknown_blank_and_overcap_rows",
            "test_p3_text_patch_receipt_distinguishes_model_prose_over_schema_cap",
            "test_p3_text_patch_rejects_a_resolved_artifact_wrapper_without_reroll",
            "test_p3_openrouter_overlength_uses_same_slot_full_repair_with_json_mode",
            "test_p3_scheduler_openrouter_stays_on_full_repair_and_forwards_json_mode",
            "test_p3_two_decode_failures_restart_only_from_trusted_draft_context",
            "test_p3_rewrite_rejects_structural_mutation_then_repairs_the_draft",
            "test_project_compile_round_trip_preserves_the_rewrite_structure",
            "test_radio_score_draft_surface_is_finite_before_p3_reserves_output_capacity",
            "test_max_width_p3_draft_envelopes_fit_the_local_gemma_context",
            "test_radio_score_draft_output_budget_preserves_the_live_p3_repair_window",
            "test_fact_index_contract_bounds_output_surface",
            "test_fact_index_token_budget_keeps_the_live_120_word_window",
            "test_p0_typed_repair_is_compact_and_requires_scalar_tone",
            "test_p0_deterministic_repair_bounds_an_exact_overwide_literal_quote",
            "test_script_output_token_budget_receipts_and_bounds",
            "test_script_artifact_metadata_repair_normalizes_only_graph_metadata",
            "test_script_metadata_repair_short_circuits_the_typed_repair_model_call",
            "test_quality_patch_targets_are_row_local_and_invalid_ids_do_not_widen",
            "test_quality_patch_prompt_is_compact_complete_and_fact_grounded",
            "test_quality_patch_merge_changes_only_target_text_and_validates_whole_script",
            "test_quality_patch_rotates_to_technical_slot_after_malformed_creative",
            "test_quality_patch_capacity_floor_records_both_slots",
            "test_two_failed_quality_slots_stop_without_rejudging_unchanged_script",
            "test_quality_judge_transport_failure_keeps_prior_valid_story",
            "test_character_word_fit_uses_compact_patch_and_fresh_recount",
            "test_character_word_fit_retries_a_failed_pair_then_recovers",
            "test_character_word_fit_exhaustion_fails_before_assembly",
            "test_character_word_fit_rejects_valid_no_progress_patches",
            "test_initial_compact_p5_alternates_complete_candidate_producer",
            "test_complete_script_campaign_retires_candidate_not_episode",
        ),
        "tests/test_fable2_assembly.py": (
            "test_word_band_defect_fails_before_assembly_mutates_ledger",
            "test_final_word_fit_retries_failed_slots_and_reseals_one_row",
            "test_final_word_fit_rejects_no_progress_until_typed_exhaustion",
            "test_word_fit_patch_rejects_fake_commercial_and_new_number",
            "test_fable_capacity_uses_post_merge_rows_and_the_exact_hygiene_cap",
            "test_trailing_mechanical_outro_cannot_hide_or_create_thesis",
        ),
        "tests/test_freeze_policy_readonly.py": (
            "test_declared_word_delivery_passes_readonly_freeze_without_content_mutation",
            "test_declared_word_drift_halts_before_video_readiness",
        ),
        "tests/test_story_brief_c5a2.py": (
            "test_reflections_describe_the_final_word_fitted_rows",
        ),
        "tests/test_generation_budget.py": (
            "test_complete_patch_budget_refuses_clamp_but_default_call_still_clamps",
            "test_writer_local_complete_patch_refuses_before_model_generate",
            "test_model_loader_captures_complete_patch_marker_before_normalization",
            "test_openrouter_complete_patch_refuses_before_network",
            "test_openrouter_complete_patch_refuses_provider_cap_before_network",
            "test_comfy_credits_complete_patch_refuses_before_network",
            "test_comfy_credits_strict_patch_keeps_exact_requested_budget",
        ),
        "tests/test_gguf_backend.py": (
            "test_complete_patch_capacity_refuses_before_llama_call",
            "test_complete_patch_refuses_gguf_provider_cap",
        ),
        "tests/test_google_api_llm_lane.py": (
            "test_complete_patch_capacity_refuses_before_google_request",
        ),
        "tests/test_structured_call_clamp.py": (
            "test_authored_artifact_can_disable_the_overlong_string_clamp",
        ),
        "tests/test_scifi_lane_schema_parity.py": (
            "test_source_grounded_p0_has_a_finite_shared_output_envelope",
            "test_source_grounded_p0_disables_generic_string_clamping",
            "test_sibling_p0_typed_repairs_are_compact_and_require_scalar_tone",
        ),
        "tests/test_fetch_science_news_no_legacy_wrapper.py": (
            "test_scifi_v4_source_floor_requires_length_words_and_token_diversity",
        ),
        "tests/test_fable2_tail_context.py": (
            "test_content_owned_tail_stamps_delivery_before_finalizer",
        ),
        "tests/test_cast_lock.py": (
            "test_content_owned_lane_preserves_its_own_voices_without_replay",
            "test_content_owned_lane_still_fails_on_colliding_bark_voices",
        ),
        "tests/test_ltx_audio_in_engine.py": (
            "test_ltx_audio_in_videovae_is_split_enc_dec",
            "test_ltx_av_vram_reserve_bumps_then_restores",
            "test_ltx_av_vram_reserve_restores_on_exception",
        ),
        "tests/test_post_upscale_procgen_blend.py": (
            "test_build_cmd_3input_scopes_no_double_format_gbrp_bug402",
            "test_blend_cmd_does_NOT_use_shortest_for_c7_safety",
        ),
        "tests/test_canonical_headless_api.py": (
            "test_headless_wrapper_clears_stale_extra_env_hook_before_boot",
        ),
        "tests/test_image_platform_c1.py": (
            "test_roles_requiring_stills_needs_a_complete_resolvable_policy",
            "test_meta_brief_all_visualizers_bypass_prompt_authoring",
            "test_meta_brief_node_bypasses_before_writer_resolution",
            "test_meta_brief_mixed_policy_authors_only_proven_consumer_roles",
            "test_dispatcher_refuses_image_render_without_proven_consumer",
            "test_dispatcher_preserves_proven_role_when_another_slot_is_unresolved",
            "test_dispatcher_rejects_explicit_unknown_object_role",
        ),
        "tests/test_openrouter_backend.py": (
            "test_generate_uses_lowest_catalog_effort_when_reasoning_is_mandatory",
            "test_stale_cache_learns_mandatory_reasoning_from_exact_400",
            "test_non_retryable_status_aborts_immediately",
        ),
        "tests/test_openrouter_catalog_rows.py": (
            "test_slim_model_preserves_reasoning_capability_contract",
        ),
        "tests/test_video_platform_aseam.py": (
            "test_shotlock_all_visualizers_skip_writer_visual_directives",
        ),
    }

    def test_otr_live_production_regressions_remain_covered(self, pack_dir):
        anchor = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        if not os.path.isfile(anchor):
            pytest.skip("BUG-07.22..12.52 catalog is OTR-local")

        for relative_path, test_names in self.EXPECTED_TESTS.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            assert os.path.isfile(path), (
                f"production regression module missing: {relative_path}"
            )
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"production regression missing: {relative_path}::{test_name}"
                )

        headless_path = os.path.join(pack_dir, "scripts", "otr_headless_canonical.ps1")
        with open(headless_path, "r", encoding="utf-8") as f:
            headless_source = f.read()
        assert "$StaleExtraEnv" in headless_source
        assert "Remove-Item -LiteralPath $StaleExtraEnv -Force" in headless_source, (
            "BUG-12.52: canonical headless boot must clear a stale one-shot override"
        )

    def test_otr_positioned_media_timeline_ownership(self, pack_dir):
        """BUG-12.69: positioned output excludes duplicated crossfade work."""
        driver_path = os.path.join(
            pack_dir, "nodes", "_otr_video_engines", "render_driver.py",
        )
        composite_path = os.path.join(
            pack_dir, "nodes", "otr_silent_composite.py",
        )
        if not os.path.isfile(driver_path) or not os.path.isfile(composite_path):
            pytest.skip("BUG-12.69 positioned timeline guard is OTR-local")

        driver_source = open(driver_path, encoding="utf-8").read()
        composite_source = open(composite_path, encoding="utf-8").read()
        for marker in (
            '"timeline_total_frames": timeline_total',
            '"render_target_frames": total',
            'timeline_source = "ledger.total_episode_dur_s"',
            "math.ceil(",
        ):
            assert marker in driver_source, (
                f"BUG-12.69 manifest ownership marker missing: {marker}"
            )
        for marker in (
            "slot_end = min(requested_end, next_start, timeline_end)",
            "manifest_positioned and base_total != target_total",
            '"planned_visible_frame_count": planned_visible',
            '"overlap_trimmed_frame_count"',
        ):
            assert marker in composite_source, (
                f"BUG-12.69 positioned planner marker missing: {marker}"
            )

        tests = {
            "tests/test_video_render_driver_additive.py": (
                "test_build_clip_manifest_positioned_timeline_uses_ledger_boundary",
            ),
            "tests/test_video_render_path_cw4.py": (
                "test_positioned_crossfades_partition_visible_timeline_without_duplication",
                "test_positioned_assemble_reconciles_oversized_manifest_down_to_master",
            ),
        }
        for relative_path, test_names in tests.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            source = open(path, encoding="utf-8").read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"BUG-12.69 executable guard missing: {test_name}"
                )

    def test_otr_explicit_word_delivery_is_owned_before_media(self, pack_dir):
        """BUG-12.70: requested length is hash-bound before media readiness."""
        paths = {
            "shared": os.path.join(pack_dir, "nodes", "_otr_word_delivery.py"),
            "codex": os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py"),
            "fable2": os.path.join(pack_dir, "nodes", "_otr_scifi_fable2.py"),
            "inline": os.path.join(pack_dir, "nodes", "_otr_radio_editor.py"),
            "writer": os.path.join(pack_dir, "nodes", "OTR_LedgerScriptWriter.py"),
            "freeze": os.path.join(pack_dir, "nodes", "_otr_freeze_cascade.py"),
        }
        if not os.path.isfile(paths["shared"]):
            pytest.skip("BUG-12.70 explicit word-delivery guard is OTR-local")
        sources = {
            name: open(path, encoding="utf-8").read()
            for name, path in paths.items()
        }
        expected = {
            "shared": (
                "def delivery_word_bounds(",
                "MAX_CONSECUTIVE_REPAIR_STALLS = 4",
                "class WordFitLivenessController",
                "def retire_word_fit_candidate(",
                "def accept_word_fit_candidate(",
                "bounded_model_output_retries_until_ledger_legal",
                '"actual_text_sha256": character_text_sha256(ledger_data)',
                "if require_in_band and drift:",
            ),
            "codex": (
                "class CodexWordDeliveryError",
                "def _run_complete_script_campaign(",
                "candidate_index=candidate_index",
                'owner="scifi_codex"',
                "accept_word_fit_candidate(",
            ),
            "fable2": (
                "class Fable2WordDeliveryError",
                "canonical_word_count",
                "delivery_candidate_index",
                'owner="scifi_news_pro"',
                "retire_word_fit_candidate(",
                "accept_word_fit_candidate(",
            ),
            "inline": (
                "def fit_final_word_delivery_campaign(",
                "def _author_complete_inline_candidate(",
                "owner=spec.owner",
                "retire_word_fit_candidate(",
                "accept_word_fit_candidate(",
            ),
            "writer": (
                "fit_final_word_delivery_campaign(",
                'stage="writer_final_rows"',
                "run_story_brief_reflection(",
            ),
            "freeze": (
                'stage="freeze_pre_media"',
                'verdict="needs_full_rerun"',
                '"phase_8_video_readiness"',
            ),
        }
        for name, markers in expected.items():
            for marker in markers:
                assert marker in sources[name], (
                    f"BUG-12.70 {name} ownership marker missing: {marker}"
                )


    def test_otr_outer_word_fit_campaign_is_fail_closed(self, pack_dir):
        """BUG-12.71: a non-converging word-fit campaign must stop the queue."""
        shared_path = os.path.join(pack_dir, "nodes", "_otr_word_delivery.py")
        test_path = os.path.join(
            pack_dir, "tests", "test_radio_editor_live_budget_lineage.py",
        )
        if not os.path.isfile(shared_path):
            pytest.skip("BUG-12.71 word-fit ceiling guard is OTR-local")

        shared_source = open(shared_path, encoding="utf-8").read()
        for marker in (
            "DEFAULT_MAX_OUTER_WORD_FIT_CANDIDATES = 12",
            "def _resolve_outer_candidate_ceiling(",
            "class WordFitCeilingExceeded(WordDeliveryError)",
            "OTR_MAX_WORD_FIT_CANDIDATES",
            "bounded_model_output_retries_until_ledger_legal",
            'if int(state["active_candidate_index"]) >= ceiling:',
        ):
            assert marker in shared_source, (
                f"BUG-12.71 fail-closed ceiling marker missing: {marker}"
            )

        test_source = open(test_path, encoding="utf-8").read()
        for test_name in (
            "test_outer_word_fit_campaign_fails_closed_at_default_ceiling",
            "test_outer_word_fit_campaign_respects_environment_ceiling",
            "test_outer_word_fit_campaign_can_accept_before_ceiling",
        ):
            assert f"def {test_name}(" in test_source, (
                f"BUG-12.71 executable guard missing: {test_name}"
            )
    def test_otr_protected_suffix_final_surface_contract(self, pack_dir):
        """BUG-12.60: the assembled delivery surface owns the final gate."""
        test_path = os.path.join(
            pack_dir, "tests", "test_news_coda_delivery_surface.py",
        )
        if not os.path.isfile(test_path):
            pytest.skip("BUG-12.60 assembled-coda guard is OTR-local")
        with open(test_path, "r", encoding="utf-8") as f:
            source = f.read()
        for test_name in (
            "test_live_b009_first_pass_keeps_exact_clean_sentence_and_never_rewrites_fact",
            "test_sentence_prefix_parser_never_splits_initials_or_versions",
            "test_finalizer_never_returns_an_unscored_emergency_sentence",
            "test_single_sentence_source_note_defers_intact_fact_to_credits",
            "test_dirty_old_coda_is_repaired_as_combined_surface_with_hash_receipt",
            "test_phase7_expansion_then_combined_coda_scour_is_clean",
            "test_row_local_failure_details_are_returned_for_phase_receipts",
            "test_content_owned_direct_scour_is_byte_identical",
        ):
            assert f"def {test_name}(" in source, (
                f"BUG-12.60 executable guard missing: {test_name}"
            )

    def test_otr_cast_role_identity_classification_is_covered(self, pack_dir):
        """BUG-12.61: role labels and personal names need distinct projections."""
        modules = {
            "tests/test_story_brief_c5a1.py": (
                "test_generic_role_labels_are_legal_visual_nouns",
                "test_all_six_bank_personal_name_shapes_stay_forbidden",
                "test_role_input_forms_preserve_one_identity_without_mapping_articles",
                "test_private_repair_detail_names_surface_but_public_code_stays_stable",
            ),
            "tests/test_brief_prompt_finishing.py": (
                "test_failed_brief_still_finishes_a_valid_non_authoring_visual_prompt",
            ),
        }
        anchor = os.path.join(pack_dir, "nodes", "_otr_story_brief.py")
        if not os.path.isfile(anchor):
            pytest.skip("BUG-12.61 cast-role identity guard is OTR-local")
        with open(anchor, "r", encoding="utf-8") as f:
            story_brief_source = f.read()
        for symbol in (
            "_is_generic_role_label",
            "_cast_input_substitution_forms",
            "_cast_output_forbidden_forms",
            "_matched_cast_name_token",
        ):
            assert f"def {symbol}(" in story_brief_source, (
                f"BUG-12.61 production classifier missing: {symbol}"
            )
        for relative_path, test_names in modules.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"BUG-12.61 executable guard missing: {test_name}"
                )

    def test_otr_rename_transaction_and_active_consumer_join(self, pack_dir):
        """BUG-12.66: a renamed artifact tree must carry durable identity."""
        ledger_path = os.path.join(pack_dir, "nodes", "production_ledger.py")
        if not os.path.isfile(ledger_path):
            pytest.skip("BUG-12.66 artifact-tree rename guard is OTR-local")

        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger_source = f.read()
        tree = ast.parse(ledger_source)
        function_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {
            "_rebase_episode_local_paths",
            "_same_durable_run",
            "rename_episode",
            "_merge_with_disk",
        } <= function_names
        assert "save_ledger_safe" in ledger_source
        assert "mirrored_from" in ledger_source
        assert "music_cue_spec_sha256" in ledger_source

        modules = {
            "tests/test_production_ledger.py": (
                "test_path_rebase_handles_windows_slashes_and_component_boundaries",
                "test_rename_rebases_shared_six_bank_episode_paths",
                "test_merge_rejects_foreign_or_reauthored_disk_only_music_mirrors",
                "test_durable_identity_rejects_one_sided_freeze",
            ),
            "tests/test_video_ledger.py": (
                "test_shot_lock_identity_rejects_one_sided_freeze",
                "test_post_audio_overlay_rehydrates_owned_sections_despite_existing_timing",
                "test_post_audio_overlay_identity_merges_music_and_assembler_mirrors",
                "test_post_audio_overlay_rejects_cross_episode_freeze",
            ),
            "tests/test_image_platform_c1.py": (
                "test_reresolve_stale_pending_rekeys_to_renamed_episode",
                "test_reresolve_rejects_active_sibling_with_different_freeze",
            ),
            "tests/test_clip_fill.py": (
                "test_resolve_stale_pending_clip_episode_to_renamed_dir",
                "test_resolve_stale_pending_clip_rejects_foreign_freeze",
            ),
            "tests/test_google_video_sfx_workflow.py": (
                "test_master_audio_reresolve_uses_active_ledger_not_newest_sibling",
                "test_master_audio_reresolve_fails_closed_without_active_ledger",
                "test_master_audio_reresolve_rejects_ledger_directory_identity_mismatch",
            ),
            "tests/test_workflow_live_passes_validator.py": (
                "test_production_workflow_visual_structure_pinned",
            ),
        }
        for relative_path, test_names in modules.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            assert os.path.isfile(path), (
                f"BUG-12.66 regression module missing: {relative_path}"
            )
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"BUG-12.66 executable guard missing: "
                    f"{relative_path}::{test_name}"
                )

        workflow_path = os.path.join(pack_dir, "workflows", "otr_canonical.json")
        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)
        links = {int(row[0]): row for row in workflow.get("links", [])}
        assert links.get(284) == [284, 12, 0, 90, 4, "STRING"], (
            "BUG-12.66: canonical workflow must gate ShotLock on rename owner"
        )

    def test_otr_canonical_ledger_text_metric_owner(self, pack_dir):
        """BUG-12.67: every durable text/count surface shares one owner."""
        import runpy

        metrics_path = os.path.join(pack_dir, "nodes", "_otr_text_metrics.py")
        if not os.path.isfile(metrics_path):
            pytest.skip("BUG-12.67 canonical text-metric guard is OTR-local")

        metrics = runpy.run_path(metrics_path)
        count = metrics["canonical_word_count"]
        assert count("forty-two") == 1
        assert count("don't don\u2019t") == 2
        assert count("off\u2014it's") == 2
        assert count("off\u2013it\u2019s") == 2

        required_uses = {
            "nodes/production_ledger.py": "refresh_ledger_text_metrics",
            "nodes/_otr_ledger_freeze.py": "canonical_word_count",
            "nodes/_otr_freeze_cascade.py": "refresh_ledger_text_metrics(led)",
            "nodes/_otr_readiness.py": "set_line_text_metrics",
            "nodes/_otr_ledger_scrub.py": "set_line_text_metrics",
            "nodes/_otr_ledger_reviewer.py": "set_line_text_metrics",
            "nodes/_otr_story_spine.py": "set_line_text_metrics",
            "nodes/_otr_scifi_codex.py": "set_line_text_metrics",
        }
        for relative_path, marker in required_uses.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            assert os.path.isfile(path), (
                f"BUG-12.67 production module missing: {relative_path}"
            )
            source = open(path, encoding="utf-8").read()
            assert marker in source, (
                f"BUG-12.67 owner marker missing from {relative_path}: {marker}"
            )

        tests = {
            "tests/test_production_ledger.py": (
                "test_save_self_heals_all_text_metrics_for_every_bank",
            ),
            "tests/test_lfc_phase_0_10_gap_audit.py": (
                "test_punctuation_glue_count_is_clean_for_every_bank",
            ),
            "tests/test_lfc_phase_7_8_readiness.py": (
                "test_final_metric_refresh_preserves_pre_diagnosis_and_cleans_post",
            ),
            "tests/test_text_metric_ownership.py": (
                "test_production_nodes_do_not_bypass_canonical_text_metric_owner",
            ),
        }
        for relative_path, test_names in tests.items():
            path = os.path.join(pack_dir, *relative_path.split("/"))
            assert os.path.isfile(path), (
                f"BUG-12.67 regression module missing: {relative_path}"
            )
            source = open(path, encoding="utf-8").read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"BUG-12.67 executable guard missing: "
                    f"{relative_path}::{test_name}"
                )

    def test_otr_compiler_owned_p5_text_transport(self, pack_dir):
        """BUG-12.68: bounded P5 transports only model-owned line text."""
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        if not os.path.isfile(lane_path):
            pytest.skip("BUG-12.68 compact P5 transport guard is OTR-local")
        with open(lane_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        classes = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        functions = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {
            "ScriptTextDraftLineV4",
            "ScriptTextDraftV4",
            "_P5TextDraftMessages",
        } <= set(classes)
        assert {
            "compile_script_text_draft",
            "_call_script_text_draft",
            "_run_initial_script_generation",
        } <= set(functions)

        compiler_source = ast.get_source_segment(
            source, functions["compile_script_text_draft"],
        ) or ""
        call_source = ast.get_source_segment(
            source, functions["_call_script_text_draft"],
        ) or ""
        restart_source = ast.get_source_segment(
            source, functions["_run_initial_script_generation"],
        ) or ""
        assert "set(observed_ids) != set(expected)" in compiler_source
        assert "text=text_by_id[line_id]" in compiler_source
        assert "result_type=ScriptTextDraftV4" in call_source
        assert "include_result_json_schema=False" in call_source
        assert "repair_script_hygiene_after_exhaustion" in call_source
        assert '"max_ladders": 2' in restart_source
        assert '"creative"' in restart_source and '"technical"' in restart_source
        assert "for (" in restart_source and "in lanes:" in restart_source
        assert "_otr_require_full_output_budget = True" in source
        assert 'repair_payload["failed_text_draft"]' in source

        pack_path = os.path.join(
            pack_dir, "nodes", "story_packs", "scifi_news", "scifi_news.json",
        )
        pipeline_path = os.path.join(
            pack_dir, "nodes", "story_packs", "pipelines.json",
        )
        with open(pack_path, "r", encoding="utf-8") as f:
            pack = json.load(f)
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipelines = json.load(f)
        prompt = pack["prompt_stages"]["codex_play_system"]
        assert "ScriptTextDraftV4" in prompt
        assert "exactly one key" in prompt
        assert "Python compiles" in prompt
        pipeline = next(
            row for row in pipelines["pipelines"]
            if row["story_pipeline_id"] == "scifi_news_circuit"
        )
        p5 = next(
            row for row in pipeline["passes"]
            if row["pass_id"] == "P5_first_play"
        )
        assert "compact closed {line_id,text}" in p5["description"]
        assert "fresh technical-slot ladder" in p5["description"]

        test_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")
        with open(test_path, "r", encoding="utf-8") as f:
            test_source = f.read()
        for test_name in (
            "test_max_width_p5_text_envelopes_fit_the_live_gemma_12b_context",
            "test_compact_p5_compiler_preserves_text_and_owns_every_mechanical_field",
            "test_compact_p5_compiler_fails_closed_on_non_bijective_line_ids",
            "test_compact_p5_typed_repair_carries_small_authority_not_whole_request",
            "test_compact_p5_malformed_retry_omits_unusable_failed_prefix",
            "test_initial_compact_p5_restart_is_flat_creative_then_technical",
            "test_initial_compact_p5_restart_exhausts_after_exactly_two_ladders",
        ):
            assert f"def {test_name}(" in test_source, (
                f"BUG-12.68 executable guard missing: {test_name}"
            )

    def test_otr_p3_prose_patch_transports_are_declared_and_fail_closed(self, pack_dir):
        """BUG-11.42: bounded prose repair requires a proven transport."""
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        if not os.path.isfile(lane_path):
            pytest.skip("BUG-11.42 P3 prose patch guard is OTR-local")
        with open(lane_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        class_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        function_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert {
            "_RadioScoreDraftTextPatchRowV4",
            "_RadioScoreDraftTextPatchV4",
        } <= class_names, (
            "BUG-11.42: P3 prose patch must have a strict typed patch root"
        )
        assert {
            "_derive_p3_text_patch_targets",
            "_p3_text_patch_preflight",
            "_merge_p3_text_patch",
            "_run_p3_text_patch",
        } <= function_names, (
            "BUG-11.42: P3 prose patch must retain its guarded boundary"
        )
        assert "_P3_TEXT_PATCH_MAX_TARGETS = 12" in source
        assert "_P3_TEXT_PATCH_MAX_OUTPUT_TOKENS = 1024" in source
        assert "(target.max_chars * 3) // 4" in source
        assert '"rewrite_tasks"' in source
        assert '"source_to_shorten"' in source
        assert '"replacement_over_schema_cap"' in source
        assert "invoke_structured_slot(" in source
        assert "_P3TextPatchMessages(_p3_text_patch_messages" in source
        assert "_otr_strict_remote_output_budget = True" in source
        assert "capture._otr_openrouter" in source
        assert "_otr_p3_text_patch_transport" in source
        assert '"full_message_remote"' in source
        assert "and isinstance(error, ValidationError)" in source

        writer_path = os.path.join(pack_dir, "nodes", "OTR_LedgerScriptWriter.py")
        with open(writer_path, "r", encoding="utf-8") as f:
            writer_source = f.read()
        assert "def _slot_transport_markers" in writer_source
        assert "_otr_p3_text_patch_local" in writer_source
        assert "_otr_p3_text_patch_transport" in writer_source
        assert '"full_message_remote"' in writer_source
        assert "response_format=None" in writer_source

        backend_path = os.path.join(pack_dir, "nodes", "_otr_openrouter_backend.py")
        with open(backend_path, "r", encoding="utf-8") as f:
            backend_source = f.read()
        assert "_otr_strict_remote_output_budget" in backend_source

        pack_path = os.path.join(
            pack_dir, "nodes", "story_packs", "scifi_codex", "scifi_codex_v1.json",
        )
        pipeline_path = os.path.join(pack_dir, "nodes", "story_packs", "pipelines.json")
        with open(pack_path, "r", encoding="utf-8") as f:
            pack = json.load(f)
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipelines = json.load(f)
        seam = pack["prompt_stages"]["codex_radio_score_text_patch"]
        assert "replacements" in seam and "exactly once" in seam
        pipeline = next(
            row for row in pipelines["pipelines"]
            if row["story_pipeline_id"] == "scifi_codex_circuit"
        )
        patch_pass = next(
            row for row in pipeline["passes"]
            if row["pass_id"] == "P3_authored_text_patch"
        )
        assert patch_pass["seam_refs"] == ["codex_radio_score_text_patch"]

    def test_otr_sibling_row_normalizers_name_the_same_speaker(self, pack_dir):
        """BUG-12.101: two normalizers for parallel row types must not
        disagree about a shared identity field.

        The enumerated dict each one builds IS its schema, so a field only
        one of them names is a field the other silently drops. This diffs
        the two key sets out of the AST rather than asserting one string,
        because the symmetry is the invariant -- the day a third row type
        arrives without `speaker`, a string check would still be green.
        """
        ledger_path = os.path.join(pack_dir, "nodes", "production_ledger.py")
        if not os.path.isfile(ledger_path):
            pytest.skip("BUG-12.101 ledger normalizer guard is OTR-local")
        with open(ledger_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        def _built_keys(func_name):
            """Every literal dict key constructed inside one function."""
            for node in ast.walk(tree):
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == func_name):
                    keys = set()
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Dict):
                            for key in inner.keys:
                                if isinstance(key, ast.Constant) and isinstance(
                                        key.value, str):
                                    keys.add(key.value)
                    return keys
            return None

        beat_keys = _built_keys("set_beats")
        line_keys = _built_keys("set_lines")
        init_keys = _built_keys("init_lines_from_outline")
        assert beat_keys, "BUG-12.101: set_beats not found in production_ledger"
        assert line_keys, "BUG-12.101: set_lines not found in production_ledger"
        assert init_keys, (
            "BUG-12.101: init_lines_from_outline not found in production_ledger"
        )
        for name, keys in (
            ("set_beats", beat_keys),
            ("set_lines", line_keys),
            ("init_lines_from_outline", init_keys),
        ):
            assert "speaker" in keys, (
                f"BUG-12.101: {name}() does not name 'speaker' in the row it "
                f"builds, so every caller that supplies one has it silently "
                f"discarded. Its sibling normalizer names it; the asymmetry "
                f"IS the bug."
            )

        # The producing lanes must SUPPLY it too -- half a fix is not a fix.
        for relative_path, marker in (
            ("nodes/_otr_scifi_codex.py", '"speaker": b.speaker'),
            ("nodes/_otr_scifi_fable2.py", '"speaker": speaker'),
        ):
            path = os.path.join(pack_dir, *relative_path.split("/"))
            if not os.path.isfile(path):
                continue
            source = open(path, encoding="utf-8").read()
            assert marker in source, (
                f"BUG-12.101: {relative_path} builds line rows without a "
                f"speaker, so the normalizer has nothing to carry"
            )

        # And the OTR-side regression guards must exist by name.
        for relative_path, test_names in (
            ("tests/test_production_ledger.py", (
                "test_set_lines_carries_speaker",
                "test_line_and_beat_normalizers_agree_on_speaker",
            )),
            ("tests/test_phase2b_progressive_ledger.py", (
                "test_line_row_carries_the_owning_beats_speaker",
            )),
        ):
            path = os.path.join(pack_dir, *relative_path.split("/"))
            if not os.path.isfile(path):
                continue
            source = open(path, encoding="utf-8").read()
            for test_name in test_names:
                assert f"def {test_name}(" in source, (
                    f"BUG-12.101 executable guard missing: "
                    f"{relative_path}::{test_name}"
                )


    def test_otr_no_schema_cap_sits_at_its_own_trim_limit(self, pack_dir):
        """BUG-12.102: a parse-time cap equal to a downstream trim REFUSES
        the input the trim was written to shorten.

        This is the static diff the entry's verify step (4) asks for, and it
        is the check that catches the NEXT one: a per-field test only ever
        covers the fields somebody remembered. It compares the constants a
        bounded list field declares against the constants passed as
        `limit=` to the deterministic trims in the same module.
        """
        lane = os.path.join(pack_dir, "nodes", "_otr_scifi_fable2.py")
        if not os.path.isfile(lane):
            pytest.skip("BUG-12.102 dossier cap guard is OTR-local")
        with open(lane, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        # Constants handed to a deterministic trim as its limit.
        trim_limits = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if not name or "balanced" not in name:
                continue
            for kw in node.keywords:
                if kw.arg == "limit" and isinstance(kw.value, ast.Name):
                    trim_limits.add(kw.value.id)
        assert trim_limits, (
            "BUG-12.102: found no deterministic trim to compare caps against; "
            "the guard would pass vacuously"
        )

        # Constants used as max_length on a bounded LIST field.
        collisions = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) or stmt.value is None:
                    continue
                if not ast.unparse(stmt.annotation).startswith("list["):
                    continue
                for kw in getattr(stmt.value, "keywords", []):
                    if kw.arg != "max_length":
                        continue
                    if not isinstance(kw.value, ast.Name):
                        continue
                    if kw.value.id in trim_limits:
                        collisions.append(
                            f"{node.name}.{ast.unparse(stmt.target)} "
                            f"caps at {kw.value.id}, which is also a trim limit"
                        )
        assert not collisions, (
            "BUG-12.102: a schema cap sits at the same constant a downstream "
            "trim already enforces, so a richer-than-usual input is REFUSED "
            "before the trim can shorten it:\n  " + "\n  ".join(collisions)
        )


class TestPhase02BugBible0214:
    """BUG-02.14 / BUG-LOCAL-043: SD 1.5 .ckpt offline/Windows four-layer fix.

    Applies to any downstream custom-node project that loads a single-file
    .ckpt via diffusers from inside a stdout-piped sidecar subprocess on
    Windows. If the project does not live at the known OTR path, the test
    is skipped cleanly.
    """

    ANCHOR_GEN_PATHS = [
        r"C:\Users\jeffr\Documents\ComfyUI\custom_nodes\ComfyUI-OldTimeRadio\otr_v2\hyworld\anchor_gen.py",
    ]

    def test_bug_02_14_sd15_ckpt_four_layer_fix(self):
        import pathlib, pytest
        src = None
        for candidate in self.ANCHOR_GEN_PATHS:
            p = pathlib.Path(candidate)
            if p.is_file():
                src = p.read_text(encoding="utf-8")
                break
        if src is None:
            pytest.skip("anchor_gen.py not found on this host; BUG-02.14 test is OTR-local")

        # Layer 1: torch.load kwargs override (not setdefault)
        assert 'kwargs["weights_only"] = False' in src or \
               "kwargs['weights_only'] = False" in src, \
               "BUG-02.14 layer 1: torch.load weights_only override missing"

        # Layer 2: pytorch_lightning shim injected into sys.modules
        assert "pytorch_lightning" in src and "sys.modules" in src, \
               "BUG-02.14 layer 2: pytorch_lightning sys.modules shim missing"

        # Layer 3: local original_config path + local_files_only=True
        assert "original_config" in src and "local_files_only" in src, \
               "BUG-02.14 layer 3: original_config + local_files_only missing"

        # Layer 4: both tqdm silencers
        assert "disable_progress_bar" in src, \
               "BUG-02.14 layer 4a: disable_progress_bar missing"
        assert "set_progress_bar_config" in src, \
               "BUG-02.14 layer 4b: pipe.set_progress_bar_config missing"


# ---------------------------------------------------------------------------
# A graph that accepts a tensor does not prove the checkpoint learned its
# meaning.  This is deliberately AST-only: capability admission must be
# inspectable before ComfyUI, a model, or a GPU is available.
# ---------------------------------------------------------------------------

class TestModelSpecificReferenceAdmission:
    """BUG-12.120: semantic capabilities require model-specific evidence."""

    _NON_LITERAL = object()
    _SHA256 = re.compile(r"[0-9a-f]{64}")
    _APPROVAL_SCHEMA = "reference-image-semantic-approval.v1"
    _MATCH_KEYS = {"prompt", "negative", "seed", "width", "height",
                   "delivery_path"}

    @classmethod
    def _literal_class_attributes(cls, path):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            tree = ast.parse(fh.read(), filename=path)
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = {}
            for stmt in node.body:
                name = None
                value = None
                if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)):
                    name = stmt.targets[0].id
                    value = stmt.value
                elif (isinstance(stmt, ast.AnnAssign)
                      and isinstance(stmt.target, ast.Name)):
                    name = stmt.target.id
                    value = stmt.value
                if name is None or value is None:
                    continue
                try:
                    attrs[name] = ast.literal_eval(value)
                except (ValueError, TypeError):
                    # A dynamic declaration is not statically provable.  Keep
                    # it visible so a capability opt-in fails closed below.
                    attrs[name] = cls._NON_LITERAL
            if attrs:
                found.append((node.name, attrs))
        return found

    @classmethod
    def _approval_violations(cls, pack_dir, label, approval):
        violations = []
        if not isinstance(approval, dict):
            return [
                f"{label} advertises accepts_reference_image=True without a "
                "literal reference_image_approval mapping"
            ]

        checkpoint = approval.get("checkpoint_sha256")
        receipt = approval.get("matched_pixel_ab_receipt")
        if not (isinstance(checkpoint, str)
                and cls._SHA256.fullmatch(checkpoint)):
            violations.append(
                f"{label} has no exact lowercase checkpoint_sha256"
            )
        if not isinstance(receipt, str) or not receipt.strip():
            violations.append(f"{label} has no matched_pixel_ab_receipt")
            return violations

        pack_root = os.path.realpath(pack_dir)
        receipt_path = os.path.realpath(os.path.join(pack_root, receipt))
        try:
            contained = os.path.commonpath((pack_root, receipt_path)) == pack_root
        except ValueError:
            contained = False
        if os.path.isabs(receipt) or not contained:
            violations.append(
                f"{label} cites a receipt outside the checked-in pack: {receipt!r}"
            )
            return violations
        if not os.path.isfile(receipt_path):
            violations.append(
                f"{label} cites missing matched pixel A/B receipt {receipt!r}"
            )
            return violations
        try:
            in_worktree = subprocess.run(
                ["git", "-C", pack_root, "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, check=False,
            )
        except OSError:
            in_worktree = None
        if in_worktree is not None and in_worktree.returncode == 0:
            tracked = subprocess.run(
                ["git", "-C", pack_root, "ls-files", "--error-unmatch",
                 "--", receipt],
                capture_output=True, text=True, check=False,
            )
            if tracked.returncode != 0:
                violations.append(
                    f"{label} cites an untracked matched pixel A/B receipt "
                    f"{receipt!r}"
                )
        try:
            with open(receipt_path, "r", encoding="utf-8-sig") as fh:
                evidence = json.load(fh)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            violations.append(
                f"{label} cites unreadable matched pixel A/B receipt "
                f"{receipt!r}: {exc}"
            )
            return violations
        if not isinstance(evidence, dict):
            return violations + [f"{label} receipt root is not an object"]
        if evidence.get("schema") != cls._APPROVAL_SCHEMA:
            violations.append(
                f"{label} receipt has no {cls._APPROVAL_SCHEMA!r} schema"
            )
        if evidence.get("checkpoint_sha256") != checkpoint:
            violations.append(
                f"{label} receipt checkpoint_sha256 does not match the engine"
            )
        if not isinstance(evidence.get("checkpoint_filename"), str) \
                or not evidence["checkpoint_filename"].strip():
            violations.append(f"{label} receipt has no checkpoint_filename")
        reference_sha = evidence.get("reference_sha256")
        if not (isinstance(reference_sha, str)
                and cls._SHA256.fullmatch(reference_sha)):
            violations.append(f"{label} receipt has no exact reference_sha256")

        if evidence.get("verdict") != "APPROVED":
            violations.append(
                f"{label} receipt has no explicit APPROVED pixel verdict"
            )
        review = evidence.get("pixel_review")
        if not (isinstance(review, dict)
                and isinstance(review.get("reviewer"), str)
                and review["reviewer"].strip()
                and isinstance(review.get("finding"), str)
                and review["finding"].strip()):
            violations.append(
                f"{label} receipt has no attributed pixel-review finding"
            )

        arms = evidence.get("arms")
        signatures = {}
        graph_hashes = {}
        output_hashes = {}
        if not isinstance(arms, dict):
            violations.append(f"{label} receipt has no OFF/ON arms")
            return violations
        for arm, expected_branch in (("off", False), ("on", True)):
            arm_data = arms.get(arm)
            if not isinstance(arm_data, dict):
                violations.append(f"{label} receipt has no {arm.upper()} arm")
                continue
            if arm_data.get("status") != "SUCCESS":
                violations.append(
                    f"{label} receipt {arm.upper()} arm is not SUCCESS"
                )
            if arm_data.get("reference_branch") is not expected_branch:
                violations.append(
                    f"{label} receipt {arm.upper()} arm does not prove its "
                    "reference-branch state"
                )
            signature = arm_data.get("match_signature")
            if not (isinstance(signature, dict)
                    and cls._MATCH_KEYS <= set(signature)):
                violations.append(
                    f"{label} receipt {arm.upper()} arm has an incomplete "
                    "match_signature"
                )
            else:
                signatures[arm] = signature
            for field, bucket in (("graph_sha256", graph_hashes),
                                  ("native_output_sha256", output_hashes)):
                value = arm_data.get(field)
                if not (isinstance(value, str)
                        and cls._SHA256.fullmatch(value)):
                    violations.append(
                        f"{label} receipt {arm.upper()} arm has no exact {field}"
                    )
                else:
                    bucket[arm] = value

        if set(signatures) == {"off", "on"} \
                and signatures["off"] != signatures["on"]:
            violations.append(f"{label} receipt OFF/ON arms are not matched")
        if len(set(graph_hashes.values())) != len(graph_hashes):
            violations.append(f"{label} receipt OFF/ON graph hashes are equal")
        if len(set(output_hashes.values())) != len(output_hashes):
            violations.append(f"{label} receipt OFF/ON native pixels are equal")
        return violations

    def test_reference_image_capability_requires_checkpoint_and_pixel_proof(
            self, py_files, pack_dir):
        """A generic ReferenceLatent-style node is structural evidence only.

        A literal opt-in must name the exact checkpoint and a checked-in matched
        pixel A/B receipt.  The OTR-local tail pins the live rejection, including
        the cache-version bump and the independent identity seed.
        """
        violations = []
        for path in py_files:
            relative = os.path.relpath(path, pack_dir).replace("\\", "/")
            if any(part in {".claude", "tmp", "scratch", "kibitz",
                            "otr", "otr_soak_receipts"}
                   for part in relative.split("/")):
                continue
            with open(path, "r", encoding="utf-8-sig",
                      errors="replace") as fh:
                if "accepts_reference_image" not in fh.read():
                    continue
            for class_name, attrs in self._literal_class_attributes(path):
                capability = attrs.get("accepts_reference_image")
                label = f"{os.path.relpath(path, pack_dir)}::{class_name}"
                if capability is self._NON_LITERAL:
                    violations.append(
                        f"{label} has a dynamic accepts_reference_image; "
                        "shipping capability declarations must be literal"
                    )
                    continue
                if capability is not True:
                    continue
                approval = attrs.get("reference_image_approval")
                violations.extend(
                    self._approval_violations(pack_dir, label, approval)
                )

        assert not violations, "BUG-12.120: " + "; ".join(violations)

        # OTR-specific executable receipt.  Other packs stop at the generic
        # admission scan above.
        zimage_path = os.path.join(
            pack_dir, "nodes", "_otr_image_engines", "z_image_turbo.py"
        )
        if not os.path.isfile(zimage_path):
            return
        zimage_attrs = dict(self._literal_class_attributes(zimage_path)).get(
            "ZImageTurboEngine", {}
        )
        assert zimage_attrs.get("accepts_reference_image") is False
        assert zimage_attrs.get("engine_version") == "2", (
            "BUG-12.120: disabling the rejected reference path must invalidate "
            "v1 cached grids"
        )

        engine_tests = os.path.join(pack_dir, "tests", "test_image_engine_c2.py")
        seed_tests = os.path.join(pack_dir, "tests", "test_still_spine_helpers.py")
        harness = os.path.join(pack_dir, "scripts", "otr_zimage_reference_ab.py")
        for required in (engine_tests, seed_tests, harness):
            assert os.path.isfile(required), (
                f"BUG-12.120: required rejection evidence missing: {required}"
            )
        with open(engine_tests, "r", encoding="utf-8") as fh:
            assert "test_no_shipping_image_engine_advertises_unproven_reference_conditioning" in fh.read()
        with open(seed_tests, "r", encoding="utf-8") as fh:
            assert "test_zimage_reference_rejection_keeps_the_identity_seed" in fh.read()

        dispatcher = os.path.join(pack_dir, "nodes", "otr_image_gen_dispatcher.py")
        with open(dispatcher, "r", encoding="utf-8-sig") as fh:
            dispatcher_tree = ast.parse(fh.read(), filename=dispatcher)
        cache_functions = [
            node for node in ast.walk(dispatcher_tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "request_cache_key"
        ]
        assert len(cache_functions) == 1
        cache_function = cache_functions[0]
        assert "engine_version" in {
            arg.arg for arg in cache_function.args.args
        }, "BUG-12.120: cache key API lost engine_version"
        assert any(
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "engine_version"
            for node in ast.walk(cache_function)
        ), "BUG-12.120: request_cache_key no longer consumes engine_version"

    def test_unproved_opt_in_fails_and_a_pinned_receipt_passes(self, tmp_path):
        """Mutation proof for the generic half of BUG-12.120."""
        engine = tmp_path / "engine.py"
        checkpoint = "0" * 64
        receipt = tmp_path / "evidence" / "matched-reference-ab.json"
        receipt.parent.mkdir()

        def write_engine(capability="True"):
            engine.write_text(
                "class Engine:\n"
                f"    accepts_reference_image = {capability}\n"
                "    reference_image_approval = {\n"
                f"        'checkpoint_sha256': {checkpoint!r},\n"
                "        'matched_pixel_ab_receipt': "
                "'evidence/matched-reference-ab.json',\n"
                "    }\n",
                encoding="utf-8",
            )

        def write_receipt(**updates):
            signature = {
                "prompt": "subject", "negative": "artifact", "seed": 7,
                "width": 1024, "height": 1024, "delivery_path": "native",
            }
            payload = {
                "schema": self._APPROVAL_SCHEMA,
                "checkpoint_filename": "model.safetensors",
                "checkpoint_sha256": checkpoint,
                "reference_sha256": "1" * 64,
                "verdict": "APPROVED",
                "pixel_review": {
                    "reviewer": "operator", "finding": "identity preserved",
                },
                "arms": {
                    "off": {
                        "status": "SUCCESS", "reference_branch": False,
                        "match_signature": signature,
                        "graph_sha256": "2" * 64,
                        "native_output_sha256": "3" * 64,
                    },
                    "on": {
                        "status": "SUCCESS", "reference_branch": True,
                        "match_signature": dict(signature),
                        "graph_sha256": "4" * 64,
                        "native_output_sha256": "5" * 64,
                    },
                },
            }
            for dotted_key, value in updates.items():
                target = payload
                parts = dotted_key.split("__")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
            receipt.write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )

        def assert_rejected(match):
            with pytest.raises(AssertionError, match=match):
                self.test_reference_image_capability_requires_checkpoint_and_pixel_proof(
                    [str(engine)], str(tmp_path)
                )

        engine.write_text(
            "class Engine:\n"
            "    accepts_reference_image = True\n",
            encoding="utf-8",
        )
        assert_rejected("reference_image_approval")

        write_engine("bool(os.environ.get('ENABLE_REFERENCE'))")
        assert_rejected("dynamic accepts_reference_image")

        write_engine()
        receipt.write_text("{not-json}\n", encoding="utf-8")
        assert_rejected("unreadable matched pixel A/B receipt")

        write_receipt(checkpoint_sha256="f" * 64)
        assert_rejected("checkpoint_sha256 does not match")

        write_receipt(arms__on__match_signature={"prompt": "drifted"})
        assert_rejected("incomplete match_signature")

        write_receipt(arms__on__reference_branch=False)
        assert_rejected("does not prove its reference-branch state")

        write_receipt(arms__off__status="FAILED")
        assert_rejected("OFF arm is not SUCCESS")

        write_receipt(verdict="REJECTED")
        assert_rejected("no explicit APPROVED pixel verdict")

        write_receipt(pixel_review={})
        assert_rejected("no attributed pixel-review finding")

        subprocess.run(
            ["git", "init", "--quiet"], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "add", "engine.py"], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        )
        write_receipt()
        assert_rejected("untracked matched pixel A/B receipt")
        subprocess.run(
            ["git", "add", "evidence/matched-reference-ab.json"],
            cwd=tmp_path, check=True, capture_output=True, text=True,
        )
        self.test_reference_image_capability_requires_checkpoint_and_pixel_proof(
            [str(engine)], str(tmp_path)
        )


class TestProvisioningTrackedStateBoundary:
    def test_cloud_provisioner_does_not_reject_template_untracked_paths(
        self, pack_dir
    ):
        """BUG-12.141: a tracked-work guard must not reject normal untracked
        venvs, caches, or sibling links owned by a cloud template."""
        provisioner = os.path.join(pack_dir, "scripts", "otr_pod_provision.sh")
        if not os.path.isfile(provisioner):
            pytest.skip("pack has no OTR pod provisioner")
        with open(provisioner, encoding="utf-8") as handle:
            text = handle.read()
        assert "status --porcelain --untracked-files=no" in text
        assert "status --porcelain --untracked-files=all" not in text


# ---------------------------------------------------------------------------
# The bible must actually BE machine-readable
# ---------------------------------------------------------------------------
# README.md calls BUG_BIBLE.yaml "machine-readable" in three places and the
# Three-File Contract is built on that claim. It was not true: six entry fields
# were written as PLAIN scalars whose text contains ': ', which YAML reads as a
# second mapping value, so yaml.safe_load raised a ScannerError at line 834 and
# had done since those entries landed. Nothing noticed because every structural
# check in this suite counts '^- id:' with a REGEX -- a text scan that cannot
# tell a parseable file from an unparseable one.
#
# That is the same defect class the bible itself now carries as BUG-12.87: a
# check that reports clean because it never examined the thing it claims to
# cover. Fixed by converting those six fields to block scalars; kept fixed here.

class TestBibleIsActuallyParseable:
    def _repo_root(self):
        """Survival-guide repo root (parent of tests/).

        Same one-liner TestThreeFileContract uses. Deliberately duplicated
        rather than imported across classes: these tests must resolve the
        BIBLE's own location, never the --pack-dir target the rest of the
        suite is aimed at.
        """
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _bible_text(self):
        with open(os.path.join(self._repo_root(), "BUG_BIBLE.yaml"),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_bug_bible_yaml_safe_loads(self):
        yaml = pytest.importorskip(
            "yaml", reason="pyyaml not installed on this host")
        raw = self._bible_text()
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:              # pragma: no cover - the bug
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1} col {mark.column + 1}" if mark else ""
            pytest.fail(
                f"BUG_BIBLE.yaml does not parse{where}: "
                f"{getattr(exc, 'problem', exc)}. README calls this file "
                f"machine-readable. The usual cause is a plain (unquoted) "
                f"scalar containing ': ' -- use a '|' block scalar instead."
            )
        assert isinstance(data, dict), (
            f"top level parsed as {type(data).__name__}, expected a mapping "
            f"with 'schema' and 'bugs'"
        )
        assert "bugs" in data, f"no 'bugs' key; got {sorted(data)}"

    def test_parsed_entry_count_matches_the_regex_count(self):
        """Ties the two views together.

        Every other structural test here counts '^- id:' textually. If the
        parsed count and the text count ever disagree, one of the two views is
        lying and both are load-bearing.
        """
        yaml = pytest.importorskip(
            "yaml", reason="pyyaml not installed on this host")
        raw = self._bible_text()
        text_count = sum(1 for ln in raw.splitlines()
                         if ln.startswith("- id:"))
        parsed = yaml.safe_load(raw)["bugs"]
        assert len(parsed) == text_count, (
            f"parsed {len(parsed)} entries but {text_count} '- id:' lines"
        )

    def test_every_parsed_entry_has_the_documented_fields(self):
        """README: 'Each entry: id, phase, area, symptom, cause, fix, verify,
        tags, legacy_id.' Unreachable while the file would not parse."""
        yaml = pytest.importorskip(
            "yaml", reason="pyyaml not installed on this host")
        parsed = yaml.safe_load(self._bible_text())["bugs"]
        required = ("id", "phase", "area", "symptom", "cause", "fix", "verify",
                    "tags")
        missing = []
        for entry in parsed:
            gaps = [k for k in required if not entry.get(k)]
            if gaps:
                missing.append((entry.get("id", "<no id>"), gaps))
        assert not missing, f"entries missing documented fields: {missing[:10]}"
