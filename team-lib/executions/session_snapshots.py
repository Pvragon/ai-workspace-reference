#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.0
# summary: "Snapshot the open Claude/tmux session fleet to a dated file, and rebuild it after a reboot. store: capture every live claude session (sessionId + cwd + tmux label) to ~/.claude/session-snapshots/YYMMDD-HHMM[-auto]-sessions.json. resume: for each stored session open one Windows-Terminal window that either RE-ATTACHES to the still-live tmux session (window-close, no reboot) or RESUMES it from disk (claude --resume <id> -n <name>) post-reboot — tmux label = the Claude session name. Backs /store-sessions and /resume-sessions. Builds on list_claude_sessions.py."
# created: 2026-06-23
# last_updated: 2026-07-24
# maintainer: your-agent
# usage: python3 session_snapshots.py {store|resume|list} [opts]
#   store  [--auto|--tag NAME] [--keep N]
#                                   write a snapshot of the current fleet. --auto (nightly cron) and
#                                   --tag NAME (e.g. 'debrief') each prune within their OWN bucket only,
#                                   so frequent debrief snapshots never evict the nightly ones.
#   list                            list available snapshots (newest first)
#   resume [DATE] [--dry-run] [--force] [--include-current]
#       DATE = latest (default) | YYMMDD (most recent that day) | a snapshot filename/path
#       --dry-run         print the per-window plan, open nothing
#       --force           allow resuming a snapshot with >15 sessions
#       --include-current resume even the session this command runs from (default: skip it)
# ---
"""
Store and resume the open Claude Code session fleet across a reboot.

WHY
---
Closing a Windows-Terminal window only DETACHES its tmux session (the server keeps
it + its claude alive). A real reboot / `wsl --shutdown` kills the tmux server and
every claude process — only the on-disk <sessionId>.jsonl survives. `store` records
the fleet while it's alive; `resume` rebuilds it afterward, choosing per session:

  * original tmux session still alive  -> RE-ATTACH (perfect live restore, no loss)
  * gone (post-reboot)                 -> `claude --resume <id> -n <name>` from disk

Each restored window is its own Windows-Terminal window (wt.exe), tmux session
labelled with the Claude session's name so the label finally matches the session.

Linux/WSL only. Needs tmux + wt.exe (Windows Terminal via WSL interop).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import list_claude_sessions as lcs  # noqa: E402

SNAP_DIR = Path.home() / ".claude" / "session-snapshots"
LAUNCH_DIR = SNAP_DIR / ".launch"
SESS_DIR = Path.home() / ".claude" / "sessions"        # <pid>.json: name + sessionId + cwd
PROJECTS_DIR = Path.home() / ".claude" / "projects"    # <slug>/<sessionId>.jsonl transcripts
MAX_WINDOWS_SOFT = 15  # require --force above this


# --- helpers -----------------------------------------------------------------

def _sanitize_label(name, sessionId):
    """tmux session label: derive from the Claude name; keep only [A-Za-z0-9_-]."""
    if name:
        lbl = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
        if lbl:
            return lbl[:80]
    return f"unnamed-{(sessionId or 'x')[:8]}"


def _safe_single(s):
    """Strip single quotes so a value is safe inside a single-quoted shell string."""
    return (s or "").replace("'", "")


def _snapshots():
    """All snapshot files, newest first (filenames sort chronologically)."""
    if not SNAP_DIR.is_dir():
        return []
    return sorted(SNAP_DIR.glob("*-sessions.json"), reverse=True)


def _resolve_snapshot(date):
    """date: None/'latest' -> newest; 'YYMMDD' -> newest that day; else a path/filename."""
    snaps = _snapshots()
    if date in (None, "latest", ""):
        return snaps[0] if snaps else None
    p = Path(date)
    if p.is_file():
        return p
    cand = SNAP_DIR / date
    if cand.is_file():
        return cand
    if re.fullmatch(r"\d{6}", date):  # YYMMDD
        day = [s for s in snaps if s.name.startswith(date + "-")]
        return day[0] if day else None
    return None


# --- store -------------------------------------------------------------------

def cmd_store(args):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    rows = lcs.run()
    # Capture genuinely-OPEN windows by default. ORPHAN/PHANTOM = windows you
    # already closed (the tmux session merely lingers detached); restoring those
    # would resurrect work you deliberately put away. --include-detached opts in.
    fleet = []
    skipped = 0
    for r in rows:
        if not r.get("sessionId"):
            continue
        if not args.include_detached and r.get("state") != "OPEN":
            skipped += 1
            continue
        fleet.append({
            "tmux": r["tmux"],                       # original launcher session (for re-attach)
            "label": _sanitize_label(r.get("name"), r["sessionId"]),
            "name": r.get("name"),                   # Claude display name (for -n on resume)
            "sessionId": r["sessionId"],
            "cwd": r.get("cwd"),
            "status": r.get("status"),
            "state": r.get("state"),
        })

    now = datetime.now()
    # --tag names an independent retention bucket: snapshots only ever prune
    # against others carrying the SAME tag. Without this, frequent debrief
    # snapshots would evict the nightly midnight ones (shared --keep window).
    kind = getattr(args, "tag", None) or ("auto" if args.auto else "manual")
    tag = "" if kind == "manual" else f"-{kind}"
    fname = f"{now.strftime('%y%m%d-%H%M')}{tag}-sessions.json"
    path = SNAP_DIR / fname
    payload = {
        "created": now.isoformat(timespec="seconds"),
        "kind": kind,
        "count": len(fleet),
        "sessions": fleet,
    }
    path.write_text(json.dumps(payload, indent=2))
    # convenience pointer to the newest snapshot
    latest = SNAP_DIR / "latest.json"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(path.name)
    except OSError:
        pass

    if tag:  # prune only within this tag's own bucket
        peers = sorted(SNAP_DIR.glob(f"*{tag}-sessions.json"), reverse=True)
        for old in peers[args.keep:]:
            try:
                old.unlink()
            except OSError:
                pass

    note = f"  (skipped {skipped} detached/closed; --include-detached to keep)" if skipped else ""
    print(f"Stored {len(fleet)} session(s) -> {path}{note}")
    for s in fleet:
        nm = s["name"] or "(unnamed)"
        print(f"  {s['label']:<46} {lcs._short_cwd(s['cwd']):<26} [{s['state']}] {s['sessionId'][:8]}")
    return 0


# --- list --------------------------------------------------------------------

def cmd_list(args):
    snaps = _snapshots()
    if not snaps:
        print(f"No snapshots in {SNAP_DIR}")
        return 0
    print(f"Snapshots in {SNAP_DIR} (newest first):")
    for s in snaps:
        try:
            d = json.loads(s.read_text())
            print(f"  {s.name:<34} {d.get('count','?')} session(s)  [{d.get('kind','?')}]  {d.get('created','')}")
        except (OSError, json.JSONDecodeError):
            print(f"  {s.name:<34} (unreadable)")
    return 0


# --- resume ------------------------------------------------------------------

def _inner_script(sess):
    """Generate the per-window bash launcher (reattach-or-resume, nvm-loaded)."""
    orig = _safe_single(sess["tmux"])
    label = _safe_single(sess["label"])
    cwd = _safe_single(sess.get("cwd") or "")
    sid = _safe_single(sess["sessionId"])
    name = _safe_single(sess.get("name") or "")
    name_flag = f" -n '{name}'" if name else ""
    return f"""#!/usr/bin/env bash
# Auto-generated by session_snapshots.py resume. Reattach if alive, else resume from disk.
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
for b in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$b" ] && PATH="$b:$PATH"; done
export PATH
# 1) original tmux session still alive (closed window, no reboot) -> rename to label + attach
if tmux has-session -t '{orig}' 2>/dev/null; then
  tmux rename-session -t '{orig}' '{label}' 2>/dev/null || true
  exec tmux attach -t '{label}'
fi
# 2) already restored under the label earlier in this run -> just attach (never double-resume)
if tmux has-session -t '{label}' 2>/dev/null; then
  exec tmux attach -t '{label}'
fi
# 3) gone -> resume the conversation from disk into a fresh, labelled tmux session
cd '{cwd}' 2>/dev/null || cd "$HOME"
exec tmux new-session -s '{label}' "claude --resume '{sid}'{name_flag}"
"""


def _ccusage_cache_files():
    """The /tmp files the statusline caches ccusage output in (shared per-UID, 60s TTL)."""
    uid = os.getuid()
    return [Path(f"/tmp/ccusage-5h-active.{uid}"), Path(f"/tmp/ccusage-7d-total.{uid}")]


def _cache_warm(files, max_age=55):
    now = time.time()
    return all(f.exists() and f.stat().st_size > 0 and (now - f.stat().st_mtime) < max_age
               for f in files)


def _launch(sess):
    inner = LAUNCH_DIR / f"resume-{sess['label']}.sh"
    inner.write_text(_inner_script(sess))
    inner.chmod(0o755)
    subprocess.Popen(["wt.exe", "-w", "new", "wsl.exe", "--", "bash", str(inner)])


def _session_records():
    """Newest ~/.claude/sessions/<pid>.json record per sessionId.

    Claude writes name + sessionId + cwd here for every *windowed* session. These
    files survive a reboot, which is what makes post-hoc reconcile possible — but
    they are keyed by PID, and PIDs restart low after every reboot, so an old
    record is eventually overwritten by an unrelated new session. Newest-mtime-wins
    per sessionId keeps the freshest truth. Headless/cron runs never appear here
    (no `-n` name, no record), which is exactly the filter we want.
    """
    best = {}
    for f in SESS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            mt = f.stat().st_mtime
        except (OSError, json.JSONDecodeError):
            continue
        sid, name = d.get("sessionId"), d.get("name")
        if not sid or not name:
            continue
        if sid not in best or mt > best[sid][0]:
            best[sid] = (mt, d)
    return {sid: d for sid, (_, d) in best.items()}


def _jsonl_mtime(session_id):
    """Last-write time of a session's transcript, across all project dirs."""
    newest = 0.0
    for p in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


_GEN_RE = re.compile(r"^(.*?)-(\d+)$")


def _generation(name):
    """Split a session name into (base, generation). '260717-one-Mahjong-5' -> (…, 5)."""
    m = _GEN_RE.match(name or "")
    return (m.group(1), int(m.group(2))) if m else (name or "", 0)


def _supersedes(name, known):
    """True if `known` already holds the same workstream at an equal-or-newer generation.

    /handoff rotates a workstream into a new numbered session and debriefs the old
    one, so BOTH transcripts get written the same day. Without this, reconcile
    resurrects every retired predecessor: on 2026-07-24 it dragged back
    one-Mahjong-1 and bid-context-8 alongside the live -5 and -9.
    """
    base, gen = _generation(name)
    if not base:
        return False
    for k in known:
        kbase, kgen = _generation(k)
        if kbase == base and kgen >= gen:
            return True
    return False


def _reconcile(fleet, created_iso):
    """Union the snapshot with sessions that appeared/advanced AFTER it was taken.

    A snapshot is authoritative about which windows were OPEN (a signal that does
    not survive on disk), but it goes stale the moment a workstream rotates
    generation via /handoff. The transcripts are the opposite: always current, but
    they record *activity*, never openness. Neither alone is right — on 2026-07-24
    the midnight snapshot was missing waystar -14 and mahjong-constituents -5,
    while a log-only rebuild would have dropped three open-but-idle windows the
    snapshot had. So: trust the snapshot for its own contents, and additively
    recover anything that has been written to since.
    """
    try:
        cutoff = datetime.fromisoformat(created_iso).timestamp()
    except (ValueError, TypeError):
        return fleet, []

    have = {s.get("sessionId") for s in fleet}
    names = {s.get("name") for s in fleet if s.get("name")}
    added = []
    # newest generation first, so an added -5 immediately suppresses a stale -4
    cands = sorted(_session_records().items(),
                   key=lambda kv: _generation(kv[1].get("name")), reverse=True)
    for sid, rec in cands:
        if sid in have or _jsonl_mtime(sid) <= cutoff:
            continue
        if _supersedes(rec.get("name"), names):
            continue
        names.add(rec.get("name"))
        added.append({
            "tmux": f"mylib-{sid[:8]}",   # placeholder; dead tmux -> resume-from-disk path
            "label": _sanitize_label(rec.get("name"), sid),
            "name": rec.get("name"),
            "sessionId": sid,
            "cwd": rec.get("cwd"),
            "status": rec.get("status"),
            "state": "RECONCILED",
        })
    return fleet + added, added


def cmd_resume(args):
    snap = _resolve_snapshot(args.date)
    if snap is None:
        print(f"No matching snapshot for '{args.date or 'latest'}' in {SNAP_DIR}", file=sys.stderr)
        return 2
    data = json.loads(snap.read_text())
    fleet = data.get("sessions", [])

    reconciled = []
    if not args.no_reconcile:
        fleet, reconciled = _reconcile(fleet, data.get("created", ""))

    # skip the session this command is running from, unless asked otherwise
    current_id = None
    if not args.include_current:
        for r in lcs.run():
            if r.get("is_current"):
                current_id = r.get("sessionId")
        fleet = [s for s in fleet if s["sessionId"] != current_id]

    print(f"Snapshot: {snap.name}  ({data.get('created','')}) — {len(fleet)} window(s) to open")
    if reconciled:
        print(f"  + {len(reconciled)} session(s) recovered from transcripts "
              f"(active after this snapshot; --no-reconcile to skip):")
        for s in reconciled:
            if s["sessionId"] != current_id:
                print(f"      {s['label']:<52} {lcs._short_cwd(s.get('cwd'))}")
    if not fleet:
        print("Nothing to resume.")
        return 0
    if len(fleet) > MAX_WINDOWS_SOFT and not args.force and not args.dry_run:
        print(f"Refusing to open {len(fleet)} windows (> {MAX_WINDOWS_SOFT}); re-run with --force.",
              file=sys.stderr)
        return 3

    have_wt = subprocess.run(["bash", "-lc", "command -v wt.exe"],
                             capture_output=True).returncode == 0
    if not have_wt and not args.dry_run:
        print("ERROR: wt.exe not found (need Windows Terminal via WSL interop).", file=sys.stderr)
        return 3

    LAUNCH_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        for i, sess in enumerate(fleet):
            inner = LAUNCH_DIR / f"resume-{sess['label']}.sh"
            inner.write_text(_inner_script(sess)); inner.chmod(0o755)
            cwd = lcs._short_cwd(sess.get("cwd"))
            print(f"  [dry-run] window {i+1}: label='{sess['label']}' cwd={cwd} "
                  f"resume={sess['sessionId'][:8]}  (orig tmux {sess['tmux']})")
        print(f"\n[dry-run] {len(fleet)} window(s) planned. Inner scripts in {LAUNCH_DIR}")
        return 0

    have_ccusage = subprocess.run(["bash", "-lc", "command -v ccusage"],
                                  capture_output=True).returncode == 0
    cache_files = _ccusage_cache_files()
    warm = (not args.no_warm) and have_ccusage and len(fleet) > 1

    def _say(i, sess):
        print(f"  window {i+1}/{len(fleet)}: '{sess['label']}'  ({lcs._short_cwd(sess.get('cwd'))})")

    # Launch the FIRST window, then let its statusline populate the shared per-UID
    # ccusage cache BEFORE the rest start. Otherwise N cold statuslines each re-parse
    # the whole JSONL corpus at once (thundering herd -> RAM overcommit -> swap-out
    # writes peg the disk for minutes). One warm parse instead of N.
    _launch(fleet[0]); _say(0, fleet[0])
    if warm and not _cache_warm(cache_files):
        print(f"  warming ccusage cache (prevents the cold-start disk thrash; up to {args.warm_timeout}s)...")
        deadline = time.time() + args.warm_timeout
        while time.time() < deadline and not _cache_warm(cache_files):
            time.sleep(1)
        print("  cache warm — remaining windows will reuse it" if _cache_warm(cache_files)
              else f"  warm timed out; pacing remaining windows {args.stagger}s apart instead")

    for i, sess in enumerate(fleet[1:], start=1):
        time.sleep(args.stagger)
        _launch(sess); _say(i, sess)

    print(f"\nLaunched {len(fleet)} window(s). Each reattaches if its tmux session "
          f"survived, else resumes from disk.")
    return 0


# --- main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Snapshot / restore the open Claude session fleet.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("store", help="snapshot the current fleet to a dated file")
    sp.add_argument("--auto", action="store_true", help="mark as automatic + prune old auto snapshots")
    sp.add_argument("--tag", help="retention bucket + filename tag (e.g. 'debrief'); "
                                  "prunes only against same-tagged snapshots. Overrides --auto's tag.")
    sp.add_argument("--keep", type=int, default=30, help="tagged snapshots to retain per bucket (default 30)")
    sp.add_argument("--include-detached", action="store_true",
                    help="also snapshot ORPHAN/PHANTOM (closed-window) sessions")
    sp.set_defaults(func=cmd_store)

    lp = sub.add_parser("list", help="list available snapshots")
    lp.set_defaults(func=cmd_list)

    rp = sub.add_parser("resume", help="rebuild the fleet from a snapshot")
    rp.add_argument("date", nargs="?", default="latest",
                    help="latest (default) | YYMMDD | snapshot filename/path")
    rp.add_argument("--dry-run", action="store_true", help="print the plan, open nothing")
    rp.add_argument("--no-reconcile", action="store_true",
                    help="do NOT union in sessions that were active after the snapshot was taken "
                         "(reconcile is on by default, and is what keeps a stale snapshot correct)")
    rp.add_argument("--force", action="store_true", help="allow > %d windows" % MAX_WINDOWS_SOFT)
    rp.add_argument("--include-current", action="store_true",
                    help="also resume the session this command runs from")
    rp.add_argument("--stagger", type=float, default=2.0,
                    help="seconds between windows after the first (default 2)")
    rp.add_argument("--warm-timeout", type=int, default=45,
                    help="max seconds to wait for the ccusage cache to warm (default 45)")
    rp.add_argument("--no-warm", action="store_true",
                    help="skip ccusage cache pre-warm (not recommended on cold /tmp)")
    rp.set_defaults(func=cmd_resume)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
