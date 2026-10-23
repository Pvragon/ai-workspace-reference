---
name: session-debrief
description: "Runs the end-of-session procedure: captures learnings into memory topic files, verifies index consistency, updates current-state.md, and syncs changes to team-lib. Use when the user asks for a session debrief, says they are wrapping up or ending the session, or before closing a window after a /handoff."
summary: "Run at end of a work session to persist learnings, check index health, update workspace current state, and propagate improvements to team-lib. A short router: preflight script, three parallel subagents that read their own instructions, on-disk verification, postflight script, one-line close."
version: 3.2.0
created: 2026-02-20
last_updated: 2026-10-22
maintainer: pvragon
listing: "on"
category: sessions
---

# Session Debrief

Capture what this session learned, keep memory and current-state true, and commit it. Scripts do the deterministic work (`preflight.sh`, `postflight.sh`); you and three subagents do the judgment work. Each phase below says what to do and links the reference file that holds the detail. Open a reference file when you reach its step, not before.

## Rules that hold on every run

1. **Write memory only through `$AGENT_MEMORY`**, bound from preflight's `t1_files_staged.memory_dir_canonical`. Never write through `~/.claude/projects/<cwd>/memory/`: it is under a protected directory, so every write prompts and no hook can prevent it.
2. **Never edit `current-state.md` by hand,** including in a fallback. `regen_current_state.py` is its only writer, which is what keeps concurrent debriefs from clobbering it.
3. **Spawn subagents without `name:`.** A named agent stays alive as a peer and its report never comes back as a result.
4. **Verify subagent work on disk, and read the findings files, before postflight.** Reports can go missing; files cannot. `runtime/.tmp` does not survive, so promote what matters.
5. **Pass `--session-marker` from preflight to postflight.** It is how postflight finds this session's log among concurrent ones.
6. **At close, findings get one line of keys only,** unless you recorded that finding with `--severity critical` in Phase 2e.
7. **Handoff briefs are append-only, and never the newest file in `handoffs/`.** Concurrent sessions write briefs the same day, so the newest is often another thread's.

## Phase 1: Preflight

```bash
bash ~/.claude/skills/session-debrief/preflight.sh
```

It prints a JSON report and saves the same report to the file named in `session_info.report_path`. Keep three values from it:

| Value | From | Used for |
|---|---|---|
| Report path | `session_info.report_path` | handed to every subagent |
| Session marker | `session_info.session_marker` | postflight |
| `$AGENT_MEMORY` | `t1_files_staged.memory_dir_canonical` | every memory path |

`$AGENT_HOME` is the parent of `$AGENT_MEMORY`. Bind both from the report; never use a path you inferred or remembered. Dates in file names (`YYMMDD`) come from `session_info.date`, so a debrief that crosses midnight still finds its files. `git_changes` covers my-lib only, so use `git log` in any other repo you worked in.

## Phase 2: Judgment work

### 2a. Fix trivial preflight issues

Registries and the memory index are generated, so never hand-edit a `registry/*.yaml` entry or a `MEMORY.md` row. From `registry_issues` and `memory_issues`:
- **`unregistered`, `missing_registry`, `unindexed`:** make sure the file has a `summary:` in its frontmatter. Registries rebuild at push and nightly, and postflight regenerates `MEMORY.md`, so the issue can show until then.
- **`missing_file`, broken links:** nothing to do by hand; the next rebuild drops the entry. If the file was deleted by mistake, restore it.

### 2b. Write the session summary

Three to five specific sentences: the goal, what was decided, built or discovered, and what is still open. "Rebuilt the debrief router, cut the main-agent prompt payload, pushed nothing" beats "worked on skills". The subagents rely on this instead of re-reading the session.

### 2c. Spawn the three subagents

How many run at once depends on `session_info.machine_load` from preflight:

| `fanout_verdict` | `safe_parallel_workers` | Do this |
|---|---|---|
| `parallel-ok` | 3 or more | Spawn A, B and C in one message |
| `parallel-ok` | 2 | Spawn A and C together; spawn B after A finishes |
| `single-worker` | 1 | Spawn A, then B, then C, one at a time |
| `serial-only` or `unknown` | 0 | Spawn nothing; do A, then B, then C yourself, following each instructions file |

When they run in sequence, A goes before B, so B sees the sweep result and any T2 file A created.

Use the Agent tool, `subagent_type: "general-purpose"`, `model: "sonnet"`, no `name:`. If the Agent tool offers `run_in_background`, set it to `false`. If this harness runs subagents in the background anyway, each report arrives as a notification; wait for all of them. If a spawn must be named or backgrounded, end its prompt with: "Final step: send this report via SendMessage to main; your plain final text is not delivered." Each prompt is only this, filled in:

```
You are session-debrief Subagent <A|B|C>.
Read and follow ~/.claude/skills/session-debrief/reference/<file>.
Preflight report: <session_info.report_path>
Session name: <the /rename name, or a 2-4 word name>
Session summary: <the 2b summary>
```

| Subagent | Instructions file | Owns |
|---|---|---|
| A, memory | `subagent-a-memory.md` | T1 facts and residue, T2 lifecycle fields, close/age sweep |
| B, state | `subagent-b-state.md` | T2 index flags, `current-state.md` render |
| C, log | `subagent-c-log.md` | session-log line, pulse message |

Do not paste the report or the instructions into the prompt; the subagent reads both. Wait until all three have finished. If Subagent C's report never arrives, compose the pulse message yourself from the 2b summary, in the format in `reference/subagent-c-log.md`.

### 2d. Sync to team-lib (rarely needed)

If `sync_needed` lists `agents_md`, run the `push-agents-to-template` skill. For `skill:<name>`, propagate only stable, generally useful changes. Most sessions skip this.

### 2e. Verify on disk, then promote findings

Follow [reference/verify-and-promote.md](reference/verify-and-promote.md): grep each subagent's artifacts, read the findings files, promote what matters into the findings inbox, and handle a subagent that failed.

If the caller gave you a handoff brief path ("enrich the brief at …"), or `$AGENT_HOME/handoffs/.pending-enrichment/` holds an entry, also follow [reference/handoff-enrichment.md](reference/handoff-enrichment.md).

Collect the pulse message from Subagent C and the candidates from Subagent A. Show the user only lens candidates that passed all three placement clauses; reusable-method candidates wait for a second use case. Do not act on either.

## Phase 3: Postflight

```bash
bash ~/.claude/skills/session-debrief/postflight.sh \
  --session-name "<session-name>" \
  --session-marker "<session_info.session_marker>" \
  --pulse-message "<pulse message from Subagent C>"
```

It commits the agents repo (and pushes it), commits my-lib (no push), posts the pulse message, and runs housekeeping. Touched files are found automatically, and every changed memory file is committed with them. Overrides, the full step list, and how to read its step timings are in [reference/postflight.md](reference/postflight.md).

## Phase 4: Close

Report briefly: memory files written, registry or index fixes, current-state changes, any team-lib sync, commit results, the session-log entry, the pulse post, and whether a handoff brief got an addendum. Read postflight's `✗` lines and report each one; a failed agents-repo push is non-fatal but leaves the memory commit unpushed. Then follow [reference/close-out.md](reference/close-out.md) for the findings line and the stale-findings offer. Both have strict wording rules.

## Phase 5: Close a parked handoff pane (last step, always run)

```bash
python3 ~/.claude/skills/session-debrief/close_parked_session.py
```

Run it after the Phase 4 report, as the very last thing. It acts only in a pane that `/handoff` parked (tmux option `@handoff_parked`); anywhere else it says so and does nothing. In a parked pane it keeps the window open if the operator typed in this session after the park, if postflight did not run, or if background work is still unreported; otherwise a small pane counts down 60 seconds (Ctrl-C keeps the window) and kills this tmux session. Relay its one line. Decisions are logged to `~/.local/state/handoff/handoff.log`.

## Maintaining this skill

my-lib is where this skill is edited; team-lib holds a byte-identical published copy, including `reference/` and all three scripts. Agent paths are written through `$AGENT_MEMORY`, `$AGENT_HOME` and `~/.claude/skills/session-debrief/`. The files still assume the workspace layout (`~/ai-workspace/my-lib`, `~/ai-workspace/team-lib`), and the pulse prefix `JH` names this operator. Any difference between the two copies is drift: fix it by re-copying from my-lib, never by editing team-lib. Keep this file a router. Detail goes in `reference/`, and each rule carries a one-line reason, not an incident history.
