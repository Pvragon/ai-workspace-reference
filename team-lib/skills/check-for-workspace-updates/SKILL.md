---
name: check-for-workspace-updates
description: Check and upgrade local workspace files against latest team-lib templates
summary: "Compares local workspace files (AGENTS.md, etc.) against team-lib canonical templates and guides upgrades. Run periodically or after team-lib releases."
version: 1.1.0
created: 2026-01-23
last_updated: 2026-10-16
maintainer: pvragon
listing: name-only
category: workspace
---

# Workspace Upgrade Check

Compare your local workspace installation against the current team-lib templates and setup configuration. Identify differences and optionally upgrade to the latest versions.

## When to Use

- After `git pull` on team-lib shows template changes
- Periodically to ensure your workspace is current
- When onboarding issues suggest outdated configuration

## Files Checked

| Local File | Template Source |
|------------|-----------------|
| `my-lib/AGENTS.md` | `team-lib/context/indexed/templates/template-agent-automation-user.md` |
| `my-lib/CLAUDE.md` | Stub format (pointer to AGENTS.md) |
| `my-lib/GEMINI.md` | Stub format (pointer to AGENTS.md) |
| `~/.claude/skills` (per-skill links) | every team-lib skill and `ext-*` pointer, via `team-lib/executions/link_skills.py` |
| `~/.claude/settings.json` `skillOverrides` | the generated `my-lib/config/claude-skill-overrides.json` (what the model is shown for each skill), via `build_skill_overrides.py --installed` |

## Upgrade Procedure

### 1. Pull latest team-lib

```bash
cd ~/ai-workspace/team-lib && git pull origin main
```

### 1b. Relink skills and refresh the skill listing

A pull can add skills or change a skill's `listing:`. New skills are invisible to the harness
until linked, and a changed listing does nothing until the map is regenerated and installed.

```bash
python3 ~/ai-workspace/team-lib/executions/link_skills.py                 # new skills -> ~/.claude/skills
python3 ~/ai-workspace/team-lib/executions/build_skill_overrides.py       # regenerate the map (my-lib/config)
python3 ~/ai-workspace/team-lib/executions/build_skill_overrides.py --installed   # settings vs the map
```

If `--installed` reports missing keys, run `install_skill_overrides.py` (dry run) and then
`--apply`. It writes `~/.claude/settings.json`, so the agent runs it with one approval from the
owner; it keeps any key set by hand and reports it as foreign. Restart Claude Code afterwards.
Never edit `skillOverrides` in settings.json by hand: change the skill's frontmatter instead.

### 2. Check AGENTS.md differences

```bash
echo "=== AGENTS.md Version Check ==="
echo "Local:    $(grep 'version:' ~/ai-workspace/my-lib/AGENTS.md 2>/dev/null | head -1)"
echo "Template: $(grep 'version:' ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md | head -1)"
echo ""
echo "=== Differences ==="
diff ~/ai-workspace/my-lib/AGENTS.md \
     ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md
```

### 3. Review and decide

If differences exist, review them carefully:
- **Template is newer** → Consider upgrading your local file
- **Local has customizations** → Merge manually to preserve your changes
- **Files are identical** → No action needed

### 4. Upgrade (if desired)

> [!CAUTION]
> Only proceed if you want to replace your local AGENTS.md with the template.
> This will overwrite any personal customizations.

**Option A: Full replacement (lose local customizations)**
```bash
cp ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md \
   ~/ai-workspace/my-lib/AGENTS.md
echo "✅ AGENTS.md upgraded to template version"
```

**Option B: Backup then replace (safe)**
```bash
cp ~/ai-workspace/my-lib/AGENTS.md ~/ai-workspace/my-lib/AGENTS.md.backup.$(date +%Y%m%d)
cp ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md \
   ~/ai-workspace/my-lib/AGENTS.md
echo "✅ AGENTS.md upgraded (backup saved)"
```

### 5. Verify stub files

Check that CLAUDE.md and GEMINI.md are proper pointers:

```bash
echo "=== CLAUDE.md ===" && head -3 ~/ai-workspace/my-lib/CLAUDE.md
echo "=== GEMINI.md ===" && head -3 ~/ai-workspace/my-lib/GEMINI.md
```

Expected format:
```
# claude.md (local)

READ ~/ai-workspace/my-lib/AGENTS.md BEFORE ANYTHING
```

If missing or malformed, recreate:
```bash
echo '# claude.md (local)

READ ~/ai-workspace/my-lib/AGENTS.md BEFORE ANYTHING

# Local specific tweaks for Claude
## - insert model-specific tweaks here
' > ~/ai-workspace/my-lib/CLAUDE.md

echo '# gemini.md (local)

READ ~/ai-workspace/my-lib/AGENTS.md BEFORE ANYTHING

# Local specific tweaks for Gemini
## - insert model-specific tweaks here
' > ~/ai-workspace/my-lib/GEMINI.md
```

### 6. Commit upgraded files

```bash
cd ~/ai-workspace/my-lib
git add AGENTS.md CLAUDE.md GEMINI.md
git commit -m "Upgrade agent files to template v$(grep 'version:' AGENTS.md | head -1 | awk '{print $2}')"
git push origin main
```

## Quick Check Script

Run this one-liner to see if an upgrade is needed:

```bash
TEMPLATE_VER=$(grep 'version:' ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md | head -1 | awk '{print $2}')
LOCAL_VER=$(grep 'version:' ~/ai-workspace/my-lib/AGENTS.md 2>/dev/null | head -1 | awk '{print $2}' || echo "MISSING")
if [ "$TEMPLATE_VER" = "$LOCAL_VER" ]; then
  echo "✅ Up to date (v$LOCAL_VER)"
else
  echo "⚠️  Upgrade available: $LOCAL_VER → $TEMPLATE_VER"
fi
```

## What This Skill Does NOT Touch

This skill only affects agent instruction files. It will **never** modify:
- Your personal files in `personal/`
- Your custom skills in `my-lib/skills/`
- Your custom directives in `my-lib/directives/`
- Your executions, personas, or other my-lib content
- Any project files in `projects/`
