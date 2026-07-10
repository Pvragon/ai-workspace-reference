#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Posts a ClickUp task comment with @mentions resolved to real structured tags. Wraps Restish for the API call."
# created: 2026-03-19
# last_updated: 2026-03-19
# maintainer: pvragon
# ---
"""
Post a ClickUp task comment with @mentions.

Parses @Name references in the message body, resolves them against workspace
members (case-insensitive), and posts a structured comment with real ClickUp
mention tags that trigger notifications.

Usage:
    python3 clickup_mention_comment.py --task TASK_ID --message "Hey @Jane Smith check this out"
    python3 clickup_mention_comment.py --task TASK_ID --message "@Sam Lee @Alex Kim ready for review"

Requires:
    - restish CLI configured with clickup-v2 API (see ~/.config/restish/apis.json)
    - CLICKUP_API_TOKEN in environment or ~/ai-workspace/personal/secrets/.env
"""

import os
import sys
import re
import json
import argparse
import subprocess
import requests
from dotenv import load_dotenv

WORKSPACE_ID = "YOUR_WORKSPACE_ID"

def get_token():
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("Error: CLICKUP_API_TOKEN not set.")
        sys.exit(1)
    return token

def fetch_members():
    """Fetch all workspace members and return as list of {id, username, email}."""
    url = f"https://api.clickup.com/api/v2/team/{WORKSPACE_ID}"
    resp = requests.get(url, headers={"Authorization": get_token()}, timeout=10)
    if not resp.ok:
        print(f"Error fetching members: {resp.text}")
        sys.exit(1)
    members = []
    for m in resp.json().get("team", {}).get("members", []):
        u = m.get("user", {})
        members.append({
            "id": u.get("id"),
            "username": u.get("username") or "",
            "email": u.get("email") or ""
        })
    return members

def resolve_mentions(message, members):
    """Parse @Name references and build the structured comment array.

    Returns (comment_array, resolved_names).
    Matching is case-insensitive. Tries longest match first to handle
    multi-word names like "@Sam Lee" before "@Dana".
    """
    # Sort members by username length descending so longer names match first
    sorted_members = sorted(members, key=lambda m: len(m["username"]), reverse=True)

    # Build a mapping of lowercase name -> member
    name_map = {}
    for m in sorted_members:
        if m["username"]:
            name_map[m["username"].lower()] = m

    # Find all @mentions using a greedy approach
    # Pattern: @ followed by words (including accented chars) until we stop matching a known name
    mentions_found = []
    i = 0
    while i < len(message):
        if message[i] == '@':
            # Try to match against known usernames, longest first
            matched = None
            for name_lower, member in name_map.items():
                candidate = message[i+1:i+1+len(member["username"])]
                if candidate.lower() == name_lower:
                    # Check that the next char after the name is a word boundary
                    end_pos = i + 1 + len(member["username"])
                    if end_pos >= len(message) or not message[end_pos].isalpha():
                        matched = (i, end_pos, member)
                        break
            if matched:
                mentions_found.append(matched)
                i = matched[1]
                continue
        i += 1

    if not mentions_found:
        return [{"text": message}], []

    # Build the structured comment array
    comment = []
    resolved = []
    last_end = 0
    for start, end, member in sorted(mentions_found, key=lambda x: x[0]):
        # Add text before this mention
        if start > last_end:
            comment.append({"text": message[last_end:start]})
        # Add the mention tag
        comment.append({"type": "tag", "user": {"id": member["id"]}})
        resolved.append(member["username"])
        last_end = end

    # Add any trailing text
    if last_end < len(message):
        comment.append({"text": message[last_end:]})

    return comment, resolved

def post_comment(task_id, comment_array):
    """Post the structured comment via Restish."""
    payload = json.dumps({"comment": comment_array})
    result = subprocess.run(
        ["restish", "post", f"clickup-v2/task/{task_id}/comment"],
        input=payload,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error posting comment: {result.stderr}")
        sys.exit(1)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def run(task_id, message):
    """Main entry point for programmatic use."""
    members = fetch_members()
    comment_array, resolved = resolve_mentions(message, members)

    if resolved:
        print(f"Mentioning: {', '.join(resolved)}")
    else:
        print("No @mentions resolved (posting as plain text)")

    result = post_comment(task_id, comment_array)
    comment_id = result.get("id", "unknown")
    print(f"Comment posted to task {task_id} (comment ID: {comment_id})")
    return result

def main():
    load_dotenv(os.path.expanduser("~/ai-workspace/personal/secrets/.env"))

    parser = argparse.ArgumentParser(description="Post a ClickUp comment with @mentions")
    parser.add_argument("--task", required=True, help="ClickUp task ID")
    parser.add_argument("--message", required=True, help='Comment body with @Name mentions')
    args = parser.parse_args()

    run(args.task, args.message)

if __name__ == "__main__":
    main()
