#!/usr/bin/env python3
# ---
# template: execution
# version: 1.4.0
# summary: Validate registry manifests that CANNOT be generated — the bucketed/sectioned kinds
#          where a human chose the grouping. Parse-checks every manifest, reports coverage in
#          both directions, enum-checks skill listing/category, honours declared exclusions, and
#          runs the frontmatter census (including skills with no `listing:`).
# created: 2026-08-08
# last_updated: 2026-10-16
# maintainer: pvragon
# known_limitations: >-
#   Coverage is only computed for kinds whose on-disk set is cheaply enumerable and declared in
#   the repo's registry-map (`validate.coverage`). A kind with no mapping is parse-checked only,
#   and says so rather than printing a green line it has not earned.
# ---
"""The half of registry conformance that GENERATION cannot do.

`build_registry.py` regenerates a manifest whose entries are 1:1 with files, deriving each field
from that file's own frontmatter. That covers most manifests and removes the second owner.

It cannot cover the rest. Some manifests are deliberately NOT 1:1 with the disk: `docs.yaml`
groups documents into topical sections, `_bucket_*` entries stand for whole trees via `covers:`,
and `excluded:` blocks record trees considered and rejected WITH A REASON. Every one of those is
a human judgement recorded nowhere else — regenerating them would erase the judgement, which is
the precise failure the generator exists to avoid. So they are VALIDATED instead of generated,
and this is the tool that does it.

WHY IT EXISTS AT ALL. A registry broke twice in three days, both times identically: an unescaped
apostrophe inside a single-quoted YAML scalar (`the '837 wins the tiebreaker' rule`). YAML needs
'' for a literal quote there. These files are read FIRST and always loaded — so a parse error
means every consumer gets an exception instead of an index, silently, until someone happens to
run yaml.safe_load by hand. Nothing validated it. Now something does.

⚑ `--docs-coverage` WAS A SILENT NO-OP until 2026-08-06. `_coverage()` returned [] for the
`sections` kind, which is the kind `docs.yaml` declares, so the flag parsed and changed nothing:
every run printed OK on four manifests, which meant they PARSE, not that they COVER. 85 entries
stood against 1,491 markdown files and the gate said nothing. A gate that cannot fail measures
nothing. Three things were needed to make it real rather than merely make it run:

  1. the residue had to stop being noise — coverage reports BY DIRECTORY with counts, and
     --verbose gives the file list. A gate whose output nobody can read gets ignored just as
     thoroughly as one that never fires.
  2. GENERATED trees had to be declarable, in `excluded:` with a reason, so "considered and
     excluded" stays distinguishable from "never considered".
  3. bucket entries had to declare what they cover. A bucket standing for a whole tree while
     naming none of it cannot suppress its own files; `covers:` is read, and a bucket without
     one covers nothing — which is the honest answer, not a convenient one.

Graduated from acme-health-main/tools/validate_registry.py on 2026-08-08 and generalized: the repo
is an argument rather than this file's own location, and the coverage kinds come from the repo's
registry-map instead of being hardcoded to that one repo's layout.

    python3 validate_registry.py [--repo DIR] [path ...] [--docs-coverage] [--frontmatter] [--verbose]

Exit 0 = clean. Exit 1 = broken, with the offending line and column printed.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_registry import read_frontmatter          # noqa: E402  one frontmatter reader, not two
import build_registry as BR                          # noqa: E402  one listing resolver, not two

# An entry must carry a POINTER field. Which name it uses is a layer convention, not a truth:
# acme-health-main says `summary:`, team-lib says `description:`. Requiring one name reported all 48
# team-lib executions as structurally broken when every one of them was fine.
REQUIRED_ANY = ("summary", "description")
REQUIRED_DOC_FIELDS = REQUIRED_ANY  # back-compat alias

# Each manifest declares its entries under a different top-level key, because the kinds are not
# the same shape: docs nest in topical sections, everything else is a flat mapping or list.
#
# ⚑ THIS LIST IS WHY A WHOLE LAYER WENT UNVALIDATED. It held only the three kinds acme-health-main
# happens to use, so pointing the validator at team-lib — whose manifests key on `executions`,
# `directives`, `personas`, `context`, `integrations` — reported "0 manifests OK" and exited 0.
# Not a failure, not a warning: it recognised nothing and said nothing, which is indistinguishable
# from a clean repo. Extend via `validate.collection_keys` in a repo's registry-map rather than
# editing this default, so the next layer does not repeat it. Measured 2026-08-08.
DEFAULT_COLLECTION_KEYS = ("sections", "skills", "sources", "executions", "directives",
                           "personas", "context", "integrations", "packs")
COLLECTION_KEYS = DEFAULT_COLLECTION_KEYS

# ⚑ `_archive` AND `_archived` — the same concept, two spellings, both live on disk. Naming only
# one leaves the other unbounded, which is the narrow-glob shape: team-lib carries
# `context/indexed/_archived/` and `skills/_archived/`, holding superseded copies of documents that
# also exist live, so every one was counted twice and its archived twin reported as a gap.
SKIP_DIRS = (".git", "archive", "node_modules", "_archive", "_archived", "__pycache__")

# Fallback only. The repo's registry-map `validate.coverage` block is authoritative when present;
# these defaults exist so a repo with no map still gets the checks its layout obviously supports.
#
# ⚑ `skip_prefixes` DIFFERS BY KIND AND MUST. A `_`-prefixed directory under skills/ is
# scaffolding (`_staging`, `_external`); under a data root it is an ordinary source that happens
# to sort first (`_archive`, `_staging`). The first version of this generalization applied one
# filter to both and silently traded one finding for a false one — it stopped reporting an
# unindexed `data/_staging` and started reporting a live `data/_archive` as missing. Same run,
# same exit code, both wrong. Per-kind, and declared in config rather than buried in an if/elif,
# so the asymmetry is visible to whoever next wonders why.
DEFAULT_COVERAGE = {
    "skills": {"dir": "skills", "skip_prefixes": [".", "_"]},
    "sources": {"dir": "data", "skip_prefixes": ["."]},
}
DEFAULT_DOCS_ROOT = "docs"


def _cov_spec(cov_map: dict, kind: str) -> dict | None:
    """Normalize a coverage entry: a bare string is the directory, a dict is the full spec."""
    spec = cov_map.get(kind)
    if not spec:
        return None
    if isinstance(spec, str):
        spec = {"dir": spec}
    if not isinstance(spec, dict) or not spec.get("dir"):
        return None
    return {"dir": spec["dir"],
            "skip_prefixes": tuple(spec.get("skip_prefixes",
                                            DEFAULT_COVERAGE.get(kind, {}).get(
                                                "skip_prefixes", ["."])))}


# ---------------------------------------------------------------------------- config
def load_settings(repo: Path, config: str | None) -> dict:
    """`validate:` block from the repo's registry-map, or {} — never a guess dressed as config."""
    p = Path(config) if config else repo / "config" / "registry-map.yaml"
    if not p.exists():
        return {}
    try:
        return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("validate") or {}
    except yaml.YAMLError as exc:
        print(f"WARNING: {p} did not parse ({exc.__class__.__name__}); using defaults")
        return {}


# ---------------------------------------------------------------------------- helpers
def _show(path: Path, line: int, col: int) -> None:
    """Print the offending line with a caret, so the fix is obvious rather than hunted."""
    try:
        src = path.read_text(encoding="utf-8").split("\n")
    except OSError:
        return
    if not (1 <= line <= len(src)):
        return
    text = src[line - 1]
    lo = max(0, col - 60)
    print(f"\n  line {line}, col {col}:")
    print(f"    {text[lo:col + 60]}")
    print(f"    {' ' * (col - lo - 1)}^")
    stripped = text.strip()
    if stripped.startswith(("summary:", "description:")) and "'" in text:
        print("\n  LIKELY CAUSE: an unescaped apostrophe inside a single-quoted YAML scalar.")
        print("  In single quotes a literal ' must be DOUBLED:  'the ''837 wins'' rule'")


def _entries(data: dict, keys=None) -> tuple[str, dict]:
    """(kind, {entry_id: meta}) for whichever collection key this manifest uses."""
    if isinstance(data.get("sections"), dict):
        flat = {}
        for _sname, sec in data["sections"].items():
            if isinstance(sec, dict):
                for dpath, meta in (sec.get("documents") or {}).items():
                    flat[dpath] = meta
        return "sections", flat
    for key in (keys or COLLECTION_KEYS):
        v = data.get(key)
        if isinstance(v, dict) and v:
            return key, v
        # a LIST manifest (personas, skills in some layers) is identified by each entry's `name`
        if isinstance(v, list) and v and all(isinstance(e, dict) for e in v):
            return key, {e.get("name") or e.get("id") or str(i): e for i, e in enumerate(v)}
    return "", {}


def _is_skipped(relpath: str) -> bool:
    parts = relpath.replace("\\", "/").split("/")
    return any(p in SKIP_DIRS or p.startswith("v1-backup-snapshot") for p in parts)


def classify(path: Path) -> tuple[str, str]:
    """(verdict, detail) — one of `ok`, `no-summary`, `absent`, `malformed`.

    Shares build_registry's reader rather than keeping a second one. Also accepts the leading
    `# summary:` comment form, which yaml and python files here use by convention.

    ⚑ FOUR STATES, NOT TWO, and the predecessor collapsed them lexically. It asked only whether
    some line in the block STARTED WITH `summary:` — so 22 acme-health-main documents whose
    frontmatter no YAML parser can read (an unquoted `: ` inside a plain scalar) were counted as
    fully compliant. A lexical answer to a structural question, and it inflated the census from
    24 gaps to 2. `malformed` is not a worse `absent`: a file with no frontmatter needs one
    written, a file with broken frontmatter needs one QUOTED, and the census cannot send you to
    the right fix if it prints the same word for both.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            if fh.readline().startswith("# summary:"):
                return "ok", ""
    except OSError:
        return "absent", "unreadable"
    fm = read_frontmatter(path)
    if isinstance(fm, dict):
        return ("ok", "") if fm.get("summary") else ("no-summary", "")
    detail = str(fm)
    if detail.startswith("malformed"):
        return "malformed", detail.replace("malformed:", "").strip()
    return "absent", ""


def has_frontmatter(path: Path) -> tuple[bool, bool]:
    """(has_frontmatter, has_summary) — kept for callers that only want the coarse answer."""
    v, _ = classify(path)
    return v != "absent", v == "ok"


def _declared_exclusions(data: dict) -> list[tuple[str, str]]:
    """`excluded:` entries as (path-or-glob, reason). Declared, never silently absent."""
    out = []
    for e in (data.get("excluded") or []):
        if isinstance(e, dict) and e.get("path"):
            out.append((str(e["path"]).rstrip("/"), e.get("reason", "")))
    return out


CONVENTION_EXEMPT_LINES = 15


def convention_exempt(repo: Path, rel: str) -> str | None:
    """Why progressive-disclosure-convention.md excuses this file from carrying a `summary:`.

    ⚑ The convention has always had an "Exempt Files" list; the census could not see it, so it
    counted every exempt file as a gap. Measured 2026-08-08: team-lib reported 317 gaps of which
    the overwhelming majority are `_external/` third-party files we are FORBIDDEN to modify — a
    census whose number can only be reduced by breaking a rule is not measuring conformance, it
    is manufacturing a backlog nobody may work.

    Kept in code rather than in each repo's registry-map on purpose: these three are workspace-wide
    rules from one convention document, not a per-repo judgement. Per-repo judgement is what
    `validate.non_index` and the manifests' own `exclude:` lists are for, and those still apply
    first. Returns a REASON so the report can say which rule fired, never a bare bool.
    """
    parts = rel.replace("\\", "/").split("/")
    if "_external" in parts:
        return "third-party under _external/ (must not be modified)"
    if len(parts) <= 2 and parts[-1] in ("README.md", "CHANGELOG.md"):
        return "README/CHANGELOG at a project root"
    try:
        n = sum(1 for _ in (repo / rel).open(encoding="utf-8", errors="ignore"))
    except OSError:
        return None
    if n <= CONVENTION_EXEMPT_LINES:
        # The reason string is the RULE, not the measurement — it is used as a grouping key in the
        # report, and embedding each file's own line count would split one rule into N rows.
        return f"under {CONVENTION_EXEMPT_LINES} lines"
    return None


def is_excluded(rel: str, excl: list) -> bool:
    """Does a declared exclusion cover this path?

    Globs are the point: `data/v1-snapshots/*/catalog` keeps covering the NEXT snapshot, where an
    enumerated path would silently stop at the ones that existed the day it was written. An
    exclusion list that rots reopens the gap it was added to close.
    """
    rel = rel.replace("\\", "/")
    for pat, _reason in excl:
        if rel == pat or rel.startswith(pat + "/"):
            return True
        if "*" in pat and (fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat + "/*")):
            return True
    return False


def _ranked(counter: Counter, limit: int) -> list:
    """Most-common, with ties broken by NAME so the report is byte-stable across runs.

    `Counter.most_common` breaks ties by insertion order, and these counters are built by
    iterating a set — so two runs over an unchanged tree printed the same directories in a
    different order. That is invisible day to day and fatal to the one use that matters most:
    rebuild-and-diff. A drift gate whose clean output differs from its own previous clean output
    cannot be diffed, so it silently stops being usable as a gate.
    """
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def _md_under(root: Path, rel_prefix: str = "") -> set:
    out = set()
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), root)
            if not _is_skipped(rel):
                out.add(os.path.join(rel_prefix, rel) if rel_prefix else rel)
    return out


# ---------------------------------------------------------------------------- coverage
def _docs_coverage(repo: Path, docs_rel: str, entries: dict, data: dict,
                   verbose: bool) -> list[str]:
    """Which files under the docs root no entry, bucket or exclusion accounts for.

    Reported BY DIRECTORY, because 1,400 raw paths is a list nobody reads — and an unread gate
    fails exactly as silently as an unfired one.
    """
    docs_root = repo / docs_rel
    if not docs_root.is_dir():
        return []
    disk = _md_under(docs_root)
    pre = docs_rel.rstrip("/") + "/"

    covered = {p[len(pre):] if p.startswith(pre) else p for p in entries}
    prefixes = []
    for _epath, meta in entries.items():
        if isinstance(meta, dict):
            for c in (meta.get("covers") or []):
                c = str(c).rstrip("/")
                prefixes.append(c[len(pre):] if c.startswith(pre) else c)
    excl = _declared_exclusions(data)

    residue = {f for f in disk - covered
               if not any(f == p or f.startswith(p + "/") for p in prefixes)
               and not is_excluded(pre + f, excl)}

    out = []
    if residue:
        by_dir = Counter(os.path.dirname(f) or "." for f in residue)
        out.append(f"{len(residue)} {docs_rel}/ file(s) accounted for by NO entry, "
                   f"bucket or exclusion:")
        for d, n in _ranked(by_dir, 15 if not verbose else 10_000):
            out.append(f"    {n:>5}  {pre}{d}")
        if not verbose and len(by_dir) > 15:
            out.append(f"    … and {len(by_dir) - 15} more directories (--verbose for all)")
    return out


def _is_archived(meta) -> bool:
    """Has this entry DECLARED itself archived, in either spelling?

    Two spellings are live: the original `archived: true` and acme-health-main's `liveness: archived`
    (which pairs with a `liveness_basis:` recording where the tree moved and when that was
    measured). One helper because TWO checks ask this question, and they answered it differently
    until 2026-08-08 — `_coverage` honoured only the first spelling and the indexed-path check
    honoured neither, so three correctly-declared archives were reported as absences by one
    checker and not the other. A declared archive is a statement, not an absence.
    """
    if not isinstance(meta, dict):
        return False
    return bool(meta.get("archived")) or str(meta.get("liveness", "")).lower() == "archived"


def _coverage(repo: Path, kind: str, entries: dict, cov_map: dict) -> list[str]:
    """Set difference against disk, for kinds whose on-disk set is cheaply enumerable.

    Present-but-unindexed is the half that is usually invisible: nothing ever told anyone that
    four skills and fourteen data sources had no entry.
    """
    spec = _cov_spec(cov_map, kind)
    if not spec:
        return []
    root = repo / spec["dir"]
    if not root.is_dir():
        return []
    disk = {d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(spec["skip_prefixes"])}

    # ⚑ AN ENTRY'S DECLARED `path:` IS THE TRUTH; ITS KEY IS ONLY A NAME. This used to compare
    # keys against directory names under ONE root, which produced false "INDEXED but not present"
    # on a CORRECT index in two ways, both reported by a peer session on 2026-08-08 with evidence:
    #
    #   * acme-health-main indexes `load-acme-health-cfo` at `.claude/skills/load-acme-health-cfo/SKILL.md`
    #     and globs that tree in its registry-map. Coverage looked only under `skills/`, so a
    #     present, correctly-indexed skill was reported missing on every run.
    #   * three data sources carry `liveness: archived` with a measured new location; only the
    #     older `archived: true` spelling was honoured, so all three read as absent.
    #
    # Same discipline build_registry.provenance() already uses: resolve the location, never infer
    # it from a name. And a coverage warning that fires on a correct index is worse than none —
    # it trains the reader to skim the one block where a REAL missing source would appear.
    claimed, missing = set(), []
    for k, v in entries.items():
        v = v if isinstance(v, dict) else {}
        if _is_archived(v):
            continue                      # a DECLARED archive is a statement, not an absence
        declared = v.get("path")
        if declared:
            target = repo / str(declared)
            if not target.exists():
                missing.append(k)
                continue
            try:                          # does it sit under this kind's root? then it claims a dir
                claimed.add(target.resolve().relative_to(root.resolve()).parts[0])
            except ValueError:
                pass                      # legitimately lives elsewhere — declared and present
        elif k in disk:
            claimed.add(k)
        else:
            missing.append(k)

    out = [f"UNINDEXED on disk but absent from the manifest: {n}" for n in sorted(disk - claimed)]
    out += [f"INDEXED but not present in this checkout: {n}" for n in sorted(missing)]
    return out


# ---------------------------------------------------------------------------- validate
def validate_one(repo: Path, path: Path, settings: dict, docs_coverage: bool = False,
                 verbose: bool = False) -> int:
    if not path.exists():
        print(f"FAIL: {path} not found")
        return 1

    # 1. it must parse at all — the failure that actually happened, twice
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"FAIL: {path} is not valid YAML")
        print(f"  {getattr(e, 'problem', e)}")
        mark = getattr(e, "problem_mark", None)
        if mark is not None:
            _show(path, mark.line + 1, mark.column + 1)
        return 1

    # 2. shape — a file that parses but is structurally wrong is still broken
    if not isinstance(data, dict):
        print(f"FAIL: {path}: top level is not a mapping")
        return 1
    if path.name in set(settings.get("non_index") or ()):
        # Declared not-an-index. Checked BEFORE key detection on purpose: a non-index manifest can
        # still contain a word this tool treats as a collection key, and then it would be judged
        # as an index — skills-scan-state.yaml has `sources:`, workspace.yaml has `workspace:`.
        # One failed loudly and the other passed FALSELY, which is the more dangerous outcome.
        print(f"SKIP: {path.name} — declared not-an-index in registry-map validate.non_index")
        return 0
    required_any = tuple(settings.get("required_any") or REQUIRED_ANY)
    kind, entries = _entries(data, settings.get("collection_keys"))
    if not kind:
        # Not every manifest is an index. mirror.yaml is a publication contract, workspace.yaml a
        # topology, skills-scan-state.yaml scanner state. Those are fine — but they have to be
        # DECLARED, because "has no entries" and "is not that kind of file" look identical from
        # here, and silently passing the second would make this gate unable to fail on the first.
        if path.name in set(settings.get("non_index") or ()):
            print(f"SKIP: {path.name} — declared not-an-index in registry-map validate.non_index")
            return 0
        print(f"FAIL: {path}: no recognised collection key "
              f"(expected one of {', '.join(COLLECTION_KEYS)}). If this manifest is not an index, "
              f"declare it in registry-map `validate.non_index`.")
        return 1
    if not entries:
        print(f"FAIL: {path}: `{kind}` is empty")
        return 1

    problems: list[str] = []
    for epath, meta in entries.items():
        if not isinstance(meta, dict):
            problems.append(f"{epath}: entry is not a mapping")
            continue
        if not any(meta.get(f) for f in required_any):
            problems.append(f"{epath}: missing a pointer field ({' or '.join(required_any)})")
    if kind == "skills":
        problems += _listing_problems(repo, entries, settings)

    # 3. referenced files should exist — catches a doc renamed or deleted without updating the
    #    index. Paths are relative to EITHER the docs root or the repo root; both conventions are
    #    live, so accept either. A gate that reports false positives gets ignored, which is worse
    #    than no gate.
    docs_rel = settings.get("docs_root", DEFAULT_DOCS_ROOT)
    missing = []
    for epath, meta in entries.items():
        if epath.startswith("_bucket") or epath.endswith("/"):
            continue                       # bucket entries and directory refs are not files
        if _is_archived(meta):
            continue                       # declared archive: it lives elsewhere on purpose
        cand = epath
        if isinstance(meta, dict) and meta.get("path"):
            cand = meta["path"]            # skills.yaml keys are names, not paths
        elif kind == "sources":
            # ⚑ `elif`, not `if`. This branch used to OVERRIDE a declared `path:` with
            # `<data-dir>/<key>`, so an entry that correctly recorded where it lives was judged
            # against a guess assembled from its name — the same key-over-path bug `_coverage`
            # carried. A declared path wins; the key is only the fallback.
            _s = _cov_spec(settings.get("coverage", DEFAULT_COVERAGE), "sources")
            cand = os.path.join(_s["dir"] if _s else "data", epath)
        if any((root / cand).exists() for root in (repo / docs_rel, repo)):
            continue
        missing.append(epath)

    if problems:
        print(f"FAIL: {path}: {len(problems)} structural problem(s)")
        for p in problems[:25]:
            print(f"  - {p}")
        return 1

    print(f"OK: {path}")
    print(f"  parses cleanly · {kind} · {len(entries)} entries")
    if missing:
        # a stale path is a warning, not a hard failure: worktrees legitimately lag main and
        # would otherwise fail this gate for entirely unrelated reasons.
        print(f"  WARNING: {len(missing)} indexed path(s) not present in this checkout:")
        for m in missing[:10]:
            print(f"    - {m}")

    cov_map = settings.get("coverage", DEFAULT_COVERAGE)
    if kind == "sections":
        cov = _docs_coverage(repo, docs_rel, entries, data, verbose) if docs_coverage else []
    else:
        cov = _coverage(repo, kind, entries, cov_map)
        if not _cov_spec(cov_map, kind):
            print(f"  NOTE: no `validate.coverage.{kind}` mapping — parse-checked only, "
                  f"coverage NOT measured")
    for line in cov:
        print(f"  COVERAGE: {line}")
    return 0


def _listing_problems(repo: Path, entries: dict, settings: dict) -> list[str]:
    """Enum + vocabulary check on a skills manifest's `listing` / `category` values.

    The allowed sets come from the SAME declaration build_registry derives from (the repo's
    registry-map skills spec, via BR.policy_for_repo), so the generator and the validator cannot
    disagree about what is legal. `off` is legal in a manifest because a sidecar may set it.
    A repo whose map declares no listing policy gets no check — and no false finding.
    `settings["_listing_policy"]` injects a policy (self-check only).
    """
    pol = settings.get("_listing_policy") or BR.policy_for_repo(repo)
    if not pol:
        return []
    legal = set(pol["values"]) | set(BR.SIDECAR_ONLY_LISTING)
    out = []
    for name, meta in entries.items():
        if not isinstance(meta, dict):
            continue
        if "listing" in meta and BR._norm_listing(meta["listing"]) not in legal:
            out.append(f"{name}: listing {meta['listing']!r} not in {sorted(legal)}")
        cat = meta.get("category")
        if cat is not None and pol["vocabulary"] is not None and cat not in pol["vocabulary"]:
            out.append(f"{name}: category {cat!r} not in the vocabulary")
    return out


def listing_census(repo: Path) -> tuple[list[str], list[str]]:
    """(listing_missing, category_invalid) across the files the skills spec indexes — measured
    from the FILES through BR.resolve_listing, not read back from a manifest that may lag them."""
    cfg_path = repo / "config" / "registry-map.yaml"
    try:
        spec = ((yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {})
                .get("registries") or {}).get("skills")
    except (OSError, yaml.YAMLError):
        return [], []
    pol = BR.load_listing_policy(repo, spec) if spec else None
    if not pol:
        return [], []
    missing, invalid = [], []
    found, _ = BR.discover(repo, spec)
    for eid, p in sorted(found.items()):
        r = BR.resolve_listing(eid, read_frontmatter(p), BR.provenance(repo, p), pol,
                               str(p.relative_to(repo)))
        for bucket, msg in r["problems"]:
            if bucket == "listing_missing":
                missing.append(eid)
            elif bucket in ("category_invalid", "listing_invalid"):
                invalid.append(msg)
    return missing, invalid


def frontmatter_census(repo: Path, registry_dir: Path, verbose: bool = False,
                       settings: dict | None = None) -> int:
    """Which agent-consumable documents carry frontmatter and a `summary:`.

    Honours every manifest's declared exclusions, so a GENERATED tree is reported as
    excluded-with-a-reason rather than counted as a gap. Every file lands in exactly one of three
    buckets and `unclassified` is impossible by construction.

    Exclusions come from EVERY manifest, because each kind owns its own tree: the docs manifest
    declares generated docs output, the data manifest declares derived data output. One list in
    one file would put data rules in the docs manifest — the split-ownership shape that lets two
    copies drift.
    """
    excl = []
    for man in sorted(registry_dir.glob("*.yaml")) if registry_dir.is_dir() else []:
        try:
            excl += _declared_exclusions(yaml.safe_load(man.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError:
            print(f"WARNING: {man.name} did not parse; its exclusions are NOT in force")

    # `validate.census_exclude` — the home for trees NO manifest owns. `backlog/` and `runtime/`
    # are not indexed by any kind, so an `excluded:` block inside skills.yaml or context.yaml
    # would be a rule filed under an owner that has nothing to do with it, which is how an
    # exclusion ends up invisible to whoever next asks why a tree is not measured.
    # ⚑ Every entry MUST carry a reason. An exclusion is a deletion decision — it removes a tree
    # from the gate permanently — so the report prints the reason next to the count and a bare
    # path is refused rather than accepted quietly.
    for e in ((settings or {}).get("census_exclude") or []):
        if isinstance(e, dict) and e.get("path") and e.get("reason"):
            excl.append((str(e["path"]).rstrip("/"), e["reason"]))
        else:
            print(f"WARNING: census_exclude entry ignored — needs both `path:` and `reason:`: {e}")

    everything = _md_under(repo)
    excluded, exempt, ok = [], [], 0
    buckets: dict[str, list] = {"absent": [], "no-summary": [], "malformed": []}
    for rel in sorted(everything):
        if is_excluded(rel, excl):
            excluded.append(rel)
            continue
        # Per-repo declarations first, then the workspace-wide convention. A file excused by the
        # convention is NOT a gap: it is a file the convention says needs no `summary:`.
        why = convention_exempt(repo, rel)
        if why:
            exempt.append((rel, why))
            continue
        verdict, detail = classify(repo / rel)
        if verdict == "ok":
            ok += 1
        else:
            buckets[verdict].append((rel, detail))

    gap = [r for b in buckets.values() for r, _ in b]
    print("FRONTMATTER CENSUS")
    print(f"  {len(everything):>6}  markdown files (excluding {', '.join(SKIP_DIRS)})")
    print(f"  {len(excluded):>6}  excluded by a DECLARED rule in registry/*.yaml")
    ex_by_rule = Counter(r for _, r in exempt)
    print(f"  {len(exempt):>6}  EXEMPT by progressive-disclosure-convention.md")
    for rule, n in sorted(ex_by_rule.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:>6}    · {rule}")
    print(f"  {ok:>6}  carry frontmatter AND a summary:")
    print(f"  {len(gap):>6}  GAP  "
          f"({len(buckets['absent'])} no frontmatter · "
          f"{len(buckets['no-summary'])} no summary: · "
          f"{len(buckets['malformed'])} MALFORMED, will not parse)")
    # Skills with no `listing:` — a separate count, deliberately NOT folded into GAP: a file can
    # carry perfect frontmatter and still leave the harness guessing what the model should see.
    # The nightly parses the GAP line by regex; this line is shaped so it cannot match it.
    lmiss, linvalid = listing_census(repo)
    print(f"  {len(lmiss):>6}  skills with no `listing:` (listing_missing)"
          + (f" · {len(linvalid)} listing/category INVALID" if linvalid else ""))
    if excl:
        print("\n  declared exclusions:")
        for p, r in excl:
            n = sum(1 for e in excluded if is_excluded(e, [(p, "")]))
            print(f"    {n:>5}  {p}\n           {str(r)[:100]}")
    if buckets["malformed"]:
        # named individually: this is the bucket whose members LOOK compliant to a reader and are
        # invisible to every yaml.safe_load consumer, so a by-directory count would under-sell it
        print("\n  ⚑ MALFORMED frontmatter — present, and no parser can read it:")
        for rel, detail in buckets["malformed"][:25 if not verbose else 10_000]:
            print(f"    - {rel}\n        {detail}")
        if not verbose and len(buckets["malformed"]) > 25:
            print(f"    … and {len(buckets['malformed']) - 25} more (--verbose for all)")
    if gap:
        by_dir = Counter(os.path.dirname(f) or "." for f in gap)
        print("\n  gap by directory:")
        for d, n in _ranked(by_dir, 20 if not verbose else 10_000):
            print(f"    {n:>5}  {d}")
    if lmiss or linvalid:
        print("\n  listing_missing (set `listing:` in the SKILL.md, or a sidecar for files we "
              "cannot edit):")
        for n in lmiss[: 20 if not verbose else 10_000]:
            print(f"    - {n}")
        if not verbose and len(lmiss) > 20:
            print(f"    … and {len(lmiss) - 20} more (--verbose for all)")
        for m in linvalid[:25]:
            print(f"    ⚑ {m}")
    return 1 if (gap or lmiss or linvalid) else 0


# ---------------------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate registry manifests.")
    ap.add_argument("paths", nargs="*", help="specific manifests; default: every registry/*.yaml")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--config", default=None, help="registry-map.yaml carrying a `validate:` block")
    ap.add_argument("--docs-coverage", action="store_true")
    ap.add_argument("--frontmatter", action="store_true", help="run the frontmatter census")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()

    repo = Path(a.repo).resolve()
    registry_dir = repo / "registry"
    settings = load_settings(repo, a.config)

    if a.frontmatter:
        return frontmatter_census(repo, registry_dir, a.verbose, settings)

    if a.paths:
        paths = [Path(p) for p in a.paths]
    elif registry_dir.is_dir():
        paths = sorted(registry_dir.glob("*.yaml"))
    else:
        print(f"FAIL: no registry manifests found under {registry_dir}")
        return 1

    rc = 0
    for p in paths:
        rc |= validate_one(repo, p, settings, a.docs_coverage, a.verbose)
    return rc


def self_check() -> int:
    """Two-sided: a sound manifest passes, and each defect class MUST fail."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / "registry").mkdir()
        (repo / "skills" / "alpha").mkdir(parents=True)
        (repo / "skills" / "beta").mkdir(parents=True)
        good = repo / "registry" / "skills.yaml"
        settings = {"coverage": {"skills": "skills"}}

        def write(entries: str) -> None:
            good.write_text("skills:\n" + entries)

        write("  alpha:\n    path: skills/alpha\n    summary: A.\n"
              "  beta:\n    path: skills/beta\n    summary: B.\n")
        if validate_one(repo, good, settings) != 0:
            print("FAIL: a sound manifest did not validate"); ok = False

        # the convention's Exempt Files list must be HONOURED — and must not swallow real gaps
        (repo / "skills" / "_external" / "vendor").mkdir(parents=True)
        (repo / "skills" / "_external" / "vendor" / "SKILL.md").write_text("x\n" * 40)
        (repo / "README.md").write_text("y\n" * 40)
        (repo / "stub.md").write_text("z\n" * 5)
        (repo / "skills" / "alpha" / "real.md").write_text("w\n" * 40)
        cases = {
            "skills/_external/vendor/SKILL.md": "third-party",
            "README.md": "README/CHANGELOG",
            "stub.md": "under 15",
            "skills/alpha/real.md": None,     # ⚑ the other side: a REAL gap must stay a gap
        }
        for rel, want in cases.items():
            got = convention_exempt(repo, rel)
            if want is None and got is not None:
                print(f"FAIL: {rel} was exempted but is a real gap ({got})"); ok = False
            if want is not None and (got is None or want not in got):
                print(f"FAIL: {rel} should be exempt for '{want}', got {got!r}"); ok = False
        # a deep README is NOT a project-root README — the convention says project roots
        (repo / "skills" / "alpha" / "README.md").write_text("q\n" * 40)
        if convention_exempt(repo, "skills/alpha/README.md") is not None:
            print("FAIL: a nested README was exempted as a project-root README"); ok = False

        # coverage must judge an entry by its DECLARED PATH, not by its key, and must honour
        # BOTH archive spellings. Reported by a peer session 2026-08-08 as two false positives
        # against a correct index; each assertion below fails if its half is removed.
        (repo / ".claude" / "skills" / "elsewhere").mkdir(parents=True)
        (repo / ".claude" / "skills" / "elsewhere" / "SKILL.md").write_text("x\n")
        cov = _coverage(repo, "skills", {
            "alpha": {"path": "skills/alpha"},
            "beta": {"path": "skills/beta"},
            "elsewhere": {"path": ".claude/skills/elsewhere/SKILL.md"},   # outside the root
            "old_true": {"path": "gone/a", "archived": True},             # legacy spelling
            "old_liveness": {"path": "gone/b", "liveness": "archived"},   # newer spelling
            "really_gone": {"path": "skills/nope"},                       # a REAL absence
        }, {"skills": "skills"})
        joined = " | ".join(cov)
        if "elsewhere" in joined:
            print(f"FAIL: an entry present at its declared path outside the root was reported "
                  f"missing: {joined}"); ok = False
        for k in ("old_true", "old_liveness"):
            if k in joined:
                print(f"FAIL: a declared archive ({k}) was reported as an absence"); ok = False
        if "really_gone" not in joined:
            print("FAIL: an entry whose declared path does NOT exist was not reported"); ok = False

        # The SECOND checker — the "indexed path(s) not present" pass inside validate_one — asked
        # the same two questions and answered both differently: it honoured NEITHER archive
        # spelling, and for `sources` it OVERRODE a declared `path:` with `<data-dir>/<key>`.
        # Exercised through validate_one, not the helper, because that is where it lives.
        import io as _io, contextlib as _cl
        (repo / "data" / "live").mkdir(parents=True)
        (repo / "elsewhere").mkdir()
        src = repo / "registry" / "data.yaml"
        src.write_text(
            "sources:\n"
            "  live: {summary: L.}\n"
            "  moved: {summary: M., liveness: archived, liveness_basis: 'moved 2026-08-06'}\n"
            "  offroot: {summary: O., path: elsewhere}\n"
            "  vanished: {summary: V.}\n")
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            validate_one(repo, src, {"coverage": {"sources": {"dir": "data"}}})
        rep = buf.getvalue()
        for k, why in (("moved", "a declared `liveness: archived` source"),
                       ("offroot", "a source present at its declared path outside the data dir")):
            if f"- {k}" in rep:
                print(f"FAIL: {why} was reported as missing\n{rep}"); ok = False
        if "- vanished" not in rep:
            print(f"FAIL: a genuinely missing source was NOT reported\n{rep}"); ok = False

        # census_exclude: a declared tree is excluded, and an entry with NO reason is REFUSED.
        # An exclusion is a deletion decision, so an unexplained one must not slip through quietly.
        import io, contextlib
        (repo / "backlog").mkdir()
        (repo / "backlog" / "item.md").write_text("no frontmatter\n" * 40)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            frontmatter_census(repo, repo / "registry", False,
                               {"census_exclude": [{"path": "backlog", "reason": "work tracking"},
                                                   {"path": "nowhere"}]})
        out = buf.getvalue()
        if "1  excluded by a DECLARED rule" not in out:
            print(f"FAIL: a declared census_exclude tree was still counted\n{out}"); ok = False
        if "census_exclude entry ignored" not in out:
            print("FAIL: an exclusion with no reason was accepted silently"); ok = False
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            frontmatter_census(repo, repo / "registry", False, {})
        if "1  excluded by a DECLARED rule" in buf.getvalue():
            print("FAIL: backlog was excluded with NO declaration — the rule is not doing it")
            ok = False

        # listing / category enum + vocabulary (2026-10-16): legal values pass — including `off`,
        # which a sidecar may set — and each illegal one MUST fail
        pol = {"values": ("on", "name-only", "user-only"), "vocabulary": {"writing"}}
        lset = dict(settings, _listing_policy=pol)
        write("  alpha:\n    path: skills/alpha\n    summary: A.\n    listing: user-only\n"
              "    category: writing\n"
              "  beta:\n    path: skills/beta\n    summary: B.\n    listing: 'off'\n")
        with contextlib.redirect_stdout(io.StringIO()):
            if validate_one(repo, good, lset) != 0:
                print("FAIL: legal listing/category values were rejected"); ok = False
        for bad, why in (("    listing: loud\n", "an unknown listing"),
                         ("    category: nonsense\n", "a category outside the vocabulary")):
            write("  alpha:\n    path: skills/alpha\n    summary: A.\n" + bad +
                  "  beta:\n    path: skills/beta\n    summary: B.\n")
            with contextlib.redirect_stdout(io.StringIO()):
                if validate_one(repo, good, lset) == 0:
                    print(f"FAIL: {why} passed validation"); ok = False

        # census: a SKILL.md with no `listing:` is counted, one with it is not
        lrepo = repo / "lrepo"
        for n, body in (("has", "listing: on\n"), ("lacks", "")):
            (lrepo / "skills" / n).mkdir(parents=True)
            (lrepo / "skills" / n / "SKILL.md").write_text(f"---\nname: {n}\n{body}summary: S.\n---\n")
        (lrepo / "config").mkdir()
        (lrepo / "config" / "registry-map.yaml").write_text(yaml.safe_dump({"registries": {
            "skills": {"globs": ["skills/*/SKILL.md"], "derived": ["listing"],
                       "listing_defaults": {"local": "name-only"},
                       "listing_required": ["local"]}}}))
        miss, _inv = listing_census(lrepo)
        if miss != ["lacks"]:
            print(f"FAIL: listing census wrong — expected ['lacks'], got {miss}"); ok = False
        (lrepo / "skills" / "lacks" / "SKILL.md").write_text(
            "---\nname: lacks\nlisting: name-only\nsummary: S.\n---\n")
        if listing_census(lrepo)[0]:
            print("FAIL: listing census still counts a skill that now sets listing"); ok = False

        # unparseable YAML MUST fail
        good.write_text("skills:\n  alpha:\n    summary: 'the '837 wins' rule'\n")
        if validate_one(repo, good, settings) == 0:
            print("FAIL: a YAML parse error was not caught"); ok = False

        # a missing required field MUST fail
        write("  alpha:\n    path: skills/alpha\n")
        if validate_one(repo, good, settings) == 0:
            print("FAIL: a missing summary was not caught"); ok = False

        # present-but-unindexed MUST be reported (beta exists on disk, not in the manifest)
        write("  alpha:\n    path: skills/alpha\n    summary: A.\n")
        data = yaml.safe_load(good.read_text())
        cov = _coverage(repo, "skills", data["skills"], {"skills": "skills"})
        if not any("UNINDEXED" in c and "beta" in c for c in cov):
            print("FAIL: present-but-unindexed not reported"); ok = False

        # indexed-but-absent MUST be reported
        write("  alpha:\n    path: skills/alpha\n    summary: A.\n"
              "  beta:\n    path: skills/beta\n    summary: B.\n"
              "  ghost:\n    path: skills/ghost\n    summary: G.\n")
        data = yaml.safe_load(good.read_text())
        cov = _coverage(repo, "skills", data["skills"], {"skills": "skills"})
        if not any("INDEXED but not present" in c and "ghost" in c for c in cov):
            print("FAIL: indexed-but-absent not reported"); ok = False

        # a DECLARED archive is a statement, not an absence — it must NOT be reported
        write("  alpha:\n    path: skills/alpha\n    summary: A.\n"
              "  beta:\n    path: skills/beta\n    summary: B.\n"
              "  retired:\n    path: archive/retired\n    summary: R.\n    archived: true\n")
        data = yaml.safe_load(good.read_text())
        cov = _coverage(repo, "skills", data["skills"], {"skills": "skills"})
        if any("retired" in c for c in cov):
            print("FAIL: a declared archive was reported as missing"); ok = False

        # an unmapped kind must SAY it measured nothing rather than print a green line
        if _coverage(repo, "skills", data["skills"], {}) != []:
            print("FAIL: an unmapped coverage kind produced findings"); ok = False

        # exclusion globs must keep covering new siblings
        excl = [("data/snap/*/catalog", "generated")]
        if not is_excluded("data/snap/260808/catalog/x.md", excl):
            print("FAIL: exclusion glob did not cover a new sibling"); ok = False
        if is_excluded("data/snap/260808/real.md", excl):
            print("FAIL: exclusion glob over-matched"); ok = False
    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
