#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.6
# summary: "Publishes team-lib to the public reference repo as a GENERALIZATION: copies every
#   included tree, drops what is proprietary, rewrites operator and client identifiers into
#   placeholders, and REFUSES to write any file that still contains a blocked term afterwards.
#   The refusal is the point — the public repo had been scrubbed by hand, which is exactly the
#   arrangement that cannot survive a routine refresh. Driven entirely by registry/mirror.yaml so
#   the contract and the tool cannot disagree. Dry-run by default."
# created: 2026-07-30
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""publish_public_reference.py — refresh the public reference repo from team-lib.

The goal of the public repo is that someone outside the company can point their
agent at it and say "build this", and end up with the same system. So it is
team-lib MINUS what is proprietary — not a curated subset, and not a fork that
drifts. Everything published should be current, and everything absent should be
absent on purpose.

Three transformations, in order:

1. **Exclude** — proprietary trees and files never leave (client brand content,
   incident write-ups naming affected repos, client-specific integrations, and
   mirror.yaml itself, which contains the blocklist and therefore every client
   name).
2. **Generalize** — the operator's identity becomes a placeholder the reader
   replaces with their own: the agent name, username, email, and client names
   used as incidental examples.
3. **Gate** — after generalizing, any file still containing a blocked term is
   REFUSED, and the run reports it rather than publishing it. A scrub that only
   runs when someone remembers is not a scrub.

Usage:
    publish_public_reference.py                 # dry run: what would change
    publish_public_reference.py --apply         # write it
    publish_public_reference.py --apply --prune # also delete published files
                                                # that no longer have a source
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import workspace  # noqa: E402

TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt",
                 ".toml", ".gs", ".js", ".mjs", ".cfg", ".ini"}


def _excluded(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def _generalize(text: str, rules: list[dict]) -> str:
    """Apply replacements in declared order, case-sensitively.

    Order matters and is the caller's responsibility: `you@example.com` has to
    be rewritten before a bare `you@` would swallow its prefix.
    """
    for rule in rules:
        text = text.replace(rule["from"], rule["to"])
    return text


def _filter_registry(text: str, published: set[str], shared: Path) -> tuple[str, int]:
    """Drop registry entries whose `path` is not among the published files.

    The registries ARE the agent's tool-resolution index — Operating Principle #1 has it
    scan them before doing anything. Publication filters files (client trees, the external
    packs, anything the scrub list blocks) but used to publish the indexes unchanged, so
    the public artifact advertised 36 capabilities whose files were deliberately withheld.
    An index that points at nothing is worse than a shorter index.

    Comments above the first key are kept verbatim — they are the schema documentation a
    reader needs. Entry-level comments do not survive; a generated index is the price of
    it being true.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return text, 0
    if not isinstance(data, dict):
        return text, 0

    dropped = 0

    def keep(node) -> bool:
        """Drop only what publication actually withheld.

        The predicate is deliberately narrow: the entry must name something that EXISTS
        in the shared layer and is absent from the published tree. Testing membership
        alone was wrong twice over — workspace.yaml's paths are workspace-relative
        (`personal`, `my-lib`), and several entries name directories rather than files,
        so a first cut deleted the layer descriptions and every directory entry. Anything
        this publisher does not own — a foreign path shape, an entry already dangling at
        the source — is left exactly as written and stays someone else's finding.
        """
        p = node.get("path") if isinstance(node, dict) else None
        if not isinstance(p, str) or not p:
            return True
        rel = p.strip().strip("/")
        if not rel or not (shared / rel).exists():
            return True
        return rel in published

    def walk(node):
        nonlocal dropped
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if isinstance(value, dict) and not keep(value):
                    del node[key]
                    dropped += 1
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in list(node):
                if isinstance(item, dict) and not keep(item):
                    node.remove(item)
                    dropped += 1
                else:
                    walk(item)

    walk(data)
    if not dropped:
        return text, 0

    header = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            header.append(line)
        else:
            break
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    return "\n".join(header + [body.rstrip(), ""]), dropped


def published_rel_paths(pub: dict, shared: Path) -> set[str]:
    """Every team-lib-relative path publication would emit, plus their ancestor dirs.

    Public because layer_drift_scan needs the identical set to predict what publishing
    would produce. Two copies of this rule would drift, and the thing they would disagree
    about is precisely whether a registry entry survives.
    """
    excludes = list(pub.get("exclude") or [])
    names: set[str] = set()
    for name in pub.get("include_files") or []:
        if (shared / name).is_file():
            names.add(name)
    for tree in pub.get("include") or []:
        root = shared / tree
        if not root.is_dir():
            continue
        for src in root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(root).as_posix()
            if _excluded(rel, excludes):
                continue
            names.add(f"{tree}/{rel}")
    out = set(names)
    for name in names:
        parts = name.split("/")
        for i in range(1, len(parts)):
            out.add("/".join(parts[:i]))
    return out


def is_registry(name: str) -> bool:
    return name.startswith("registry/") and name.endswith((".yaml", ".yml"))


def _blocked(text: str, blocklist: list[tuple[str, str]]) -> list[str]:
    low = text.lower()
    return sorted({f"{g}:{t}" for g, t in blocklist if t.lower() in low})


def run(apply: bool = False, prune: bool = False, manifest: str | None = None,
        force: bool = False) -> dict:
    """Publish team-lib into the public reference repo.

    Args:
        apply: Write changes. Default False (dry run).
        prune: Delete published files whose source no longer exists.
        force: Publish even if the shared layer is not on main.
        manifest: Path to mirror.yaml; defaults to ../registry/mirror.yaml.

    Returns:
        dict with status, and lists: written, unchanged, refused, pruned, skipped_binary.
    """
    mpath = Path(manifest) if manifest else \
        Path(__file__).resolve().parent.parent / "registry" / "mirror.yaml"
    if not mpath.is_file():
        # In the PUBLIC reference distribution this file is withheld on purpose — it holds
        # the scrub blocklist, so it names every client. Tools that need it therefore cannot
        # run there, and "manifest not found: <path>" reads like a broken install rather than
        # a deliberate omission. Say which it is.
        hint = ""
        if not (mpath.parent.parent / "registry" / "mirror.yaml").is_file():
            hint = (" — this tool is not available in the public reference distribution: "
                    "registry/mirror.yaml holds the scrub blocklist and is withheld by design, "
                    "so publication tooling cannot run from a public clone. Nothing is broken.")
        return {"status": "error", "error": f"manifest not found: {mpath}{hint}"}

    spec = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
    pub = spec.get("publication") or {}
    layers = spec.get("layers") or {}
    ws = workspace()

    shared = ws / layers.get("shared", "team-lib")
    public = ws / layers.get("public", "")

    # The public repo is generated from whatever is CHECKED OUT, and the shared tree is
    # shared: a peer can leave team-lib on a feature branch, and did — measured 2026-08-01,
    # team-lib sat on `fix/waystar-creds-canonical-location` with six unpushed commits while
    # the publish gate was armed. Publishing then would ship an unreviewed branch to the
    # world, and nothing in this tool or the gate would have noticed. Refuse instead.
    if not force:
        import subprocess
        try:
            br = subprocess.run(["git", "-C", str(shared), "branch", "--show-current"],
                                capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:                                   # noqa: BLE001
            br = ""
        # `br == ""` means UNDETERMINED (detached HEAD — every CI checkout — or a non-git
        # source tree), and the first cut treated that as permission. That is the precise
        # failure this guard was written to prevent, reproduced inside the guard itself:
        # a probe that cannot answer must not return the permissive value.
        if br != "main":
            undetermined = not br
            where = "an UNDETERMINED branch (detached HEAD, or not a git tree)" if undetermined \
                else f"branch '{br}', not main"
            return {"status": "error",
                    "error": f"team-lib is on {where} — refusing to publish. Switch team-lib to "
                             f"main, or pass --force if you truly mean to publish this state."}
    if not public or not public.is_dir():
        return {"status": "error", "error": f"public layer not found: {public}"}

    prefix = pub.get("public_prefix") or ""
    base = public / prefix if prefix else public

    excludes = list(pub.get("exclude") or [])
    rules = list(pub.get("generalize") or [])
    blocklist = [(g, t) for g, ts in (pub.get("scrub") or {}).items() for t in ts]

    written, unchanged, refused, skipped, pruned = [], [], [], [], []
    expected: set[Path] = set()

    # (tree, source-file, relative-name-for-reporting, destination)
    candidates: list[tuple[str, Path, str, Path]] = []

    # Root-level files first — they are the entry points a stranger reads, and
    # they are in no tree, so the rglob walk below can never reach them.
    for name in pub.get("include_files") or []:
        src = shared / name
        if src.is_file():
            candidates.append(("", src, name, base / name))

    for tree in pub.get("include") or []:
        src_root = shared / tree
        if not src_root.is_dir():
            continue
        for src in sorted(src_root.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(src_root).as_posix()
            if _excluded(rel, excludes):
                continue
            candidates.append((tree, src, f"{tree}/{rel}", base / tree / rel))

    # Every path that WILL exist in the published tree, in the same team-lib-relative
    # shape the registries use. Needed before the write loop so a registry can be filtered
    # against the whole set rather than against whatever has been written so far.
    # One implementation, shared with layer_drift_scan (see published_rel_paths).
    published_paths = published_rel_paths(pub, shared)
    registry_drops: dict[str, int] = {}

    for _tree, src, name, dst in candidates:
        # Text-vs-binary by DECODABILITY, not by suffix: a suffix allowlist
        # silently drops LICENSE, .gitignore and .csv, which are ordinary
        # publishable text. Anything that will not decode cannot be scrubbed,
        # so it is skipped and reported rather than copied blind — an image
        # can carry a client logo that no content gate would ever see.
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped.append(name)
            continue

        out = _generalize(text, rules)

        if is_registry(name):
            out, dropped = _filter_registry(out, published_paths, shared)
            if dropped:
                registry_drops[name] = dropped

        # The destination PATH is published too, and was never scrubbed. mirror.yaml's own
        # comments note client names appear as path fragments (`projects/northwind`,
        # `acme-health-brand`); an adversarial probe published `executions/acme-health_export_helper.py`
        # and `skills/northwind-deploy-notes/SKILL.md` with clean bodies and every gate reported
        # 0 leaks. A name is as public as a line of text.
        leftover = _blocked(out, blocklist) + _blocked(name, blocklist)
        if leftover:
            # Refuse, loudly. Publishing this would leak; silently skipping
            # it would make the public repo quietly incomplete instead.
            refused.append({"file": name, "identifiers": leftover[:6]})
            continue

        expected.add(dst)
        if dst.is_file() and dst.read_text(encoding="utf-8") == out:
            unchanged.append(name)
            continue

        written.append(name)
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(out, encoding="utf-8")

    if prune:
        # Root-level entry docs first. They come from include_files, not from a tree, so the
        # tree walk below never sees them and a renamed guide orphans forever: measured
        # 2026-08-01, renaming ONBOARDING.md to GETTING_STARTED.md left BOTH in the public
        # repo, and the stale one still read perfectly plausibly. Publication is a total
        # function over root files, so anything at the root that is not in include_files is
        # by definition no longer published.
        keep_root = set(pub.get("include_files") or [])
        for existing in sorted(base.glob("*")):
            if not existing.is_file() or existing.name in keep_root:
                continue
            if _excluded(existing.name, excludes):
                continue
            pruned.append(existing.name)
            if apply:
                existing.unlink()

        for tree in pub.get("include") or []:
            tree_root = base / tree
            if not tree_root.is_dir():
                continue
            for existing in sorted(tree_root.rglob("*")):
                if not existing.is_file() or existing in expected:
                    continue
                # EXCLUDED is not the same as DELETE. A path the contract excludes
                # is simply not managed by this publisher, so pruning it would be
                # the publisher deleting content it never owned — on the first run
                # that meant 680 vendored third-party skills. Prune is only for
                # files that WERE published from a source that no longer exists.
                if _excluded(existing.relative_to(tree_root).as_posix(), excludes):
                    continue
                pruned.append(str(existing.relative_to(base)))
                if apply:
                    existing.unlink()

    return {
        "status": "ok",
        "applied": apply,
        "written": written,
        "unchanged": unchanged,
        "refused": refused,
        "pruned": pruned,
        "skipped_binary": skipped,
        "registry_entries_dropped": registry_drops,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish team-lib to the public reference repo.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--force", action="store_true",
                    help="publish even if team-lib is not on main")
    ap.add_argument("--prune", action="store_true",
                    help="delete published files whose source no longer exists")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--verbose", action="store_true", help="list every file")
    args = ap.parse_args()

    r = run(apply=args.apply, prune=args.prune, manifest=args.manifest, force=args.force)
    if r["status"] == "error":
        print(f"Error: {r['error']}", file=sys.stderr)
        return 2

    mode = "APPLIED" if r["applied"] else "dry run"
    print(f"publish to public reference — {mode}")
    print(f"  written/updated : {len(r['written'])}")
    print(f"  unchanged       : {len(r['unchanged'])}")
    print(f"  refused (leak)  : {len(r['refused'])}")
    print(f"  pruned          : {len(r['pruned'])}")
    drops = r.get("registry_entries_dropped") or {}
    if drops:
        total = sum(drops.values())
        print(f"  registry entries dropped (path withheld from publication): {total}")
        for name, n in sorted(drops.items()):
            print(f"      {name}: {n}")
    print(f"  skipped (binary): {len(r['skipped_binary'])}")

    if r["refused"]:
        print("\nREFUSED — still contain a blocked identifier after generalization:")
        for item in r["refused"][:30]:
            print(f"  {item['file']}  {item['identifiers']}")
        print("\nEither add a generalization rule, or exclude the file as proprietary.")

    if args.verbose:
        for f in r["written"]:
            print(f"  + {f}")
        for f in r["pruned"]:
            print(f"  - {f}")

    return 1 if r["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
