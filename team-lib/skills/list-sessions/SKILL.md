---
name: list-sessions
description: List the Claude Code sessions that are open right now, showing BOTH identifiers side-by-side — the tmux name (mylib-<pid>) and the Claude name (the /rename or -n display name) — plus worktree, status, and sessionId. Thin wrapper over executions/list_claude_sessions.py. Also flags orphaned sessions (window closed but tmux survived) as reap candidates. Use when you ask "what sessions / terminals do I have open", "which window is X in", or before reaping/rotating.
template: skill-definition
version: 1.0.0
summary: Joins the tmux view (mylib-<pid>) to the Claude view (/rename name + sessionId) for every open window, using live-client + WSL-relay-ancestry liveness so phantom/orphan windows are correctly separated from genuinely-open ones. Read-only.
created: 2026-06-23
last_updated: 2026-06-23
maintainer: pvragon
argument-hint: "[--all] [--json]"
---

# /list-sessions

Show every Claude Code session that's open right now, with its **tmux identifier** and its **Claude identifier** next to each other — the two names neither tool shows you together.

## Run it

```
python3 ~/ai-workspace/team-lib/executions/list_claude_sessions.py $ARGUMENTS
```

- **No args** — prints a table of genuinely-**OPEN** sessions and a one-line footer counting any orphan/phantom windows.
- **`--all`** — also lists `ORPHAN` (detached, window-closed) and `PHANTOM` (client lingering, no live terminal) sessions in the table.
- **`--json`** — structured output for chaining (implies `--all`).

## Then report

Relay the table to the user as-is (it's already aligned and marks `<- this window`). If there are orphans, note them and offer `/reap-tmux` to clean up.

## How it decides what's "open" (the reliable recipe)

A tmux session (`mylib-<pid>`, named by the `go` launcher after the *launcher* pid) and a Claude session (named via `/rename` or `claude -n`, stored in `~/.claude/sessions/<claude-pid>.json`) are two identifiers for the same window, and neither side stores the other's name. The script joins them:

1. `tmux list-clients` → sessions that currently have a client (candidate-open).
2. **WSL relay ancestry** → walk the client pid's parents; a live `Relay(...)` ancestor proves a real terminal window is still behind it. The relay dies when the window closes, so this survives WSL's "tmux outlives the window" leak — which the `attached=1` flag does **not**.
3. `tmux list-panes` → `pane_pid` is the claude process (or its wrapper); descend to the pid that owns a `sessions/<pid>.json`.
4. `sessions/<claude-pid>.json` → `name` (the `/rename`/`-n` value), `sessionId`, `cwd`, `status`.

States: **OPEN** (live client + live relay), **PHANTOM** (client but no relay — window closed), **ORPHAN** (no client at all — window closed, session survived → reap).

## Notes

- Read-only — never kills or mutates anything. Reaping is a separate step (`/reap-tmux`).
- Linux/WSL-specific (reads `/proc` + tmux). No-ops cleanly when there's no tmux server.
- The `sessionId` in `--json` is the value you'd pass to `/resume`.
