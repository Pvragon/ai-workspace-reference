#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Scaffolds the standard docs/ directory structure for a project in projects/, copying templates and replacing placeholders."
# created: 2026-02-18
# last_updated: 2026-02-25
# maintainer: pvragon
# ---
"""Scaffold the standard docs/ structure for a project in projects/.

Usage:
    python scaffold_project_docs.py <target_path> [--name PROJECT_NAME] [--force]

Examples:
    python scaffold_project_docs.py ~/ai-workspace/projects/my-app
    python scaffold_project_docs.py ~/ai-workspace/projects/my-app --name "My App"
    python scaffold_project_docs.py ~/ai-workspace/projects/my-app --force
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# Template location relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / "context" / "indexed" / "templates" / "docs-structure"


def find_projects_root(target: Path) -> Path | None:
    """Walk up from target to find a directory named 'projects'."""
    for parent in [target] + list(target.parents):
        if parent.name == "projects":
            return parent
    return None


def validate_target(target: Path) -> None:
    """Ensure the target is inside a projects/ directory."""
    projects_root = find_projects_root(target)
    if projects_root is None:
        print(f"Error: Target '{target}' is not inside a projects/ directory.", file=sys.stderr)
        sys.exit(1)
    if target == projects_root:
        print(f"Error: Target is the projects/ root itself. Specify a project subdirectory.", file=sys.stderr)
        sys.exit(1)


def scaffold(target: Path, project_name: str, force: bool) -> dict:
    """Copy template structure to target/docs/ with placeholder replacement.

    Returns:
        dict with keys: status, docs_dir, project_name, files_created, placeholders_replaced, error
    """
    docs_dir = target / "docs"

    if docs_dir.exists() and not force:
        return {"status": "error", "error": f"'{docs_dir}' already exists. Use --force to overwrite."}

    if not TEMPLATE_DIR.exists():
        return {"status": "error", "error": f"Template directory not found at '{TEMPLATE_DIR}'."}

    # Copy template tree
    if docs_dir.exists() and force:
        shutil.rmtree(docs_dir)

    shutil.copytree(TEMPLATE_DIR, docs_dir)

    # Replace placeholders in all files
    replaced_count = 0
    for filepath in docs_dir.rglob("*"):
        if filepath.is_file() and filepath.name != ".gitkeep":
            content = filepath.read_text(encoding="utf-8")
            if "{PROJECT_NAME}" in content:
                filepath.write_text(content.replace("{PROJECT_NAME}", project_name), encoding="utf-8")
                replaced_count += 1

    files_created = sum(1 for _ in docs_dir.rglob('*') if _.is_file())

    return {
        "status": "ok",
        "docs_dir": str(docs_dir),
        "project_name": project_name,
        "files_created": files_created,
        "placeholders_replaced": replaced_count,
    }


def run(target: str, name: str = None, force: bool = False) -> dict:
    """Importable entry point for programmatic use.

    Args:
        target: Path to the project directory.
        name: Project name for placeholders (defaults to directory name).
        force: Overwrite existing docs/ directory.

    Returns:
        dict with status and result details.
    """
    target_path = Path(target).resolve()
    validate_target(target_path)

    project_name = name or target_path.name
    target_path.mkdir(parents=True, exist_ok=True)

    return scaffold(target_path, project_name, force)


def main() -> None:
    """CLI entry point — thin wrapper around run()."""
    parser = argparse.ArgumentParser(description="Scaffold standard docs/ structure for a project.")
    parser.add_argument("target", type=str, help="Path to the project directory")
    parser.add_argument("--name", type=str, default=None, help="Project name for placeholders (defaults to directory name)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing docs/ directory")
    args = parser.parse_args()

    result = run(args.target, name=args.name, force=args.force)

    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"Scaffolded docs/ structure at: {result['docs_dir']}")
    print(f"  Project name: {result['project_name']}")
    print(f"  Files created: {result['files_created']}")
    print(f"  Placeholders replaced in: {result['placeholders_replaced']} files")


if __name__ == "__main__":
    main()
