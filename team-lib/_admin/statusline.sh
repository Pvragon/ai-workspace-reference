#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "The Claude Code status line: location, context window used against the model's
#   ceiling, model, rate-limit clocks, and the ambient findings count. Graduated from the
#   agent adapter layer 2026-08-01 — team-lib's findings skill documents a statusline segment,
#   so the statusline itself belongs in the shared layer that ships it."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Installed by _admin/install_statusline.sh, which symlinks ~/.claude/statusline.sh here and
# registers the statusLine command in settings.json. Edit THIS file — the harness path is a
# pointer, so there is one implementation and no copy to drift.
#
# Needs jq only (setup_system.sh installs it).
# Claude Code statusLine — two rows, color-coded.
# Row 1: 📍 repo:branch [· session-name]  │  💵 cost  │  🧠 model
# Row 2: 📊 context  │  ⏳ 5h limit  │  📅 7d limit

input=$(cat)

# ── ANSI helpers ──────────────────────────────────────────────────────────
RESET=$'\033[0m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'

color_for_pct() {
  local p=${1:-0}
  if   (( p >= 80 )); then echo "$RED"
  elif (( p >= 50 )); then echo "$YELLOW"
  else                      echo "$GREEN"
  fi
}

# Middle-truncate a string to <max> display chars, inserting … in the middle.
# We keep BOTH ends because our names carry meaning at each: the YYMMDD- prefix
# (session names, branches) and the descriptive tail. Tune the caps at the call
# sites below to trade Row-1 length against detail (matters most in half-width).
mid_truncate() {
  local s=$1 max=${2:-28}
  local n=${#s}
  (( n <= max )) && { printf '%s' "$s"; return; }
  local keep=$(( max - 1 ))            # reserve 1 char for the …
  local head=$(( (keep + 1) / 2 ))
  local tail=$(( keep - head ))
  printf '%s…%s' "${s:0:head}" "${s: -tail}"
}

# ── Pull fields ───────────────────────────────────────────────────────────
model=$(echo "$input" | jq -r '.model.display_name // "?"')
model_id=$(echo "$input" | jq -r '.model.id // ""')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "."')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
session_id=$(echo "$input" | jq -r '.session_id // ""')

# Session name: newer builds may pass .session_name in the payload; otherwise
# look it up in the live-session registry (~/.claude/sessions/<pid>.json,
# written by 2.1.x builds and by /rename) via our session_id.
session_name=$(echo "$input" | jq -r '.session_name // ""')
if [[ -z "$session_name" && -n "$session_id" ]]; then
  session_name=$(jq -r --arg sid "$session_id" \
    'select(.sessionId == $sid) | .name // empty' \
    "$HOME"/.claude/sessions/*.json 2>/dev/null | head -1)
fi

ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
ctx_in=$(echo "$input"  | jq -r '.context_window.current_usage.input_tokens // 0')
ctx_cr=$(echo "$input"  | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')
ctx_cc=$(echo "$input"  | jq -r '.context_window.current_usage.cache_creation_input_tokens // 0')

rl5_pct=$(echo "$input"  | jq -r '.rate_limits.five_hour.used_percentage // empty')
rl5_at=$(echo "$input"   | jq -r '.rate_limits.five_hour.resets_at // empty')
rl7_pct=$(echo "$input"  | jq -r '.rate_limits.seven_day.used_percentage // empty')
rl7_at=$(echo "$input"   | jq -r '.rate_limits.seven_day.resets_at // empty')

# ── 5h active block $ + 7d total $ (ccusage, 60s cache, single-flight) ─────
# 5h: ccusage's "active block" maps to Anthropic's 5h billing window.
# 7d: ccusage is day-granular; prorate the oldest day to the fraction inside
# the 168h rolling window so the value doesn't step at midnight.
# SINGLE-FLIGHT GUARD: each ccusage call re-parses the whole ~/.claude/projects
# corpus (~GB). When many sessions' caches go cold or expire together (a reboot,
# or 60s TTLs lining up across ~10 open windows) they'd all parse at once →
# RAM overcommit → swap-out writes peg the disk for minutes. An flock makes at
# most ONE statusline refresh at a time; everyone else skips the parse and
# renders the last cached value. Never blocks, never herds. Cache reads below
# are unconditional, so the line always shows the last-known number.
total_5h=""
total_7d=""
if command -v ccusage >/dev/null 2>&1; then
  cache_5h=/tmp/ccusage-5h-active.$UID
  cache_7d=/tmp/ccusage-7d-total.$UID

  refresh_5h() {
    local age tmp val
    age=$(( $(date +%s) - $(stat -c %Y "$cache_5h" 2>/dev/null || echo 0) ))
    if [[ ! -s "$cache_5h" ]] || (( age > 60 )); then
      tmp="${cache_5h}.tmp.$$"
      val=$(ccusage blocks --active --json 2>/dev/null \
        | jq -r '[.blocks[]? | select(.isActive == true) | .costUSD] | add // 0' 2>/dev/null)
      [[ -n "$val" ]] && echo "$val" > "$tmp" && mv "$tmp" "$cache_5h"
    fi
  }

  refresh_7d() {
    local age since oldest_date now_secs_today oldest_fraction tmp val
    age=$(( $(date +%s) - $(stat -c %Y "$cache_7d" 2>/dev/null || echo 0) ))
    if [[ ! -s "$cache_7d" ]] || (( age > 60 )); then
      since=$(date -d '7 days ago' +%Y%m%d 2>/dev/null)
      oldest_date=$(date -d '7 days ago' +%Y-%m-%d 2>/dev/null)
      now_secs_today=$(( $(date +%s) - $(date -d 'today 00:00:00' +%s) ))
      oldest_fraction=$(awk -v s="$now_secs_today" 'BEGIN{printf "%.6f", (86400 - s) / 86400}')
      tmp="${cache_7d}.tmp.$$"
      val=$(ccusage --since "$since" --json -b 2>/dev/null \
        | jq -r --arg oldest "$oldest_date" --argjson frac "$oldest_fraction" \
            '[.daily[]
              | .totalCost * (if .date == $oldest then $frac else 1 end)
             ] | add // 0' 2>/dev/null)
      [[ -n "$val" ]] && echo "$val" > "$tmp" && mv "$tmp" "$cache_7d"
    fi
  }

  if command -v flock >/dev/null 2>&1; then
    # Single-flight AND non-blocking: refresh runs in the BACKGROUND under an
    # flock, so (a) this render returns immediately on the cached value (never
    # hangs ~15-20s on the corpus parse), and (b) at most one refresh runs at a
    # time across all sessions (flock -n: losers exit instantly). New value is
    # picked up on a later render. Mirrors the northwind-drift background pattern.
    ( flock -n 9 || exit 0; refresh_5h; refresh_7d ) 9>"/tmp/ccusage-refresh.$UID.lock" >/dev/null 2>&1 &
  else
    refresh_5h; refresh_7d
  fi

  [[ -s "$cache_5h" ]] && total_5h=$(cat "$cache_5h" 2>/dev/null)
  [[ -s "$cache_7d" ]] && total_7d=$(cat "$cache_7d" 2>/dev/null)
fi

# ── Git: repo (shared .git), worktree (toplevel), branch ─────────────────
branch=""
repo=""
worktree=""
wt_is_main=1
if [[ -d "$cwd" ]]; then
  common=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  toplevel=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)
  if [[ -n "$common" && -n "$toplevel" ]]; then
    repo_root=$(dirname "$common")
    repo=$(basename "$repo_root")
    worktree=$(basename "$toplevel")
    [[ "$toplevel" != "$repo_root" ]] && wt_is_main=0
  fi
  branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
fi
branch_disp=$(mid_truncate "${branch:-?}" 24)

# Worktree segment: only shown in non-main worktrees.
# Yellow when branch name doesn't contain the worktree name (likely forgot to switch back).
wt_seg=""
if (( ! wt_is_main )) && [[ -n "$worktree" ]]; then
  wt_disp=$(mid_truncate "$worktree" 18)
  if [[ "$branch" == *"$worktree"* ]]; then
    wt_seg="${DIM}:${wt_disp}${RESET}"
  else
    wt_seg=":${YELLOW}${wt_disp}${RESET}"
  fi
fi

# ── Active-specs drift (northwind only, 5-min cache, background refresh) ────
# Shows the file-level drift between origin/docs/active-specs and origin/main.
# Only rendered when the current repo is northwind. Background-refreshes the cache
# so the statusline never blocks on git fetch.
drift_seg=""
if [[ "$repo" == "northwind" ]]; then
  cache_drift=/tmp/northwind-active-specs-drift.$UID
  age=$(( $(date +%s) - $(stat -c %Y "$cache_drift" 2>/dev/null || echo 0) ))
  if [[ ! -s "$cache_drift" ]] || (( age > 300 )); then
    (
      base="${repo_root:-$cwd}"
      git -C "$base" fetch --quiet origin main docs/active-specs 2>/dev/null
      diff_out=$(git -C "$base" diff --name-only origin/docs/active-specs origin/main 2>/dev/null)
      total=$(echo "$diff_out" | grep -c .)
      docs=$(echo "$diff_out" | grep -c "^docs/")
      tmp="${cache_drift}.tmp.$$"
      printf "%s|%s" "$total" "$docs" > "$tmp" && mv "$tmp" "$cache_drift"
    ) >/dev/null 2>&1 &
  fi
  if [[ -s "$cache_drift" ]]; then
    IFS='|' read -r drift_total drift_docs < "$cache_drift"
    if [[ -n "$drift_total" && "$drift_total" -gt 0 ]] 2>/dev/null; then
      if   (( drift_total >= 100 )); then drift_color=$RED
      elif (( drift_total >=  20 )); then drift_color=$YELLOW
      else                                drift_color=$GREEN
      fi
      drift_seg="  │  📦 ${drift_color}${drift_total} drift${RESET}${DIM} (${drift_docs} docs)${RESET}"
    fi
  fi
fi

# ── Context usage ─────────────────────────────────────────────────────────
# Max window: 1M if [1m] suffix, else 200k
max=200000
[[ "$model" == *"1M"* || "$model_id" == *"[1m]"* ]] && max=1000000

tokens=$(( ctx_in + ctx_cr + ctx_cc ))
tok_k=$(( tokens / 1000 ))
max_k=$(( max / 1000 ))

# Prefer Claude-reported percentage; fall back to manual
if [[ -n "$ctx_pct" && "$ctx_pct" != "null" ]]; then
  ctx_pct_int=$(printf '%.0f' "$ctx_pct")
else
  ctx_pct_int=$(( max > 0 ? tokens * 100 / max : 0 ))
fi

ctx_color=$(color_for_pct "$ctx_pct_int")
fire=""
(( ctx_pct_int >= 90 )) && fire=" 🔥"

# ── Rate-limit reset formatting ───────────────────────────────────────────
fmt_reset() {
  local epoch=$1
  [[ -z "$epoch" || "$epoch" == "null" ]] && { echo "?"; return; }
  local now secs h m
  now=$(date +%s)
  secs=$(( epoch - now ))
  (( secs < 0 )) && { echo "now"; return; }
  h=$(( secs / 3600 ))
  m=$(( (secs % 3600) / 60 ))
  if (( h > 24 )); then echo "$((h/24))d $((h%24))h"
  elif (( h > 0 )); then echo "${h}h ${m}m"
  else                    echo "${m}m"
  fi
}

# ── Rate limit segments ───────────────────────────────────────────────────
fmt_rl() {
  local pct=$1 epoch=$2 label=$3 icon=$4 dollar=$5
  if [[ -z "$pct" || "$pct" == "null" ]]; then
    printf "%s%s %s: —%s" "$DIM" "$icon" "$label" "$RESET"
    return
  fi
  local pct_int color reset_in dollar_seg=""
  pct_int=$(printf '%.0f' "$pct")
  color=$(color_for_pct "$pct_int")
  reset_in=$(fmt_reset "$epoch")
  [[ -n "$dollar" ]] && dollar_seg=$(printf " · \$%.2f" "$dollar")
  printf "%s %s: %s%d%%%s %s(→%s)%s%s" \
    "$icon" "$label" "$color" "$pct_int" "$RESET" "$DIM" "$reset_in" "$RESET" "$dollar_seg"
}

# ── Fit the whole location block to a fixed budget ────────────────────────
# Row 1 leads with `repo:branch[:worktree]  · session`. Each piece was capped
# individually (24/18/26) but the BLOCK was not, so a deep worktree rendered
# ~87 chars and pushed the context % off the right edge — which is the one
# number that must never be invisible. Cap the block, not the pieces.
#
# Budget is a hard display cap (50) chosen from the longest comfortable real-world
# case, len("team-lib:main  · 260801-team-lib-currency-3")=43, plus headroom.
# Shrink in priority order — branch first (it
# usually restates the worktree), then worktree, then repo — so the session
# name, the piece that tells you WHICH window this is, degrades last.
LOC_BUDGET=50
_b_floor=6; _w_floor=6; _r_floor=6; _n_floor=12

_loc_repo="${repo:-?}"
_loc_branch="${branch:-?}"
_loc_wt=""
(( ! wt_is_main )) && [[ -n "$worktree" ]] && _loc_wt="$worktree"
_loc_name="$session_name"

# Start from the historical per-piece caps, then shrink the block to fit.
_r_cap=${#_loc_repo}; _b_cap=24; _w_cap=18; _n_cap=26
(( _b_cap > ${#_loc_branch} )) && _b_cap=${#_loc_branch}
(( _w_cap > ${#_loc_wt} ))     && _w_cap=${#_loc_wt}
(( _n_cap > ${#_loc_name} ))   && _n_cap=${#_loc_name}

_drop_branch=0
_loc_width() {   # 1 for ':' + 1 for ':wt' + 4 for '  · ' when each is present
  local w=$_r_cap
  (( ! _drop_branch )) && w=$(( w + 1 + _b_cap ))
  [[ -n "$_loc_wt" ]]   && w=$(( w + 1 + _w_cap ))
  [[ -n "$_loc_name" ]] && w=$(( w + 4 + _n_cap ))
  printf '%s' "$w"
}

# A branch that merely restates its worktree (feat/billing-coverage-q3-260520
# inside billing-coverage-q3) carries no information the worktree segment isn't
# already showing. Drop it WHOLE rather than let the shrink loop mince both into
# `fea…20:bil…q3` — one readable name beats two unreadable ones at equal cost.
if [[ -n "$_loc_wt" && "$_loc_branch" == *"$_loc_wt"* ]] && (( $(_loc_width) > LOC_BUDGET )); then
  _drop_branch=1
fi

while (( $(_loc_width) > LOC_BUDGET )); do
  if   (( _b_cap > _b_floor )); then _b_cap=$(( _b_cap - 1 ))
  elif [[ -n "$_loc_wt" ]] && (( _w_cap > _w_floor )); then _w_cap=$(( _w_cap - 1 ))
  elif (( _r_cap > _r_floor )); then _r_cap=$(( _r_cap - 1 ))
  elif [[ -n "$_loc_name" ]] && (( _n_cap > _n_floor )); then _n_cap=$(( _n_cap - 1 ))
  else break   # already at every floor — accept the overflow rather than spin
  fi
done

repo_disp=$(mid_truncate "$_loc_repo" "$_r_cap")
branch_seg=""
(( ! _drop_branch )) && branch_seg=":$(mid_truncate "$_loc_branch" "$_b_cap")"

wt_seg=""
if [[ -n "$_loc_wt" ]]; then
  wt_disp=$(mid_truncate "$_loc_wt" "$_w_cap")
  if [[ "$branch" == *"$_loc_wt"* ]]; then
    wt_seg="${DIM}:${wt_disp}${RESET}"
  else
    wt_seg=":${YELLOW}${wt_disp}${RESET}"
  fi
fi

# ── Render ────────────────────────────────────────────────────────────────
name_seg=""
[[ -n "$_loc_name" ]] && name_seg="  ${DIM}· $(mid_truncate "$_loc_name" "$_n_cap")${RESET}"

printf "📍 %s%s%s%s  │  📊 %s%dk/%dk (%d%%)%s%s  │  🧠 %s\n" \
  "$repo_disp" "$branch_seg" "$wt_seg" "$name_seg" \
  "$ctx_color" "$tok_k" "$max_k" "$ctx_pct_int" "$RESET" "$fire" \
  "$model"

# Findings inbox — ambient only. The segment is pre-rendered by findings.py on every
# mutation (see SEGMENT_CACHE there), so this is a file read rather than a python start on
# every statusline refresh. Empty file = empty inbox = no segment, deliberately: a counter
# that is always present is one that is never read.
findings_seg=""
# Resolve the agent home rather than naming it: findings.py writes this via agent_paths'
# state_dir(), so a hardcoded name means any OTHER agent reads a path that does not exist
# and renders no segment — which is indistinguishable from an empty inbox. Pure bash on
# purpose; the whole point of the cache is to avoid a python start per refresh.
_ahome="${PVRAGON_AGENT_HOME:-}"
if [[ -z "$_ahome" ]]; then
  for _cand in "$HOME"/ai-workspace/agents/*/identity.md; do
    [[ -f "$_cand" ]] && { _ahome="${_cand%/identity.md}"; break; }
  done
fi
_fcache="${_ahome:+$_ahome/runtime/state/findings-statusline.txt}"
[[ -n "$_fcache" && -s "$_fcache" ]] && findings_seg="$(<"$_fcache")"

printf "%s  │  %s%s%s\n" \
  "$(fmt_rl "$rl5_pct" "$rl5_at" "5h" "⏳" "$total_5h")" \
  "$(fmt_rl "$rl7_pct" "$rl7_at" "7d" "📅" "$total_7d")" \
  "$drift_seg" \
  "$findings_seg"
