---
name: resume-sessions
description: Rebuild your whole Claude Code session fleet from a snapshot after a reboot — opens one Windows Terminal window per session, each either RE-ATTACHING to its still-live tmux session (if you only closed windows) or RESUMING it from disk (claude --resume <id> -n <name>) post-reboot, with the tmux label set to the Claude session name. Thin wrapper over executions/session_snapshots.py resume. Defaults to the most recent snapshot; accepts a date. Pairs with /store-sessions.
template: skill-definition
version: 1.1.0
summary: Reopens every stored session in its own window, in its original cwd, labelled with its Claude name, ready to work — reattaching live sessions or resuming dead ones from disk per-session. Auto-reconciles the snapshot against the transcript logs so sessions that rotated generation after the snapshot are never lost. Preview with --dry-run first; opens real windows otherwise.
created: 2026-06-23
last_updated: 2026-07-24
maintainer: pvragon
argument-hint: "[latest|YYMMDD|file] [--dry-run] [--force] [--include-current] [--no-reconcile]"
---

# /resume-sessions

Rebuild the open-session fleet captured by `/store-sessions`. One Windows Terminal window per session, in its original directory, tmux-labelled with the Claude session name, ready to work in.

## First preview, then launch

Always dry-run first so the user sees what will open:

```
python3 ~/ai-workspace/team-lib/executions/session_snapshots.py resume $ARGUMENTS --dry-run
```

Show the plan, then on the user's go-ahead launch for real (drop `--dry-run`):

```
python3 ~/ai-workspace/team-lib/executions/session_snapshots.py resume $ARGUMENTS
```

- **No date** → newest snapshot. **`YYMMDD`** → newest snapshot that day. A **filename/path** → that exact snapshot. (`list` shows what's available.)
- **`--force`** → required to open more than 15 windows.
- **`--include-current`** → also resume the session this command runs from (default: skip it, so you don't duplicate your own window).
- **`--no-reconcile`** → restore the snapshot verbatim, skipping the log-delta step below. Rarely what you want.

## Reconcile — why the snapshot alone is never trusted (on by default)

**No snapshot is current at the moment you need it.** Sessions rotate generation via `/handoff` all day; the snapshot you're restoring was taken before that. So `resume` always unions the snapshot with a scan of the transcripts, and prints what it recovered:

```
Snapshot: 260724-0000-auto-sessions.json — 15 window(s) to open
  + 6 session(s) recovered from transcripts (active after this snapshot; --no-reconcile to skip):
      260707-waystar-claims-ceo-readiness-14    rc-wt/billing-coverage-q3
      260718-mahjong-hand-constituents-5        projects/mahjong-card-db
```

**Each source covers the other's blind spot — neither is sufficient alone.** Verified on 2026-07-24: the midnight snapshot was missing waystar `-14` and constituents `-5`, while a transcript-only rebuild dropped **three** open-but-idle windows the snapshot had.

- **The snapshot is the only record of which windows were OPEN.** That signal does not exist on disk — `list_claude_sessions` computes it from live tmux clients + WSL relay ancestry, and it dies with the tmux server. Transcript mtime shows *activity*, not openness, so an open-but-idle window looks exactly like a closed one.
- **The transcripts are the only current source.** They also survive intact, whereas the session-name records in `~/.claude/sessions/<pid>.json` are PID-keyed — PIDs restart low after every reboot and eventually overwrite old records, so reconstruction quality *decays fastest right after the reboot you need it for*.

Two filters keep the union honest:

- **Headless runs are excluded** — cron/automation sessions never get a `~/.claude/sessions/` record (no `-n` name), so they can't claim a window. Verified against the agent-mailbox triage cron.
- **Retired predecessors are excluded** — `/handoff` writes both the old and new transcript the same day, so a naive union resurrects every superseded generation. Any recovered session whose base name already appears in the fleet at an equal-or-newer generation is dropped (`one-Mahjong-1` loses to `-5`).

**The guarantee is one-directional: reconcile ensures nothing is *missing*, not that nothing is extra.** Unnumbered sessions closed earlier that day can still slip in, since generation can't rank them. That's the right bias — an extra window costs one `Ctrl-D`, a silently-dropped workstream costs the session. Dry-run first and prune there.

## How each window restores (decided at launch, per session)

1. **Original tmux session still alive** (you closed windows but didn't reboot) → **re-attach** to the live session (renamed to its Claude-name label). Perfect, lossless — it's the same running process.
2. **Gone** (post-reboot, tmux server died) → **`claude --resume <sessionId> -n <name>`** from disk in the stored cwd: reloads the full conversation into a fresh, labelled tmux session.

Either way you land "exactly where you left off," minus anything actively in-flight at the instant of shutdown (an un-saved tool result / half-typed message), which isn't on disk.

## Notes

- Opens **real Windows Terminal windows** (`wt.exe`). Launches the first window, **waits for its statusline to warm the shared ccusage cache**, then launches the rest — otherwise N cold statuslines each re-parse the whole JSONL corpus at once (thundering herd → swap thrash → disk pegged for minutes after a reboot). Tunable: `--stagger` (default 2s between windows), `--warm-timeout` (default 45s), `--no-warm` to skip. Needs WSL + Windows Terminal.
- Never double-resumes: if a label is already restored in the same run, later windows just attach to it.
- List/choose snapshots: `python3 ~/ai-workspace/team-lib/executions/session_snapshots.py list`.
