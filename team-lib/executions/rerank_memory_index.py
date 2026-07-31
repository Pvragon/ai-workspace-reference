#!/usr/bin/env python3
# ---
# template: execution
# version: 2.1.0
# summary: "Memory reranker (two-strength model) — walks all T2 memory topic files, computes score = (access_count+1) * exp(-days_since_last_access / stability), and regenerates MEMORY.md as Hot (auto-loaded, ~3K-token budget, pin:true always included) + New (born within GRACE_DAYS, ordered newest-first) + Cold (one Read away). stability is the per-file adaptive decay time-constant maintained by update_memory_access.py (grows with spaced reinforcement; defaults to 14d). v2.1.0 adds the New band: a brand-new memory scored 1.00 and ranked ~#125 of 612 against ~49 visible slots, so it was born straight into the archive — never indexed, never read, never reinforced, which is a loop the design cannot close. Preserves hand-curated row summaries; superseded files forced to archive. Last step of session-debrief. flock-serialized against the Read hook."
# created: 2026-07-12
# last_updated: 2026-07-30
# maintainer: the-operator
# ---
"""
rerank_memory_index.py — regenerate MEMORY.md with frequency-weighted Hot/Cold tiers.

Score (two-strength model, pre-Graphiti bridge):
    score = (access_count + 1) * exp(-days_since_last_access / stability)

  - (access_count + 1)  ~ STORAGE strength (monotonic, never decays).
  - exp(-days / stability) ~ RETRIEVAL strength (decays with time).
  - `stability` is the adaptive decay time-constant (days). It grows with spaced
    reinforcement (update_memory_access.py) and never decays, so a well-rehearsed
    memory decays slowly (stays Hot longer) while a cram-read one decays fast.
    Default STABILITY_DEFAULT=14 when absent.
  - access_count / last_accessed / stability come from file frontmatter; when
    absent, defaults are access_count=0, last_accessed=file mtime (never "now" —
    preserves real recency on day 1), stability=14.
  - pin: true          -> always Hot, regardless of score.
  - status: superseded* -> always archived (content now lives in a T3/T4 surface).

Birth grace (v2.1.0):
    A newly written memory has access_count=0 and last_accessed=now, so it scores
    exactly 1.00 — which on the live corpus ranked ~#125 of 612 against ~49
    visible slots. It was therefore born into the archive: never indexed, so
    never seen, so never read, so never reinforced, so decaying from 1.00
    downward. "The reinforcement loop closes through retrieval" assumes the
    memory is retrievable to begin with; for a newborn it never was.

    Files with `created:` within GRACE_DAYS get a reserved band, ordered
    newest-first (every newborn scores ~1.00, so score order among them would be
    filename order — i.e. arbitrary). Keyed on `created:` only: mtime is
    last-touch, not birth, because update_memory_access.py rewrites frontmatter
    on every touch. No `created:` -> not a newborn (fail closed).

Hot budget: HOT_CHAR_BUDGET chars of row text (~3K tokens) so cold-start cost
stays predictable inside the ~24 KB auto-load window.

Row text comes from the file's own `summary:` frontmatter, falling back to
`description:`. The index is therefore a PURE FUNCTION of the corpus — it does
not read its own previous output, and hand-edits to MEMORY.md are discarded.
Rows whose file no longer exists are kept from the archive with a ⚠ marker
(never delete); that is a tombstone, not curation.

Usage:
  python3 rerank_memory_index.py            # regenerate in place
  python3 rerank_memory_index.py --dry-run  # print tier stats only
"""

import argparse
import datetime
import fcntl
import math
import os
import re
import sys
import tempfile
from pathlib import Path

# --- portable path resolution (team-lib) -------------------------------------
# Scripts here are invoked by absolute path from hooks and cron, so the sibling
# module is not importable from cwd. Add our own directory to sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    memory_dir, meditations_dir, lenses_dir, journal_dir, shortterm_dir,
    state_dir, exec_dir, backlog_dir, agent_home, workspace, TOPIC_PREFIXES,
)
# -----------------------------------------------------------------------------

MEMORY_DIR = memory_dir().resolve()
MEMORY_MD = MEMORY_DIR / "MEMORY.md"
LOCK_FILE = MEMORY_DIR / ".access-lock"
STABILITY_DEFAULT = 14.0  # days; time-constant when a file has no `stability` field yet
IMPORTANCE_WEIGHT = 0.6   # points added to score per importance unit (0-10 scale)
HOT_CHAR_BUDGET = 12000  # ~3K tokens of row text
COLD_CHAR_BUDGET = 4000  # active Cold index cap; lower-relevance overflow rolls to MEMORY-archive.md
# (kept small so HOT(12K)+COLD+prose stays under the ~24.4KB auto-load READ limit — else
#  tail entries silently drop from the loaded index. Cold is one-Read-away; archive holds the rest.)
GRACE_DAYS = 14.0        # a memory younger than this is visible on birth, before it has earned a rank
NEWBORN_CHAR_BUDGET = 2500  # reserved slots for newborns, so the long tail cannot crowd them out
NEWBORN_SUMMARY_CHARS = 160  # newborn rows are triage ("worth opening?"), not the full summary.
# Doubles the band (6 -> ~13 of 62 eligible; ~1.2 -> ~2.5 days of real visibility). Safe ONLY
# because the index no longer reads its own output: the full summary lives in the file, so a
# truncated row can never be harvested back as the canonical text. If summary carry-forward is
# ever reintroduced, turn this off in the same change.
# (ADDED to the auto-load total rather than carved out of Cold — measured headroom was 5,846 bytes
#  against the ~24.4KB limit, so 2.5K fits with ~3.3KB to spare. Recheck if HOT/COLD grow.)
MEMORY_ARCHIVE = MEMORY_DIR / "MEMORY-archive.md"

HEADER = """# Memory Index

This file is auto-loaded on cold-start; only the **Hot** section is guaranteed inside the auto-load window. **New** holds memories born in the last 14 days — they have not earned a rank yet and are shown so they can be read at all. **Cold** entries are one `Read` away — reading a file reinforces it (bumps its score, grows its stability) and the next rerank may promote it. Lower-relevance entries beyond the Cold budget **roll off to `MEMORY-archive.md`** (a full catalog, one `Read` away) — the topic files are never deleted, only their index visibility shifts. Ranking (two-strength model): `(access_count + 1) * exp(-days_since_last_access / stability) + 0.6 * importance`, where `stability` grows with spaced reinforcement and `importance` (0-10, default 0) is a non-decaying floor for critical memories. Maintained by `executions/rerank_memory_index.py`.
"""

ARCHIVE_HEADER = """# Memory Archive (rolled-off index)

Deep catalog of lower-relevance T2 topic memories that rolled off the active
`MEMORY.md` Cold budget. **Nothing here is deleted** — these files live on disk and
are one `Read` away; reading one bumps its score and the next rerank may re-promote it
back into `MEMORY.md`. Regenerated by `executions/rerank_memory_index.py` (do not hand-edit).
Ranked by the same two-strength score as MEMORY.md.
"""

HOW_TO_USE = """## How to Use

1. **Cold-start (in order):**
   1. Read `current-state.md` — what's happening *now*.
   2. Read the most recent **dream-journal residue** — `dream_journal.py recent --n 2` then read those files. This is the experiential trace the last reflective wake (a meditation) left for you — not facts, but what shifted / stayed open. It's how continuity thickens across the session gap.
   3. Glob `short-term/*.md` for the last 7 days. Two flavors per date: `YYMMDD-facts.md` (distilled T1 episodic) and `YYMMDD-residue.md` (texture/pickup-state). Read the most recent of each unconditionally; older within 7 days if cued.
   4. Scan the **Hot** table for relevant T2 topic files; open only what your task needs. Then scan **New** — those were written in the last 14 days and have not been read yet, so nothing about their position tells you whether they matter.
   5. If a topic isn't in Hot, grep the **Cold** table (or the memory dir) — cold entries are NOT gone, just one explicit `Read` away. Reading bumps the score; the next rerank may re-promote.
   6. If the user signals 'pick up where we left off', also pull the most recent extracted transcript from the agent's `transcripts/` directory, or fall back to the raw session log.
2. **Adding knowledge**: Append to the appropriate existing topic file (T2). If no topic fits, create a new one and give it a `summary:` in its frontmatter — that is the text shown here, and the next rerank picks it up automatically. **Do not hand-edit rows in this file.** It is regenerated from the corpus, so an edit here is discarded on the next run; edit the memory file's `summary:` instead. A memory written today appears under **New** regardless of score.
3. **Current-state.md** is special — it tracks what's happening *now*. The session-debrief skill maintains it.
4. **T1 vs T2 vs T3 vs T4:** see `project_memory-architecture-layers.md` for the 5-tier memory model. Rows tagged **[SUPERSEDED→…]** were promoted to a T3 lens / T4 surface (Move 3) and are pinned Cold.
"""


FM_KEYS = ("access_count", "last_accessed", "stability", "importance", "pin", "status",
           "description", "summary", "created")


def _read_scalar(lines, i):
    """Read the YAML scalar starting on lines[i] (already past 'key:'). -> (value, next_i).

    Deliberately a minimal reader, not a YAML parser: 24 files in the live corpus fail
    strict YAML, and this must degrade rather than refuse them. It handles the four
    shapes that actually occur — plain, quoted, quoted-spanning-lines, and block
    scalars.

    A previous regex took only the FIRST line of a value. That was invisible while the
    index carried the summary, because frontmatter was merely a fallback. The moment
    the file becomes the source of truth, first-line-only silently truncates every
    multi-line summary — 216 files already have one.
    """
    head = lines[i].split(":", 1)[1].strip()

    # Block scalar: `>`/`|` with optional chomping indicator. Value is the following
    # more-indented lines; folded joins with spaces, literal keeps newlines.
    if head[:1] in (">", "|"):
        fold = head[0] == ">"
        body, j = [], i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t")):
            body.append(lines[j].strip())
            j += 1
        return ((" " if fold else "\n").join(x for x in body if x), j)

    quote = head[:1]
    if quote in ('"', "'"):
        buf = head[1:]
        # Closing quote on the same line? (an escaped \" does not close a "-scalar)
        if _closes(buf, quote):
            return _unescape(_upto_close(buf, quote), quote), i + 1
        j = i + 1
        while j < len(lines):
            buf += " " + lines[j].strip()
            if _closes(lines[j].strip(), quote):
                break
            j += 1
        return _unescape(_upto_close(buf, quote), quote), j + 1

    return head, i + 1


def _closes(s: str, q: str) -> bool:
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\" and q == '"':
            esc = True
            continue
        if ch == q:
            return True
    return False


def _upto_close(s: str, q: str) -> str:
    esc, out = False, []
    for ch in s:
        if esc:
            out.append("\\" + ch)
            esc = False
            continue
        if ch == "\\" and q == '"':
            esc = True
            continue
        if ch == q:
            return "".join(out)
        out.append(ch)
    return "".join(out)


def _unescape(s: str, q: str) -> str:
    if q == "'":
        return s.replace("''", "'")
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def parse_frontmatter(text: str) -> dict:
    """Extract the fields we need, tolerating nested `metadata:` blocks (keys at any indent)."""
    out = {}
    if not text.startswith("---\n"):
        return out
    end = text.find("\n---", 4)
    if end == -1:
        return out
    lines = text[4:end + 1].split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*):", lines[i])
        if not m or m.group(1) not in FM_KEYS or m.group(1) in out:
            i += 1
            continue
        try:
            val, i = _read_scalar(lines, i)
        except (IndexError, ValueError):
            i += 1
            continue
        out[m.group(1)] = val.strip()
    return out


def parse_dt(val: str, fallback: float) -> float:
    """Return a UTC epoch for an ISO-ish timestamp string, else fallback."""
    val = (val or "").strip().strip('"')
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(val, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return fallback


def truncate(text: str, limit: int) -> str:
    """Shorten to `limit` chars on a word boundary. Table cells must stay single-line,
    so any embedded pipe is escaped — an unescaped one would split the row into a
    phantom column and corrupt the table."""
    text = text.replace("|", "\\|").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return (cut or text[:limit]) + "…"


def existing_rows(md_text: str) -> dict:
    """filename -> curated summary cell, from any table row in the current MEMORY.md."""
    rows = {}
    for m in re.finditer(r"^\| `([^`]+\.md)` \| (.+?) \|?\s*$", md_text, re.M):
        rows[m.group(1)] = m.group(2)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    # The index is a pure function of the corpus: summaries are read from each file's
    # `summary:` frontmatter, never carried forward from the previous MEMORY.md.
    #
    # Before, the summary text lived ONLY in the index, so every run had to read its own
    # prior output from BOTH MEMORY.md and MEMORY-archive.md and carry it forward. That
    # made the index stateful and gave it a destructive failure mode: harvest only
    # MEMORY.md and the curation of everything rolled off to the archive is silently
    # destroyed. It also weakened the concurrency guarantee, which only held if parallel
    # writers read the same prior output.
    #
    # Rows whose FILE NO LONGER EXISTS are the one legitimate use of prior output: the
    # corpus cannot supply text for a file that is gone, and "never delete" requires the
    # row survive. Harvested from both index files — a file deleted while it was Hot or
    # Cold has its only row in MEMORY.md. This is not summary carry-forward: tombstones
    # are consulted ONLY for names absent from disk, so no live file's summary can come
    # from here. (Regression caught by test_deleted_file_keeps_a_tombstone, which failed
    # when this read the archive alone.)
    old_md = MEMORY_MD.read_text(encoding="utf-8") if MEMORY_MD.exists() else ""
    old_arch = MEMORY_ARCHIVE.read_text(encoding="utf-8") if MEMORY_ARCHIVE.exists() else ""
    tombstones = existing_rows(old_arch)
    tombstones.update(existing_rows(old_md))

    entries = []
    seen_files = set()
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if not path.name.startswith(TOPIC_PREFIXES):
            continue
        seen_files.add(path.name)
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        count = int(fm.get("access_count", "0") or 0)
        last = parse_dt(fm.get("last_accessed", ""), path.stat().st_mtime)
        days = max(0.0, (now - last) / 86400.0)
        try:
            stability = float(fm.get("stability", STABILITY_DEFAULT) or STABILITY_DEFAULT)
        except ValueError:
            stability = STABILITY_DEFAULT
        stability = max(1.0, stability)  # guard against div-by-zero / bad values
        try:
            importance = float(fm.get("importance", 0) or 0)
        except ValueError:
            importance = 0.0
        importance = min(10.0, max(0.0, importance))
        score = (count + 1) * math.exp(-days / stability) + IMPORTANCE_WEIGHT * importance
        pinned = str(fm.get("pin", "")).lower().startswith("true")
        superseded = str(fm.get("status", "")).startswith("superseded")
        summary = fm.get("summary") or fm.get("description") or "(no summary — add one)"
        # Birth grace: a memory too new to have earned a rank is shown anyway, so it can be
        # read and reinforced. Keyed on `created:` ONLY — mtime is last-touch, not birth
        # (update_memory_access.py rewrites frontmatter on every touch), so a file with no
        # `created:` is treated as NOT newborn. Fail closed: the cost of missing a real
        # newborn is one lost grace window; the cost of a false one is evicting a real memory.
        created_ts = parse_dt(fm.get("created", ""), 0.0)
        born_days = (now - created_ts) / 86400.0 if created_ts else float("inf")
        entries.append({"file": path.name, "score": score, "pin": pinned,
                        "superseded": superseded, "summary": summary,
                        "born_days": born_days, "created_ts": created_ts})

    # Rows whose file vanished: keep, cold, marked (never delete).
    for fname, summary in tombstones.items():
        if fname not in seen_files and fname.startswith(TOPIC_PREFIXES):
            entries.append({"file": fname, "score": 0.0, "pin": False,
                            "superseded": False, "summary": "⚠ file missing — " + summary,
                            "born_days": float("inf"), "created_ts": 0.0})

    # Explicit secondary key on filename. Ties are the COMMON case here (most of the corpus
    # shares a base score), and the "parallel regenerations emit identical bytes" guarantee
    # rests on this being total. It held implicitly before — Python's sort is stable and the
    # input arrived filename-sorted from glob() — but that is a property of the caller, and a
    # refactor that reorders the input would have broken determinism silently.
    entries.sort(key=lambda e: (-e["score"], e["file"]))

    # Three tiers, score-ranked: Hot (auto-loaded) -> Cold (active, budget-capped)
    # -> archive (rolled off to MEMORY-archive.md). Pins are always Hot; superseded
    # rows roll straight to the archive (dead weight out of the active index).
    def row_of(e):
        return f"| `{e['file']}` | {e['summary']} |\n"

    hot, new, cold, archive = [], [], [], []
    used_hot = used_new = used_cold = 0

    # Pass 1 — superseded rows never occupy an active band.
    live = []
    for e in entries:
        (archive if e["superseded"] else live).append(e)

    # Pass 2 — Hot, by score. Pins always make it.
    rest = []
    for e in live:
        row = row_of(e)
        if e["pin"] or used_hot + len(row) <= HOT_CHAR_BUDGET:
            hot.append((e, row))
            used_hot += len(row)
        else:
            rest.append(e)

    # Pass 3 — New, by BIRTH not score. Every newborn scores ~1.00, so ranking them by
    # score would order them by filename, i.e. arbitrarily; newest-first is the only
    # ordering that means anything. A newborn already Hot on merit is not repeated here.
    newborns = [e for e in rest if e["born_days"] <= GRACE_DAYS]
    newborns.sort(key=lambda e: (-e["created_ts"], e["file"]))
    claimed = set()
    for e in newborns:
        row = f"| `{e['file']}` | {truncate(e['summary'], NEWBORN_SUMMARY_CHARS)} |\n"
        if used_new + len(row) <= NEWBORN_CHAR_BUDGET:
            new.append((e, row))
            used_new += len(row)
            claimed.add(e["file"])

    # Pass 4 — Cold, by score, from whatever the first three passes did not take.
    for e in rest:
        if e["file"] in claimed:
            continue
        row = row_of(e)
        if used_cold + len(row) <= COLD_CHAR_BUDGET:
            cold.append((e, row))
            used_cold += len(row)
        else:
            archive.append(e)

    # Re-sort: pass 1 put all superseded rows ahead of pass 4's overflow. Without this the
    # archive would reorder wholesale on this release for no semantic reason, burying the
    # real diff. Same key as the main sort, so the archive stays score-ranked as documented.
    archive.sort(key=lambda e: (-e["score"], e["file"]))
    archive = [(e, row_of(e)) for e in archive]

    if args.dry_run:
        print(f"entries: {len(entries)}  hot: {len(hot)} ({used_hot} chars)  "
              f"new: {len(new)} ({used_new} chars)  "
              f"cold: {len(cold)} ({used_cold} chars)  archive: {len(archive)}")
        for e, _ in hot[:15]:
            print(f"  HOT {e['score']:7.3f}  {'PIN ' if e['pin'] else '    '}{e['file']}")
        for e, _ in new:
            print(f"  NEW {e['born_days']:5.1f}d  {e['file']}")
        return 0

    parts = [HEADER, "\n## Hot (auto-loaded)\n\n| Topic File | Summary |\n|------------|---------|\n"]
    parts += [row for _, row in hot]
    parts += [f"\n## New (born within {int(GRACE_DAYS)} days — visible on birth, rank not yet earned)\n\n"
              "Newest first. These have not been read enough to compete on score; they are here so they "
              "*can* be. Reading one reinforces it, and it graduates to Hot/Cold on merit when its grace "
              "window closes.\n\n| Topic File | Summary |\n|------------|---------|\n"]
    parts += ([row for _, row in new] if new
              else ["| _(none — nothing written in the last "
                    f"{int(GRACE_DAYS)} days)_ | |\n"])
    parts += ["\n## Cold (one Read away — reading re-warms; overflow rolls to `MEMORY-archive.md`)\n\n| Topic File | Summary |\n|------------|---------|\n"]
    parts += [row for _, row in cold]
    parts += ["\n", HOW_TO_USE]
    new_md = "".join(parts)

    arch_parts = [ARCHIVE_HEADER, "\n| Topic File | Summary |\n|------------|---------|\n"]
    arch_parts += ([row for _, row in archive] if archive
                   else ["| _(none — every memory fits the active index)_ | |\n"])
    new_arch = "".join(arch_parts)

    with open(LOCK_FILE, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for target, content in ((MEMORY_MD, new_md), (MEMORY_ARCHIVE, new_arch)):
            fd, tmp = tempfile.mkstemp(dir=str(MEMORY_DIR), prefix=".memory-md-tmp-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, target)

    print(f"MEMORY.md regenerated: {len(hot)} hot ({used_hot} chars) / "
          f"{len(new)} new ({used_new} chars) / "
          f"{len(cold)} cold ({used_cold} chars) / {len(archive)} archived / {len(entries)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
