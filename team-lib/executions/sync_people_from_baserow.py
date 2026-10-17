#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Refresh the generated block in team-lib person files (context/indexed/people/) from an export of Baserow People table 656. Writes only an allowlist of non-HR columns between the people-sync markers, never touches hand-authored text, and reports team members with no person file. Dry run by default."
# created: 2026-10-07
# last_updated: 2026-10-07
# maintainer: pvragon
# ---
"""sync_people_from_baserow.py — Baserow is a sync source, not the source of truth.

Person files in context/indexed/people/ are the durable record (the operator, 2026-10-07: "assume
Baserow may not exist after a while but keep it as a sync for now"). This script only rewrites
the block between

    <!-- BEGIN GENERATED: people-sync ... -->
    <!-- END GENERATED -->

so if Baserow is retired, nothing breaks: the block just stops refreshing.

INPUT: a JSON export of People (table 656), as returned by the Baserow MCP tool
`list_table_rows` or the REST API with user_field_names=true: either a list of row objects or
{"results": [...]}. Scripts cannot call MCP tools, so the export is an agent step:
    1. list_table_rows(table_id=656, size=200) -> save to my-lib/runtime/.tmp/YYMMDD-baserow-people.json
    2. python3 sync_people_from_baserow.py --rows <file>            (dry run)
    3. python3 sync_people_from_baserow.py --rows <file> --apply

SAFETY: only columns in ALLOWED are ever written. HR fields (personal email, phone, birthday,
emergency contact, compensation, notes, risk flags) are dropped even if present in the export.
Column names are matched case-insensitively. Single-select values ({"value": ...}) and lists
are flattened. A row matches a file by slug of its full name (`first-last.md`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PEOPLE_DIR = Path(__file__).resolve().parent.parent / "context" / "indexed" / "people"
BEGIN = "<!-- BEGIN GENERATED: people-sync (Baserow People table 656). Do not hand-edit; rerun the sync. -->"
END = "<!-- END GENERATED -->"
BLOCK_RE = re.compile(r"<!-- BEGIN GENERATED: people-sync.*?-->.*?<!-- END GENERATED -->", re.S)

# Baserow column (lowercased) -> label written into the file. Anything else is dropped.
ALLOWED = {
    "preferred name": "Preferred name",
    "pronouns": "Pronouns",
    "status": "Status",
    "person type": "Type",
    "role": "Role",
    "title": "Role",
    "location": "Location",
    "timezone": "Timezone",
    "start date": "Start date",
    "end date": "End date",
    "work email": "Work email",
    "github handle": "GitHub",
    "github": "GitHub",
    "clickup user id": "ClickUp user id",
}
NAME_KEYS = ("full name", "name")


def flat(v):
    if isinstance(v, dict):
        return flat(v.get("value") or v.get("name") or "")
    if isinstance(v, list):
        return ", ".join(x for x in (flat(i) for i in v) if x)
    return "" if v is None else str(v).strip()


def slug(name: str) -> str:
    """'Akhlaque, Areeba' -> 'areeba-akhlaque'; 'Toni McGee' -> 'toni-mcgee'."""
    name = name.strip()
    if "," in name:
        last, first = [p.strip() for p in name.split(",", 1)]
        name = f"{first} {last}"
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("results", data) if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)]


def render(row: dict) -> str:
    lower = {k.lower().strip(): v for k, v in row.items()}
    lines, seen = [], set()
    for col, label in ALLOWED.items():
        val = flat(lower.get(col))
        if val and label not in seen:
            lines.append(f"- **{label}:** {val}")
            seen.add(label)
    body = "\n".join(lines) if lines else "- (no allowed fields in the export)"
    return f"{BEGIN}\n## From Baserow (synced)\n\n{body}\n{END}"


def run(rows_path: str, apply: bool = False, people_dir: Path = PEOPLE_DIR) -> dict:
    rows = load_rows(Path(rows_path))
    updated, unchanged, no_file, no_marker = [], [], [], []
    for row in rows:
        lower = {k.lower().strip(): v for k, v in row.items()}
        name = next((flat(lower[k]) for k in NAME_KEYS if flat(lower.get(k))), "")
        if not name:
            continue
        f = people_dir / f"{slug(name)}.md"
        if not f.exists():
            no_file.append(name)
            continue
        text = f.read_text(encoding="utf-8")
        if not BLOCK_RE.search(text):
            no_marker.append(f.name)
            continue
        new = BLOCK_RE.sub(lambda _m: render(row), text, count=1)
        if new == text:
            unchanged.append(f.name)
            continue
        updated.append(f.name)
        if apply:
            f.write_text(new, encoding="utf-8")
    return {"rows": len(rows), "updated": updated, "unchanged": unchanged,
            "no_person_file": no_file, "no_marker": no_marker, "applied": apply}


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync the people-sync block from a Baserow export.")
    ap.add_argument("--rows", required=True, help="JSON export of Baserow People (table 656)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--people-dir", type=Path, default=PEOPLE_DIR)
    a = ap.parse_args()
    res = run(a.rows, a.apply, a.people_dir)
    verb = "updated" if a.apply else "would update"
    print(f"{res['rows']} rows; {verb} {len(res['updated'])}, unchanged {len(res['unchanged'])}")
    for k in ("updated", "no_person_file", "no_marker"):
        if res[k]:
            print(f"  {k}: {', '.join(res[k])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
