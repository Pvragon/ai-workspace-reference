---
name: update-bashrc
description: Add aliases, functions, or env vars to ~/.bashrc with section-aware placement
summary: "Procedure for adding aliases, functions, or env vars to ~/.bashrc with section-aware placement and verification. Follow when modifying shell configuration."
version: 1.1.0
created: 2026-01-23
last_updated: 2026-01-23
maintainer: username
---

# Update Bashrc

Add configuration to the user's bashrc while maintaining section organization and keeping the backup copy synchronized.

## File Locations

| File | Purpose |
|------|---------|
| `~/.bashrc` | **Active config** — loaded by bash on each new terminal |
| `~/ai-workspace/my-lib/config/linux/bash/bashrc_master` | **Backup/master copy** — version-controlled reference |

## Section Map

The bashrc is organized into sections marked by header comments. Insert new content at the **end of the appropriate section**, just before the next section header.

| Section Header | What goes here |
|----------------|----------------|
| `# 1. SYSTEM & SHELL BEHAVIOR` | Shell options, history settings, shopt |
| `# 2. PROMPT & COLOR SUPPORT` | PS1 prompt, colors, dircolors |
| `# 3. GLOBAL ENVIRONMENTAL VARIABLES` | Exports, PATH additions, API keys |
| `# 4. ALIASES & FUNCTIONS` | All aliases and shell functions |
| `# 5. EXTERNAL COMPLETIONS & HOOKS` | Sourcing other files, eval hooks, completions |

## Procedure

### 1. Determine the correct section
- Alias → Section 4
- Environment variable / export → Section 3
- Shell function → Section 4
- Completion or hook → Section 5

### 2. Find insertion point
Search for the *next* section header and insert just above it:
```bash
# To add to section 4, find "# 5. EXTERNAL" and insert above it
grep -n "# 5. EXTERNAL" ~/.bashrc
```

### 3. Insert content in both files
Add the new content (with a descriptive comment) at the identified location in:
- `~/.bashrc`
- `~/ai-workspace/my-lib/config/linux/bash/bashrc_master`

### 4. Apply changes
```bash
source ~/.bashrc
```

## Verification Checklist

After making changes, confirm:

### 1. Content is in the correct section
```bash
# Show context around the change (adjust line numbers as needed)
grep -B2 -A2 "your_new_alias" ~/.bashrc
```
Verify the surrounding content belongs to the expected section.

### 2. Both files are in sync
```bash
diff ~/.bashrc ~/ai-workspace/my-lib/config/linux/bash/bashrc_master
```
Should return no output (files identical).

### 3. Alias/function is active
```bash
type aliasname   # Shows definition if active
# Or test the command directly
```

### 4. (Optional) Commit backup to git
```bash
cd ~/ai-workspace/my-lib
git add config/linux/bash/bashrc_master
git commit -m "Add [name] to bashrc section [N]"
```

## Notes

- Always add a comment line above new entries explaining what they do
- Keep both files in sync — if you edit one, edit the other
- The `bashrc_master` file is the source of truth for restoration
- Never append blindly to end of file — use the section map
