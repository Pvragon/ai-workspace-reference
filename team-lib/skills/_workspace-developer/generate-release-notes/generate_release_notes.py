#!/usr/bin/env python3
import argparse
import subprocess
import os
import shutil
import json
import datetime
import re
from pathlib import Path

# Configuration
WORKSPACE_ROOT = os.path.expanduser("~/ai-workspace")
MY_LIB_DIR = os.path.join(WORKSPACE_ROOT, "my-lib")
TEAM_LIB_DIR = os.path.join(WORKSPACE_ROOT, "team-lib")
HISTORY_FILE = os.path.join(MY_LIB_DIR, "runtime/logs/release-notes-history.json")
DRAFTS_DIR = os.path.join(MY_LIB_DIR, "runtime/.tmp")
DELIVERABLES_DIR = os.path.join(MY_LIB_DIR, "runtime/deliverables")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def get_smart_last_run(history):
    """
    Finds the last *meaningful* run.
    Logic: Skip any runs that happened within 2 hours of NOW (to avoid iterative testing).
    If multiple runs exist >2h ago, pick the most recent of those.
    """
    if not history:
        return None

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(hours=2)

    # Sort history by date descending
    sorted_history = sorted(history, key=lambda x: x['date'], reverse=True)

    for entry in sorted_history:
        entry_date = datetime.datetime.fromisoformat(entry['date'])
        if entry_date < cutoff:
            # Use the since_date from that entry as our new start (day after)
            prev_since = entry.get('since_date')
            if prev_since:
                # Start from the day after the previous period ended
                return entry_date.strftime("%Y-%m-%d")
            return entry_date.strftime("%Y-%m-%d")

    return None

def get_git_log(since_date, repo_path):
    cmd = [
        "git", "-C", repo_path, "log",
        f"--since={since_date}",
        "--pretty=format:%ad - %s",
        "--date=short"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error reading git log: {e}"

def parse_changelog():
    """
    Parses team-lib/CHANGELOG.md to extract the latest version and its description body.
    Returns: (version, summary_text)
    """
    changelog_path = os.path.join(TEAM_LIB_DIR, "CHANGELOG.md")
    if not os.path.exists(changelog_path):
        print(f"Warning: CHANGELOG.md not found at {changelog_path}")
        return ("Unknown", "(No CHANGELOG found)")

    try:
        with open(changelog_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Warning: Could not read CHANGELOG: {e}")
        return ("Unknown", "(Error reading CHANGELOG)")

    version = "Unknown"
    summary_lines = []
    capture = False

    # Regex to match version headers like "## [1.2.5] - 2026-01-30"
    version_pattern = re.compile(r"^## \[(?P<ver>\d+\.\d+\.\d+)\] -")

    for line in lines:
        match = version_pattern.match(line)
        if match:
            if not capture:
                # Found our first (latest) version
                version = match.group("ver")
                capture = True
                continue # Skip the header line itself
            else:
                # Found the NEXT version header, stop capturing
                break

        if capture:
            summary_lines.append(line)

    # Clean up the summary (remove leading/trailing whitespace from the block)
    summary_text = "".join(summary_lines).strip()

    if not summary_text:
        summary_text = "(No summary found for this version in CHANGELOG)"

    return (version, summary_text)

def generate_notes(since_date):
    print(f"Generating notes since: {since_date}")

    # 1. Get Version & Summary from CHANGELOG
    version, changelog_summary = parse_changelog()
    print(f"Detected latest version from CHANGELOG: {version}")

    if changelog_summary:
        print("-" * 40)
        print("Found the following summary in CHANGELOG:")
        print(changelog_summary)
        print("-" * 40)
        print("Using this as the formatted summary.")
    else:
        print("Warning: No summary found in CHANGELOG for this version.")

    # 2. Analyze team-lib git log
    team_log = get_git_log(since_date, TEAM_LIB_DIR)

    # 3. Generate content
    today_obj = datetime.datetime.now()
    today_str = today_obj.strftime("%Y-%m-%d")
    file_prefix = today_obj.strftime("%y%m%d")

    output_filename = f"{file_prefix}-ai-workspace-release-notes-draft-v{version}.md"
    output_path = os.path.join(DRAFTS_DIR, output_filename)

    content = f"""---
version: {version}
created: {today_str}
type: release-notes
---

# AI Workspace Release Notes v{version} ({today_str})

**Period**: {since_date} to {today_str}

## Summary of Changes
{changelog_summary}

## Detailed Commit Log (team-lib)
```text
{team_log}
```
"""

    os.makedirs(DRAFTS_DIR, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)

    print(f"Draft generated: {output_path}")

    # Update History
    history = load_history()
    history.append({
        "date": datetime.datetime.now().isoformat(),
        "since_date": since_date,
        "output_file": output_path
    })
    save_history(history)

def finalize_notes(draft_path):
    if not os.path.exists(draft_path):
        print(f"Error: Draft file not found at {draft_path}")
        return

    filename = os.path.basename(draft_path)

    # Check if filename matches expected draft pattern: YYMMDD-ai-workspace-release-notes-draft-vX.Y.Z.md
    # We want to transform it to: YYMMDD-ai-workspace-release-notes-vX.Y.Z.md

    if "-draft-" in filename:
        final_filename = filename.replace("-draft-", "-")
    elif "-draft." in filename: # Handling edge case usage at end of file
         final_filename = filename.replace("-draft.", ".")
    else:
        # If manual naming didn't follow draft pattern, just ensure prefix is okay.
        print(f"Warning: Filename {filename} does not contain '-draft-'. Moving as is.")
        final_filename = filename

    # Verify YYMMDD prefix
    if not re.match(r"^\d{6}-", final_filename):
         print(f"Warning: Filename {final_filename} does not match YYMMDD pattern.")

    final_path = os.path.join(DELIVERABLES_DIR, final_filename)

    os.makedirs(DELIVERABLES_DIR, exist_ok=True)
    shutil.move(draft_path, final_path)

    print(f"Success: Release notes finalized at {final_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate Release Notes")
    parser.add_argument("--since", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--last-run", action="store_true", help="Use smart last run logic")
    parser.add_argument("--finalize", help="Finalize a draft file (provide path)")

    args = parser.parse_args()

    if args.finalize:
        finalize_notes(args.finalize)
        return

    since_date = None

    if args.since:
        since_date = args.since
    elif args.last_run:
        history = load_history()
        since_date = get_smart_last_run(history)
        if not since_date:
            # Default to 7 days if no valid history found
            print("No valid previous run found > 24h ago. Defaulting to 7 days.")
            since_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        # Default behavior if nothing specified (e.g. 7 days?)
        print("No arguments provided. Using default 7 days.")
        since_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

    generate_notes(since_date)

if __name__ == "__main__":
    main()
