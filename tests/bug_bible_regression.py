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
    BUG-12.52.

    These rules were admitted from dated smokes, published artifacts, or GPU
    runs. The project tests named below exercise their concrete behavior; this
    catalog guard makes loss of that coverage a Bible regression as well.
    """

    EXPECTED_TESTS = {
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


class TestPhase02BugBible0216:
    """BUG-02.16: capability-gated architecture and split-revision HF cache."""

    def test_otr_gemma4_unified_admission_contract(self, pack_dir):
        loader_path = os.path.join(pack_dir, "nodes", "_otr_model_loader.py")
        env_path = os.path.join(pack_dir, "nodes", "_otr_hf_env.py")
        requirements_path = os.path.join(pack_dir, "requirements.txt")
        tests_path = os.path.join(pack_dir, "tests", "test_hf_env_offline.py")
        doctor_path = os.path.join(pack_dir, "scripts", "otr_gemma4_doctor.py")

        if not os.path.isfile(loader_path):
            pytest.skip("BUG-02.16 Gemma4Unified admission guard is OTR-local")
        for path in (env_path, requirements_path, tests_path, doctor_path):
            assert os.path.isfile(path), f"BUG-02.16 required artifact missing: {path}"

        with open(loader_path, encoding="utf-8") as handle:
            loader_source = handle.read()
        with open(env_path, encoding="utf-8") as handle:
            env_source = handle.read()
        with open(requirements_path, encoding="utf-8") as handle:
            requirements = handle.read()
        with open(tests_path, encoding="utf-8") as handle:
            test_source = handle.read()
        with open(doctor_path, encoding="utf-8") as handle:
            doctor_source = handle.read()

        assert re.search(
            r"(?m)^transformers>=5\.10\.4,<6\.0\s*$", requirements
        )
        assert '_GEMMA4_UNIFIED_MIN_TRANSFORMERS = "5.10.4"' in loader_source
        gate = loader_source.index(
            "_require_transformers_model_support(normalized)"
        )
        download = loader_source.index(
            "_otr_catalog.auto_download_if_missing("
        )
        assert gate < download

        assert "def _snapshot_has_weights(" in env_source
        assert "if _snapshot_has_weights(p)" in env_source
        assert "def resolve_snapshot_file(" in env_source
        assert '"chat_template.jinja"' in loader_source
        assert "local_files_only=True" in loader_source

        for test_name in (
            "test_snapshot_resolver_prefers_weights_and_composes_newer_metadata",
            "test_snapshot_resolver_rejects_metadata_only_cache",
            "test_gemma_version_guard_is_early_and_actionable",
            "test_request_slot_uses_complete_canonical_cache_without_download",
        ):
            assert f"def {test_name}(" in test_source

        assert "get_cached_transformers_schema_constraint" in doctor_source
        assert "local_files_only=True" in doctor_source
        assert (
            "RESULT=PASS (official Transformers + NF4 + LMFE, fully offline)"
            in doctor_source
        )


class TestPhase11BugBible1155:
    """BUG-11.55: constrained schemas must be compiler-safe, not open wildcards."""

    def test_otr_script_artifact_uses_a_closed_scene_schema(self, pack_dir):
        lane_path = os.path.join(pack_dir, "nodes", "_otr_scifi_codex.py")
        tests_path = os.path.join(pack_dir, "tests", "test_scifi_codex_lane.py")

        if not os.path.isfile(lane_path):
            pytest.skip("BUG-11.55 ScriptArtifactV4 contract is OTR-local")
        assert os.path.isfile(tests_path), (
            f"BUG-11.55 executable regression missing: {tests_path}"
        )

        with open(lane_path, encoding="utf-8") as handle:
            lane_source = handle.read()
        with open(tests_path, encoding="utf-8") as handle:
            test_source = handle.read()

        assert "class ScriptSceneV4(_Strict):" in lane_source
        assert "scenes: list[ScriptSceneV4]" in lane_source
        assert (
            "    scenes: list[dict[str, Any]] = Field(min_length=1)"
            not in lane_source
        )
        assert (
            "def test_script_artifact_scene_schema_is_closed_for_lm_format_enforcer("
            in test_source
        )
        for proof in (
            "JsonSchemaParser(schema)",
            "parser.get_allowed_characters()",
            "parser.add_character(character)",
            "parser.can_end()",
            'scene_schema["additionalProperties"] is False',
        ):
            assert proof in test_source, f"BUG-11.55 proof missing: {proof}"
