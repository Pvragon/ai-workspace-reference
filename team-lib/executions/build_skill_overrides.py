#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.1
# summary: "Single writer of the Claude Code skill listing map. Resolves the listing of every skill
#   the harness sees, plus the built-in (bundled) skills declared in a sidecar, and writes
#   my-lib/config/claude-skill-overrides.json with an owned-keys state file. --check exits 1 when
#   stale; --installed diffs against settings.json; every run simulates the listing budget."
# created: 2026-10-16
# last_updated: 2026-10-16
# maintainer: your-agent
# ---
"""Render each skill's `listing` into Claude Code's `skillOverrides` map.

Why a generated file and not a hand-edited setting: the listing is a fact about each skill, owned
by its SKILL.md frontmatter (or a sidecar for files we may not edit). `skillOverrides` in
settings.json is a second rendering of that fact. Two hand-kept copies drift; one generated copy
plus a `--check` cannot drift silently.

Why the harness directory and not the repo: the harness lists what is in ~/.claude/skills (a real
directory of per-skill links since 2026-10-12, holding two Omarchy skills that live nowhere in
the workspace) plus the synced `anthropic-skills:*` tree. A key emitted for a skill the harness
cannot see is a no-op; a skill the harness sees with no key is listed in full. So membership is
read from the harness, and resolution from the registry-map policy of the harness-tree layer
(my-lib). Skills present in my-lib/skills but not linked into the harness are reported as
`unlinked` (run link_skills.py).

Bundled skills (Claude Code's own: dataviz, code-review, update-config, ...) are on no disk this
tool can read, but the harness charges their FULL description against the budget before any of
ours gets one (2.1.300 fitter: bundled and name-only entries are paid first, the rest are granted
by usage priority while room lasts). Measured 2026-10-16: at a 200k window they alone left every
`on` skill name-only. So they are declared in the my-lib sidecar with `provenance: bundled` and
managed like any other key (default name-only, via `listing_defaults.bundled`).

Keys are HARNESS names: the folder name (`ext-pdf`, never the frontmatter `pdf`, which would hit
`anthropic-skills:pdf` instead — proven in Phase 0), and `anthropic-skills:<dir>` for synced
skills. Every managed key is written, `"on"` included, so the installer can tell a key it owns
from one the operator set by hand in /skills.

Usage:
    python3 build_skill_overrides.py              # regenerate the JSON + state
    python3 build_skill_overrides.py --check      # exit 1 if the committed JSON is stale
    python3 build_skill_overrides.py --installed  # exit 1 if settings.json differs from it
    python3 build_skill_overrides.py --self-check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_registry as BR  # noqa: E402  one resolver, not two

WORKSPACE = BR.WORKSPACE
DEFAULT_REPO = WORKSPACE / "my-lib"
DEFAULT_HARNESS = Path.home() / ".claude" / "skills"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
OUT_REL = "config/claude-skill-overrides.json"
STATE_REL = "config/claude-skill-overrides.state.json"
SYNCED_PREFIX = "anthropic-skills:"
# The layer this script ships in. Its own config/registry-map.yaml skills spec is the DEFAULT
# listing policy: a teammate or a public cloner has an empty my-lib/config/, and without a
# fallback every listing tool exited 2 there, so the feature never turned on for anyone but the
# one machine whose my-lib declared a policy. my-lib's own policy still wins when present.
TEAM_LIB = Path(__file__).resolve().parent.parent


def harness_policy(repo: Path, default_repo: Path = TEAM_LIB) -> tuple[dict | None, str | None]:
    """(policy, where it came from). The repo's own skills spec first, else team-lib's default."""
    policy = BR.policy_for_repo(repo)
    if policy:
        return policy, f"{repo}/config/registry-map.yaml"
    if default_repo and Path(default_repo).resolve() != Path(repo).resolve():
        policy = BR.policy_for_repo(Path(default_repo))
        if policy:
            return policy, f"{default_repo}/config/registry-map.yaml (default: {repo.name} declares none)"
    return None, None

# The harness budget for the whole skill listing, in characters: context tokens x chars-per-token
# x skillListingBudgetFraction (0.01). ⚑ chars-per-token is 3, not 4, for every current model:
# 2.1.300's `Zg(model)` returns 4 only for a fixed legacy list (claude-3-*, opus/sonnet 4.0-4.6,
# haiku-4-5) and 3 for anything else (opus-5-5, haiku-5-5, ...). So 6,000 at a 200k window and
# 30,000 at 1M. The earlier 8k/40k figures used 4 and over-promised by a third (measured
# 2026-10-16: a map the 8k figure called "fits" left 2 of 13 `on` skills name-only at 200k).
# Per-description cap 1536.
BUDGETS = {"200k window": 6_000, "1M window": 30_000}
DESC_CAP = 1536
BUNDLED = "bundled"


def bundled_entries(policy: dict) -> dict[str, dict]:
    """{name: sidecar entry} for every sidecar key declared `provenance: bundled` (first sidecar
    wins). These are Claude Code's built-in skills: no SKILL.md on disk, still in the listing."""
    out: dict[str, dict] = {}
    for _, entries in policy["sidecars"]:
        for k, ent in entries.items():
            if isinstance(ent, dict) and ent.get("provenance") == BUNDLED and k not in out:
                out[k] = ent
    return out


# ---------------------------------------------------------------------------- enumerate
def harness_skills(harness: Path) -> dict[str, Path]:
    """{harness_name: SKILL.md path as the harness reaches it} — top-level entries holding a
    SKILL.md, plus synced skills at synced/<account>/<skill>/SKILL.md."""
    found: dict[str, Path] = {}
    if not harness.is_dir():
        return found
    for entry in sorted(harness.iterdir()):
        if entry.name == "synced":
            for sk in sorted(entry.glob("*/*/SKILL.md")):
                found[SYNCED_PREFIX + sk.parent.name] = sk
            continue
        if (entry / "SKILL.md").is_file():
            found[entry.name] = entry / "SKILL.md"
    return found


def unlinked_skills(repo: Path, harness: Path, seen: dict) -> list[str]:
    """Skills in the repo's skills/ tree the harness cannot see. Only meaningful when the harness
    directory is a REAL directory; a symlink to the repo's skills/ sees everything by definition."""
    if harness.is_symlink() or not (repo / "skills").is_dir():
        return []
    return sorted(e.name for e in (repo / "skills").iterdir()
                  if (e / "SKILL.md").is_file() and e.name not in seen)


# ---------------------------------------------------------------------------- estimate
def _desc(fm: dict) -> str:
    s = " ".join(str(fm.get("description") or fm.get("summary") or "").split())
    w = fm.get("when_to_use") or fm.get("when-to-use")
    if w:
        s += " - " + " ".join(str(w).split())
    return s[:DESC_CAP]


def listing_chars(name: str, fm: dict, listing: str, desc_chars: int | None = None) -> int:
    """Characters one skill costs in the listing, in the binary's `- name: description` line
    format (`- name (frontmatter-name): ...` when the two differ), plus its newline. Hidden skills
    cost 0. `desc_chars` stands in for the description of a bundled skill (none on disk)."""
    if listing in ("user-only", "off"):
        return 0
    if listing == "name-only":
        return len(f"- {name}") + 1
    fm_name = fm.get("name")
    shown = name if fm_name in (None, name) or name.startswith(SYNCED_PREFIX) else f"{name} ({fm_name})"
    desc = _desc(fm) if desc_chars is None else "x" * min(int(desc_chars), DESC_CAP)
    return len(f"- {shown}: {desc}") + 1


def simulate_budget(rows: list[dict], budget: int) -> dict:
    """Replay the 2.1.300 listing fitter (`Xln`) for one budget.

    Under budget: everything is shown as configured. Over it: name-only entries and EVERY bundled
    entry are paid in full first; the remaining described (`on`) entries get their description by
    usage priority while room lasts. Usage priority is unknowable here, so the answer is the
    worst case: `all_on_described` is True only if every `on` description fits at once.
    """
    shown = [r for r in rows if r["chars"]]
    total = sum(r["chars"] for r in shown)
    if total <= budget:
        return {"budget": budget, "chars": total, "mode": "fits", "room": budget - total,
                "need": 0, "all_on_described": True}
    paid_first = sum(r["chars"] if (r["source"] == BUNDLED or r["listing"] == "name-only")
                     else r["name_chars"] for r in shown)
    room = budget - paid_first
    need = sum(r["chars"] - r["name_chars"] for r in shown
               if r["listing"] == "on" and r["source"] != BUNDLED)
    return {"budget": budget, "chars": total, "mode": "priority", "room": room, "need": need,
            "all_on_described": need <= room}


# ---------------------------------------------------------------------------- compute
def compute(repo: Path = DEFAULT_REPO, harness: Path = DEFAULT_HARNESS,
            default_repo: Path = TEAM_LIB) -> dict:
    """Resolve every harness-visible skill. Pure: reads, never writes.

    Returns {status, overrides, rows, unlinked, orphans, problems, estimate, counts} or an error.
    """
    policy, policy_source = harness_policy(repo, default_repo)
    if not policy:
        return {"status": "error", "error": f"{repo}/config/registry-map.yaml declares no skills "
                                            f"listing policy (listing_sidecars / listing_defaults), "
                                            f"and no default was found in {default_repo}/config"}
    if policy["errors"]:
        return {"status": "error", "error": "; ".join(policy["errors"])}
    seen = harness_skills(harness)
    bundled = {k: v for k, v in bundled_entries(policy).items() if k not in seen}
    overrides, rows, problems = {}, [], []
    total, counts = 0, {"on": 0, "name-only": 0, "user-only": 0, "off": 0}
    for name, sk in list(seen.items()) + [(k, None) for k in sorted(bundled)]:
        if sk is None:                      # bundled: no file; the sidecar entry is all we have
            fm, src, desc_chars = {}, BUNDLED, bundled[name].get("desc_chars")
        else:
            fm = BR.read_frontmatter(sk)
            fm = fm if isinstance(fm, dict) else {}
            src, desc_chars = BR.provenance(repo, sk), None
        r = BR.resolve_listing(name, fm, src, policy)
        for bucket, msg in r["problems"]:
            if bucket != "category_missing":
                problems.append((bucket, msg))
        listing = r["listing"]
        if listing is None:
            problems.append(("unresolved", f"{name} ({src}): no listing and no default"))
            continue
        if src == BUNDLED and listing == "on" and desc_chars is None:
            problems.append(("bundled_unsized", f"{name}: bundled and `on` but no desc_chars — "
                                                f"the budget simulation counts its name only"))
        overrides[name] = BR.HARNESS_LISTING[listing]
        counts[listing] += 1
        cost = listing_chars(name, fm, listing, desc_chars)
        total += cost
        rows.append({"name": name, "source": src, "listing": listing,
                     "listing_source": r["listing_source"], "category": r["category"],
                     "chars": cost, "name_chars": (len(f"- {name}") + 1) if cost else 0})
    sidecar_keys = {k for _, entries in policy["sidecars"] for k in entries} - set(bundled)
    return {"status": "ok", "policy_source": policy_source,
            "overrides": dict(sorted(overrides.items())), "rows": rows,
            "unlinked": unlinked_skills(repo, harness, seen),
            "orphans": sorted(sidecar_keys - set(seen)),
            "problems": problems, "counts": counts, "bundled": sorted(bundled),
            "estimate": {"chars": total,
                         "budgets": {k: dict(simulate_budget(rows, v),
                                             pct=round(100 * total / v, 1))
                                     for k, v in BUDGETS.items()}}}


def render(overrides: dict) -> str:
    return json.dumps({"skillOverrides": overrides}, indent=2, sort_keys=True) + "\n"


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def installed_diff(managed: dict, owned: set, settings: Path) -> dict:
    """How settings.json's skillOverrides differs from the generated map.
    missing: managed key absent or with another value; stale: a key we owned that is no longer
    managed; foreign: a key we never wrote (set via /skills) — kept by the installer, reported."""
    cur = (_load_json(settings).get("skillOverrides") or {}) if settings.exists() else {}
    return {"missing": sorted(k for k, v in managed.items() if cur.get(k) != v),
            "stale": sorted(k for k in cur if k in owned and k not in managed),
            "foreign": sorted(k for k in cur if k not in owned and k not in managed)}


# ---------------------------------------------------------------------------- run
def run(mode: str = "write", repo: Path = DEFAULT_REPO, harness: Path = DEFAULT_HARNESS,
        settings: Path = DEFAULT_SETTINGS) -> dict:
    """mode: write | check | installed | dry-run.

    Returns compute()'s dict plus: out, state, stale (bool: committed JSON differs from a
    rebuild), wrote (bool), and for `installed` an `installed` diff dict.
    """
    repo, harness = Path(repo), Path(harness)
    res = compute(repo, harness)
    if res["status"] != "ok":
        return res
    out, state = repo / OUT_REL, repo / STATE_REL
    rendered = render(res["overrides"])
    current = out.read_text(encoding="utf-8") if out.exists() else ""
    prev_owned = set(_load_json(state).get("owned") or [])
    owned = sorted(prev_owned | set(res["overrides"]))
    res.update(out=str(out), state=str(state), stale=current != rendered, wrote=False)
    if mode == "write" and (res["stale"] or set(owned) != prev_owned):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        # OWNED keys accumulate: a skill removed from the harness drops out of `overrides`, but
        # its key is still ours, so the installer can delete it from settings.json rather than
        # mistake it for a /skills toggle and keep hiding a skill that no longer exists.
        state.write_text(json.dumps({"owned": owned}, indent=2) + "\n", encoding="utf-8")
        res["wrote"] = True
    if mode == "installed":
        res["installed"] = installed_diff(res["overrides"], set(owned), Path(settings))
    return res


def _print(res: dict, mode: str, verbose: bool) -> None:
    c, est = res["counts"], res["estimate"]
    print(f"build_skill_overrides: {sum(c.values())} harness skill(s) — "
          f"{c['on']} on, {c['name-only']} name-only, {c['user-only']} user-only, {c['off']} off")
    if res.get("policy_source"):
        print(f"  listing policy: {res['policy_source']}")
    b = est["budgets"]
    print(f"  estimated listing: {est['chars']:,} chars — "
          + ", ".join(f"{v['pct']}% of the {k} budget ({v['budget']:,})" for k, v in b.items())
          + f"  [includes {len(res.get('bundled') or [])} bundled; excludes plugin and "
            f"cwd-project skills]")
    for k, v in b.items():
        if v["mode"] == "fits":
            print(f"  {k}: fits, every description shown ({v['room']:,} chars spare)")
        else:
            verdict = ("every `on` description fits" if v["all_on_described"]
                       else "⚑ NOT every `on` description fits — demote one, or name-only a bundled skill")
            print(f"  {k}: over budget, priority mode — `on` descriptions need {v['need']:,}, "
                  f"room {v['room']:,}: {verdict}")
    if res["unlinked"]:
        print(f"  ! unlinked — in my-lib/skills but NOT visible to the harness "
              f"(run link_skills.py): {', '.join(res['unlinked'])}")
    if res["orphans"]:
        print(f"  ℹ sidecar keys with no harness skill on this machine: {len(res['orphans'])}"
              + (f" ({', '.join(res['orphans'][:8])})" if verbose or len(res['orphans']) <= 8 else ""))
    by = {}
    for bucket, msg in res["problems"]:
        by.setdefault(bucket, []).append(msg)
    for bucket, msgs in sorted(by.items()):
        print(f"  {bucket}: {len(msgs)}")
        for m in msgs[: (len(msgs) if verbose else 5)]:
            print(f"    - {m}")
    if mode == "installed":
        d = res["installed"]
        for k, label in (("missing", "managed key not installed / different value"),
                         ("stale", "owned key no longer managed — installer will remove"),
                         ("foreign", "⚑ FOREIGN key (set outside this tool) — installer keeps it")):
            if d[k]:
                print(f"  {label}: {len(d[k])} ({', '.join(d[k][:8])}{' …' if len(d[k]) > 8 else ''})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if the committed JSON is stale")
    g.add_argument("--installed", action="store_true",
                   help="exit 1 if ~/.claude/settings.json skillOverrides differs")
    g.add_argument("--dry-run", action="store_true", help="resolve and report; write nothing")
    g.add_argument("--self-check", action="store_true")
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--harness-dir", default=str(DEFAULT_HARNESS))
    ap.add_argument("--settings", default=str(DEFAULT_SETTINGS))
    ap.add_argument("--quiet", action="store_true", help="one status line only")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()
    mode = "check" if a.check else "installed" if a.installed else "dry-run" if a.dry_run else "write"
    res = run(mode, Path(a.repo), Path(a.harness_dir), Path(a.settings))
    if res["status"] != "ok":
        print(f"build_skill_overrides: ERROR — {res['error']}", file=sys.stderr)
        return 2
    if mode == "check":
        if res["stale"]:
            # Worded as what needs doing, not a command to paste: the agent runs it (a standing
            # rule — the owner is never handed a command to type).
            print(f"skill listing map STALE: {OUT_REL} differs from a rebuild — the agent "
                  f"regenerates it with {Path(__file__).name} (writes my-lib/config only)")
            return 1
        if not a.quiet:
            print(f"skill listing map current ({len(res['overrides'])} keys)")
        return 0
    if mode == "installed":
        d = res["installed"]
        bad = d["missing"] or d["stale"]
        if a.quiet:
            if bad or res["stale"]:
                print("skill listing out of date: the agent runs install_skill_overrides.py "
                      "--apply (one settings.json approval)")
            return 1 if (bad or res["stale"]) else 0
        _print(res, mode, a.verbose)
        if res["stale"]:
            print(f"  ! {OUT_REL} itself is stale — regenerate before installing")
        return 1 if (bad or res["stale"]) else 0
    if not a.quiet:
        _print(res, mode, a.verbose)
    print(f"  {'wrote' if res['wrote'] else 'unchanged' if mode == 'write' else 'dry-run, not written'}"
          f": {res['out']}")
    return 0


# ---------------------------------------------------------------------------- self-check
def self_check() -> int:
    """Two-sided: a correct tree renders every key; staleness, drift and foreign keys MUST show."""
    import tempfile
    ok = True

    def fail(msg):
        nonlocal ok
        print(f"FAIL: {msg}")
        ok = False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "my-lib"
        (repo / "skills").mkdir(parents=True)
        (repo / "config").mkdir()
        harness = root / "home" / "skills"
        harness.mkdir(parents=True)

        def skill(d: Path, extra: str = "", desc: str = "Does a thing.") -> Path:
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(f"---\nname: {d.name}\ndescription: {desc}\n{extra}---\n")
            return d

        own = skill(repo / "skills" / "daily", "listing: on\n", desc="Daily driver skill.")
        rare = skill(repo / "skills" / "rare")                     # internal, no listing
        skill(repo / "skills" / "notlinked", "listing: on\n")     # repo-only, never linked
        ext = skill(root / "team-lib" / "skills" / "_external" / "p" / "pdf", "", "PDF things.")
        sync = skill(harness / "synced" / "acct" / "docx", "", "Docx things.")
        for name, tgt in (("daily", own), ("rare", rare), ("ext-pdf", ext)):
            (harness / name).symlink_to(tgt, target_is_directory=True)
        (repo / "config" / "skill-listing.yaml").write_text(
            "skills:\n  anthropic-skills:docx: {listing: name-only}\n  gone-skill: {listing: 'on'}\n")
        (repo / "config" / "registry-map.yaml").write_text(json.dumps({"registries": {"skills": {
            "derived": ["listing"], "listing_sidecars": ["config/skill-listing.yaml"],
            "listing_defaults": {"external": "user-only", "synced": "user-only",
                                 "local": "name-only", "team": "name-only"},
            "listing_required": ["local", "team"]}}}))

        r = run("write", repo, harness, root / "settings.json")
        if r["status"] != "ok":
            fail(f"run errored: {r}")
            print("self-check: FAIL")
            return 1
        want = {"daily": "on", "rare": "name-only", "ext-pdf": "user-invocable-only",
                "anthropic-skills:docx": "name-only"}
        if r["overrides"] != want:
            fail(f"overrides {r['overrides']} != {want}")
        written = json.loads((repo / OUT_REL).read_text())
        if written.get("skillOverrides", {}).get("daily") != "on":
            fail("an `on` key was omitted — the installer could not tell it from a /skills toggle")
        if r["unlinked"] != ["notlinked"]:
            fail(f"repo skill missing from the harness not reported as unlinked: {r['unlinked']}")
        if r["orphans"] != ["gone-skill"]:
            fail(f"sidecar key with no harness skill not reported: {r['orphans']}")
        if not any(b == "listing_missing" and "rare" in m for b, m in r["problems"]):
            fail("an internal skill with no listing was not reported")
        exp = (len("- daily: Daily driver skill.") + 1) + (len("- rare") + 1) \
            + (len("- anthropic-skills:docx") + 1)
        if r["estimate"]["chars"] != exp:
            fail(f"listing estimate {r['estimate']['chars']} != {exp}")

        # idempotent: an immediate --check is clean ...
        if run("check", repo, harness)["stale"]:
            fail("--check reported stale right after a write")
        # ... and a frontmatter change MUST make it stale
        (rare / "SKILL.md").write_text("---\nname: rare\ndescription: x\nlisting: on\n---\n")
        if not run("check", repo, harness)["stale"]:
            fail("--check missed a changed listing")
        # removing a skill: its key leaves the map but stays OWNED
        (harness / "rare").unlink()
        r2 = run("write", repo, harness)
        owned = set(json.loads((repo / STATE_REL).read_text())["owned"])
        if "rare" in r2["overrides"] or "rare" not in owned:
            fail(f"a removed skill must leave the map but stay owned: {owned}")

        # --installed classifies foreign / stale / missing
        (root / "settings.json").write_text(json.dumps({"model": "x", "skillOverrides": {
            "rare": "name-only", "mine-via-ui": "off", "daily": "on"}}))
        d = run("installed", repo, harness, root / "settings.json")["installed"]
        if d["stale"] != ["rare"] or d["foreign"] != ["mine-via-ui"]:
            fail(f"installed diff misclassified: {d}")
        if "ext-pdf" not in d["missing"] or "daily" in d["missing"]:
            fail(f"installed diff missing-set wrong: {d}")

        # bundled skills: declared in a sidecar, managed with no file, never sidecar orphans
        (repo / "config" / "skill-listing.yaml").write_text(
            "skills:\n  anthropic-skills:docx: {listing: name-only}\n"
            "  dataviz: {provenance: bundled}\n"
            "  code-review: {provenance: bundled, listing: 'on', desc_chars: 300}\n")
        mp = json.loads((repo / "config" / "registry-map.yaml").read_text())
        mp["registries"]["skills"]["listing_defaults"]["bundled"] = "name-only"
        (repo / "config" / "registry-map.yaml").write_text(json.dumps(mp))
        rb = run("dry-run", repo, harness)
        if rb["overrides"].get("dataviz") != "name-only" or rb["overrides"].get("code-review") != "on":
            fail(f"bundled keys not managed (want dataviz name-only, code-review on): {rb['overrides']}")
        if "dataviz" in rb["orphans"] or "code-review" in rb["orphans"]:
            fail(f"a bundled key was reported as a sidecar orphan: {rb['orphans']}")
        cr = next((x for x in rb["rows"] if x["name"] == "code-review"), {})
        if cr.get("source") != "bundled" or cr.get("chars") != len("- code-review: ") + 300 + 1:
            fail(f"bundled `on` row must be costed from desc_chars: {cr}")

        # budget simulation (2.1.300 fitter): fits / priority, bundled paid first, worst case
        R = lambda n, src, lst, c: {"name": n, "source": src, "listing": lst, "chars": c,
                                    "name_chars": len(f"- {n}") + 1}
        rows = [R("a", "local", "on", 400), R("b", "local", "on", 400), R("big", "bundled", "on", 500),
                R("c", "team", "name-only", 4)]
        sim = simulate_budget(rows, 2_000)
        if sim["mode"] != "fits" or not sim["all_on_described"]:
            fail(f"1,304 chars under a 2,000 budget must fit: {sim}")
        sim = simulate_budget(rows, 1_000)
        if sim["mode"] != "priority" or sim["all_on_described"]:
            fail(f"bundled (500) paid first must leave room for only one `on` (need 788): {sim}")
        rows[2]["listing"], rows[2]["chars"] = "name-only", rows[2]["name_chars"]
        if not simulate_budget(rows, 1_000)["all_on_described"]:
            fail("with the bundled skill name-only, both `on` descriptions fit in 1,000")
        if BUDGETS["200k window"] != 6_000 or BUDGETS["1M window"] != 30_000:
            fail(f"budgets must use 3 chars/token for current models: {BUDGETS}")

        # a policy that cannot load is an ERROR, never an empty map
        (repo / "config" / "skill-listing.yaml").unlink()
        if run("dry-run", repo, harness)["status"] != "error":
            fail("a missing sidecar produced a map instead of an error")

        # a COLD my-lib (no registry-map at all, as setup_workspace leaves it) falls back to
        # team-lib's default policy; with no default anywhere it is still an error
        cold = root / "cold-my-lib"
        (cold / "config").mkdir(parents=True)
        tl = root / "team-lib"
        (tl / "config").mkdir(parents=True, exist_ok=True)
        (tl / "config" / "registry-map.yaml").write_text(json.dumps({"registries": {"skills": {
            "derived": ["listing"],
            "listing_defaults": {"external": "user-only", "synced": "user-only",
                                 "local": "name-only", "team": "name-only"}}}}))
        rc = compute(cold, harness, default_repo=tl)
        if rc["status"] != "ok" or "default" not in (rc.get("policy_source") or ""):
            fail(f"a cold my-lib did not fall back to team-lib's default policy: {rc}")
        elif rc["overrides"].get("ext-pdf") != "user-invocable-only":
            fail(f"default policy not applied to an external skill: {rc['overrides']}")
        if compute(cold, harness, default_repo=root / "nowhere")["status"] != "error":
            fail("no policy anywhere produced a map instead of an error")

    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
