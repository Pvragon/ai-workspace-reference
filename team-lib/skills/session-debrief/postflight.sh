#!/usr/bin/env bash
# ---
# template: execution
# version: 1.1.0
# summary: "Deterministic post-flight for session-debrief: cleans Zone.Identifier junk, runs adapters, commits repos, posts pulse debrief. Takes debrief message as argument."
# created: 2026-03-31
# last_updated: 2026-04-09
# maintainer: pvragon
# ---
#
# postflight.sh — Session debrief post-flight actions
#
# Runs all deterministic wrap-up steps in one pass:
#   0. Workspace hygiene: remove WSL Zone.Identifier junk files
#   1. Claude adapter: symlinks + config backup
#   2. Agent identity repo: stage + commit + push
#   3. my-lib repo: stage + commit (no push)
#   4. Pulse channel: post debrief message
#
# Usage: bash postflight.sh [--pulse-message "message"] [--session-name "name"]
#
# Options:
#   --pulse-message "msg"   Debrief message to post to ClickUp Pulse channel
#   --session-name "name"   Session name for commit messages
#   --skip-pulse            Skip posting to Pulse channel
#   --skip-commit           Skip git commits (dry run for adapters only)

set -euo pipefail

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

# Validate file-list args (unless skipping commits or using legacy fallback)
if [[ "$SKIP_COMMIT" == false && "$LEGACY_ADD_ALL" == false ]]; then
  if [[ "$MYLIB_FILES_SET" == false ]]; then
    echo "ERROR: --mylib-files is required (pass space-separated paths the debrief modified, or empty string to skip my-lib commit, or --legacy-add-all for catch-all behavior)." >&2
    echo "  Example: --mylib-files \"backlog/foo.md skills/bar/SKILL.md\"" >&2
    echo "  Skip:    --mylib-files \"\"" >&2
    exit 1
  fi
  if [[ "$AGENTS_FILES_SET" == false ]]; then
    echo "ERROR: --agents-files is required (pass space-separated paths the debrief modified, or empty string to skip agents commit, or --legacy-add-all for catch-all behavior)." >&2
    echo "  Example: --agents-files \"memory/MEMORY.md memory/foo.md\"" >&2
    echo "  Skip:    --agents-files \"\"" >&2
    exit 1
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
# echo1), the JSONL lives under the launch-cwd's encoded project dir. So if the
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

    # JSON-escape the message
    escaped_msg=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read().strip()))" <<< "$PULSE_MESSAGE")
    payload="{\"type\":\"message\",\"content\":$escaped_msg}"

    pulse_out=$(echo "$payload" | restish post "clickup-v3/workspaces/${WS_CLICKUP_WORKSPACE}/chat/channels/${WS_PULSE_CHANNEL}/messages" 2>&1) && \
      results+=("pulse_post: ok") || \
      errors+=("pulse_post: FAILED — $pulse_out")
  else
    errors+=("pulse_post: secrets file not found at $SECRETS")
  fi
elif [[ "$SKIP_PULSE" == true ]]; then
  results+=("pulse_post: skipped")
else
  results+=("pulse_post: skipped (no message provided)")
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

# Exit with error if any step failed
if [[ ${#errors[@]} -gt 0 ]]; then
  exit 1
fi
exit 0
