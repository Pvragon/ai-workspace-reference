---
name: check-workspace-consistency
description: Rigorously validate all files referencing workspace structure are in sync
summary: "Three-pass validation protocol ensuring all workspace files (templates, docs, registry) are mutually consistent. Run before releases or after structural changes."
version: 1.1.0
created: 2026-01-23
last_updated: 2026-01-23
maintainer: pvragon
---

# Workspace Consistency Validation

Rigorously validate that ALL files referencing the workspace structure stay in sync.

> [!CAUTION]
> **Multi-Pass Required**: Historical experience shows consistency issues are often missed on the first pass. This skill enforces THREE verification passes before declaring success.

## When to Use This Skill

Run this validation **after any change** to:
- Directory structure (adding/removing/renaming folders)
- Any script, index, registry, or documentation file

---

## Complete File Inventory

### Tier 1: Primary Structure Files (MUST check every time)

| File | What to Check |
|------|---------------|
| `_admin/setup_workspace.sh` | `ensure_dir` calls match all directories |
| `_admin/validate.sh` | `check_dir` calls match setup script |
| `context/indexed/workspace-reference.md` | Section 5 directory map + section 4.x descriptions |
| `_admin/GETTING_STARTED.md` | Folder references, setup instructions |
| `README.md` | Directory structure diagram |

### Tier 2: Registry & Manifest Files (Check for path references)

| File | What to Check |
|------|---------------|
| `_admin/workspace-manifest.yaml` | `key_subdirs` sections match actual structure |
| `registry/workspace.yaml` | Path references |
| `registry/skills.yaml` | Skill paths |
| `registry/directives.yaml` | Directive paths |
| `registry/personas.yaml` | Persona paths |
| `registry/context-packs.yaml` | Context paths |

### Tier 3: Index Files (Check for outdated subdirectory lists)

| File | What to Check |
|------|---------------|
| `_admin/index.md` | Subdirectory descriptions |
| `context/index.md` | Subdirectory descriptions |
| `context/global/index.md` | Contents list |
| `context/indexed/index.md` | Contents list |
| `directives/index.md` | Contents list |
| `executions/index.md` | Contents list |
| `harnesses/index.md` | Contents list |
| `logs/index.md` | Contents list |
| `personas/index.md` | Contents list |
| `registry/index.md` | Contents list |
| `skills/index.md` | Contents list |

### Tier 4: Governance & Templates (Check for structural assumptions)

| File | What to Check |
|------|---------------|
| `directives/team-library-governance.md` | Path references |
| `directives/workspace-validation.md` | Validation instructions |
| `context/global/template-agent-*.md` | Path references in templates |
| `_admin/tests/test_setup_workspace.sh` | Test assertions match setup |

---

## Three-Pass Verification Protocol

> [!IMPORTANT]
> You MUST complete all three passes. Do not skip ahead.

### Pass 1: Automated Extraction

Run these commands and capture output:

```bash
# 1. Directories from setup script
grep -oP 'ensure_dir "\K[^"]+' ~/ai-workspace/team-lib/_admin/setup_workspace.sh | \
  sed 's|\${WORKSPACE_ROOT}/||' | sort -u > /tmp/setup_dirs.txt

# 2. Directories from validate script
grep -oP 'check_dir "\K[^"]+' ~/ai-workspace/team-lib/_admin/validate.sh | \
  sort -u > /tmp/validate_dirs.txt

# 3. Compare for discrepancies
echo "=== Missing from validate.sh ===" && comm -23 /tmp/setup_dirs.txt /tmp/validate_dirs.txt
echo "=== Orphaned in validate.sh ===" && comm -13 /tmp/setup_dirs.txt /tmp/validate_dirs.txt
```

**Fix any discrepancies before proceeding.**

### Pass 2: Documentation Review

Open and manually inspect each Tier 1 file:

- [ ] `workspace-reference.md` section 5 matches setup_dirs.txt
- [ ] `workspace-reference.md` section 4.x descriptions cover all directories
- [ ] `GETTING_STARTED.md` folder references are current
- [ ] `README.md` structure diagram is current

**Fix any discrepancies before proceeding.**

### Pass 3: Deep Scan

Search for any file referencing specific paths:

```bash
# Check for hardcoded paths that might be stale
grep -r "my-lib/" ~/ai-workspace/team-lib --include="*.md" --include="*.yaml" | \
  grep -v ".git" | grep -v "SKILL.md"
```

Review each hit for accuracy. Check Tier 2-4 files for:
- [ ] Registry YAML files have correct paths
- [ ] Index files list current contents
- [ ] Governance references are accurate

---

## Final Validation

After all three passes, run:

```bash
bash ~/ai-workspace/team-lib/_admin/validate.sh
```

**Only declare success if:**
1. ✅ All three passes completed
2. ✅ All discrepancies fixed
3. ✅ validate.sh passes with no errors

---

## Post-Change Checklist

After ANY structural change, confirm:

- [ ] `setup_workspace.sh` updated
- [ ] `validate.sh` updated
- [ ] `workspace-reference.md` section 5 updated
- [ ] `workspace-reference.md` section 4.x updated (if adding to a layer)
- [ ] `workspace-manifest.yaml` updated (if new subdirectory)
- [ ] Relevant `index.md` updated
- [ ] `README.md` updated (if structure diagram exists)
- [ ] `GETTING_STARTED.md` reviewed
- [ ] All three verification passes completed
- [ ] `validate.sh` passes
