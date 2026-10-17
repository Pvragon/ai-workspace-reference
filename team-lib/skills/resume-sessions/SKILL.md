---
name: resume-sessions
description: Rebuild your whole Claude Code session fleet from a snapshot after a reboot — opens one terminal window per session (Windows Terminal on WSL, foot on Hyprland/Omarchy), each either RE-ATTACHING to its still-live tmux session (if you only closed windows) or RESUMING it from disk (claude --resume <id> -n <name>) post-reboot, with the tmux label set to the Claude session name. Thin wrapper over executions/session_snapshots.py resume. Defaults to the UNION of the newest /store-sessions snapshot and the newest debrief snapshot; accepts a date. Pairs with /store-sessions.
template: skill-definition
version: 1.1.5
summary: "Reopens every stored session in its own window and original cwd, labeled with its Claude name: reattaches live tmux sessions or resumes dead ones from disk. Default fleet is the union of the newest manual and debrief snapshots. Reconcile is opt-in. Preview with --dry-run, list the windows in chat, launch only on the operator's reply."
created: 2026-06-23
last_updated: 2026-10-16
maintainer: pvragon
argument-hint: "[YYMMDD|file] [--dry-run] [--force] [--include-current] [--reconcile]"
listing: name-only
category: sessions
---

# /resume-sessions

Rebuild the open-session fleet captured by `/store-sessions`. One terminal window per session (Windows Terminal on WSL, foot on Hyprland/Omarchy), in its original directory and, on Hyprland, its original workspace, tmux-labelled with the Claude session name, ready to work in.

## First preview, then launch

Always dry-run first so the user sees what will open:

```
python3 ~/ai-workspace/team-lib/executions/session_snapshots.py resume $ARGUMENTS --dry-run
```

Show the plan as a short table in chat with a **numbered `#` column first**, then label, directory, and which snapshot it came from, and stop. The numbers are how the operator points at windows (the operator, 2026-09-18: "it helps for each one to have a number label ... so that we can say, 'launch these ones but not that one'"). If he excludes some, `resume` has no `--exclude` flag: build a filtered snapshot in `my-lib/runtime/.tmp/YYMMDD-HHMM-resume-*.json` (same JSON shape, `kind: manual`, only the wanted sessions) and pass that path as the positional argument. **Do not wrap the go-ahead in an `AskUserQuestion` selection** (the operator, 2026-09-08: "just give me the list of windows and then I'll confirm the launch"). When he replies with a go, launch for real (drop `--dry-run`):

```
python3 ~/ai-workspace/team-lib/executions/session_snapshots.py resume $ARGUMENTS
```

- **No date** → the **union of the newest manual snapshot and the newest debrief snapshot** (see below). **`YYMMDD`** → newest snapshot that day, alone. A **filename/path** → that exact snapshot, alone. (`list` shows what's available.)
- **`--force`** → required to open more than 15 windows.
- **`--include-current`** → also resume the session this command runs from (default: skip it, so you don't duplicate your own window).
- **`--reconcile`** → additionally union in sessions whose transcript was written after the newest snapshot. Off by default since 2026-09-08 (below).

## Which snapshots — manual ∪ debrief (the default since 2026-09-08)

Two kinds of snapshot exist and **neither alone is the fleet**:

- **Manual** (`/store-sessions`, `YYMMDD-HHMM-sessions.json`) is the deliberate "this is what I want back" record. It goes stale the moment a workstream rotates generation via `/handoff`.
- **Debrief** (`YYMMDD-HHMM-debrief-sessions.json`, written by every `/session-debrief`) carries those rotations, but only sees whatever happened to be open at that instant, often one window.

`resume` with no argument merges the newest of each: the newer snapshot is the base, the older one adds only sessions absent by id and not superseded by an equal-or-newer generation of the same name. The dry-run prints which snapshot each window came from.

*Why the rule changed:* until 2026-09-08 the default was "newest file of any kind". On that day a 1-session debrief snapshot from 2026-09-07 outranked the 3-session manual store from 2026-09-05, and the restore offered the wrong set entirely. the operator's rule: "always pull the set from the last manual store AND the last debrief; the union of the two will always be the right set."

## Reconcile — the transcript delta (opt-in with `--reconcile`)

Transcript reconcile was the default until 2026-09-08. It is now opt-in because it resurrects sessions that were opened briefly and closed on purpose (transcript mtime shows *activity*, never *openness*), and the debrief snapshot already covers the `/handoff` rotations it was built to catch. Everything below still describes how it works when you ask for it.

**No snapshot is current at the moment you need it.** Sessions rotate generation via `/handoff` all day; the snapshot you're restoring was taken before that. With `--reconcile`, `resume` unions the fleet with a scan of the transcripts, and prints what it recovered:

```
Snapshot: 260724-0000-auto-sessions.json — 15 window(s) to open
  + 6 session(s) recovered from transcripts (active after the newest snapshot; --reconcile requested):
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

- Opens **real terminal windows**: `wt.exe` on WSL; on Hyprland, `foot` via `uwsm-app`, moved back to the workspace the snapshot recorded (matched by the new foot's pid, since tmux overwrites the title). Launches the first window, **waits for its statusline to warm the shared ccusage cache**, then launches the rest — otherwise N cold statuslines each re-parse the whole JSONL corpus at once (thundering herd → swap thrash → disk pegged for minutes after a reboot). Tunable: `--stagger` (default 2s between windows), `--warm-timeout` (default 45s), `--no-warm` to skip. Needs WSL + Windows Terminal, or Hyprland + foot.
- Never double-resumes: if a label is already restored in the same run, later windows just attach to it.
- List/choose snapshots: `python3 ~/ai-workspace/team-lib/executions/session_snapshots.py list`.
