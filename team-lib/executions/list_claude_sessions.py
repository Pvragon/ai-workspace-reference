#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "List currently-open Claude Code sessions with BOTH their tmux identifier (mylib-<pid>) and their Claude identifier (the /rename or -n name + sessionId). Cross-references live tmux clients, WSL relay ancestry (filters phantom windows), tmux pane pids, and ~/.claude/sessions/<pid>.json. Flags orphaned (detached, window-closed) sessions for reaping."
# created: 2026-06-23
# last_updated: 2026-06-23
# maintainer: your-agent
# usage: python3 list_claude_sessions.py [--json] [--all]
#   (no args)  print a human table of OPEN sessions + an ORPHANS section
#   --json     emit structured JSON (for chaining); implies --all
#   --all      include orphaned/phantom sessions in the table output
# ---
"""
List open Claude Code sessions, joining the tmux view to the Claude view.

Why this exists
---------------
A tmux session (named ``mylib-<pid>`` by the `go` launcher) and a Claude
session (named via ``/rename`` or ``claude -n``) are two different identifiers
for the same window, and neither side knows the other's name:

  * tmux only knows ``mylib-<pid>``  (the launcher pid, NOT the claude pid).
  * Claude stores its display name in ``~/.claude/sessions/<claude-pid>.json``
    under the ``name`` key — present whether the name came from ``-n`` or
    ``/rename``.

Detection recipe (the reliable one)
-----------------------------------
1. ``tmux list-clients``      -> sessions that currently have a client = candidate-open.
2. WSL relay ancestry         -> walk the client pid's parents; a live ``Relay(...)``
                                 ancestor means a real terminal window is still behind
                                 it. If the client got reparented to init/systemd with
                                 no relay, the window was closed (PHANTOM). This is the
                                 signal that survives WSL's "tmux outlives the window"
                                 leak, which ``attached=1`` does not.
3. ``tmux list-panes``        -> ``pane_pid`` is the claude process (or its wrapper);
                                 descend to the pid that owns a sessions/<pid>.json.
4. sessions/<claude-pid>.json -> name + sessionId + cwd + status.

States
------
  OPEN     live client + live relay ancestor   (a real window is open)
  PHANTOM  has a client but no relay ancestor   (window closed, tmux client lingering)
  ORPHAN   detached, no client at all           (window closed, session survived) -> reap

Linux/WSL only (reads /proc and tmux). No-ops cleanly off-tmux.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path

SESSIONS_DIR = Path.home() / ".claude" / "sessions"
MAX_ANCESTRY_HOPS = 20


# --- /proc helpers -----------------------------------------------------------

def _proc_stat(pid):
    """Return (comm, ppid) for a pid, or None if it's gone.

    Parse via the last ')' so a comm containing spaces/parens (e.g. 'Relay(123)')
    doesn't break field splitting.
    """
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    rparen = data.rfind(")")
    if rparen == -1:
        return None
    comm = data[data.find("(") + 1:rparen]
    rest = data[rparen + 2:].split()
    ppid = int(rest[1]) if len(rest) > 1 else 0
    return comm, ppid


def _has_relay_ancestor(pid):
    """True if a live WSL Relay(...) process sits above `pid` before init/systemd.

    That relay is the terminal-backend bridge; it dies when the window closes,
    so its presence is proof the window is genuinely open.
    """
    cur = pid
    for _ in range(MAX_ANCESTRY_HOPS):
        info = _proc_stat(cur)
        if info is None:
            return False
        comm, ppid = info
        if comm.startswith("Relay("):
            return True
        if ppid <= 2:  # reached init (1) or kthreadd/systemd (2) with no relay
            return False
        cur = ppid
    return False


def _descendants(pid):
    """Yield pid and all descendant pids (shallow BFS via pgrep -P)."""
    seen = [pid]
    queue = [pid]
    while queue:
        p = queue.pop(0)
        try:
            out = subprocess.run(
                ["pgrep", "-P", str(p)], capture_output=True, text=True
            ).stdout.split()
        except FileNotFoundError:
            out = []
        for c in out:
            c = int(c)
            if c not in seen:
                seen.append(c)
                queue.append(c)
    return seen


def _claude_record_for(pid):
    """Find the sessions/<pid>.json belonging to `pid` or a descendant.

    pane_pid may be claude itself or a wrapper shell that launched claude; the
    record is keyed by claude's actual pid, so we search the subtree.
    """
    for cand in _descendants(pid):
        f = SESSIONS_DIR / f"{cand}.json"
        if f.exists() and _proc_stat(cand) is not None:
            try:
                rec = json.loads(f.read_text())
                rec["_pid"] = cand
                return rec
            except (json.JSONDecodeError, OSError):
                continue
    return None


# --- tmux helpers ------------------------------------------------------------

def _tmux(*args):
    try:
        r = subprocess.run(["tmux", *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return ""
    return r.stdout


def _current_claude_pid():
    """Walk up from this process to the nearest pid owning a sessions/<pid>.json
    — that's the session this script is running inside (mark it 'this window')."""
    cur = os.getpid()
    for _ in range(MAX_ANCESTRY_HOPS):
        info = _proc_stat(cur)
        if info is None:
            return None
        _, ppid = info
        if (SESSIONS_DIR / f"{cur}.json").exists():
            return cur
        if ppid <= 2:
            return None
        cur = ppid
    return None


# --- core --------------------------------------------------------------------

def collect():
    """Return a list of session dicts joining the tmux + Claude views."""
    if _tmux("has-server") is None:  # tmux not installed
        return []

    # session -> (client_pid, tty) for sessions that currently have a client
    clients = {}
    for line in (_tmux("list-clients", "-F",
                       "#{client_session}\t#{client_pid}\t#{client_tty}") or "").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0]:
            clients[parts[0]] = (int(parts[1]), parts[2])

    # session -> pane_pid (root process of the pane = claude or its wrapper)
    panes = {}
    for line in (_tmux("list-panes", "-a", "-F",
                       "#{session_name}\t#{pane_pid}") or "").splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] and parts[0] not in panes:
            panes[parts[0]] = int(parts[1])

    # all sessions (so detached/orphan ones still appear)
    all_sessions = [s for s in (_tmux("list-sessions", "-F",
                                "#{session_name}") or "").splitlines() if s]

    this_pid = _current_claude_pid()
    rows = []
    for sess in all_sessions:
        client = clients.get(sess)
        pane_pid = panes.get(sess)
        rec = _claude_record_for(pane_pid) if pane_pid else None

        if client is None:
            state = "ORPHAN"          # detached, no client -> window gone, reap
        elif _has_relay_ancestor(client[0]):
            state = "OPEN"            # live window behind it
        else:
            state = "PHANTOM"         # client lingering but window closed

        rows.append({
            "tmux": sess,
            "state": state,
            "name": (rec or {}).get("name"),
            "sessionId": (rec or {}).get("sessionId"),
            "cwd": (rec or {}).get("cwd"),
            "status": (rec or {}).get("status"),
            "claude_pid": (rec or {}).get("_pid"),
            "is_current": bool(rec and rec.get("_pid") == this_pid),
        })

    order = {"OPEN": 0, "PHANTOM": 1, "ORPHAN": 2}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["tmux"]))
    return rows


def run():
    """Programmatic entry point for chaining. Returns the list of session dicts."""
    return collect()


# --- presentation ------------------------------------------------------------

def _short_cwd(cwd, width=32):
    if not cwd:
        return "?"
    home = str(Path.home())
    s = (cwd.replace(home + "/ai-workspace/", "")
            .replace("projects/acme-health-main-worktrees/", "rc-wt/")
            .replace(home, "~"))
    return s if len(s) <= width else "…" + s[-(width - 1):]


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _print_table(rows, include_all):
    shown = rows if include_all else [r for r in rows if r["state"] == "OPEN"]
    if not shown:
        print("No open Claude sessions found.")
    else:
        cells = [(r["tmux"], r["name"] or "(unnamed)", _short_cwd(r["cwd"]),
                  r["state"], (r["status"] or "?"),
                  "  <- this window" if r["is_current"] else "")
                 for r in shown]
        # size each column to its widest value (header included) — true alignment
        wt = max(len("TMUX"), *(len(c[0]) for c in cells))
        wn = max(len("CLAUDE NAME"), *(len(c[1]) for c in cells))
        wc = max(len("CWD"), *(len(c[2]) for c in cells))
        ws = max(len("STATE"), *(len(c[3]) for c in cells))
        hdr = (f"{'TMUX':<{wt}}  {'CLAUDE NAME':<{wn}}  {'CWD':<{wc}}  "
               f"{'STATE':<{ws}}  STATUS")
        print(hdr)
        print("-" * len(hdr))
        for tmux, name, cwd, state, status, mark in cells:
            print(f"{tmux:<{wt}}  {name:<{wn}}  {cwd:<{wc}}  "
                  f"{state:<{ws}}  {status}{mark}")

    orphans = [r for r in rows if r["state"] == "ORPHAN"]
    phantoms = [r for r in rows if r["state"] == "PHANTOM"]
    if not include_all and (orphans or phantoms):
        extra = []
        if orphans:
            extra.append(_plural(len(orphans), "orphan"))
        if phantoms:
            extra.append(_plural(len(phantoms), "phantom"))
        print(f"\n{' + '.join(extra)} not shown (window-closed). "
              f"Run with --all to see them; /reap-tmux to clean up.")


def main():
    ap = argparse.ArgumentParser(description="List open Claude Code sessions "
                                             "(tmux id + Claude id).")
    ap.add_argument("--json", action="store_true", help="emit JSON (implies --all)")
    ap.add_argument("--all", action="store_true",
                    help="include orphan/phantom sessions in the table")
    args = ap.parse_args()

    rows = collect()
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    _print_table(rows, include_all=args.all)


if __name__ == "__main__":
    main()
