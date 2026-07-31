---
name: store-sessions
description: Snapshot every open Claude Code session (tmux label + Claude name + sessionId + cwd) to a dated file so the whole fleet can be rebuilt after a reboot / wsl --shutdown. Thin wrapper over executions/session_snapshots.py store. Run it before restarting the computer. Pairs with /resume-sessions. A nightly auto-snapshot (00:00 cron) also runs as a safety net.
template: skill-definition
version: 1.0.0
summary: Captures the current open-session fleet to ~/.claude/session-snapshots/YYMMDD-HHMM-sessions.json (manual snapshots kept forever; nightly --auto ones pruned). The bridge across a reboot, which kills the tmux server and every claude process — only the on-disk JSONL + this snapshot survive. Read-only.
created: 2026-06-23
last_updated: 2026-06-23
maintainer: pvragon
argument-hint: ""
---

# /store-sessions

Snapshot the open Claude/tmux session fleet so `/resume-sessions` can rebuild it after a reboot.

## Run it

```
python3 ~/ai-workspace/team-lib/executions/session_snapshots.py store
```

Writes `~/.claude/session-snapshots/YYMMDD-HHMM-sessions.json` capturing, per live session: original tmux name, derived label (= Claude name), Claude display name, `sessionId`, cwd, status.

## Then report

Relay the stored count and the one-line-per-session list the script prints. Remind the user it's safe to reboot now and that `/resume-sessions` will bring everything back.

## When to use

- **Before** a reboot / `wsl --shutdown` / Windows restart (the event that kills the tmux server and every claude process).
- Any time you want a named restore point of the current fleet.

A nightly auto-snapshot runs at 00:00 via cron (`store --auto`, pruned to the last ~30), so a recent list exists even if you forget — but a manual `/store-sessions` right before shutting down is the freshest.

## Notes

- Read-only; opens/kills nothing. Captures only genuinely-**OPEN** windows by default — detached/closed sessions (ORPHAN/PHANTOM, i.e. windows you already closed; the tmux session just lingers) are skipped so resume doesn't resurrect work you put away. Pass `--include-detached` to keep them.
- See `/resume-sessions` to rebuild, and `list_claude_sessions.py` / `/list-sessions` for the live inventory it's built on.
