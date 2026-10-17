---
template: skill-reference
version: 2.0.1
summary: "Instructions for session-debrief Subagent B (current state): set cs_section/cs_headline flags on T2 files, demote stale in-flight items by last_touched, and render current-state.md through regen_current_state.py. Read by the subagent itself."
created: 2026-10-06
last_updated: 2026-10-06
maintainer: pvragon
---

# Subagent B: Current State Update

## Contents
- Inputs and the one rule
- 1 Read recent session-log entries · 2 Set index flags
- 3 Demote stale in-flight items · 4 The In Flight cap
- 5 Render
- Findings file · What to return

`current-state.md` is a derived index over the T2 project files. You set flags on those files, then run the renderer, which is the file's only writer.

## Inputs and the one rule

Your prompt gives you the preflight report path, the session name and a session summary. Read the report; note `stale_flags` and `git_changes`. Bind `$AGENT_MEMORY` to its `t1_files_staged.memory_dir_canonical` and write memory only under that path; if the field is missing, stop and say so. "Today" means `session_info.date`.

**Never edit `current-state.md` directly.** The renderer holds a lock and writes atomically, so hand edits reintroduce the race between concurrent debriefs, and the next render overwrites them anyway.

**Write memory files with the Edit or Write tool, never through Bash** (no heredocs, `sed -i`, `echo >>` or inline Python). Two things depend on it: postflight finds which files to commit from Edit/Write calls, and the memory access counter only reinforces a file on those calls. Set index fields with Edit; the renderer in step 5 is the only script that writes.

Each T2 file carries two index fields in its frontmatter:
- `cs_section: in_flight | handed_off | follow_on`: which section shows the item. No field means not shown.
- `cs_headline: "**Name** — <status in 25 words or fewer>"`: the exact rendered line.

Subagent A owns the lifecycle fields (`status`, `last_touched`, `resolves_when`, `resume_via`, `close_signal`) on the same files. Touch only your two fields.

## 1. Read recent session-log entries

Read the 5 newest entries in `$AGENT_MEMORY/session-log.md`. They are at the top of the file, just below the `<!-- entries below -->` marker, not at the end.

## 2. Set index flags

For each workstream this session touched, set `cs_section` and `cs_headline` on its T2 file. Use `in_flight` for actively driven work, `handed_off` when someone else has the ball, `follow_on` for parked cleanup. Keep the headline to 25 words; depth belongs in the T2 body.

## 3. Demote stale in-flight items

Apply this only to items with `cs_section: in_flight`. Never apply it to `handed_off` or `follow_on`: those hold work that is quiet by design, and the dormancy sweep ages them out.

For each in-flight item:

```
demote if (today − last_touched) > 14 days    (missing last_touched counts as stale)
```

Nothing else demotes an item. How often the session log mentions it does not matter: an item touched today stays, and one untouched for 32 days goes, however often it was discussed. Read the `last_touched` field; do not infer staleness from prose.

To demote, change `cs_section` to `handed_off` or `follow_on`, or delete both index fields to drop the item. Its state stays in the T2 body. Items the close/age sweep archived already have their index fields cleared.

Immediately before rendering, run `git -C "$AGENT_MEMORY" status --short` and look for new untracked `project_*.md` files. Subagent A may have created this session's T2 file after you started, and the session's headline belongs on that file.

## 4. The In Flight cap

The renderer shows at most 5 in-flight items, the freshest by `last_touched`, and prints a line naming any it withheld. If that line appears, those items still need a real decision in step 3.

## 5. Render

This step writes the file, and it is the only one that does:

```bash
python3 ~/ai-workspace/team-lib/executions/regen_current_state.py \
  --today YYYY-MM-DD \
  --add-decision "YYYY-MM-DD: <decision from this session>" \
  --add-note "<pointer at the next actual work>"
```

Pass one `--add-decision` per decision worth logging; old ones are pruned automatically. Pass one to three `--add-note` items pointing at the next actual work, or none, or `--clear-notes` to reset them. Blockers are kept verbatim and the renderer has no flag to change them; if one must change, list it under "Flagged for user attention". Both flags are idempotent, so re-running with the same text does nothing. Do not grep first to check whether a decision already landed; the script checks inside its lock.

## Findings file (your last disk action)

Append to `~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-state.md`, creating it if absent:

```
## state — HH:MM
- <finding>
```

A finding is something the orchestrator could not learn by grepping the files you wrote: a demotion you suspect is wrong, a rule that misfired, a contradiction, a gap you worked around. Write `- none` if you have none. Your report may never be read; this file will be.

## What to return

End your response with these lines:
- `current-state.md updated: yes/no`
- `In Flight count: <N>`
- `Headlines set: <cs_headline values you wrote>`
- `Items demoted: <count> (<workstream → section>, ...)`
- `Items removed: <count>`
- `Flagged for user attention: <list or none>`
