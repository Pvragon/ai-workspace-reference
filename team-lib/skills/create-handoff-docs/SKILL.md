---
name: create-handoff-docs
description: Generate a thread-handoff context doc + verbatim cold-start prompt for a new session. Use when wrapping up a long thread, when context is approaching limits, or when the user says "let's start a new thread." (Renamed from /handoff 2026-05-31; the name /handoff is being reserved for the forthcoming session-rotate flow.)
template: skill-definition
version: 1.3.2
summary: >-
  Synthesizes the session into a handoff brief that OPENS WITH THE STARTUP CHECKLIST (worktree,
  memory cold-start, persona reload, debrief addendum), plus git state per touched repo,
  anti-patterns and don't-redo calls. Runs a resume-safety check and auto-commits on feature
  branches. Owns the brief FORMAT for every caller, /handoff included.
created: 2026-05-04
last_updated: 2026-10-16
maintainer: pvragon
listing: name-only
category: sessions
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
- Confirm the save location, per the **Default save-location convention** in Inputs above — the
  agent's `handoffs/` dir for a session-rotation brief, otherwise alongside the artifact the
  session covered. **Never `runtime/.tmp/`**: it is gitignored, so the brief the next thread is
  told to read would not survive a fresh clone. (This step used to name a `.tmp` path outright,
  contradicting the convention four paragraphs above it — fixed 2026-08-08.)

### Step 2 — Gather state (parallel Bash calls)

For **every repo touched in this session** (typically my-lib + a project repo):
- `git status --short` (+ which files are uncommitted)
- `git log -3 --oneline`
- `git rev-parse --abbrev-ref HEAD` (current branch)
- `git rev-list --count @{u}..HEAD 2>/dev/null` (commits ahead of upstream — flag if not pushed)

Note any validation markers / runtime state files (e.g., `.app-audit-matching-validated`).

### Step 3 — Synthesize the doc

> **⚑ A brief is NOT self-contained, and calling it that was the bug (corrected 2026-08-07).**
> A brief is a **pointer to what changed** — never a replacement for the agent's own state.
> `OPERATING-CORE`/`PROJECT-T3-LENS` **B6** says in as many words that a session handoff sits
> **BELOW all other sources** in precedence. A brief that seeds nothing else hands the next
> session the lowest-precedence artifact in the hierarchy and declares it sufficient.
> The startup checklist below is what makes the new session *itself*; the brief only makes it
> *current*. **Every brief opens with the checklist — no exceptions, no caller opts out.**

#### Step 3a — The startup checklist (REQUIRED — this is the top of every brief)

This skill owns the brief format, so it owns this checklist. Callers (`/handoff`, or a human
invoking this skill directly) supply the two parameters and nothing else:

- `WORKTREE` — where the next session must run. Default: this session's worktree
  (`git -C "$PWD" rev-parse --show-toplevel`, falling back to `$PWD`).
- `PERSONA` — the persona/role skill active in this thread, if any (e.g. `rc-cto`). Omit item 3
  entirely when there is none.

Emit it verbatim, as the first thing after the frontmatter:

````markdown
# Startup checklist — do these IN ORDER before reading anything below

1. **Confirm the worktree** is `<WORKTREE>` (`cd` there if not).

2. **Cold-start the agent — BEFORE reading the rest of this brief.** This brief is a summary and
   ranks below every source it describes (`PROJECT-T3-LENS` B6). These reads are the sources.

   ```bash
   MEM=$(python3 ~/ai-workspace/team-lib/executions/agent_paths.py | awk '$1=="memory_dir"{print $2}')
   ```
   1. Read `$MEM/current-state.md` — what is happening *now*.
   2. Read the last two dream-journal entries:
      `python3 ~/ai-workspace/team-lib/executions/dream_journal.py recent --n 2`, then read those files.
   3. Read the most recent `$MEM/short-term/YYMMDD-facts.md` **and** `YYMMDD-residue.md`.
   4. Scan the **Hot** and **New** tables in `$MEM/MEMORY.md`; open only the topic files this work needs.

   **If `$MEM/MEMORY.md` does not exist, say so immediately and stop** — it means this root has no
   memory symlink and you are operating without recall. Run
   `bash ~/ai-workspace/agents/*/adapters/claude/link.sh` and restart the session. (A SessionStart
   hook creates the link from 2026-08-07 onward; a failure here means that hook did not fire.)

3. **Re-load the active persona** — `<PERSONA>`. Phrase it as a Skill-tool invocation, NOT a shell
   command: "Invoke the Skill tool with skill name `<PERSONA>`." (Writing "run /<PERSONA>" makes the
   new agent try to execute it in Bash, which errors — the leading slash is only human prompt
   syntax.) A persona load has its own required reads; follow them rather than assuming the
   rotation carried them over. *Omit this item entirely if no persona was active — and say so
   explicitly ("Persona: none. Do not load one."), so the next session doesn't go looking.*

4. **Check for a debrief addendum** — include this line verbatim:
   > *"Re-read the bottom of this brief before you start work, and again at your first natural
   > break. The originating session's debrief runs AFTER this brief was written and may have
   > appended a `## Debrief addendum` section with findings that postdate everything above."*

5. Then read the work context below.
````

**Why item 4 is load-bearing:** the brief is always frozen before `/session-debrief` runs, so the
debrief's findings — often the session's most important — cannot be in it. The line converts that
race into a documented *pull*: the next session knows to look, instead of this one hoping to patch
in time. (`/handoff` makes the race acute; see that skill's step 4 note.)

#### Step 3b — The body

After the checklist, write the rest with this structure:

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

# Startup checklist — do these IN ORDER before reading anything below

<the five items from Step 3a, verbatim, with WORKTREE and PERSONA substituted>

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
   (do its startup checklist FIRST — the memory cold-start is not optional
    and the brief does not replace it)
2. <most important file>
3. <next-most-important file>

State of play: <one-sentence summary>.

Sequence:
1. <first action>
2. <second action>
3. <third action>

Don't over-engineer. <one-sentence scope-bound>.
```

Keep it tight (≤18 lines). The handoff doc carries the detail; the prompt is the entry point.

**The parenthetical on line 1 is required, not decorative.** A prompt that says only "read the
brief" makes the checklist a *deferred* read, and a deferred read that leaves no trace is
indistinguishable from one that never happened (`feedback_deferred-read-never-happens`). Naming
the checklist in the first instruction, and gating the first deliverable behind it, is what makes
it actually run. `/handoff`'s launcher seeds this same sentence — see `handoff.sh`'s
`DEFAULT_SEED`, which is the one place that wording is authored for the rotation path.

### Step 5 — Resume-safety check

Before finalizing, verify:
- **The brief opens with the Step 3a startup checklist**, all five items, with `WORKTREE`
  substituted and the persona item either filled in or explicitly marked "none". This is the one
  check that fails silently in use — a brief missing it still reads fine and still hands the next
  session a summary with no state behind it.
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

- Work commit: `<scope>(<area>): <imperative summary>` followed by 2-4 sentences of WHY (not WHAT — diff already shows what). Include the `Co-Authored-By:` trailer **exactly as your own harness specifies it** — don't copy a model name from this file, which can only ever name whichever model was current when the line was written (it said `Opus 4.7` until 2026-08-08).
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
- **Don't ship a brief without the Step 3a checklist**, however short the handoff or however
  "obvious" the continuation. The brief is the *only* artifact the next session is guaranteed to
  read; if the cold-start isn't in it, it happens nowhere.
- **Don't let a caller restate the checklist in its own words.** This skill owns the brief format.
  A second copy in a calling skill is a copy with no owner for the diff — which is exactly how the
  checklist came to exist in `/handoff` v2.4.0 and not here, so a direct invocation of this skill
  produced briefs with no memory cold-start at all for two months.
