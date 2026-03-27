---
template: directive
version: 1.0.0
summary: "5-phase procedure for graduating files from my-lib to team-lib: identify, conflict detection, file transfer, git operations, and verification. Follow when a local tool is ready for team-wide use."
created: 2026-01-15
last_updated: 2026-01-15
maintainer: pvragon
---

# Directive: Graduate Files to Team Library

**Purpose:** Safely move mature files from private library (`my-lib`) to shared team library (`team-lib`) with version conflict detection and collision prevention.

---

## When to Use

- You have a context file, directive, skill, or other agent-consumable file that is ready to share with the team
- The file has been tested and validated in your private workflow
- You want to make resources available to all team members via the shared library

---

## File Types Eligible for Graduation

**Allowed:**
- Context files (`context/indexed/`)
- Directives (`directives/`)
- Skills (`skills/`)
- Execution scripts (`executions/`)
- Workflows (`.agent/workflows/`)
- Templates and other shared resources

**Not Allowed (will be blocked):**
- Secrets (`.env`, credentials, tokens)
- Client-specific sensitive data
- Personal preferences
- Temporary/intermediate files (`runtime/`)

---

## Workflow

### Phase 1: Identify & Validate (pre-flight checks)

1. **Identify files to graduate**
   - User specifies file path(s) relative to `my-lib`
   - Supports single file or multiple files in one operation
   - Agent validates files exist and are eligible types

2. **Safety checks**
   - Confirm files are not in exclusion list (secrets, sensitive data)
   - Check files have proper metadata frontmatter
   - Verify files are in committed state (no uncommitted changes)

3. **User confirmation**
   - Show list of files to be graduated
   - Display target paths in team library
   - Ask for explicit confirmation before proceeding

---

### Phase 2: Conflict Detection

For each file being graduated:

1. **Check if file exists in team library**
   - If file doesn't exist → proceed to Phase 3
   - If file exists → compare versions

2. **Version comparison** (if file exists)
   - Extract `version` from YAML frontmatter in both files
   - Compare semantic versions
   - **Decision tree:**
     - **Private version > Team version** → Warn user, allow override
     - **Private version = Team version** → Block and require manual resolution
     - **Private version < Team version** → Block with error, team version is newer

3. **Manual conflict resolution**
   - If blocked, provide options:
     - Rename file in private library and try again
     - Pull team version to private library for review/merge
     - Abort operation

---

### Phase 3: File Transfer

**Using execution script:** `executions/graduate_files.py`

1. **Create target directories** (if they don't exist)
   - Preserve folder structure from private library
   - Example: `context/indexed/pvragon/` → same in team library

2. **Copy files to team library**
   - Copy each file to corresponding location in `team-lib`
   - Preserve file permissions and timestamps

3. **Update registry/index files** (if necessary)
   - Check if graduated file type requires registry update
   - Update `registry/skills.yaml` for skills
   - Update other index files as needed

---

### Phase 4: Git Operations

**In team library (team-lib):**

1. **Stage new files**
   ```bash
   git add <graduated-files>
   ```

2. **Commit with descriptive message**
   ```
   Graduate files from private library
   
   Files graduated:
   - path/to/file1.md
   - path/to/file2.md
   
   Graduated by: [username]
   Date: [YYYY-MM-DD]
   Source: my-lib
   ```

3. **Push to remote**
   ```bash
   git push origin main
   ```

**In private library (my-lib):**

1. **Remove graduated files**
   ```bash
   git rm <graduated-files>
   ```

2. **Commit removal**
   ```
   Graduated files to team library
   
   Files moved to team-lib:
   - path/to/file1.md
   - path/to/file2.md
   
   Team repo commit: [commit-hash]
   ```

3. **Push to remote**
   ```bash
   git push origin main
   ```

---

### Phase 5: Verification

1. **Verify files in team library**
   - Confirm files exist at expected paths
   - Check git commit succeeded
   - Verify remote push completed

2. **Verify removal from private library**
   - Confirm files removed locally
   - Check git commit succeeded
   - Verify remote push completed

3. **Summary report**
   - List all graduated files
   - Show commit hashes in both repos
   - Confirm successful operation

---

## Execution Script

**Script:** `executions/graduate_files.py`

**Usage:**
```bash
python executions/graduate_files.py <file1> <file2> ... <fileN>
```

**Script Responsibilities:**
- Validate file paths and eligibility
- Check for version conflicts
- Create target directories
- Copy files preserving structure
- Update registry files if needed
- Generate git commit messages
- Execute git operations
- Provide detailed logging

**Exit Codes:**
- `0` - Success
- `1` - File validation failed
- `2` - Version conflict detected (manual resolution required)
- `3` - Git operation failed
- `4` - User aborted operation

---

## Example Workflow

**Scenario:** Graduate three context files created tonight

```bash
# User request
"Graduate these files to team library:
- context/indexed/pvragon/pvragon-business-overview.md
- context/indexed/example-company/example-business-overview.md
- context/indexed/example-company/example-operations-platform.md"

# Agent executes
python executions/graduate_files.py \
  context/indexed/pvragon/pvragon-business-overview.md \
  context/indexed/example-company/example-business-overview.md \
  context/indexed/example-company/example-operations-platform.md

# Script output
✓ Validated 3 files
✓ No conflicts detected
✓ Created directory: team-lib/context/indexed/pvragon/
✓ Created directory: team-lib/context/indexed/example-company/
✓ Copied 3 files to team library
✓ Committed to team library: a1b2c3d
✓ Pushed to remote: team-lib
✓ Removed 3 files from private library
✓ Committed to private library: e4f5g6h
✓ Pushed to remote: my-lib

Files successfully graduated!
```

---

## Error Handling

### Version Conflict
```
ERROR: Version conflict detected

File: context/indexed/pvragon/pvragon-business-overview.md
- Private version: 1.0.0
- Team version: 1.2.0

Team library has a newer version. Options:
1. Pull team version to review and merge
2. Rename your file to avoid collision
3. Abort operation

What would you like to do?
```

### Missing Metadata
```
ERROR: File missing required metadata

File: context/indexed/example.md

This file is missing YAML frontmatter with version information.
Please add metadata before graduating to team library.

See AGENTS.md for metadata standards.
```

### Uncommitted Changes
```
ERROR: Uncommitted changes detected

File: context/indexed/example.md

This file has uncommitted changes in your private library.
Please commit changes before graduating.

Run: git add <file> && git commit -m "..."
```

---

## Safety Principles

1. **Never overwrite without confirmation** - If team library has the file, require explicit user action
2. **Version awareness** - Block graduation if team version is newer
3. **Preserve structure** - Maintain exact folder hierarchy across libraries
4. **Atomic operations** - If any file fails validation, abort entire operation
5. **Clean commits** - Separate commits for each library with clear documentation
6. **Verification** - Always verify successful completion before reporting success

---

## Post-Graduation

**For the user who graduated:**
- Files are removed from your private library
- They are now available in team library
- Any updates should be made in team library and pulled to private

**For other team members:**
- Run `git pull` in `team-lib` to access new files
- Files are immediately available for use in their workflows

---

## Related Directives

- *[Future]* Roll back graduated files
- *[Future]* Sync updates from team library to private library
- *[Future]* Propose graduated file for official inclusion (with approval workflow)

---

## Notes

- Graduation is a one-way operation (source file is removed)
- For rollback, use separate directive
- Always have committed work before graduating
- Team library should be considered "production" - test files thoroughly in private library first
