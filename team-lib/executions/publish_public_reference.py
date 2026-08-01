#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
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


def _blocked(text: str, blocklist: list[tuple[str, str]]) -> list[str]:
    low = text.lower()
    return sorted({f"{g}:{t}" for g, t in blocklist if t.lower() in low})


def run(apply: bool = False, prune: bool = False, manifest: str | None = None) -> dict:
    """Publish team-lib into the public reference repo.

    Args:
        apply: Write changes. Default False (dry run).
        prune: Delete published files whose source no longer exists.
        manifest: Path to mirror.yaml; defaults to ../registry/mirror.yaml.

    Returns:
        dict with status, and lists: written, unchanged, refused, pruned, skipped_binary.
    """
    mpath = Path(manifest) if manifest else \
        Path(__file__).resolve().parent.parent / "registry" / "mirror.yaml"
    if not mpath.is_file():
        return {"status": "error", "error": f"manifest not found: {mpath}"}

    spec = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
    pub = spec.get("publication") or {}
    layers = spec.get("layers") or {}
    ws = workspace()

    shared = ws / layers.get("shared", "team-lib")
    public = ws / layers.get("public", "")
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

        leftover = _blocked(out, blocklist)
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
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish team-lib to the public reference repo.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--prune", action="store_true",
                    help="delete published files whose source no longer exists")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--verbose", action="store_true", help="list every file")
    args = ap.parse_args()

    r = run(apply=args.apply, prune=args.prune, manifest=args.manifest)
    if r["status"] == "error":
        print(f"Error: {r['error']}", file=sys.stderr)
        return 2

    mode = "APPLIED" if r["applied"] else "dry run"
    print(f"publish to public reference — {mode}")
    print(f"  written/updated : {len(r['written'])}")
    print(f"  unchanged       : {len(r['unchanged'])}")
    print(f"  refused (leak)  : {len(r['refused'])}")
    print(f"  pruned          : {len(r['pruned'])}")
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
