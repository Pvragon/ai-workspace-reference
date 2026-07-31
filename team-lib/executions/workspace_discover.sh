#!/usr/bin/env bash
# ---
# template: execution
# version: 1.2.0
# summary: "Discovers workspace paths by convention — no hardcoded user/repo names. Outputs JSON for other scripts to source. v1.2.0: also detects ONBOARDING.md as a workspace marker (team-lib ships it) and is layer-neutral so both layers can run an identical copy. v1.1.0: re-anchors WORKSPACE_ROOT on the script's own location when invoked from a cwd outside the workspace tree (fixes silent empty-path discovery during debrief postflight when cwd=~/.claude)."
# created: 2026-04-02
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
#
# workspace_discover.sh — Workspace path discovery
#
# Finds key workspace directories by convention rather than hardcoding.
# Designed to work for any user with a similar workspace structure.
#
# Usage:
#   eval "$(bash workspace_discover.sh)"       # Sets WS_* env vars
#   bash workspace_discover.sh --json           # Outputs JSON
#   source <(bash workspace_discover.sh)        # Source into current shell
#
# Discovery strategies:
#   1. Current repo     — git rev-parse --show-toplevel
#   2. Workspace root   — parent of current repo (convention: repos are siblings)
#   3. Claude project   — ~/.claude/projects/ + path encoding (/ → -)
#   4. Agent identity   — sibling repo containing identity.md at root
#   5. Team-lib         — sibling repo containing GETTING_STARTED.md
#   6. Secrets .env     — personal/secrets/.env under workspace root
#   7. Pulse config     — from workspace .env or secrets file (PULSE_CHANNEL_ID, CLICKUP_WORKSPACE_ID)

set -euo pipefail

JSON_MODE=false
[[ "${1:-}" == "--json" ]] && JSON_MODE=true

# ============================================================
# 1. Current repo
# ============================================================
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$PWD"
fi

# ============================================================
# 2. Workspace root — walk up from repo root looking for the
#    directory that contains agents/ or team-lib markers.
#    This handles nested repos (e.g., projects/northwind).
# ============================================================
WORKSPACE_ROOT=""
_candidate="$REPO_ROOT"
while [[ "$_candidate" != "/" && "$_candidate" != "$HOME" ]]; do
  _candidate=$(dirname "$_candidate")
  # A workspace root has sibling dirs: agents/, or a dir with GETTING_STARTED.md
  # / ONBOARDING.md (team-lib ships the latter, so both markers must be checked).
  if [[ -d "$_candidate/agents" ]] || ls "$_candidate"/*/GETTING_STARTED.md "$_candidate"/*/ONBOARDING.md &>/dev/null; then
    WORKSPACE_ROOT="$_candidate"
    break
  fi
done
# Fallback: parent of repo root (original behavior)
if [[ -z "$WORKSPACE_ROOT" ]]; then
  WORKSPACE_ROOT=$(dirname "$REPO_ROOT")
fi

# Robustness: the cwd-based discovery above breaks when this script is invoked
# from a cwd OUTSIDE the workspace tree (e.g. ~/.claude during a debrief, or any
# arbitrary cwd). git rev-parse then finds no repo, REPO_ROOT falls back to PWD,
# and the walk-up lands on $HOME — which has no agents/ sibling, so every derived
# repo path comes back empty and downstream commits/pulse silently no-op.
# This script's own location is an unambiguous anchor: it lives at
# <workspace>/<layer>/executions/workspace_discover.sh, in either layer. Re-anchor
# on it whenever the discovered workspace root doesn't actually contain agents/.
# No-op in the healthy case.
if [[ ! -d "$WORKSPACE_ROOT/agents" ]]; then
  _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _script_ws="$(dirname "$(dirname "$_self_dir")")"   # executions -> <layer> -> workspace
  if [[ -d "$_script_ws/agents" ]]; then
    WORKSPACE_ROOT="$_script_ws"
  fi
fi

# ============================================================
# 3. Claude project directory
# ============================================================
CLAUDE_PROJECT_DIR=""
ENCODED_PATH=$(echo "$REPO_ROOT" | sed 's|/|-|g')
CANDIDATE="$HOME/.claude/projects/$ENCODED_PATH"
if [[ -d "$CANDIDATE" ]]; then
  CLAUDE_PROJECT_DIR="$CANDIDATE"
fi

# ============================================================
# 4. Agent identity repo (sibling with identity.md)
# ============================================================
AGENT_REPO=""
AGENT_ADAPTERS=""
if [[ -d "$WORKSPACE_ROOT" ]]; then
  # Search one level deep in sibling dirs (agents/<name>/identity.md)
  for candidate in "$WORKSPACE_ROOT"/agents/*/identity.md "$WORKSPACE_ROOT"/*/identity.md; do
    if [[ -f "$candidate" ]]; then
      AGENT_REPO=$(dirname "$candidate")
      break
    fi
  done
  # Check for adapters/claude within agent repo
  if [[ -n "$AGENT_REPO" && -d "$AGENT_REPO/adapters/claude" ]]; then
    AGENT_ADAPTERS="$AGENT_REPO/adapters/claude"
  fi
fi

# ============================================================
# 5. Team-lib (sibling with GETTING_STARTED.md)
# ============================================================
TEAM_LIB=""
if [[ -d "$WORKSPACE_ROOT" ]]; then
  for candidate in "$WORKSPACE_ROOT"/*/GETTING_STARTED.md; do
    if [[ -f "$candidate" ]]; then
      TEAM_LIB=$(dirname "$candidate")
      break
    fi
  done
fi

# ============================================================
# 5b. My-lib (sibling named my-lib with AGENTS.md marker)
# ============================================================
MY_LIB=""
if [[ -d "$WORKSPACE_ROOT/my-lib" && -f "$WORKSPACE_ROOT/my-lib/AGENTS.md" ]]; then
  MY_LIB="$WORKSPACE_ROOT/my-lib"
fi

# ============================================================
# 6. Secrets .env
# ============================================================
SECRETS_FILE=""
for candidate in \
  "$WORKSPACE_ROOT/personal/secrets/.env" \
  "$WORKSPACE_ROOT/.env" \
  "$HOME/.env"; do
  if [[ -f "$candidate" ]]; then
    SECRETS_FILE="$candidate"
    break
  fi
done

# ============================================================
# 7. Pulse / ClickUp config (from secrets or workspace config)
# ============================================================
PULSE_CHANNEL_ID=""
CLICKUP_WORKSPACE_ID=""
if [[ -n "$SECRETS_FILE" ]]; then
  PULSE_CHANNEL_ID=$(grep -oP '^PULSE_CHANNEL_ID=\K.*' "$SECRETS_FILE" 2>/dev/null | tr -d '"' || true)
  CLICKUP_WORKSPACE_ID=$(grep -oP '^CLICKUP_WORKSPACE_ID=\K.*' "$SECRETS_FILE" 2>/dev/null | tr -d '"' || true)
fi

# ============================================================
# 8. History file
# ============================================================
HISTORY_FILE="$HOME/.claude/history.jsonl"
[[ ! -f "$HISTORY_FILE" ]] && HISTORY_FILE=""

# ============================================================
# Output
# ============================================================
if [[ "$JSON_MODE" == true ]]; then
  python3 -c "
import json
print(json.dumps({
    'repo_root': '$REPO_ROOT',
    'workspace_root': '$WORKSPACE_ROOT',
    'claude_project_dir': '$CLAUDE_PROJECT_DIR',
    'agent_repo': '$AGENT_REPO',
    'agent_adapters': '$AGENT_ADAPTERS',
    'team_lib': '$TEAM_LIB',
    'my_lib': '$MY_LIB',
    'secrets_file': '$SECRETS_FILE',
    'history_file': '$HISTORY_FILE',
    'pulse_channel_id': '$PULSE_CHANNEL_ID',
    'clickup_workspace_id': '$CLICKUP_WORKSPACE_ID',
}, indent=2))
"
else
  # Shell-sourceable output
  cat <<VARS
WS_REPO_ROOT="$REPO_ROOT"
WS_WORKSPACE_ROOT="$WORKSPACE_ROOT"
WS_CLAUDE_PROJECT="$CLAUDE_PROJECT_DIR"
WS_AGENT_REPO="$AGENT_REPO"
WS_AGENT_ADAPTERS="$AGENT_ADAPTERS"
WS_TEAM_LIB="$TEAM_LIB"
WS_MYLIB="$MY_LIB"
WS_SECRETS="$SECRETS_FILE"
WS_HISTORY="$HISTORY_FILE"
WS_PULSE_CHANNEL="$PULSE_CHANNEL_ID"
WS_CLICKUP_WORKSPACE="$CLICKUP_WORKSPACE_ID"
VARS
fi
