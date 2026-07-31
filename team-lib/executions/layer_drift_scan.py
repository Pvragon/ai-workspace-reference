#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Deterministic drift detector between the personal layer (my-lib) and the shared layer
#   (team-lib). Compares CONTENT HASHES of the file bodies, not version numbers — because the
#   2026-07-30 audit found three shared skills carrying IDENTICAL versions with different content,
#   so metadata cannot reveal the drift. Walks registry/mirror.yaml (explicit cross-named pairs +
#   same-path trees), reports silent-drift / known-drift / ungraduated / shared-only / registry
#   dangling entries, portability defects (a shared copy that depends on the personal layer), and
#   honours two-sided `mirror: divergent` declarations. Drift findings name WHICH SIDE is missing
#   sections, because the failure that motivated this was directional, not symmetric. Read-only by design:
#   detection is deterministic and belongs in the nightly tick; RESOLUTION is reasoning and stays
#   task-triggered."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""layer_drift_scan.py — is the shared layer actually current with the personal layer?

The failure this catches
------------------------
A capability is developed in `my-lib`, copied to `team-lib`, and then only the
`my-lib` copy keeps getting fixed. Both copies stay individually valid; only the
*comparison* is wrong, and nothing compares them. A teammate installing from
`team-lib` gets the stale one. Measured 2026-07-30: 5/5 shared skills diverged,
3 of them at identical version numbers.

So this compares body hashes. Frontmatter is stripped before hashing (version and
last_updated churn is not drift), but a version *skew* is reported alongside, and
a drift where the two versions are EQUAL is escalated — that is the silent case
nobody can see by looking.

Declaring an intentional difference
-----------------------------------
Put `mirror: divergent` in the frontmatter of BOTH copies (plus a
`mirror_reason:`). One-sided declarations are rejected on purpose: an
undocumented intentional difference is indistinguishable from rot. Use
`mirror: local` on a personal-layer file that should never graduate.

Usage
-----
    python3 layer_drift_scan.py                 # human-readable report
    python3 layer_drift_scan.py --json          # machine-readable (cron/dream tick)
    python3 layer_drift_scan.py --severity high # only the findings that matter tonight
    python3 layer_drift_scan.py --strict        # exit 1 if any finding at/above --severity
    python3 layer_drift_scan.py --tree skills   # restrict to one manifest tree

Exit codes: 0 = clean (or non-strict), 1 = findings under --strict, 2 = scan error.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import workspace  # noqa: E402

#: Severity ordering, low → high. Used by --severity filtering.
SEVERITY = ["info", "low", "med", "high"]

#: Files worth hashing. Anything else (images, binaries, lockfiles) is compared
#: by raw bytes rather than by stripped body.
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".toml"}

#: Inside a skill directory, this is the file whose frontmatter speaks for the skill.
PRIMARY_NAMES = ("SKILL.md", "index.md", "README.md")


# --------------------------------------------------------------------------
# frontmatter + hashing
# --------------------------------------------------------------------------

_YAML_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_PY_FM = re.compile(r"\A(#![^\n]*\n)?# ---\r?\n(.*?)^# ---\r?\n", re.DOTALL | re.MULTILINE)


def _split_frontmatter(text: str, suffix: str) -> tuple[dict, str]:
    """Return (metadata, body). Frontmatter is stripped so version/date churn
    never registers as content drift."""
    meta: dict = {}
    body = text

    if suffix == ".py":
        m = _PY_FM.match(text)
        if m:
            raw = "\n".join(
                line[2:] if line.startswith("# ") else line.lstrip("#")
                for line in m.group(2).splitlines()
            )
            body = text[m.end():]
            meta = _safe_yaml(raw)
    else:
        m = _YAML_FM.match(text)
        if m:
            body = text[m.end():]
            meta = _safe_yaml(m.group(1))

    return meta, body


def _safe_yaml(raw: str) -> dict:
    try:
        data = yaml.safe_load(raw)
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def _normalize(body: str) -> str:
    """Trailing whitespace and end-of-file blank lines are not drift."""
    return "\n".join(line.rstrip() for line in body.splitlines()).rstrip() + "\n"


def _read(path: Path) -> tuple[dict, str]:
    """(metadata, body-hash) for one file. Binary files hash their raw bytes."""
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return {}, hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return {}, hashlib.sha256(path.read_bytes()).hexdigest()
    meta, body = _split_frontmatter(text, path.suffix.lower())
    return meta, hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# walking
# --------------------------------------------------------------------------

def _excluded(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def _walk(root: Path, excludes: list[str]) -> dict[str, Path]:
    """Relative-posix-path -> absolute path, for every file under root."""
    if not root.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if _excluded(rel, excludes):
            continue
        out[rel] = p
    return out


def _group_key(rel: str, unit: str) -> str:
    """A finding is reported per skill-directory or per file, depending on unit."""
    return rel.split("/", 1)[0] if unit == "dir" else rel


def _primary(files: dict[str, tuple[dict, str]], group: str, unit: str) -> str | None:
    """Which file's frontmatter speaks for this group."""
    if unit == "file":
        return group if group in files else None
    members = sorted(r for r in files if r.split("/", 1)[0] == group)
    if not members:
        return None
    for name in PRIMARY_NAMES:
        for rel in members:
            if rel.split("/")[-1] == name:
                return rel
    return members[0]


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------

def _finding(kind, severity, tree, item, **extra) -> dict:
    f = {"kind": kind, "severity": severity, "tree": tree, "item": item}
    f.update(extra)
    return f


def _declared(meta: dict) -> str | None:
    """The `mirror:` declaration on a file, if any."""
    val = meta.get("mirror")
    return str(val).strip().lower() if val else None


# --- derived pairs -------------------------------------------------------
# Some shared-layer files are a GENERALIZATION of a personal-layer file, not a
# copy of it: the team AGENTS.md template is my-lib/AGENTS.md with the agent
# name, the operator's name, and specific repo/host policies stripped out. Body
# equality is impossible there by design, so demanding it would either produce a
# permanent false positive or push personal specifics into the shared layer.
#
# What IS checkable is structural currency: the derived file must carry the same
# SECTIONS. That catches "the template is six operating principles behind"
# without ever asking the two files to be identical.

_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_NUMBERED = re.compile(r"^\*\*(\d+)\.\s*(.+?)\*\*\s*$")


def _outline(text: str, suffix: str) -> list[str]:
    """Normalized section titles, in document order."""
    _, body = _split_frontmatter(text, suffix)
    out: list[str] = []
    for line in body.splitlines():
        m = _HEADER.match(line)
        if m:
            out.append(_norm_title(m.group(2)))
            continue
        m = _NUMBERED.match(line)
        if m:
            out.append(_norm_title(m.group(2)))
    return out


def _norm_title(raw: str) -> str:
    t = raw.replace("*", "").replace("`", "")
    t = re.sub(r"^\s*\d+\.\s*", "", t)          # leading "3. "
    t = re.sub(r"[^\w\s()&/,'—-]", "", t)       # emoji and decoration
    return re.sub(r"\s+", " ", t).strip().lower()


def _compare_group(tree_id, group, unit, p_files, s_files, p_meta, s_meta) -> dict | None:
    """One personal/shared group that exists on BOTH sides."""
    p_rels = {r for r in p_files if _group_key(r, unit) == group}
    s_rels = {r for r in s_files if _group_key(r, unit) == group}

    differing = sorted(
        r for r in (p_rels & s_rels) if p_files[r][1] != s_files[r][1]
    )
    only_personal = sorted(p_rels - s_rels)
    only_shared = sorted(s_rels - p_rels)

    if not (differing or only_personal or only_shared):
        return None

    p_ver = str(p_meta.get("version", "")) or None
    s_ver = str(s_meta.get("version", "")) or None

    # Two-sided declaration is the ONLY way to accept a difference.
    p_decl, s_decl = _declared(p_meta), _declared(s_meta)
    if p_decl == "divergent" and s_decl == "divergent":
        return _finding(
            "declared-divergent", "info", tree_id, group,
            personal_version=p_ver, shared_version=s_ver,
            files_differing=differing, only_personal=only_personal,
            only_shared=only_shared,
            reason=str(p_meta.get("mirror_reason", "") or s_meta.get("mirror_reason", "")),
        )

    one_sided = (p_decl == "divergent") ^ (s_decl == "divergent")

    # The trap: content differs but the versions are identical, so nothing about
    # the metadata looks wrong and no human would ever notice.
    silent = (p_ver == s_ver)
    kind = "silent-drift" if silent else "known-drift"
    severity = "high" if silent else "med"

    # "These differ" is the wrong headline. The failure that motivated this
    # scanner was DIRECTIONAL: team-lib's session-debrief was missing the memory
    # groom and index rerank outright, so a teammate installing from the shared
    # layer captured memories that never got an index row. Symmetric wording
    # buries that. Name which side lacks capability, so the report self-announces.
    missing_in_shared, missing_in_personal = _section_gap(p_files, s_files, differing)

    return _finding(
        kind, severity, tree_id, group,
        personal_version=p_ver, shared_version=s_ver,
        files_differing=differing, only_personal=only_personal,
        only_shared=only_shared,
        missing_in_shared=missing_in_shared,
        missing_in_personal=missing_in_personal,
        one_sided_declaration=one_sided,
    )


def _section_gap(p_files, s_files, differing) -> tuple[list[str], list[str]]:
    """Which whole sections does each side lack? Markdown only.

    A body-hash says "different". This says "the copy teammates install is
    missing these five steps", which is the thing worth waking up for.
    """
    missing_shared: list[str] = []
    missing_personal: list[str] = []
    for rel in differing:
        if not rel.endswith(".md"):
            continue
        p_path, s_path = p_files[rel][2], s_files[rel][2]
        try:
            p_out = _outline(p_path.read_text(encoding="utf-8"), ".md")
            s_out = _outline(s_path.read_text(encoding="utf-8"), ".md")
        except (OSError, UnicodeDecodeError):
            continue
        s_set, p_set = set(s_out), set(p_out)
        missing_shared += [t for t in p_out if t not in s_set]
        missing_personal += [t for t in s_out if t not in p_set]
    return missing_shared, missing_personal


def _scan_tree(tree: dict, personal_root: Path, shared_root: Path) -> list[dict]:
    tree_id = tree.get("id") or tree.get("personal")
    unit = tree.get("unit", "file")
    policy = tree.get("policy", "mirror")
    excludes = list(tree.get("exclude") or []) + list(tree.get("_always") or [])

    p_root = personal_root / tree["personal"]
    s_root = shared_root / tree["shared"]

    p_paths = _walk(p_root, excludes)
    s_paths = _walk(s_root, excludes)

    if policy == "integrity":
        return _registry_integrity(tree_id, p_root, personal_root, "personal") + \
               _registry_integrity(tree_id, s_root, shared_root, "shared")

    # (metadata, body-hash, path) — the path is kept so a drift finding can say
    # WHICH SIDE is missing sections, not merely that the two differ.
    p_files = {rel: (*_read(p), p) for rel, p in p_paths.items()}
    s_files = {rel: (*_read(p), p) for rel, p in s_paths.items()}

    p_groups = {_group_key(r, unit) for r in p_files}
    s_groups = {_group_key(r, unit) for r in s_files}

    findings: list[dict] = []

    for group in sorted(p_groups & s_groups):
        p_prim = _primary(p_files, group, unit)
        s_prim = _primary(s_files, group, unit)
        p_meta = p_files[p_prim][0] if p_prim else {}
        s_meta = s_files[s_prim][0] if s_prim else {}
        f = _compare_group(tree_id, group, unit, p_files, s_files, p_meta, s_meta)
        if f:
            findings.append(f)

    for group in sorted(p_groups - s_groups):
        prim = _primary(p_files, group, unit)
        meta = p_files[prim][0] if prim else {}
        if _declared(meta) == "local":
            continue
        findings.append(_finding(
            "ungraduated", "low", tree_id, group,
            personal_version=str(meta.get("version", "")) or None,
            hint="present only in the personal layer; graduate it or declare `mirror: local`",
        ))

    for group in sorted(s_groups - p_groups):
        findings.append(_finding(
            "shared-only", "info", tree_id, group,
            hint="exists in the shared layer but not the personal one",
        ))

    return findings


def _registry_integrity(tree_id: str, reg_dir: Path, layer_root: Path, side: str) -> list[dict]:
    """Every `path:` in a registry must resolve to something on disk.

    The registries were healthy on 2026-07-30 (0 dangling entries). This check
    exists to keep them that way, not because they are broken.
    """
    findings: list[dict] = []
    if not reg_dir.is_dir():
        return findings

    for reg in sorted(reg_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(reg.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            findings.append(_finding(
                "registry-unreadable", "high", tree_id, f"{side}:{reg.name}",
                error=str(exc)[:200],
            ))
            continue

        dangling = [
            p for p in sorted(set(_collect_paths(data)))
            if not _resolves(p, layer_root)
        ]
        if dangling:
            findings.append(_finding(
                "registry-dangling", "high", tree_id, f"{side}:{reg.name}",
                missing=dangling[:25], missing_count=len(dangling),
            ))
    return findings


#: A `dependencies:` entry is free-form — it holds both tool names ("python3",
#: "git") and file paths. Only the ones that LOOK like paths are asserted.
_LOOKS_LIKE_PATH = re.compile(r"^[.\w/-]+/[\w.-]+\.(py|sh|md|yaml|yml|json|mjs|js)$")


def _collect_paths(node) -> list[str]:
    """Every string under a `path` key, plus path-shaped `dependencies` entries.

    Dependencies matter: when the seven session-tooling scripts graduated on
    2026-07-30, three skills kept pointing `dependencies:` at my-lib paths that
    no longer existed. A `path`-only check called that registry clean.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "path" and isinstance(v, str) and v.strip():
                found.append(v.strip())
            elif k == "dependencies" and isinstance(v, list):
                found.extend(d.strip() for d in v
                             if isinstance(d, str) and _LOOKS_LIKE_PATH.match(d.strip()))
            else:
                found.extend(_collect_paths(v))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_paths(item))
    return found


def _resolves(rel: str, layer_root: Path) -> bool:
    if rel.startswith(("http://", "https://")) or "*" in rel:
        return True  # URLs and globs are not disk assertions
    cleaned = rel.lstrip("./")
    for base in (layer_root, layer_root.parent):
        if (base / cleaned).exists():
            return True
    return False


def _scan_pairs(pairs: list[dict], personal_root: Path, shared_root: Path) -> list[dict]:
    """Explicit cross-named pairs — the ones no name-matcher could find."""
    findings: list[dict] = []
    for pair in pairs:
        p_path = personal_root / pair["personal"]
        s_path = shared_root / pair["shared"]
        item = f"{pair['personal']} -> {pair['shared']}"

        if not p_path.is_file():
            findings.append(_finding("pair-missing", "med", "pairs", item, side="personal"))
            continue
        if not s_path.is_file():
            findings.append(_finding(
                "pair-missing", "high", "pairs", item, side="shared",
                hint="the shared layer is missing a capability it is declared to mirror",
            ))
            continue

        p_meta, p_hash = _read(p_path)
        s_meta, s_hash = _read(s_path)

        p_ver = str(p_meta.get("version", "")) or None
        s_ver = str(s_meta.get("version", "")) or None

        # A derived file is a generalization, never a copy — compare structure.
        if pair.get("policy") == "derived":
            p_out = _outline(p_path.read_text(encoding="utf-8"), p_path.suffix.lower())
            s_out = _outline(s_path.read_text(encoding="utf-8"), s_path.suffix.lower())
            missing = [t for t in p_out if t not in set(s_out)]
            extra = [t for t in s_out if t not in set(p_out)]
            if missing or extra:
                findings.append(_finding(
                    "derived-behind" if missing else "derived-extra",
                    "high" if missing else "low", "pairs", item,
                    personal_version=p_ver, shared_version=s_ver,
                    missing_sections=missing, extra_sections=extra,
                    hint="the shared copy is a generalization; port the SUBSTANCE of "
                         "these sections, do not copy personal specifics across",
                ))
            continue

        if p_hash == s_hash:
            continue

        if _declared(p_meta) == "divergent" and _declared(s_meta) == "divergent":
            findings.append(_finding(
                "declared-divergent", "info", "pairs", item,
                personal_version=p_ver, shared_version=s_ver,
                reason=str(p_meta.get("mirror_reason", "")),
            ))
            continue

        silent = (p_ver == s_ver)
        findings.append(_finding(
            "silent-drift" if silent else "known-drift",
            "high" if silent else "med", "pairs", item,
            personal_version=p_ver, shared_version=s_ver,
            files_differing=[pair["shared"]],
            one_sided_declaration=(_declared(p_meta) == "divergent") ^ (_declared(s_meta) == "divergent"),
        ))
    return findings


def _portability(spec: dict, shared_root: Path) -> list[dict]:
    """The shared layer must be standalone.

    A same-name content diff cannot see this defect class: a team-lib file that
    shells out to `~/ai-workspace/my-lib/...` has nothing to compare against, and
    is simply broken for everyone who is not this operator.
    """
    if not spec:
        return []

    excludes = list(spec.get("exclude") or [])
    allow = spec.get("allow") or []
    compiled = {name: re.compile(pat) for name, pat in (spec.get("patterns") or {}).items()}

    def allowed(rel: str) -> bool:
        return any(fnmatch.fnmatch(rel, entry["path"]) for entry in allow)

    # Exemptions are tracked, not silent. A lint can reach "zero findings" purely
    # by widening its allowlist, so the exemption count is reported next to the
    # finding count and a reader can judge whether the clean result was earned.
    exempted: list[str] = []

    findings: list[dict] = []
    for tree_name in spec.get("scan") or []:
        root = shared_root / tree_name
        for rel, path in sorted(_walk(root, excludes).items()):
            full_rel = f"{tree_name}/{rel}"
            if allowed(full_rel):
                exempted.append(full_rel)
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            hits: dict[str, list[str]] = {}
            for name, rx in compiled.items():
                for i, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        hits.setdefault(name, []).append(f"{i}: {line.strip()[:100]}")
            if not hits:
                continue

            # A script BREAKS; a doc merely misleads the reader.
            executable = path.suffix.lower() in (".py", ".sh")
            findings.append(_finding(
                "not-standalone", "high" if executable else "med",
                "portability", full_rel,
                violations={k: v[:3] for k, v in hits.items()},
                violation_count=sum(len(v) for v in hits.values()),
                hint="team-lib must run without the personal layer; parameterize the "
                     "path, or add an allow entry with a reason if it is by design",
            ))
    _portability.exempted = exempted
    return findings


def _publication(spec: dict, shared_root: Path, public_root: Path) -> list[dict]:
    """team-lib -> public reference repo: what is stale, and what would leak.

    Two questions, one walk, because they are the same question asked at
    different gates. `stale-in-public` says the published reference no longer
    matches the system it documents. `LEAK` says a refresh would publish a client
    or operator identifier — and that one is a hard block, never a warning.

    The public repo is a curated SUBSET, so "present in team-lib, absent from
    public" is a candidate for review, not a defect. Only content already
    published, or content that would carry an identifier, raises severity.
    """
    if not spec or not public_root.is_dir():
        return []

    excludes = list(spec.get("exclude") or [])
    blocklist: list[tuple[str, str]] = [
        (group, term)
        for group, terms in (spec.get("scrub") or {}).items()
        for term in terms
    ]

    prefix = spec.get("public_prefix") or ""
    pub_base = public_root / prefix if prefix else public_root

    # Compare the GENERALIZED source against the published copy. Comparing the
    # raw source marks every generalized-but-unblocked file permanently stale —
    # e.g. anything containing the operator's first name, which is rewritten by
    # a generalization rule but is not itself a blocked term. 10 files read as
    # stale that way immediately after a clean publish.
    gen_rules = list(spec.get("generalize") or [])

    def _as_published(text: str) -> str:
        for rule in gen_rules:
            text = text.replace(rule["from"], rule["to"])
        return text

    findings: list[dict] = []
    for tree in spec.get("include") or []:
        s_files = _walk(shared_root / tree, excludes)
        p_files = _walk(pub_base / tree, excludes)

        for rel, s_path in sorted(s_files.items()):
            full = f"{tree}/{rel}"
            if s_path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = s_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Check what publishing would ACTUALLY produce. Testing the raw
            # source reports files as leak-blocking that the publisher would
            # generalize cleanly — e.g. a `maintainer:` field naming the agent.
            source_hits = _blocked(_as_published(text), blocklist)
            published = rel in p_files

            # The ONLY true leak is an identifier in the PUBLISHED copy. Testing
            # the team-lib source instead conflates "the source mentions a client"
            # with "we exposed a client", and cries wolf on the most severe class:
            # measured 2026-07-30, that mistake produced 10 false criticals against
            # public copies that had been correctly scrubbed by hand.
            if published:
                try:
                    pub_text = p_files[rel].read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                pub_hits = _blocked(pub_text, blocklist)
                if pub_hits:
                    findings.append(_finding(
                        "LEAK", "high", "publication", full,
                        identifiers=pub_hits[:8],
                        hint="this identifier is LIVE in the public repo — scrub and "
                             "decide whether the git history also needs rewriting",
                    ))
                elif source_hits:
                    # Published copy is clean while the source is not: that is the
                    # scrub working. A derived relationship, not drift — so content
                    # equality must never be asserted here.
                    findings.append(_finding(
                        "scrubbed", "info", "publication", full,
                        identifiers=source_hits[:6],
                        hint="published copy is correctly scrubbed; content will "
                             "never match the source, by design",
                    ))
                elif _norm_pub(_as_published(text)) != _norm_pub(pub_text):
                    findings.append(_finding(
                        "stale-in-public", "med", "publication", full,
                        hint="the published copy differs from what publishing this "
                             "source would produce — run publish_public_reference.py",
                    ))
                continue

            findings.append(_finding(
                "leak-blocks-publish" if source_hits else "unpublished",
                "med" if source_hits else "low",
                "publication", full,
                identifiers=source_hits[:8],
                hint="scrub or generalize before this can publish; if the file is "
                     "inherently client-specific, exclude it"
                if source_hits else
                "clean and publishable, but not in the public repo — publish it or "
                "record why it stays internal",
            ))
    return findings


def _split_capabilities(personal_root: Path, shared_root: Path) -> list[dict]:
    """A capability present in the shared layer must be COMPLETE there.

    A capability is a stem that can appear as several kinds: `findings.py` (an
    execution), `findings/` (a skill), `findings.md` (a directive). Graduating one
    kind without its siblings leaves the shared layer holding a fragment — on
    2026-07-31 team-lib shipped `findings.py`, its two clocks and its statusline
    segment, with no `/findings` skill to work the list. The store accumulated and
    nothing could drain it.

    File-level drift detection is blind to this: there is no pair to compare, so a
    half-graduated capability produces zero drift findings. This is the check for
    the shape that mistake actually has.

    Note the direction. The rule is NOT "every personal caller must graduate" — a
    personal skill driving a shared execution is perfectly legitimate. The rule is
    that whatever the shared layer already ships must be usable on its own.
    """
    SKIP_PREFIX = ("_", "ext-", ".")

    def kinds_by_stem(root: Path) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for p in (root / "executions").glob("*"):
            if p.is_file() and p.suffix in (".py", ".sh") and not p.name.startswith(SKIP_PREFIX):
                out.setdefault(p.stem, set()).add("execution")
        for p in (root / "skills").glob("*"):
            if p.is_dir() and not p.name.startswith(SKIP_PREFIX):
                out.setdefault(p.name, set()).add("skill")
        for p in (root / "directives").glob("*.md"):
            if p.stem != "index" and not p.name.startswith(SKIP_PREFIX):
                out.setdefault(p.stem, set()).add("directive")
        return out

    personal, shared = kinds_by_stem(personal_root), kinds_by_stem(shared_root)

    findings: list[dict] = []
    for stem in sorted(personal):
        if stem not in shared:
            continue                      # wholly ungraduated — a different finding
        missing = personal[stem] - shared[stem]
        if missing:
            findings.append(_finding(
                "split-capability", "high", "capability", stem,
                shared_has=sorted(shared[stem]), personal_only=sorted(missing),
                hint=f"team-lib ships the {'/'.join(sorted(shared[stem]))} but not the "
                     f"{'/'.join(sorted(missing))}; a teammate gets a fragment they "
                     f"cannot use. Graduate the missing piece or explain the split.",
            ))
    return findings


def _public_sweep(spec: dict, public_root: Path) -> list[dict]:
    """Scan the ENTIRE public repo for blocked identifiers, independent of the
    publication mapping.

    Defence in depth, and not redundant: the mapping-based check above can only
    be as complete as its `include:` list, and on 2026-07-30 it missed a live
    `Acme Health` reference in `integrations/apps-script/Code.gs` purely because
    `integrations` was not listed. What is exposed cannot be a function of what
    we remembered to map. This sweep answers the safety question directly —
    "does anything in the public repo name a client or the operator?" — and
    would still fire if the mapping were deleted entirely.
    """
    if not spec or not public_root.is_dir():
        return []
    blocklist = [(g, t) for g, ts in (spec.get("scrub") or {}).items() for t in ts]
    excludes = list(spec.get("exclude") or []) + [".git/*", "*/.git/*"]

    findings: list[dict] = []
    for rel, path in sorted(_walk(public_root, excludes).items()):
        if path.suffix.lower() not in TEXT_SUFFIXES and path.suffix.lower() != ".gs":
            continue
        try:
            hits = _blocked(path.read_text(encoding="utf-8"), blocklist)
        except (UnicodeDecodeError, OSError):
            continue
        if hits:
            findings.append(_finding(
                "LEAK", "high", "public-sweep", rel,
                identifiers=hits[:8],
                hint="LIVE in the public repo — scrub it, then decide whether the "
                     "git history needs rewriting too",
            ))
    return findings


def _norm_pub(text: str) -> str:
    """Whitespace-insensitive compare for published content."""
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip()


def _blocked(text: str, blocklist: list[tuple[str, str]]) -> list[str]:
    """Blocklist hits, case-insensitive. Deliberately dumb: a scrub gate that
    reasons about context is a scrub gate that eventually lets one through."""
    low = text.lower()
    return sorted({f"{g}:{term}" for g, term in blocklist if term.lower() in low})


def _metrics(spec: dict, personal_root: Path, shared_root: Path) -> dict:
    out: dict = {}
    ext = spec.get("external_mirror") or {}
    if ext:
        personal = len(list(personal_root.glob(ext["personal_glob"])))
        shared = len({
            p.parent for p in shared_root.glob(ext["shared_glob"])
        })
        out["external_mirror"] = {
            "personal": personal, "shared": shared, "lag": personal - shared,
        }
    return out


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------

def run(manifest: str | Path | None = None, tree: str | None = None,
        severity: str = "info") -> dict:
    """Scan both layers for drift.

    Args:
        manifest: Path to mirror.yaml. Defaults to `<this script>/../registry/mirror.yaml`.
        tree: Restrict the scan to one manifest tree id (or "pairs").
        severity: Minimum severity to include in `findings` — one of
            info / low / med / high.

    Returns:
        dict with keys:
          status   — "ok" or "error"
          findings — list of finding dicts (kind, severity, tree, item, ...)
          summary  — counts by kind and by severity
          metrics  — informational counters (e.g. external-mirror lag)
          layers   — resolved absolute roots for both layers
    """
    manifest_path = Path(manifest) if manifest else \
        Path(__file__).resolve().parent.parent / "registry" / "mirror.yaml"

    if not manifest_path.is_file():
        return {"status": "error", "error": f"manifest not found: {manifest_path}"}

    try:
        spec = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return {"status": "error", "error": f"manifest unparseable: {exc}"}

    ws = workspace()
    layers = spec.get("layers") or {}
    personal_root = ws / layers.get("personal", "my-lib")
    shared_root = ws / layers.get("shared", "team-lib")

    for label, root in (("personal", personal_root), ("shared", shared_root)):
        if not root.is_dir():
            return {"status": "error", "error": f"{label} layer not found: {root}"}

    findings: list[dict] = []
    if tree in (None, "pairs"):
        findings += _scan_pairs(spec.get("pairs") or [], personal_root, shared_root)

    always = list(spec.get("exclude_always") or [])
    for t in spec.get("trees") or []:
        if tree and t.get("id") != tree:
            continue
        findings += _scan_tree({**t, "_always": always}, personal_root, shared_root)

    portability_exempt: list[str] = []
    if tree in (None, "capability"):
        findings += _split_capabilities(personal_root, shared_root)

    if tree in (None, "portability"):
        findings += _portability(spec.get("portability") or {}, shared_root)
        portability_exempt = getattr(_portability, "exempted", [])

    if tree in (None, "publication"):
        pub_root = ws / layers.get("public", "") if layers.get("public") else None
        if pub_root:
            findings += _publication(spec.get("publication") or {}, shared_root, pub_root)
            findings += _public_sweep(spec.get("publication") or {}, pub_root)

    floor = SEVERITY.index(severity) if severity in SEVERITY else 0
    findings = [f for f in findings if SEVERITY.index(f["severity"]) >= floor]
    findings.sort(key=lambda f: (-SEVERITY.index(f["severity"]), f["tree"], f["item"]))

    by_kind: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

    # "shared-only" alone cannot tell a rule violation from a rule SUCCESS: after
    # a correct move-graduation the personal copy is archived, so the capability is
    # shared-only by design. The distinguishing signal is whether an archived
    # counterpart exists in the personal layer. Without that check the metric would
    # report every correct graduation as a violation.
    archived = {
        q.name for q in (personal_root / "archive").rglob("*")
        if q.is_file() or q.is_dir()
    } if (personal_root / "archive").is_dir() else set()

    born_shared = sorted(
        f"{f['tree']}/{f['item']}" for f in findings
        if f["kind"] == "shared-only" and f["tree"] in ("skills", "executions")
        and f["item"].split("/")[-1] not in archived
    )

    return {
        "status": "ok",
        "findings": findings,
        "born_in_shared": born_shared,
        "summary": {
            "total": len(findings),
            "actionable": sum(v for k, v in by_sev.items() if k in ("med", "high")),
            "by_kind": by_kind,
            "by_severity": by_sev,
        },
        "metrics": {
            **_metrics(spec.get("metrics") or {}, personal_root, shared_root),
            "portability_exemptions": len(portability_exempt),
            "born_in_shared": len(born_shared),
        },
        "exempted": portability_exempt,
        "layers": {"personal": str(personal_root), "shared": str(shared_root)},
    }


_LABEL = {
    "silent-drift": "SILENT DRIFT  (content differs; metadata shows nothing)",
    "known-drift": "drift         (versions differ)",
    "pair-missing": "MISSING       (declared mirror absent)",
    "derived-behind": "DERIVED BEHIND (shared copy is missing whole sections)",
    "derived-extra": "derived extra (shared copy has sections the source lost)",
    "split-capability": "SPLIT CAPABILITY (shared layer ships only part of it)",
    "LEAK": "LEAK — PUBLISHED (a client/operator identifier is already public)",
    "leak-blocks-publish": "leak blocks publish (identifier present; refresh is blocked)",
    "stale-in-public": "stale in public (published copy no longer matches team-lib)",
    "unpublished": "unpublished (clean and publishable, not in the public repo)",
    "not-standalone": "NOT STANDALONE (shared layer depends on the personal one)",
    "registry-dangling": "REGISTRY      (entry points at nothing)",
    "registry-unreadable": "REGISTRY      (unparseable)",
    "ungraduated": "personal-only (never graduated)",
    "shared-only": "shared-only",
    "declared-divergent": "declared divergent (accepted)",
}


def _render(result: dict) -> str:
    lines: list[str] = []
    s = result["summary"]
    lines.append(f"layer drift scan — {s['total']} finding(s), {s['actionable']} actionable")
    lines.append(f"  personal: {result['layers']['personal']}")
    lines.append(f"  shared:   {result['layers']['shared']}")

    ext = result.get("metrics", {}).get("external_mirror")
    if ext:
        lines.append(f"  external skills: {ext['personal']} personal / "
                     f"{ext['shared']} shared (lag {ext['lag']})")
    born = result.get("metrics", {}).get("born_in_shared")
    if born:
        lines.append(f"  born in the shared layer: {born} skill(s)/execution(s) with no "
                     f"archived personal-layer origin — principle 15 says capabilities are "
                     f"born project-local and graduate")
    exempt = result.get("metrics", {}).get("portability_exemptions")
    if exempt:
        lines.append(f"  portability exemptions in force: {exempt} "
                     f"(a clean result is only as good as this number)")
    lines.append("")

    if not result["findings"]:
        lines.append("  no drift at this severity — the layers agree.")
        return "\n".join(lines)

    current = None
    for f in result["findings"]:
        if f["kind"] != current:
            current = f["kind"]
            lines.append(f"{_LABEL.get(current, current)}")
        detail = ""
        if f.get("personal_version") or f.get("shared_version"):
            detail = f"  [my-lib {f.get('personal_version') or '-'} | " \
                     f"team-lib {f.get('shared_version') or '-'}]"
        lines.append(f"  {f['tree']}/{f['item']}{detail}")
        for sec in (f.get("missing_in_shared") or [])[:8]:
            lines.append(f"      !! team-lib is MISSING: {sec}")
        for sec in (f.get("missing_in_personal") or [])[:4]:
            lines.append(f"      .. my-lib is missing:   {sec}")
        for rel in (f.get("files_differing") or [])[:6]:
            lines.append(f"      ~ {rel}")
        for rel in (f.get("only_personal") or [])[:4]:
            lines.append(f"      + {rel}  (personal only)")
        for rel in (f.get("only_shared") or [])[:4]:
            lines.append(f"      - {rel}  (shared only)")
        if f.get("missing"):
            for rel in f["missing"][:6]:
                lines.append(f"      ? {rel}")
        for sec in (f.get("missing_sections") or [])[:12]:
            lines.append(f"      - MISSING section: {sec}")
        for sec in (f.get("extra_sections") or [])[:6]:
            lines.append(f"      + extra section:   {sec}")
        for kind, examples in (f.get("violations") or {}).items():
            lines.append(f"      [{kind}] x{len(examples)}")
            for ex in examples[:2]:
                lines.append(f"        {ex}")
        if f.get("shared_has"):
            lines.append(f"      team-lib has: {', '.join(f['shared_has'])}"
                         f"  |  MISSING: {', '.join(f['personal_only'])}")
        for ident in (f.get("identifiers") or [])[:6]:
            lines.append(f"      >> {ident}")
        if f.get("one_sided_declaration"):
            lines.append("      ! one-sided `mirror: divergent` — both copies must declare it")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect drift between the personal and shared layers.")
    ap.add_argument("--manifest", default=None, help="path to mirror.yaml")
    ap.add_argument("--tree", default=None, help="restrict to one manifest tree id")
    ap.add_argument("--severity", default="info", choices=SEVERITY,
                    help="minimum severity to report (default: info)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any finding is reported")
    args = ap.parse_args()

    result = run(manifest=args.manifest, tree=args.tree, severity=args.severity)

    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2) if args.json else _render(result))

    return 1 if (args.strict and result["summary"]["total"]) else 0


if __name__ == "__main__":
    sys.exit(main())
