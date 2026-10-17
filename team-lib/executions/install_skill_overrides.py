#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.0
# summary: "Installs the generated skill listing map (my-lib/config/claude-skill-overrides.json)
#   into ~/.claude/settings.json skillOverrides. Merges, never replaces; keeps and reports foreign
#   keys, including any in project .claude/settings*.json files. Dry-run by default; --apply locks,
#   backs up and writes atomically. The agent runs it with the owner's one-time approval."
# created: 2026-10-16
# last_updated: 2026-10-16
# maintainer: your-agent
# ---
"""Install the generated skill listing map into the user's Claude Code settings.

Who runs it: the agent, with the owner's one-time approval. ~/.claude/settings.json is a
protected path and auto mode blocks agent writes to it (correctly: settings carry permissions and
hooks), so the owner switches auto mode off for that one approval and the agent runs `--apply`.
The owner is never handed a command to type.

Ownership, so nothing is hidden forever and nothing of the operator's is dropped:
  * managed  — every key in the generated file (including "on"): set to the generated value
  * stale    — a key in the owned-keys state file that is no longer managed (the skill was
               removed or renamed): REMOVED, otherwise it would keep hiding a skill that is gone
  * foreign  — any other key (set by hand in settings.json): KEPT, and reported loudly so the
               second owner is visible rather than silently overwritten or dropped
  * project  — skillOverrides in a project's .claude/settings.json or settings.local.json under
               the workspace. Reported only, never touched. They matter: the harness reads project
               settings before user settings, and the /skills toggle writes the cwd project's
               settings.local.json, not this file (read from the 2.1.300 binary; medium
               confidence, it is minified code).
A managed key whose installed value differs is overwritten and listed, because the frontmatter
is the owner; to keep a hand toggle, put it in my-lib/config/skill-listing.yaml instead.

Usage:
    python3 install_skill_overrides.py            # dry-run: show what would change
    python3 install_skill_overrides.py --apply    # back up settings.json, then write
    python3 install_skill_overrides.py --self-check
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_skill_overrides as BSO  # noqa: E402

DEFAULT_SETTINGS = BSO.DEFAULT_SETTINGS


SKIP_DIRS = {".git", "node_modules", "runtime", "archive", "_archive", "_archived", ".venv",
             "__pycache__"}


def project_overrides(ws: Path = BSO.WORKSPACE, max_depth: int = 4) -> dict[str, list[str]]:
    """{settings file: [skillOverrides keys]} for every project-level Claude Code settings file
    under the workspace that carries skillOverrides. Read-only."""
    found: dict[str, list[str]] = {}
    ws = Path(ws)
    if not ws.is_dir():
        return found
    base = len(ws.parts)
    for root, dirs, _files in os.walk(ws):
        depth = len(Path(root).parts) - base
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and (d == ".claude" or not d.startswith("."))
                   and depth < max_depth]
        if Path(root).name != ".claude":
            continue
        for fn in ("settings.json", "settings.local.json"):
            f = Path(root) / fn
            if not f.is_file():
                continue
            so = (BSO._load_json(f).get("skillOverrides") or {})
            if isinstance(so, dict) and so:
                found[str(f)] = sorted(so)
    return found


def _digest(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def plan(generated: dict, owned: set, settings: dict) -> dict:
    """Pure merge. Returns {new, set, changed, removed, foreign, unchanged}."""
    cur = dict(settings.get("skillOverrides") or {})
    new = {k: v for k, v in cur.items() if not (k in owned and k not in generated)}
    removed = sorted(k for k in cur if k in owned and k not in generated)
    added = sorted(k for k in generated if k not in cur)
    changed = sorted(k for k in generated if k in cur and cur[k] != generated[k])
    new.update(generated)
    foreign = sorted(k for k in cur if k not in owned and k not in generated)
    return {"new": dict(sorted(new.items())), "set": added, "changed": changed,
            "removed": removed, "foreign": foreign,
            "unchanged": not (added or changed or removed)}


def run(apply: bool = False, repo: Path = BSO.DEFAULT_REPO,
        settings_path: Path = DEFAULT_SETTINGS, allow_stale: bool = False,
        ws: Path | None = BSO.WORKSPACE, _before_replace=None) -> dict:
    """Merge the generated map into settings.json.

    Returns {status, set, changed, removed, foreign, unchanged, wrote, backup} or
    {status: error, error}. Refuses: a stale generated file (unless allow_stale), a generated
    file with no `skillOverrides`, or a settings.json that is not valid JSON.
    """
    repo = Path(repo)
    gen_p, state_p = repo / BSO.OUT_REL, repo / BSO.STATE_REL
    try:
        gen = json.loads(gen_p.read_text(encoding="utf-8")).get("skillOverrides")
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error": f"cannot read {gen_p} ({exc.__class__.__name__}) — "
                                            f"run build_skill_overrides.py first"}
    if not isinstance(gen, dict) or not gen:
        return {"status": "error", "error": f"{gen_p} has no skillOverrides map"}
    if not allow_stale:
        chk = BSO.run("check", repo)
        if chk.get("status") == "ok" and chk["stale"]:
            return {"status": "error", "error": f"{gen_p} is STALE against the skills on disk — "
                                                f"run build_skill_overrides.py, then re-run this"}
    owned = set(BSO._load_json(state_p).get("owned") or []) | set(gen)

    # Write through a symlink to its target: os.replace on the link path would swap the link
    # for a plain file and silently detach whatever it pointed at.
    target = Path(os.path.realpath(settings_path))
    proj = project_overrides(ws) if ws else {}
    if not apply:
        return _plan_once(gen, owned, target, False, proj)
    # Two guards for read -> merge -> write. An flock serializes concurrent installer runs. Claude
    # Code does not take that lock, so the file's hash is re-read just before os.replace: if a
    # running session wrote settings.json meanwhile (an "always allow", /config), re-plan from the
    # new content instead of overwriting it; give up after 3 tries rather than lose its write.
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.skill-overrides.lock")
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(3):
            r = _plan_once(gen, owned, target, True, proj, _before_replace)
            if r.get("status") != "retry":
                return r
            _before_replace = None
        return {"status": "error", "error": f"{target} kept changing during the merge — nothing "
                                            f"written; run again when sessions are idle"}


def _plan_once(gen: dict, owned: set, target: Path, apply: bool, proj: dict,
               _before_replace=None) -> dict:
    """One read -> plan -> (write). Returns status retry when the file changed under us."""
    digest = _digest(target)
    if target.exists():
        try:
            settings = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": f"{target} is not valid JSON ({exc}) — refusing to touch it"}
        if not isinstance(settings, dict):
            return {"status": "error", "error": f"{target} is not a JSON object — refusing"}
    else:
        settings = {}
    p = plan(gen, owned, settings)
    out = {"status": "ok", **{k: p[k] for k in ("set", "changed", "removed", "foreign", "unchanged")},
           "wrote": False, "backup": None, "settings": str(target), "project": proj}
    if not apply or p["unchanged"]:
        return out
    settings["skillOverrides"] = p["new"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        bak = target.with_name(f"{target.name}.bak-{datetime.datetime.now():%y%m%d-%H%M%S}-skill-overrides")
        shutil.copy2(target, bak)
        out["backup"] = str(bak)
    tmp = target.with_name(f".{target.name}.skill-overrides.tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))          # validate before swapping in
    if _before_replace:
        _before_replace(target)                           # self-check hook: simulate a racer
    if _digest(target) != digest:
        tmp.unlink(missing_ok=True)
        if out["backup"]:
            Path(out["backup"]).unlink(missing_ok=True)
        return {"status": "retry"}
    os.replace(tmp, target)
    out["wrote"] = True
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write (default is a dry-run)")
    ap.add_argument("--repo", default=str(BSO.DEFAULT_REPO))
    ap.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    ap.add_argument("--allow-stale", action="store_true",
                    help="install even if the generated file is behind the skills on disk")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()
    r = run(a.apply, Path(a.repo), Path(a.settings), a.allow_stale)
    if r["status"] != "ok":
        print(f"install_skill_overrides: ERROR — {r['error']}", file=sys.stderr)
        return 2
    tag = "" if a.apply else "[dry-run] "
    if r["unchanged"]:
        print(f"{tag}skillOverrides already current in {r['settings']}")
    else:
        print(f"{tag}{r['settings']}: {len(r['set'])} key(s) added, {len(r['changed'])} changed, "
              f"{len(r['removed'])} stale owned key(s) removed")
        for k in ("changed", "removed"):
            if r[k]:
                print(f"  {k}: {', '.join(r[k][:12])}{' …' if len(r[k]) > 12 else ''}")
    if r["foreign"]:
        print(f"  ⚑ FOREIGN keys kept (set outside this tool, e.g. via /skills): "
              f"{', '.join(r['foreign'])}\n    To make one permanent, move it into "
              f"my-lib/config/skill-listing.yaml so the generated map owns it.")
    for f, keys in (r.get("project") or {}).items():
        print(f"  ⚑ PROJECT skillOverrides (read before user settings; not touched): {f}: "
              f"{', '.join(keys[:8])}{' …' if len(keys) > 8 else ''}")
    if r["backup"]:
        print(f"  backup: {r['backup']}")
    if not a.apply and not r["unchanged"]:
        print("  --apply writes it (the agent runs it with the owner's one-time approval); "
              "then restart Claude Code sessions")
    return 0


def self_check() -> int:
    """Two-sided, against a temp HOME — never the real settings.json."""
    import tempfile
    ok = True

    def fail(msg):
        nonlocal ok
        print(f"FAIL: {msg}")
        ok = False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "my-lib"
        (repo / "config").mkdir(parents=True)
        (repo / BSO.OUT_REL).write_text(json.dumps({"skillOverrides": {
            "a": "on", "b": "user-invocable-only", "c": "name-only"}}))
        (repo / BSO.STATE_REL).write_text(json.dumps({"owned": ["a", "b", "c", "gone"]}))
        sp = root / "real-settings.json"
        link = root / "settings.json"
        link.symlink_to(sp)
        sp.write_text(json.dumps({"model": "opus", "hooks": {"X": [1]}, "skillOverrides": {
            "gone": "user-invocable-only", "mine": "off", "c": "on"}}))
        before = sp.read_text()

        r = run(False, repo, link, allow_stale=True, ws=None)
        if r["status"] != "ok" or r["wrote"] or sp.read_text() != before:
            fail(f"dry-run wrote or failed: {r}")
        r = run(True, repo, link, allow_stale=True, ws=None)
        got = json.loads(sp.read_text())
        so = got.get("skillOverrides", {})
        if so != {"a": "on", "b": "user-invocable-only", "c": "name-only", "mine": "off"}:
            fail(f"merged map wrong: {so}")
        if got.get("model") != "opus" or got.get("hooks") != {"X": [1]}:
            fail("other settings keys were not preserved")
        if r["removed"] != ["gone"] or r["foreign"] != ["mine"] or r["changed"] != ["c"]:
            fail(f"classification wrong: {r}")
        if not r["backup"] or json.loads(Path(r["backup"]).read_text()) != json.loads(before):
            fail("no faithful backup was taken")
        if not link.is_symlink():
            fail("writing replaced the settings symlink with a plain file")
        if run(True, repo, link, allow_stale=True, ws=None)["wrote"]:
            fail("a second apply was not a no-op")

        # a concurrent write between read and replace must not be lost
        (repo / BSO.OUT_REL).write_text(json.dumps({"skillOverrides": {
            "a": "name-only", "b": "user-invocable-only", "c": "name-only"}}))
        state = {"n": 0}

        def racer(t: Path):
            if state["n"] == 0:
                d = json.loads(t.read_text())
                d["permissions"] = {"allow": ["Bash(ls)"]}
                t.write_text(json.dumps(d))
            state["n"] += 1
        r = run(True, repo, link, allow_stale=True, ws=None, _before_replace=racer)
        got = json.loads(sp.read_text())
        if got.get("permissions") != {"allow": ["Bash(ls)"]} or got["skillOverrides"].get("a") != "name-only":
            fail(f"a write landing mid-merge was lost or the merge not re-planned: {got}, {r}")
        # the merge must wait while another installer holds the lock
        import threading
        lockf = link.parent / ".real-settings.json.skill-overrides.lock"
        (repo / BSO.OUT_REL).write_text(json.dumps({"skillOverrides": {
            "a": "on", "b": "user-invocable-only", "c": "name-only"}}))
        with open(lockf, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            th = threading.Thread(target=run, args=(True, repo, link), kwargs={
                "allow_stale": True, "ws": None})
            th.start()
            th.join(0.5)
            if not th.is_alive():
                fail("the merge did not wait for a held lock around read-merge-write")
            fcntl.flock(held, fcntl.LOCK_UN)
        th.join(10)
        if json.loads(sp.read_text())["skillOverrides"].get("a") != "on":
            fail("the merge waiting on the lock did not complete after release")

        # project-level skillOverrides are reported, never touched
        pws = root / "ws"
        (pws / "projects/demo/.claude").mkdir(parents=True)
        pf = pws / "projects/demo/.claude/settings.local.json"
        pf.write_text(json.dumps({"skillOverrides": {"x-skill": "off"}}))
        (pws / "node_modules/.claude").mkdir(parents=True)
        (pws / "node_modules/.claude/settings.json").write_text(
            json.dumps({"skillOverrides": {"vendored": "off"}}))
        r = run(False, repo, link, allow_stale=True, ws=pws)
        if r.get("project") != {str(pf): ["x-skill"]}:
            fail(f"project skillOverrides not reported exactly (vendored dirs skipped): {r.get('project')}")
        if json.loads(pf.read_text()) != {"skillOverrides": {"x-skill": "off"}}:
            fail("a project settings file was modified")

        sp.write_text("{not json")
        if run(True, repo, link, allow_stale=True, ws=None)["status"] != "error":
            fail("invalid settings JSON was not refused")
        if sp.read_text() != "{not json":
            fail("invalid settings JSON was modified")
        (repo / BSO.OUT_REL).write_text(json.dumps({"other": {}}))
        if run(False, repo, link, allow_stale=True, ws=None)["status"] != "error":
            fail("a generated file with no skillOverrides was accepted")

    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
