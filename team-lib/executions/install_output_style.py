#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: 'Installs the agent chat-voice output style end to end: scaffold agents/<agent>/output-styles/<agent>-output-style.md
#   from context/indexed/templates/template-output-style.md (name set from identity.md), symlink ~/.claude/output-styles
#   to that directory, and set "outputStyle" in ~/.claude/settings.json. Idempotent, dry-run by default (--apply writes).
#   Never overwrites an existing style file; never edits a style that already has content.'
# created: 2026-09-05
# last_updated: 2026-09-05
# maintainer: pvragon
# ---
"""
install_output_style.py — put the agent's chat voice where Claude Code reads it.

Why a script: the style is a system-prompt-level artifact. It lives canonically in the agent home
(agents/<agent>/output-styles/) so it is git-backed and vendor-independent, and the vendor reads it
through a symlink at ~/.claude/output-styles/. Three things have to agree — the file's `name:`, the
symlink, and the `outputStyle` setting — and a hand install that gets two of three right looks
installed and silently is not.

Usage:
  install_output_style.py            # dry run: report what would change
  install_output_style.py --apply    # write
  install_output_style.py --json     # machine-readable report

Exit: 0 ok (or nothing to do), 1 failed, 2 deferred (no agent home yet — run choose-name first).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import AgentResolutionError, agent_home, output_styles_dir  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "context/indexed/templates/template-output-style.md"
SETTINGS = Path.home() / ".claude/settings.json"
VENDOR_DIR = Path.home() / ".claude/output-styles"
# Claude Code reads only these three keys from a style's frontmatter; workspace metadata is dropped
# on install so the vendor sees a clean style file.
KEEP_KEYS = ("name", "description", "keep-coding-instructions")


def _agent_display_name(home: Path) -> str:
    """The `name:` from identity.md, else the directory name."""
    ident = home / "identity.md"
    if ident.is_file():
        m = re.search(r"^name:\s*(.+?)\s*$", ident.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return home.name


def _render_style(template_text: str, name: str) -> str:
    """Template body with a vendor-clean frontmatter (name substituted, workspace keys dropped)."""
    parts = template_text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"template has no frontmatter: {TEMPLATE}")
    fm_lines = []
    for line in parts[1].strip("\n").splitlines():
        key = line.split(":", 1)[0].strip()
        if key in KEEP_KEYS:
            fm_lines.append(line.replace("<your-agent-name>", name))
    return "---\n" + "\n".join(fm_lines) + "\n---" + parts[2]


def run(apply: bool = False) -> dict:
    """Scaffold the style, link the vendor dir, select the style. Returns a report dict."""
    actions: list[str] = []
    try:
        home = agent_home()
    except AgentResolutionError as exc:
        return {"status": "deferred", "reason": f"no agent home yet: {exc}", "actions": actions}
    if not TEMPLATE.is_file():
        return {"status": "error", "reason": f"template missing: {TEMPLATE}", "actions": actions}

    name = _agent_display_name(home)
    sdir = output_styles_dir()
    style = sdir / f"{home.name}-output-style.md"

    # 1. style file. An agent that already has a style under any filename keeps it: the one whose
    #    `name:` matches the current outputStyle setting wins, else the conventional filename.
    settings = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.is_file() else {}
    existing: dict[str, Path] = {}
    if sdir.is_dir():
        for f in sorted(sdir.glob("*.md")):
            m = re.search(r"^name:\s*(.+?)\s*$", f.read_text(encoding="utf-8"), re.M)
            if m and f.name != "README.md":
                existing[m.group(1).strip()] = f
    current = settings.get("outputStyle")
    if current in existing:
        style, name = existing[current], current
    if style.is_file():
        actions.append(f"keep      {style} (exists; not overwritten)")
        m = re.search(r"^name:\s*(.+?)\s*$", style.read_text(encoding="utf-8"), re.M)
        if m:
            name = m.group(1).strip()
    else:
        actions.append(f"create    {style} (name: {name})")
        if apply:
            sdir.mkdir(parents=True, exist_ok=True)
            style.write_text(_render_style(TEMPLATE.read_text(encoding="utf-8"), name), encoding="utf-8")

    # 2. vendor symlink
    if VENDOR_DIR.is_symlink():
        if VENDOR_DIR.resolve() == sdir.resolve():
            actions.append(f"ok        {VENDOR_DIR} -> {sdir}")
        else:
            return {"status": "error", "actions": actions,
                    "reason": f"{VENDOR_DIR} points at {VENDOR_DIR.resolve()}, not {sdir}; fix by hand"}
    elif VENDOR_DIR.exists():
        return {"status": "error", "actions": actions,
                "reason": f"{VENDOR_DIR} is a real directory; move its files into {sdir} and remove it, then re-run"}
    else:
        actions.append(f"link      {VENDOR_DIR} -> {sdir}")
        if apply:
            sdir.mkdir(parents=True, exist_ok=True)
            VENDOR_DIR.symlink_to(sdir)

    # 3. settings.json
    if settings.get("outputStyle") == name:
        actions.append(f"ok        outputStyle = {name}")
    else:
        actions.append(f"set       outputStyle = {name} (was {settings.get('outputStyle')!r})")
        if apply:
            settings["outputStyle"] = name
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
            tmp.replace(SETTINGS)

    return {"status": "ok", "applied": apply, "style": str(style), "name": name, "actions": actions}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args()
    rep = run(apply=a.apply)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        tag = "" if a.apply else "  [dry-run]"
        for line in rep.get("actions", []):
            print(f"  {line}{tag}")
        if rep["status"] != "ok":
            print(f"{rep['status'].upper()}: {rep.get('reason')}")
        elif not a.apply:
            print("dry run — re-run with --apply to write")
    return {"ok": 0, "deferred": 2}.get(rep["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
