---
name: handoff
description: Rotate to a fresh session in one step — run /create-handoff-docs, spawn a NEW terminal window with a fresh Claude that auto-reads the brief and continues, THEN run /session-debrief in the old pane. Spawning before the (slow) debrief lets you keep working in the new window while the old one closes out. The new session inherits the current name with an incremented -N suffix, runs in the same worktree, and re-loads the active persona (e.g. /rc-cto). Does NOT close the current window.
template: skill-definition
version: 2.3.0
summary: The session-rotate orchestrator. Order: /create-handoff-docs (brief) → spawn new window via skills/handoff/handoff.sh (fresh tmux mylib-<pid>, reaper-managed; `claude -n <current-name>-<n+1>` in the same worktree, seeded to read the brief + re-load the active persona) → /session-debrief in the old pane. Spawn-before-debrief so work continues immediately. Reaping is NOT a separate step; it comes from the debrief + the new window's SessionStart hook. Requires WSL + Windows Terminal.
created: 2026-05-31
last_updated: 2026-07-30
maintainer: pvragon
argument-hint: "(no args — derives everything from the current session)"
---

# /handoff — rotate to a fresh, seeded session

Wrap up this thread and continue in a brand-new window, by composing existing skills. The new session picks up exactly where this one left off: same name (incremented), same worktree, same persona, brief already read.

## 1. Compute the new session name
Take the **current session's name** (the `/rename` name for this session). Append/increment a `-N` suffix:
- If it ends in `-<integer>` → increment it (`foo-2` → `foo-3`).
- Otherwise → append `-2` (`foo` → `foo-2`; "no suffix" = n=1, so next is n=2).

Call this `NEW_NAME`. (Example: `260531-review-toms-spreadsheet-billing-analysis` → `…-analysis-2`.)

## 2. Capture worktree + active persona
- **Worktree:** the worktree this thread is working in — `git -C "$PWD" rev-parse --show-toplevel` (fall back to `$PWD`). Call it `WORKTREE`. The new session must run here.
- **Active persona:** if a persona/role skill is active in this thread (e.g. `rc-cto`, loaded earlier), note its skill **name** so the brief can re-load it. If none, skip.

## 3. Generate the handoff brief → /create-handoff-docs
First resolve the agent's handoffs directory — do NOT write a literal agent name:

```bash
HANDOFFS=$(python3 ~/ai-workspace/team-lib/executions/agent_paths.py | awk '$1=="handoffs_dir"{print $2}')
```

`agent_paths.py` finds the agent home by looking for `identity.md`, so it is correct for whichever
agent is running and refuses to guess when it cannot decide. `/session-debrief` resolves the SAME
directory the same way; if these two ever disagree, the debrief addendum lands where nobody reads it.

Then invoke **/create-handoff-docs**, saving the brief to **`$HANDOFFS/<NEW_NAME>.md`** (self-contained — the new session has no other context).

> **Why NOT `~/.claude/handoffs/`:** that path is inside the PROTECTED `.claude/` directory, so the Write tool prompts for permission on every brief — and a PreToolUse allow-hook cannot rescue protected-dir writes (verified 2026-06-25, same root cause as memory writes; see [[reference_claude-protected-dir-memory-write-prompts]]). the agent's `handoffs/` dir is non-protected and already allow-listed (`Edit(//…/ai-workspace/agents/**)`) AND covered by the `allow_memory_writes` hook's `handoffs/` segment, so it never prompts in any mode. It's equally global/stable for the new session to read.

Ensure the brief **opens with a startup checklist**:
1. **Re-load the active persona** if one was noted — phrase it as a Skill-tool invocation, NOT a shell command: "Invoke the Skill tool with skill name `rc-cto`." (Writing "run /rc-cto" makes the new agent try to execute it in Bash, which errors — the leading slash is only the human prompt syntax.)
2. **Confirm the worktree** is `WORKTREE` (cd there if not).
3. **Check for a debrief addendum** — include this line verbatim in the checklist:
   > *"Re-read the bottom of this brief before you start work, and again at your first natural
   > break. The originating session's debrief runs AFTER this brief was written and may have
   > appended a `## Debrief addendum` section with findings that postdate everything above."*
4. Then the work context: what this thread did, current state, open items / next action, key paths, anti-patterns.

> **Why the addendum line is load-bearing (added 2026-07-30).** Step 4 spawns the new window
> *before* step 5 runs the debrief, so the brief is frozen before the debrief can surface
> anything. On 2026-07-30 the single most important finding of the session had to be
> hand-patched into an already-launched brief; it only worked because the new window happened
> to be untouched. Had it been in use, its work queue would have been missing its top item.
> The checklist line converts that race into a documented pull — the new session knows to look,
> instead of the old session hoping to patch in time.

### 3b. Register the brief for enrichment
So the debrief in step 5 can find this brief unambiguously, write a pointer entry:

Substitute `<NEW_NAME>` the same way you do everywhere else in this skill — these are
placeholders, not shell variables you have set:

```bash
H="$HANDOFFS"
mkdir -p "$H/.pending-enrichment"
printf '{"brief":"%s","new_name":"%s","written_at":"%s"}\n' \
  "$H/<NEW_NAME>.md" "<NEW_NAME>" "$(date -Iseconds)" \
  > "$H/.pending-enrichment/<NEW_NAME>.json"
```

**Do NOT expect the debrief to find the brief by mtime.** "Most recent file in `handoffs/`" is
wrong and will enrich another thread's brief: there are 60+ briefs there and concurrent
sessions fork their own on the same day — on 2026-07-30 a sibling thread's brief sorted above
this one's within hours. One file per handoff (never a single shared pointer) so two
concurrent handoffs can't overwrite each other.

## 4. Launch the new window (before the debrief)
```
~/.claude/skills/handoff/handoff.sh <NEW_NAME> "$HANDOFFS/<NEW_NAME>.md" --dir <WORKTREE>
```
Opens a new Windows-Terminal window: fresh tmux session (`mylib-<pid>`, so the reaper still manages it) + `claude -n <NEW_NAME>` in `WORKTREE`, seeded to read the brief and follow its startup checklist. **It does NOT close the current window.**

Do this **before** the debrief (the brief is already written in step 3, so the new session has everything it needs). The debrief can be slow; spawning first lets the user start working in the new window immediately while this pane closes out.

## 5. Run the debrief → /session-debrief
Now invoke **/session-debrief** end-to-end in *this* (old) pane — captures memory/state/log, commits, posts pulse, and its postflight runs the tmux reaper. This is also what cleans up; `/handoff` does not reap separately. The new window is already live and usable while this runs.

**Tell the debrief which brief to enrich.** State the path explicitly when you invoke it:

> "Enrich the handoff brief at `$HANDOFFS/<NEW_NAME>.md`
> (Phase 2e) — this debrief follows a `/handoff`."

Direct-pass is the primary mechanism and the only one that cannot pick the wrong brief: you
are the actor that just wrote it, in the same conversation. The `.pending-enrichment` entry
from step 3b is the fallback for a debrief run out-of-band later.

## 6. Confirm
Right after step 4, tell the user the new window is up as `<NEW_NAME>` in `<WORKTREE>` and ready (it re-loads the persona, reads the handoff, gives a 3-line status, then waits). Then run the debrief here; when it finishes, this window can be closed — its detached `mylib-*` session is reaped automatically (the new session's SessionStart hook + the next debrief).

## Notes
- Composition only: `/create-handoff-docs` + `/session-debrief` + `skills/handoff/handoff.sh`. No bespoke reaping.
- The launcher loads nvm so `claude` resolves to the working binary (not the Windows npm shim).
- Requires WSL + Windows Terminal (`wt.exe`) interop.
