---
name: reap-tmux
description: Clean up orphaned go-created tmux sessions (mylib-<pid>) that are detached and idle or dead. Thin wrapper over skills/reap-tmux/reap_tmux_sessions.sh. Dry-run by default; pass --live to actually kill. Use standalone, or it runs automatically via the SessionStart hook, inside /session-debrief, and as a step of /handoff.
template: skill-definition
version: 1.0.0
summary: Invokes the deterministic tmux reaper and reports the result. Only manages mylib-<pid> sessions (the proliferation source); never touches attached or the current session. Safe by design — Claude conversation state persists to disk and is /resume-able even if a session is reaped.
created: 2026-05-31
last_updated: 2026-05-31
maintainer: pvragon
argument-hint: "[--live] [--grace-min N] [--pattern REGEX]"
---

# /reap-tmux

Reap orphaned `go`-created tmux sessions so they stop accumulating and exhausting RAM/swap.

## Run it

```
~/ai-workspace/team-lib/skills/reap-tmux/reap_tmux_sessions.sh --live $ARGUMENTS
```

- **Runs live by default** (actually kills qualifying orphans), logging to `runtime/logs/tmux-reaper.log`.
- Pass **`--dry-run`** to preview without killing (logs `WOULD-REAP` only). `--grace-min N` tunes the idle threshold (default 120). `--pattern REGEX` overrides the managed-name pattern (default `^mylib-[0-9]+$`).

## Then report

Read the tail of `~/ai-workspace/my-lib/runtime/logs/tmux-reaper.log` and give the user the one-line summary (`managed=… reaped=… kept=…`) plus any `WOULD-REAP`/`REAPED` lines.

## What it does / safety

- Manages **only `mylib-<pid>`** sessions (the `go` proliferation source). Rotate/user-named sessions are ignored.
- Reaps a session only if **detached AND** (idle > grace **OR** a dead shell where claude already exited, idle > 15 min).
- **Never** touches attached sessions or the current one.
- Reaping loses only live tmux scrollback — the Claude conversation is on disk and `/resume`-able.

## Where it's deployed

The same worker script runs live in two places (plus manual `/reap-tmux`):
1. **SessionStart hook** (`~/.claude/settings.json`) — sweeps on every new session start (`--live`).
2. **`/session-debrief`** postflight — sweeps at session wrap-up (`--live`).

(`/handoff` does not reap separately — it relies on the debrief it runs + the new window's SessionStart hook.) To revert any of these to preview-only, swap `--live` for `--dry-run`.
