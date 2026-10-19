---
template: skill-reference
version: 2.0.3
summary: "Instructions for session-debrief Subagent A (memory capture): write T1 facts and residue, update T2 workstream lifecycle fields, run the close/age sweep, and return lens and reusable-method candidates. Read by the subagent itself."
created: 2026-10-06
last_updated: 2026-10-19
maintainer: pvragon
---

# Subagent A: Memory Capture

## Contents
- Inputs and the path rule
- 1 T1 facts · 2 Residue
- 3 T2 lifecycle fields
- 4 Close/age sweep
- 5 Topic files and reusable methods · 6 Lens candidates
- Findings file · What to return · Boundaries

You capture this session into the memory architecture. The framing for every tier, and the T2 lifecycle fields, is in `$AGENT_MEMORY/project_memory-architecture-layers.md`; read its §"T2 workstream-lifecycle metadata" if a field below is unclear.

## Inputs and the path rule

Your prompt gives you the preflight report path, the session name and a session summary. Read the report first. "Today" and `YYMMDD` mean `session_info.date`; `HH:MM` is the current local time.

Bind `$AGENT_MEMORY` to the report's `t1_files_staged.memory_dir_canonical`. If that field is missing, stop and say so. Every memory path below means a path under `$AGENT_MEMORY`: `memory/project_x.md` is `$AGENT_MEMORY/project_x.md`. Never write through `~/.claude/projects/<cwd>/memory/`. That alias resolves to the same files, but it sits under a protected directory, so every write prompts for permission and no hook can prevent it.

**Write memory files with the Edit or Write tool, never through Bash** (no heredocs, `sed -i`, `echo >>` or inline Python). Two things depend on it: postflight finds which files to commit from Edit/Write calls, and the memory access counter only reinforces a file on those calls. The one exception is `sweep_workstreams.py` in step 4, a script that writes its own files.

You do no git, no network writes and no destructive commands. Postflight commits.

## 1. T1 facts

Append a `## HH:MM — <session-name>` block to the file at `t1_files_staged.facts_path`. Bullet the specific facts the session surfaced: decisions, observations, numbers, `file:line` references. The file already has frontmatter; append below it and never rewrite the file.

## 2. Residue

Append a `## HH:MM — <session-name>` block to the file at `t1_files_staged.residue_path`, in exactly this form:

```
**Direction:** <1 sentence: where things were trending>
**Unresolved:** <1 sentence: what is open or pending>
**Salient:** <1 sentence: what felt important or surprising>
```

Keep it under about 500 tokens. Residue is texture, not facts.

## 3. T2 lifecycle fields

For each workstream the session actively touched, find or create `memory/project_<name>.md` and set its lifecycle frontmatter:

| Field | Value |
|---|---|
| `last_touched` | today, `YYYY-MM-DD` |
| `status` | `in-flight`, `handed-off`, `follow-on` or `archived`, if it changed |
| `resolves_when` | the trigger that closes it; required for `handed-off` and `follow-on` |
| `resume_via` | the single most useful cold-start pointer |
| `close_signal` | a machine-checkable trigger, wherever one exists (see step 4) |

Status meanings: `in-flight` is being driven this week; `handed-off` means someone else has the ball; `follow-on` is known cleanup with no external trigger; `archived` was resolved this session. If the session changed substantive state, also append a one-liner under the file's `## Recent activity` section.

**You own the lifecycle fields; Subagent B owns the index fields** (`cs_section`, `cs_headline`). You both edit the same files at the same time, split by field. One exception: if you create a T2 file this run, **or revive a dormant one** (status back to `in-flight`, by edit or `--revive`), set its `cs_section` and `cs_headline` yourself and say so in your return. B cannot see a file that did not exist, or was dormant, when it started.

**Read the file body before writing `status`, `resolves_when` or `close_signal`.** Each is a claim about whether something has happened, and the body may already say otherwise. Never write one from the session summary alone.

## 4. Close/age sweep

```bash
python3 ~/ai-workspace/team-lib/executions/sweep_workstreams.py --apply
```

It scans every `memory/project_*.md`:
- **Close detection.** Checks each `close_signal` against live sources (ClickUp, GitHub, files) and archives anything satisfied.
- **Dormancy.** Marks any open item whose `last_touched` is older than `--age-days` (default 20), and not `pin: true`, as `dormant`. Dormancy removes it from current-state, never from memory. It needs nothing from anyone: no backlog item, no disposition step.
- **Revival.** A dormant item whose `last_touched` moves past `dormant_since` returns to the status it held before dormancy (`dormant_from`; `in-flight` if unrecorded). `--revive NAME` forces it without an edit.

Report its `closed_by_signal`, `went_dormant`, `revived`, `needs_attention` and `errors` in your return.

For open items with no `close_signal`, grep the 5 newest session-log entries against `resolves_when`. On a clear match, set `status: archived` and append a `## Archived YYYY-MM-DD` note.

When you set up a `handed-off` or `follow-on` item, add a `close_signal` wherever an objective trigger exists, so the sweep can retire it from whatever session eventually closes it. Supported kinds are exactly `clickup`, `clickup-done`, `pr`, `pr-any`, `file`, `grep` and `judgment`, for example `clickup:<id>`, `pr:<owner>/<repo>#<n>`, `file:<path>`, `grep:<path>::<regex>`. Any other kind errors on every sweep. There is no negated form; when nothing fits, use `judgment:<reason>`.

## 5. Topic files and reusable methods

Only when the session produced a cross-session pattern. Most sessions do not.
- **A reusable fact or pattern:** create or update `memory/<topic>.md` with a `summary:` in its frontmatter. The memory index is regenerated from that field.
- **A reusable method** (a workflow, rubric, orchestration shape, how-to): this is T2 procedural knowledge, not a lens. Return it as a reusable-method candidate. If it has a concrete artifact, suggest turning that into a skill once a second use case exists.

If you want to write "during this session…", it is T1, not T2.

## 6. Lens candidates

Return something as a lens candidate only if it passes all three clauses of the placement rule in `project_memory-architecture-layers.md` §"Placement rule":
1. It colors how inputs are interpreted; it is not a fact to look up or a method to apply.
2. Forgetting it would cause a wrong decision, not merely a slower one.
3. For T3, a tight `tool_match` and `path_pattern` can fire it only when it matters. If it applies everywhere, it is T4.

Anything that fails a clause goes to step 5. Never promote a lens yourself; the user curates lenses.

## Findings file (your last disk action)

Append to `~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-memory.md`, creating it if absent:

```
## memory — HH:MM
- <finding>
```

A finding is something the orchestrator could not learn by grepping the files you wrote: a surprise, a contradiction, a number that looks wrong, a rule that misfired, a gap you worked around. Write `- none` if you have none. Skip routine notes such as "wrote 3 files". Your report may never be read; this file will be.

## What to return

End your response with these lines:
- `Files written: <paths>`
- `Workstreams updated: <name=status, ...>`
- `Workstreams archived (resolves-when fired): <names or none>`
- `T2 files created and indexed by me: <names or none>`
- `Reusable-method candidates (T2): <list or none>`
- `Lens candidates (T3/T4): <list or none>`
- `Sweep: <closed_by_signal / went_dormant / revived / needs_attention / errors>`

## Boundaries

Do not edit AGENTS.md, CLAUDE.md or identity files; return candidates instead. Do not touch `current-state.md` or `session-log.md`; Subagents B and C own them.
