"""Compare the three normalization versions side-by-side.

Inputs:
  v0 = docs/normalization_compare/BUG_BIBLE.v0_baseline.yaml
  v1 = docs/normalization_compare/BUG_BIBLE.v1_claude.yaml
  v2 = docs/normalization_compare/BUG_BIBLE.v2_round_robin.yaml  (you create this
       AFTER reading the round-robin synthesis and applying its suggestions)

Outputs (printed + saved to compare_report.md):
  - line-count delta
  - entry-count delta
  - common changes (overlapping diffs)
  - changes unique to Claude pass
  - changes unique to round-robin pass
  - schema validation status of each
"""

import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
COMP = ROOT / "docs" / "bonus_normalization_experiment"
V0 = COMP / "BUG_BIBLE.v0_baseline.yaml"
V1 = COMP / "BUG_BIBLE.v1_claude.yaml"
V2 = COMP / "BUG_BIBLE.v2_round_robin.yaml"
REPORT = COMP / "compare_report.md"


def count_entries(text: str) -> int:
    return len(re.findall(r"^- id:", text, flags=re.MULTILINE))


def schema_check(yaml_path: Path) -> str:
    try:
        out = subprocess.check_output(
            [
                sys.executable,
                str(ROOT / "tools" / "reload_bug_bible.py"),
                "--bible",
                str(yaml_path),
            ],
            stderr=subprocess.STDOUT,
            text=True,
        )
        return out.splitlines()[-1]
    except subprocess.CalledProcessError as e:
        return f"FAIL: {e.output.splitlines()[-1] if e.output else e}"


def diff_summary(a: str, b: str, label_a: str, label_b: str) -> str:
    diff = list(
        difflib.unified_diff(
            a.splitlines(),
            b.splitlines(),
            fromfile=label_a,
            tofile=label_b,
            lineterm="",
            n=0,
        )
    )
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    return f"{added:+d} / {removed:-d} (added/removed lines)"


def main() -> int:
    if not V0.is_file() or not V1.is_file():
        print(f"ERROR: missing baseline ({V0}) or v1 ({V1})", file=sys.stderr)
        return 2

    v0 = V0.read_text(encoding="utf-8")
    v1 = V1.read_text(encoding="utf-8")
    v2_present = V2.is_file()
    v2 = V2.read_text(encoding="utf-8") if v2_present else None

    lines: list[str] = [
        "# Normalization comparison report",
        "",
        f"Versions present: v0=baseline, v1=Claude, v2={'round-robin' if v2_present else 'NOT YET CREATED'}",
        "",
        "## Counts",
        "",
        "| version | entries | lines | schema |",
        "|---------|---------|-------|--------|",
        f"| v0 baseline      | {count_entries(v0)} | {len(v0.splitlines())} | {schema_check(V0)} |",
        f"| v1 Claude        | {count_entries(v1)} | {len(v1.splitlines())} | {schema_check(V1)} |",
    ]
    if v2_present:
        lines.append(
            f"| v2 round-robin   | {count_entries(v2)} | {len(v2.splitlines())} | {schema_check(V2)} |"
        )
    else:
        lines.append("| v2 round-robin   | (not yet created — run `run_pass_b.ps1` then save the result here) | | |")

    lines += [
        "",
        "## Diff summaries",
        "",
        f"- v0 → v1 (Claude): {diff_summary(v0, v1, 'v0', 'v1')}",
    ]
    if v2_present:
        lines += [
            f"- v0 → v2 (round-robin): {diff_summary(v0, v2, 'v0', 'v2')}",
            f"- v1 → v2 (round-robin vs Claude): {diff_summary(v1, v2, 'v1', 'v2')}",
        ]
    lines += [
        "",
        "## Where the two passes agree",
        "",
    ]
    if v2_present:
        v0_lines = set(v0.splitlines())
        v1_only = set(v1.splitlines()) - v0_lines
        v2_only = set(v2.splitlines()) - v0_lines
        common = v1_only & v2_only
        v1_unique = v1_only - v2_only
        v2_unique = v2_only - v1_only
        lines += [
            f"- common new lines (both passes added): {len(common)}",
            f"- Claude-only new lines: {len(v1_unique)}",
            f"- round-robin-only new lines: {len(v2_unique)}",
            "",
            "### Sample of Claude-only changes (first 15)",
            "",
        ]
        lines += [f"  {ln[:100]}" for ln in sorted(v1_unique)[:15]]
        lines += [
            "",
            "### Sample of round-robin-only changes (first 15)",
            "",
        ]
        lines += [f"  {ln[:100]}" for ln in sorted(v2_unique)[:15]]
    else:
        lines += [
            "(intersection requires v2 — run the round-robin pass and save the",
            "result as `BUG_BIBLE.v2_round_robin.yaml` next to this report,",
            "then re-run `python compare_passes.py`.)",
        ]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
