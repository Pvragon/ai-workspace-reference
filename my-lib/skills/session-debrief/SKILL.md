---
name: session-debrief
description: "End-of-session procedure that captures learnings into memory topic files, verifies index consistency, updates current-state.md, and syncs changes to team-lib."
summary: "Run at end of a work session to persist learnings, check index health, update workspace current state, and propagate improvements to team-lib."
version: 1.4.0
created: 2026-02-20
last_updated: 2026-03-26
maintainer: pvragon
---

# Session Debrief

Run this skill at the end of a work session to capture learnings and maintain workspace hygiene.

## Procedure

### Step 1: Review What Changed

Run `git diff --name-only` and check recent commits to understand what was modified this session.

```bash
git diff --name-only
git log --oneline -10
```

Note which directories were touched — you'll need this for Steps 3 and 5.

### Step 2: Memory Check

Answer these three questions. If the answer is yes, act immediately:

1. **Learned something future agents should know?**
   → Write to the appropriate topic file in `~/.claude/projects/-home-username-ai-workspace-my-lib/memory/`.
   → If no existing topic file fits, create a new one and add a row to `MEMORY.md`.

2. **Discovered a convention or gotcha?**
   → Append to `lessons-learned.md` in the memory directory.

3. **Learned about a person, process, or entity?**
   → Find or create the relevant topic file in the memory directory.

### Step 3: Registry Consistency Check

For each registered directory modified this session, verify the corresponding `registry/*.yaml` file is up to date:

**Library registries** (in `my-lib/registry/` and `team-lib/registry/`):
- `directives.yaml` ← `directives/`
- `skills.yaml` ← `skills/`
- `personas.yaml` ← `personas/`
- `executions.yaml` ← `executions/`
- `context.yaml` ← `context/indexed/`

For each:
- New files → must have an entry in the registry
- Deleted files → entry must be removed
- Renamed files → path must be updated
- Modified files (if description changed) → update the description

**Project doc registries:** If any files under `projects/*/docs/` were modified, check the corresponding `docs/registry.yaml` and update it.

### Step 4: Update current-state.md

Open `~/.claude/projects/-home-username-ai-workspace-my-lib/memory/current-state.md` and update:

1. **Active Work** — add/update items based on this session's work. Remove completed items.
2. **Blockers** — add new blockers, remove resolved ones.
3. **Recent Decisions** — add any decisions made this session with date and rationale.
4. **Notes for Next Session** — leave notes for the next agent (ephemeral — consumed on read).
5. **Update the `Last updated` date** at the top of the file.

**Cleanup rules** (apply each time):
- **Notes for Next Session**: Previous notes should have been consumed by this session. Clear any remaining stale notes.
- **Recent Decisions**: Prune entries older than 14 days. If a decision is worth keeping long-term, move it to the relevant memory topic file before removing it.
- **Active Work**: Flag items with no update in 14+ days to the user ("still active?"). Remove confirmed-complete items.
- **Blockers**: Remove resolved blockers.

### Step 5: Sync to Team-Lib

**This step ensures learnings flow from my-lib to the canonical team template.** The workspace owner treats my-lib as the proving ground — improvements validated here should always propagate to team-lib so new workspaces inherit them.

Check if any of these were modified this session:
- **`AGENTS.md`** → Run the `push-agents-to-template` skill (`skills/push-agents-to-template/SKILL.md`) to sync to `team-lib/context/indexed/templates/template-agent-automation-user.md`. Both files must stay identical.
- **Skills, executions, or context files ready for promotion** → Use `graduate_files.py` or manually copy to the corresponding team-lib directory. Only promote files that are stable and generally useful (not workspace-specific customizations).

If nothing was modified that warrants syncing, skip this step.

### Step 6: Session Log Entry

Append a one-line chronicle entry to `memory/session-log.md`. This provides temporal memory independent of Claude Code's `sessions-index.json` (which is known to corrupt).

**Format:** `YYYY-MM-DD | session-name | key topics/outcomes`

- **session-name**: Use the `/rename` name if one was set, otherwise compose a 2-4 word descriptive name
- **topics/outcomes**: 1 short sentence — what was accomplished or decided
- Newest entries go at the top (after the `<!-- entries below -->` marker)

**Example:**
```
2026-03-26 | Pulse Upgrades | Added AFK suppression, deployed crontab for 15-min summaries
```

If the session doesn't have a name yet, suggest one to the user and offer to `/rename` it before closing.

### Step 7: Agent Identity Repo Maintenance

Run the symlink adapter to catch any new Claude Code project directories created during this session:

```bash
bash ~/ai-workspace/agents/rowan-anicca/adapters/claude/link.sh
```

Then commit any memory changes to the agent identity repo (no push):

```bash
cd ~/ai-workspace/agents/rowan-anicca
git add -A
git diff --cached --quiet || git commit -m "chore: session memory update — $(date +%Y-%m-%d)"
git push
cd ~/ai-workspace/my-lib
```

### Step 8: Post Debrief to Pulse Channel

Post a session summary to the ClickUp Pulse channel so it appears alongside the 15-minute activity summaries. This gives a narrative bookend to the work.

**Format:**
```
JH Claude Debrief [<start time> - <end time>]: <1-3 sentence summary of what was accomplished, key decisions made, and what's next>
```

**How to post:**
```bash
source ~/ai-workspace/personal/secrets/.env && echo '{"type":"message","content":"<message>"}' | restish post clickup-v3/workspaces/9011906822/chat/channels/5-90117802942-8/messages
```

**Guidelines:**
- Keep it to 1-3 sentences — this is a pulse, not a report
- Focus on outcomes and decisions, not process
- Include any backlog items created or significant state changes
- The start time is when the session began (first activity), end time is now
- Privacy rules apply — same as activity summaries

### Step 9: Confirm

Summarize to the user what was updated:
- Which memory topic files were modified or created
- Which index files were corrected
- What changed in current-state.md
- Whether anything was synced to team-lib
- Whether the agent identity repo was committed
- Any items flagged for attention (stale work items, pruned decisions)
- Whether a session-log entry was added
- Whether the Pulse debrief was posted
