#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: >-
#   Collects every `shortcut: <limit>, <when to upgrade>` code comment across the workspace's git
#   repos into one generated ledger (my-lib/context/indexed/shortcut-ledger.md), tagging markers
#   that name no upgrade trigger. Run nightly by dream_cycle.py. Has --self-check.
# created: 2026-10-21
# last_updated: 2026-10-21
# maintainer: pvragon
# ---
"""shortcut_ledger.py — so a deliberate shortcut cannot quietly become permanent.

The convention (execution-standard.md, Key Rule 8; adapted from Ponytail's /ponytail-debt):

    # shortcut: <the limit>, <when to upgrade>

Only code comments count (a `#`, `//` or `/*` prefix in a code file), so prose that merely
describes the convention, like the execution standard itself, stays out of the ledger. Ignored
files, `archive/` and third-party `_external/` trees are skipped. The ledger is a GENERATED
file: fix the comment in the code, never the ledger row.

Usage
-----
    python3 shortcut_ledger.py              # print the ledger, write nothing
    python3 shortcut_ledger.py --apply      # write the ledger file
    python3 shortcut_ledger.py --json       # machine-readable rows
    python3 shortcut_ledger.py --self-check # assert the parser on known cases
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

WS = Path.home() / "ai-workspace"
OUT = WS / "my-lib" / "context" / "indexed" / "shortcut-ledger.md"
CODE_GLOBS = ["*.py", "*.sh", "*.js", "*.mjs", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs"]
SKIP_PARTS = {"archive", "_archive", "_external", "node_modules"}
GREP = r"(#|//|/\*) ?shortcut:"
MARKER = re.compile(r"(?:#|//|/\*)\s?shortcut:\s*(.*?)\s*(?:\*/)?\s*$")


def _repos() -> list[Path]:
    """The workspace's own git repos: the layers plus every project with a .git."""
    roots = [WS / n for n in ("my-lib", "team-lib", "personal", "agents")]
    projects = WS / "projects"
    if projects.is_dir():
        roots += sorted(p for p in projects.iterdir() if (p / ".git").exists())
    return [r for r in roots if (r / ".git").exists()]


def parse(comment_line: str) -> dict | None:
    """Split one source line into limit and trigger. None when it is not a marker."""
    m = MARKER.search(comment_line)
    if not m or not m.group(1):
        return None
    before = comment_line[:m.start()]
    if before.count('"') % 2 or before.count("'") % 2:  # inside a string literal, not a comment
        return None
    body = m.group(1)
    if body.startswith("<"):  # the convention's own placeholder, e.g. in a docstring
        return None
    limit, sep, trigger = body.partition(", ")
    return {"limit": limit.strip(), "trigger": trigger.strip() if sep else ""}


def _blame(repo: Path, path: str, line: int) -> tuple[str, str]:
    r = subprocess.run(["git", "-C", str(repo), "blame", "--porcelain", "-L", f"{line},{line}", "--", path],
                       capture_output=True, text=True)
    author, when = "uncommitted", ""
    for l in r.stdout.splitlines():
        if l.startswith("author "):
            author = l[7:]
        elif l.startswith("author-time "):
            when = dt.date.fromtimestamp(int(l[12:])).isoformat()
    return author, when


def run(apply: bool = False, out: Path = OUT) -> dict:
    """Scan every repo and build the ledger.

    Args:
        apply: write the ledger to `out` when True.
        out: ledger path.
    Returns:
        {"status", "rows": [{repo, file, line, limit, trigger, no_trigger, author, date}],
         "markers", "no_trigger", "written"}
    """
    rows = []
    for repo in _repos():
        r = subprocess.run(["git", "-C", str(repo), "grep", "--untracked", "-nE", GREP, "--", *CODE_GLOBS],
                           capture_output=True, text=True)
        if r.returncode not in (0, 1):
            return {"status": "error", "error": f"git grep failed in {repo}: {r.stderr.strip()[:200]}"}
        for hit in r.stdout.splitlines():
            path, lineno, text = hit.split(":", 2)
            if SKIP_PARTS & set(Path(path).parts):
                continue
            p = parse(text)
            if p is None:
                continue
            author, when = _blame(repo, path, int(lineno))
            rows.append({"repo": repo.name, "file": path, "line": int(lineno), **p,
                         "no_trigger": not p["trigger"], "author": author, "date": when})
    no_trig = sum(r["no_trigger"] for r in rows)
    result = {"status": "ok", "rows": rows, "markers": len(rows), "no_trigger": no_trig, "written": None}
    if apply:
        out.write_text(render(rows))
        result["written"] = str(out)
    return result


def render(rows: list[dict]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        "---",
        "template: generated-ledger",
        "version: 1.0.0",
        'summary: "Generated ledger of every `shortcut:` code comment across the workspace repos, '
        'with markers that name no upgrade trigger tagged. Regenerated nightly by '
        'team-lib/executions/shortcut_ledger.py; never hand-edit."',
        "created: 2026-10-21",
        f"last_updated: {today}",
        "maintainer: pvragon",
        "---",
        "",
        "# Shortcut ledger",
        "",
        "<!-- GENERATED by team-lib/executions/shortcut_ledger.py. Fix the comment in the code, not this file. -->",
        "",
        "Every deliberate shortcut, from comments of the form `# shortcut: <the limit>, <when to upgrade>`",
        "(execution-standard.md, Key Rule 8). A row tagged **no-trigger** names no upgrade trigger;",
        "those are the ones that rot.",
        "",
    ]
    if not rows:
        lines.append("No shortcut debt. Clean ledger.")
    for repo in sorted({r["repo"] for r in rows}):
        lines += ["", f"## {repo}", ""]
        for r in (x for x in rows if x["repo"] == repo):
            tag = " **no-trigger**" if r["no_trigger"] else ""
            trig = r["trigger"] or "none named"
            lines.append(f"- `{r['file']}:{r['line']}`: {r['limit']}. Upgrade: {trig}. "
                         f"({r['author']}, {r['date'] or 'uncommitted'}){tag}")
    lines += ["", f"{len(rows)} markers, {sum(r['no_trigger'] for r in rows)} with no trigger.", ""]
    return "\n".join(lines)


def self_check() -> None:
    assert parse("x = 1  # shortcut: linear scan, index it past 10k rows") == \
        {"limit": "linear scan", "trigger": "index it past 10k rows"}
    assert parse("// shortcut: hard-coded payer list") == {"limit": "hard-coded payer list", "trigger": ""}
    assert parse("/* shortcut: no retry, add backoff if 429s appear */") == \
        {"limit": "no retry", "trigger": "add backoff if 429s appear"}
    assert parse("#shortcut: a, b, c") == {"limit": "a", "trigger": "b, c"}
    assert parse("    # shortcut: <the limit>, <when to upgrade>") is None  # placeholder
    assert parse("print('keyboard shortcut: ctrl+s')") is None  # not a comment marker
    assert parse("# shortcut:") is None
    mk = "#" + " shortcut:"  # split so this test line is not itself a marker
    assert parse(f'assert parse("x  {mk} in a string, not a marker")') is None
    assert parse("s = 'a'  # shortcut: after a closed string, still a marker") == \
        {"limit": "after a closed string", "trigger": "still a marker"}
    rows = [{"repo": "r", "file": "a.py", "line": 3, "limit": "x", "trigger": "", "no_trigger": True,
             "author": "me", "date": "2026-10-21"}]
    text = render(rows)
    assert "**no-trigger**" in text and "1 markers, 1 with no trigger." in text
    assert "Clean ledger." in render([])
    print("self-check ok")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the ledger file")
    ap.add_argument("--json", action="store_true", help="print rows as JSON")
    ap.add_argument("--self-check", action="store_true", help="assert the parser on known cases")
    a = ap.parse_args()
    if a.self_check:
        self_check()
        return
    res = run(apply=a.apply)
    if res["status"] != "ok":
        print(res["error"], file=sys.stderr)
        sys.exit(1)
    if a.json:
        print(json.dumps(res, indent=1))
    elif a.apply:
        print(f"{res['markers']} marker(s), {res['no_trigger']} with no trigger -> {res['written']}")
    else:
        print(render(res["rows"]))


if __name__ == "__main__":
    main()
