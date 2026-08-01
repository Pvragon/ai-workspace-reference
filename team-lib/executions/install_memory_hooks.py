#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.1
# summary: "Wires the memory system into the Claude Code harness: registers the four PreToolUse hooks
#   in settings.json and installs the two crontab lines for the nightly sleep cycle. Idempotent (a
#   second run is a no-op), dry-run by default, backs settings.json up before writing, and never
#   touches unrelated hook entries. Separate from bootstrap_memory.py because bootstrapping the DATA
#   and wiring the HARNESS fail for different reasons and should be diagnosable independently."
# created: 2026-07-30
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""install_memory_hooks.py — register the hooks and the nightly cron.

What gets installed
-------------------
Four ``PreToolUse`` hooks in ``~/.claude/settings.json``:

===========================  ==========================  ==================================
matcher                      script                      why
===========================  ==========================  ==================================
Read|Edit|Write|MultiEdit    update_memory_access.py     reinforcement + spacing gate
Edit|Write|MultiEdit|Bash|   inject_lens.py              T3 situational lens injection
  Agent|Workflow
Edit|Write|MultiEdit|        allow_memory_writes.py      memory writes never prompt
  NotebookEdit
===========================  ==========================  ==================================

Two crontab lines:

* ``03:47`` — ``dream_cycle.py``: deterministic passes, spends no tokens, cues what
  reflective work is due.
* ``03:52`` — the reflective wake, five minutes later, which performs what was cued.

The five-minute offset is deliberate: the deterministic tick must finish writing its
cue file before the reflective wake reads it.

Usage
-----
    install_memory_hooks.py                 # dry run
    install_memory_hooks.py --apply
    install_memory_hooks.py --apply --no-cron        # hooks only
    install_memory_hooks.py --apply --agent-cmd "claude -p '/dream auto'"
    install_memory_hooks.py --uninstall --apply      # remove what we added
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import AgentResolutionError, agent_home, exec_dir  # noqa: E402

SETTINGS = Path.home() / ".claude/settings.json"

HOOKS = [
    ("Read|Edit|Write|MultiEdit", "update_memory_access.py",
     "two-strength reinforcement (recency always, reinforcement gated at 20h)"),
    ("Edit|Write|MultiEdit|Bash|Agent|Workflow", "inject_lens.py",
     "T3 situational lens injection"),
    ("Edit|Write|MultiEdit|NotebookEdit", "allow_memory_writes.py",
     "auto-approve memory writes so capture never prompts"),
]

CRON_TAG_TICK = "# pvragon-memory: nightly deterministic tick"
CRON_TAG_WAKE = "# pvragon-memory: nightly reflective wake"
DEFAULT_WAKE_CMD = "claude -p '/dream auto' --dangerously-skip-permissions"


# --------------------------------------------------------------- settings ----
def load_settings() -> dict:
    if not SETTINGS.is_file():
        return {}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"!! {SETTINGS} is not valid JSON ({exc}). Refusing to touch it.", file=sys.stderr)
        raise SystemExit(1)


def hook_entries(settings: dict) -> list:
    return settings.setdefault("hooks", {}).setdefault("PreToolUse", [])


def find_entry(entries: list, script: str):
    """Find the entry registering this script, wherever it currently points.

    Matches on the BASENAME so we also find an entry pointing at a different copy
    of the same script (e.g. a personal-layer install being migrated to team-lib).
    Returns (entry, hook_dict) so the caller can correct a stale path rather than
    mistaking it for a correct registration — matching on name alone silently
    treats "registered, but at the wrong path" as "already done".
    """
    for e in entries:
        for h in e.get("hooks", []):
            cmd = h.get("command", "")
            if script in cmd:
                return e, h
    return None, None


def install_hooks(apply: bool, uninstall: bool) -> int:
    settings = load_settings()
    entries = hook_entries(settings)
    changed = 0

    for matcher, script, why in HOOKS:
        cmd = f"{exec_dir() / script}"
        existing, hook = find_entry(entries, script)
        if uninstall:
            if existing:
                entries.remove(existing)
                changed += 1
                print(f"  remove hook  {script}")
            continue
        if existing:
            cur_cmd = hook.get("command", "")
            path_ok = str(exec_dir()) in cur_cmd
            matcher_ok = existing.get("matcher") == matcher
            if path_ok and matcher_ok:
                print(f"  ok           {script:<26} (already registered)")
                continue
            if not path_ok:
                # Preserve any interpreter prefix (e.g. "python3 ") the entry used.
                prefix = cur_cmd.split(script)[0].rsplit("/", 1)[0]
                prefix = "python3 " if prefix.strip().endswith("python3") else ""
                hook["command"] = prefix + cmd
                print(f"  repoint      {script:<26} -> {exec_dir()}")
            if not matcher_ok:
                print(f"  update       {script:<26} matcher {existing.get('matcher')!r} -> {matcher!r}")
                existing["matcher"] = matcher
            changed += 1
            continue
        print(f"  add hook     {script:<26} matcher {matcher}")
        print(f"               {why}")
        entries.append({"matcher": matcher,
                        "hooks": [{"type": "command", "command": cmd}]})
        changed += 1

    if not changed:
        print("  settings.json already correct — nothing to do")
        return 0
    if not apply:
        print(f"  [dry-run] {changed} change(s) to {SETTINGS}")
        return 0

    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS.is_file():
        bak = SETTINGS.with_suffix(f".json.bak-{datetime.date.today():%y%m%d}-memory-install")
        shutil.copy2(SETTINGS, bak)
        print(f"  backup       {bak.name}")
    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))       # validate before swapping in
    os.replace(tmp, SETTINGS)
    print(f"  wrote        {SETTINGS} ({changed} change(s))")
    return 0


# ------------------------------------------------------------------- cron ----
class CronUnavailable(RuntimeError):
    """No `crontab` binary on this host.

    Deliberately distinct from "crontab exists and is empty". Collapsing the two
    would make a box that CANNOT schedule look identical to one that simply has
    nothing scheduled yet, and the installer would report a cron it never installed.
    """


def current_crontab() -> str:
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError as exc:  # the `cron` package is not installed
        raise CronUnavailable("no `crontab` binary on this host") from exc
    return r.stdout if r.returncode == 0 else ""


def install_cron(apply: bool, uninstall: bool, wake_cmd: str) -> int:
    cur = current_crontab()
    lines = [ln for ln in cur.splitlines()
             if CRON_TAG_TICK not in ln and CRON_TAG_WAKE not in ln]
    removed = len(cur.splitlines()) - len(lines)

    if uninstall:
        if not removed:
            print("  no memory cron lines present")
            return 0
        print(f"  remove {removed} cron line(s)")
        return write_crontab(lines, apply)

    log = agent_home() / "runtime/logs"
    tick = (f"47 3 * * * {sys.executable} {exec_dir() / 'dream_cycle.py'} "
            f">> {log / 'dream_cycle.log'} 2>&1  {CRON_TAG_TICK}")
    wake = (f"52 3 * * * cd {agent_home()} && env -u ANTHROPIC_API_KEY timeout 900 {wake_cmd} "
            f">> {log / 'dream_wake.log'} 2>&1  {CRON_TAG_WAKE}")

    if removed == 2 and tick in cur and wake in cur:
        print("  crontab already correct — nothing to do")
        return 0
    print(f"  install cron 03:47 deterministic tick")
    print(f"  install cron 03:52 reflective wake")
    if not apply:
        print("  [dry-run] crontab unchanged")
        return 0
    log.mkdir(parents=True, exist_ok=True)
    return write_crontab(lines + [tick, wake], apply)


def write_crontab(lines: list[str], apply: bool) -> int:
    if not apply:
        return 0
    body = "\n".join(ln for ln in lines if ln.strip()) + "\n"
    try:
        r = subprocess.run(["crontab", "-"], input=body, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise CronUnavailable("no `crontab` binary on this host") from exc
    if r.returncode != 0:
        print(f"!! crontab install failed: {r.stderr.strip()}", file=sys.stderr)
        return 1
    print("  crontab updated")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--uninstall", action="store_true", help="remove what this installer added")
    ap.add_argument("--no-cron", action="store_true", help="skip the crontab step")
    ap.add_argument("--agent-cmd", default=DEFAULT_WAKE_CMD,
                    help="command the reflective wake runs (default: %(default)s)")
    args = ap.parse_args()

    # Only the CRON step needs an agent (it cd's into the agent home and writes its
    # logs there). Hook registration needs exec_dir() alone, which is agent-independent
    # — and the hooks are built to exit 0 when they cannot resolve an agent, a state
    # verify_memory_install.py asserts explicitly. So gate the check on the step that
    # actually needs it: an unconditional guard blocks the one useful thing a
    # pre-naming install CAN do, which is wire the harness ahead of the ceremony.
    if not args.no_cron:
        try:
            agent_home()
        except AgentResolutionError as exc:
            print(f"cannot resolve the agent:\n{exc}\n\n"
                  f"Hooks alone do not need an agent — re-run with --no-cron to register\n"
                  f"them now and install the cron after the naming ceremony.", file=sys.stderr)
            return 1

    verb = "Uninstalling" if args.uninstall else "Installing"
    print(f"{verb} memory-system harness wiring{'' if args.apply else '  [dry-run]'}\n")
    print("Hooks:")
    rc = install_hooks(args.apply, args.uninstall)
    if not args.no_cron:
        print("\nCron:")
        try:
            rc |= install_cron(args.apply, args.uninstall, args.agent_cmd)
        except CronUnavailable as exc:
            # Soft on purpose, and it must stay soft: verify_memory_install.py treats
            # cron as a WARN for exactly this reason — a host may schedule with systemd
            # timers or Task Scheduler instead. Failing the whole install here would
            # block the memory system on a container that never wanted cron anyway.
            print(f"  SKIPPED — {exc}.")
            print("  The memory system is fully installed; only the NIGHTLY SLEEP CYCLE")
            print("  is unscheduled. Install cron and re-run, or schedule these yourself:")
            print(f"    03:47  {sys.executable} {exec_dir() / 'dream_cycle.py'}")
            print(f"    03:52  {DEFAULT_WAKE_CMD}")
    else:
        print("\nCron: skipped (--no-cron)")

    if args.apply and not args.uninstall:
        print("\nNext: verify_memory_install.py   (proves the wiring actually works)")
    elif not args.apply:
        print("\nRe-run with --apply to make these changes.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
