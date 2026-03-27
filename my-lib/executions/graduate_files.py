#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Safely graduates files from my-lib to team-lib with version conflict detection, collision prevention, metadata validation, and automatic git branch/PR workflow."
# created: 2026-02-18
# last_updated: 2026-02-25
# maintainer: pvragon
# ---
"""
Graduate files from private library (my-lib) to team library (team-lib).

This script safely moves agent-consumable files to the shared team library with:
- Version conflict detection
- Collision prevention
- Metadata validation
- Automatic git operations

Usage:
    python graduate_files.py <file1> [file2] [file3] ...

Examples:
    python graduate_files.py context/indexed/pvragon/pvragon-business-overview.md

    python graduate_files.py \\
        context/indexed/pvragon/pvragon-business-overview.md \\
        context/indexed/example-company/example-business-overview.md
"""

import os
import sys
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

@dataclass
class FileGraduation:
    """Represents a file being graduated"""
    relative_path: str
    source_path: Path
    target_path: Path
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    conflict: bool = False

# Configuration
PRIVATE_LIBRARY = Path.home() / "ai-workspace" / "my-lib"
TEAM_LIBRARY = Path.home() / "ai-workspace" / "team-lib"

# Exclusion patterns - files that should never be graduated
EXCLUSION_PATTERNS = [
    r'secrets/',
    r'\.env',
    r'credentials\.json',
    r'token\.json',
    r'runtime/',
    r'\.tmp/',
    r'__pycache__/',
    r'\.git/',
]

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.RESET} {text}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.RESET} {text}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {text}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {text}")

def extract_version_from_file(file_path: Path) -> Optional[str]:
    """Extract version from YAML frontmatter"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Match YAML frontmatter
        match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL | re.MULTILINE)
        if not match:
            return None

        frontmatter = match.group(1)

        # Extract version
        version_match = re.search(r'version:\s*([^\s]+)', frontmatter)
        if version_match:
            return version_match.group(1)

        return None
    except Exception as e:
        print_warning(f"Could not extract version from {file_path}: {e}")
        return None

def is_excluded_file(relative_path: str) -> bool:
    """Check if file matches exclusion patterns"""
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, relative_path):
            return True
    return False

def validate_file(relative_path: str) -> Tuple[bool, str]:
    """Validate that file is eligible for graduation"""

    # Check if excluded
    if is_excluded_file(relative_path):
        return False, "File type is excluded (secrets, runtime files, etc.)"

    # Check if file exists
    source_path = PRIVATE_LIBRARY / relative_path
    if not source_path.exists():
        return False, f"File does not exist: {source_path}"

    if not source_path.is_file():
        return False, f"Path is not a file: {source_path}"

    # Check for metadata (for certain file types)
    if any(source_path.match(pattern) for pattern in ['*.md', '*.py']):
        version = extract_version_from_file(source_path)
        if version is None and source_path.suffix == '.md':
            return False, "Markdown file missing version in YAML frontmatter"

    # --- GOVERNANCE CHECKS ---

    # 1. Naming Conventions
    filename = source_path.name
    if ' ' in filename:
        return False, "Filename contains spaces (use kebab-case or snake_case)"

    if source_path.suffix == '.md':
        if not re.match(r'^[a-z0-9-]+\.md$', filename):
            return False, "Markdown files must be kebab-case (lowercase, hyphens)"

    if source_path.suffix == '.py':
        # common python convention is snake_case
        if not re.match(r'^[a-z0-9_]+\.py$', filename):
            return False, "Python scripts must be snake_case (lowercase, underscores)"

    # 2. No Personal Stuff (User Namespacing)
    # Heuristic: Check for user name prefixes or common personal patterns
    # This assumes the current user's name might be part of the filename
    current_user = os.getenv('USER', 'unknown')
    if filename.startswith(f"{current_user}-") or filename.startswith("user-"):
        return False, "Personal namespacing detected (user-*). Please generalize the resource."

    # 3. Content Safety (Hardcoded paths)
    try:
        with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Check for absolute home dir paths
            home_dir = str(Path.home())
            if home_dir in content:
                # Exception: if checking for the env var definition itself, but unlikely in source code
                return False, f"Hardcoded absolute path detected ({home_dir}). Use $WORKSPACE_ROOT or relative paths."
    except Exception as e:
        print_warning(f"Could not scan content for safety: {e}")

    # 4. Definition of Done (Docstrings key check)
    if source_path.suffix == '.py':
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if '"""' not in content and "'''" not in content:
                 return False, "Python script missing module-level docstring (Definition of Done)"

    return True, "OK"

def check_version_conflict(graduation: FileGraduation) -> Tuple[bool, str]:
    """Check for version conflicts between source and target"""

    if not graduation.target_path.exists():
        return False, "No conflict - file doesn't exist in team library"

    # Extract versions
    source_version = extract_version_from_file(graduation.source_path)
    target_version = extract_version_from_file(graduation.target_path)

    graduation.source_version = source_version
    graduation.target_version = target_version

    if source_version is None or target_version is None:
        return False, "Cannot compare versions - missing metadata"

    # Parse semantic versions
    def parse_version(v: str) -> Tuple[int, int, int]:
        parts = v.split('.')
        return (int(parts[0]), int(parts[1]), int(parts[2]))

    try:
        src_ver = parse_version(source_version)
        tgt_ver = parse_version(target_version)
    except:
        return False, "Cannot parse version numbers"

    if src_ver < tgt_ver:
        return True, f"CONFLICT: Team version ({target_version}) is newer than your version ({source_version})"
    elif src_ver == tgt_ver:
        return True, f"CONFLICT: Same version ({source_version}) exists in team library"
    else:
        # Source is newer - warn but allow
        return False, f"WARNING: Your version ({source_version}) is newer than team version ({target_version})"

def run_git_command(repo_path: Path, command: List[str]) -> Tuple[bool, str]:
    """Run a git command in the specified repository"""
    try:
        result = subprocess.run(
            ['git'] + command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def run(files: list[str], dry_run: bool = False, confirm: bool = True) -> dict:
    """Importable entry point for programmatic use.

    Args:
        files: List of relative file paths within my-lib to graduate to team-lib.
        dry_run: If True, validate and check conflicts but don't copy or commit.
        confirm: If True, prompt user for confirmation before proceeding.
                 Set to False for non-interactive/programmatic use.

    Returns:
        dict with keys: status, files_graduated, team_commit, private_commit,
                        branch_name, pr_url, steps, errors
    """
    steps = []
    errors = []

    if not files:
        return {"status": "error", "error": "No files specified", "steps": steps}

    # Phase 1: Validate all files
    graduations: List[FileGraduation] = []
    validation_failed = False

    for relative_path in files:
        valid, message = validate_file(relative_path)

        if not valid:
            errors.append(f"{relative_path}: {message}")
            validation_failed = True
        else:
            source_path = PRIVATE_LIBRARY / relative_path
            target_path = TEAM_LIBRARY / relative_path

            graduation = FileGraduation(
                relative_path=relative_path,
                source_path=source_path,
                target_path=target_path
            )
            graduations.append(graduation)
            steps.append(f"Validated: {relative_path}")

    if validation_failed:
        return {"status": "error", "error": "Validation failed", "errors": errors, "steps": steps}

    # Phase 2: Check for conflicts
    conflicts_found = False
    for graduation in graduations:
        has_conflict, message = check_version_conflict(graduation)

        if has_conflict:
            errors.append(f"{graduation.relative_path}: {message}")
            graduation.conflict = True
            conflicts_found = True
        else:
            steps.append(f"Conflict check: {graduation.relative_path} — {message}")

    if conflicts_found:
        return {"status": "error", "error": "Version conflicts detected", "errors": errors, "steps": steps}

    # Phase 3: Confirm (interactive mode only)
    if confirm and not dry_run:
        print_header("Ready to Graduate")
        print("The following files will be graduated:\n")
        for graduation in graduations:
            print(f"  • {graduation.relative_path}")

        print(f"\nFrom: {Colors.YELLOW}{PRIVATE_LIBRARY}{Colors.RESET}")
        print(f"To:   {Colors.GREEN}{TEAM_LIBRARY}{Colors.RESET}\n")

        response = input(f"{Colors.BOLD}Proceed with graduation? (y/N): {Colors.RESET}").strip().lower()
        if response != 'y':
            return {"status": "cancelled", "steps": steps}

    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "files_validated": [g.relative_path for g in graduations],
            "steps": steps,
        }

    # Phase 4: Copy files to team library
    for graduation in graduations:
        graduation.target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(graduation.source_path, graduation.target_path)
        steps.append(f"Copied: {graduation.relative_path}")

    # Phase 5: Git operations in team library (PR WORKFLOW)
    username = os.getenv('USER', 'unknown')
    date = subprocess.run(['date', '+%Y-%m-%d'], capture_output=True, text=True).stdout.strip()
    timestamp = subprocess.run(['date', '+%H%M'], capture_output=True, text=True).stdout.strip()

    # 1. Create Branch
    branch_name = f"graduation/{username}/{date}-{timestamp}"
    success, output = run_git_command(TEAM_LIBRARY, ['checkout', '-b', branch_name])
    if not success:
        steps.append(f"Warning: Could not create branch {branch_name}, proceeding on current branch")
    else:
        steps.append(f"Created branch: {branch_name}")

    # 2. Add files
    for graduation in graduations:
        success, output = run_git_command(TEAM_LIBRARY, ['add', str(graduation.relative_path)])
        if not success:
            return {"status": "error", "error": f"Git add failed: {graduation.relative_path}: {output}", "steps": steps}

    # 3. Commit
    commit_message = f"""Graduate files from private library

Files graduated:
{chr(10).join('- ' + g.relative_path for g in graduations)}

Graduated by: {username}
Date: {date}
Source: my-lib"""

    success, output = run_git_command(TEAM_LIBRARY, ['commit', '-m', commit_message])
    if not success:
        return {"status": "error", "error": f"Git commit failed in team-lib: {output}", "steps": steps}

    success, team_commit_hash = run_git_command(TEAM_LIBRARY, ['rev-parse', '--short', 'HEAD'])
    team_commit_hash = team_commit_hash.strip()
    steps.append(f"Committed to team-lib ({branch_name}): {team_commit_hash}")

    # 4. Push Branch
    success, output = run_git_command(TEAM_LIBRARY, ['push', '-u', 'origin', branch_name])
    if not success:
        return {"status": "error", "error": f"Git push failed in team-lib: {output}", "steps": steps}
    steps.append(f"Pushed branch: {branch_name}")

    # 5. Switch back to main
    run_git_command(TEAM_LIBRARY, ['checkout', 'main'])

    # Phase 6: Remove from private library
    for graduation in graduations:
        success, output = run_git_command(PRIVATE_LIBRARY, ['rm', str(graduation.relative_path)])
        if not success:
            return {"status": "error", "error": f"Git rm failed in my-lib: {graduation.relative_path}: {output}", "steps": steps}
        steps.append(f"Removed from my-lib: {graduation.relative_path}")

    removal_message = f"""Graduated files to team library

Files moved to team-lib:
{chr(10).join('- ' + g.relative_path for g in graduations)}

Team repo commit: {team_commit_hash}"""

    success, output = run_git_command(PRIVATE_LIBRARY, ['commit', '-m', removal_message])
    if not success:
        return {"status": "error", "error": f"Git commit failed in my-lib: {output}", "steps": steps}

    success, private_commit_hash = run_git_command(PRIVATE_LIBRARY, ['rev-parse', '--short', 'HEAD'])
    private_commit_hash = private_commit_hash.strip()

    success, output = run_git_command(PRIVATE_LIBRARY, ['push', 'origin', 'main'])
    if not success:
        return {"status": "error", "error": f"Git push failed in my-lib: {output}", "steps": steps}
    steps.append(f"Pushed to my-lib: {private_commit_hash}")

    repo_url = "https://github.com/Pvragon/pvragon-ai-library"
    pr_url = f"{repo_url}/compare/main...{branch_name}?expand=1"

    return {
        "status": "ok",
        "files_graduated": [g.relative_path for g in graduations],
        "team_commit": team_commit_hash,
        "private_commit": private_commit_hash,
        "branch_name": branch_name,
        "pr_url": pr_url,
        "steps": steps,
    }


def main():
    """CLI entry point — thin wrapper around run()."""

    print_header("File Graduation to Team Library")

    if len(sys.argv) < 2:
        print_error("No files specified")
        print(f"\nUsage: {sys.argv[0]} <file1> [file2] ...")
        sys.exit(1)

    file_paths = sys.argv[1:]

    result = run(files=file_paths, dry_run=False, confirm=True)

    if result["status"] == "error":
        print_error(result["error"])
        for err in result.get("errors", []):
            print_error(err)
        sys.exit(1)
    elif result["status"] == "cancelled":
        print_info("Graduation cancelled by user")
        sys.exit(0)

    # Success summary
    print_header("Graduation Complete!")

    print(f"{Colors.GREEN}{len(result['files_graduated'])} file(s) successfully graduated{Colors.RESET}\n")
    print(f"Team library commit:    {Colors.BOLD}{result['team_commit']}{Colors.RESET}")
    print(f"Private library commit: {Colors.BOLD}{result['private_commit']}{Colors.RESET}\n")

    print("Graduated files:")
    for f in result["files_graduated"]:
        print(f"  • {f}")

    print(f"\n{Colors.BOLD}{Colors.GREEN}ACTION REQUIRED: Open Pull Request{Colors.RESET}")
    print(f"🔗 {result['pr_url']}\n")

    print(f"{Colors.GREEN}All team members can now access these files by pulling from team-lib{Colors.RESET}\n")

if __name__ == "__main__":
    main()
