---
name: create-handoff-docs
description: Generate a thread-handoff context doc + verbatim cold-start prompt for a new session. Use when wrapping up a long thread, when context is approaching limits, or when the user says "let's start a new thread." (Renamed from /handoff 2026-05-31; the name /handoff is being reserved for the forthcoming session-rotate flow.)
template: skill-definition
version: 1.2.0
summary: Synthesizes the current session into a handoff doc, captures git state per touched repo, anti-patterns to avoid, and "don't redo" judgment calls. Runs a resume-safety check, prints a verbatim cold-start prompt, and auto-commits the work + handoff doc on feature branches (with safety guards).
created: 2026-05-04
last_updated: 2026-05-31
maintainer: pvragon
---

# /create-handoff-docs

Generate a thread-handoff package: a context doc for the next session + a verbatim cold-start prompt.

## When to invoke

- User says "let's wrap up", "hand off", "start a new thread"
- Context window approaching ~180k+ tokens
- Long session with non-trivial decisions / dead-ends that should NOT be re-derived

## Inputs (optional)

- `--topic <slug>` — short slug for filename (e.g., `app-audit-v1.4.2`). Default: prompt the user.
- `--out <path>` — override default save location.

**Default save-location convention:** the skill saves to a non-gitignored, commit-friendly location alongside the artifact the session covered. For session work centered on a specific skill, save to that skill's own directory, in whichever layer it lives (e.g. `<layer>/skills/<skill>/CONTEXT-YYMMDD-<topic>-handoff.md`). For session work on a project, save to the project's docs directory. **Avoid `runtime/.tmp/`** — that's gitignored, which defeats the "commit + push so the next thread can read it" purpose. **Never save under `~/.claude/`** (e.g. `~/.claude/handoffs/`) — it's a PROTECTED directory, so the Write tool prompts for permission on every brief and a PreToolUse allow-hook cannot rescue it (verified 2026-06-25; see [[reference_claude-protected-dir-memory-write-prompts]]). For session-rotation briefs, use `~/ai-workspace/agents/<your-agent>/handoffs/` (non-protected, allow-listed, hook-covered).
- `--no-commit` — skip the auto-commit step entirely (just save the doc and print the prompt).

## Procedure

### Step 1 — Confirm scope

Ask the user (single short question):
- Topic slug if not provided
- Confirm save location is `~/ai-workspace/my-lib/runtime/.tmp/YYMMDD-<topic>-handoff.md`

### Step 2 — Gather state (parallel Bash calls)

For **every repo touched in this session** (typically my-lib + a project repo):
- `git status --short` (+ which files are uncommitted)
- `git log -3 --oneline`
- `git rev-parse --abbrev-ref HEAD` (current branch)
- `git rev-list --count @{u}..HEAD 2>/dev/null` (commits ahead of upstream — flag if not pushed)

Note any validation markers / runtime state files (e.g., `.app-audit-matching-validated`).

### Step 3 — Synthesize the doc

Write to the chosen path with this structure:

```markdown
---
template: session-handoff
name: <topic>-handoff
summary: <one-line state of play>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
maintainer: pvragon
status: active-handoff
---

# <Topic> — Session Handoff

## State of play

<1-paragraph: where we landed, what was just done>

## Repo state

| Repo | Branch | Last commit | Pushed? | Uncommitted? |
|---|---|---|---|---|
| my-lib | <branch> | `<hash>` <subject> | yes/no | <files or none> |
| <project> | <branch> | `<hash>` <subject> | yes/no | <files or none> |

Plus: validation markers, runtime state files, anything else load-bearing.

## Key decisions / findings (don't re-derive)

Numbered list of judgment calls + non-obvious findings:
- Bug roots discovered (with the actual fix)
- Calibrated thresholds / rubric numbers
- Architectural choices made
- Anything that took >5 min of investigation to figure out

## Don't repeat these mistakes

Numbered list of dead-ends / anti-patterns:
- "Don't try X — fails because Y"
- Regex / edge-case bugs that bit us
- Wrong assumptions corrected mid-session

## Don't redo these (already-resolved judgment calls)

Things the user verbally resolved that aren't in code:
- "User confirmed X is final"
- "User said Y is acceptable, don't penalize again"
- Decisions that look reversible but the user has moved past

## Open items / next-session order

Numbered list of what to do next, in order.

## Files to read first (cold-start order)

1. `<path>` — what to extract
2. `<path>` — what to extract
3. `<path>` — what to extract

## Cold-start prompt (verbatim)

```
<the paste-ready prompt block from Step 4>
```
```

### Step 4 — Generate the cold-start prompt

A self-contained block the user pastes into a new thread. Format:

```
Pick up <topic>. Read these in order:

1. <handoff doc path>
2. <most important file>
3. <next-most-important file>

State of play: <one-sentence summary>.

Sequence:
1. <first action>
2. <second action>
3. <third action>

Don't over-engineer. <one-sentence scope-bound>.
```

Keep it tight (≤15 lines). The handoff doc carries the detail; the prompt is the entry point.

### Step 5 — Resume-safety check

Before finalizing, verify:
- Every file path referenced in the cold-start prompt **exists on disk**
- No uncommitted changes in files the new thread will read (if any, flag them — the new thread might pull from git and lose state)
- Branches are pushed (or note explicitly that they're local-only)
- Validation markers are still fresh if referenced

If anything's inconsistent, surface it to the user **before** finalizing.

### Step 6 — Auto-commit (with safety guards) + print

Default behavior is **auto-commit**, not "offer to commit." Frequent commits make iterations recoverable, and the handoff is the natural checkpoint moment. Skip entirely if `--no-commit`.

**Two commits, in order:**

1. **Work commit** — the substantive changes Claude made this session in the project repo (and/or my-lib). Stage ONLY files Claude knows it touched (track via tool-call history during the session — Edit/Write/Bash-mv targets). Never `git add -A` or `git add .` — that sweeps in unrelated work from other sessions.

2. **Handoff commit** — the handoff doc itself. Always its own commit, separate from the work commit, even if scope feels small. Keeps the handoff cleanly identifiable in `git log`.

**Safety guards (apply to BOTH commits):**

- **Branch check.** If `git rev-parse --abbrev-ref HEAD` returns `main` (or `master`), STOP. Print the staged file list and ask for explicit confirmation before committing on a protected branch. Northwind has a hook that blocks main commits; other repos rely on discipline. Either way, never auto-commit to main without confirmation.
- **Diff preview.** Before each commit, print:
  - The staged file list (`git diff --cached --stat`)
  - One-line summary of what's in the commit
  Even with auto-commit, show the diff/scope BEFORE the commit lands. Per `feedback_diff-preview-before-push.md` the principle generalizes — show before mutating shared state.
- **Scope discipline.** If the staged file list contains anything Claude didn't touch this session, STOP and ask. Don't sweep in other sessions' uncommitted changes. Common false-positive: someone else's untracked CSV in the same project repo.
- **Never auto-push.** Commits are local and reversible; push is the higher-stakes "publish" step. Always end with the local commit and let the user decide whether to push. Print the local commit hashes + a one-line "to push: `git push`" hint.

**Commit message conventions:**

- Work commit: `<scope>(<area>): <imperative summary>` followed by 2-4 sentences of WHY (not WHAT — diff already shows what). Include `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` per workspace convention.
- Handoff commit: `docs(<area>): session handoff — <topic>`, body = 2-line state-of-play. Same Co-Authored-By line.

After both commits land:
- Print the cold-start prompt in chat (in a fenced block) so the user can copy it
- Print the handoff doc path
- Print the two commit hashes + push reminder

## Output to user (chat)

Four things:
1. The two commit hashes (work + handoff) with one-line subjects, plus a `to push: git push` reminder
2. Path to the saved handoff doc
3. The cold-start prompt block (fenced, copyable)
4. 2-line summary of what's pending

If `--no-commit` was used or the branch-safety guard fired, item 1 becomes "uncommitted — see below" and surface the reason.

## Don'ts

- Don't auto-summarize the entire conversation. Synthesize what *mattered*.
- Don't include memory-style capture (that's `/session-debrief`).
- Don't restate trivia that's already in skill specs / registries / project docs.
- Don't write a multi-page handoff. The cold-start prompt is load-bearing; the doc is supplementary.
- Don't include the "what skills are available" boilerplate — that's already in every cold-start.
