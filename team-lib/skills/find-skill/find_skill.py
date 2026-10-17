#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Search every skill this machine can run (harness links, both registries, disk, and the cwd project's own skills) by free text and/or category; print invocation name, listing level, category, one-line summary, absolute SKILL.md path and how to use it."
# created: 2026-10-16
# last_updated: 2026-10-16
# maintainer: pvragon
# ---
"""
find-skill: the search the Claude Code harness does not have.

The harness lists ~200 skills but, to stay inside its listing budget, shows most of them by name
only (`name-only`) or not at all (`user-only`). This script is how a session finds the rest.

Sources, joined by harness name:
  1. ~/.claude/skills            — what the harness can actually invoke (truth for "linked").
  2. my-lib registry/skills.yaml — the invocable set as last generated (summary, tags).
  3. team-lib registry/skills.yaml — tags and summaries for team and external skills.
  4. disk: my-lib/skills/*, team-lib/skills/* — catches registry lag (a skill born today).
  5. the cwd project: <root>/.claude/skills/* and <root>/registry/skills.yaml, when present.
Listing level is resolved LIVE with build_registry.resolve_listing (frontmatter -> my-lib sidecar
-> team-lib sidecar -> default), the same resolver that writes the skillOverrides map.

Ranking: match quality first, then layer, then score.
  * Match quality = tier, then how many query terms hit the NAME. Tier 4 is an exact, unprefixed
    name; a name that only matches after stripping `ext-` or `anthropic-skills:` is tier 3, so an
    external never outranks an internal skill on the strength of its prefix being dropped.
  * Layer is the AGENTS.md skill search hierarchy: Local/Project > Team/System > Account (synced
    claude.ai skills: the operator's own account layer, above third-party) > External.
  * A run of two query words found verbatim in a description ("open that") adds to the score.
  * A weak match (half the words, none in a name or category) is shown only when nothing
    better matched.
  * Generic verbs and nouns (make, open, file, ...) count toward the score but not toward
    coverage, unless the query has nothing else.
  * Demoted to the bottom: `[SUPERSEDED` skills and any sidecar entry marked `search: demote`.
    Excluded entirely: sidecar entries marked `search: exclude` (a skill a rule bans, e.g. the
    Google Workspace connector skill, which CLAUDE.md forbids).

Category filters (`--categories`): a skill matches by its `category:`. A skill of the cwd
PROJECT that has no category matches only through text: its name/description must contain a word
of one of the requested categories, or match the query. Superseded and excluded skills never ride
in on a category load.

How to use a hit:
  on / name-only           -> Skill tool with the name.
  user-only / off / unlinked -> Read the SKILL.md at the printed path and follow it; the Skill tool
                              refuses these, but the file is readable (proven 2026-10-16).

Usage:
    python3 find_skill.py "log my hours"
    python3 find_skill.py --categories messaging,personal-admin
    python3 find_skill.py "billing denial" --cwd ~/ai-workspace/projects/acme-health-main --json
    python3 find_skill.py --self-check [--live]
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

WS = Path(os.environ.get("PVRAGON_WORKSPACE") or (Path.home() / "ai-workspace")).expanduser()
ML, TL = WS / "my-lib", WS / "team-lib"
HARNESS = Path.home() / ".claude" / "skills"
SYNCED_PREFIX = "anthropic-skills:"
sys.path.insert(0, str(TL / "executions"))
try:
    import build_registry as BR  # the one listing resolver
except Exception:  # pragma: no cover - team-lib missing: degrade to registry-only data
    BR = None

# archive/ code must never be run (AGENTS.md protocol 2), so it is never offered.
ARCHIVED = re.compile(r"/_?archived?/")
LAYER = {"local": 0, "project": 0, "project-scope": 0, "team": 1, "system": 1,
         "synced": 2, "external": 3}
# What a hit's layer prints as, by provenance (not by sort rank: Omarchy's skills are not Team).
SOURCE_LABEL = {"local": "Local", "project": "Project", "project-scope": "Project",
                "team": "Team", "system": "System", "synced": "Account", "external": "External"}
INVOCABLE = ("on", "name-only")
STOP = set("""a an and are as at be by can do for from get have help how i in into is it its me my
need of on or our please run show some something that the this to use want we what when where which
who with you your skill skills find""".split())
# Words that name an action or a thing every skill touches. They still score, but a query's
# coverage is judged on its other words, so "make a spreadsheet" is about spreadsheets.
GENERIC = set("""make create new open file files thing stuff do doing build write add set up start
work job task page""".split())
W_NAME, W_CAT, W_TAG, W_TEXT = 5, 3, 2, 1


# ---------------------------------------------------------------------------- helpers
def _fm(path: Path) -> dict:
    if BR:
        fm = BR.read_frontmatter(path)
        return fm if isinstance(fm, dict) else {}
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            return yaml.safe_load(text.split("---", 2)[1]) or {}
    except Exception:
        pass
    return {}


def _oneline(s, n=180) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _stem(t: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


def _terms(q: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+", (q or "").lower()) if t not in STOP and len(t) > 1]
    return list(dict.fromkeys(_stem(t) for t in toks))


GENERIC_STEMS = {_stem(g) for g in GENERIC}


def _sidecar_flags(policy: dict | None) -> dict:
    """{harness name: search flag} from the listing sidecars (`search: exclude | demote`)."""
    out = {}
    for _, entries in (policy or {}).get("sidecars") or []:
        for k, ent in entries.items():
            if isinstance(ent, dict) and ent.get("search") and k not in out:
                out[k] = str(ent["search"]).strip()
    return out


def _has(stem: str, text: str) -> bool:
    return re.search(r"\b" + re.escape(stem), text) is not None


def _load_registry(repo: Path) -> dict:
    p = repo / "registry" / "skills.yaml"
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    items = d.get("skills") or []
    if isinstance(items, dict):
        items = [{"name": k, **(v or {})} for k, v in items.items()]
    return {e["name"]: e for e in items if isinstance(e, dict) and e.get("name")}


def project_root(cwd: Path, ws: Path, libs: tuple = ()) -> Path | None:
    """Nearest ancestor of cwd holding .claude/skills or registry/skills.yaml, below the workspace
    root and not one of the two libraries (those are searched already)."""
    cwd = cwd.resolve()
    for d in [cwd, *cwd.parents]:
        if d == ws.resolve() or d == d.parent:
            return None
        if d in {Path(x).resolve() for x in libs}:
            return None
        if (d / ".claude" / "skills").is_dir() or (d / "registry" / "skills.yaml").is_file():
            return d
    return None


# ---------------------------------------------------------------------------- collect
def collect(harness: Path = HARNESS, ml: Path = ML, tl: Path = TL, cwd: Path | None = None,
            ws: Path = WS) -> list[dict]:
    """Every skill reachable from this machine, one record per invocation name."""
    policy = BR.policy_for_repo(ml) if BR else None
    flags = _sidecar_flags(policy)
    reg_ml, reg_tl = _load_registry(ml), _load_registry(tl)
    recs: dict[str, dict] = {}

    def add(name, path: Path, linked: bool, scope: str | None = None, reg: dict | None = None):
        if name in recs or not path.is_file() or ARCHIVED.search(str(path)):
            return
        fm = _fm(path)
        if BR:
            src = scope or BR.provenance(ml, path)
        else:
            src = scope or (reg or {}).get("source") or "local"
        listing, category = None, fm.get("category")
        if policy and scope is None:
            r = BR.resolve_listing(name, fm, src, policy, str(path))
            listing, category = r["listing"], r["category"]
        elif scope == "project-scope":
            listing = BR._norm_listing(fm["listing"]) if (BR and "listing" in fm) else "on"
        if not linked:
            listing = "unlinked"
        meta = {**(reg_tl.get(name) or {}), **(reg_ml.get(name) or {}), **(reg or {})}
        desc = str(fm.get("description") or meta.get("description") or "")
        flag = flags.get(name)
        if not flag and desc.lstrip().upper().startswith("[SUPERSEDED"):
            flag = "demote"
        recs[name] = {
            "name": name, "listing": listing or meta.get("listing") or "on",
            "category": category or meta.get("category"),
            "source": src, "layer": LAYER.get(src, 1),
            "summary": _oneline(fm.get("summary") or meta.get("description") or fm.get("description")),
            "text": " ".join(str(x) for x in (fm.get("description"), fm.get("summary"),
                                               meta.get("description")) if x).lower(),
            "tags": [str(t).lower() for t in (fm.get("tags") or meta.get("tags") or [])],
            "path": str(path.resolve()), "scope": scope,
            "search": flag, "superseded": desc.lstrip().upper().startswith("[SUPERSEDED"),
        }

    # 1. what the harness can invoke
    if harness.is_dir():
        for entry in sorted(harness.iterdir()):
            if entry.name == "synced":
                for sk in sorted(entry.glob("*/*/SKILL.md")):
                    add(SYNCED_PREFIX + sk.parent.name, sk, True)
            elif (entry / "SKILL.md").is_file():
                add(entry.name, entry / "SKILL.md", True)
    # 2-4. registries and disk: anything not linked (registry lag, unlinked bundles)
    for repo, reg in ((ml, reg_ml), (tl, reg_tl)):
        for name, e in reg.items():
            p = repo / str(e.get("path") or "")
            add(name, p, harness.is_dir() is False, reg=None)
        sk_dir = repo / "skills"
        if sk_dir.is_dir():
            for d in sorted(sk_dir.iterdir()):
                if not d.name.startswith(("_", ".")):
                    add(d.name, d / "SKILL.md", harness.is_dir() is False)
    # 5. the cwd project's own skills
    root = project_root(cwd or Path.cwd(), ws, (ml, tl))
    if root:
        for sk in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
            add(sk.parent.name, sk, True, scope="project-scope")
        for name, e in _load_registry(root).items():
            add(name, root / str(e.get("path") or ""), False, scope="project-scope", reg=e)
    return list(recs.values())


# ---------------------------------------------------------------------------- rank
def score(rec: dict, terms: list[str], query: str) -> tuple[int, int, int]:
    """(tier, name_hits, score). 4 exact unprefixed name; 3 every term matched and at least half of
    them in the name or category (or an exact name once `ext-`/`anthropic-skills:` is stripped);
    2 every term matched; 1 at least half matched AND one of them in the name or category; 0 drop.
    Coverage is judged on the query's non-generic terms when it has any. Name hits rank before
    layer within a tier; layer breaks the remaining ties, so a local skill beats a team one only
    when they match equally well."""
    slug = "-".join(re.findall(r"[a-z0-9]+", query.lower()))
    if slug and slug == rec["name"]:
        return 4, 99, 100
    name = rec["name"].replace("-", " ").replace(":", " ")
    cat = (rec.get("category") or "").replace("-", " ")
    tags = " ".join(rec["tags"]).replace("-", " ")
    core = [t for t in terms if t not in GENERIC_STEMS] or terms
    total, hit, strong, name_hits = 0, 0, 0, 0
    for t in terms:
        w = (W_NAME if _has(t, name) else W_CAT if _has(t, cat) else
             W_TAG if _has(t, tags) else W_TEXT if _has(t, rec["text"]) else 0)
        if t not in core:
            total += w // 2 if w else 0      # generic: scores a little, never decides coverage
            continue
        total += w
        hit += w > 0
        strong += w >= W_CAT
        name_hits += w == W_NAME
    if slug and slug in (rec["name"].removeprefix(SYNCED_PREFIX), rec["name"].removeprefix("ext-")):
        return 3, max(name_hits, len(core)), total + 50
    if not core or not hit:
        return 0, 0, 0
    words = re.findall(r"[a-z0-9]+", query.lower())
    total += 2 * sum(f"{a} {b}" in rec["text"] for a, b in zip(words, words[1:]))
    cov = hit / len(core)
    if cov == 1:
        return (3 if strong * 2 >= len(core) else 2), name_hits, total
    if cov >= 0.5:
        return (1 if strong else -1), name_hits, total   # -1: weak, a fallback only
    return 0, 0, 0


def how_to_use(rec: dict) -> str:
    if rec["listing"] in INVOCABLE:
        where = (" (project scope: only in sessions started under that project)"
                 if rec["scope"] == "project-scope" else "")
        return f"Skill tool, skill=\"{rec['name']}\"{where}"
    why = {"unlinked": "not linked into the harness"}.get(rec["listing"], "hidden from the Skill tool")
    return f"Read {rec['path']} and follow it ({why})"


def run(query: str = "", categories: list[str] | None = None, cwd: str | None = None,
        limit: int = 8, harness: Path = HARNESS, ml: Path = ML, tl: Path = TL,
        ws: Path = WS) -> dict:
    """Importable entry point. Returns {status, hits:[...], searched} or {status: error}."""
    cats = {c.strip() for c in (categories or []) if c.strip()}
    if not (query or "").strip() and not cats:
        return {"status": "error", "error": "give a query, --categories, or both"}
    recs = collect(harness, ml, tl, Path(cwd).expanduser() if cwd else None, ws)
    recs = [r for r in recs if r.get("search") != "exclude"]
    terms = _terms(query)
    if cats:
        cat_terms = list(dict.fromkeys(_stem(w) for c in cats for w in re.split(r"[-_ ]", c) if w))

        def in_cats(r):
            if r["superseded"] or r.get("search") == "demote":
                return False
            if r.get("category") in cats:
                return True
            if r["scope"] == "project-scope" and not r.get("category"):
                blob = r["name"].replace("-", " ") + " " + r["text"]
                return any(_has(t, blob) for t in cat_terms) or bool(
                    terms and score(r, terms, query)[0])
            return False
        recs = [r for r in recs if in_cats(r)]
    hits, weak = [], []
    for r in recs:
        tier, nh, sc = score(r, terms, query) if query.strip() else (1, 0, 0)
        if tier:
            (hits if tier > 0 else weak).append(
                {**r, "tier": tier, "name_hits": nh, "score": sc, "use": how_to_use(r)})
    hits = hits or weak
    hits.sort(key=lambda h: (h.get("search") == "demote", -h["tier"], -h["name_hits"],
                             h["layer"], -h["score"], h["name"]))
    if query.strip() and limit:
        hits = hits[:limit]
    for h in hits:
        h.pop("text", None)
    return {"status": "ok", "query": query, "categories": sorted(cats),
            "searched": len(recs), "hits": hits}


def render(res: dict, brief: bool = False) -> str:
    if res["status"] != "ok":
        return f"find-skill: {res['error']}"
    head = f"find-skill: {len(res['hits'])} hit(s) of {res['searched']} skills"
    if res["query"]:
        head += f" for {res['query']!r}"
    if res["categories"]:
        head += f" in [{', '.join(res['categories'])}]"
    if not res["hits"]:
        return head + "\n  No skill matches. Do the task directly, or retry with other words."
    out = [head]
    if brief:   # persona startup: one line each; hidden hits carry their Read path
        for h in res["hits"]:
            line = (f"- {h['name']} [{h['listing']} · {h.get('category') or 'no category'}]: "
                    f"{_oneline(h['summary'], 90)}")
            if h["listing"] not in INVOCABLE:
                line += f" (Read {h['path']})"
            out.append(line)
        return "\n".join(out)
    for i, h in enumerate(res["hits"], 1):
        out.append(f"{i}. {h['name']}  [{h['listing']} · {h.get('category') or 'no category'} · "
                   f"{SOURCE_LABEL.get(h['source'], 'Team')}/{h['source']}]")
        out.append(f"   {h['summary']}")
        out.append(f"   path: {h['path']}")
        out.append(f"   use:  {h['use']}")
    return "\n".join(out)


# ---------------------------------------------------------------------------- self-check
def self_check() -> int:
    """Two-sided checks against a synthetic workspace (never the real harness)."""
    base = ML / "runtime" / ".tmp"
    tmp = Path(tempfile.mkdtemp(prefix="find-skill-selfcheck-",
                                dir=base if base.is_dir() else None))
    fails = []
    saved_ws = BR.WORKSPACE if BR else None

    def sk(path: Path, name, desc, extra=""):
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n{extra}---\nbody\n")

    try:
        ws, ml, tl, h = tmp / "ws", tmp / "ws/my-lib", tmp / "ws/team-lib", tmp / "claude/skills"
        (ml / "config").mkdir(parents=True)
        (tl / "config").mkdir(parents=True)
        (tl / "config/skill-categories.yaml").write_text(
            "categories: {personal-admin: x, messaging: x, writing: x, career: x, billing-audit: x}\n")
        (ml / "config/skill-listing.yaml").write_text("skills: {}\n")
        (tl / "config/skill-listing.yaml").write_text(
            "skills:\n  ext-resume-tailor: {category: career}\n")
        (ml / "config/registry-map.yaml").write_text(yaml.safe_dump({"registries": {"skills": {
            "derived": ["listing", "category"],
            "listing_sidecars": ["config/skill-listing.yaml", "../team-lib/config/skill-listing.yaml"],
            "category_vocabulary": "../team-lib/config/skill-categories.yaml",
            "listing_defaults": {"external": "user-only", "team": "name-only", "local": "name-only"},
            "listing_required": [], "listing_not_linked": []}}}))
        sk(ml / "skills/log-hours-to-calendar", "log-hours-to-calendar",
           "Log worked hours onto the calendar.", 'listing: "on"\ncategory: personal-admin\n')
        sk(tl / "skills/send-note", "send-note", "Send a short message to a teammate.",
           "listing: name-only\ncategory: messaging\n")
        sk(tl / "skills/_external/pack/resume-tailor", "resume-tailor",
           "Tailor a resume to a job description.")
        sk(ml / "skills/write-note", "write-note", "Write a message draft.",
           "listing: name-only\ncategory: messaging\n")
        sk(ml / "skills/fresh-unlinked", "fresh-unlinked", "Calendar cleanup born today.",
           "listing: name-only\ncategory: personal-admin\n")
        h.mkdir(parents=True)
        for n, tgt in (("log-hours-to-calendar", ml / "skills/log-hours-to-calendar"),
                       ("send-note", tl / "skills/send-note"),
                       ("write-note", ml / "skills/write-note"),
                       ("ext-resume-tailor", tl / "skills/_external/pack/resume-tailor")):
            (h / n).symlink_to(tgt)
        proj = ws / "projects/demo"
        sk(proj / ".claude/skills/demo-billing", "demo-billing", "Reconcile demo billing denials.")
        kw = dict(harness=h, ml=ml, tl=tl, ws=ws, cwd=str(ws))   # never the real cwd

        def names(res):
            return [x["name"] for x in res["hits"]]

        r = run("log my hours", **kw)
        if not r["hits"] or r["hits"][0]["name"] != "log-hours-to-calendar":
            fails.append(f"must-hit: 'log my hours' -> {names(r)}")
        elif not r["hits"][0]["use"].startswith("Skill tool"):
            fails.append("an `on` hit must say Skill tool")
        r = run("xylophone tuning", **kw)
        if r["hits"]:
            fails.append(f"must-miss: 'xylophone tuning' returned {names(r)}")
        r = run("", categories=["messaging"], **kw)
        if sorted(names(r)) != ["send-note", "write-note"]:
            fails.append(f"category filter: got {names(r)}")
        elif names(r)[0] != "write-note":
            fails.append(f"Local must outrank Team at equal match: {names(r)}")
        r = run("message", categories=["personal-admin"], **kw)
        if r["hits"]:
            fails.append(f"category filter must exclude other categories: {names(r)}")
        r = run("tailor resume", **kw)
        hit = next((x for x in r["hits"] if x["name"] == "ext-resume-tailor"), None)
        if not hit or hit["listing"] != "user-only" or not hit["use"].startswith("Read /"):
            fails.append(f"user-only hit must show the Read path: {hit}")
        r = run("calendar cleanup", **kw)
        hit = next((x for x in r["hits"] if x["name"] == "fresh-unlinked"), None)
        if not hit or hit["listing"] != "unlinked" or "Read " not in hit["use"]:
            fails.append(f"disk discovery of an unlinked skill must surface it as Read: {hit}")
        r = run("billing denials", **{**kw, "cwd": str(proj)})
        if "demo-billing" not in names(r):
            fails.append(f"project scope: demo-billing not found from its cwd: {names(r)}")
        r = run("billing denials", **{**kw, "cwd": str(ws / "projects")})
        if "demo-billing" in names(r):
            fails.append("project scope leaked outside its project")
        sk(proj / "archive/old-billing", "old-billing", "Reconcile billing denials, retired.")
        (proj / "registry").mkdir(parents=True, exist_ok=True)
        (proj / "registry/skills.yaml").write_text(
            "skills:\n- name: old-billing\n  path: archive/old-billing/SKILL.md\n")
        r = run("billing denials", **{**kw, "cwd": str(proj)})
        if "old-billing" in names(r):
            fails.append("an archive/ skill was offered (AGENTS.md protocol 2 forbids running it)")
        sk(ml / "skills/notes-digest", "notes-digest", "A digest that can send a note summary.",
           "listing: name-only\ncategory: writing\n")
        r = run("send note", **kw)
        if names(r)[:1] != ["send-note"]:
            fails.append(f"a name match must outrank a description-only match across layers: {names(r)}")
        if run("", **kw)["status"] != "error":
            fails.append("an empty query with no categories must be an error")

        # ---- ranking fixes (2026-10-16 final review, findings 2-4 and 12) --------------------
        sk(tl / "skills/create-brand-guidelines", "create-brand-guidelines",
           "Create a brand guidelines file.", "listing: name-only\ncategory: writing\n")
        sk(tl / "skills/_external/pack/brand-guidelines", "brand-guidelines",
           "Apply Anthropic brand guidelines.")
        sk(h / "synced/acct/xlsx", "xlsx", "Use whenever a spreadsheet file is the input or output.")
        sk(tl / "skills/_external/pack/xlsx", "xlsx", "Spreadsheet creation and analysis.")
        sk(tl / "skills/_external/pack/make-cl", "make-cl", "Make a cover letter.")
        sk(h / "synced/acct/acme-brand-guidelines", "acme-brand-guidelines",
           "Acme brand guidelines.")
        sk(h / "synced/acct/google-workspace", "google-workspace",
           "Google Drive, Docs and Sheets connector calls for spreadsheet work.")
        sk(ml / "skills/old-sheet-matcher", "old-sheet-matcher",
           "'[SUPERSEDED] spreadsheet bucket classifier. Do not use.'",
           "listing: name-only\ncategory: writing\n")
        sk(ml / "skills/pane-show", "pane-show", "Show the file in a pane. Use when the user "
           "says open that.", "listing: name-only\ncategory: writing\n")
        sk(ml / "skills/crash-helper", "crash-helper", "Open a file of crash logs and diagnose the PC.",
           "listing: name-only\ncategory: writing\n")
        sk(Path(tmp) / "usr/share/omarchy-tool", "omarchy-tool", "Customize the desktop.")
        (ml / "config/skill-listing.yaml").write_text(
            "skills:\n  anthropic-skills:google-workspace: {listing: user-only, search: exclude}\n"
            "  anthropic-skills:xlsx: {listing: name-only, category: writing}\n"
            "  omarchy-tool: {listing: name-only, category: writing}\n")
        for n, tgt in (("create-brand-guidelines", tl / "skills/create-brand-guidelines"),
                       ("ext-brand-guidelines", tl / "skills/_external/pack/brand-guidelines"),
                       ("ext-xlsx", tl / "skills/_external/pack/xlsx"),
                       ("ext-make-cl", tl / "skills/_external/pack/make-cl"),
                       ("old-sheet-matcher", ml / "skills/old-sheet-matcher"),
                       ("pane-show", ml / "skills/pane-show"),
                       ("crash-helper", ml / "skills/crash-helper"),
                       ("omarchy-tool", Path(tmp) / "usr/share/omarchy-tool")):
            (h / n).symlink_to(tgt)

        # provenance() is judged against the WORKSPACE root: point it at the synthetic one so a
        # target outside it (tmp/usr/share) is `system`, as Omarchy's skills are on the machine.
        if BR:
            BR.WORKSPACE = ws
        r = names(run("brand guidelines", **kw))
        if "ext-brand-guidelines" not in r:
            fails.append(f"external twin must stay findable: {r}")
        elif r.index("create-brand-guidelines") > r.index("ext-brand-guidelines"):
            fails.append(f"internal must outrank external at equal match: {r}")
        if "anthropic-skills:acme-brand-guidelines" not in r or \
                r.index("anthropic-skills:acme-brand-guidelines") < r.index("create-brand-guidelines"):
            fails.append(f"internal must outrank the synced account layer at equal match: {r}")
        hx = {x["name"]: x for x in run("xlsx", **kw)["hits"]}
        if not ({"anthropic-skills:xlsx", "ext-xlsx"} <= set(hx)) or \
                hx["anthropic-skills:xlsx"]["layer"] >= hx["ext-xlsx"]["layer"]:
            fails.append("the synced account layer must rank above external (layer order)")
        r = names(run("brand-guidelines", **kw))
        if r[:1] == ["ext-brand-guidelines"]:
            fails.append(f"an ext- prefix-stripped exact name must not take tier 4: {r}")
        r = names(run("make a spreadsheet", **kw))
        if "anthropic-skills:xlsx" not in r[:3]:
            fails.append(f"synced anthropic-skills:xlsx must be searchable and top 3: {r}")
        elif "ext-xlsx" in r and r.index("ext-xlsx") < r.index("anthropic-skills:xlsx"):
            fails.append(f"account (synced) layer must outrank external: {r}")
        if "ext-make-cl" in r[:3]:
            fails.append(f"a generic verb ('make') must not decide the match: {r}")
        if "anthropic-skills:google-workspace" in r or "anthropic-skills:google-workspace" in \
                names(run("google workspace", **kw)):
            fails.append("a `search: exclude` (banned) skill was offered")
        if "old-sheet-matcher" not in r:
            fails.append(f"a superseded skill must stay findable (demoted, not dropped): {r}")
        elif r.index("old-sheet-matcher") < r.index("anthropic-skills:xlsx"):
            fails.append(f"a superseded name match must rank below a live description match: {r}")
        if "old-sheet-matcher" in names(run("", categories=["writing"], **kw)):
            fails.append("a superseded skill rode in on a category load")
        r = names(run("open that file", **kw))
        if r[:1] != ["pane-show"]:
            fails.append(f"'open that file' must put the phrase match first: {r}")
        out = render(run("tailor resume", **kw), brief=True)
        line = next((l for l in out.splitlines() if "ext-resume-tailor" in l), "")
        if "Read /" not in line:
            fails.append(f"--brief must print the Read path for a user-only hit: {line!r}")
        line = next((l for l in render(run("log my hours", **kw), brief=True).splitlines()
                     if "log-hours" in l), "")
        if "Read /" in line:
            fails.append(f"--brief must not print a Read path for an invocable hit: {line!r}")
        out = render(run("customize the desktop", **kw))
        if "System/system" not in out or "Team/system" in out:
            fails.append(f"an Omarchy (system) skill must print as System: {out[:200]}")


        # ---- project scope with category filters (finding 4) ----------------------------
        sk(proj / ".claude/skills/demo-transport", "demo-transport", "Catalog transport statuses.")
        r = names(run("", categories=["billing-audit"], **{**kw, "cwd": str(proj)}))
        if "demo-billing" not in r:
            fails.append(f"uncategorized project skill must match a category by text: {r}")
        if "demo-transport" in r:
            fails.append(f"uncategorized project skill must NOT match a category without text: {r}")
        r = names(run("transport statuses", categories=["billing-audit"], **{**kw, "cwd": str(proj)}))
        if "demo-transport" not in r:
            fails.append(f"project skill must be returned when the query matches it: {r}")
        if "demo-billing" in names(run("", categories=["billing-audit"], **kw)):
            fails.append("project skill leaked into a category load outside its project")
    finally:
        if BR:
            BR.WORKSPACE = saved_ws
        shutil.rmtree(tmp, ignore_errors=True)
    for f in fails:
        print("FAIL:", f)
    print("find_skill self-check:", "ALL PASS" if not fails else f"{len(fails)} FAIL")
    return 1 if fails else 0


def live_check() -> int:
    """Real-data checks (this machine's harness, registries and acme-health-main). Read-only. Each
    case is skipped, not failed, when the data it needs is absent (a teammate's machine)."""
    fails, ran = [], 0

    def names(res):
        return [x["name"] for x in res["hits"]]

    rc = WS / "projects" / "acme-health-main"
    if (rc / "skills").is_dir() or (rc / ".claude" / "skills").is_dir():
        ran += 1
        # rc-cfo Step 2's exact load: the project's uncategorized skills must ride in by text.
        r = run("", ["billing-audit", "data-ml", "documents", "review"], str(rc), 0)
        got = {h["name"] for h in r["hits"] if h["scope"] == "project-scope"}
        if not {"load-acme-health-cfo", "payer-audit-match", "contract-billing-match"} <= got:
            fails.append(f"rc-cfo load from acme-health-main is missing project skills: {sorted(got)}")
        if any(h["superseded"] for h in r["hits"]):
            fails.append("rc-cfo load carries a [SUPERSEDED] skill")
        if "load-acme-health-cfo" not in names(run("billing denial remittance", None, str(rc), 5)):
            fails.append("query from acme-health-main does not find load-acme-health-cfo")
        if "load-acme-health-cfo" in names(run("billing denial remittance", None, str(WS / "my-lib"), 0)):
            fails.append("acme-health-main project skill leaked into a my-lib search")
    cases = (("brand guidelines", lambda n: "create-brand-guidelines" in n and (
                 "ext-brand-guidelines" not in n
                 or n.index("create-brand-guidelines") < n.index("ext-brand-guidelines"))),
             ("make a spreadsheet", lambda n: "anthropic-skills:xlsx" in n[:3]
                 and "anthropic-skills:google-workspace" not in n),
             ("open that file", lambda n: n[:1] == ["view"]),
             ("resume a session", lambda n: n[:1] == ["resume-sessions"]))
    for q, ok in cases:
        n = names(run(q, None, str(WS / "my-lib"), 8))
        if not n:
            continue
        ran += 1
        if not ok(n):
            fails.append(f"{q!r} -> {n[:5]}")
    for f in fails:
        print("FAIL:", f)
    print(f"find_skill live check: {ran} case group(s) run,",
          "ALL PASS" if not fails else f"{len(fails)} FAIL")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Search every skill this machine can run.")
    ap.add_argument("query", nargs="*", help="free text, e.g. 'log my hours'")
    ap.add_argument("--categories", default="", help="comma-separated category filter")
    ap.add_argument("--cwd", default=None, help="project dir to include (default: current dir)")
    ap.add_argument("--limit", type=int, default=8, help="max hits for a text query (0 = all)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--brief", action="store_true", help="one line per hit (persona startup)")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="with --self-check: also run read-only checks against this machine's data")
    a = ap.parse_args(argv)
    if a.self_check:
        rc = self_check()
        return rc or (live_check() if a.live else 0)
    res = run(" ".join(a.query), a.categories.split(",") if a.categories else None,
              a.cwd or os.getcwd(), a.limit)
    print(json.dumps(res, indent=2) if a.json else render(res, a.brief))
    return 0 if res["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
