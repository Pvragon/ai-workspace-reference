---
template: skill-reference
version: 2.0.2
summary: "Instructions for session-debrief Subagent C (session log and pulse): append the one-line session-log entry and compose the pulse-channel debrief message. Read by the subagent itself."
created: 2026-10-06
last_updated: 2026-10-20
maintainer: pvragon
---

# Subagent C: Session Log and Pulse

Your prompt gives you the preflight report path, the session name and a session summary. Read the report. Bind `$AGENT_MEMORY` to its `t1_files_staged.memory_dir_canonical`; if the field is missing, stop and say so. Never write through `~/.claude/projects/<cwd>/memory/`, because that protected path prompts on every write. **Write memory files with the Edit or Write tool, never through Bash** (no heredocs, `sed -i`, `echo >>` or inline Python). Two things depend on it: postflight finds which files to commit from Edit/Write calls, and the memory access counter only reinforces a file on those calls.

## 1. Session-log line

`YYMMDD` and the date below mean `session_info.date`.

Insert one line into `$AGENT_MEMORY/session-log.md` immediately after the `<!-- entries below -->` marker, so the newest entry is on top:

```
YYYY-MM-DD | <session-name> | <key topics and outcomes>
```

The whole entry is one physical line of at most 200 characters. The log is scanned, not read; detail belongs in the day's `short-term/YYMMDD-facts.md`, which Subagent A writes.

## 2. Pulse message

Compose, in exactly this form, one line:

```
XX Claude Debrief [<start time> - <end time>]: <summary>
```

Take the times from `session_info.approx_start` and `session_info.end`, as given (`HH:MM`, or `MM-DD HH:MM` on both when `spans_midnight` is true). The summary is 1 to 3 sentences on outcomes, decisions and next steps.

## Findings file (your last disk action)

Append to `~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-log.md`, creating it if absent:

```
## log — HH:MM
- <finding>
```

A finding is something the orchestrator could not learn by grepping what you wrote: a log entry that contradicts the summary, a timestamp that looks wrong, a gap you worked around. Write `- none` if you have none. Skip routine notes. Your report may never be read; this file will be.

## What to return

End your response with these lines:
- `session-log.md updated: yes`
- `PULSE_MESSAGE: <the full pulse message on one line>`
