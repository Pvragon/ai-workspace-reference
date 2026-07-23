#!/usr/bin/env python3
# ---
# template: execution
# version: 0.1.0
# summary: "Git-backed cross-machine agent-to-agent mailbox. Directed messages addressed by STABLE AGENT NAME (agent-a, agent-b), transported over a shared git repo (pull/push), stored one-file-per-message (never conflicts on rebase), with LOCAL uncommitted read-state per machine. The cross-machine sibling of session_activity.py's machine-local mailbox."
# created: 2026-07-21
# last_updated: 2026-07-21
# maintainer: pvragon
# ---
"""
Git-backed agent-to-agent mailbox.

WHY a separate script from session_activity.py:
  session_activity.py is machine-LOCAL session coordination — peers are ephemeral
  session-ids sharing one disk, messages are a single append-only JSONL guarded by
  flock. That model cannot cross machines: session-ids are not stable across hosts,
  and two hosts appending to one JSONL merge-conflict every push.

This mailbox keeps the same MENTAL model (directed async messages, poll-on-wake,
dedup via read-state) but changes three things so it survives git:
  1. Address by STABLE AGENT NAME, not session-id.
  2. ONE immutable file per message under messages/ — rebase never conflicts.
  3. Read-state is LOCAL and uncommitted (~/.config/agent-mailbox/) — each machine
     tracks its own "seen" set; committing it would conflict AND leak who-read-what.

Transport: a shared git repo (private GitHub repo both machines can clone).
  send  = write message file -> add -> commit -> pull --rebase -> push (retry once)
  inbox = pull --rebase -> list messages addressed to me not yet in read-state
  ack   = mark message id(s) seen in local read-state

CLI:
    python3 agent_mailbox.py init --identity <your-agent> --remote git@github.com:<your-org>/agent-mailbox.git
    python3 agent_mailbox.py whoami
    python3 agent_mailbox.py register --name vesper --machine machine-b
    python3 agent_mailbox.py agents
    python3 agent_mailbox.py send --to vesper --subject "hi" --msg "hello from the other side"
    python3 agent_mailbox.py inbox            # unread addressed to me
    python3 agent_mailbox.py inbox --all      # everything addressed to me
    python3 agent_mailbox.py thread --conv <conv_id>
    python3 agent_mailbox.py ack --all        # or --id <msgid>
    python3 agent_mailbox.py pull
    python3 agent_mailbox.py --self-test      # full cross-machine flow, throwaway repos

Importable:
    from executions.agent_mailbox import run
    run("send", to="vesper", msg="hi")   # -> {"ok": True, "id": ...}
    run("inbox")                          # -> {"ok": True, "messages": [...]}
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# --- Config / paths --------------------------------------------------------

CONFIG_DIR = Path(os.path.expanduser("~/.config/agent-mailbox"))
CONFIG_PATH = CONFIG_DIR / "config.json"
READSTATE_PATH = CONFIG_DIR / "read-state.json"

MESSAGES_DIRNAME = "messages"
AGENTS_FILENAME = "agents.json"

# Overridable for --self-test (points config elsewhere without touching real ~/.config)
_CONFIG_OVERRIDE = None


def _now():
    return datetime.now(timezone.utc)


def _ts():
    return _now().strftime("%Y%m%dT%H%M%SZ")


def _msg_id():
    return uuid.uuid4().hex[:10]


def _config_path():
    return _CONFIG_OVERRIDE / "config.json" if _CONFIG_OVERRIDE else CONFIG_PATH


def _readstate_path():
    return _CONFIG_OVERRIDE / "read-state.json" if _CONFIG_OVERRIDE else READSTATE_PATH


def _load_config():
    p = _config_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_config(cfg):
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n")


def _load_readstate():
    p = _readstate_path()
    if not p.exists():
        return {"seen": [], "last_pull": ""}
    try:
        d = json.loads(p.read_text())
        d.setdefault("seen", [])
        d.setdefault("last_pull", "")
        return d
    except Exception:
        return {"seen": [], "last_pull": ""}


def _save_readstate(rs):
    p = _readstate_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rs, indent=2) + "\n")


# --- Git helpers -----------------------------------------------------------

def _git(repo, *args, check=False):
    """Run a git command in `repo`. Returns (rc, stdout, stderr)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _has_remote(repo):
    rc, out, _ = _git(repo, "remote")
    return rc == 0 and out.strip() != ""


def _pull(repo):
    """git pull --rebase if a remote exists. Returns True on success (or no remote)."""
    if not _has_remote(repo):
        return True
    rc, _, err = _git(repo, "pull", "--rebase", "--autostash")
    return rc == 0


def _push(repo):
    """Push; if rejected, pull --rebase and retry once. Returns True on success
    (or no remote — local-only mode)."""
    if not _has_remote(repo):
        return True
    rc, _, _ = _git(repo, "push")
    if rc == 0:
        return True
    # Rejected (peer pushed first). Rebase onto their commits — per-file messages
    # never conflict — and retry.
    _git(repo, "pull", "--rebase", "--autostash")
    rc, _, _ = _git(repo, "push")
    return rc == 0


def _commit(repo, paths, message):
    for p in paths:
        _git(repo, "add", str(p))
    rc, _, err = _git(repo, "commit", "-m", message)
    return rc == 0


# --- Repo layout accessors -------------------------------------------------

def _repo_root(cfg):
    return Path(cfg["repo_path"])


def _messages_dir(cfg):
    d = _repo_root(cfg) / MESSAGES_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _agents_path(cfg):
    return _repo_root(cfg) / AGENTS_FILENAME


def _load_agents(cfg):
    p = _agents_path(cfg)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _iter_messages(cfg):
    """Yield every message record in the repo (sorted by ts)."""
    md = _messages_dir(cfg)
    recs = []
    for f in md.glob("*.json"):
        try:
            recs.append(json.loads(f.read_text()))
        except Exception:
            continue
    recs.sort(key=lambda r: r.get("ts", ""))
    return recs


# --- Commands --------------------------------------------------------------

def _require_cfg():
    cfg = _load_config()
    if not cfg or not cfg.get("identity") or not cfg.get("repo_path"):
        raise RuntimeError("mailbox not initialized — run: agent_mailbox.py init "
                           "--identity <name> --remote <git-url>")
    return cfg


def cmd_init(identity, remote=None, repo_path=None):
    """Initialize this machine's mailbox: clone the shared repo (or init a fresh
    one) and write local config naming this machine's agent identity."""
    if not repo_path:
        # Default sibling location next to the other workspace repos.
        repo_path = os.path.expanduser(f"~/ai-workspace/agent-mailbox")
    repo_path = os.path.abspath(repo_path)
    root = Path(repo_path)

    if remote and not root.exists():
        rc, _, err = subprocess.run(
            ["git", "clone", remote, repo_path],
            capture_output=True, text=True,
        ).returncode, "", ""
        if rc != 0:
            # Clone failed (repo may be empty / not yet created) — init locally.
            root.mkdir(parents=True, exist_ok=True)
            _git(root, "init")
            if remote:
                _git(root, "remote", "add", "origin", remote)
    elif not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        _git(root, "init")

    (root / MESSAGES_DIRNAME).mkdir(parents=True, exist_ok=True)
    if not _agents_path({"repo_path": repo_path}).exists():
        (root / AGENTS_FILENAME).write_text("{}\n")

    cfg = {"identity": identity, "repo_path": repo_path,
           "remote": remote or "", "created": _now().isoformat()}
    _save_config(cfg)
    # Register self.
    cmd_register(identity, machine=os.uname().nodename, _cfg=cfg)
    return {"ok": True, "identity": identity, "repo_path": repo_path,
            "remote": remote or "(local-only)"}


def cmd_register(name, machine=None, _cfg=None):
    cfg = _cfg or _require_cfg()
    _pull(_repo_root(cfg))
    agents = _load_agents(cfg)
    if name in agents:
        return {"ok": True, "already": True, "name": name}
    agents[name] = {"machine": machine or "", "added": _now().isoformat()}
    _agents_path(cfg).write_text(json.dumps(agents, indent=2) + "\n")
    _commit(_repo_root(cfg), [_agents_path(cfg)], f"mailbox: register agent {name}")
    _push(_repo_root(cfg))
    return {"ok": True, "name": name, "agents": sorted(agents)}


def cmd_agents():
    cfg = _require_cfg()
    _pull(_repo_root(cfg))
    agents = _load_agents(cfg)
    return {"ok": True, "agents": agents, "me": cfg["identity"]}


def cmd_send(to, msg, subject=None, conv=None):
    cfg = _require_cfg()
    root = _repo_root(cfg)
    _pull(root)
    me = cfg["identity"]
    agents = _load_agents(cfg)
    if to not in agents and to != me:
        # Not fatal — allow sending to a not-yet-registered agent, but flag it.
        unknown = True
    else:
        unknown = False
    mid = _msg_id()
    rec = {
        "id": mid,
        "ts": _now().isoformat(),
        "from": me,
        "to": to,
        "conv_id": conv or mid,
        "subject": subject or "",
        "body": msg,
    }
    fname = f"{_ts()}-{me}-to-{to}-{mid}.json"
    fpath = _messages_dir(cfg) / fname
    fpath.write_text(json.dumps(rec, indent=2) + "\n")
    _commit(root, [fpath], f"mailbox: {me} -> {to}: {(subject or msg)[:50]}")
    pushed = _push(root)
    return {"ok": True, "id": mid, "conv_id": rec["conv_id"], "to": to,
            "pushed": pushed, "unknown_recipient": unknown}


def cmd_inbox(show_all=False):
    cfg = _require_cfg()
    _pull(_repo_root(cfg))
    me = cfg["identity"]
    rs = _load_readstate()
    seen = set(rs["seen"])
    rs["last_pull"] = _now().isoformat()
    _save_readstate(rs)
    out = []
    for r in _iter_messages(cfg):
        if r.get("to") != me:
            continue
        if not show_all and r.get("id") in seen:
            continue
        out.append({**r, "unread": r.get("id") not in seen})
    return {"ok": True, "me": me, "count": len(out), "messages": out}


def cmd_thread(conv):
    cfg = _require_cfg()
    _pull(_repo_root(cfg))
    out = [r for r in _iter_messages(cfg) if r.get("conv_id") == conv]
    return {"ok": True, "conv_id": conv, "messages": out}


def cmd_ack(msg_id=None, ack_all=False):
    cfg = _require_cfg()
    me = cfg["identity"]
    rs = _load_readstate()
    seen = set(rs["seen"])
    added = []
    for r in _iter_messages(cfg):
        if r.get("to") != me:
            continue
        if ack_all or r.get("id") == msg_id:
            if r.get("id") not in seen:
                seen.add(r.get("id"))
                added.append(r.get("id"))
    rs["seen"] = sorted(seen)
    _save_readstate(rs)
    return {"ok": True, "acked": added, "total_seen": len(seen)}


def cmd_pull():
    cfg = _require_cfg()
    ok = _pull(_repo_root(cfg))
    rs = _load_readstate()
    rs["last_pull"] = _now().isoformat()
    _save_readstate(rs)
    return {"ok": ok}


def cmd_whoami():
    cfg = _load_config()
    if not cfg:
        return {"ok": False, "error": "not initialized"}
    return {"ok": True, "identity": cfg.get("identity"),
            "repo_path": cfg.get("repo_path"), "remote": cfg.get("remote")}


# --- Dispatch --------------------------------------------------------------

def run(command, **kw):
    """Importable entry point. Returns a dict."""
    if command == "init":
        return cmd_init(kw["identity"], kw.get("remote"), kw.get("repo_path"))
    if command == "register":
        return cmd_register(kw["name"], kw.get("machine"))
    if command == "agents":
        return cmd_agents()
    if command == "send":
        return cmd_send(kw["to"], kw["msg"], kw.get("subject"), kw.get("conv"))
    if command == "inbox":
        return cmd_inbox(kw.get("all", False))
    if command == "thread":
        return cmd_thread(kw["conv"])
    if command == "ack":
        return cmd_ack(kw.get("id"), kw.get("all", False))
    if command == "pull":
        return cmd_pull()
    if command == "whoami":
        return cmd_whoami()
    raise ValueError(f"unknown command: {command}")


def _print_inbox(res):
    if not res["messages"]:
        print(f"(inbox empty for {res['me']})")
        return
    for m in res["messages"]:
        flag = "•" if m.get("unread") else " "
        subj = f" [{m['subject']}]" if m.get("subject") else ""
        print(f"{flag} {m.get('ts','')[:19]}  from {m.get('from')}{subj}  "
              f"(conv {m.get('conv_id')}, id {m.get('id')})")
        print(f"    {m.get('body','')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Git-backed agent-to-agent mailbox")
    ap.add_argument("command", nargs="?",
                    choices=["init", "register", "agents", "send", "inbox",
                             "thread", "ack", "pull", "whoami"])
    ap.add_argument("--identity", help="init: this machine's agent name")
    ap.add_argument("--remote", help="init: shared git repo URL")
    ap.add_argument("--repo-path", dest="repo_path", help="init: local clone path")
    ap.add_argument("--name", help="register: agent name")
    ap.add_argument("--machine", help="register: machine label")
    ap.add_argument("--to", help="send: recipient agent name")
    ap.add_argument("--msg", help="send: message body")
    ap.add_argument("--subject", help="send: subject line")
    ap.add_argument("--conv", help="send/thread: conversation id")
    ap.add_argument("--id", help="ack: message id")
    ap.add_argument("--all", action="store_true", help="inbox/ack: include/act on all")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return 0 if _self_test() else 1

    if not args.command:
        ap.print_help()
        return 1

    try:
        if args.command == "init":
            res = cmd_init(args.identity, args.remote, args.repo_path)
        elif args.command == "register":
            res = cmd_register(args.name or args.identity, args.machine)
        elif args.command == "agents":
            res = cmd_agents()
        elif args.command == "send":
            if not args.to or not args.msg:
                print("send requires --to and --msg"); return 1
            res = cmd_send(args.to, args.msg, args.subject, args.conv)
        elif args.command == "inbox":
            res = cmd_inbox(args.all)
            _print_inbox(res)
            return 0
        elif args.command == "thread":
            res = cmd_thread(args.conv)
        elif args.command == "ack":
            res = cmd_ack(args.id, args.all)
        elif args.command == "pull":
            res = cmd_pull()
        elif args.command == "whoami":
            res = cmd_whoami()
    except RuntimeError as e:
        print(f"error: {e}")
        return 1
    print(json.dumps(res, indent=2))
    return 0


# --- Self-test: full cross-machine flow against throwaway local repos -------

def _self_test():
    import tempfile
    global _CONFIG_OVERRIDE
    ok = True
    tmp = Path(tempfile.mkdtemp(prefix="agent-mailbox-selftest-"))
    try:
        # 1. A bare repo acts as the shared "GitHub" remote.
        bare = tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)

        def clone_for(identity):
            """Simulate one machine: its own clone + its own local config dir."""
            cdir = tmp / f"cfg-{identity}"
            cdir.mkdir()
            rpath = tmp / f"clone-{identity}"
            subprocess.run(["git", "clone", "-q", str(bare), str(rpath)], check=True)
            for k, v in (("user.email", f"{identity}@test"), ("user.name", identity)):
                _git(rpath, "config", k, v)
            return cdir, rpath

        # 2. rowan initializes, registers, and seeds agents.json.
        rowan_cfg_dir, rowan_repo = clone_for("rowan")
        _CONFIG_OVERRIDE = rowan_cfg_dir
        _save_config({"identity": "rowan", "repo_path": str(rowan_repo), "remote": str(bare)})
        (rowan_repo / MESSAGES_DIRNAME).mkdir(exist_ok=True)
        (rowan_repo / AGENTS_FILENAME).write_text("{}\n")
        _commit(rowan_repo, [rowan_repo / AGENTS_FILENAME], "init")
        _push(rowan_repo)
        cmd_register("rowan", machine="machine-a")
        cmd_register("vesper", machine="machine-b")

        # 3. rowan sends to vesper.
        send_res = cmd_send("vesper", "hello from the other side", subject="first contact")
        assert send_res["ok"] and send_res["pushed"], "send/push failed"
        conv = send_res["conv_id"]

        # 4. vesper (a DIFFERENT machine: different clone, different read-state) pulls.
        vesper_cfg_dir, vesper_repo = clone_for("vesper")
        _CONFIG_OVERRIDE = vesper_cfg_dir
        _save_config({"identity": "vesper", "repo_path": str(vesper_repo), "remote": str(bare)})
        inbox = cmd_inbox()
        assert inbox["count"] == 1, f"vesper expected 1 msg, got {inbox['count']}"
        assert inbox["messages"][0]["body"] == "hello from the other side"
        print("✓ cross-machine deliver: vesper received rowan's message")

        # 5. Dedup: unread once, then acked, then gone from unread view.
        cmd_ack(ack_all=True)
        assert cmd_inbox()["count"] == 0, "acked message still showing as unread"
        assert cmd_inbox(show_all=True)["count"] == 1, "--all should still show acked msg"
        print("✓ read-state dedup: acked message drops from unread, survives in --all")

        # 6. vesper replies in-thread; rowan sees it, rowan's OWN read-state is separate.
        cmd_send("rowan", "received, thank you", subject="re: first contact", conv=conv)
        _CONFIG_OVERRIDE = rowan_cfg_dir
        rin = cmd_inbox()
        assert rin["count"] == 1 and rin["messages"][0]["conv_id"] == conv, "reply not delivered in-thread"
        print("✓ threaded reply: rowan received vesper's reply on the same conv_id")

        # 7. Concurrent send: both push 'simultaneously' — per-file, no conflict.
        _CONFIG_OVERRIDE = rowan_cfg_dir
        cmd_send("vesper", "msg A")
        _CONFIG_OVERRIDE = vesper_cfg_dir
        _git(vesper_repo, "pull", "--rebase", "--autostash")  # get to a known state
        cmd_send("rowan", "msg B")
        _CONFIG_OVERRIDE = rowan_cfg_dir
        assert cmd_inbox()["count"] >= 1, "concurrent-send delivery failed"
        print("✓ concurrent per-file sends rebase cleanly (no merge conflict)")

        th = cmd_thread(conv)
        assert len(th["messages"]) == 2, f"thread expected 2, got {len(th['messages'])}"
        print(f"✓ thread view: {len(th['messages'])} messages on conv {conv[:8]}")

        print("\nALL SELF-TESTS PASSED ✓")
    except AssertionError as e:
        print(f"\n✗ SELF-TEST FAILED: {e}")
        ok = False
    except Exception as e:
        print(f"\n✗ SELF-TEST ERROR: {e}")
        ok = False
    finally:
        _CONFIG_OVERRIDE = None
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


if __name__ == "__main__":
    sys.exit(main())
