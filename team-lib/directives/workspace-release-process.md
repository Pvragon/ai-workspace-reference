---
template: directive
version: 1.3.0
summary: "End-to-end workspace release workflow: validation, git commits, CHANGELOG updates, release notes, and GitHub release creation. Follow when cutting a new workspace release."
created: 2026-01-26
last_updated: 2026-02-07
maintainer: pvragon
tags: [release, git, workspace-validation, deployment, github-releases]
---

# Workspace Release Process

Complete workflow for releasing AI workspace changes: validation, git commits, CHANGELOG updates, and release notes.

## When to Use This Directive

Execute this process **before distributing AI workspace changes** to ensure quality and communication.

**AI Workspace changes include:**
- Modifications to `team-lib/`
- New root-level directories in `my-lib/` or `personal/`
- Changes affecting workspace structure or agent behavior

## User Triggers

**Run this directive when the user asks to:**
- "Release the workspace"
- "Prepare a release"

## Prerequisites

- Changes complete and ready for release
- Git push access to affected repositories
- All files saved

---

## Step 1: Workspace Consistency Validation

**Goal:** Ensure all workspace structure files are in sync.

### Execute the check-workspace-consistency skill

Follow: `team-lib/skills/_workspace-developer/check-workspace-consistency/SKILL.md`

The skill will guide you through:
- Three verification passes (automated, documentation, deep scan)
- Fixing any inconsistencies
- Running `validate.sh`

### Checkpoint

- [ ] Consistency check skill completed
- [ ] `validate.sh` passes cleanly
- [ ] No structural discrepancies remain

**Do not proceed until checkpoint passes.**

---

## Step 2: Commit All Changes

**Goal:** Capture all changes in git with meaningful commit messages.

### For each repository with changes (team-lib, my-lib):

1. Review changes:
   ```bash
   cd ~/ai-workspace/[repo-name]
   git status
   git diff
   ```

2. Stage and commit with clear message:
   ```bash
   git add .
   git commit -m "[Category] Brief description

   - Detailed change 1
   - Detailed change 2"
   ```

**Commit categories:** `[Feature]`, `[Fix]`, `[Docs]`, `[Refactor]`, `[Chore]`, `[Breaking]`

### Checkpoint

- [ ] All changes committed
- [ ] Commit messages are clear
- [ ] `git status` shows clean working tree

---

## Step 3: Push to GitHub

Push each repository:

```bash
cd ~/ai-workspace/team-lib
git push origin main

cd ~/ai-workspace/my-lib  # if applicable
git push origin main
```

### Checkpoint

- [ ] Push completed without errors
- [ ] GitHub shows latest commits

**If push fails:** Pull, resolve conflicts, re-push.

---

## Step 4: Sync CHANGELOG.md with Git History

**Goal:** Ensure CHANGELOG.md reflects all committed changes.

### Compare git history to CHANGELOG

```bash
cd ~/ai-workspace/team-lib
git log --oneline -20  # Review recent commits
```

Open `CHANGELOG.md` and verify:
- [ ] All significant changes documented
- [ ] Changes categorized (Added/Changed/Fixed/Removed)
- [ ] Version number incremented (semver)
- [ ] Date is current

### If CHANGELOG is missing changes:

1. Add new version section:
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD

   ### Added
   - New capabilities

   ### Changed
   - Modified behavior
   ```

2. Commit and push:
   ```bash
   git add CHANGELOG.md
   git commit -m "[Docs] Update CHANGELOG for vX.Y.Z"
   git push origin main
   ```

### Checkpoint

- [ ] CHANGELOG current with git history
- [ ] Version incremented appropriately
- [ ] CHANGELOG committed and pushed (if updated)

---

## Step 5: Generate Release Notes

**Goal:** Create team-facing release notes.

### Execute the generate-release-notes skill

Follow instructions in: `team-lib/skills/_workspace-developer/generate-release-notes/SKILL.md`

1. **Generate Draft**: Run skill (recommend `--last-run`).
2. **Review Draft**: meaningful context, breaking changes, migration steps.
3. **Finalize**: Run skill with `--finalize` to publish to `deliverables/`.

### Checkpoint

- [ ] Release notes generated
- [ ] Draft reviewed and enhanced
- [ ] Final release notes file ready in deliverables/

---

## Step 6: Publish GitHub Release

**Goal:** Make release visible on GitHub with generated release notes.

### Run the publish script

```bash
cd ~/ai-workspace/team-lib
python3 executions/publish_github_release.py \
  --version vX.Y.Z \
  --notes-file ~/ai-workspace/my-lib/runtime/deliverables/YYMMDD-ai-workspace-release-notes-vX.Y.Z.md
```

The script will:
1. Create an annotated git tag
2. Push the tag to origin
3. Publish a GitHub release with the release notes

**Dry-run mode:** Add `--dry-run` to preview without making changes.

### Checkpoint

- [ ] Tag created and pushed
- [ ] GitHub release published
- [ ] Release notes visible at: https://github.com/Pvragon/pvragon-ai-library/releases

---

## Final Checklist

**Validation:**
- [ ] Workspace consistency validated
- [ ] `validate.sh` passes

**Git:**
- [ ] All changes committed and pushed
- [ ] No uncommitted changes remain

**Documentation:**
- [ ] CHANGELOG.md current and accurate
- [ ] Version incremented
- [ ] Release notes finalized

**GitHub Release:**
- [ ] Tag created: `vX.Y.Z`
- [ ] GitHub release published with release notes

**Output:**
- [ ] Release notes file: `my-lib/runtime/deliverables/YYMMDD-release-notes-v[Version].md`
- [ ] GitHub release: https://github.com/Pvragon/pvragon-ai-library/releases/tag/vX.Y.Z

---

## Troubleshooting

**Consistency check fails:**
- Review reported file in error
- Propagate changes through all affected files
- Verify YAML syntax
- Re-run validation

**Git push rejected:**
- `git pull origin main --rebase`
- Resolve conflicts
- Re-validate workspace
- Push again

**CHANGELOG out of sync:**
- Review `git log` for unreported changes
- Focus on impact: breaking > features > fixes
- Update and re-commit

**GitHub release already exists:**
- Delete existing release: `gh release delete vX.Y.Z --yes`
- Re-run the publish script

**Tag already exists:**
- If local only: `git tag -d vX.Y.Z` then re-run
- If on remote: coordinate with team before force-pushing

---

## Version History

- **v1.3.0** (2026-02-07): Added Step 6 for GitHub releases with `publish_github_release.py` script
- **v1.2.0** (2026-01-26): Added "User Triggers" section to map intent to action (DOE Framework)
- **v1.1.0** (2026-01-26): Streamlined to high-level orchestration, removed redundant details
- **v1.0.0** (2026-01-26): Initial directive created

