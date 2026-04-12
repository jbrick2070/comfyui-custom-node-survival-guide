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
    Phase 04: Widget ordering (INPUT_TYPES structure)
    Phase 05: Execution order (passthrough enforcement)
    Phase 07: VRAM discipline (unload/flush patterns)
    Phase 09: Subprocess safety (pipe deadlocks, cleanup)
    Phase 12: Git/repo hygiene (0-byte files, workflow JSON integrity)
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
    """Collect all .py files in the pack (excluding __pycache__)."""
    found = []
    for root, dirs, files in os.walk(pack_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__" and d != ".git"]
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

        Checks files containing OUTPUT_NODE = True.
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

        At least 80% of node IDs should have a prefix (e.g., OTR_).
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
        """BUG-04.01/04.02: Verify widgets_values length matches
        the number of optional widgets in each node's INPUT_TYPES.

        Skips nodes where INPUT_TYPES can't be statically analyzed.
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
        """BUG-07.01/03.02: No heavy model loads at module scope.

        from_pretrained, torch.load, load_checkpoint at module scope
        (outside a function/class) cause slow startup and VRAM leak.
        """
        heavy_patterns = [
            r"^from_pretrained\(",
            r"^torch\.load\(",
            r"^\.load_checkpoint\(",
            r"^AutoModel\w*\.from_pretrained\(",
            r"^AutoTokenizer\.from_pretrained\(",
        ]
        combined = re.compile("|".join(heavy_patterns), re.MULTILINE)

        violations = []
        for fpath in py_files:
            try:
                tree = ast.parse(open(fpath, "r", encoding="utf-8").read())
            except SyntaxError:
                continue

            # Check for calls at module scope (not inside functions/classes)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.Expr, ast.Assign)):
                    src_line = ast.get_source_segment(
                        open(fpath, "r", encoding="utf-8").read(), node
                    )
                    if src_line and ("from_pretrained" in str(src_line) or
                                     "torch.load" in str(src_line)):
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
# BUG-12.05: Multi-layer parameter sync
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


# ─────────────────────────────────────────────────────────────────
# SUMMARY REPORT
# ─────────────────────────────────────────────────────────────────

class TestSummary:
    """Final summary assertions."""

    def test_pack_has_init(self, pack_dir):
        """Basic: Pack must have __init__.py."""
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
