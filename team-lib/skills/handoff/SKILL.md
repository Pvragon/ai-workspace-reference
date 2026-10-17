---
name: handoff
description: "Rotate to a fresh session in one step: write the handoff brief, open a new terminal whose Claude reads it and continues (same name with -N, same worktree, same persona), then debrief the old pane. Use when the user says to start a new thread or context is getting full."
template: skill-definition
version: 2.5.5
summary: >-
  The session-rotate orchestrator: /create-handoff-docs writes the brief (it owns the format and
  the startup checklist; this skill supplies only WORKTREE and PERSONA), handoff.sh spawns a new
  seeded window, then /session-debrief runs in the old pane. Spawn before debrief so work
  continues immediately. Requires WSL + Windows Terminal, or Hyprland (Omarchy) + foot.
created: 2026-05-31
last_updated: 2026-10-16
maintainer: pvragon
argument-hint: "(no args — derives everything from the current session)"
listing: "on"
category: sessions
---

# /handoff — rotate to a fresh, seeded session

Wrap up this thread and continue in a brand-new window, by composing existing skills. The new session picks up exactly where this one left off: same name (incremented), same worktree, same persona, brief already read.

## 1. Compute the new session name — MUST match `YYMMDD-<descriptive-name>`
`NEW_NAME` MUST follow the standard thread-naming convention: a **`YYMMDD-` date prefix** + a descriptive
slug. There are exactly two valid shapes:

- **Current name already starts with a `YYMMDD-` date** → keep the date and append/increment a `-N` suffix:
  - ends in `-<integer>` → increment it (`260531-foo-2` → `260531-foo-3`)
  - otherwise → append `-2` (`260531-foo` → `260531-foo-2`; "no suffix" = n=1, so next is n=2)
- **Current name is DATELESS** (no leading `YYMMDD-`, e.g. a descriptive debrief title like
  `waystar-claims-working-view-skills`) → do NOT propagate the dateless name. Mint a fresh conventional
  name: **`<today-YYMMDD>-<short-descriptive-slug>`** for the handoff's scope
  (e.g. handing off "add ICN/ACNT columns" → `260724-waystar-deliverable-icn-acnt-columns`).

**Sanity gate before proceeding: `NEW_NAME` must match `^[0-9]{6}-`.** If it doesn't, you built it wrong —
fix it here. (Origin 2026-07-24: a dateless parent name propagated a dateless child thread that the operator had
to rename by hand. The date prefix makes threads self-sort chronologically — same rule as file naming.)

## 2. Capture worktree + active persona
- **Worktree:** the worktree this thread is working in — `git -C "$PWD" rev-parse --show-toplevel` (fall back to `$PWD`). Call it `WORKTREE`. The new session must run here.
- **Active persona:** if a persona/role skill is active in this thread (e.g. `rc-cto`, loaded earlier), note its skill **name** so the brief can re-load it. If none, skip.
  The new session re-loads it **through the Skill tool**, which refuses a `listing: user-only` skill — so a persona skill must be `on` or `name-only`, never `user-only` (proven 2026-10-16; the AGENTS.md metadata standard says the same).

## 3. Generate the handoff brief → /create-handoff-docs
First resolve the agent's handoffs directory — do NOT write a literal agent name:

```bash
HANDOFFS=$(python3 ~/ai-workspace/team-lib/executions/agent_paths.py | awk '$1=="handoffs_dir"{print $2}')
```

`agent_paths.py` finds the agent home by looking for `identity.md`, so it is correct for whichever
agent is running and refuses to guess when it cannot decide. `/session-debrief` resolves the SAME
directory the same way; if these two ever disagree, the debrief addendum lands where nobody reads it.

Then invoke **/create-handoff-docs**, saving the brief to **`$HANDOFFS/<NEW_NAME>.md`**.

> **⚑ The brief is NOT self-contained.** It is a pointer to what changed, never a replacement for
> the agent's own state — which is why it opens with a startup checklist whose second item is a
> full memory cold-start. That requirement and its wording live in **`/create-handoff-docs`
> Step 3a**, which owns the brief format. Rationale and history are there too.

> **Why NOT `~/.claude/handoffs/`:** that path is inside the PROTECTED `.claude/` directory, so the Write tool prompts for permission on every brief — and a PreToolUse allow-hook cannot rescue protected-dir writes (verified 2026-06-25, same root cause as memory writes; see [[reference_claude-protected-dir-memory-write-prompts]]). the agent's `handoffs/` dir is non-protected and already allow-listed (`Edit(//…/ai-workspace/agents/**)`) AND covered by the `allow_memory_writes` hook's `handoffs/` segment, so it never prompts in any mode. It's equally global/stable for the new session to read.

**The brief's format — including the startup checklist — is `/create-handoff-docs`'s to define, not
this skill's to restate.** Invoking it loads its SKILL.md into context, so Step 3a arrives as a real
read, not a deferred one. Pass it the two parameters it asks for and let it emit the checklist:

| Parameter | Value from this rotation |
|---|---|
| `WORKTREE` | the worktree from step 2 |
| `PERSONA` | the active persona from step 2, or "none" |

> **⚑ Do NOT re-inline the checklist here, however tempting.** It lived in this file and *only* this
> file from 2026-08-07 to 2026-08-08, which meant a brief produced by invoking
> `/create-handoff-docs` directly — a documented, encouraged entry point — carried no memory
> cold-start at all. The fix had landed in the caller instead of in the owner of the format. Two
> copies of one requirement have no owner for the diff; see
> `feedback_owned-path-hardcoded-elsewhere`.

**Rotation-specific, and why the addendum item is acute here (2026-07-30).** Step 4 spawns the new
window *before* step 5 runs the debrief, so the brief is frozen before the debrief can surface
anything. On 2026-07-30 the single most important finding of the session had to be hand-patched
into an already-launched brief; it only worked because the new window happened to be untouched. Had
it been in use, its work queue would have been missing its top item. Checklist item 4 converts that
race into a documented pull — the new session knows to look, instead of this one hoping to patch in
time.

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
- Requires WSL + Windows Terminal (`wt.exe`) interop, or Hyprland (Omarchy) with `foot`, launched via `uwsm-app` on the current workspace. Verified on Omarchy 2026-10-14.
- Hyprland take-over-in-place (`~/.config/hypr/handoff-park-workspace` set): no new window lands in the tile. The new session starts detached, the old session gets a parked window on the park workspace, then this window's tmux client switches to the new session. Same tile, focus never moves, independent of which window is active (v1.4.0, 2026-10-16).
