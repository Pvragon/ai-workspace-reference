#!/usr/bin/env python3
# ---
# template: execution
# name: close_parked_session.py
# version: 1.0.0
# summary: >-
#   Last step of /session-debrief in a pane that /handoff parked (tmux option @handoff_parked set by
#   handoff.sh). Closes the parked window once the debrief is truly done: postflight ran after the
#   park, no background task is still unreported, and the operator typed nothing after the park. Shows a
#   60-second Ctrl-C-able countdown in a small tmux pane, then kills its own tmux session (the
#   window closes via detach-on-destroy). Logs every decision to ~/.local/state/handoff/handoff.log.
# created: 2026-10-22
# last_updated: 2026-10-22
# maintainer: pvragon
# usage: >-
#   close_parked_session.py [--dry-run] [--session NAME] [--transcript JSONL] [--countdown 60]
#   [--wait 1800] | --self-check. Run from inside the parked Claude session's Bash tool; it returns at
#   once and the countdown runs in a split pane (--watch, internal).
# ---
"""Close a parked /handoff pane after its debrief.

Signals and what they can and cannot see:
- "the operator typed after the park": user entries in this session's Claude JSONL with origin.kind ==
  "human", not isMeta, not sidechain, timestamp after @handoff_parked. Typed /session-debrief or
  /handoff invocations are ignored. Tool results, task notifications (origin task-notification),
  subagent hand-backs (origin peer) and cron fires (isMeta, no origin) are not typing. Entries with
  no origin field at all (older Claude Code) count as typing unless they are a notification: the
  guard errs toward keeping the pane.
- "Debrief finished": a Bash call to session-debrief/postflight.sh after the park, with a result.
- "Background work": every async Agent launch (toolUseResult.agentId) and background Bash
  (toolUseResult.backgroundTaskId) in the transcript that has no later task-notification or
  hand-back naming its id is pending, and blocks. It cannot see a background process that a
  subagent started, or work Claude never announced in the transcript (e.g. a nohup'd process).
- "Claude is idle": the transcript has not been written for IDLE_SECS. A turn in progress writes.
"""
import argparse, glob, json, os, re, shutil, signal, subprocess, sys, tempfile, time
from datetime import datetime, timezone

LOG = os.path.expanduser("~/.local/state/handoff/handoff.log")
IDLE_SECS = 30
IGNORED_COMMANDS = re.compile(r"<command-name>/?(session-debrief|handoff)</command-name>")


def log(session, msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {session} close_parked: {msg}\n")
    except OSError:
        pass


def tmux(*args):
    r = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def current_session():
    pane = os.environ.get("TMUX_PANE")
    if not os.environ.get("TMUX") or not pane:
        return None
    rc, out = tmux("display", "-p", "-t", pane, "#{session_name}")
    return out if rc == 0 and out else None


def park_marker(session):
    rc, out = tmux("show-options", "-v", "-t", f"={session}:", "@handoff_parked")
    if rc != 0 or not out.strip().isdigit():
        return None, None
    _, new = tmux("show-options", "-v", "-t", f"={session}:", "@handoff_new_session")
    return int(out.strip()), new or None


def find_transcript(session_id):
    """Newest copy of <session_id>.jsonl under ~/.claude/projects (copies can exist per project dir)."""
    if not session_id:
        return None
    hits = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    return max(hits, key=lambda p: (os.path.getmtime(p), os.path.getsize(p))) if hits else None


def _ts(entry):
    t = entry.get("timestamp")
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else None
    except ValueError:
        return None


def _text(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def analyse(transcript, park_epoch):
    """Return the facts the decision needs, from the transcript alone.

    Typing reaches the transcript two ways: a `user` entry (prompt sent while Claude was idle) or an
    `attachment` of type queued_command (typed while Claude was mid-turn). Completion of background
    work also arrives several ways (user entry, queued_command attachment, queue-operation, hand-back
    message, TaskStop result), so any non-assistant line naming <task-id>X</task-id> resolves X.
    """
    typed, postflight_uses, postflight_done = [], set(), False
    launched, resolved = {}, set()
    with open(transcript, errors="replace") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("isSidechain"):
                continue
            ts = _ts(r)
            kind_of_entry = r.get("type")
            msg = r.get("message") or {}
            content = msg.get("content")
            if kind_of_entry == "assistant":
                for b in content if isinstance(content, list) else []:
                    if (isinstance(b, dict) and b.get("type") == "tool_use"
                            and "session-debrief/postflight.sh" in str((b.get("input") or {}).get("command", ""))
                            and ts and ts > park_epoch):
                        postflight_uses.add(b.get("id"))
                continue
            resolved.update(re.findall(r"<task-id>([^<]+)</task-id>", line))
            resolved.update(re.findall(r'<agent-message from=\\?"([^"\\]+)', line))
            if kind_of_entry == "attachment":
                att = r.get("attachment") or {}
                if att.get("type") != "queued_command":
                    continue
                origin, text = att.get("origin") or {}, str(att.get("prompt") or "")
                ts = _ts(att) or ts
            elif kind_of_entry == "user":
                tur = r.get("toolUseResult") if isinstance(r.get("toolUseResult"), dict) else {}
                if tur.get("isAsync") and tur.get("agentId"):
                    launched[tur["agentId"]] = "agent"
                if tur.get("backgroundTaskId"):
                    launched[tur["backgroundTaskId"]] = "bash"
                if tur.get("task_id"):  # TaskStop result
                    resolved.add(tur["task_id"])
                if isinstance(content, list) and content and all(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    if any(b.get("tool_use_id") in postflight_uses for b in content):
                        postflight_done = True
                    continue
                if r.get("isMeta"):
                    origin = r.get("origin") or {}
                    if origin.get("kind") == "peer" and origin.get("from"):
                        resolved.add(origin["from"])
                    continue
                origin, text = r.get("origin") or {}, _text(content)
            else:
                continue
            kind = origin.get("kind")
            if kind == "peer" and origin.get("from"):
                resolved.add(origin["from"])
            if kind not in (None, "human") or text.lstrip().startswith("<task-notification"):
                continue
            if IGNORED_COMMANDS.search(text):
                continue
            if ts and ts > park_epoch:
                typed.append((r.get("timestamp") or "?", text.strip().replace("\n", " ")[:80]))
    pending = sorted(f"{kind}:{tid}" for tid, kind in launched.items() if tid not in resolved)
    return {"typed": typed, "postflight": postflight_done, "pending": pending}


def agents_repo_dirt():
    """Uncommitted memory/handoff files in the agents repo: reported, never blocking (peers dirty it too)."""
    try:
        home = subprocess.run(
            [sys.executable, os.path.expanduser("~/ai-workspace/team-lib/executions/agent_paths.py")],
            capture_output=True, text=True, timeout=20).stdout
        home = next(l.split(None, 1)[1].strip() for l in home.splitlines() if l.startswith("agent_home"))
        out = subprocess.run(["git", "-C", home, "status", "--porcelain", "--", "memory", "handoffs"],
                             capture_output=True, text=True, timeout=20).stdout
        return [l[3:] for l in out.splitlines() if l.strip()]
    except Exception:
        return ["(could not check)"]


def decide(facts):
    """(verdict, reason). verdict: keep | wait | close."""
    if facts["typed"]:
        ts, text = facts["typed"][-1]
        return "keep", f"used after the park ({len(facts['typed'])} message(s), last {ts}: {text!r})"
    if not facts["postflight"]:
        return "keep", "debrief not finished: no postflight.sh run after the park"
    if facts["pending"]:
        return "wait", "background work still unreported: " + ", ".join(facts["pending"])
    return "close", "debrief done, nothing pending, not used after the park"


def kill_session(session):
    rc, _ = tmux("kill-session", "-t", f"={session}")
    return rc == 0


def watch(a):
    """Runs in the split pane: wait for quiet, count down, re-check, kill."""
    deadline = time.time() + a.wait
    while True:
        verdict, reason = decide(analyse(a.transcript, a.park))
        quiet = time.time() - os.path.getmtime(a.transcript) >= IDLE_SECS
        if verdict == "keep":
            log(a.session, f"keep ({reason})")
            print(f"Pane stays open: {reason}")
            time.sleep(15)
            return 0
        if verdict == "close" and quiet:
            break
        if time.time() > deadline:
            log(a.session, f"keep (gave up waiting after {a.wait}s: {reason if verdict == 'wait' else 'transcript still active'})")
            print("Pane stays open: still busy after the wait limit.")
            time.sleep(15)
            return 0
        print(f"\r\033[KWaiting: {reason if verdict == 'wait' else 'Claude still writing'}   ", end="", flush=True)
        time.sleep(5)

    def cancel(*_):
        log(a.session, "cancelled by Ctrl-C during the countdown; pane stays open")
        print("\nCancelled. This pane stays open.")
        time.sleep(3)
        sys.exit(0)
    signal.signal(signal.SIGINT, cancel)
    log(a.session, f"countdown {a.countdown}s started")
    for left in range(a.countdown, 0, -1):
        print(f"\r\033[KParked handoff pane: closing in {left:2d}s. Ctrl-C to keep it open.   ", end="", flush=True)
        time.sleep(1)
    verdict, reason = decide(analyse(a.transcript, a.park))
    if verdict != "close":
        log(a.session, f"keep (re-check at kill time: {reason})")
        print(f"\nPane stays open: {reason}")
        time.sleep(15)
        return 0
    log(a.session, f"killing tmux session {a.session}")
    if kill_session(a.session):
        return 0  # not reached in practice: this pane dies with the session
    log(a.session, "kill-session FAILED; pane stays open")
    return 1


def main(a):
    session = a.session or current_session()
    if not session:
        print("close-parked: not inside tmux; nothing to do.")
        return 0
    park, new = park_marker(session)
    if park is None:
        print(f"close-parked: {session} is not a parked handoff pane; nothing to do.")
        log(session, "not parked (no @handoff_parked); nothing to do")
        return 0
    transcript = a.transcript or find_transcript(os.environ.get("CLAUDE_CODE_SESSION_ID"))
    if not transcript or not os.path.exists(transcript):
        print("close-parked: pane stays open: this session's transcript was not found, so the used-after-park guard cannot run.")
        log(session, "keep (transcript not found)")
        return 0
    facts = analyse(transcript, park)
    verdict, reason = decide(facts)
    dirt = agents_repo_dirt()
    log(session, f"park={park} new={new} transcript={transcript} verdict={verdict} ({reason}); agents-repo dirty: {len(dirt)}")
    if dirt:
        print(f"close-parked: note: {len(dirt)} uncommitted memory/handoff file(s) in the agents repo (peers may own them): {', '.join(dirt[:5])}")
    if verdict == "keep":
        print(f"close-parked: pane stays open: {reason}.")
        return 0
    if a.dry_run:
        print(f"close-parked [dry-run]: {session} parked at {park} (new session {new or "unknown"}); would {'wait, then ' if verdict == 'wait' else ''}"
              f"count down {a.countdown}s and kill it. {reason}.")
        return 0
    cmd = [sys.executable, os.path.realpath(__file__), "--watch", "--session", session, "--transcript", transcript,
           "--park", str(park), "--countdown", str(a.countdown), "--wait", str(a.wait)]
    rc, _ = tmux("split-window", "-v", "-l", "3", "-t", f"={session}:", " ".join(map(_q, cmd)))
    if rc != 0:
        log(session, "keep (could not open the countdown pane)")
        print("close-parked: could not open the countdown pane; pane stays open.")
        return 1
    log(session, "countdown pane opened")
    first = "waits for that, then counts down" if verdict == "wait" else "counts down"
    print(f"close-parked: {reason}. A pane below {first} {a.countdown}s, then closes this window (Ctrl-C there keeps it).")
    return 0


def _q(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def self_check():
    """Fixture transcripts with known answers; no tmux needed."""
    park = 1_800_000_000
    iso = lambda dt: datetime.fromtimestamp(park + dt, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    def user(dt, text, **kw):
        return {"type": "user", "timestamp": iso(dt), "message": {"role": "user", "content": text}, **kw}
    def tool_use(dt, uid, cmd):
        return {"type": "assistant", "timestamp": iso(dt), "message": {"content": [
            {"type": "tool_use", "id": uid, "name": "Bash", "input": {"command": cmd}}]}}
    def result(dt, uid, tur=None):
        e = {"type": "user", "timestamp": iso(dt), "message": {"content": [
            {"type": "tool_result", "tool_use_id": uid, "content": "ok"}]}}
        if tur:
            e["toolUseResult"] = tur
        return e
    pf = [tool_use(100, "pf", "bash ~/.claude/skills/session-debrief/postflight.sh --session-name x"), result(101, "pf")]
    human = {"origin": {"kind": "human"}}
    cases = {
        "clean after park": ([user(-50, "/handoff please", **human)] + pf, "close"),
        "typed after park": (pf + [user(120, "wait, one more thing", **human)], "keep"),
        "typed before park only": ([user(-5, "rotate now", **human)] + pf, "close"),
        "typed /session-debrief": ([user(10, "<command-message>session-debrief</command-message>\n<command-name>/session-debrief</command-name>", **human)] + pf, "close"),
        "notifications and cron": (pf + [user(50, "<task-notification><task-id>x</task-id></task-notification>", origin={"kind": "task-notification"}),
                                         user(60, "[job j-1] nightly rotation check", isMeta=True),
                                         user(70, "hand-back", isMeta=True, origin={"kind": "peer", "from": "a1"})], "close"),
        "no origin field counts as typing": (pf + [user(130, "hello")], "keep"),
        "sidechain ignored": (pf + [user(130, "subagent prompt", isSidechain=True, **human)], "close"),
        "no postflight": ([user(-5, "go", **human)], "keep"),
        "postflight before park only": ([tool_use(-100, "pf0", "bash ~/.claude/skills/session-debrief/postflight.sh"), result(-99, "pf0")], "keep"),
        "pending agent": ([result(20, "ag", {"isAsync": True, "status": "async_launched", "agentId": "a9"})] + pf, "wait"),
        "agent notified": ([result(20, "ag", {"isAsync": True, "status": "async_launched", "agentId": "a9"})] + pf +
                           [user(150, "<task-notification>\n<task-id>a9</task-id>\n<status>completed</status>", origin={"kind": "task-notification"})], "close"),
        "agent handed back": ([result(20, "ag", {"isAsync": True, "status": "async_launched", "agentId": "a9"})] + pf +
                              [user(150, "report", isMeta=True, origin={"kind": "peer", "from": "a9"})], "close"),
        "pending bash": ([result(20, "bg", {"backgroundTaskId": "b7"})] + pf, "wait"),
        "typed mid-turn (queued_command)": (pf + [{"type": "attachment", "timestamp": iso(140), "attachment": {
            "type": "queued_command", "commandMode": "prompt", "prompt": "hold on", "origin": {"kind": "human"}, "timestamp": iso(140)}}], "keep"),
        "notification as queued_command": ([result(20, "bg", {"backgroundTaskId": "b7"})] + pf + [{"type": "attachment", "timestamp": iso(140), "attachment": {
            "type": "queued_command", "commandMode": "task-notification", "prompt": "<task-notification>\n<task-id>b7</task-id>", "origin": {"kind": "task-notification"}}}], "close"),
        "notification as queue-operation": ([result(20, "bg", {"backgroundTaskId": "b7"})] + pf + [{"type": "queue-operation", "operation": "enqueue",
            "timestamp": iso(140), "content": "<task-notification>\n<task-id>b7</task-id>"}], "close"),
        "agent stopped by TaskStop": ([result(20, "ag", {"isAsync": True, "status": "async_launched", "agentId": "a9"})] + pf + [result(150, "ts", {"task_id": "a9", "task_type": "local_agent"})], "close"),
    }
    d = tempfile.mkdtemp(prefix="close-parked-selfcheck-")
    fails = 0
    try:
        for name, (rows, want) in cases.items():
            p = os.path.join(d, "t.jsonl")
            with open(p, "w") as fh:
                fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
            got, why = decide(analyse(p, park))
            ok = got == want
            fails += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {name}: {got} ({why})")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"self-check: {len(cases) - fails}/{len(cases)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="decide and report; open no pane, kill nothing")
    ap.add_argument("--session", help="tmux session (default: this pane's)")
    ap.add_argument("--transcript", help="Claude JSONL (default: from CLAUDE_CODE_SESSION_ID)")
    ap.add_argument("--countdown", type=int, default=60)
    ap.add_argument("--wait", type=int, default=1800, help="max seconds to wait for background work")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--park", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.self_check:
        sys.exit(self_check())
    sys.exit(watch(args) if args.watch else main(args))
