#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Normalize project_*.md status frontmatter onto the canonical vocabulary. A file
#   with no status is invisible to every sweep pathway — it can neither close nor go
#   dormant — so it sits open forever without appearing anywhere."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: your-agent
# ---
"""normalize_workstream_status.py — put every T2 workstream on the canonical vocabulary.

Found 2026-07-30, immediately after dormancy shipped: 66 of the corpus's project_*.md
files carried a status outside the canonical set — 62 had NO status field at all, plus
one-off `done` / `complete` / `closed` / `current`. Every one was invisible to both sweep
pathways, because both begin by testing membership in OPEN_STATUSES. They could not be
closed, could not go dormant, and did not appear in any count.

The cost was not theoretical: project_v2-contract-billing-grain-and-rates was ACTIVE work
("DESIGN in-flight (SOT-3)", touched 6 days prior) that no report could see.

This is the same defect dormancy just fixed, one level down — an item the system declines
to look at is indistinguishable from an item that does not exist.

Mapping:
  done / complete / closed  -> archived   (the file itself claims completion)
  current                   -> archived   (a stale pointer doc, not open work)
  (no status), recently touched -> in-flight   (real open work; needs a human read)
  (no status), older than --age-days -> dormant  (we stopped; the honest claim)

Statusless old files become `dormant`, NOT `archived`. Archived asserts the work finished,
which we cannot know for a pre-convention file. Dormant asserts only that we stopped —
which is exactly what the evidence supports, and it is revivable by a single edit.
"""
import argparse, datetime, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import memory_dir  # noqa: E402

MEM = memory_dir()
CANONICAL = {"in-flight", "handed-off", "follow-on", "archived", "dormant", "backlog"}
TO_ARCHIVED = {"done", "complete", "closed", "current", "shipped", "finished"}


def read_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return (m.group(1) if m else ""), m


def field(fm, key):
    m = re.search(rf"^\s*{key}:\s*(.+)$", fm, re.M)
    if not m:
        return ""
    return re.sub(r"\s+#.*$", "", m.group(1).strip().strip("\"'"))


def set_field(text, key, value):
    if re.search(rf"^\s*{key}:.*$", text, re.M):
        return re.sub(rf"^(\s*){key}:.*$", rf"\1{key}: {value}", text, count=1, flags=re.M)
    return text.replace("---\n", f"---\n{key}: {value}\n", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--age-days", type=int, default=20)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    today = datetime.date.fromisoformat(args.today)

    plan = []
    for p in sorted(MEM.glob("project_*.md")):
        text = p.read_text()
        fm, m = read_fm(text)
        if not m:
            plan.append({"name": p.stem, "from": "(no frontmatter)", "to": None,
                         "why": "cannot normalize safely — needs a human"})
            continue
        st = field(fm, "status").lower()
        if st in CANONICAL:
            continue
        lt = field(fm, "last_touched") or field(fm, "last_updated") or field(fm, "created")
        age = None
        if re.match(r"\d{4}-\d{2}-\d{2}", lt):
            age = (today - datetime.date.fromisoformat(lt[:10])).days
        if st == "current":
            # Not a completion claim — a pointer doc that called itself "current" and then
            # went stale. Archived because it is not open WORK; the content stays fully
            # discoverable through the memory index.
            to, why = "archived", f"stale pointer doc self-labelled 'current' ({age}d old)"
        elif st in TO_ARCHIVED:
            to, why = "archived", f"'{st}' is a completion claim in the file itself"
        elif age is None:
            to, why = None, "no status and no date — needs a human"
        elif age < args.age_days:
            to, why = "in-flight", f"statusless but touched {age}d ago — real open work"
        else:
            to, why = "dormant", f"statusless, untouched {age}d — we stopped"
        plan.append({"name": p.stem, "from": st or "(none)", "to": to, "why": why,
                     "age_days": age})

    for item in plan:
        if not (args.apply and item["to"]):
            continue
        p = MEM / f"{item['name']}.md"
        t = set_field(p.read_text(), "status", item["to"])
        if item["to"] == "dormant":
            # Same rule as the sweep: do NOT stamp last_touched. Revival compares
            # last_touched against dormant_since, so equal dates would mean no later
            # edit could ever look newer and touch-to-revive would never fire.
            if not re.search(r"^\s*dormant_since:", t, re.M):
                t = re.sub(r"^(\s*status: dormant)$", rf"\1\ndormant_since: {args.today}",
                           t, count=1, flags=re.M)
            t = re.sub(r"^\s*cs_(section|headline):.*\n", "", t, flags=re.M)
            note = (f"\n## Dormant {args.today}\n\nNormalized from a missing status field "
                    f"({item['age_days']} days untouched). Not finished and not queued — "
                    "moved on from. Edit this file and the next sweep returns it to "
                    "in-flight automatically.\n")
            if f"## Dormant {args.today}" not in t:
                t = t.rstrip() + "\n" + note
        elif item["to"] == "archived":
            t = re.sub(r"^\s*cs_(section|headline):.*\n", "", t, flags=re.M)
        p.write_text(t)

    counts = {}
    for i in plan:
        counts[i["to"] or "NEEDS-HUMAN"] = counts.get(i["to"] or "NEEDS-HUMAN", 0) + 1
    print(json.dumps({"mode": "apply" if args.apply else "report",
                      "total": len(plan), "by_target": counts, "plan": plan}, indent=2))


if __name__ == "__main__":
    main()
