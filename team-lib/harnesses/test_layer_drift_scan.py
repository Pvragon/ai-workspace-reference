#!/usr/bin/env python3
# ---
# template: harness
# version: 1.0.0
# summary: "Falsifiability harness for layer_drift_scan.py. Builds a synthetic two-layer workspace in
#   a temp dir and asserts every detector branch BOTH fires when it should and stays silent when it
#   should — including the case that motivated the scanner (identical version numbers, different
#   content) and the case that would make it useless (a check that never fires). Run before trusting
#   a clean scan result."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""test_layer_drift_scan.py — prove the drift detector can actually fail.

A drift detector that reports "clean" is only meaningful if it is capable of
reporting "dirty". Each case below is paired: something that MUST be flagged and
something that MUST NOT be, so a scan that silently stopped working is caught.

Usage:
    python3 harnesses/test_layer_drift_scan.py          # run all cases
    python3 harnesses/test_layer_drift_scan.py -v       # show each finding
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "executions"))

MANIFEST = Path(__file__).resolve().parent.parent / "registry" / "mirror.yaml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fm(version: str | None = "1.0.0", mirror: str | None = None,
        body: str = "body", **extra) -> str:
    lines = ["---"]
    if version:
        lines.append(f"version: {version}")
    if mirror:
        lines.append(f"mirror: {mirror}")
    for k, v in extra.items():
        lines.append(f"{k}: {v}")
    lines += ["---", "", body, ""]
    return "\n".join(lines)


def _build(root: Path) -> None:
    """A synthetic workspace exercising every branch."""
    mine, team = root / "my-lib", root / "team-lib"
    for layer in (mine, team):
        for d in ("skills", "registry", "executions", "directives",
                  "context/indexed", "personas", "harnesses"):
            (layer / d).mkdir(parents=True, exist_ok=True)

    # MUST FIRE — same version, different content (the silent case)
    _write(mine / "skills/alpha/SKILL.md", _fm(body="personal"))
    _write(team / "skills/alpha/SKILL.md", _fm(body="shared"))

    # MUST NOT FIRE — divergence declared on BOTH sides
    _write(mine / "skills/beta/SKILL.md",
           _fm(mirror="divergent", body="A", mirror_reason='"public variant"'))
    _write(team / "skills/beta/SKILL.md",
           _fm(mirror="divergent", body="B", mirror_reason='"public variant"'))

    # MUST FIRE — one-sided declaration is not a declaration
    _write(mine / "skills/gamma/SKILL.md", _fm(mirror="divergent", body="A"))
    _write(team / "skills/gamma/SKILL.md", _fm(body="B"))

    # MUST NOT FIRE — personal-only but declared local
    _write(mine / "skills/delta/SKILL.md", _fm(mirror="local", body="local"))

    # MUST FIRE (low) — personal-only, undeclared
    _write(mine / "skills/epsilon/SKILL.md", _fm(body="local"))

    # MUST NOT FIRE — only the frontmatter differs; the body is identical
    _write(mine / "skills/zeta/SKILL.md", _fm(version="9.9.9", body="same"))
    _write(team / "skills/zeta/SKILL.md", _fm(version="1.0.0", body="same"))

    # MUST NOT FIRE — index.md is a per-layer folder README by design
    _write(mine / "skills/index.md", "# personal index\n")
    _write(team / "skills/index.md", "# shared index\n")

    # MUST NOT FIRE — trailing-whitespace / blank-line churn is not drift
    _write(mine / "executions/whitespace.py", "# ---\n# version: 1.0.0\n# ---\nx = 1\n")
    _write(team / "executions/whitespace.py", "# ---\n# version: 1.0.0\n# ---\nx = 1   \n\n\n")

    # MUST FIRE — versions differ AND content differs
    _write(mine / "directives/known.md", _fm(version="2.0.0", body="new"))
    _write(team / "directives/known.md", _fm(version="1.0.0", body="old"))

    # MUST FIRE — registry entry pointing at nothing
    _write(team / "registry/skills.yaml",
           "skills:\n  - name: ghost\n    path: skills/does-not-exist/SKILL.md\n")

    # MUST NOT FIRE — registry entry that resolves
    _write(mine / "registry/skills.yaml",
           "skills:\n  - name: alpha\n    path: skills/alpha/SKILL.md\n")


CASES = [
    # (item, expected_kind or None for "must not be reported", note)
    ("skills/alpha", "silent-drift", "identical version, different content"),
    ("skills/beta", "declared-divergent", "two-sided declaration is accepted"),
    ("skills/gamma", "silent-drift", "one-sided declaration is rejected"),
    ("skills/delta", None, "`mirror: local` suppresses the ungraduated nag"),
    ("skills/epsilon", "ungraduated", "personal-only and undeclared"),
    ("skills/zeta", None, "frontmatter-only difference is not drift"),
    ("skills/index.md", None, "per-layer folder README"),
    ("executions/whitespace.py", None, "whitespace churn is not drift"),
    ("directives/known.md", "known-drift", "visible version skew"),
    ("registry/shared:skills.yaml", "registry-dangling", "entry resolves to nothing"),
    ("registry/personal:skills.yaml", None, "entry that resolves is silent"),
]


def main() -> int:
    verbose = "-v" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="layer-drift-test-"))
    try:
        _build(tmp)
        os.environ["PVRAGON_WORKSPACE"] = str(tmp)

        import agent_paths
        agent_paths.workspace.cache_clear()
        import layer_drift_scan

        result = layer_drift_scan.run(manifest=MANIFEST)
        if result["status"] != "ok":
            print(f"FAIL: scan errored — {result.get('error')}", file=sys.stderr)
            return 1

        found = {f"{f['tree']}/{f['item']}": f for f in result["findings"]}
        if verbose:
            for f in result["findings"]:
                print(f"  {f['severity']:5} {f['kind']:20} {f['tree']}/{f['item']}")
            print()

        failures = []
        for item, expected, note in CASES:
            got = found.get(item)
            if expected is None:
                if got is not None:
                    failures.append(f"{item}: expected SILENCE ({note}), got {got['kind']}")
            elif got is None:
                failures.append(f"{item}: expected {expected} ({note}), got nothing")
            elif got["kind"] != expected:
                failures.append(f"{item}: expected {expected} ({note}), got {got['kind']}")

        # The one-sided case must also carry the explanatory flag.
        gamma = found.get("skills/gamma")
        if gamma and not gamma.get("one_sided_declaration"):
            failures.append("skills/gamma: one_sided_declaration flag not set")

        for line in failures:
            print(f"FAIL  {line}")
        if failures:
            print(f"\n{len(failures)} of {len(CASES)} case(s) failed")
            return 1

        print(f"ok — {len(CASES)} cases pass "
              f"({sum(1 for c in CASES if c[1])} fire, "
              f"{sum(1 for c in CASES if not c[1])} correctly silent)")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("PVRAGON_WORKSPACE", None)


if __name__ == "__main__":
    sys.exit(main())
