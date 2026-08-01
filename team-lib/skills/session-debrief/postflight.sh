#!/usr/bin/env bash
# ---
# template: execution
# version: 1.7.1
# summary: "Deterministic post-flight for session-debrief: cleans Zone.Identifier junk, extracts session transcripts, dumps system state, runs adapters, AUTO-EXTRACTS touched files from JSONL, commits repos, posts pulse debrief. v1.6.0 adds the dream-cycle memory self-maintenance: an incremental groom (memory_self_check.py --fix-safe --limit 15, deterministic frontmatter backfills) + a detection pass surfacing remaining hygiene findings, then the two-strength memory-index rerank. All memory steps non-fatal. v1.4.2 hardens PATH (self-adds ~/.local/bin) so the pulse post (restish) survives degraded non-login shells."
# created: 2026-03-31
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# postflight.sh — Session debrief post-flight actions
#
# Runs all deterministic wrap-up steps in one pass:
#   0.  Workspace hygiene: remove WSL Zone.Identifier junk files
#   0b. Session transcript extraction: JSONL → filtered markdown (T1 verbatim)
#   0c. System state dump: crontab, hooks, settings, MCP → agents/system-state/
#   1.  Claude adapter: symlinks + config backup
#   2.  Agent identity repo: stage + commit + push (auto-stages transcripts/ and system-state/)
#   3.  my-lib repo: stage + commit (no push)
#   4.  Pulse channel: post debrief message
#
# Usage: bash postflight.sh [--pulse-message "message"] [--session-name "name"]
#
# Options:
#   --pulse-message "msg"   Debrief message to post to ClickUp Pulse channel
#   --session-name "name"   Session name for commit messages
#   --skip-pulse            Skip posting to Pulse channel
#   --skip-commit           Skip git commits (dry run for adapters only)

set -euo pipefail

# --- PATH hardening (resilient to degraded / non-login shells) ---
# A non-login shell — e.g. a session reconnected after a network drop — may not
# have sourced ~/.profile, which is what normally puts ~/.local/bin on PATH.
# Tools invoked below (notably `restish` for the pulse post) live there, so
# self-add the usual user bin dirs defensively. Idempotent.
for _d in "$HOME/.local/bin" "$HOME/bin"; do
  case ":$PATH:" in
    *":$_d:"*) : ;;                      # already present
    *) [ -d "$_d" ] && PATH="$_d:$PATH" ;;
  esac
done
export PATH
unset _d

# Discover workspace paths (no hardcoded user/repo names)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISCOVER="$(cd "$SCRIPT_DIR/../../executions" && pwd)/workspace_discover.sh"
if [[ ! -f "$DISCOVER" ]]; then
  echo "ERROR: workspace_discover.sh not found at $DISCOVER" >&2
  exit 1
fi
eval "$(bash "$DISCOVER")"

REPO_ROOT="$WS_REPO_ROOT"
MYLIB="${WS_MYLIB:-$WS_REPO_ROOT}"   # target of my-lib commit
TEAM_LIB="${WS_TEAM_LIB:-}"
AGENTS_REPO="$WS_AGENT_REPO"
ADAPTERS="$WS_AGENT_ADAPTERS"
SECRETS="$WS_SECRETS"
TODAY=$(date +%Y-%m-%d)

# Resolve an execution script using project > my-lib > team-lib precedence.
# Echoes the first match, or empty if none found.
resolve_script() {
  local relpath="$1"
  for root in "$REPO_ROOT" "$MYLIB" "$TEAM_LIB"; do
    [[ -z "$root" ]] && continue
    if [[ -x "$root/$relpath" ]]; then
      echo "$root/$relpath"
      return 0
    fi
  done
  return 1
}

# Parse arguments
PULSE_MESSAGE=""
SESSION_NAME="session-debrief"
SESSION_ID=""
SESSION_MARKER=""
SKIP_PULSE=false
SKIP_COMMIT=false
MYLIB_FILES=""
AGENTS_FILES=""
MYLIB_FILES_SET=false
AGENTS_FILES_SET=false
LEGACY_ADD_ALL=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --pulse-message) PULSE_MESSAGE="$2"; shift 2 ;;
    --session-name) SESSION_NAME="$2"; shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
    --session-marker) SESSION_MARKER="$2"; shift 2 ;;
    --skip-pulse) SKIP_PULSE=true; shift ;;
    --skip-commit) SKIP_COMMIT=true; shift ;;
    --mylib-files) MYLIB_FILES="$2"; MYLIB_FILES_SET=true; shift 2 ;;
    --agents-files) AGENTS_FILES="$2"; AGENTS_FILES_SET=true; shift 2 ;;
    --legacy-add-all) LEGACY_ADD_ALL=true; shift ;;
    *) shift ;;
  esac
done

# File-list args are now OPTIONAL — postflight auto-extracts touched files from
# the session JSONL via executions/extract_touched_files.py if not provided.
# This eliminates the brittle Phase 2h burden where the LLM had to track every
# file. Explicit args still win as overrides (useful for surgical commits or
# when bypassing autodetection).
AUTO_EXTRACTED=false
if [[ "$SKIP_COMMIT" == false && "$LEGACY_ADD_ALL" == false ]]; then
  if [[ "$MYLIB_FILES_SET" == false || "$AGENTS_FILES_SET" == false ]]; then
    # Need session-id to find the JSONL; resolve from marker if needed (replicate the
    # marker-resolution logic that the title-prepend step does later).
    if [[ -z "$SESSION_ID" && -n "$SESSION_MARKER" ]]; then
      MARKED_JSONL=$(grep -l "$SESSION_MARKER" "$HOME/.claude/projects/"*/*.jsonl 2>/dev/null | head -1)
      if [[ -n "$MARKED_JSONL" ]]; then
        SESSION_ID=$(basename "$MARKED_JSONL" .jsonl)
        echo "Auto-extract: resolved session from marker: $SESSION_ID"
      fi
    fi

    EXTRACT_TOUCHED=$(resolve_script "executions/extract_touched_files.py" || true)
    if [[ -n "$EXTRACT_TOUCHED" && -n "$SESSION_ID" ]]; then
      auto_out=$(python3 "$EXTRACT_TOUCHED" --session-id "$SESSION_ID" --format shell --mylib "$MYLIB" --agents "$AGENTS_REPO" 2>/dev/null || true)
      if [[ -n "$auto_out" ]]; then
        # auto_out has multiple lines: MYLIB_FILES='...' / AGENTS_FILES='...'
        # Prefix each line with `auto_` (eval'ing the raw output would clobber
        # any same-named variables in postflight's scope, AND a single `auto_`
        # prefix only applies to the first line). sed prefixes per-line.
        auto_out_prefixed=$(echo "$auto_out" | sed 's/^/auto_/')
        eval "$auto_out_prefixed"
        if [[ "$MYLIB_FILES_SET" == false ]]; then
          MYLIB_FILES="${auto_MYLIB_FILES:-}"
          MYLIB_FILES_SET=true
          echo "Auto-extracted --mylib-files: $MYLIB_FILES"
        fi
        if [[ "$AGENTS_FILES_SET" == false ]]; then
          AGENTS_FILES="${auto_AGENTS_FILES:-}"
          AGENTS_FILES_SET=true
          echo "Auto-extracted --agents-files: $AGENTS_FILES"
        fi
        AUTO_EXTRACTED=true
      else
        echo "WARNING: extract_touched_files returned empty; falling back to required-arg behavior" >&2
      fi
    fi

    # If after auto-extract attempt either is still unset, fall back to error
    if [[ "$MYLIB_FILES_SET" == false ]]; then
      echo "ERROR: --mylib-files not provided and auto-extract failed (no session-id, no marker, or extract script missing)." >&2
      echo "  Pass explicitly: --mylib-files \"backlog/foo.md skills/bar/SKILL.md\"" >&2
      echo "  Or skip:         --mylib-files \"\"" >&2
      exit 1
    fi
    if [[ "$AGENTS_FILES_SET" == false ]]; then
      echo "ERROR: --agents-files not provided and auto-extract failed." >&2
      echo "  Pass explicitly: --agents-files \"memory/MEMORY.md memory/foo.md\"" >&2
      echo "  Or skip:         --agents-files \"\"" >&2
      exit 1
    fi
  fi
fi

# Resolve SESSION_ID from SESSION_MARKER if provided.
# The marker was emitted by preflight on stdout → captured in THIS session's
# JSONL as the bash tool_result. grep -l identifies the matching JSONL
# deterministically, regardless of how many concurrent sessions exist.
if [[ -n "$SESSION_MARKER" && -z "$SESSION_ID" ]]; then
  MARKED_JSONL=$(grep -l "$SESSION_MARKER" "$HOME/.claude/projects/"*/*.jsonl 2>/dev/null | head -1)
  if [[ -n "$MARKED_JSONL" ]]; then
    SESSION_ID=$(basename "$MARKED_JSONL" .jsonl)
    echo "Resolved session from marker: $SESSION_ID"
  else
    echo "WARNING: --session-marker provided but no JSONL contains it; title step may guess wrong." >&2
  fi
fi

results=()
errors=()

# ============================================================
# 0. WORKSPACE HYGIENE — remove WSL Zone.Identifier junk files
# ============================================================
echo "=== Cleaning Zone.Identifier files ==="

ZONE_CLEANER=$(resolve_script "executions/clean_zone_identifiers.sh" || true)
if [[ -n "$ZONE_CLEANER" ]]; then
  zone_out=$(bash "$ZONE_CLEANER" --quiet 2>&1) && \
    results+=("zone_cleanup: ok") || \
    errors+=("zone_cleanup: FAILED — $zone_out")
  echo "$zone_out"
else
  errors+=("zone_cleanup: script not found in repo/my-lib/team-lib under executions/clean_zone_identifiers.sh")
fi

# ============================================================
# 0a2. TMUX SESSION REAP — clean up orphaned go-created sessions
# ============================================================
# Reaps detached/idle/dead mylib-<pid> sessions (LIVE). Never touches attached
# or current sessions; claude state is /resume-able regardless. Logs to
# runtime/logs/tmux-reaper.log. Matches the SessionStart hook's live posture. Non-fatal.
echo ""
echo "=== Reaping orphaned tmux sessions (live) ==="
REAPER=$(resolve_script "skills/reap-tmux/reap_tmux_sessions.sh" || true)
if [[ -n "$REAPER" ]]; then
  reap_out=$(bash "$REAPER" --live --quiet 2>&1) && \
    results+=("tmux_reap: ok") || \
    errors+=("tmux_reap: FAILED — $reap_out")
  echo "$reap_out"
else
  results+=("tmux_reap: skipped (skills/reap-tmux/reap_tmux_sessions.sh not found)")
fi

# ============================================================
# 0b. SESSION TRANSCRIPT EXTRACTION — JSONL → filtered markdown
# ============================================================
# Deterministic: streams Claude Code session JSONLs into the agents
# transcript archive. Idempotent (mtime-based skip), stdlib-only Python,
# ~97-98% size reduction on tool-heavy sessions. Runs before the agents
# repo commit (step 2) so newly-extracted transcripts get committed
# automatically. Skipping is non-fatal.
echo ""
echo "=== Extracting session transcripts ==="

EXTRACT_SCRIPT=$(resolve_script "executions/extract_session_transcripts.py" || true)
if [[ -n "$EXTRACT_SCRIPT" ]]; then
  extract_out=$(python3 "$EXTRACT_SCRIPT" 2>&1) && \
    results+=("transcript_extract: ok") || \
    errors+=("transcript_extract: FAILED — $extract_out")
  echo "$extract_out" | tail -10
else
  errors+=("transcript_extract: script not found in repo/my-lib/team-lib under executions/extract_session_transcripts.py")
fi

# ============================================================
# 0c. SYSTEM STATE DUMP — crontab, hooks, settings, MCP servers
# ============================================================
# Deterministic: writes git-backed snapshots of live infrastructure to
# the agent's system-state/ dir. Pairs with my-lib/context/indexed/active-systems.md
# (manual overview). Idempotent — only changes git-staged files when
# infrastructure actually drifted. Skipping is non-fatal.
echo ""
echo "=== Dumping system state (crontab, hooks, settings, MCP) ==="

DUMP_SCRIPT=$(resolve_script "executions/dump_system_state.py" || true)
if [[ -n "$DUMP_SCRIPT" ]]; then
  dump_out=$(python3 "$DUMP_SCRIPT" --quiet 2>&1) && \
    results+=("system_state_dump: ok") || \
    errors+=("system_state_dump: FAILED — $dump_out")
  echo "$dump_out"
else
  errors+=("system_state_dump: script not found in repo/my-lib/team-lib under executions/dump_system_state.py")
fi

# ============================================================
# 0d. ARCHIVE OLD TRANSCRIPTS — bound the ~/.claude corpus
# ============================================================
# Deterministic: moves session JSONLs older than 14 days out of the live
# ~/.claude/projects dir (move-not-delete → ~/.claude/projects-archive) so the
# statusline's ccusage cost meter can't re-parse a multi-GB pile, balloon RAM,
# and thrash swap → freeze the box. Idempotent (mtime-based), same-fs renames.
# Skipping is non-fatal. See memory: reference_ccusage-statusline-swap-thrash-crash.
echo ""
echo "=== Archiving old session transcripts ==="

ARCHIVE_SCRIPT=$(resolve_script "executions/archive_old_transcripts.sh" || true)
if [[ -n "$ARCHIVE_SCRIPT" ]]; then
  archive_out=$(bash "$ARCHIVE_SCRIPT" 2>&1) && \
    results+=("transcript_archive: ok") || \
    errors+=("transcript_archive: FAILED — $archive_out")
  echo "$archive_out" | tail -3
else
  errors+=("transcript_archive: script not found in repo/my-lib/team-lib under executions/archive_old_transcripts.sh")
fi

# ============================================================
# 1. CLAUDE ADAPTERS — symlinks + config backup
# ============================================================
echo "=== Running Claude adapters ==="

if [[ -x "$ADAPTERS/link.sh" ]]; then
  link_out=$(bash "$ADAPTERS/link.sh" 2>&1) && \
    results+=("adapters_link: ok") || \
    errors+=("adapters_link: FAILED — $link_out")
  echo "$link_out"
else
  errors+=("adapters_link: script not found at $ADAPTERS/link.sh")
fi

if [[ -x "$ADAPTERS/sync-config.sh" ]]; then
  sync_out=$(bash "$ADAPTERS/sync-config.sh" 2>&1) && \
    results+=("adapters_sync: ok") || \
    errors+=("adapters_sync: FAILED — $sync_out")
  echo "$sync_out"
else
  errors+=("adapters_sync: script not found at $ADAPTERS/sync-config.sh")
fi

# ============================================================
# 1b. SESSION TITLE — prepend custom-title to current session JSONL
# ============================================================
echo ""
echo "=== Fixing /resume session title ==="

# The /resume TUI reads first 64KB of each JSONL for custom-title events.
# Prepending ensures the title is always visible regardless of file size.
CLAUDE_PROJECT="$WS_CLAUDE_PROJECT"

# Resolve current session JSONL
# Prefer explicit --session-id (reliable with multiple agent terminals).
# The session's project dir isn't always the current repo — if the session was
# launched from a different cwd (e.g., my-lib) but has added working dirs (e.g.,
# a project repo), the JSONL lives under the launch-cwd's encoded project dir. So if the
# path-derived CLAUDE_PROJECT doesn't hold the file, fall back to a global search
# under ~/.claude/projects/.
if [[ -n "$SESSION_ID" ]]; then
  CURRENT_JSONL=""
  if [[ -n "$CLAUDE_PROJECT" && -f "$CLAUDE_PROJECT/$SESSION_ID.jsonl" ]]; then
    CURRENT_JSONL="$CLAUDE_PROJECT/$SESSION_ID.jsonl"
  else
    # Global fallback: find the JSONL regardless of which project dir it lives in
    FOUND=$(find "$HOME/.claude/projects" -maxdepth 2 -name "$SESSION_ID.jsonl" -print -quit 2>/dev/null)
    if [[ -n "$FOUND" ]]; then
      CURRENT_JSONL="$FOUND"
    else
      errors+=("session_title: --session-id JSONL not found under ~/.claude/projects/ for $SESSION_ID")
    fi
  fi
else
  echo "  WARNING: No --session-id provided. Guessing from mtime (unreliable with multiple terminals)."
  CURRENT_JSONL=$(ls -t "$CLAUDE_PROJECT"/*.jsonl 2>/dev/null | grep -v '/agent-' | head -1)
fi

if [[ -n "$CURRENT_JSONL" ]]; then
  CURRENT_SID=$(basename "$CURRENT_JSONL" .jsonl)

  # Check if user already /rename'd this session — if so, use that name verbatim
  # (don't add YYMMDD-HH:MM prefix to explicit /rename names)
  RENAME_NAME=$(python3 -c "
import json, sys
name = None
for line in open('$WS_HISTORY'):
    try:
        d = json.loads(line.strip())
        if d.get('sessionId') == '$CURRENT_SID' and d.get('display','').startswith('/rename '):
            name = d['display'][len('/rename '):].strip()
    except: pass
if name: print(name)
" 2>/dev/null || true)

  if [[ -n "$RENAME_NAME" ]]; then
    TITLE_NAME="$RENAME_NAME"
  else
    # Use YYMMDD-HH:MM prefix + session name
    # Get first timestamp from the JSONL
    FIRST_TS=$(head -c 65536 "$CURRENT_JSONL" | grep -oP '"timestamp"\s*:\s*"[^"]*"' | head -1 | grep -oP '"[^"]*"$' | tr -d '"')
    if [[ -n "$FIRST_TS" ]]; then
      TS_PREFIX=$(python3 -c "
from datetime import datetime, timezone
ts = '$FIRST_TS'
try:
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone()
    print(dt.strftime('%y%m%d-%H:%M'))
except: print('')
" 2>/dev/null)
    fi
    if [[ -n "${TS_PREFIX:-}" ]]; then
      TITLE_NAME="$TS_PREFIX $SESSION_NAME"
    else
      TITLE_NAME="$SESSION_NAME"
    fi
  fi

  # Check if line 1 is already a matching custom-title
  LINE1=$(head -1 "$CURRENT_JSONL")
  ALREADY_SET=false
  if echo "$LINE1" | grep -q '"type":"custom-title"'; then
    EXISTING=$(echo "$LINE1" | python3 -c "import json,sys; print(json.loads(sys.stdin.read().strip()).get('customTitle',''))" 2>/dev/null || true)
    if [[ "$EXISTING" == "$TITLE_NAME" ]]; then
      ALREADY_SET=true
    fi
  fi

  if [[ "$ALREADY_SET" == true ]]; then
    results+=("session_title: already set — $TITLE_NAME")
    echo "Title already set: $TITLE_NAME"
  else
    # Build the custom-title event and prepend to JSONL (type MUST be first key for CLI parser)
    # Save mtime, prepend, restore mtime
    ORIG_MTIME=$(stat -c %Y "$CURRENT_JSONL")

    python3 - "$CURRENT_JSONL" "$TITLE_NAME" "$CURRENT_SID" <<'PYEOF'
import json, sys

filepath, title, sid = sys.argv[1], sys.argv[2], sys.argv[3]
event = json.dumps({"type": "custom-title", "customTitle": title, "sessionId": sid},
                    ensure_ascii=False, separators=(",", ":"))

with open(filepath, "r") as f:
    lines = f.readlines()

# Strip old custom-title from first 3 lines
cleaned = []
for i, line in enumerate(lines):
    if i < 3 and line.strip().startswith('{"type":"custom-title"'):
        continue
    cleaned.append(line)

with open(filepath, "w") as f:
    f.write(event + "\n")
    f.writelines(cleaned)
PYEOF

    if [[ $? -eq 0 ]]; then
      touch -d "@$ORIG_MTIME" "$CURRENT_JSONL" 2>/dev/null || true
      results+=("session_title: set — $TITLE_NAME")
      echo "Title set: $TITLE_NAME"
    else
      errors+=("session_title: failed to prepend event")
    fi
  fi
else
  errors+=("session_title: no session JSONL found")
fi

# ============================================================
# 2. AGENT IDENTITY REPO — commit + push
# ============================================================
if [[ "$SKIP_COMMIT" == false ]]; then
  echo ""
  echo "=== Committing agent identity repo ==="
  cd "$AGENTS_REPO"

  if [[ "$LEGACY_ADD_ALL" == true ]]; then
    echo "WARNING: --legacy-add-all in effect — staging all changes (catch-all behavior)." >&2
    git add -A
  elif [[ -z "$AGENTS_FILES" ]]; then
    echo "Skipping agents commit (--agents-files was empty)."
    results+=("agents_commit: skipped (empty file list)")
  else
    # Stage only the explicitly listed paths. Word-split on whitespace.
    # shellcheck disable=SC2086
    git add -- $AGENTS_FILES 2>&1 || {
      errors+=("agents_add: FAILED for paths: $AGENTS_FILES")
      echo "ERROR: git add failed in agents repo for: $AGENTS_FILES" >&2
    }

    # Auto-stage outputs from postflight steps 0b (transcripts/) and 0c (system-state/).
    # The LLM in Phase 2h can't know about these (they're generated by postflight
    # itself), and they're fully managed by their respective scripts — safe to
    # sweep without triggering the unrelated-work concerns that gated the catch-all
    # `git add -A`.
    for auto_dir in transcripts system-state; do
      if [[ -d "$auto_dir" ]]; then
        git add "$auto_dir/" 2>&1 || {
          errors+=("agents_add_${auto_dir}: FAILED")
          echo "WARNING: git add $auto_dir/ failed; continuing." >&2
        }
      fi
    done
  fi

  if [[ "$LEGACY_ADD_ALL" == true || -n "$AGENTS_FILES" ]]; then
    if git diff --cached --quiet 2>/dev/null; then
      results+=("agents_commit: nothing to commit")
      echo "Nothing to commit in agents repo."
    else
      commit_msg="chore: $SESSION_NAME — $TODAY"
      if git commit -m "$commit_msg" 2>&1; then
        results+=("agents_commit: ok")
        echo "Committed: $commit_msg"
        # Push (non-fatal if it fails — remote might be unavailable)
        if git push 2>&1; then
          results+=("agents_push: ok")
        else
          errors+=("agents_push: push failed (non-fatal)")
        fi
      else
        errors+=("agents_commit: FAILED")
      fi
    fi
  fi
fi

# ============================================================
# 3. MY-LIB REPO — commit (no push)
# ============================================================
if [[ "$SKIP_COMMIT" == false ]]; then
  echo ""
  echo "=== Committing my-lib repo ==="
  cd "$MYLIB"

  if [[ "$LEGACY_ADD_ALL" == true ]]; then
    echo "WARNING: --legacy-add-all in effect — staging all changes (catch-all behavior)." >&2
    git add -A
  elif [[ -z "$MYLIB_FILES" ]]; then
    echo "Skipping my-lib commit (--mylib-files was empty)."
    results+=("mylib_commit: skipped (empty file list)")
  else
    # Normalize symlinked paths before staging. `.claude/skills` is a symlink to
    # `skills/`, so `git add .claude/skills/foo` fails ("beyond a symbolic link").
    # Rewrite any such path to its real target so `git add` succeeds.
    NORM_MYLIB_FILES=""
    for f in $MYLIB_FILES; do
      case "$f" in
        .claude/skills/*) f="skills/${f#.claude/skills/}" ;;
      esac
      NORM_MYLIB_FILES="$NORM_MYLIB_FILES $f"
    done
    MYLIB_FILES="${NORM_MYLIB_FILES# }"
    # Stage only the explicitly listed paths. Word-split on whitespace.
    # shellcheck disable=SC2086
    git add -- $MYLIB_FILES 2>&1 || {
      errors+=("mylib_add: FAILED for paths: $MYLIB_FILES")
      echo "ERROR: git add failed in my-lib for: $MYLIB_FILES" >&2
    }
  fi

  if [[ "$LEGACY_ADD_ALL" == true || -n "$MYLIB_FILES" ]]; then
    if git diff --cached --quiet 2>/dev/null; then
      results+=("mylib_commit: nothing to commit")
      echo "Nothing to commit in my-lib."
    else
      commit_msg="chore: $SESSION_NAME — $TODAY"
      if git commit -m "$commit_msg" 2>&1; then
        results+=("mylib_commit: ok")
        echo "Committed: $commit_msg"
      else
        errors+=("mylib_commit: FAILED")
      fi
    fi
  fi
fi

# ============================================================
# 4. PULSE CHANNEL — post debrief
# ============================================================
if [[ "$SKIP_PULSE" == false ]] && [[ -n "$PULSE_MESSAGE" ]]; then
  echo ""
  echo "=== Posting to Pulse channel ==="

  if [[ -f "$SECRETS" ]]; then
    source "$SECRETS"

    # .env defines these as CLICKUP_WORKSPACE_ID / PULSE_CHANNEL_ID; keep the
    # legacy WS_* names as a fallback. (Mismatch silently posted to an empty URL
    # — fixed 2026-06-25.)
    ws_id="${CLICKUP_WORKSPACE_ID:-$WS_CLICKUP_WORKSPACE}"
    ch_id="${PULSE_CHANNEL_ID:-$WS_PULSE_CHANNEL}"

    if [[ -z "$ws_id" || -z "$ch_id" ]]; then
      errors+=("pulse_post: FAILED — workspace/channel id unset (need CLICKUP_WORKSPACE_ID + PULSE_CHANNEL_ID in $SECRETS)")
    else
      # JSON-escape the message
      escaped_msg=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read().strip()))" <<< "$PULSE_MESSAGE")
      payload="{\"type\":\"message\",\"content\":$escaped_msg}"

      pulse_out=$(echo "$payload" | restish post "clickup-v3/workspaces/${ws_id}/chat/channels/${ch_id}/messages" 2>&1) && \
        results+=("pulse_post: ok") || \
        errors+=("pulse_post: FAILED — $pulse_out")
    fi
  else
    errors+=("pulse_post: secrets file not found at $SECRETS")
  fi
elif [[ "$SKIP_PULSE" == true ]]; then
  results+=("pulse_post: skipped")
else
  results+=("pulse_post: skipped (no message provided)")
fi

# ============================================================
# STEP — Memory self-maintenance ("dream cycle" incremental groom + detection)
# ============================================================
# Incremental groom: apply a small capped batch of deterministic frontmatter
# backfills (name/type from filename) so the corpus converges over sessions
# without large diffs. Then a detection pass surfaces remaining hygiene findings.
# Both non-fatal — memory hygiene never fails a debrief.
GROOM=$(python3 "$HOME/ai-workspace/team-lib/executions/memory_self_check.py" --fix-safe --limit 15 2>/dev/null | head -1)
results+=("memory_groom: ${GROOM:-skipped}")
CHECK=$(python3 "$HOME/ai-workspace/team-lib/executions/memory_self_check.py" --json 2>/dev/null \
  | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin); hard=sum(len(d[k]) for k in d if k!="dead_wikilink")
  print(f"{hard} hygiene finding(s) remain (see /self-check)" if hard else "clean")
except Exception: print("check skipped")' 2>/dev/null)
results+=("memory_self_check: ${CHECK:-skipped}")

# ============================================================
# STEP — Memory index rerank (two-strength Hot/Cold MEMORY.md)
# ============================================================
# Non-fatal by design: a rerank failure must never fail the debrief.
if python3 "$HOME/ai-workspace/team-lib/executions/rerank_memory_index.py" >/dev/null 2>&1; then
  results+=("memory_rerank: MEMORY.md hot/cold regenerated")
else
  results+=("memory_rerank: FAILED (non-fatal — run rerank_memory_index.py manually)")
fi

# ============================================================
# OUTPUT — Summary
# ============================================================
echo ""
echo "=== Postflight Summary ==="
for r in "${results[@]}"; do
  echo "  ✓ $r"
done
for e in "${errors[@]}"; do
  echo "  ✗ $e"
done

# Remote-control disconnect reminder — remote control cannot be toggled off
# programmatically (interactive /remote-control only, by design; verified via
# claude-code-guide 2026-07-13). Best we can do is detect the active connection
# ($CLAUDE_CODE_BRIDGE_SESSION_ID, set v2.1.199+) and nudge the user.
if [[ -n "${CLAUDE_CODE_BRIDGE_SESSION_ID:-}" ]]; then
  echo ""
  echo "⚠ Remote control still active — run /remote-control to disconnect."
fi

# Exit with error if any step failed
if [[ ${#errors[@]} -gt 0 ]]; then
  exit 1
fi
exit 0
