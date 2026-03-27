#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Manages git worktrees for multi-agent session isolation: create, merge, status, and cleanup of per-session worktree branches."
# created: 2026-02-18
# last_updated: 2026-02-25
# maintainer: pvragon
# ---
"""
Manage Git Worktrees for Multi-Agent Isolation.

Creates, merges, inspects, and cleans up per-session git worktrees
so multiple agents can work on the same repo without conflicts.

Usage:
    python3 worktree_manager.py create <repo> <session_id>
    python3 worktree_manager.py merge <repo> <session_id>
    python3 worktree_manager.py status
    python3 worktree_manager.py cleanup
"""
import sys
import subprocess
import os
import argparse
from pathlib import Path
import time
from datetime import datetime, timedelta

def run_git(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"Git command failed: {' '.join(cmd)}")
        print(f"Error: {result.stderr}")
        sys.exit(result.returncode)
    return result.stdout.strip()

def get_repo_path(repo_name):
    """
    Assumes this script is located at <workspace>/<some-lib>/executions/worktree_manager.py
    So workspace root is parent.parent.parent of this script.
    """
    workspace_root = Path(__file__).resolve().parent.parent.parent
    repo_path = workspace_root / repo_name
    if not repo_path.is_dir() or not (repo_path / '.git').exists():
        print(f"Error: Repository '{repo_name}' not found at {repo_path}")
        sys.exit(1)
    return repo_path

def create_worktree(args):
    repo_name = args.repo
    session_id = args.session_id
    repo_path = get_repo_path(repo_name)

    worktree_dir = repo_path / '.worktrees' / session_id
    branch_name = f"wt/{session_id}"

    if worktree_dir.exists():
        print(f"Worktree for session '{session_id}' already exists at {worktree_dir}")
        return

    print(f"Creating worktree at {worktree_dir} on branch {branch_name}...")

    (repo_path / '.worktrees').mkdir(exist_ok=True)

    # Check if branch exists, if yes, just checkout that branch into the worktree, else create it (-b)
    branches = run_git(['git', 'branch', '--list', branch_name], cwd=repo_path)
    if branch_name in branches:
        run_git(['git', 'worktree', 'add', str(worktree_dir), branch_name], cwd=repo_path)
    else:
        run_git(['git', 'worktree', 'add', str(worktree_dir), '-b', branch_name], cwd=repo_path)

    print(f"✅ Worktree created successfully. Path: {worktree_dir}")

def merge_worktree(args):
    repo_name = args.repo
    session_id = args.session_id
    repo_path = get_repo_path(repo_name)

    worktree_dir = repo_path / '.worktrees' / session_id
    branch_name = f"wt/{session_id}"

    if not worktree_dir.exists():
        print(f"Error: Worktree for session '{session_id}' not found at {worktree_dir}")
        sys.exit(1)

    print(f"Validating and merging worktree for session {session_id}...")

    status = run_git(['git', 'status', '--porcelain'], cwd=worktree_dir)
    if status:
        print("Committing uncommitted changes in worktree...")
        run_git(['git', 'add', '.'], cwd=worktree_dir)
        run_git(['git', 'commit', '-m', f'Auto-commit from session {session_id} before merge'], cwd=worktree_dir)

    print(f"Merging {branch_name} into main (fast-forward only)...")

    # Must run the merge from the main repo checkout
    result = subprocess.run(['git', 'merge', '--ff-only', branch_name], cwd=repo_path, text=True, capture_output=True)

    if result.returncode == 0:
        print("✅ Merged cleanly using fast-forward.")
        print("Cleaning up worktree...")
        run_git(['git', 'worktree', 'remove', str(worktree_dir), '--force'], cwd=repo_path)
        run_git(['git', 'branch', '-d', branch_name], cwd=repo_path)
        print("✅ Cleanup complete.")
    else:
        print("⚠️ Merge conflict or fast-forward not possible!")
        print("Error details:")
        print(result.stderr or result.stdout)
        print(f"Leaving worktree {worktree_dir} intact for manual review.")
        sys.exit(result.returncode)

def show_status(args):
    workspace_root = Path(__file__).resolve().parent.parent.parent
    print(f"Checking worktrees in workspace: {workspace_root}\n")

    found_any = False
    for repo_path in workspace_root.iterdir():
        worktrees_dir = repo_path / '.worktrees'
        if repo_path.is_dir() and (repo_path / '.git').exists() and worktrees_dir.exists():
            for wt in worktrees_dir.iterdir():
                if wt.is_dir():
                    found_any = True
                    print(f"Repository: {repo_path.name}")
                    print(f"  Session / Branch: wt/{wt.name}")
                    print(f"  Path: {wt}")

                    try:
                        mtime = wt.stat().st_mtime
                        age = datetime.now() - datetime.fromtimestamp(mtime)
                        uptime = f"{age.days} days, {age.seconds//3600} hours"
                        print(f"  Age: {uptime}")
                    except Exception:
                        pass
                    print()

    if not found_any:
        print("No active worktrees found.")

def cleanup_stale(args):
    workspace_root = Path(__file__).resolve().parent.parent.parent
    print(f"Scanning for stale worktrees (>48h old with no uncommitted changes)...\n")

    cutoff_time = datetime.now() - timedelta(hours=48)

    for repo_path in workspace_root.iterdir():
        worktrees_dir = repo_path / '.worktrees'
        if repo_path.is_dir() and (repo_path / '.git').exists() and worktrees_dir.exists():
            for wt in worktrees_dir.iterdir():
                if not wt.is_dir(): continue

                mtime = datetime.fromtimestamp(wt.stat().st_mtime)
                if mtime < cutoff_time:
                    print(f"Found stale worktree: {wt} (Last modified: {mtime})")
                    status = run_git(['git', 'status', '--porcelain'], cwd=wt)
                    if not status:
                        print(f"  No uncommitted changes. Removing...")
                        run_git(['git', 'worktree', 'remove', str(wt), '--force'], cwd=repo_path)
                        run_git(['git', 'branch', '-D', f"wt/{wt.name}"], cwd=repo_path)
                        print(f"  ✅ Removed.")
                    else:
                        print(f"  ⚠️ Has uncommitted changes. Skipping.")

def main():
    parser = argparse.ArgumentParser(description="Manage Git Worktrees for Multi-Agent Isolation")
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    subparsers.required = True

    create_parser = subparsers.add_parser('create', help='Create a new worktree for a session')
    create_parser.add_argument('repo', help='Repository name (e.g. my-lib)')
    create_parser.add_argument('session_id', help='Unique session identifier')

    merge_parser = subparsers.add_parser('merge', help='Merge worktree back to main and cleanup')
    merge_parser.add_argument('repo', help='Repository name')
    merge_parser.add_argument('session_id', help='Session identifier to merge')

    status_parser = subparsers.add_parser('status', help='List all active worktrees')
    cleanup_parser = subparsers.add_parser('cleanup', help='Remove stale worktrees')

    args = parser.parse_args()

    if args.command == 'create':
        create_worktree(args)
    elif args.command == 'merge':
        merge_worktree(args)
    elif args.command == 'status':
        show_status(args)
    elif args.command == 'cleanup':
        cleanup_stale(args)

if __name__ == '__main__':
    main()
