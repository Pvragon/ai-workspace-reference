#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Creates an annotated git tag and publishes a GitHub release with release notes from a markdown file. Supports dry-run and idempotent re-runs."
# created: 2026-02-18
# last_updated: 2026-02-25
# maintainer: pvragon
# ---
"""
Publish GitHub Release

Creates an annotated git tag and publishes a GitHub release with release notes.
Designed for use with the AI Workspace release process.

Usage:
    python3 publish_github_release.py --version v1.3.2 --notes-file path/to/notes.md
    python3 publish_github_release.py --version v1.3.2 --notes-file path/to/notes.md --dry-run
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd: list[str], dry_run: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    """Execute a shell command, optionally in dry-run mode.

    Raises RuntimeError on failure (instead of sys.exit) for importability.
    """
    if dry_run:
        print(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    print(f"[EXEC] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {result.returncode}: {' '.join(cmd)}\nstderr: {result.stderr}"
        )

    return result


def tag_exists(version: str) -> bool:
    """Check if a git tag already exists."""
    result = subprocess.run(
        ["git", "tag", "-l", version],
        capture_output=True, text=True
    )
    return version in result.stdout.strip().split('\n')


def remote_tag_exists(version: str) -> bool:
    """Check if a tag exists on the remote."""
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "origin", version],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())


def github_release_exists(version: str) -> bool:
    """Check if a GitHub release already exists for this version."""
    result = subprocess.run(
        ["gh", "release", "view", version],
        capture_output=True, text=True
    )
    return result.returncode == 0


def run(version: str, notes_file: str, title: str = None, dry_run: bool = False) -> dict:
    """Importable entry point for programmatic use.

    Args:
        version: Version tag (e.g., 'v1.3.2'). The 'v' prefix will be added if missing.
        notes_file: Path to release notes markdown file.
        title: Release title (defaults to 'AI Workspace {version}').
        dry_run: If True, print commands without executing.

    Returns:
        dict with keys: status, version, title, tag_created, tag_pushed, release_created,
                        release_url, error, steps (list of log messages)
    """
    steps = []

    # Validate version format
    if not version.startswith("v"):
        version = f"v{version}"
        steps.append(f"Added 'v' prefix → {version}")

    # Validate notes file exists
    notes_path = Path(notes_file).expanduser().resolve()
    if not notes_path.exists():
        return {"status": "error", "error": f"Release notes file not found: {notes_path}"}

    # Set default title
    release_title = title or f"AI Workspace {version}"
    tag_created = False
    tag_pushed = False
    release_created = False
    release_url = None

    try:
        # Step 1: Check if tag already exists locally
        if tag_exists(version):
            steps.append(f"Tag {version} already exists locally")
        else:
            run_command(
                ["git", "tag", "-a", version, "-m", f"Release {version}"],
                dry_run=dry_run
            )
            tag_created = True
            steps.append(f"Created annotated tag: {version}")

        # Step 2: Push tag to origin
        if remote_tag_exists(version):
            steps.append(f"Tag {version} already exists on remote")
        else:
            run_command(
                ["git", "push", "origin", version],
                dry_run=dry_run
            )
            tag_pushed = True
            steps.append(f"Pushed tag {version} to origin")

        # Step 3: Check if GitHub release already exists
        if not dry_run and github_release_exists(version):
            steps.append(f"GitHub release {version} already exists — skipped")
            return {
                "status": "ok",
                "version": version,
                "title": release_title,
                "tag_created": tag_created,
                "tag_pushed": tag_pushed,
                "release_created": False,
                "release_url": None,
                "already_exists": True,
                "steps": steps,
            }

        # Step 4: Create GitHub release
        run_command(
            [
                "gh", "release", "create", version,
                "--title", release_title,
                "--notes-file", str(notes_path)
            ],
            dry_run=dry_run
        )
        release_created = True
        steps.append(f"GitHub release {version} published")

        # Get release URL
        if not dry_run:
            url_result = subprocess.run(
                ["gh", "release", "view", version, "--json", "url", "-q", ".url"],
                capture_output=True, text=True
            )
            if url_result.returncode == 0 and url_result.stdout.strip():
                release_url = url_result.stdout.strip()

    except RuntimeError as e:
        return {"status": "error", "error": str(e), "steps": steps}

    return {
        "status": "ok",
        "version": version,
        "title": release_title,
        "tag_created": tag_created,
        "tag_pushed": tag_pushed,
        "release_created": release_created,
        "release_url": release_url,
        "steps": steps,
    }


def main():
    """CLI entry point — thin wrapper around run()."""
    parser = argparse.ArgumentParser(
        description="Create git tag and publish GitHub release with release notes."
    )
    parser.add_argument(
        "--version", "-v",
        required=True,
        help="Version tag (e.g., v1.3.2)"
    )
    parser.add_argument(
        "--notes-file", "-n",
        required=True,
        help="Path to release notes markdown file"
    )
    parser.add_argument(
        "--title", "-t",
        default=None,
        help="Release title (default: 'AI Workspace {version}')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing"
    )

    args = parser.parse_args()

    result = run(args.version, args.notes_file, title=args.title, dry_run=args.dry_run)

    if result["status"] == "error":
        print(f"[ERROR] {result['error']}", file=sys.stderr)
        sys.exit(1)

    # Print step log
    print(f"\n{'='*60}")
    print(f"Publishing GitHub Release")
    print(f"{'='*60}")
    print(f"  Version:     {result['version']}")
    print(f"  Title:       {result['title']}")
    print(f"  Dry run:     {args.dry_run}")
    print(f"{'='*60}")
    for step in result.get("steps", []):
        print(f"[INFO] {step}")

    if result.get("already_exists"):
        print(f"\n[INFO] To update, delete the existing release first:")
        print(f"       gh release delete {result['version']} --yes")
    elif result.get("release_url"):
        print(f"\n[SUCCESS] View at: {result['release_url']}")
    else:
        print(f"\n[SUCCESS] GitHub release {result['version']} published!")


if __name__ == "__main__":
    main()
