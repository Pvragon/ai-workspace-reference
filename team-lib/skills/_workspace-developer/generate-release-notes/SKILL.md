---
name: generate-release-notes
description: Automate team release notes by analyzing git history and changelogs.
summary: "Generates release notes from git history and CHANGELOG.md. Supports --since, --last-run, and --finalize flags. Run during the workspace release process."
version: 1.0.0
created: 2026-01-24
last_updated: 2026-01-24
maintainer: pvragon
---

# Generate Release Notes

This skill automates the creation of team update communications. It analyzes the git history of the workspace provided a time window and extracts key changes to draft a "Release Notes" document.

## Capability
- **Changed-Aware**: Parses `CHANGELOG.md` to extract the correct Version and Human-Curated Summary.
- **Git Analysis**: Scans `team-lib` (and optionally other roots) for commits to append as detailed history.
- **Smart Windowing**:
    - `--since [DATE]`: Strict start date.
    - `--last-run`: Automatically finds the last *meaningful* run (ignoring recent iterative testing < 24h ago).
- **Output**: Generates a Draft Markdown file in `my-lib/runtime/.tmp/` populated with the content from CHANGELOG.
- **Finalization**: Promotes draft from `.tmp` to `deliverables/`.


## Usage

```bash
# 1. Generate notes since a specific date
python3 team-lib/skills/_workspace-developer/generate-release-notes/generate_release_notes.py --since "2026-01-17"

# 2. Generate notes since the last official release (Smart Mode)
python3 team-lib/skills/_workspace-developer/generate-release-notes/generate_release_notes.py --last-run

# 3. Finalize a draft (Move to deliverables)
python3 team-lib/skills/_workspace-developer/generate-release-notes/generate_release_notes.py --finalize my-lib/runtime/.tmp/YYMMDD-release-notes-draft-vX.Y.Z.md
```

## How it Works
1.  **Date Resolution**:
    - Calculates the start date based on arguments.
    - If `--last-run` is used, it checks `my-lib/runtime/logs/release-notes-history.json`.
    - It skips any runs that occurred within 24 hours of the *current* time, stepping back until it finds a run > 24h ago (or defaults to 7 days).
2.  **Extraction**: Runs `git log` with the date range.
3.  **Drafting**: Creates a formatted markdown file.

## Artifacts
- **Draft**: `my-lib/runtime/.tmp/YYMMDD-release-notes-draft-v[Version].md`
- **History**: `my-lib/runtime/logs/release-notes-history.json` (Updated on success)
