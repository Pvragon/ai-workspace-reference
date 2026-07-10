---
name: session-debrief
description: "End-of-session procedure that captures learnings into memory topic files, verifies index consistency, updates current-state.md, and syncs changes to team-lib."
summary: "Run at end of a work session to persist learnings, check index health, update workspace current state, and propagate improvements to team-lib. Uses preflight/postflight scripts for speed and reliability."
version: 2.4.0
created: 2026-02-20
last_updated: 2026-05-04
maintainer: pvragon
---

# Session Debrief

Run this skill at the end of a work session to capture learnings and maintain workspace hygiene.

**Architecture:** Deterministic work is pushed to shell scripts (`preflight.sh`, `postflight.sh`). The LLM focuses only on judgment-requiring work (memory, state updates, summaries). This makes the debrief faster and more reliable.

## Phase 1: Preflight (deterministic)

Run the preflight script to collect all session data in one pass:

```bash
bash ~/ai-workspace/my-lib/skills/session-debrief/preflight.sh
```

This outputs a JSON report with:
- **`git_changes`** — files changed, recent commits, which registered dirs were touched
- **`registry_issues`** — files missing from registries or registry entries pointing to missing files
- **`sync_needed`** — AGENTS.md or skills that changed and also exist in team-lib
- **`stale_flags`** — current-state.md health (stale entries, pending notes, old decisions)
- **`memory_issues`** — MEMORY.md index inconsistencies (unindexed files, broken links)
- **`session_info`** — date, approximate timestamps, memory index line count, **and a `session_marker` token you must pass to postflight**

**Read the report carefully before proceeding.** It tells you exactly what needs attention.

**Grab `session_info.session_marker`** — you'll pass it to postflight so it can deterministically identify the current session's JSONL (needed for setting the /resume title correctly when multiple concurrent sessions exist).

## Phase 2: LLM Judgment Work

With the preflight report in hand, work through these items. Do them all before moving to Phase 3.

### 2a. Fix Registry Issues

If `registry_issues` is non-empty, fix each one:
- **`unregistered`** — Add the file to the appropriate `registry/*.yaml`
- **`missing_file`** — Remove the stale entry from the registry

### 2b. Fix Memory Index Issues

If `memory_issues` is non-empty:
- **`unindexed`** — Add the file to `MEMORY.md` with a one-line summary
- **`missing_file`** — Remove the broken link from `MEMORY.md`

### 2c. Memory Capture

Reflect on the session and answer these questions. If the answer is yes, act immediately:

1. **Learned something future agents should know?**
   → Write to the appropriate topic file in memory. If no existing topic fits, create a new one and add a row to `MEMORY.md`.

2. **Discovered a convention or gotcha?**
   → Append to `lessons-learned.md` in the memory directory.

3. **Learned about a person, process, or entity?**
   → Find or create the relevant topic file.

### 2d. Update current-state.md

`memory/current-state.md` is a **structured snapshot, not an append log**. It holds only the four sections below. Verbose session detail belongs in `memory/short-term/YYMMDD-facts.md` (Phase 2c — and Move 1 of the 4-tier memory architecture).

**🚫 DO NOT append "## Session Add" blocks to current-state.md.** This was the historical bloat pattern that produced a 228KB file. Update sections **in place** — replace stale content, don't accrete it. (Reset 2026-05-04: prior session-add history → `current-state-archive.md`.)

Open `memory/current-state.md` and update:

1. **Active Work** — add/update items from this session. **Remove completed items.** Keep to bulleted, single-line-per-workstream form.
2. **Blockers** — add new, remove resolved.
3. **Recent Decisions** — add decisions made this session with date and rationale. Cap at ~10 entries; older decisions either graduate to a topic memory or drop off.
4. **Notes for Next Session** — leave notes for the next agent. Replace stale notes; don't stack them.
5. **Update the `Last updated` (or `Last reset`) header comment.**

**Size discipline:** Target ≤5KB total. If you find yourself wanting to add a long session narrative, that's a signal it belongs in `short-term/YYMMDD-facts.md` instead. The structured sections here distill *current state*, not session history.

**Cleanup (informed by preflight `stale_flags`):**
- **`pending_notes`** → Previous notes should have been consumed. Clear stale ones.
- **`old_decisions`** → Prune entries older than 14 days. Move long-term-worthy decisions to memory topic files first.
- Flag any Active Work items with no update in 14+ days to the user.

### 2e. Sync to Team-Lib

If `sync_needed` is non-empty:
- **`agents_md`** → Run the `push-agents-to-template` skill.
- **`skill:<name>`** → Review whether the skill changes should propagate to team-lib. Only promote stable, generally-useful changes (not workspace-specific tweaks).

If nothing in `sync_needed`, skip this.

### 2f. Session Log Entry

Append a one-line entry to `memory/session-log.md`:

**Format:** `YYYY-MM-DD | session-name | key topics/outcomes`

- Use the `/rename` name if set, otherwise compose a 2-4 word descriptive name
- Newest entries at the top (after `<!-- entries below -->`)
- If no session name yet, suggest one and offer to `/rename`

### 2g. Compose Pulse Debrief

Write a 1-3 sentence debrief message. **Do not post it yet** — it will be passed to postflight.

**Format:**
```
JH Claude Debrief [<start time> - <end time>]: <summary of outcomes, decisions, and next steps>
```

Use `session_info.approx_start` and `session_info.end` from the preflight report for timestamps.

### 2h. Enumerate touched files (REQUIRED for postflight)

Before invoking postflight, build two explicit space-separated lists of repo-relative paths the debrief modified — one for the my-lib repo, one for the agents identity repo. **Postflight will refuse to run without these.** This replaces the old `git add -A` catch-all behavior (which previously swept up unrelated work from concurrent sessions — see commit `836c2c6` and the 2026-04-20 21:11 incident in current-state.md).

**What counts as "touched":**

- Files you explicitly Edit'd or Write'd during the debrief (memory entries, `current-state.md`, `session-log.md`, `MEMORY.md`, etc.)
- Files modified via Bash (`cp`, `mv`, hook scripts, etc.) — these don't show in tool-call history; track them deliberately as you go
- Files created during the debrief (new memory entries, new backlog items)
- **Files committed manually during the debrief that you'd ALSO have postflight commit again — exclude these.** If you already ran `git commit` on a file, don't pass it again; postflight won't have anything to add.

**What does NOT count:**

- Files dirty *before* the debrief started (the preflight `git_changes.changed_files` baseline). Those belong to whatever produced them (likely a concurrent session) and must be preserved as-is.
- Files committed by other sessions or out-of-band tooling.

**Path format:** repo-relative (e.g., `backlog/foo.md`, `memory/MEMORY.md`), space-separated.

**If nothing was touched in a given repo,** pass an empty string (`--mylib-files ""`) to skip that repo's commit cleanly.

## Phase 3: Postflight (deterministic)

Run the postflight script with the composed pulse message and the file lists from Phase 2h:

```bash
bash ~/ai-workspace/my-lib/skills/session-debrief/postflight.sh \
  --session-name "<session-name>" \
  --session-marker "<value from preflight's session_info.session_marker>" \
  --mylib-files "backlog/foo.md skills/bar/SKILL.md" \
  --agents-files "memory/MEMORY.md memory/topic_xyz.md" \
  --pulse-message "<debrief message>"
```

**IMPORTANT — required args (will error if missing):**
- `--mylib-files "..."` — explicit space-separated paths the debrief modified in my-lib (or `""` to skip)
- `--agents-files "..."` — explicit space-separated paths the debrief modified in agents identity repo (or `""` to skip)

**IMPORTANT:** Pass `--session-marker` from the preflight report's `session_info.session_marker`. Postflight will grep JSONLs for that marker to identify the current session deterministically — no guessing, safe with any number of concurrent sessions. (`--session-id <uuid>` is still accepted as an explicit override if you already know the UUID.)

This handles in one pass:
1. Workspace hygiene — removes WSL `*:Zone.Identifier` junk files across `~/ai-workspace` (via `executions/clean_zone_identifiers.sh`)
2. Session title prepend (custom-title at line 1 of session JSONL for /resume)
3. Claude adapters (symlinks + config backup)
4. Agent identity repo commit + push (only the files in `--agents-files`)
5. my-lib repo commit, no push (only the files in `--mylib-files`)
6. Pulse channel post

**Title logic:** If the user did `/rename`, uses that name verbatim. Otherwise, prepends `YYMMDD-HH:MM <session-name>` to the JSONL head so `/resume` shows a meaningful name.

**Options:**
- `--mylib-files "<paths>"` — **REQUIRED** unless `--skip-commit` or `--legacy-add-all`. Space-separated repo-relative paths to stage for the my-lib commit. Pass `""` to skip that repo cleanly.
- `--agents-files "<paths>"` — **REQUIRED** unless `--skip-commit` or `--legacy-add-all`. Same shape as `--mylib-files`, for the agents identity repo.
- `--legacy-add-all` — Escape hatch: revert to the old `git add -A` catch-all behavior. **Use only when explicitly justified** (e.g., recovering after extensive uncommitted work that genuinely all belongs to this debrief). Logs a prominent warning. Prefer explicit file lists.
- `--session-marker "<token>"` — Marker from preflight output; resolves to the current session's UUID via JSONL grep (**preferred**)
- `--session-id "<uuid>"` — Explicit session UUID (skip marker lookup; use only if you already know it)
- `--skip-pulse` — Skip posting (e.g., if the user declines)
- `--skip-commit` — Dry run (adapters only, no git commits — also bypasses the file-list requirement)

## Phase 4: Confirm

Summarize to the user what was updated:
- Memory topic files modified or created
- Registry/index corrections made
- What changed in current-state.md
- Whether anything was synced to team-lib
- Git commit results (agents repo + my-lib)
- Any items flagged for attention
- Session-log entry added
- Pulse debrief posted (or skipped)
