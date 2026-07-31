#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "End-to-end self-test proving the memory POLICY is actually wired, not merely that files
#   exist. Resolves the agent, checks the tier directories, confirms the hooks are registered, then
#   exercises the real hook against a throwaway topic file to prove reinforcement fires, the 20h
#   spacing gate holds, non-reinforcing tools are no-ops, and hooks degrade to exit 0 when the agent
#   cannot be resolved. Without this an operator cannot distinguish a working install from a silently
#   dead one. Exits non-zero on any hard failure; always cleans up its scratch file."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""verify_memory_install.py — prove the install works, don't assume it.

The hygiene linter (``memory_self_check.py``) checks the memory CONTENT. This checks
the MACHINERY. They fail for different reasons: content rots gradually, wiring is
either connected or it isn't, and a disconnected hook is invisible — memories simply
stop accumulating strength and nothing complains.

    verify_memory_install.py            # run all checks
    verify_memory_install.py --verbose  # show each subprocess result
    verify_memory_install.py --json     # machine-readable

Exit 0 = every hard check passed. Exit 1 = at least one hard failure.
Soft findings (WARN) never fail the run: cron is optional on hosts that use a
different scheduler, and an empty lens directory is a legitimate state.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    AgentResolutionError, agent_home, exec_dir, journal_dir, lenses_dir,
    meditations_dir, memory_dir, shortterm_dir, state_dir,
)

SETTINGS = Path.home() / ".claude/settings.json"
SCRATCH_NAME = "reference_zz-install-verify-scratch.md"
HOOK_SCRIPTS = ["update_memory_access.py", "inject_lens.py", "allow_memory_writes.py"]

results: list[tuple[str, str, str]] = []   # (level, check, detail)


def ok(check, detail=""):
    results.append(("PASS", check, detail))


def bad(check, detail=""):
    results.append(("FAIL", check, detail))


def warn(check, detail=""):
    results.append(("WARN", check, detail))


def run(script: str, *args, stdin: str | None = None):
    return subprocess.run([sys.executable, str(exec_dir() / script), *args],
                          input=stdin, capture_output=True, text=True, timeout=180)


def fm_field(path: Path, key: str):
    m = re.search(rf"^{key}:\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else None


def fire_hook(path: Path, tool: str):
    payload = json.dumps({"tool_name": tool, "tool_input": {"file_path": str(path)}})
    return run("update_memory_access.py", stdin=payload)


# ------------------------------------------------------------------ checks ----
def check_resolution():
    try:
        home = agent_home()
    except AgentResolutionError as exc:
        bad("agent resolution", str(exc).splitlines()[0])
        return False
    ok("agent resolution", str(home))
    return True


def check_dirs():
    required = {"memory": memory_dir(), "short-term": shortterm_dir(),
                "dream-journal": journal_dir(), "meditations": meditations_dir(),
                "runtime/state": state_dir()}
    missing = [n for n, p in required.items() if not p.is_dir()]
    if missing:
        bad("tier directories", f"missing: {', '.join(missing)} — run bootstrap_memory.py --apply")
    else:
        ok("tier directories", f"{len(required)} present")
    if not lenses_dir().is_dir():
        warn("lens directory", "absent — lenses are optional but inject_lens has nothing to serve")


def check_hooks_registered():
    if not SETTINGS.is_file():
        bad("hooks registered", f"{SETTINGS} not found — run install_memory_hooks.py --apply")
        return
    try:
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        bad("hooks registered", f"settings.json invalid JSON: {exc}")
        return
    blob = json.dumps(cfg.get("hooks", {}).get("PreToolUse", []))
    missing = [s for s in HOOK_SCRIPTS if s not in blob]
    if missing:
        bad("hooks registered", f"not wired: {', '.join(missing)}")
    else:
        ok("hooks registered", f"{len(HOOK_SCRIPTS)} PreToolUse hooks present")
    # the reinforcement hook must cover writes, not only reads
    for e in cfg.get("hooks", {}).get("PreToolUse", []):
        if any("update_memory_access.py" in h.get("command", "") for h in e.get("hooks", [])):
            m = e.get("matcher", "")
            if "Edit" in m and "Write" in m:
                ok("curation counts", f"matcher = {m}")
            else:
                warn("curation counts",
                     f"matcher {m!r} omits Edit/Write — editing a memory will not reinforce it")
            break


def check_reinforcement_live():
    """The core check: does the hook actually change a file on disk?"""
    scratch = memory_dir() / SCRATCH_NAME
    try:
        scratch.write_text("---\nname: reference_zz-install-verify-scratch\n"
                           "type: reference\n---\n\nscratch\n", encoding="utf-8")

        # 1. a fresh file reinforces on first touch
        fire_hook(scratch, "Read")
        ac, st = fm_field(scratch, "access_count"), fm_field(scratch, "stability")
        if ac == "1" and st and abs(float(st) - 22.4) < 0.05:
            ok("reinforcement fires", f"access_count 0->1, stability 14->{st}")
        else:
            bad("reinforcement fires", f"expected ac=1 stability=22.4, got ac={ac} stability={st}")
            return

        # 2. an immediate second touch must NOT reinforce (spacing gate)
        fire_hook(scratch, "Read")
        if fm_field(scratch, "access_count") == "1":
            ok("spacing gate holds", "immediate re-read did not inflate storage strength")
        else:
            bad("spacing gate holds",
                f"cramming counted: access_count became {fm_field(scratch, 'access_count')}")

        # 3. a non-reinforcing tool must be a no-op
        before = scratch.read_text(encoding="utf-8")
        fire_hook(scratch, "Grep")
        if scratch.read_text(encoding="utf-8") == before:
            ok("non-reinforcing tools", "Grep left the file untouched")
        else:
            bad("non-reinforcing tools", "Grep mutated the file")

        # 4. curation (Edit) reinforces once the gate has expired
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        t = scratch.read_text(encoding="utf-8")
        t = re.sub(r"^last_reinforced:.*$", f"last_reinforced: {old}", t, flags=re.M)
        scratch.write_text(t, encoding="utf-8")
        fire_hook(scratch, "Edit")
        ac2, st2 = fm_field(scratch, "access_count"), fm_field(scratch, "stability")
        if ac2 == "2" and st2 and abs(float(st2) - 35.8) < 0.1:
            ok("curation reinforces", f"Edit after 30h: access_count 1->2, stability -> {st2}")
        else:
            bad("curation reinforces", f"expected ac=2 stability=35.8, got ac={ac2} stability={st2}")
    finally:
        scratch.unlink(missing_ok=True)


def check_hook_resilience():
    """A hook must never raise, even with a completely unresolvable agent."""
    import os
    env = dict(os.environ, PVRAGON_WORKSPACE="/nonexistent-path-for-verify")
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.md"}})
    codes = []
    for s in ("update_memory_access.py", "inject_lens.py", "allow_memory_writes.py"):
        r = subprocess.run([sys.executable, str(exec_dir() / s)], input=payload,
                           capture_output=True, text=True, env=env, timeout=60)
        codes.append((s, r.returncode))
    bad_ones = [f"{s} -> exit {c}" for s, c in codes if c != 0]
    if bad_ones:
        bad("hook resilience", "; ".join(bad_ones) + " (must be 0 — a hook must never block a tool)")
    else:
        ok("hook resilience", "all hooks exit 0 with an unresolvable agent")


def check_reranker():
    r = run("rerank_memory_index.py", "--dry-run")
    # The `new:` segment is OPTIONAL so this parses both v2.0.x and v2.1.0+ output.
    # It was not optional once, and adding the New band silently broke this check: the
    # regex stopped matching, the raw output was reported as a hard failure, and a
    # perfectly good install was declared unsound. A verifier coupled to another
    # script's print formatting has to tolerate that script changing.
    m = re.search(r"entries:\s*(\d+)\s+hot:\s*(\d+)\s*\((\d+) chars\)\s+"
                  r"(?:new:\s*(\d+)\s*\((\d+) chars\)\s+)?"
                  r"cold:\s*(\d+)\s*\((\d+) chars\)\s+archive:\s*(\d+)", r.stdout)
    if not m:
        bad("reranker", (r.stderr or r.stdout).strip()[:160] or "no parseable output")
        return
    entries, hot, hotc = int(m.group(1)), int(m.group(2)), int(m.group(3))
    new = int(m.group(4) or 0)
    newc = int(m.group(5) or 0)
    cold, coldc, arch = int(m.group(6)), int(m.group(7)), int(m.group(8))

    if entries == 0:
        # A brand-new install has no T2 memories yet. That is the CORRECT state right
        # after bootstrap, not a fault — telling a new teammate their install is
        # unsound at the end of onboarding is worse than saying nothing.
        ok("reranker", "ran clean; corpus is empty (expected on a fresh install)")
        return
    if hotc <= 12000 and coldc <= 4000 and newc <= 2500:
        ok("reranker", f"{entries} entries -> hot {hot} ({hotc}c) / new {new} ({newc}c) / "
                       f"cold {cold} ({coldc}c) / archive {arch}")
    else:
        bad("reranker", f"band budgets exceeded: hot {hotc}/12000, "
                        f"new {newc}/2500, cold {coldc}/4000")
    if hot == 0:
        bad("reranker", "corpus is non-empty but the Hot band is empty")


def check_meditations():
    objs = [p for p in meditations_dir().glob("*.md")
            if p.name not in ("README.md",) and not p.name.startswith("EXAMPLE")] \
        if meditations_dir().is_dir() else []
    if not objs:
        bad("meditation library", "empty — run bootstrap_memory.py --apply to seed it")
        return
    shelves = {}
    for p in objs:
        m = re.search(r"^shelf:\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
        s = m.group(1) if m else "(unset)"
        shelves[s] = shelves.get(s, 0) + 1
    if "awareness" not in shelves:
        warn("meditation library",
             f"{len(objs)} objects but no 'awareness' shelf — the floor cannot protect anything")
    else:
        ok("meditation library",
           f"{len(objs)} objects: " + ", ".join(f"{k}={v}" for k, v in sorted(shelves.items())))
    r = run("dream_select.py")
    pick = r.stdout.strip()
    if r.returncode == 0 and pick and (meditations_dir() / f"{pick}.md").is_file():
        ok("meditation selector", f"chose '{pick}'")
    else:
        bad("meditation selector", (r.stderr or "no valid object returned").strip()[:120])


def check_cron():
    # `crontab` is absent on minimal boxes (containers, slim images). A verifier that
    # raises instead of reporting is worse than useless — it is the tool you run to find
    # out whether anything is wrong, so it must survive every environment it describes.
    # Caught by the pristine-container test, which is the only place this can surface.
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        warn("nightly cron", "no `crontab` on this box — install cron for self-maintenance; "
                             "everything else works interactively")
        return
    body = r.stdout if r.returncode == 0 else ""
    tick = "dream_cycle.py" in body
    wake = "/dream" in body
    if tick and wake:
        ok("nightly cron", "deterministic tick + reflective wake both scheduled")
    elif tick:
        warn("nightly cron", "tick scheduled but no reflective wake — nothing will meditate")
    else:
        warn("nightly cron", "not scheduled — the system works interactively but never self-maintains")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if check_resolution():
        check_dirs()
        check_hooks_registered()
        check_reinforcement_live()
        check_hook_resilience()
        check_reranker()
        check_meditations()
        check_cron()

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]

    if args.json:
        print(json.dumps({"results": [{"level": l, "check": c, "detail": d} for l, c, d in results],
                          "passed": len(results) - len(fails) - len(warns),
                          "warnings": len(warns), "failures": len(fails)}, indent=2))
    else:
        width = max((len(c) for _, c, _ in results), default=10)
        for level, check, detail in results:
            mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "WARN": " warn "}[level]
            print(f"[{mark}] {check:<{width}}  {detail}")
        print()
        if fails:
            print(f"{len(fails)} hard failure(s), {len(warns)} warning(s). The install is NOT sound.")
        elif warns:
            print(f"All hard checks passed, {len(warns)} warning(s). The policy is wired and working.")
        else:
            print("All checks passed. The policy is wired and working.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
