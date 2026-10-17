#!/usr/bin/env python3
# ---
# template: execution
# version: 2.1.3
# summary: "PreToolUse hook for the two-strength memory model. On a read or edit of a T2 topic file it refreshes last_accessed hourly, and counts a spaced reinforcement (access_count +1, stability x1.6) only after 20h, so cramming cannot inflate storage strength. Writes nothing when no gate is due. Flock-serialized, atomic, always exits 0."
# ---
# v2.1.0 (2026-07-29): CURATION now reinforces. The hook fired on Read only, so
#   every Edit/Write to a topic file — the session-debrief append, a correction,
#   an extension — reinforced nothing, despite being a stronger relevance signal
#   than a read. Matcher widened to Read|Edit|Write|MultiEdit in settings.json.
#   Deliberately still excluded: MEMORY.md Hot-table auto-load (would make Hot
#   self-perpetuating) and Grep/Glob hits (fragments, not a retrieval decision).
"""
update_memory_access.py — reinforce a memory topic file's strength when it is Read.

Two-strength model (Bjork & Bjork 1992, "New Theory of Disuse"):
  - RETRIEVAL strength = how accessible right now. Decays with time. Here it is
    exp(-days_since_last_accessed / stability), computed at rank time.
  - STORAGE strength   = how well-learned. ~Monotonic, never decays. Here it is
    carried by `stability` (the decay time-constant) + `access_count`.

Frontmatter fields maintained (all inserted top-level if missing):
  access_count    int    # spaced reinforcements (NOT raw read count)
  last_accessed   ISO-Z  # every read refreshes this (recency signal)
  last_reinforced ISO-Z  # last read that counted as a spaced reinforcement
  stability       float  # days; decay time-constant. grows on spaced reads.

Spacing rule (the fix over v1): a read only counts as a reinforcement when it is
>= SPACING_GAP_HOURS after the previous reinforcement. Massed same-day re-reads
refresh recency but do NOT bump access_count or stability — matching the
empirical finding that spaced practice, not cramming, builds durable memory.

Stability growth: stability = min(stability * STABILITY_GROWTH, STABILITY_CAP).
Starting at BASE_STABILITY, ~7 spaced reinforcements reach the cap. So an
untouched-after-one-read file decays with a ~2-week constant (cold in ~2 weeks),
while a 7x-spaced-reinforced file decays with a ~1-year constant (stays warm ~a
year). That difference is the whole point.

Hook contract (stdin JSON): {"tool_name":"Read","tool_input":{"file_path":...}}
Only fires for files whose realpath is directly inside the CANONICAL memory dir
(resolved by agent_paths); a ~/.claude symlink alias resolves
there too. MEMORY.md, backups, current-state.md, and subdirs (short-term/) are
ignored. flock on memory/.access-lock; atomic tmp+rename; ALWAYS exit 0.

Test:
  echo '{"tool_name":"Read","tool_input":{"file_path":"<memory file>"}}' \
    | python3 update_memory_access.py
"""

import datetime
import fcntl
import json
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

# MEMORY_DIR is resolved lazily inside main(), never at import: this module is a
# PreToolUse hook and an import-time raise would block the tool call it hooks.

BASE_STABILITY = 14.0        # days; time-constant for a never-reinforced memory
STABILITY_GROWTH = 1.6       # multiplier per spaced reinforcement
STABILITY_CAP = 365.0        # days; ceiling on the bridge (Graphiti era can raise)
SPACING_GAP_HOURS = 20.0     # a reinforcement only counts if this long since the last
RECENCY_RESOLUTION_MIN = 60.0  # don't rewrite last_accessed more often than this (see bump())

# Tools whose use on a topic file counts as a retrieval/rehearsal event.
# Read = retrieval. Edit/Write/MultiEdit = CURATION, which is a stronger relevance
# signal than a read (you went and corrected/extended the memory) and was silently
# uncounted until 2026-07-29 — every session-debrief write reinforced nothing.
# NOT included by design:
#   - the MEMORY.md Hot-table auto-load: reinforcing on auto-load would make Hot
#     self-perpetuating (rich-get-richer) so nothing could ever be displaced.
#   - Grep/Glob hits: those return fragments, not a decision to retrieve the file.
REINFORCING_TOOLS = ("Read", "Edit", "Write", "MultiEdit")


def _parse_iso(val: str):
    val = (val or "").strip().strip('"')
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(val, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _set_field(fm: str, key: str, value: str) -> str:
    """Replace a top-level `key:` line in the frontmatter body, or append it."""
    m = re.search(rf"^{key}:\s*.*$", fm, re.M)
    if m:
        return fm[:m.start()] + f"{key}: {value}" + fm[m.end():]
    return fm + f"{key}: {value}\n"


def bump(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return
    end = text.find("\n---", 4)
    if end == -1:
        return
    fm = text[4:end + 1]
    rest = text[end + 1:]

    now = datetime.datetime.now(datetime.timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    m = re.search(r"^access_count:\s*(\d+)", fm, re.M)
    count = int(m.group(1)) if m else 0

    m = re.search(r"^stability:\s*([0-9.]+)", fm, re.M)
    stability = float(m.group(1)) if m else BASE_STABILITY

    m = re.search(r"^last_reinforced:\s*(.+)$", fm, re.M)
    last_reinf = _parse_iso(m.group(1)) if m else None

    m = re.search(r"^last_accessed:\s*(.+)$", fm, re.M)
    last_acc = _parse_iso(m.group(1)) if m else None

    # Spaced-reinforcement gate.
    spaced = last_reinf is None or (now - last_reinf).total_seconds() >= SPACING_GAP_HOURS * 3600
    if spaced:
        count += 1
        stability = min(stability * STABILITY_GROWTH, STABILITY_CAP)
        fm = _set_field(fm, "access_count", str(count))
        fm = _set_field(fm, "stability", f"{stability:.1f}")
        fm = _set_field(fm, "last_reinforced", now_s)

    # Recency refreshes, but only at the resolution the score actually uses.
    #
    # This used to write unconditionally, which made EVERY Read of a topic file rewrite that
    # file. The harness tracks file state to protect edits, so the agent's own Read would
    # trip its own subsequent Edit with "content changed since last read" — no other writer
    # involved. Measured 2026-08-19: 3 occurrences across 3 different agents in one day, and
    # the workaround being adopted was to bypass Edit entirely with a Python write via Bash,
    # which loses the staleness protection everywhere it is used.
    #
    # The write bought nothing at that frequency. `last_accessed` feeds
    # exp(-days_since / stability), a quantity in DAYS, against stability >= 14 days. Holding
    # it to RECENCY_RESOLUTION_MIN costs at most ~0.3% of one file's retrieval strength, and
    # never changes a band. Below the threshold the hook now writes nothing at all, so a
    # read-then-edit cycle inside one session no longer touches the file.
    stale = last_acc is None or \
        (now - last_acc).total_seconds() >= RECENCY_RESOLUTION_MIN * 60
    if not (spaced or stale):
        return                      # nothing to write — leave the file untouched
    if stale:
        fm = _set_field(fm, "last_accessed", now_s)

    new_text = "---\n" + fm + rest
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".access-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") not in REINFORCING_TOOLS:
            return 0
        file_path = (payload.get("tool_input") or {}).get("file_path")
        if not file_path:
            return 0
        real = Path(file_path).expanduser().resolve()
        if real.parent != memory_dir().resolve():  # directly in memory/ only (skips short-term/ etc.)
            return 0
        if not real.name.startswith(TOPIC_PREFIXES) or not real.name.endswith(".md"):
            return 0
        with open(memory_dir() / ".access-lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            bump(real)
    except BaseException:
        pass  # never block the Read
    return 0


if __name__ == "__main__":
    sys.exit(main())
