---
template: skill-definition
version: 1.1.0
summary: "Refreshes the Google Drive index at team-lib/context/indexed/pvragon-google-drive-index.md by enumerating all Shared Drives and their root-level contents via the Google Drive API. Run periodically or when drives/folders are reorganized."
created: 2026-02-25
last_updated: 2026-03-03
maintainer: pvragon
---

# Skill: Update Drive Index

## Purpose

Refresh `team-lib/context/indexed/pvragon-google-drive-index.md` with the current state of all Shared Drives in the pvragon.com Google Workspace. This ensures agents always have accurate Drive IDs, folder structures, and routing rules.

## When to Run

- After creating or renaming a Shared Drive
- After significant folder reorganization within a drive
- Periodically (monthly) to catch drift
- When an agent encounters a "Shared drive not found" or similar error

## Prerequisites

- **Python environment**: `my-lib/.venv` with Google API packages installed. If missing, run `team-lib/_admin/setup_workspace.sh` — it creates the venv and installs all required packages automatically.
- **MCP OAuth credentials** at `~/.google_workspace_mcp/credentials/user@example.com.json`

## Procedure

### Step 1: Run the enumeration script

```bash
~/ai-workspace/my-lib/.venv/bin/python ~/ai-workspace/team-lib/executions/list_shared_drives.py --depth 1
```

This outputs all Shared Drives with their IDs and root-level folder contents.

For JSON output (easier to parse programmatically):

```bash
~/ai-workspace/my-lib/.venv/bin/python ~/ai-workspace/team-lib/executions/list_shared_drives.py --depth 1 --json
```

### Step 2: Review the output

Compare the script output against the current `google-drive-index.md`:

- **New drives**: Add a new section with Drive ID, purpose, and folder table
- **Removed drives**: Remove the section (or mark as archived)
- **New/renamed/removed folders**: Update the folder tables
- **New key documents**: Add to the Key Documents section if frequently referenced

### Step 3: Update the index file

Edit `team-lib/context/indexed/pvragon-google-drive-index.md`:

1. Update the `last_updated` field in frontmatter
2. Bump the `version` (patch for folder changes, minor for new drives)
3. Update the relevant Shared Drive sections
4. Verify routing rules still make sense
5. Update the cleanup section if issues have been resolved

### Step 4: Update the context index

If any drives were added or removed, update `team-lib/context/indexed/index.md` to reflect the new drive count in the summary.

## Notes

- The script reuses OAuth credentials from the Google Workspace MCP server — no separate auth setup needed
- The `--depth` flag controls how deep into subfolders the script explores (1 = root only, 2 = one level of subfolders, etc.)
- Scope: pvragon.com business drives only. Do not add personal folders.
- The script does NOT modify the index file directly — an agent reviews and applies changes to preserve routing rules, key documents, and cleanup notes that aren't auto-discoverable
