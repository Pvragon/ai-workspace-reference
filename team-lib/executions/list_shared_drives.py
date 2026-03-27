#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Lists all Google Workspace Shared Drives and their root-level contents using OAuth credentials from the Google Workspace MCP server."
# created: 2026-02-25
# last_updated: 2026-02-25
# maintainer: pvragon
# ---
"""
List all Google Workspace Shared Drives and their root-level contents.

Reuses the OAuth credentials from the Google Workspace MCP server
stored at ~/.google_workspace_mcp/credentials/{email}.json.

Usage:
    python list_shared_drives.py [--email EMAIL] [--depth DEPTH] [--json]

Outputs:
    Drive ID, name, and root-level folder structure for each shared drive.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDS_DIR = Path.home() / ".google_workspace_mcp" / "credentials"
DEFAULT_EMAIL = "user@example.com"


def load_credentials(email: str) -> Credentials:
    creds_file = CREDS_DIR / f"{email}.json"
    if not creds_file.exists():
        raise FileNotFoundError(f"No credentials found at {creds_file}")

    with open(creds_file) as f:
        creds_data = json.load(f)

    expiry = None
    if creds_data.get("expiry"):
        expiry = datetime.fromisoformat(creds_data["expiry"])
        if expiry.tzinfo is not None:
            expiry = expiry.replace(tzinfo=None)

    credentials = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes"),
        expiry=expiry,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        creds_data["token"] = credentials.token
        creds_data["expiry"] = credentials.expiry.isoformat() if credentials.expiry else None
        with open(creds_file, "w") as f:
            json.dump(creds_data, f, indent=2)

    return credentials


def list_shared_drives(service):
    drives = []
    page_token = None
    while True:
        resp = service.drives().list(
            pageSize=100,
            pageToken=page_token,
            fields="nextPageToken, drives(id, name, createdTime)"
        ).execute()
        drives.extend(resp.get("drives", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return drives


def list_drive_root(service, drive_id, depth=1, current_depth=0):
    """List items in a shared drive folder, optionally recursing into subfolders."""
    items = []
    page_token = None
    parent_id = drive_id if current_depth == 0 else drive_id

    while True:
        resp = service.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            driveId=drive_id if current_depth == 0 else None,
            corpora="drive" if current_depth == 0 else "allDrives",
            pageSize=100,
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if current_depth < depth - 1:
        for item in items:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                item["children"] = list_folder_contents(
                    service, drive_id, item["id"], depth, current_depth + 1
                )

    return items


def list_folder_contents(service, drive_id, folder_id, depth, current_depth):
    items = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=100,
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    if current_depth < depth - 1:
        for item in items:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                item["children"] = list_folder_contents(
                    service, drive_id, item["id"], depth, current_depth + 1
                )

    return items


def format_item(item, indent=0):
    prefix = "  " * indent
    icon = "📁" if item["mimeType"] == "application/vnd.google-apps.folder" else "📄"
    line = f"{prefix}{icon} {item['name']} (ID: {item['id']})"
    lines = [line]
    if "children" in item:
        for child in sorted(item["children"], key=lambda x: (
            0 if x["mimeType"] == "application/vnd.google-apps.folder" else 1,
            x["name"]
        )):
            lines.extend(format_item(child, indent + 1))
    return lines


def run(email=DEFAULT_EMAIL, depth=1, as_json=False):
    credentials = load_credentials(email)
    service = build("drive", "v3", credentials=credentials)

    drives = list_shared_drives(service)

    if as_json:
        result = []
        for drive in sorted(drives, key=lambda d: d["name"]):
            root_items = list_drive_root(service, drive["id"], depth=depth)
            result.append({
                "drive_id": drive["id"],
                "name": drive["name"],
                "created": drive.get("createdTime"),
                "root_items": root_items,
            })
        print(json.dumps(result, indent=2))
        return result
    else:
        all_lines = []
        for drive in sorted(drives, key=lambda d: d["name"]):
            all_lines.append(f"\n🗂️  {drive['name']} (Drive ID: {drive['id']})")
            all_lines.append(f"   Created: {drive.get('createdTime', 'unknown')}")
            root_items = list_drive_root(service, drive["id"], depth=depth)
            if not root_items:
                all_lines.append("   (empty)")
            else:
                for item in sorted(root_items, key=lambda x: (
                    0 if x["mimeType"] == "application/vnd.google-apps.folder" else 1,
                    x["name"]
                )):
                    all_lines.extend(format_item(item, indent=1))
        output = "\n".join(all_lines)
        print(output)
        return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List Google Workspace Shared Drives")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--depth", type=int, default=1, help="Folder depth to explore (1=root only)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    run(email=args.email, depth=args.depth, as_json=args.json)
