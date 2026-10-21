#!/usr/bin/env bash
# ---
# template: execution
# version: 1.1.2
# summary: 'The Claude Code status line: location, context window used against the model''s ceiling,
#   model, rate-limit clocks, and the ambient findings count. Graduated from the agent adapter layer
#   2026-08-01 — team-lib''s findings skill documents a statusline segment, so the statusline itself
#   belongs in the shared layer that ships it.'
# created: 2026-08-01
# last_updated: 2026-10-20
# maintainer: pvragon
# ---
#
# Installed by _admin/install_statusline.sh, which symlinks ~/.claude/statusline.sh here and
# registers the statusLine command in settings.json. Edit THIS file — the harness path is a
# pointer, so there is one implementation and no copy to drift.
#
# Needs jq only (setup_system.sh installs it).
# Claude Code statusLine — two rows, color-coded.
# Row 1: 📍 repo:branch [· session-name]  │  📊 context  │  🧠 model
# Row 2: ⏳ 5h limit  │  📅 7d limit  [│  📦 drift]  [│  📥 findings]
# Width-aware (1.1.0, 2026-10-20): when a row is wider than $COLUMNS allows, the segments
# wrap onto at most 3 rows and degrade in a fixed order (see "Width-aware layout"); at any
# width where both rows fit, the output is byte-identical to 1.0.x. The everpresent Your Agent pane
# (session name your-agent-the-everpresent*) adds its queue segment from summary.json.

input=$(cat)

# ── ANSI helpers ──────────────────────────────────────────────────────────
RESET=$'\033[0m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'

# Segment separator. Plain everywhere, except on an Omarchy desktop running the theme named below,
# where the bars take the theme's brand orange (the operator, 2026-10-14). Other machines and other
# themes are unaffected. Pure bash: this runs on every statusline refresh.
SEP="  │  "
_omarchy_state="$HOME/.local/state/omarchy/current"
if [[ -r "$_omarchy_state/theme.name" && "$(<"$_omarchy_state/theme.name")" == "your-theme" ]]; then
  while IFS= read -r _line; do
    if [[ $_line =~ ^orange[[:space:]]*=[[:space:]]*\"#([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})\" ]]; then
      SEP="  "$'\033'"[38;2;$((16#${BASH_REMATCH[1]}));$((16#${BASH_REMATCH[2]}));$((16#${BASH_REMATCH[3]}))m│${RESET}  "
      break
    fi
  done < "$_omarchy_state/theme/colors.toml" 2>/dev/null
fi

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
# One jq start for every payload field: each `echo | jq` costs a few ms, and this runs on
# every refresh of every session. Fields are joined with the unit separator (0x1f), so an
# empty value stays an empty field. Defaults match what the per-field reads used to give.
mapfile -t -d $'\x1f' _f < <(printf '%s' "$input" | jq -j '[
  (.model.display_name // "?"), (.model.id // ""), (.workspace.current_dir // .cwd // "."),
  (.cost.total_cost_usd // 0), (.session_id // ""), (.session_name // ""),
  (.context_window.used_percentage // ""), (.context_window.current_usage.input_tokens // 0),
  (.context_window.current_usage.cache_read_input_tokens // 0),
  (.context_window.current_usage.cache_creation_input_tokens // 0),
  (.rate_limits.five_hour.used_percentage // ""), (.rate_limits.five_hour.resets_at // ""),
  (.rate_limits.seven_day.used_percentage // ""), (.rate_limits.seven_day.resets_at // ""),
  (.context_window.context_window_size // "")] | map(tostring) | join("\u001f")' 2>/dev/null)
# No output at all (empty or unparseable payload) leaves every field empty, as the per-field
# reads did; only a parsed payload gets the defaults.
model=${_f[0]}; model_id=${_f[1]}; cwd=${_f[2]}; cost=${_f[3]}; session_id=${_f[4]}
ctx_pct=${_f[6]}; ctx_in=${_f[7]}; ctx_cr=${_f[8]}; ctx_cc=${_f[9]}
rl5_pct=${_f[10]}; rl5_at=${_f[11]}; rl7_pct=${_f[12]}; rl7_at=${_f[13]}; ctx_window_size=${_f[14]}
# Persist the plan's usage windows for the long-run skill's `harness.py budget`: the payload is
# the only place they are visible. Atomic replace; any failure is silent and never blocks a render.
if [[ -n "$rl5_pct" || -n "$rl7_pct" ]]; then
  _lr="${LONG_RUN_STATE_DIR:-$HOME/.local/state/long-run}"
  mkdir -p "$_lr" 2>/dev/null && printf '{"five_hour_pct":%s,"five_hour_resets_at":"%s","seven_day_pct":%s,"seven_day_resets_at":"%s","written_at":"%s"}\n' \
    "${rl5_pct:-null}" "$rl5_at" "${rl7_pct:-null}" "$rl7_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$_lr/usage.json.$$" 2>/dev/null && mv -f "$_lr/usage.json.$$" "$_lr/usage.json" 2>/dev/null
fi
# Session name: newer builds may pass .session_name in the payload; otherwise
# look it up in the live-session registry (~/.claude/sessions/<pid>.json,
# written by 2.1.x builds and by /rename) via our session_id.
session_name=${_f[5]}
if [[ -z "$session_name" && -n "$session_id" ]]; then
  session_name=$(jq -r --arg sid "$session_id" \
    'select(.sessionId == $sid) | .name // empty' \
    "$HOME"/.claude/sessions/*.json 2>/dev/null | head -1)
fi

# ── 5h active block $ + 7d total $ (ccusage, cached, single-flight) ───────
# 5h: ccusage's "active block" maps to Anthropic's 5h billing window.
# 7d: ccusage is day-granular; prorate the oldest day to the fraction inside
# the 168h rolling window so the value doesn't step at midnight.
# REQUIRES ccusage >= 20 (pinned 20.0.30, re-validated 2026-10-19: blocks/daily JSON shape unchanged, ~1 s; was 20.0.28).
# v18 re-parsed the ~800 MB corpus in >120 s at ~4 GB RSS, never finished inside
# the timeout, wrote no cache, and so respawned on every render: a parse loop
# running for as long as any session worked. v20 does the same corpus in ~1.4 s
# at ~330 MB. v20 daily rows say `period`, not `date`; the jq accepts both.
# PRICES: --offline reads ccusage's on-disk copy of LiteLLM's price file
# (~/.cache/ccusage/http-cache), so a render costs no network. The nightly
# dream cycle refreshes that copy online. A model missing from it prices at $0
# silently, so a non-zero-token / zero-cost row shows "$?" instead, triggers one
# online refresh, and is logged to ~/.claude/ccusage-unpriced.log.
# BACKOFF: an attempt stamp is written BEFORE each run, so a run that times out
# waits the normal TTL instead of respawning on the next render.
# SINGLE-FLIGHT: an flock allows at most ONE refresh at a time across all
# sessions; everyone else renders the last cached value. Never blocks, never herds.
total_5h=""
total_7d=""
if command -v ccusage >/dev/null 2>&1; then
  cache_5h=/tmp/ccusage-5h-active.$UID
  cache_7d=/tmp/ccusage-7d-total.$UID

  ccu() { timeout 60 env NODE_OPTIONS=--max-old-space-size=3072 ccusage "$@" 2>/dev/null; }

  # due CACHE TTL: true when neither the cached value nor the last attempt is fresh.
  due() {
    local now c a
    now=$(date +%s)
    c=$(stat -c %Y "$1" 2>/dev/null || echo 0)
    a=$(stat -c %Y "$1.attempt" 2>/dev/null || echo 0)
    (( a > c )) && c=$a
    [[ ! -s "$1" ]] && (( a == 0 )) && return 0
    (( now - c > $2 ))
  }

  # Models with tokens but zero cost in a ccusage JSON on stdin (= absent from the price file).
  unpriced() {
    jq -r '[ (.blocks[]? | select(.isActive == true)
              | select((.totalTokens // 0) > 0 and (.costUSD // 0) == 0) | .models[]?),
             (.daily[]?.modelBreakdowns[]?
              | select(((.inputTokens // 0) + (.outputTokens // 0) + (.cacheCreationTokens // 0)
                        + (.cacheReadTokens // 0)) > 0 and (.cost // 0) == 0) | .modelName)
           ] | unique | join(",")' 2>/dev/null
  }

  # fetch_priced ARGS...: offline first; if a model is unpriced, retry once online
  # (refreshes the price file). Prints the JSON, or "?" when still unpriced.
  fetch_priced() {
    local json miss
    json=$(ccu "$@" --offline)
    miss=$(printf '%s' "$json" | unpriced)
    if [[ -n "$miss" ]]; then
      json=$(ccu "$@")
      miss=$(printf '%s' "$json" | unpriced)
    fi
    if [[ -n "$miss" ]]; then
      echo "$(date -Is) unpriced model(s): $miss" >> "$HOME/.claude/ccusage-unpriced.log"
      echo "?"
    else
      printf '%s' "$json"
    fi
  }

  refresh_5h() {
    local tmp out val
    due "$cache_5h" 60 || return 0
    touch "$cache_5h.attempt"
    tmp="${cache_5h}.tmp.$$"
    out=$(fetch_priced blocks --active --json)
    if [[ "$out" == "?" ]]; then
      val="?"
    else
      val=$(printf '%s' "$out" \
        | jq -r '[.blocks[]? | select(.isActive == true) | .costUSD] | add // 0' 2>/dev/null)
    fi
    [[ -n "$val" ]] && echo "$val" > "$tmp" && mv "$tmp" "$cache_5h"
  }

  refresh_7d() {
    local since oldest_date now_secs_today oldest_fraction tmp out val
    # 900s, not 60s: the 7d figure is DAY-granular, so a 60s TTL buys no accuracy.
    due "$cache_7d" 900 || return 0
    touch "$cache_7d.attempt"
    since=$(date -d '7 days ago' +%Y%m%d 2>/dev/null)
    oldest_date=$(date -d '7 days ago' +%Y-%m-%d 2>/dev/null)
    now_secs_today=$(( $(date +%s) - $(date -d 'today 00:00:00' +%s) ))
    oldest_fraction=$(awk -v s="$now_secs_today" 'BEGIN{printf "%.6f", (86400 - s) / 86400}')
    tmp="${cache_7d}.tmp.$$"
    out=$(fetch_priced daily --since "$since" --json -b)
    if [[ "$out" == "?" ]]; then
      val="?"
    else
      val=$(printf '%s' "$out" \
        | jq -r --arg oldest "$oldest_date" --argjson frac "$oldest_fraction" \
            '[.daily[]?
              | .totalCost * (if (.period // .date) == $oldest then $frac else 1 end)
             ] | add // 0' 2>/dev/null)
    fi
    [[ -n "$val" ]] && echo "$val" > "$tmp" && mv "$tmp" "$cache_7d"
  }

  if command -v flock >/dev/null 2>&1; then
    # Refresh runs in the BACKGROUND under the flock, so this render returns
    # immediately on the cached value; the new value shows on a later render.
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
      drift_seg="${SEP}📦${drift_color}${drift_total} drift${RESET}${DIM} (${drift_docs} docs)${RESET}"
    fi
  fi
fi

# ── Context usage ─────────────────────────────────────────────────────────
# Max window: Claude Code reports it as context_window.context_window_size. The name rule
# ("1M" / "[1m]") is only a fallback: Opus 5.5 is named plainly, so the rule showed 200k for a
# 1M session (2026-10-15).
max=$ctx_window_size
if ! [[ "$max" =~ ^[0-9]+$ ]] || (( max == 0 )); then
  max=200000
  [[ "$model" == *"1M"* || "$model_id" == *"[1m]"* ]] && max=1000000
fi

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
  if [[ "$dollar" == "?" ]]; then
    dollar_seg=" · \$?"          # a model the price file does not know yet
  elif [[ "$dollar" =~ ^[0-9.]+$ ]]; then
    dollar_seg=$(printf " · \$%.2f" "$dollar")
  fi
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
# fit_loc BUDGET sets loc_str. The full-width layout calls it with 50; a narrow
# terminal calls it again with whatever room is left (see "Width-aware layout").
LOC_BUDGET=50
_b_floor=6; _w_floor=6; _r_floor=6; _n_floor=12

_loc_repo="${repo:-?}"
_loc_branch="${branch:-?}"
_loc_wt=""
(( ! wt_is_main )) && [[ -n "$worktree" ]] && _loc_wt="$worktree"
_loc_name="$session_name"

_loc_width() {   # 1 for ':' + 1 for ':wt' + 4 for '  · ' when each is present
  local w=$_r_cap
  (( ! _drop_branch )) && w=$(( w + 1 + _b_cap ))
  [[ -n "$_loc_wt" ]]   && w=$(( w + 1 + _w_cap ))
  [[ -n "$_loc_name" ]] && w=$(( w + 4 + _n_cap ))
  printf '%s' "$w"
}

fit_loc() {
  local budget=$1
  # Start from the historical per-piece caps, then shrink the block to fit.
  _r_cap=${#_loc_repo}; _b_cap=24; _w_cap=18; _n_cap=26
  (( _b_cap > ${#_loc_branch} )) && _b_cap=${#_loc_branch}
  (( _w_cap > ${#_loc_wt} ))     && _w_cap=${#_loc_wt}
  (( _n_cap > ${#_loc_name} ))   && _n_cap=${#_loc_name}

  _drop_branch=0
  # A branch that merely restates its worktree (feat/billing-coverage-q3-260520
  # inside billing-coverage-q3) carries no information the worktree segment isn't
  # already showing. Drop it WHOLE rather than let the shrink loop mince both into
  # `fea…20:bil…q3` — one readable name beats two unreadable ones at equal cost.
  if [[ -n "$_loc_wt" && "$_loc_branch" == *"$_loc_wt"* ]] && (( $(_loc_width) > budget )); then
    _drop_branch=1
  fi

  while (( $(_loc_width) > budget )); do
    if   (( _b_cap > _b_floor )); then _b_cap=$(( _b_cap - 1 ))
    elif [[ -n "$_loc_wt" ]] && (( _w_cap > _w_floor )); then _w_cap=$(( _w_cap - 1 ))
    elif (( _r_cap > _r_floor )); then _r_cap=$(( _r_cap - 1 ))
    elif [[ -n "$_loc_name" ]] && (( _n_cap > _n_floor )); then _n_cap=$(( _n_cap - 1 ))
    else break   # already at every floor — accept the overflow rather than spin
    fi
  done

  local repo_disp branch_seg="" wt_seg="" wt_disp name_seg=""
  repo_disp=$(mid_truncate "$_loc_repo" "$_r_cap")
  (( ! _drop_branch )) && branch_seg=":$(mid_truncate "$_loc_branch" "$_b_cap")"
  if [[ -n "$_loc_wt" ]]; then
    wt_disp=$(mid_truncate "$_loc_wt" "$_w_cap")
    if [[ "$branch" == *"$_loc_wt"* ]]; then
      wt_seg="${DIM}:${wt_disp}${RESET}"
    else
      wt_seg=":${YELLOW}${wt_disp}${RESET}"
    fi
  fi
  [[ -n "$_loc_name" ]] && name_seg="  ${DIM}· $(mid_truncate "$_loc_name" "$_n_cap")${RESET}"
  loc_str="${repo_disp}${branch_seg}${wt_seg}${name_seg}"
}

# ── Render ────────────────────────────────────────────────────────────────
# The everpresent pane (session name your-agent-the-everpresent*) gets a queue segment and a
# narrow layout; every other session renders as it always has when it fits.
_everpresent=0
[[ "$session_name" == your-agent-the-everpresent* ]] && _everpresent=1

# Theme orange for the one signal on the line (asks waiting on the operator). Same source as SEP.
# In the everpresent pane the bars take the theme's accent instead, because there orange is
# reserved for an ask (terminal-pane house style: teal is structure, orange is signal).
ORANGE=$YELLOW
if [[ "$SEP" == *$'\033[38;2;'* ]]; then
  _o=${SEP#*$'\033['}; ORANGE=$'\033['"${_o%%m*}m"
  if (( _everpresent )); then
    while IFS= read -r _line; do
      if [[ $_line =~ ^accent[[:space:]]*=[[:space:]]*\"#([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})\" ]]; then
        _acc="\033[38;2;$((16#${BASH_REMATCH[1]}));$((16#${BASH_REMATCH[2]}));$((16#${BASH_REMATCH[3]}))m"
        SEP="  "$(printf '%b' "$_acc")"│${RESET}  "
        break
      fi
    done < "$_omarchy_state/theme/colors.toml" 2>/dev/null
  fi

fit_loc "$LOC_BUDGET"
printf -v row1 "📍 %s${SEP}📊 %s%dk/%dk (%d%%)%s%s${SEP}🧠 %s" \
  "$loc_str" \
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
# findings.py pre-renders its own plain separator; swap it for SEP so every bar matches.
[[ "$findings_seg" == "  │  "* ]] && findings_seg="${SEP}${findings_seg#  │  }"

rl5_seg=$(fmt_rl "$rl5_pct" "$rl5_at" "5h" "⏳" "$total_5h")
rl7_seg=$(fmt_rl "$rl7_pct" "$rl7_at" "7d" "📅" "$total_7d")
printf -v row2 "%s${SEP}%s%s%s" "$rl5_seg" "$rl7_seg" "$drift_seg" "$findings_seg"

# ── Width-aware layout ────────────────────────────────────────────────────
# Claude Code sets COLUMNS to the terminal width and draws the status line two cells in,
# cutting whatever runs past the edge. Measured in the 68-column everpresent pane
# (2026-10-20): a row of 65 cells was cut to 63 plus an ellipsis, so the room for a row is
# COLUMNS minus 4 (the indent and two cells Claude Code keeps clear). When both rows fit (every full-width session), they print
# exactly as they always have. Otherwise the segments are packed into at most MAX_ROWS rows
# of that width, degrading in a fixed order (DEGRADE below) until they fit: the order is a
# decision about what matters, not an accident of where the line got cut.
# The everpresent pane (session name your-agent-the-everpresent*) also gets its queue segment; its ^F hint
# lives in the pane's own title row, not here.

# disp_width STR: display cells of STR, ANSI stripped; East Asian Wide and emoji count 2.
disp_width() {
  local s=$1 plain i c cp w=0
  shopt -s extglob
  plain=${s//$'\033['*([0-9;])m/}
  shopt -u extglob
  w=${#plain}
  plain=${plain//[[:ascii:]]/}          # only non-ASCII characters can be wide
  for (( i = 0; i < ${#plain}; i++ )); do
    c=${plain:i:1}
    printf -v cp '%d' "'$c"
    if (( cp >= 0x1F000 || (cp >= 0x1100 && cp <= 0x115F) || (cp >= 0x231A && cp <= 0x231B) \
          || (cp >= 0x23E9 && cp <= 0x23EC) || cp == 0x23F0 || cp == 0x23F3 \
          || (cp >= 0x2E80 && cp <= 0xA4CF) || (cp >= 0xAC00 && cp <= 0xD7A3) \
          || (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0xFF00 && cp <= 0xFF60) || (cp >= 0xFFE0 && cp <= 0xFFE6) )); then
      w=$(( w + 1 ))
    fi
  done
  _W=$w
}

_room=1000000
[[ "${COLUMNS:-}" =~ ^[0-9]+$ ]] && (( COLUMNS > 0 )) && _room=$(( COLUMNS - 4 ))

disp_width "$row1"; _w1=$_W
disp_width "$row2"; _w2=$_W
if (( ! _everpresent && _w1 <= _room && _w2 <= _room )); then
  printf "%s\n%s\n" "$row1" "$row2"
  exit 0
fi

fi

# Queue segment for the everpresent pane, from the task store's summary.json (written by
# agent_tasks.py). Nothing is queried live. Missing file = no segment.
queue_seg=""; queue_short=""
_summary="${_ahome:+$_ahome/runtime/state/summary.json}"
if (( _everpresent )) && [[ -n "$_summary" && -s "$_summary" ]]; then
  # Unit separator, not tab: read collapses empty tab-separated fields (an empty agent age shifted
  # every field after it). The event time arrives as ISO; the line shows HH:MM.
  IFS=$'\x1f' read -r q_asks q_doing q_waiting q_agents q_age q_at q_title q_updated < <(
    jq -r '[(.asks // 0), (.doing // 0), (.waiting // 0), (.agents // 0), (.oldest_agent_min // ""),
            ((.next_event.at // "") | if length > 5 then .[11:16] else . end), (.next_event.title // ""),
            (.updated_at // 0)] | map(tostring) | join("\u001f")' \
      "$_summary" 2>/dev/null)
  q=""
  (( ${q_asks:-0} > 0 )) && { (( q_asks == 1 )) && q="${ORANGE}● 1 ask${RESET}" || q="${ORANGE}● ${q_asks} asks${RESET}"; }
  q_counts=""
  (( ${q_doing:-0} > 0 ))   && q_counts+="  ▸${q_doing}"
  (( ${q_waiting:-0} > 0 )) && q_counts+="  ⧖${q_waiting}"
  if (( ${q_agents:-0} > 0 )); then
    q_counts+="  ⇄${q_agents}"; [[ -n "$q_age" ]] && q_counts+=" ${q_age}m"
  fi
  q_event=""
  [[ -n "$q_at" ]] && q_title=${q_title:0:16}; (( ${#q_title} == 16 )) && q_title="${q_title:0:15}…"
  q_event="  ◷ ${q_at}${q_title:+ $q_title}"
  q_stale=""
  if [[ "$q_updated" =~ ^[0-9]+$ ]] && (( q_updated > 0 )); then
    _age_s=$(( $(date +%s) - q_updated ))
    (( _age_s > 600 )) && q_stale="  ${DIM}stale $(( _age_s / 60 ))m${RESET}"
  fi
  queue_seg="${q}${q_counts}${q_event}${q_stale}"
  queue_seg="${queue_seg#  }"
  queue_short="${q}${q_counts}${q_stale}"
  queue_short="${queue_short#  }"
  [[ -z "$queue_seg" ]] && { queue_seg="${DIM}queue clear${RESET}"; queue_short=$queue_seg; }
fi

if (( _everpresent )); then
  _e1=$row1; [[ -n "$queue_seg" ]] && _e1="${queue_seg}${SEP}${row1}"
  _e2="${row2}"
  disp_width "$_e1"; _w1=$_W
  disp_width "$_e2"; _w2=$_W
  if (( _w1 <= _room && _w2 <= _room )); then
    printf "%s\n%s\n" "$_e1" "$_e2"
    exit 0
  fi
fi

# Short forms, used only when the full ones do not fit.
fmt_rl_short() {
  local pct=$1 epoch=$2 icon=$3
  [[ -z "$pct" || "$pct" == "null" ]] && { printf "%s%s —%s" "$DIM" "$icon" "$RESET"; return; }
  local pct_int; pct_int=$(printf '%.0f' "$pct")
  printf "%s %s%d%%%s %s→%s%s" "$icon" "$(color_for_pct "$pct_int")" "$pct_int" "$RESET" "$DIM" "$(fmt_reset "$epoch")" "$RESET"
}
ctx_full="📊 ${ctx_color}${tok_k}k/${max_k}k (${ctx_pct_int}%)${RESET}${fire}"
ctx_short="📊 ${ctx_color}${ctx_pct_int}%${RESET}${fire}"
rl5_short=$(fmt_rl_short "$rl5_pct" "$rl5_at" "⏳")
rl7_short=$(fmt_rl_short "$rl7_pct" "$rl7_at" "📅")
find_full="${findings_seg#"$SEP"}"
find_short="${find_full%% · *}"; [[ "$find_short" != "$find_full" ]] && find_short+="$RESET"
drift_full="${drift_seg#"$SEP"}"

# Segments in display order. S_TXT is the current text; empty = dropped.
declare -A S_FULL S_SHORT S_TXT
_order=(loc ctx model rl5 rl7 drift find)
(( _everpresent )) && _order=(queue ctx rl5 loc model rl7 find drift)
fit_loc "$LOC_BUDGET"
S_FULL[loc]="📍 ${loc_str}"
S_FULL[ctx]=$ctx_full;   S_SHORT[ctx]=$ctx_short
S_FULL[model]="🧠 ${model}"
S_FULL[rl5]=$rl5_seg;    S_SHORT[rl5]=$rl5_short
S_FULL[rl7]=$rl7_seg;    S_SHORT[rl7]=$rl7_short
S_FULL[drift]=$drift_full
S_FULL[find]=$find_full; S_SHORT[find]=$find_short
S_FULL[queue]=$queue_seg; S_SHORT[queue]=$queue_short
for k in "${_order[@]}"; do S_TXT[$k]=${S_FULL[$k]}; done

MAX_ROWS=3
_sep_w=5   # "  │  "

# pack: greedily fill rows in display order. Sets _rows (array). Returns 1 if more than
# MAX_ROWS rows are needed or one segment alone is wider than a row.
pack() {
  _rows=(); local cur="" cur_w=0 k t
  for k in "${_order[@]}"; do
    t=${S_TXT[$k]}; [[ -z "$t" ]] && continue
    disp_width "$t"
    (( _W > _room )) && return 1
    if [[ -z "$cur" ]]; then cur=$t; cur_w=$_W
    elif (( cur_w + _sep_w + _W <= _room )); then cur+="${SEP}${t}"; cur_w=$(( cur_w + _sep_w + _W ))
    else _rows+=("$cur"); cur=$t; cur_w=$_W
    fi
  done
  [[ -n "$cur" ]] && _rows+=("$cur")
  (( ${#_rows[@]} <= MAX_ROWS ))
}

# The degrade order: each step makes one segment shorter or drops it. Least important first.
# The queue, context, the 5-hour limit and the session name are the last to go.
DEGRADE=(short:find short:rl7 short:rl5 drop:drift short:ctx loc:34 drop:find
         short:queue loc:26 drop:rl7 drop:model loc:16)
_step=0
until pack; do
  (( _step >= ${#DEGRADE[@]} )) && break
  IFS=: read -r _act _key <<< "${DEGRADE[_step]}"
  case $_act in
    short) [[ -n "${S_TXT[$_key]}" && -n "${S_SHORT[$_key]}" ]] && S_TXT[$_key]=${S_SHORT[$_key]} ;;
    drop)  S_TXT[$_key]="" ;;
    loc)   fit_loc "$(( _key < _room - 2 ? _key : _room - 2 ))"; S_TXT[loc]="📍 ${loc_str}" ;;
  esac
  _step=$(( _step + 1 ))
done
printf "%s\n" "${_rows[@]}"
