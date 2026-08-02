#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.5
# summary: "Runs every deterministic gate on the my-lib -> team-lib -> public promotion chain and
#   returns one verdict: layer drift, registry resolution in all three layers, publication
#   freshness INCLUDING prune's question (files whose source is gone), the scrub blocklist over
#   freshness, the scrub blocklist over the released files, external-pack pins, version
#   staleness, harness results and push state. Read-only. The judgment half lives in the
#   update-ai-workspace-children skill."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Why this is a script and not a checklist
# ----------------------------------------
# Every one of these checks was run by hand on 2026-08-01 to clear the chain for release, and
# the sequence existed only in that conversation. A checklist in a skill file would be a list
# someone reads; this is a gate that runs. The skill supplies what the script deliberately
# withholds — which layer is right for an item, whether an ungraduated thing should graduate —
# because those are judgments and this is not.
#
# READ-ONLY by construction. It never publishes, commits, pushes or graduates. A verifier that
# can also mutate is one you cannot trust to tell you the truth about what it just did.
#
# Usage:
#   workspace_chain_audit.py            # human-readable report
#   workspace_chain_audit.py --json     # machine-readable
#   workspace_chain_audit.py --quiet    # verdict line only
#
# Exit: 0 all gates pass, 1 one or more BLOCKers, 2 the audit itself could not run.

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import workspace  # noqa: E402

WS = workspace()
TEAM = WS / "team-lib"
MINE = WS / "my-lib"
PUBLIC = WS / "projects" / "ai-workspace-reference"

GLOB_CHARS = "*?["


def _sh(*args, cwd=None, timeout=300):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as exc:                       # noqa: BLE001
        return 127, "", str(exc)


def _check(results, name, ok, detail, blocking=True):
    results.append({"check": name, "ok": bool(ok), "blocking": blocking, "detail": detail})
    return ok


def _registry_paths(root: Path, extra_root: Path | None = None):
    """Count registered paths that do not resolve.

    Glob PATTERNS are skipped: mirror.yaml states its mapping as globs, and treating those
    as files invents broken entries. Paths are tried against the layer root and, for
    workspace-scoped registries, the workspace root — an agent resolving an entry tries both.
    """
    try:
        import yaml
    except ImportError:
        return None, ["PyYAML missing"]
    checked, missing = 0, []
    for reg in sorted(glob.glob(str(root / "registry" / "*.yaml"))):
        try:
            data = yaml.safe_load(open(reg, encoding="utf-8"))
        except Exception:                          # noqa: BLE001
            missing.append(f"{os.path.basename(reg)}: UNPARSEABLE")
            continue

        def walk(node):
            nonlocal checked
            if isinstance(node, dict):
                p = node.get("path")
                if (isinstance(p, str) and p and not p.startswith(("http", "~"))
                        and not any(c in p for c in GLOB_CHARS)):
                    checked += 1
                    roots = [root] + ([extra_root] if extra_root else [])
                    if not any((r / p).exists() for r in roots):
                        missing.append(f"{os.path.basename(reg)}: {p}")
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(data)
    return checked, missing


def _scrub_released():
    """The blocklist, over the files actually in the public repo. The only true leak test."""
    try:
        import yaml
    except ImportError:
        return None, None, None
    spec = yaml.safe_load((TEAM / "registry" / "mirror.yaml").read_text(encoding="utf-8")) or {}
    terms = [t.lower() for ts in ((spec.get("publication") or {}).get("scrub") or {}).values()
             for t in ts]
    files = [p for p in PUBLIC.rglob("*") if p.is_file() and ".git/" not in str(p)]
    leaked, unscannable = [], []
    for p in files:
        try:
            low = p.read_text(encoding="utf-8").lower()
        except (UnicodeDecodeError, OSError):
            # Cannot be scrubbed, so cannot be cleared. Counted, not silently skipped:
            # a binary can carry a client logo no content gate would ever see.
            unscannable.append(str(p.relative_to(PUBLIC)))
            low = ""
        if any(t in low for t in terms):
            leaked.append(str(p.relative_to(PUBLIC)))
        # Path names are published too, and carry client names as readily as bodies do.
        if any(t in str(p.relative_to(PUBLIC)).lower() for t in terms):
            leaked.append(str(p.relative_to(PUBLIC)) + " (in the PATH)")
    return len(files), leaked, unscannable


def _git_state(repo: Path):
    if not (repo / ".git").exists():
        return None
    _, ahead, _ = _sh("git", "-C", str(repo), "rev-list", "--count", "@{u}..HEAD")
    _, dirty, _ = _sh("git", "-C", str(repo), "status", "--porcelain")
    return {"ahead": (ahead.strip() or "?"), "dirty": len([x for x in dirty.splitlines() if x])}


def run() -> dict:
    results: list[dict] = []
    info: dict = {}

    if not TEAM.is_dir():
        return {"status": "error", "error": f"no team-lib at {TEAM}"}

    # State the subject, and refuse to be quietly wrong about it.
    #
    # WS comes from agent_paths.workspace(), not from this file's location. Run from a fresh
    # clone of the PUBLIC repo it printed PASS while auditing ~/ai-workspace — a verdict about
    # a workspace it was not in. (layer_drift_scan errored honestly in the same clone; one of
    # the two was lying about its subject.) Reviewed 2026-08-01.
    info["workspace"] = str(WS)
    here = Path(__file__).resolve()
    # String-prefix matching passed for any sibling directory sharing the prefix
    # (~/ai-workspace-clone, ~/ai-workspace.bak). Compare path components.
    inside = WS.resolve() in here.parents
    _check(results, "auditing the workspace this script lives in", inside,
           f"workspace={WS}" + ("" if inside else
                                f" but this script is at {here} — the verdict below describes "
                                f"{WS}, NOT the tree you are standing in"))

    # --- 0. which branch are we even auditing? -----------------------------------
    #
    # Everything below runs the tools OUT OF the shared checkout, so the audit describes
    # whatever branch that tree happens to be on. Measured 2026-08-01: team-lib sat on a
    # peer's feature branch, the audit ran that branch's (unguarded) publisher, and reported
    # a confident PASS about a state nobody had reviewed. An audit that does not say what it
    # audited is worse than no audit — it is reassurance with no referent.
    rc, br, _ = _sh("git", "-C", str(TEAM), "branch", "--show-current")
    branch = br.strip()
    info["team_lib_branch"] = branch
    _check(results, "team-lib is on main", branch == "main",
           f"on '{branch or 'DETACHED HEAD / not a git tree'}'" + ("" if branch == "main" else
                               " — commits land here, and publication would ship THIS branch. "
                               "Do Phases 1-2, then stop before publishing."))

    # --- 1. my-lib <-> team-lib -------------------------------------------------
    rc, out, _ = _sh(sys.executable, str(TEAM / "executions" / "layer_drift_scan.py"),
                     "--json", "--severity", "low")
    try:
        drift = json.loads(out)
        summary = drift.get("summary", {})
        actionable = summary.get("actionable", -1)
        by_kind = summary.get("by_kind", {})
        info["drift"] = summary
        _check(results, "layer drift (mirrored items agree)", actionable == 0,
               f"{actionable} actionable; {by_kind.get('ungraduated', 0)} ungraduated "
               f"(ungraduated is NORMAL — my-lib is a laboratory, not a source mirror)")
    except ValueError:
        _check(results, "layer drift (mirrored items agree)", False, "scan did not return JSON")

    # --- 2. internal consistency: every index resolves ---------------------------
    for label, root, extra in (("my-lib", MINE, None), ("team-lib", TEAM, WS),
                               ("public", PUBLIC / "team-lib", PUBLIC)):
        if not root.is_dir():
            _check(results, f"registry resolves: {label}", False, f"missing layer at {root}")
            continue
        checked, missing = _registry_paths(root, extra)
        if checked is None:
            _check(results, f"registry resolves: {label}", False, "PyYAML missing", blocking=False)
        else:
            # `0 paths, 0 unresolved` is not a pass — it is a layer with no registry at all.
            _check(results, f"registry resolves: {label}", (not missing) and checked > 0,
                   f"{checked} paths, {len(missing)} unresolved"
                   + (" — NO registry entries found at all; this check had no subject"
                      if checked == 0 else "")
                   + (f" — {', '.join(missing[:4])}" if missing else ""))

    # --- 3. publication is current and clean -------------------------------------
    #
    # These two run the publisher against the CHECKED-OUT tree, so off main they compare the
    # public repo to the wrong source. Reporting PASS there is worse than reporting nothing:
    # it is the release gate greening on a comparison nobody asked for. Same defect this file
    # already fixed in the publisher and the version gate — a probe that cannot reach its
    # subject must say so, not answer about a substitute.
    if branch != "main":
        for name in ("public layer is current",
                     "publication refuses nothing (no blocked files)"):
            _check(results, name, False,
                   f"UNKNOWN — cannot compare: team-lib is on "
                   f"{branch or 'an UNDETERMINED branch (detached HEAD?)'}, so the publisher "
                   f"would read that state, not main", blocking=False)
    else:
        rc, out, _ = _sh(sys.executable, str(TEAM / "executions" / "publish_public_reference.py"))
        would_write = "written/updated : 0" in out
        _check(results, "public layer is current", would_write,
               "publish dry-run would write nothing" if would_write
               else "publish dry-run WOULD write — run publish_public_reference.py --apply")
        # Ask prune's question too. Orphans inside included trees are prune's territory,
        # and nothing in the chain was running prune — so "the public layer is current"
        # was true of additions and silent about deletions.
        _rc, pout, _ = _sh(sys.executable,
                           str(TEAM / "executions" / "publish_public_reference.py"), "--prune")
        stale_gone = "pruned          : 0" in pout
        _check(results, "no files in public whose source is gone", stale_gone,
               "prune dry-run finds nothing to remove" if stale_gone
               else "prune dry-run WOULD remove files — run publish_public_reference.py "
                    "--apply --prune")
        refused = "refused (leak)  : 0" not in out
        _check(results, "publication refuses nothing (no blocked files)", not refused,
               "a file still carries a blocked identifier after generalization" if refused
               else "no refusals")

    total, leaked, unscannable = _scrub_released()
    if total is None:
        _check(results, "no proprietary material in the public repo", False,
               "could not read the blocklist", blocking=False)
    else:
        info["public_files"] = total
        _check(results, "no proprietary material in the public repo", not leaked,
               f"{total} released files scanned (content AND path), {len(leaked)} leaking"
               + (f" — {', '.join(leaked[:4])}" if leaked else ""))
        # Undecodable files cannot be scrubbed, so they cannot be CLEARED either. Reported
        # rather than silently skipped: a binary can carry a client logo no gate would see.
        _check(results, "every released file was actually scannable", not unscannable,
               f"{len(unscannable)} undecodable file(s) — unscannable, therefore uncleared"
               + (f": {', '.join(unscannable[:3])}" if unscannable else ""), blocking=False)

    # --- 4. third-party pins ------------------------------------------------------
    pins = TEAM / "_admin" / "update_external_pack_pins.sh"
    if pins.is_file():
        rc, out, _ = _sh("bash", str(pins), "--check")
        _check(results, "external pack pins current", rc == 0,
               (out.strip().splitlines() or ["?"])[-1].strip())

    # --- 5. versions at the publish boundary --------------------------------------
    vg = TEAM / "executions" / "version_gate.py"
    if vg.is_file():
        # Pass the repo explicitly: version_gate defaults to os.getcwd(), which it inherits
        # from whoever launched the audit — run from /tmp it reported a vacuous empty result.
        rc, out, _ = _sh(sys.executable, str(vg), "--reconcile", "--dry-run", cwd=str(TEAM))
        try:
            n = len(json.loads(out).get("bumped", []))
        except ValueError:
            n = -1
        _check(results, "versions current for the publish boundary", n == 0,
               f"{n} file(s) changed without a version bump (the push hook fixes this)",
               blocking=False)

    # --- 6. the harnesses ---------------------------------------------------------
    # A guarded `if path.is_file()` meant deleting a harness removed its line entirely and
    # the audit still said PASS — the gate disappears and nothing mourns it. An expected
    # tool that is missing is a finding, not a skipped line.
    for h in ("test_layer_drift_scan.py", "test_version_gate.py"):
        path = TEAM / "harnesses" / h
        if not path.is_file():
            _check(results, f"harness: {h}", False, f"MISSING at {path} — a gate is gone")
            continue
        rc, out, err = _sh(sys.executable, str(path))
        _check(results, f"harness: {h}", rc == 0,
               (out or err).strip().splitlines()[-1][:100] if (out or err) else f"rc={rc}")

    # --- 7. install-time wiring ----------------------------------------------------
    rc, out, _ = _sh(sys.executable, str(TEAM / "executions" / "link_skills.py"), "--dry-run")
    linked_ok = " 0 would link," in out or "0 would link" in out
    _check(results, "every shared skill is invocable", linked_ok,
           (out.strip().splitlines() or ["?"])[-1][:120], blocking=False)
    _check(results, "status line installed", (Path.home() / ".claude" / "statusline.sh").exists(),
           "~/.claude/statusline.sh present", blocking=False)

    # --- 8. push state -------------------------------------------------------------
    info["repos"] = {}
    for label, repo in (("my-lib", MINE), ("team-lib", TEAM), ("public", PUBLIC)):
        st = _git_state(repo)
        if st:
            info["repos"][label] = st
    # "?" means no upstream — a repo nobody can pull from is not "pushed".
    unpushed = [k for k, v in info["repos"].items() if v["ahead"] != "0"]
    _check(results, "everything pushed", not unpushed,
           f"unpushed: {', '.join(unpushed)}" if unpushed else "all repos at origin",
           blocking=False)

    blockers = [r for r in results if not r["ok"] and r["blocking"]]
    warnings = [r for r in results if not r["ok"] and not r["blocking"]]
    return {
        "status": "ok",
        "verdict": "PASS" if not blockers else "BLOCKED",
        "blockers": len(blockers),
        "warnings": len(warnings),
        "checks": results,
        "info": info,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit the my-lib -> team-lib -> public chain.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    r = run()
    if r.get("status") != "ok":
        print(f"workspace_chain_audit: {r.get('error')}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, indent=2))
        return 0 if r["verdict"] == "PASS" else 1
    if not args.quiet:
        for c in r["checks"]:
            mark = "✅" if c["ok"] else ("❌" if c["blocking"] else "⚠️ ")
            print(f"  {mark} {c['check']}: {c['detail']}")
        print()
    print(f"CHAIN AUDIT: {r['verdict']} — {r['blockers']} blocker(s), {r['warnings']} warning(s)")
    return 0 if r["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
