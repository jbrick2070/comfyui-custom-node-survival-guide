"""tools/reload_bug_bible.py — validate BUG_BIBLE.yaml after edits.

Run this any time you add or modify a Bible entry. The script:

  - parses every `- id:` block
  - checks each block has the required keys
    (id / phase / area / symptom / cause / fix / verify / tags / legacy_id)
  - checks no duplicate IDs
  - checks tags are kebab-case (lowercase, ASCII letters/digits, hyphens)
  - checks legacy_id is either empty or matches `BUG-LOCAL-NNN` /
    a bare numeric string (older entries)
  - prints a per-phase entry count summary

Exits 0 if everything is clean, non-zero otherwise so it's easy to wire
into a pre-commit hook.

Usage::

    python tools/reload_bug_bible.py
    python tools/reload_bug_bible.py --bible BUG_BIBLE.yaml
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


REQUIRED_KEYS = (
    "id",
    "phase",
    "area",
    "symptom",
    "cause",
    "fix",
    "verify",
    "tags",
    "legacy_id",
)

ID_RE = re.compile(r'^- id:\s+"([\d.]+)"\s*$')
KEY_RE = re.compile(r"^  ([a-z_][a-z0-9_]*):")
LEGACY_OK_RE = re.compile(
    r"^(BUG-LOCAL-\d{3}|PBUG-\d{8}-\d{2}|\d+(\.\d+)?|NEW)?$"
)
# Tag style: lowercase letters/digits separated by `-` or `_`. The bible
# mixes both: `widget-default` (kebab-case for natural-language phrases)
# and `output_node` / `is_changed` / `validate_inputs` (snake_case for
# direct Python-symbol references). Both are accepted; uppercase /
# whitespace / punctuation are not.
TAG_RE = re.compile(r"^[a-z0-9]+([-_][a-z0-9]+)*$")


def parse_blocks(text: str) -> list[dict[str, str]]:
    """Walk the YAML and emit a list of dicts {key: raw_value} per block.

    We don't depend on PyYAML here — too many entries currently use a
    block-scalar style ``symptom: |`` with multi-line content, and we
    only need to verify presence/format of the required keys.
    """
    blocks: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    cur_indent_for_key: str | None = None
    cur_block_scalar_lines: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m_id = ID_RE.match(line)
        if m_id:
            if cur is not None:
                blocks.append(cur)
            cur = {"id": m_id.group(1)}
            cur_indent_for_key = None
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        m_key = KEY_RE.match(line)
        if m_key:
            key = m_key.group(1)
            value = line[len(m_key.group(0)) :].strip()
            cur[key] = value
            i += 1
            continue
        # New top-level entry (e.g. comment, blank, schema block) ends
        # the current entry's parsing scope.
        if line.startswith("- ") or (line and not line.startswith(" ")):
            blocks.append(cur)
            cur = None
            i += 1
            continue
        i += 1
    if cur is not None:
        blocks.append(cur)
    return blocks


def find_legacy_format_entries(text: str) -> list[str]:
    """Find entries that use the deprecated ``12.NN:`` mapping form
    instead of the canonical ``- id: "12.NN"`` list form.

    Returns a list of legacy ids found (e.g. ``["12.23", "12.24"]``).
    """
    matches = re.findall(r"^(\d+\.\d+):\s*$", text, flags=re.MULTILINE)
    return matches


def validate(bible_path: Path) -> int:
    if not bible_path.is_file():
        print(f"ERROR: {bible_path} not found", file=sys.stderr)
        return 2
    text = bible_path.read_text(encoding="utf-8")

    issues: list[str] = []
    blocks = parse_blocks(text)
    legacy_format_entries = find_legacy_format_entries(text)

    # 1. Duplicate-id check
    id_counts = Counter(b.get("id", "") for b in blocks)
    for id_, n in id_counts.items():
        if n > 1 and id_:
            issues.append(f"duplicate id {id_!r} appears {n} times")

    # 2. Required keys
    for blk in blocks:
        for key in REQUIRED_KEYS:
            if key not in blk:
                issues.append(
                    f"id={blk.get('id', '?')!r} is missing key {key!r}"
                )

    # 3. Legacy id format
    for blk in blocks:
        legacy = blk.get("legacy_id", "").strip().strip('"').strip("'")
        if not LEGACY_OK_RE.match(legacy):
            issues.append(
                f"id={blk.get('id', '?')!r} has malformed "
                f"legacy_id={legacy!r}"
            )

    # 4. Tag style — heuristic, since tags is a `[a, b, c]` flow list
    for blk in blocks:
        tags_raw = blk.get("tags", "").strip()
        if not (tags_raw.startswith("[") and tags_raw.endswith("]")):
            # Multi-line / unparseable shape — skip strict tag check;
            # presence is already enforced by REQUIRED_KEYS.
            continue
        inner = tags_raw[1:-1]
        for raw_tag in inner.split(","):
            tag = raw_tag.strip().strip('"').strip("'")
            if not tag:
                continue
            if not TAG_RE.match(tag):
                issues.append(
                    f"id={blk.get('id', '?')!r} has non-kebab-case "
                    f"tag {tag!r}"
                )

    # 5. Legacy mapping-format flag
    if legacy_format_entries:
        issues.append(
            "deprecated mapping-form entries detected (convert to "
            f"`- id: \"<id>\"` list form): {legacy_format_entries}"
        )

    # 6. Per-phase entry-count summary (always printed)
    by_phase: Counter[str] = Counter()
    for blk in blocks:
        phase = blk.get("phase", "?").strip()
        by_phase[phase] += 1

    print(f"Bible file:       {bible_path}")
    print(f"Total entries:    {len(blocks)}")
    print(f"Phases:           "
          f"{', '.join(f'{p}:{n}' for p, n in sorted(by_phase.items()))}")
    if legacy_format_entries:
        print(
            f"Legacy mapping:   {len(legacy_format_entries)} "
            f"({legacy_format_entries})"
        )
    if not issues:
        print("STATUS:           OK — schema clean.")
        return 0
    print(f"STATUS:           {len(issues)} issue(s):")
    for line in issues:
        print(f"  - {line}")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Validate BUG_BIBLE.yaml schema. Run after editing the "
            "bible to catch missing keys, duplicate ids, malformed "
            "tags, and deprecated mapping-form entries."
        )
    )
    p.add_argument(
        "--bible",
        default=None,
        help="Path to BUG_BIBLE.yaml (default: bible at repo root).",
    )
    args = p.parse_args(argv)
    bible_path = Path(
        args.bible
        or (Path(__file__).resolve().parent.parent / "BUG_BIBLE.yaml")
    )
    return validate(bible_path)


if __name__ == "__main__":
    raise SystemExit(main())
