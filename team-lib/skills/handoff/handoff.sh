#!/usr/bin/env bash
# ---
# name: handoff.sh
# version: 1.4.2
# summary: Launch worker for the /handoff (session-rotate) skill. Opens a NEW terminal window (Windows
#   Terminal on WSL, foot on Hyprland/Omarchy) running a fresh tmux session + a fresh, nvm-loaded `claude -n <name>` that reads a
#   handoff brief on startup and follows its instructions (re-load persona, confirm worktree, continue).
#   The tmux session is named `mylib-<pid>` so the existing reaper still manages it; the Claude display
#   name is the passed <name> (current thread name + -n+1). Does NOT close the current window and does
#   NOT reap (reaping happens via the /session-debrief that /handoff runs + the new session's SessionStart
#   hook). nvm-load fix is load-bearing (else `claude` resolves to the Windows npm shim → exit 127).
# created: 2026-05-31
# last_updated: 2026-10-20
# maintainer: pvragon
# usage: 'handoff.sh <claude_name> <handoff_path> [--dir DIR] [--dry-run] <claude_name>   Claude session
#   display name (e.g. <current>-2). [A-Za-z0-9._-]+ <handoff_path>  absolute path to the handoff brief
#   the new session reads first. --dir DIR       worktree/working dir for the new session (default:
#   $PWD) --model M       pin the new session's model (e.g. claude-opus-5-5[1m]); default: unset
#   --permission-mode M  start the new session in this mode (e.g. auto); default: unset
#   --remote-control  start the new session with Remote Control on, named <claude_name> (opt-in; the
#   everpresent series uses it so only that pane shows in the Claude mobile app)
#   --plugin-dir DIR  load a plugin or mod directory in the new session (repeatable; the everpresent
#   series loads my-lib/apps/everpresent-dash/mod this way, so no other session gets it)
#   --settings FILE  load an extra settings JSON file in the new session (claude --settings; /long-run
#   shifts use it to register their per-run PreToolUse guard hook)
#   --detached SESSION  start the new session in a DETACHED tmux session named SESSION instead of
#   opening a window (no display needed: works from cron; /long-run shifts and its watchdog use it).
#   Attach later with tmux attach -t SESSION. Pick a name outside the reaper pattern (^mylib-[0-9]+$).
#   --dry-run       generate + print the launch script, do NOT open a window'
# ---
set -euo pipefail

DRY=0
SEED_OVERRIDE=""; MODEL=""; PMODE=""; RC=0; DIR="$PWD"; PLUGINS=""; SETTINGS=""; DETACHED=""; pos=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --dir) DIR="${2:?}"; shift ;;
    --seed) SEED_OVERRIDE="$2"; shift ;;
    --model) MODEL="${2:?}"; shift ;;
    --permission-mode) PMODE="${2:?}"; shift ;;
    --remote-control) RC=1 ;;
    --detached) DETACHED="${2:?}"; shift ;;
    --plugin-dir) PLUGINS+="--plugin-dir '${2:?}' "; shift ;;
    --settings) SETTINGS="--settings '${2:?}' "; shift ;;
    *) pos+=("$1") ;;
  esac; shift
done
NAME="${pos[0]:?usage: handoff.sh <claude_name> <handoff_path> [--dir DIR] [--dry-run]}"
# A brief is required for a rotation but meaningless for a --seed session (there is no
# document to hand off — the seed IS the instruction).
HANDOFF="${pos[1]:-}"
if [ -z "$SEED_OVERRIDE" ] && [ -z "$HANDOFF" ]; then
  echo "usage: handoff.sh <claude_name> <handoff_path> [--dir DIR] [--seed TEXT] [--dry-run]"; exit 2
fi

[[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "ERROR: name must match [A-Za-z0-9._-]+ (got '$NAME')"; exit 2; }
[ -n "$HANDOFF" ] && [ ! -f "$HANDOFF" ] && { echo "ERROR: handoff file not found: $HANDOFF"; exit 2; }
[ -d "$DIR" ] || { echo "ERROR: --dir not a directory: $DIR"; exit 2; }
# Platform: Windows Terminal on WSL, foot on Hyprland (Omarchy). Same inner script either way.
[ -n "$DETACHED" ] && { [[ "$DETACHED" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "ERROR: --detached name must match [A-Za-z0-9._-]+"; exit 2; }; }
if [ -n "$DETACHED" ]; then
  PLATFORM=detached
elif command -v wt.exe >/dev/null 2>&1; then
  PLATFORM=wsl
elif [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && command -v foot >/dev/null 2>&1; then
  PLATFORM=hyprland
else
  echo "ERROR: no window launcher: need wt.exe (WSL) or foot under Hyprland"; exit 3
fi

INNER="$HOME/.claude/handoffs/.launch-${NAME}.sh"
mkdir -p "$(dirname "$INNER")"
# --seed lets a caller reuse this spawn path for a session that is NOT a rotation — the
# findings worklist being the first. One spawn implementation, several intents; a second
# copy of the wt.exe/tmux/nvm dance would drift from this one within a month.
DEFAULT_SEED="Read your handoff brief at ${HANDOFF} and follow its startup checklist IN ORDER, completing every numbered step before you start work — the cold-start reads are not optional and the brief does not replace them. Then give me a 3-line status summary and wait."
SEED="${SEED_OVERRIDE:-$DEFAULT_SEED}"

# Inner script runs inside the new window. tmux name = mylib-<pid> (reapable, like `go`);
# Claude display name = ${NAME}. nvm loaded so `claude` resolves to the working binary.
cat > "$INNER" <<EOF
#!/usr/bin/env bash
# Auto-generated by handoff.sh.
# Drop anything the launching Claude session or tmux pane exported. CLAUDE_CODE_CHILD_SESSION=1
# alone makes the new claude save no transcript (measured 2026-10-15).
# In a session handoff.sh created (HANDOFF_DETACHED), TMUX/TMUX_PANE are this pane's own: keep them.
KEEP_TMUX="\${TMUX:-}"; KEEP_PANE="\${TMUX_PANE:-}"
for v in \$(compgen -e | grep -E '^(CLAUDE|TMUX)'); do unset "\$v"; done
[ -n "\${HANDOFF_DETACHED:-}" ] && export TMUX="\$KEEP_TMUX" TMUX_PANE="\$KEEP_PANE"
unset AI_AGENT GIT_EDITOR COREPACK_ENABLE_AUTO_PIN
export NVM_DIR="\$HOME/.nvm"
[ -s "\$NVM_DIR/nvm.sh" ] && . "\$NVM_DIR/nvm.sh" >/dev/null 2>&1
for b in "\$HOME"/.nvm/versions/node/*/bin; do [ -d "\$b" ] && PATH="\$b:\$PATH"; done
export PATH
cd "${DIR}" || cd "\$HOME"
CMD="claude ${MODEL:+--model '${MODEL}' }${PMODE:+--permission-mode '${PMODE}' }${PLUGINS}${SETTINGS}$( [ "$RC" -eq 1 ] && printf "%s" "--remote-control '${NAME}' " )-n '${NAME}' '${SEED}'"
# Already inside a tmux session handoff.sh created (take-over-in-place): run claude directly.
if [ -n "\${HANDOFF_DETACHED:-}" ]; then unset HANDOFF_DETACHED; eval "exec \$CMD"; fi
exec tmux new-session -s "mylib-\$\$" "\$CMD"
EOF
chmod +x "$INNER"

if [ "$DRY" -eq 1 ]; then
  echo "[dry-run] claude name: ${NAME}"
  echo "[dry-run] worktree:    ${DIR}"
  if [ "$PLATFORM" = detached ]; then
    echo "[dry-run] would run:   tmux new-session -d -s ${DETACHED} -c ${DIR} -e HANDOFF_DETACHED=1 bash ${INNER}"
  elif [ "$PLATFORM" = wsl ]; then
    echo "[dry-run] would run:   wt.exe -w new wsl.exe -- bash ${INNER}"
  else
    echo "[dry-run] would run:   setsid -f uwsm-app -- foot -D ${DIR} bash ${INNER}"
  fi
  echo "----- generated ${INNER} -----"; cat "$INNER"
  exit 0
fi

if [ "$PLATFORM" = detached ]; then
  # No window: a detached tmux session, launched with this session's Claude/tmux env scrubbed.
  # HANDOFF_DETACHED makes the inner script exec claude directly inside it.
  tmux has-session -t "$DETACHED" 2>/dev/null && { echo "ERROR: tmux session already exists: $DETACHED"; exit 4; }
  UNSETS=(); for v in $(compgen -e | grep -E '^(CLAUDE|TMUX)'); do UNSETS+=(-u "$v"); done
  env "${UNSETS[@]}" -u AI_AGENT -u GIT_EDITOR -u COREPACK_ENABLE_AUTO_PIN \
    tmux new-session -d -s "$DETACHED" -c "$DIR" -e HANDOFF_DETACHED=1 "bash $INNER"
  echo "launched: Claude session '${NAME}' in detached tmux session ${DETACHED} (attach: tmux attach -t ${DETACHED})"
  exit 0
fi

if [ "$PLATFORM" = hyprland ]; then
  # Optional take-over-in-place: if ~/.config/hypr/handoff-park-workspace names a workspace, the new
  # session appears in this window's exact tile and the old session moves (silently) to that
  # workspace to finish its debrief. Focus never moves. Mechanism: see the tmux client swap below.
  # Without the file, behavior is unchanged: the new window opens beside the old one.
  PARK_FILE="$HOME/.config/hypr/handoff-park-workspace"
  PARK=""; [ -f "$PARK_FILE" ] && PARK=$(tr -d '[:space:]' < "$PARK_FILE")
  OLD_ADDR=""; OLD_WS=""
  if [ -n "${TMUX:-}" ] && command -v hyprctl >/dev/null && command -v jq >/dev/null; then
    cpid=$(tmux display -p '#{client_pid}' 2>/dev/null || true)
    wins=$(hyprctl clients -j)
    while [ -n "$cpid" ] && [ "$cpid" -gt 1 ] 2>/dev/null; do
      hit=$(jq -r --argjson p "$cpid" '.[] | select(.pid==$p) | "\(.address) \(.workspace.name)"' <<<"$wins" | head -1)
      if [ -n "$hit" ]; then OLD_ADDR=${hit%% *}; OLD_WS=${hit#* }; break; fi
      # Fields after the LAST ')': the process name can contain spaces ("tmux: client"), which
      # shifted a plain awk $4 onto the state letter and stopped the walk at step one (2026-10-15).
      cpid=$(sed 's/.*) //' "/proc/$cpid/stat" 2>/dev/null | awk '{print $2}'); cpid=${cpid:-0}
    done
  fi
  if [ -n "$PARK" ] && [ -n "$OLD_ADDR" ]; then
    # Swap the window's CONTENTS, not the window (v1.4.0). The tile, its size and keyboard focus
    # never change, whatever window is active: a new window would land wherever dwindle splits,
    # which follows focus (an unattended 4am rotation split Teams instead, 2026-10-16).
    #   1. start the new session detached;  2. open a parked window on ${PARK} attached to the old
    #   session;  3. switch this window's tmux client to the new session.
    # The old session gets a second client before it loses this one, so it is never detached
    # (the reaper only takes detached sessions).
    OLD_SESS=$(tmux display -p '#{session_name}')
    OLD_TTY=$(tmux display -p '#{client_tty}')
    NEW_SESS="mylib-$$"
    tmux new-session -d -s "$NEW_SESS" -c "$DIR" -e HANDOFF_DETACHED=1 "bash $INNER"
    # detach-on-destroy is off globally; on here, so the parked window closes when the old
    # session ends instead of jumping to some other session.
    tmux set-option -t "$OLD_SESS" detach-on-destroy on
    nclients() { tmux list-clients -t "$OLD_SESS" 2>/dev/null | wc -l; }
    had=$(nclients)
    # Spawned by Hyprland itself: its environment, so nothing from this Claude session leaks in.
    hyprctl dispatch "function() hl.exec_cmd([[foot -D $(printf '%q' "$DIR") tmux attach -t ${OLD_SESS}]], { no_initial_focus = true, workspace = '${PARK} silent' }) end" >/dev/null
    ok=0
    for _ in $(seq 1 50); do
      sleep 0.2
      [ "$(nclients)" -gt "$had" ] && { ok=1; break; }
    done
    if [ "$ok" -eq 1 ]; then
      tmux switch-client -c "$OLD_TTY" -t "$NEW_SESS"
      echo "launched: Claude session '${NAME}' (tmux ${NEW_SESS}) now shows in this window on ${OLD_WS}; this session (${OLD_SESS}) continues on workspace ${PARK} for its debrief"
    else
      # No parked window: leave this one alone and show the new session beside it, unfocused.
      hyprctl dispatch "function() hl.exec_cmd([[foot -D $(printf '%q' "$DIR") tmux attach -t ${NEW_SESS}]], { no_initial_focus = true }) end" >/dev/null
      echo "launched: Claude session '${NAME}' (tmux ${NEW_SESS}) in a new window; parked window not detected, this window left in place"
    fi
    exit 0
  fi
  # Default: open beside the current window. uwsm-app gives it the session environment,
  # which is also where `claude` (mise) comes from on Omarchy.
  # Launch with the Claude/tmux env scrubbed, so the window itself (and any window opened from
  # it) carries none of this session's variables. Same list as session_snapshots._clean_launch_env.
  UNSETS=(); for v in $(compgen -e | grep -E '^(CLAUDE|TMUX)'); do UNSETS+=(-u "$v"); done
  env "${UNSETS[@]}" -u AI_AGENT -u GIT_EDITOR -u COREPACK_ENABLE_AUTO_PIN \
    setsid -f uwsm-app -- foot -D "$DIR" bash "$INNER" >/dev/null 2>&1
  echo "launched: new window in ${DIR}, Claude session '${NAME}', seeded from ${HANDOFF} (current window left open)"
  exit 0
fi

# Open the window on top but leave keyboard focus where the user is typing. wt.exe cannot open a
# window without activating it, so the helper launches it, gives focus back to the previous
# window, and raises the new one without activating it. Falls back to a plain launch.
HELPER="$(dirname "$(readlink -f "$0")")/open_window_no_focus.ps1"
if [ -f "$HELPER" ] && command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$HELPER")" -Inner "$INNER" \
    || wt.exe -w new wsl.exe -- bash "$INNER"
else
  wt.exe -w new wsl.exe -- bash "$INNER"
fi
echo "launched: new window in ${DIR}, Claude session '${NAME}', seeded from ${HANDOFF} (current window left open)"
