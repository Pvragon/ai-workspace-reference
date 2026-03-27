---
name: create-directive
description: Guidelines for creating effective workflow directives that orchestrate without redundancy
summary: "Comprehensive guidelines for writing directives: template, anti-patterns, review criteria, and the directive vs skill vs AGENTS.md distinction. Follow when creating or reviewing any directive."
version: 1.1.0
created: 2026-01-26
last_updated: 2026-01-26
maintainer: pvragon
tags: [directive, documentation, workflow, best-practices]
---

# Create Directive

Guidelines for creating effective, non-redundant workflow directives.

## When to Use This Skill

Use when you need to create a new directive to orchestrate a multi-step workflow.

**Before creating a directive, ask:**

1. **Is this a single procedure?** → Create a **skill** instead
2. **Is this a global principle?** → Update **AGENTS.md** instead
3. **Is this a multi-step workflow across skills/tools?** → Create a **directive** ✓

---

## Directive vs. Skill vs. AGENTS.md

### Directive
**Purpose:** Orchestrate multi-step workflows
**Scope:** Entire processes with multiple checkpoints
**Example:** "Workspace Release Process" - validation → git → CHANGELOG → release notes
**Location:** `directives/`

### Skill
**Purpose:** Detailed procedure for a specific capability
**Scope:** Single, focused task
**Example:** "Check Workspace Consistency" - three verification passes, specific commands
**Location:** `skills/`

### AGENTS.md
**Purpose:** Global agent behavior and principles
**Scope:** All agent operations
**Example:** "Always exclude /archive/ from searches"
**Location:** Root of workspace

---

## Core Principle: Orchestration, Not Documentation

> [!IMPORTANT]
> **Directives orchestrate. They don't duplicate.**

### ✅ Good Directive (High-Level Orchestration)

```markdown
## Step 1: Validate Workspace

Execute the check-workspace-consistency skill:
Follow: `team-lib/skills/_workspace-developer/check-workspace-consistency/SKILL.md`

### Checkpoint
- [ ] Consistency check completed
- [ ] `validate.sh` passes
```

### ❌ Bad Directive (Re-Documents Skill)

````markdown
## Step 1: Validate Workspace

Run these three passes:

### Pass 1: Automated Extraction
Run these commands:
```bash
grep -oP 'ensure_dir \"\\K[^\"]+' ~/ai-workspace/team-lib/_admin/setup_workspace.sh
# ... 20 more lines of commands ...
```

### Pass 2: Documentation Review
Open each file and verify...
# ... 30 more lines of details ...
````

**Problem:** The skill already contains this. The directive just repeated it.

---

## Directive Structure Template

```markdown
---
template: directive
version: 1.0.0
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
maintainer: [your-name]
tags: [relevant, tags]
---

# [Directive Name]

[One-sentence description of the workflow]

## When to Use This Directive

[Clear trigger conditions for when to execute this workflow]

[Optional: Clarify scope - what types of changes/situations this covers]

## User Triggers

**Run this directive when the user asks to:**
- "[Phrase 1]"
- "[Phrase 2]"

## Prerequisites

[Required conditions before starting]
- Item 1
- Item 2

---

## Step 1: [Action Name]

**Goal:** [What this step accomplishes]

### [Execute skill / Run command / Verify condition]

[High-level instruction - reference skills, don't duplicate them]

### Checkpoint

- [ ] Outcome 1 verified
- [ ] Outcome 2 verified

**Do not proceed until checkpoint passes.**

---

## Step 2: [Next Action]

[Continue pattern...]

---

## Output Contract

Define what data flows where after execution:

**Return to context (agent sees this):**
- Summary counts, status messages, error descriptions
- Only what the agent needs to reason about next

**Keep in execution only (never leaves the script):**
- Raw API responses, full data dumps, verbose logs
- Intermediate transformation results

**Write to disk (persists for later use):**
- Full result files (`runtime/deliverables/` or `runtime/.tmp/`)
- Logs, exports, generated artifacts

> **Why:** Keeping raw data out of agent context reduces token usage and
> prevents context window overflow. See `execution-standard.md`.

---

## Final Checklist

**Category 1:**
- [ ] Item
- [ ] Item

**Category 2:**
- [ ] Item
- [ ] Item

---

## Troubleshooting

**Issue:** [Common problem]
- [Solution approach]

---

## Version History

- **v1.0.0** (YYYY-MM-DD): Initial directive created
```

---

## Anti-Pattern Checklist

Before finalizing your directive, check for these anti-patterns:

### 🚫 Re-Documenting Existing Skills

**Bad:**
```markdown
Run the consistency check:
1. Extract directories from setup script: grep -oP 'ensure_dir...'
2. Extract directories from validate script: grep -oP 'check_dir...'
3. Compare for discrepancies: comm -23...
```

**Good:**
```markdown
Execute the check-workspace-consistency skill:
Follow: `team-lib/skills/_workspace-developer/check-workspace-consistency/SKILL.md`
```

### 🚫 Re-Documenting Basic Agent Competencies

**Bad:**
```markdown
## Step 2: Commit Changes

First, check what files have been modified:
```bash
git status
```

This will show you a list of modified files. Then use git diff to see the changes:
```bash
git diff
```

Review each line carefully. Once satisfied, stage the files:
```bash
git add .
```
[... 20 more lines explaining basic git ...]
```

**Good:**
```markdown
## Step 2: Commit Changes

For each repository with changes:
1. Review: `git status` and `git diff`
2. Commit: `git add . && git commit -m "[Category] Description"`

### Checkpoint
- [ ] All changes committed
- [ ] Clean working tree
```

### 🚫 Listing Detailed Commands (When a Skill Exists)

**Bad:**
```markdown
## Step 5: Generate Release Notes

Run this command:
```bash
python3 team-lib/skills/_workspace-developer/generate-release-notes/generate_release_notes.py --last-run
```

Or use this command for a specific date:
```bash
python3 team-lib/skills/_workspace-developer/generate-release-notes/generate_release_notes.py --since "YYYY-MM-DD"
```
[... command documentation ...]
```

**Good:**
```markdown
## Step 5: Generate Release Notes

Execute the generate-release-notes skill:
Follow: `team-lib/skills/_workspace-developer/generate-release-notes/SKILL.md`

**Recommended:** Use `--last-run` for auto-detection.
```

### 🚫 Checkpoints Not Aligned with Step Boundaries

**Bad:**
```markdown
## Step 1: Do A and B

Do task A.
Do task B.

### Checkpoint
- [ ] A completed

## Step 2: Do C

Do task C.

### Checkpoint
- [ ] B completed
- [ ] C completed
```

**Good:**
```markdown
## Step 1: Do A and B

Do task A.
Do task B.

### Checkpoint
- [ ] A completed
- [ ] B completed

## Step 2: Do C

Do task C.

### Checkpoint
- [ ] C completed
```

**Key Principles:**
- Trust agent competencies (basic git, file ops, terminal navigation)
- Reference skills, don't repeat them
- Make checkpoints outcome-focused and verifiable
- Define scope clearly (not "use when making changes")
- Use troubleshooting sections instead of inline error prevention

### 🚫 Returning Raw Data to Agent Context

**Bad:**
```markdown
## Step 3: Fetch API Data

Run the API script and review all results:
```bash
python3 executions/fetch_data.py --all
```
Copy the full JSON output and analyze it.
```

**Good:**
```markdown
## Step 3: Fetch and Summarize API Data

Run the API script — it returns a summary dict, not raw data:
```python
from executions.fetch_data import run
result = run(target="all")
# result = {"status": "ok", "total": 42, "errors": 0}
```
Raw data stays on disk at `runtime/.tmp/fetch_results.json`.
Only the summary enters your context.
```

---

## Review Criteria

Before considering your directive complete, verify:

### Content Quality

- [ ] **Scope is clear:** When to use this directive is explicit
- [ ] **User Triggers defined:** Clear mappings from user intent to execution
- [ ] **Steps reference skills:** Not re-documenting existing procedures
- [ ] **Checkpoints are actionable:** Clear pass/fail criteria
- [ ] **No basic explanations:** Git, file ops, etc. are assumed knowledge

### Structure

- [ ] **Has frontmatter:** version, dates, maintainer, tags
- [ ] **Prerequisites listed:** Required conditions before starting
- [ ] **Steps are numbered:** Clear sequence
- [ ] **Each step has goal:** Purpose is stated
- [ ] **Checkpoints after steps:** Verification before proceeding
- [ ] **Final checklist exists:** Comprehensive verification
- [ ] **Troubleshooting included:** Common issues addressed

### Maintainability

- [ ] **Version history updated:** Changes tracked
- [ ] **No hardcoded paths:** Uses variables or clear examples
- [ ] **Skills linked properly:** Correct paths to referenced skills
- [ ] **Registry updated:** Added to `registry/directives.yaml`

---

## Workflow: Creating a New Directive

1. **Define the workflow:**
   - What's the end-to-end process?
   - What are the major steps/phases?
   - What skills already exist that can be referenced?

2. **Identify checkpoints:**
   - Where are the natural verification points?
   - What must be true before proceeding to next step?
   - What are the blocking vs. non-blocking checks?

3. **Draft using template:**
   - Start with frontmatter
   - Write "When to Use" section
   - List prerequisites
   - Create step structure with goals and checkpoints

4. **Apply anti-pattern checklist:**
   - Remove any skill re-documentation
   - Remove basic competency explanations
   - Condense command listings into skill references
   - Verify checkpoint boundaries

5. **Add metadata:**
   - Version history
   - Tags for discoverability
   - Update registry: `registry/directives.yaml`

6. **Review:**
   - Can an agent follow this without ambiguity?
   - Is every step either a skill reference or a simple action?
   - Are checkpoints clear and verifiable?

---

## File Locations

**Team directives:** `team-lib/directives/[directive-name].md`
- Workflows affecting team workspace
- Shared processes all team members use

**Personal directives:** `my-lib/directives/[directive-name].md`
- Custom workflows specific to you
- Personal automation processes

**After creating a team directive:**
- Update `team-lib/registry/directives.yaml`
- Follow workspace-release-process to publish

---

## Common Pitfalls

**Over-specifying:** Listing multiple command options instead of recommending one approach

**Under-specifying:** Vague instructions without clear goals or checkpoints

**Mixing levels:** Jumping between high-level orchestration and low-level commands in the same step - stay consistent

---

## Version History

- **v1.1.0** (2026-01-26): Added "User Triggers" to template and checklist (DOE Framework)
- **v1.0.0** (2026-01-26): Initial skill created based on lessons from workspace-release-process directive
