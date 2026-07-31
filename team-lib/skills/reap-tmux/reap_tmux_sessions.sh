#!/usr/bin/env bash
# ---
# name: reap_tmux_sessions.sh
# version: 1.0.0
# summary: Reap orphaned go-created tmux sessions (mylib-<pid>) that are detached AND
#          (idle > grace OR a dead shell where claude already exited). Never touches
#          attached sessions or the current session. Claude conversation state is
#          resumable via /resume regardless, so reaping a session loses only live
#          scrollback. DRY-RUN by default — pass --live to actually kill.
# created: 2026-05-31
# last_updated: 2026-05-31
# maintainer: pvragon
# usage: reap_tmux_sessions.sh [--live] [--grace-min N] [--pattern REGEX] [--quiet]
#   --live          actually kill (default: dry-run, log "WOULD-REAP" only)
#   --grace-min N    idle-minutes before a detached session is reapable (default 120)
#   --pattern REGEX  bash regex of MANAGED session names (default '^mylib-[0-9]+$')
#   --quiet          log to file only, no stdout
# env: REAP_GRACE_MIN overrides default grace.
# ---
set -uo pipefail

GRACE_MIN="${REAP_GRACE_MIN:-120}"
DEAD_SHELL_MIN=15                 # dead-shell sessions reaped after this many idle min (guards against claude mid-Bash-call)
PATTERN='^mylib-[0-9]+$'          # only go-created sessions; rotate/user-named sessions are NOT managed
LIVE=0
QUIET=0
LOG="${HOME}/ai-workspace/my-lib/runtime/logs/tmux-reaper.log"

while [ $# -gt 0 ]; do
  case "$1" in
    --live)      LIVE=1 ;;
    --grace-min) GRACE_MIN="${2:?}"; shift ;;
    --pattern)   PATTERN="${2:?}"; shift ;;
    --quiet)     QUIET=1 ;;
    *) ;;
  esac
  shift
done

command -v tmux >/dev/null 2>&1 || exit 0
tmux ls >/dev/null 2>&1 || exit 0          # no server / no sessions → nothing to do

mkdir -p "$(dirname "$LOG")"
now=$(date +%s)
stamp=$(date '+%Y-%m-%d %H:%M:%S')
mode=$([ "$LIVE" -eq 1 ] && echo LIVE || echo DRY-RUN)
cur=$(tmux display-message -p '#{session_name}' 2>/dev/null || echo "")

log(){ printf '%s\n' "$1" >> "$LOG"; [ "$QUIET" -eq 1 ] || printf '%s\n' "$1"; }

reaped=0; kept=0; managed=0
log "=== reaper $stamp  mode=$mode grace=${GRACE_MIN}m pattern='$PATTERN' current='$cur' ==="
while IFS='|' read -r name att act; do
  [ -n "$name" ] || continue
  [[ "$name" =~ $PATTERN ]] || continue       # ignore non-managed sessions entirely
  managed=$((managed+1))
  if [ "$att" = "1" ] || [ "$name" = "$cur" ]; then kept=$((kept+1)); continue; fi
  idle_min=$(( (now - act) / 60 ))
  # dead shell = no claude/node process in any pane (claude exited → leftover bash)
  cmds=$(tmux list-panes -t "$name" -F '#{pane_current_command}' 2>/dev/null | tr '\n' ',')
  dead_shell=1; case "$cmds" in *node*|*claude*) dead_shell=0 ;; esac
  reason=""
  if [ "$dead_shell" = "1" ] && [ "$idle_min" -gt "$DEAD_SHELL_MIN" ]; then
    reason="dead-shell, idle ${idle_min}m (claude exited; panes=${cmds%,})"
  elif [ "$idle_min" -gt "$GRACE_MIN" ]; then
    reason="idle ${idle_min}m > ${GRACE_MIN}m grace"
  fi
  if [ -n "$reason" ]; then
    reaped=$((reaped+1))
    if [ "$LIVE" -eq 1 ]; then
      tmux kill-session -t "$name" 2>/dev/null && log "REAPED      $name  ($reason)" || log "REAP-FAILED $name"
    else
      log "WOULD-REAP  $name  ($reason)"
    fi
  else
    kept=$((kept+1))
    log "keep        $name  (detached, idle ${idle_min}m, within grace)"
  fi
done < <(tmux ls -F '#{session_name}|#{session_attached}|#{session_activity}' 2>/dev/null)
log "=== summary: managed=$managed  ${mode}-reaped=$reaped  kept=$kept ==="
exit 0
