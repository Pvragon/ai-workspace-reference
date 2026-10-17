---
template: skill-reference
version: 1.0.2
summary: "Session-debrief Phase 3 detail: what postflight.sh does step by step, its options and overrides, how touched files are found, and how to read the per-step timings it prints."
created: 2026-10-06
last_updated: 2026-10-14
maintainer: pvragon
---

# Phase 3: Postflight

## Contents
- What it does
- Options
- Reading the step timings

## What it does

In order:
1. **Zone.Identifier sweep,** started in the background. It removes WSL `*:Zone.Identifier` junk under `~/ai-workspace` and logs to `runtime/logs/zone-cleaner.log`. It runs in the background because it walks every file in the workspace (about 5.7 million) and nothing after it depends on it. It runs only on WSL; on native Linux such as Omarchy it is skipped and reported as `skipped (not WSL)`.
2. **tmux reap.** Kills orphaned, detached `mylib-<pid>` sessions; never attached or current ones.
3. **Transcript extraction.** Converts new session logs into filtered markdown under `$AGENT_HOME/transcripts/`. Preflight already started it, so this is usually quick.
4. **System-state dump.** Refreshes crontab, hooks, settings and MCP snapshots under `$AGENT_HOME/system-state/`. Usually the slowest local step, about 7 seconds.
5. **Transcript archive.** At most once a day, moves session logs older than 14 days out of `~/.claude/projects/` into `projects-archive/`.
6. **Claude adapters.** Re-links memory symlinks and backs up config.
7. **Session title.** Sets the `/resume` title: the `/rename` name if there is one, else `YYMMDD-HH:MM <session-name>`.
8. **Memory upkeep.** A small capped batch of safe frontmatter fixes, a hygiene check, and a rerank of `MEMORY.md`. It runs before the commit so its edits go in with it.
9. **Agents repo.** Commits and pushes the touched files, every changed file under `memory/`, and the transcripts and system-state from steps 3 and 4.
10. **my-lib repo.** Commits only the touched files. Does not push.
11. **Pulse post.** Posts the pulse message.

Every step except the commits is non-fatal.

Preflight also starts background jobs that postflight relies on: transcript extraction and the system-state dump get a head start, and `session_snapshots.py store --tag debrief --keep 40` records which sessions are open, which is what `/resume-sessions` rebuilds from. Their logs are in `runtime/logs/`.

## Options

| Option | Use |
|---|---|
| `--session-marker "<token>"` | Finds this session's log; preferred |
| `--session-id "<uuid>"` | Instead of the marker, if you know the ID |
| `--mylib-files "<paths>"` | Override the auto-detected my-lib files; `""` skips that commit |
| `--agents-files "<paths>"` | Add agents-repo files; `""` skips that commit |
| `--skip-pulse` | Do not post |
| `--skip-commit` | Dry run: no commits |
| `--legacy-add-all` | Stage everything; only with a stated reason |

Touched files are detected from this session's log by `extract_touched_files.py`, which needs the marker or the session ID. If detection fails for any reason (no marker or ID, a marker that matches no log, or an empty result), postflight exits with an error and asks for the file lists. `--skip-commit` and `--legacy-add-all` skip detection. Pass the lists only when you need to exclude a file or detection fails.

Detection only sees Edit/Write calls, so the agents commit also stages every changed or new file under `memory/`. That catches memory written by scripts or through Bash. Everything under `memory/` is agent-written memory, so committing it is always correct.

## Reading the step timings

The summary ends with `step times`, the wall time of each step. If a debrief felt slow, read that block before changing anything. The likely slow steps are the agents-repo push and the pulse post, which wait on the network.
