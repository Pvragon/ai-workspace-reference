---
template: skill-reference
version: 1.0.0
summary: "Session-debrief Phase 2e: verify each subagent's artifacts on disk, read the findings files, promote findings into the findings inbox, and handle a subagent that failed or went silent."
created: 2026-10-06
last_updated: 2026-10-06
maintainer: pvragon
---

# Phase 2e: Verify and Promote

## Contents
- 1 Verify artifacts on disk
- 2 Read the findings files
- 3 Promote findings
- 4 When a subagent fails

Subagent reports are claims. Check the files they were supposed to write, then read what they noticed.

## 1. Verify artifacts on disk

One Bash call with fast greps:

| Subagent | Check |
|---|---|
| A | Today's `## HH:MM — <session>` block in both `short-term/YYMMDD-facts.md` and `-residue.md`; touched `project_*.md` files have `last_touched: <today>` |
| B | `current-state.md` line 1 reads `Last updated: <today>`, and the headlines B returned under `Headlines set` are present |
| C | Today's one-line entry sits just below the marker in `session-log.md` |

All paths are under `$AGENT_MEMORY`.

## 2. Read the findings files

```bash
cat ~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD from session_info.date>-debrief-findings-*.md 2>/dev/null
```

Artifact greps prove the work happened. The findings files are the only channel for what a subagent noticed. A missing findings file means that subagent did not finish its contract: check whether its other work landed.

## 3. Promote findings

`runtime/.tmp` is gitignored and does not survive, so decide each finding now:
- **A durable pattern, or something broken:** append it to today's `short-term/YYMMDD-facts.md`, or to a T2 topic file if it spans sessions.
- **Actionable but undecided:** a `my-lib/backlog/YYMMDD-<slug>.md` item.
- **Routine noise:** drop it.

Then record each promoted finding in the findings inbox:

```bash
python3 ~/ai-workspace/team-lib/executions/findings.py record \
  --source debrief --key "<stable-slug>" --text "<one line>" --once [--hold] [--severity critical]
```

- `--once`, always: a debrief never re-detects a finding, so without it the finding reads as resolved within days.
- `--hold` only when waiting has a growing cost: money, a person waiting, a deadline, something breaking.
- `--severity critical` only for a breaking bug, data loss in progress, or a live production risk, meaning something that gets worse overnight. Stale metadata, a false-positive probe or a suspicion is not critical. Phase 4 reads this flag, so decide it here.

The inbox is read later, on demand. Findings are not announced at close.

## 4. When a subagent fails

- **Finished without a report, but its work is on disk.** Fine. If it was Subagent C, compose the pulse message yourself from the 2b summary in the format in `subagent-c-log.md`.
- **No artifacts and no sign it is running.** Do its work inline by following its instructions file. A slow subagent can still be running unseen, so re-check each target file immediately before writing. Treat a "file modified since read" error as the subagent finishing: re-read, keep the correct version, do not duplicate.
- `regen_current_state.py` is idempotent, so re-running it with the same decisions and notes is safe.
- If a subagent's output is weak or off-target, re-spawn it with a sharper summary rather than rewriting its output in the main context.
- Never re-run a subagent whose writes already landed. If a late report arrives, reconcile it with what is on disk rather than applying it again.
