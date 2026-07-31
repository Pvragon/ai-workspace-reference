#!/usr/bin/env python3
"""regen_current_state.py — the SINGLE writer of current-state.md.

Concurrency fix: the three workstream sections (In Flight / Just Handed Off /
Known Follow-Ons) are a DETERMINISTIC render of per-workstream flags stored on the
T2 files themselves:

    cs_section: in_flight | handed_off | follow_on   # presence => shown in current-state
    cs_headline: "<bold name> — <1-line status>"     # the line text (link is derived)

Because membership + text live on the T2 files (per-workstream, rarely contended),
any session that regenerates produces IDENTICAL bytes for those sections — so two
concurrent debriefs can't clobber each other. Items whose status is archived/backlog
are excluded even if a stale flag lingers.

Blockers / Recent Decisions / Notes are narrative (not derivable) — preserved
verbatim, with optional --add-decision / --add-note / --clear-notes mutating them
in-place. All writes go through this script under an flock + atomic rename, so it is
the ONE writer. Subagent B sets T2 flags then calls this; it never edits the file.

IDEMPOTENT (2026-07-30): --add-decision / --add-note are no-ops when the exact line
is already present. Callers do NOT need to check first — and MUST NOT be asked to,
because they cannot do it correctly: a caller's point-in-time grep cannot see a
concurrent writer that commits between its check and its write, which is exactly how
both decisions and both notes duplicated during the 2026-07-30 debrief. The check
belongs here, inside the flock, after the file is re-read from disk. Same guarantee
`sweep_workstreams.py` already gives its `## Archived <date>` note appends.

The In Flight cap is likewise enforced here rather than asked of the caller, and
overflow is reported rather than silently dropped.
"""
import argparse, os, re, sys, fcntl, datetime, pathlib, tempfile
import sys
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

MEM = memory_dir()
CS = MEM / "current-state.md"
LOCK = MEM / ".current-state.lock"
OPEN_STATUSES = {"in-flight", "handed-off", "follow-on"}
IN_FLIGHT_CAP = 5
SECTIONS = [
    ("in_flight",  "## In Flight  <!-- max 5 items -->"),
    ("handed_off", "## Just Handed Off  <!-- ball in someone else's court -->"),
    ("follow_on",  "## Known Follow-Ons  <!-- no external trigger; cleanup queued -->"),
]
PREAMBLE = (
    "# Current State\n\n"
    "> **Format rule:** Thin INDEX over T2 project files (`memory/project_*.md`). Each\n"
    "> item is a 1-line pointer. State lives in the T2 file's frontmatter\n"
    "> (status / last_touched / resolves_when / resume_via) and body. The three\n"
    "> workstream sections below are AUTO-RENDERED from each T2's `cs_section` /\n"
    "> `cs_headline` by `executions/regen_current_state.py` — do not hand-edit them.\n"
)

def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    def sc(v):
        """Scalar-clean a frontmatter value.

        A quoted value is taken verbatim — `#` inside quotes is DATA, not a YAML
        comment. Only unquoted values get trailing-comment stripping. Doing the
        comment strip first (the old behaviour) silently truncated any headline
        containing a PR/issue reference, e.g. `why #1882 was written` rendered as
        `why` with no warning. See backlog/bug-regen-current-state-hash-truncation.md.
        """
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            return v[1:-1]
        return re.sub(r"\s+#.*$", "", v).strip()
    for line in m.group(1).splitlines():
        # accept keys at any indent so nested `metadata:` blocks are read too; first wins
        mm = re.match(r"^\s*(\w[\w_]*):\s*(.*)$", line)
        if mm and mm.group(1) not in fm:
            fm[mm.group(1)] = sc(mm.group(2))
    return fm

def split_sections(text):
    """Return (preamble_lines, {header: body}) preserving order-agnostic access."""
    lines = text.splitlines()
    # keep the <!-- Last updated --> line + blank as top matter, drop old preamble/# title
    sections, cur_header, cur_body = {}, None, []
    order = []
    for ln in lines:
        if ln.startswith("## "):
            if cur_header is not None:
                sections[cur_header] = cur_body
            cur_header = ln; cur_body = []; order.append(ln)
        elif cur_header is not None:
            cur_body.append(ln)
    if cur_header is not None:
        sections[cur_header] = cur_body
    return sections, order

def find_section(sections, prefix):
    for h, body in sections.items():
        if h.startswith(prefix):
            return h, body
    return None, None

def render_workstreams(today):
    buckets = {k: [] for k, _ in SECTIONS}
    # project_*.md are the common case; reference_*.md may also carry cs_section
    # when a reference doc doubles as a workstream pointer (e.g. a handed-off
    # build). Only files that actually set cs_section show up either way.
    candidates = sorted(MEM.glob("project_*.md")) + sorted(MEM.glob("reference_*.md"))
    for p in candidates:
        fm = parse_fm(p.read_text())
        sect = (fm.get("cs_section") or "").strip()
        if sect not in buckets:
            continue
        if (fm.get("status") or "").strip() not in OPEN_STATUSES:
            continue  # stale flag on an archived/backlog item -> exclude
        headline = (fm.get("cs_headline") or f"**{p.stem.split('_', 1)[-1]}**").strip()
        lt = fm.get("last_touched", "0000-00-00")
        buckets[sect].append((lt, p.stem, headline))
    out = {}
    for key, header in SECTIONS:
        items = sorted(buckets[key], key=lambda t: (t[0], t[1]), reverse=True)  # freshest first, stable
        overflow = []
        if key == "in_flight" and len(items) > IN_FLIGHT_CAP:
            items, overflow = items[:IN_FLIGHT_CAP], items[IN_FLIGHT_CAP:]
        lines = [f"- {h} → [[{name}]]" for _lt, name, h in items] or ["_None._"]
        if overflow:
            # Enforce the cap, but NEVER silently — a hidden truncation reads as
            # "these are all the live items" when it isn't. Name what was cut.
            names = ", ".join(f"[[{name}]]" for _lt, name, _h in overflow)
            lines.append(
                f"- _{len(overflow)} over the cap of {IN_FLIGHT_CAP}, not shown "
                f"(stalest `last_touched`): {names}. Demote or re-flag them._"
            )
        out[header] = lines
    return out

def prune_decisions(body_lines, today, cap=10):
    cutoff = today - datetime.timedelta(days=14)
    kept, undated = [], []
    for ln in body_lines:
        m = re.match(r"^- (\d{4}-\d{2}-\d{2}):", ln)
        if m:
            d = datetime.date.fromisoformat(m.group(1))
            if d >= cutoff:
                kept.append((d, ln))
        elif ln.strip() and ln.strip() != "_None._":
            undated.append(ln.strip())
    if undated:
        # A decision without a `YYYY-MM-DD:` prefix used to be collected here and then
        # dropped on the floor while the script still printed success — the caller lost
        # the decision and was told everything worked. Age-pruning (>14d) is intended and
        # stays silent; this is data loss and must not be.
        print(f"WARNING: dropped {len(undated)} undated line(s) from Recent Decisions — a "
              "decision must start with 'YYYY-MM-DD: ' to survive pruning:", file=sys.stderr)
        for u in undated:
            print(f"  dropped: {u}", file=sys.stderr)
    kept.sort(key=lambda t: t[0], reverse=True)
    if len(kept) > cap:
        # Same rule as the In Flight cap: enforce it, but never silently. Observed
        # 2026-07-30 — two decisions logged THAT SESSION were evicted here with no
        # signal, because same-day entries sort equal and the tail is simply sliced.
        # The state is recoverable (decisions live on in their T2 files) but the
        # operator has no way to know an eviction happened.
        for _d, ln in kept[cap:]:
            print(f"  evicted (over cap {cap}): {ln.strip()}", file=sys.stderr)
        print(f"WARNING: Recent Decisions over cap — {len(kept) - cap} entry(ies) evicted, "
              "listed above. Same-day entries sort equal, so a busy day can push out a "
              "decision logged this session.", file=sys.stderr)
    return [ln for _d, ln in kept[:cap]]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--add-decision", action="append", default=[])
    ap.add_argument("--add-note", action="append", default=[])
    ap.add_argument("--clear-notes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    today = datetime.date.fromisoformat(args.today)

    LOCK.touch(exist_ok=True)
    lock_fh = open(LOCK, "w")
    fcntl.flock(lock_fh, fcntl.LOCK_EX)          # serialize all writers
    try:
        existing = CS.read_text() if CS.exists() else ""
        sections, _order = split_sections(existing)
        ws = render_workstreams(args.today)

        # --- narrative sections (preserve + optional mutate) ---
        _, blk = find_section(sections, "## Blockers")
        blockers_body = blk if blk is not None else ["", "_None._", ""]

        dh, dec = find_section(sections, "## Recent Decisions")
        dec_body = dec[:] if dec is not None else []
        for d in args.add_decision:
            line = f"- {d}" if not d.startswith("- ") else d
            if line.strip() not in {l.strip() for l in dec_body}:
                dec_body.insert(0, line)
        dec_body = ["", *prune_decisions(dec_body, today), ""]

        nh, notes = find_section(sections, "## Notes for Next Session")
        notes_lines = [] if (args.clear_notes or notes is None) else [l for l in notes if l.strip() and l.strip() != "_None._"]
        for n in args.add_note:
            line = f"- {n}" if not n.startswith("- ") else n
            if line.strip() not in {l.strip() for l in notes_lines}:
                notes_lines.append(line)
        notes_body = ["", *(notes_lines or ["_None._"]), ""]

        # --- assemble ---
        parts = [f"<!-- Last updated: {args.today} -->", "", *PREAMBLE.splitlines(), ""]
        for _key, header in SECTIONS:
            parts += [header, "", *ws[header], ""]
        parts += ["## Blockers  <!-- on In Flight items only -->", *blockers_body]
        parts += ["## Recent Decisions  <!-- cap ~10, prune >14d -->", *dec_body]
        parts += ["## Notes for Next Session  <!-- 1-3 items -->", *notes_body]
        rendered = "\n".join(parts).rstrip() + "\n"

        if args.dry_run:
            sys.stdout.write(rendered); return
        # atomic write in same dir
        fd, tmp = tempfile.mkstemp(dir=str(MEM), prefix=".cs.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(rendered)
        os.replace(tmp, CS)
        # Count real items only. The over-cap notice is also a "- " bullet, so a bare
        # startswith('- ') would report one more workstream than exist — a count that
        # lies in exactly the situation you most want to trust it.
        n_items = sum(1 for _k, h in SECTIONS for l in ws[h] if l.startswith("- ") and " → [[" in l)
        print(f"current-state.md regenerated ({n_items} workstream items)")
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN); lock_fh.close()

if __name__ == "__main__":
    main()
