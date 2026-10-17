#!/usr/bin/env python3
# ---
# template: execution
# version: 0.11.0
# summary: Generate a registry manifest FROM the frontmatter of the files it indexes, per
#          config/registry-map.yaml. Derives path/version/description/source and a skill's
#          listing/category (frontmatter -> sidecars -> defaults) and a persona's skill_categories;
#          preserves every hand-authored field. --check is a rebuild-and-diff drift gate; --apply writes.
# created: 2026-08-07
# last_updated: 2026-10-16
# maintainer: pvragon
# known_limitations: >-
#   PyYAML does not round-trip comments, so a manifest carrying comments BELOW its header block
#   refuses to --apply rather than silently dropping them (acme-health-main's manifests are full of
#   load-bearing inline commentary). Non-frontmatter files are reported, never invented.
# ---
"""A registry is a BUILD ARTIFACT. Two owners for one fact is the whole bug.

Measured 2026-08-07: my-lib's registries were short but 27/30 skills descriptions had drifted from
the files' own summaries and 11/30 versions were wrong; acme-health-main's were accurate but had grown
into essays. Same disease, opposite directions. Generation removes the second owner.

What it will NOT do: invent a summary, rewrite a summary, or touch a field it does not own.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import os
import re
import sys
from pathlib import Path

import yaml

FM_MD = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)
FM_PY = re.compile(r"^#\s*---\s*$(.*?)^#\s*---\s*$", re.M | re.S)


# ---------------------------------------------------------------------------- frontmatter
def read_frontmatter(path: Path) -> dict | str | None:
    """The file's frontmatter, or a REASON it could not be read.

    Returns dict on success, the string "absent" when there is no block, or "malformed: <why>".
    ⚑ Those are THREE states and collapsing them lost information twice on 2026-08-07: the caller
    reported two files with unquoted colons in a plain scalar (`Order: /create-handoff-docs`) as
    "no frontmatter", which is a different fix from adding one — and a third file was reported the
    same way purely because this function truncated at 8 KB and missed a terminator at line 26,
    i.e. the tool's own defect wearing the file's name. Read the whole file; name the reason.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return f"malformed: unreadable ({exc.__class__.__name__})"
    # ⚑ `.sh` uses the SAME `# ---` comment block as `.py`. Keying only on `.py` sent every shell
    # script to the markdown matcher, which looks for `---` fences it will never find — so three
    # scripts whose frontmatter this session had just REPAIRED still read as "absent". The reader
    # decides by comment-style, not by one suffix. Found 2026-08-08 enabling team-lib generation.
    if path.suffix in (".py", ".sh"):
        m = FM_PY.search(text)
        if not m:
            return "absent"
        body = "\n".join(re.sub(r"^#\s?", "", ln) for ln in m.group(1).splitlines())
    else:
        m = FM_MD.search(text)
        if not m:
            return "absent"
        body = m.group(1)
    try:
        d = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at frontmatter line {mark.line + 1}" if mark else ""
        return f"malformed:{where} {getattr(exc, 'problem', exc)}"
    return d if isinstance(d, dict) else "malformed: frontmatter is not a mapping"


# `summary:` is THE pointer field. `description:` is a fallback, never an alternative — and it
# exists because progressive-disclosure-convention.md EXEMPTS third-party `_external/` files from
# carrying a `summary:` at all, while forbidding us to edit them. Measured 2026-08-08: 93 of
# my-lib's 163 skills and 94 of team-lib's 144 carry only `description:` (the field the harness
# reads), and 7 of the 10 entries `validate_registry` reported as "missing a pointer field" are
# files we may not touch. Deriving from `summary:` alone therefore cannot ever reach conformance.
# Both generators read this list, in this order, so the manifest and the index can never disagree
# about which text describes a file.
POINTER_FIELDS = ["summary", "description"]


def pointer(fm: dict, fields=None) -> tuple[str | None, str | None]:
    """(field_name_used, value) — the first pointer field present, or (None, None)."""
    for f in (fields or POINTER_FIELDS):
        if isinstance(fm, dict) and fm.get(f):
            return f, " ".join(str(fm[f]).split())
    return None, None


def _ver(s: str) -> tuple:
    """Comparable semver; unparseable sorts lowest rather than raising."""
    return tuple(int(x) if x.isdigit() else -1 for x in re.split(r"[.\-+]", str(s))[:3])


WORKSPACE = Path(os.environ.get("PVRAGON_WORKSPACE", Path.home() / "ai-workspace"))


def provenance(repo: Path, path: Path) -> str:
    """external | synced | team | local | project | system — by RESOLVED path, never by name.

    my-lib/skills/ holds 93 symlinks into team-lib/skills/_external/ and several more into
    team-lib proper. Naming (`ext-*`) happens to correlate today; the symlink target is what is
    actually true, and A1's search hierarchy (local > team internal > team external) is only
    meaningful if the registry records which is which.

    ⚑ ONLY `/_external/` IS EXTERNAL (fixed 2026-10-16). The last line used to label ANYTHING
    resolving outside the repo `external`, so `manage-inbox` and `torrent-search` — symlinks into
    projects/ — were recorded as third-party. Harmless while `source` was descriptive; fatal the
    moment `listing_defaults.external: user-only` keyed on it, because both would have vanished
    from the model with no error. The outside-the-repo cases are now named for what they are:
      * project — a target under a `projects/` tree (editable, but owned by that project repo)
      * synced  — the harness-managed mirror of the claude.ai account skills (`skills/synced/`)
      * system  — a target outside the workspace entirely (Omarchy ships two under /usr/share)
      * local   — anything else inside the workspace (agents/, personal/) — ours, editable
    """
    real = str(path.resolve())
    if "/_external/" in real:
        return "external"
    if "/skills/synced/" in real:
        return "synced"
    if "/team-lib/" in real:
        return "team"
    if real.startswith(str(repo.resolve()) + os.sep):
        return "local"
    if "/projects/" in real:
        return "project"
    ws = str(WORKSPACE.resolve()) + os.sep
    return "local" if real.startswith(ws) else "system"


# ---------------------------------------------------------------------------- listing
# What the harness shows the MODEL for a skill. `user-only` is our spelling of Claude Code's
# `user-invocable-only` (hidden from the model, still runs when the user types /<name>); `off` also
# removes /<name>, so it is accepted from a sidecar only — a SKILL.md that switched itself off
# would be a skill nobody can find to switch back on.
LISTING_VALUES = ("on", "name-only", "user-only")
SIDECAR_ONLY_LISTING = ("off",)
HARNESS_LISTING = {"on": "on", "name-only": "name-only",
                   "user-only": "user-invocable-only", "off": "off"}


def _norm_listing(v):
    """YAML 1.1 reads a bare `on` / `off` as a BOOLEAN. `listing: on` is what anyone will type, so
    True means "on" — refusing it would make the obvious spelling an error."""
    if v is True:
        return "on"
    if v is False:
        return "off"
    return None if v is None else str(v).strip()


def load_listing_policy(repo: Path, spec: dict) -> dict | None:
    """The listing/category policy a skills spec declares, or None if it derives neither.

    Sidecar and vocabulary paths are relative to the repo (my-lib reaches team-lib's as
    `../team-lib/...`). A declared file that is missing or does not parse is an ERROR in the
    report, never a silent empty set — a sidecar that quietly fails to load turns every external
    back into the default and nothing would say why.
    """
    if not ({"listing", "category"} & set(spec.get("derived") or ())):
        return None
    errors, sidecars, vocab = [], [], None
    for rel in spec.get("listing_sidecars") or []:
        p = repo / rel
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except OSError:
            errors.append(f"sidecar not found: {rel}")
            continue
        except yaml.YAMLError as exc:
            errors.append(f"sidecar does not parse: {rel} ({getattr(exc, 'problem', exc)})")
            continue
        sidecars.append((rel, d.get("skills") or {} if isinstance(d, dict) else {}))
    if spec.get("category_vocabulary"):
        rel = spec["category_vocabulary"]
        try:
            d = yaml.safe_load((repo / rel).read_text(encoding="utf-8")) or {}
            vocab = set((d.get("categories") or {}) if isinstance(d, dict) else ())
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"category vocabulary unreadable: {rel} ({exc.__class__.__name__})")
    return {"values": tuple(spec.get("listing_values") or LISTING_VALUES),
            "sidecars": sidecars,
            "defaults": {k: _norm_listing(v) for k, v in (spec.get("listing_defaults") or {}).items()},
            "required": set(spec.get("listing_required") or ()),
            "not_linked": list(spec.get("listing_not_linked") or ()),
            "vocabulary": vocab, "errors": errors}


def load_vocabulary(repo: Path, rel: str) -> tuple[set | None, str | None]:
    """(category names, error). The same vocabulary file the skills spec validates `category:`
    against; personas validate `skill_categories:` against it so a persona cannot ask find-skill
    for a category no skill can ever carry."""
    try:
        d = yaml.safe_load((repo / rel).read_text(encoding="utf-8")) or {}
        return set((d.get("categories") or {}) if isinstance(d, dict) else ()), None
    except (OSError, yaml.YAMLError) as exc:
        return None, f"category vocabulary unreadable: {rel} ({exc.__class__.__name__})"


def derive_skill_categories(fm, vocab: set | None) -> tuple[list, str | None]:
    """A persona's `skill_categories:` (what it passes to find-skill), as a list of strings, plus a
    problem string or None. A bare string is accepted as a one-item list. Unknown names are kept
    in the manifest (the file owns the value) but reported as `category_invalid`."""
    v = fm.get("skill_categories") if isinstance(fm, dict) else None
    if v is None:
        return [], None
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return [], f"is a {type(v).__name__}, want a list"
    lst = [str(x).strip() for x in v if str(x).strip()]
    bad = [x for x in lst if vocab is not None and x not in vocab]
    return lst, (f"not in the vocabulary: {bad}" if bad else None)


def policy_for_repo(repo: Path, config: Path | None = None, registry: str = "skills") -> dict | None:
    """load_listing_policy() for the repo's own registry-map — what the validator and the overrides
    generator use, so all three tools resolve from ONE declaration."""
    cfg_path = config or repo / "config" / "registry-map.yaml"
    try:
        cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    spec = (cfg.get("registries") or {}).get(registry)
    return load_listing_policy(repo, spec) if spec else None


def resolve_listing(name: str, fm, source: str, policy: dict, path: str | None = None) -> dict:
    """{listing, listing_source, category, category_source, problems:[(bucket, msg)], not_linked}.

    THE resolver — build_registry, validate_registry and build_skill_overrides all call this one
    function; a second implementation would eventually order the layers differently and the
    manifest and the harness would disagree about what the model sees. First hit wins:
        frontmatter -> each declared sidecar in order -> listing_defaults[source]
    A default on a provenance named in `listing_required` is still applied (the skill has to show
    up as SOMETHING) but is reported as `listing_missing`: drift, not a decision.
    """
    out = {"listing": None, "listing_source": None, "category": None, "category_source": None,
           "problems": [], "not_linked": False}
    if path and any(n in str(path) for n in policy["not_linked"]):
        out["not_linked"] = True
        return out
    fm = fm if isinstance(fm, dict) else {}
    values = policy["values"]
    probs = out["problems"]

    if "listing" in fm:
        v = _norm_listing(fm["listing"])
        if v in values:
            out["listing"], out["listing_source"] = v, "frontmatter"
        else:
            why = " (`off` is sidecar-only)" if v == "off" else ""
            probs.append(("listing_invalid", f"{name}: frontmatter listing {fm['listing']!r} not "
                                             f"in {list(values)}{why}"))
    for rel, entries in policy["sidecars"]:
        ent = entries.get(name)
        if not isinstance(ent, dict):
            continue
        if out["listing"] is None and "listing" in ent:
            v = _norm_listing(ent["listing"])
            if v in values or v in SIDECAR_ONLY_LISTING:
                out["listing"], out["listing_source"] = v, f"sidecar:{rel}"
            else:
                probs.append(("listing_invalid", f"{name}: {rel} listing {ent['listing']!r} not "
                                                 f"in {list(values) + list(SIDECAR_ONLY_LISTING)}"))
        if out["category"] is None and ent.get("category") is not None:
            out["category"], out["category_source"] = str(ent["category"]), f"sidecar:{rel}"
    if out["listing"] is None:
        out["listing"] = policy["defaults"].get(source)
        out["listing_source"] = "default" if out["listing"] else None
        if source in policy["required"]:
            probs.append(("listing_missing", f"{name} ({source}): no `listing:` in frontmatter or "
                                             f"a sidecar — effective {out['listing']}"))

    if fm.get("category") is not None:      # frontmatter beats any sidecar category
        out["category"], out["category_source"] = str(fm["category"]), "frontmatter"
    if out["category"] is None:
        probs.append(("category_missing", f"{name} ({source})"))
    elif policy["vocabulary"] is not None and out["category"] not in policy["vocabulary"]:
        probs.append(("category_invalid", f"{name}: category {out['category']!r} "
                                          f"({out['category_source']}) is not in the vocabulary"))
    return out


def entry_id(spec: dict, path: Path) -> str:
    """A skill is its DIRECTORY name (skills/foo/SKILL.md -> foo); everything else its stem.

    `id_rules` lets a layer declare a PREFIX derived from where the file sits. team-lib needs it:
    its 85 external-pack skills live at `skills/_external/<pack>/<skill>/SKILL.md` but are indexed
    `ext-<skill>`, because that is the name the harness exposes. Without the rule the generator
    derives `<skill>`, which does not match — so a rebuild would tombstone all 85 live entries and
    add 85 near-duplicates. Measured 2026-08-08 before enabling generation on that layer.

    Deriving the prefix from the PATH rather than the name is the same discipline `provenance()`
    already uses: the resolved location is what is true, a naming convention is what someone typed.
    """
    # `id_from: dir` names an entry by its FOLDER, for trees where every entry point shares one
    # filename (apps/<name>/README.md). Without it every app would derive the id `README` and
    # all but one would be dropped as collisions.
    base = (path.parent.name if spec.get("id_from") == "dir"
            or path.name.upper().startswith("SKILL.") else path.stem)
    for rule in (spec.get("id_rules") or []):
        needle = rule.get("when_path_contains")
        if needle and needle in str(path.as_posix()):
            return f"{rule.get('prefix', '')}{base}{rule.get('suffix', '')}"
    return base


def resolve_ref(repo: Path, tok: str, levels: int = 3) -> Path | None:
    """The root a referenced path resolves under, or None if it resolves nowhere.

    ⚑ THIS USED TO ANSWER A NARROWER QUESTION THAN IT REPORTED. It tried `repo/tok` only, so a
    perfectly live CROSS-LAYER pointer — `team-lib/executions/regen_current_state.py`, named by
    my-lib's session-debrief entry — was reported as a missing path merely because it is not
    under `my-lib/`. That false finding was carried into a session handoff on 2026-08-07 as real
    work ("two team-lib files that do not exist"); both exist. Measuring "absent from THIS repo"
    and reporting "absent" is the adjacent-property error, and this workspace is layered, so
    cross-layer references are ordinary rather than exceptional.

    Resolving outside the repo is still worth SAYING — it is a coupling the manifest does not own —
    so the caller reports it as `cross_layer`, distinct from `dangling`. Bounded to `levels`
    ancestors so a token cannot accidentally resolve against something far up the filesystem.
    """
    for root in [repo, *list(repo.resolve().parents)[:levels]]:
        if (root / tok).exists():
            return root
    return None


# ---------------------------------------------------------------------------- comments guard
def split_header_comments(raw: str) -> tuple[str, bool]:
    """(leading comment block, any REAL comments below it).

    ⚑ A line starting with `#` is not necessarily a comment. Deciding lexically flagged
    `#NAME?, #VALUE!, #DIV/0!` — a WRAPPED CONTINUATION inside a folded scalar describing Excel
    error values — as a comment, and refused a write that was perfectly safe. That is a lexical
    answer to a structural question, the same shape as a guard scanning the wrong syntactic unit.

    So decide by DELETION: a line is a comment iff removing it leaves the parsed data identical.
    Content cannot be removed without changing the data (or breaking the parse).
    """
    lines = raw.splitlines(keepends=True)
    i = 0
    while i < len(lines) and (lines[i].lstrip().startswith("#") or not lines[i].strip()):
        i += 1
    header = "".join(lines[:i])
    try:
        base = yaml.safe_load(raw)
    except yaml.YAMLError:
        return header, True                      # cannot reason about it — refuse, do not guess
    for n in range(i, len(lines)):
        if not lines[n].lstrip().startswith("#"):
            continue
        trial = "".join(lines[:n] + lines[n + 1:])
        try:
            if yaml.safe_load(trial) == base:
                return header, True              # removable without changing data => a comment
        except yaml.YAMLError:
            continue                             # removing it broke the parse => it was content
    return header, False


# ---------------------------------------------------------------------------- discovery
def discover(repo: Path, spec: dict) -> tuple[dict[str, Path], list[str]]:
    """({entry_id: path}, collisions) for one registry spec.

    Extracted from build() 2026-08-08 so build_index.py indexes EXACTLY the set of files the
    manifest indexes. Two implementations of "which files does this spec cover" is the same
    two-owners bug the generator exists to remove — one would eventually glob, exclude or
    collide differently and the index and the manifest would disagree about membership with
    nothing to detect it.
    """
    found: dict[str, Path] = {}
    collisions: list[str] = []
    for g in spec["globs"]:
        for p in sorted(repo.glob(g)):
            if any(fnmatch.fnmatch(str(p), pat) for pat in spec.get("exclude", [])):
                continue
            eid = entry_id(spec, p)
            if eid in found and found[eid] != p:
                # ⚑ This used to be a bare assignment, so the LAST file silently won and the
                # others vanished from the index with nothing said. Found 2026-08-08 mapping
                # team-lib, where one external pack vendors its skills twice (`.agents/skills/`
                # AND `skills/`) — seven ids, fourteen files, seven of them about to disappear.
                # An index that drops what it cannot name is worse than one that refuses to.
                collisions.append(f"{eid}: {found[eid]} AND {p}")
                continue
            found[eid] = p
    return found, collisions


# ---------------------------------------------------------------------------- build
def build(repo: Path, name: str, spec: dict, budget: int) -> dict:
    reg_path = repo / spec["file"]
    raw = reg_path.read_text(encoding="utf-8") if reg_path.exists() else ""
    header, comments_below = split_header_comments(raw)
    doc = yaml.safe_load(raw) if raw.strip() else {}
    doc = doc if isinstance(doc, dict) else {}
    existing = doc.get(spec["key"]) or ([] if spec["shape"] == "list" else {})

    if spec["shape"] == "list":
        cur = {e.get(spec["id"]): dict(e) for e in existing if isinstance(e, dict)}
    else:
        cur = {k: dict(v) for k, v in existing.items() if isinstance(v, dict)}

    found, collisions = discover(repo, spec)

    derived = set(spec["derived"])
    field = spec["field"]
    out, report = {}, {"new": [], "gone": [], "downgrade": [], "version": [], "summary": [],
                       "budget": [], "budget_external": [], "fallback": [], "no_frontmatter": [],
                       "malformed": [], "dangling": [], "cross_layer": [], "collision": [],
                       "listing_missing": [], "listing_invalid": [], "category_invalid": [],
                       "category_missing": [], "listing_policy": []}
    report["collision"] = collisions
    policy = load_listing_policy(repo, spec)
    if policy:
        report["listing_policy"] = list(policy["errors"])
    sc_vocab = None
    if "skill_categories" in derived and spec.get("category_vocabulary"):
        sc_vocab, err = load_vocabulary(repo, spec["category_vocabulary"])
        if err:
            report["listing_policy"].append(err)

    for eid, p in found.items():
        fm = read_frontmatter(p)
        prev = cur.get(eid, {})
        e = dict(prev)                                     # PRESERVE everything by default
        rel = str(p.relative_to(repo))
        if not isinstance(fm, dict):
            bucket = "malformed" if str(fm).startswith("malformed") else "no_frontmatter"
            detail = str(fm).replace("malformed:", "").strip()
            report[bucket].append(f"{eid} ({rel})" + (f" — {detail}" if detail else ""))
            e.setdefault("path", rel)
            out[eid] = e
            if eid not in cur:
                report["new"].append(eid)
            continue

        if "path" in derived:
            e["path"] = rel
        if "source" in derived:
            e["source"] = provenance(repo, p)
        if "provider" in derived:
            # The hand-ordered manifests carried this as SECTION DIVIDERS (`# --- Provider:
            # Anthropic ---`). Generation sorts, so a divider stops meaning anything — but the
            # fact it carried is real. Derived from the path it already lives at, so it survives
            # as DATA rather than as layout, and cannot drift from where the file actually is.
            parts = p.relative_to(repo).as_posix().split("/")
            e["provider"] = (parts[parts.index("_external") + 1]
                             if "_external" in parts and len(parts) > parts.index("_external") + 1
                             else "internal")
        if "version" in derived and fm.get("version") is not None:
            newv = str(fm["version"])
            oldv = str(prev.get("version", ""))
            if oldv not in ("", newv):
                # A registry AHEAD of its file is not ordinary drift — deriving would DOWNGRADE
                # it, and a silent downgrade looks exactly like a correction. Ruled by the
                # workspace owner (2026-08-07): the FILE wins, but the downgrade is reported
                # loudly rather than applied quietly.
                bucket = "downgrade" if _ver(newv) < _ver(oldv) else "version"
                report[bucket].append(f"{eid}: registry {oldv} -> file {newv}")
            e["version"] = newv
        used, s = pointer(fm, spec.get("pointer_fields"))
        if field in derived and used:
            if used != (spec.get("pointer_fields") or POINTER_FIELDS)[0]:
                report["fallback"].append(f"{eid}: no `summary:`, used `{used}:` ({rel})")
            if prev.get(field) and " ".join(prev[field].split()) != s:
                report["summary"].append(eid)
            if len(s.split()) > budget:
                # `_external/` is exempt from the budget by the same convention that exempts it
                # from `summary:` — we may not edit those files, so filing them as fixable
                # defects creates a finding nobody is allowed to close.
                bucket = "budget_external" if provenance(repo, p) == "external" else "budget"
                report[bucket].append(f"{eid}: {len(s.split())}w (budget {budget}) — "
                                      f"shorten the `{used}:` in {rel}")
            e[field] = s
        if policy:
            lr = resolve_listing(eid, fm, provenance(repo, p), policy, rel)
            for bucket, msg in lr["problems"]:
                report[bucket].append(msg)
            # Derived means OWNED: a value that no longer resolves is removed, not preserved —
            # otherwise a skill whose listing was deleted would keep advertising the old one.
            for k in ("listing", "category"):
                if k in derived:
                    if lr[k] is not None:
                        e[k] = lr[k]
                    else:
                        e.pop(k, None)
        if "skill_categories" in derived:
            sc, why = derive_skill_categories(fm, sc_vocab)
            if why:
                report["category_invalid"].append(f"{eid}: skill_categories {why} ({rel})")
            if sc:
                e["skill_categories"] = sc
            else:
                e.pop("skill_categories", None)     # derived means owned: removed when the file drops it
        out[eid] = e
        if eid not in cur:
            report["new"].append(eid)

    gone_entries = []
    for eid, prev in cur.items():
        if eid in out:
            continue
        # An entry ALREADY DECLARED archived is not an absence — it is a tombstone someone wrote
        # on purpose, and re-reporting it as missing (or re-tombstoning it) turns a deliberate
        # declaration into noise. acme-health-main indexes nine archived Waystar skills this way.
        if prev.get("archived") is True:
            out[eid] = prev
            continue
        report["gone"].append(f"{eid} -> {prev.get('path','?')}")
        gone_entries.append(prev | {"id": eid})

    # a PRESERVED field naming a path that no longer exists is how `submitted-837s` ended up
    # marked live against an archived writer
    for eid, e in out.items():
        for k, v in e.items():
            if k in derived:
                continue
            for tok in re.findall(r"[\w./-]+\.(?:py|md|ya?ml|sh)", str(v)):
                if "/" not in tok:
                    continue
                where = resolve_ref(repo, tok)
                if where is None:
                    report["dangling"].append(f"{eid}.{k} -> {tok}")
                elif where != repo:
                    report["cross_layer"].append(f"{eid}.{k} -> {tok} (resolved under {where})")

    if spec["shape"] == "list":
        body = [dict({spec["id"]: k}, **v) for k, v in sorted(out.items())]
    else:
        body = {k: out[k] for k in sorted(out)}
    doc[spec["key"]] = body
    # ⚑ AN ENTRY WHOSE FILE IS GONE IS TOMBSTONED, NEVER DROPPED. Dropping it silently is the
    # thing `retired:` exists to prevent — "stopped being used" must stay distinguishable from
    # "never existed". Caught 2026-08-07 when the first apply removed three .sh/.mjs entries
    # without a trace.
    if gone_entries:
        retired = list(doc.get("retired") or [])
        known = " ".join(str(r.get("note", "")) for r in retired)
        for g in gone_entries:
            if g["id"] in known:
                continue
            retired.append({"ids": [g["id"]], "note": (
                f"{g['id']} — file no longer on disk at {g.get('path','?')}; tombstoned "
                f"automatically by build_registry.py. Last recorded: "
                f"{ {k: v for k, v in g.items() if k != 'id'} }")})
        doc["retired"] = retired
    rendered = header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    return {"name": name, "path": reg_path, "raw": raw, "rendered": rendered,
            "report": report, "comments_below": comments_below}


# ---------------------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--config", default=None)
    ap.add_argument("--only", help="one registry name from the map")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true", help="write even if comments would be lost")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()

    repo = Path(a.repo).resolve()
    cfg = yaml.safe_load(Path(a.config or repo / "config" / "registry-map.yaml").read_text())
    budget = int(cfg.get("summary_budget_words", 60))
    rc = 0
    for name, spec in cfg["registries"].items():
        if a.only and name != a.only:
            continue
        r = build(repo, name, spec, budget)
        rep, drift = r["report"], False
        print(f"\n── {name}  ({spec['file']})")
        for k, label in (("new", "present but UNINDEXED"), ("gone", "indexed but ABSENT"),
                         ("downgrade", "⚑ DOWNGRADE — registry was AHEAD of the file"),
                         ("version", "VERSION drift"), ("summary", "SUMMARY drift"),
                         ("budget", "OVER BUDGET — fix in the file"),
                         ("budget_external", "ℹ over budget in `_external/` — exempt, do not edit"),
                         ("fallback", "ℹ no `summary:`, fell back to `description:`"),
                         ("no_frontmatter", "no frontmatter"),
                         ("malformed", "⚑ MALFORMED frontmatter — will not parse"),
                         ("dangling", "preserved field -> MISSING path"),
                         ("collision", "⚑ ID COLLISION — two files claim one entry, one was DROPPED"),
                         ("listing_policy", "⚑ LISTING POLICY unreadable — sidecar/vocabulary"),
                         ("listing_invalid", "LISTING value not allowed"),
                         ("listing_missing", "LISTING missing — default applied, set it in the file"),
                         ("category_invalid", "CATEGORY not in the vocabulary"),
                         ("category_missing", "ℹ no category"),
                         ("cross_layer", "ℹ preserved field -> path OUTSIDE this repo (live)")):
            if rep[k]:
                # These are INFORMATION, not drift. cross_layer: the path resolves, it just
                # resolves in another layer. budget_external / fallback: both describe `_external/`
                # files the convention exempts and forbids us to edit — counting them as drift
                # makes the gate permanently red for a reason nobody is allowed to fix, which is
                # the same false-finding shape the cross_layer bucket was carved out to end.
                # category_missing: optional until the migration lands; listing_missing is not.
                drift = drift or k not in ("cross_layer", "budget_external", "fallback",
                                           "category_missing")
                print(f"   {label}: {len(rep[k])}")
                for x in rep[k][: (99 if k == "downgrade" else 6)]:
                    print(f"      - {x}")
        if not drift and r["raw"] == r["rendered"]:
            print("   clean")
            continue
        if not a.apply:
            d = list(difflib.unified_diff(r["raw"].splitlines(), r["rendered"].splitlines(),
                                          "current", "generated", lineterm="", n=0))
            print(f"   rebuild-and-diff: {sum(1 for x in d if x[:1] in '+-' and x[:3] not in ('---','+++'))} line(s) differ")
            rc = 1
            continue
        if r["comments_below"] and not a.force:
            print("   REFUSING to write — this manifest has comments below its header block and "
                  "PyYAML cannot round-trip them.\n"
                  "   Move them into the header, or re-run with --force to discard them.")
            rc = 2
            continue
        r["path"].write_text(r["rendered"], encoding="utf-8")
        print(f"   wrote {spec['file']}")
    return rc


def self_check() -> int:
    """Two-sided: honest input produces no drift, corrupted input MUST produce drift."""
    import tempfile, shutil
    ok = True
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / "skills" / "demo").mkdir(parents=True)
        (repo / "registry").mkdir()
        (repo / "config").mkdir()
        (repo / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\nsummary: A short pointer.\nversion: 2.0.0\n---\nbody\n")
        (repo / "config" / "registry-map.yaml").write_text(yaml.safe_dump({
            "summary_budget_words": 60,
            "registries": {"skills": {"file": "registry/skills.yaml", "key": "skills",
                                      "shape": "list", "id": "name",
                                      "globs": ["skills/*/SKILL.md"], "field": "description",
                                      "derived": ["path", "version", "description"]}}}))
        (repo / "registry" / "skills.yaml").write_text("# summary: test\nskills: []\n")
        cfg = yaml.safe_load((repo / "config" / "registry-map.yaml").read_text())
        spec = cfg["registries"]["skills"]

        r = build(repo, "skills", spec, 60)
        if "demo" not in r["report"]["new"]:
            print("FAIL: an unindexed file was not reported"); ok = False
        (repo / "registry" / "skills.yaml").write_text(r["rendered"])

        r2 = build(repo, "skills", spec, 60)
        if r2["raw"] != r2["rendered"] or any(r2["report"].values()):
            print("FAIL: regenerating a clean manifest is not a no-op"); ok = False

        # corrupt the registry version — the gate MUST notice
        bad = r2["rendered"].replace("2.0.0", "1.0.0")
        (repo / "registry" / "skills.yaml").write_text(bad)
        r3 = build(repo, "skills", spec, 60)
        if not r3["report"]["version"]:
            print("FAIL: version drift not detected — the gate cannot fail"); ok = False

        # preserved field pointing at a missing path MUST be flagged
        (repo / "registry" / "skills.yaml").write_text(
            r2["rendered"].replace("  path: skills/demo/SKILL.md",
                                   "  path: skills/demo/SKILL.md\n  engine: engines/gone.py"))
        r4 = build(repo, "skills", spec, 60)
        if not r4["report"]["dangling"]:
            print("FAIL: dangling preserved path not detected"); ok = False

        # ...and the other side: a CROSS-LAYER path that genuinely exists one level up must NOT be
        # reported dangling. Without this half the check passes while calling every live
        # sibling-layer reference missing — which is exactly what it did until 2026-08-08.
        sibling = repo.parent / "sibling-layer" / "executions"
        sibling.mkdir(parents=True, exist_ok=True)
        (sibling / "real.py").write_text("x = 1\n")
        (repo / "registry" / "skills.yaml").write_text(
            r2["rendered"].replace(
                "  path: skills/demo/SKILL.md",
                "  path: skills/demo/SKILL.md\n  engine: sibling-layer/executions/real.py"))
        r5 = build(repo, "skills", spec, 60)
        if r5["report"]["dangling"]:
            print(f"FAIL: live cross-layer path reported dangling: {r5['report']['dangling']}")
            ok = False
        if not r5["report"]["cross_layer"]:
            print("FAIL: cross-layer resolution not reported at all — it is a real coupling")
            ok = False
        shutil.rmtree(sibling.parent)

        # `description:` MUST fill the entry when `summary:` is absent, and the substitution must
        # be REPORTED. Without the fallback, the 7 `_external/` skills that validate_registry
        # reports as "missing a pointer field" can never reach conformance — the convention
        # exempts them from carrying `summary:` and forbids editing them.
        (repo / "skills" / "descr").mkdir(parents=True, exist_ok=True)
        (repo / "skills" / "descr" / "SKILL.md").write_text(
            "---\nname: descr\ndescription: Only a harness description.\nversion: 1.0.0\n---\n")
        r7 = build(repo, "skills", spec, 60)
        got7 = {e["name"]: e for e in yaml.safe_load(r7["rendered"])["skills"]}
        if got7.get("descr", {}).get("description") != "Only a harness description.":
            print("FAIL: `description:` did not fill the entry when `summary:` was absent"); ok = False
        if "descr" not in " ".join(r7["report"]["fallback"]):
            print("FAIL: the fallback to `description:` was silent"); ok = False
        # ...and `summary:` still WINS wherever both are present, or the manifest and the index
        # would describe the same file differently
        (repo / "skills" / "both").mkdir(parents=True, exist_ok=True)
        (repo / "skills" / "both" / "SKILL.md").write_text(
            "---\nname: both\nsummary: The summary wins.\ndescription: The description loses.\n"
            "version: 1.0.0\n---\n")
        r8 = build(repo, "skills", spec, 60)
        got8 = {e["name"]: e for e in yaml.safe_load(r8["rendered"])["skills"]}
        if got8.get("both", {}).get("description") != "The summary wins.":
            print("FAIL: `description:` beat `summary:` — the pointer precedence is inverted"); ok = False
        if "both" in " ".join(r8["report"]["fallback"]):
            print("FAIL: a file WITH `summary:` was reported as a fallback"); ok = False

        # a hand-authored field MUST survive regeneration
        if "engine" not in [k for e in yaml.safe_load(r4["rendered"])["skills"] for k in e]:
            print("FAIL: preserved field was dropped"); ok = False
        # an id collision must be REPORTED, never silently resolved by last-write-wins
        (repo / "skills" / "dup").mkdir(parents=True, exist_ok=True)
        (repo / "skills" / "dup" / "SKILL.md").write_text(
            "---\nname: dup\nsummary: One.\nversion: 1.0.0\n---\n")
        (repo / "nested" / "dup").mkdir(parents=True, exist_ok=True)
        (repo / "nested" / "dup" / "SKILL.md").write_text(
            "---\nname: dup\nsummary: Two.\nversion: 1.0.0\n---\n")
        spec2 = dict(spec, globs=["skills/*/SKILL.md", "nested/*/SKILL.md"])
        r6 = build(repo, "skills", spec2, 60)
        if not r6["report"]["collision"]:
            print("FAIL: an id collision was silently resolved instead of reported"); ok = False

    ok = _self_check_listing() and ok
    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


def _self_check_listing() -> bool:
    """Provenance + listing/category resolution, each case two-sided (2026-10-16)."""
    import tempfile
    ok = True

    def fail(msg):
        nonlocal ok
        print(f"FAIL: {msg}")
        ok = False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "my-lib"
        sk = repo / "skills"
        sk.mkdir(parents=True)
        (repo / "config").mkdir()

        def skill(where: Path, body: str) -> Path:
            where.mkdir(parents=True, exist_ok=True)
            (where / "SKILL.md").write_text(f"---\nname: {where.name}\n{body}summary: S.\n---\n")
            return where

        # targets for each provenance, linked into the repo the way link_skills links them
        skill(sk / "own-on", "listing: on\ncategory: writing\n")      # bare `on` -> YAML True
        skill(sk / "own-bare", "")                                     # internal, nothing set
        skill(sk / "own-off", "listing: off\n")                        # off is sidecar-only
        skill(sk / "own-badcat", "listing: name-only\ncategory: nonsense\n")
        skill(sk / "own-fm-beats", "listing: name-only\ncategory: writing\n")
        ext = skill(root / "team-lib" / "skills" / "_external" / "pack" / "pdf", "")
        ext2 = skill(root / "team-lib" / "skills" / "_external" / "pack" / "art", "")
        team = skill(root / "team-lib" / "skills" / "shared", "")
        proj = skill(root / "projects" / "p" / "skills" / "inbox", "")
        sysd = skill(root / "usr-share" / "skills" / "crash", "")
        sync = skill(root / "dot-claude" / "skills" / "synced" / "u" / "docx", "")
        arch = skill(sk / "_archived" / "old", "")
        for name, target in (("ext-pdf", ext), ("ext-art", ext2), ("shared", team),
                             ("inbox", proj), ("crash", sysd), ("docx", sync)):
            (sk / name).symlink_to(target, target_is_directory=True)

        # provenance: only /_external/ is external; the bug labelled every other outside target so
        for name, want in (("ext-pdf", "external"), ("shared", "team"), ("inbox", "project"),
                           ("crash", "system"), ("docx", "synced"), ("own-bare", "local")):
            got = provenance(repo, sk / name / "SKILL.md")
            if got != want:
                fail(f"provenance({name}) = {got}, want {want}")

        (repo / "config" / "personal.yaml").write_text(
            "skills:\n  ext-pdf: {listing: name-only}\n  inbox: {listing: 'off', category: writing}\n"
            "  own-fm-beats: {listing: user-only, category: design}\n  ext-art: {listing: loud}\n")
        (repo / "config" / "team.yaml").write_text(
            "skills:\n  ext-pdf: {listing: user-only, category: documents}\n"
            "  ext-art: {category: design}\n")
        (repo / "config" / "vocab.yaml").write_text(
            "categories:\n  writing: W.\n  documents: D.\n  design: X.\n")
        spec = {"derived": ["path", "listing", "category"],
                "listing_sidecars": ["config/personal.yaml", "config/team.yaml"],
                "category_vocabulary": "config/vocab.yaml",
                "listing_defaults": {"external": "user-only", "synced": "user-only",
                                     "system": "name-only", "team": "name-only",
                                     "local": "name-only", "project": "name-only"},
                "listing_required": ["team", "local", "project"],
                "listing_not_linked": ["/_archived/"]}
        pol = load_listing_policy(repo, spec)
        if pol["errors"]:
            fail(f"a valid policy reported errors: {pol['errors']}")

        def res(name, path=None):
            p = sk / name / "SKILL.md" if path is None else path
            return resolve_listing(name, read_frontmatter(p), provenance(repo, p), pol, str(p))

        def buckets(r):
            return {b for b, _ in r["problems"]}

        r = res("own-on")
        if (r["listing"], r["listing_source"]) != ("on", "frontmatter"):
            fail(f"bare `listing: on` (YAML True) did not derive as 'on': {r}")
        if buckets(r):
            fail(f"a fully-specified skill reported problems: {r['problems']}")
        r = res("own-bare")
        if r["listing"] != "name-only" or "listing_missing" not in buckets(r):
            fail(f"an internal skill with no listing must default to name-only AND be reported: {r}")
        r = res("ext-pdf")       # personal sidecar beats team sidecar beats default
        if (r["listing"], r["listing_source"]) != ("name-only", "sidecar:config/personal.yaml"):
            fail(f"the first sidecar did not win: {r}")
        if r["category"] != "documents":
            fail(f"category did not fall through to the second sidecar: {r}")
        if "listing_missing" in buckets(r):
            fail("an external was reported listing_missing — externals are never required")
        r = res("ext-art")       # invalid sidecar value reported, default still applied
        if "listing_invalid" not in buckets(r) or r["listing"] != "user-only":
            fail(f"an invalid sidecar listing must be reported and fall to the default: {r}")
        r = res("own-fm-beats")  # frontmatter beats every sidecar, for both fields
        if (r["listing"], r["category"]) != ("name-only", "writing"):
            fail(f"frontmatter did not beat the sidecar: {r}")
        r = res("own-off")
        if "listing_invalid" not in buckets(r):
            fail("`listing: off` in FRONTMATTER was accepted — it is sidecar-only")
        r = res("inbox")         # ...but `off` IS accepted from a sidecar
        if r["listing"] != "off" or "listing_invalid" in buckets(r):
            fail(f"`off` from a sidecar was refused: {r}")
        r = res("own-badcat")
        if "category_invalid" not in buckets(r):
            fail("a category outside the vocabulary was not reported")
        r = res("crash")         # system: default, NOT reported missing (cannot carry frontmatter)
        if r["listing"] != "name-only" or "listing_missing" in buckets(r):
            fail(f"a system skill must take its default silently: {r}")
        r = res("docx")
        if r["listing"] != "user-only" or "listing_missing" in buckets(r):
            fail(f"a synced skill must take its default silently: {r}")
        r = res("old", arch / "SKILL.md")
        if not r["not_linked"] or r["problems"]:
            fail(f"an archived skill must be skipped, not reported: {r}")

        # the manifest itself: derived fields present, an unreadable sidecar is an ERROR
        (repo / "registry").mkdir()
        mspec = dict(spec, file="registry/skills.yaml", key="skills", shape="list", id="name",
                     globs=["skills/*/SKILL.md"], field="description",
                     derived=["path", "description", "source", "listing", "category"])
        b = build(repo, "skills", mspec, 60)
        got = {e["name"]: e for e in yaml.safe_load(b["rendered"])["skills"]}
        if got.get("ext-pdf", {}).get("listing") != "name-only" or got["inbox"]["source"] != "project":
            fail(f"manifest did not carry derived listing/source: {got.get('ext-pdf')}, {got.get('inbox')}")
        if not b["report"]["listing_missing"]:
            fail("build() did not surface listing_missing in its report")
        b2 = build(repo, "skills", dict(mspec, listing_sidecars=["config/nope.yaml"]), 60)
        if not b2["report"]["listing_policy"]:
            fail("a missing sidecar was not reported — it would silently revert every override")
        # derived means owned: a value that stops resolving is REMOVED from the entry
        (repo / "registry" / "skills.yaml").write_text(b["rendered"])
        (sk / "own-on" / "SKILL.md").write_text("---\nname: own-on\nsummary: S.\n---\n")
        b3 = build(repo, "skills", mspec, 60)
        got3 = {e["name"]: e for e in yaml.safe_load(b3["rendered"])["skills"]}
        if "category" in got3["own-on"]:
            fail("a category deleted from the file survived in the manifest")

        # personas: skill_categories derived from frontmatter, vocabulary-checked, owned
        pdir = repo / "personas"
        pdir.mkdir()
        (pdir / "good.md").write_text("---\nname: good\nsummary: G.\n"
                                      "skill_categories: [writing, design]\n---\n")
        (pdir / "bare.md").write_text("---\nname: bare\nsummary: B.\nskill_categories: writing\n---\n")
        (pdir / "bad.md").write_text("---\nname: bad\nsummary: X.\n"
                                     "skill_categories: [writing, billing-for-acme]\n---\n")
        (pdir / "none.md").write_text("---\nname: none\nsummary: N.\n---\n")
        pspec = {"file": "registry/personas.yaml", "key": "personas", "shape": "list", "id": "name",
                 "globs": ["personas/*.md"], "field": "description",
                 "derived": ["path", "description", "skill_categories"],
                 "category_vocabulary": "config/vocab.yaml"}
        pb = build(repo, "personas", pspec, 60)
        pg = {e["name"]: e for e in yaml.safe_load(pb["rendered"])["personas"]}
        if pg["good"].get("skill_categories") != ["writing", "design"]:
            fail(f"persona skill_categories not derived: {pg['good']}")
        if pg["bare"].get("skill_categories") != ["writing"]:
            fail(f"a bare-string skill_categories was not read as a one-item list: {pg['bare']}")
        if "skill_categories" in pg["none"]:
            fail("a persona with no skill_categories got one in the manifest")
        if not any("bad" in m for m in pb["report"]["category_invalid"]):
            fail("a persona category outside the vocabulary was not reported")
        if any(m.startswith(("good", "bare")) for m in pb["report"]["category_invalid"]):
            fail(f"valid persona categories were reported invalid: {pb['report']['category_invalid']}")
        # owned: dropping the field from the file removes it from the manifest
        (repo / "registry" / "personas.yaml").write_text(pb["rendered"])
        (pdir / "good.md").write_text("---\nname: good\nsummary: G.\n---\n")
        pg2 = {e["name"]: e for e in yaml.safe_load(build(repo, "personas", pspec, 60)["rendered"])["personas"]}
        if "skill_categories" in pg2["good"]:
            fail("skill_categories deleted from the persona file survived in the manifest")
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
