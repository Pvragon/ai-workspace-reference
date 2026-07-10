#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Deterministic pre-flight for session-debrief: collects git changes, checks registry consistency, detects sync needs, flags stale state. Outputs structured JSON."
# created: 2026-03-31
# last_updated: 2026-03-31
# maintainer: pvragon
# ---
#
# preflight.sh — Session debrief pre-flight checks
#
# Runs all deterministic checks in one pass and outputs a JSON report
# that the LLM can consume to focus only on judgment-requiring work.
#
# Usage: bash preflight.sh [--mylib-dir DIR]
#
# Output: JSON to stdout with sections:
#   git_changes, registry_issues, sync_needed, stale_flags, session_info

set -euo pipefail

# Discover workspace paths (no hardcoded user/repo names)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISCOVER="$(cd "$SCRIPT_DIR/../../executions" && pwd)/workspace_discover.sh"
if [[ ! -f "$DISCOVER" ]]; then
  echo "ERROR: workspace_discover.sh not found at $DISCOVER" >&2
  exit 1
fi
eval "$(bash "$DISCOVER")"

MYLIB="${1:-$WS_REPO_ROOT}"
TEAMLIB="$WS_TEAM_LIB"
AGENTS_REPO="$WS_AGENT_REPO"
MEMORY_DIR="$AGENTS_REPO/memory"

cd "$MYLIB"

# ============================================================
# Helper: JSON-escape a string
# ============================================================
json_escape() {
  python3 -c "import json,sys; print(json.dumps(sys.stdin.read().strip()))" <<< "$1"
}

# ============================================================
# 1. GIT CHANGES — What happened this session?
# ============================================================
git_diff_names=$(git diff --name-only 2>/dev/null || echo "")
git_diff_staged=$(git diff --cached --name-only 2>/dev/null || echo "")
git_untracked=$(git ls-files --others --exclude-standard 2>/dev/null || echo "")
git_recent_commits=$(git log --oneline -10 2>/dev/null || echo "")

# Combine all changed files into one list
all_changed=$(printf '%s\n%s\n%s' "$git_diff_names" "$git_diff_staged" "$git_untracked" | sort -u | grep -v '^$' || true)
# Count rows in $all_changed safely. `grep -c .` of empty input prints "0" AND
# exits 1, which combined with `|| echo 0` produces "0\n0" (malformed JSON).
# Compute the count once, here, with explicit empty-string handling.
if [[ -z "$all_changed" ]]; then
  all_changed_count=0
else
  all_changed_count=$(printf '%s' "$all_changed" | grep -c '^')
fi

# Categorize which registered directories were touched
touched_dirs=""
for dir in directives skills personas executions context/indexed; do
  if echo "$all_changed" | grep -q "^${dir}/"; then
    touched_dirs="${touched_dirs:+$touched_dirs,}\"$dir\""
  fi
done

# ============================================================
# 2. REGISTRY CONSISTENCY — filesystem vs YAML
# ============================================================
registry_issues=""

check_registry() {
  local dir_name="$1"
  local registry_file="$2"
  local fs_dir="$3"
  local yaml_key="$4"

  local issues=""

  [[ -d "$fs_dir" ]] || return 0
  [[ -f "$registry_file" ]] || {
    registry_issues="${registry_issues:+$registry_issues,}{\"dir\":\"$dir_name\",\"type\":\"missing_registry\",\"detail\":\"Registry file not found: $registry_file\"}"
    return 0
  }

  # Get files on filesystem (exclude index.md and __pycache__)
  local fs_files
  if [[ "$dir_name" == "skills" ]]; then
    # Skills are directories with SKILL.md
    fs_files=$(find "$fs_dir" -maxdepth 2 -name "SKILL.md" -not -path "*/_*" 2>/dev/null | \
      sed "s|^$MYLIB/||" | sort || true)
  elif [[ "$dir_name" == "executions" ]]; then
    fs_files=$(find "$fs_dir" -maxdepth 1 -name "*.py" -not -name "__*" 2>/dev/null | \
      sed "s|^$MYLIB/||" | sort || true)
  elif [[ "$dir_name" == "directives" ]]; then
    fs_files=$(find "$fs_dir" -maxdepth 1 -name "*.md" -not -name "index.md" 2>/dev/null | \
      sed "s|^$MYLIB/||" | sort || true)
  elif [[ "$dir_name" == "personas" ]]; then
    fs_files=$(find "$fs_dir" -maxdepth 1 -name "*.md" -not -name "index.md" 2>/dev/null | \
      sed "s|^$MYLIB/||" | sort || true)
  elif [[ "$dir_name" == "context/indexed" ]]; then
    fs_files=$(find "$fs_dir" -maxdepth 1 \( -name "*.md" -o -name "*.yaml" -o -name "*.json" \) -not -name "index.md" 2>/dev/null | \
      sed "s|^$MYLIB/||" | sort || true)
  fi

  # Get paths listed in registry YAML
  local reg_paths
  reg_paths=$(python3 -c "
import yaml, sys
with open('$registry_file') as f:
    data = yaml.safe_load(f) or {}
entries = data.get('$yaml_key', {})
if isinstance(entries, dict):
    for v in entries.values():
        if isinstance(v, dict) and 'path' in v:
            print(v['path'])
elif isinstance(entries, list):
    for item in entries:
        if isinstance(item, dict) and 'path' in item:
            print(item['path'])
" 2>/dev/null | sort || true)

  # Find files on disk but not in registry
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if ! echo "$reg_paths" | grep -qF "$f"; then
      issues="${issues:+$issues,}{\"dir\":\"$dir_name\",\"type\":\"unregistered\",\"detail\":$(json_escape "$f")}"
    fi
  done <<< "$fs_files"

  # Find registry entries pointing to missing files
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    if [[ ! -e "$MYLIB/$p" ]]; then
      issues="${issues:+$issues,}{\"dir\":\"$dir_name\",\"type\":\"missing_file\",\"detail\":$(json_escape "$p")}"
    fi
  done <<< "$reg_paths"

  if [[ -n "$issues" ]]; then
    registry_issues="${registry_issues:+$registry_issues,}$issues"
  fi
}

check_registry "directives" "$MYLIB/registry/directives.yaml" "$MYLIB/directives" "directives"
check_registry "skills" "$MYLIB/registry/skills.yaml" "$MYLIB/skills" "skills"
check_registry "personas" "$MYLIB/registry/personas.yaml" "$MYLIB/personas" "personas"
check_registry "executions" "$MYLIB/registry/executions.yaml" "$MYLIB/executions" "executions"
check_registry "context/indexed" "$MYLIB/registry/context.yaml" "$MYLIB/context/indexed" "context"

# ============================================================
# 3. SYNC NEEDED — What should flow to team-lib?
# ============================================================
sync_items=""

# Check if AGENTS.md changed
if echo "$all_changed" | grep -q "^AGENTS.md$"; then
  sync_items="${sync_items:+$sync_items,}\"agents_md\""
fi

# Check if any skills changed that also exist in team-lib
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ "$f" == skills/* ]]; then
    skill_name=$(echo "$f" | cut -d/ -f2)
    if [[ -d "$TEAMLIB/skills/$skill_name" ]] && ! echo "$sync_items" | grep -qF "skill:$skill_name"; then
      sync_items="${sync_items:+$sync_items,}$(json_escape "skill:$skill_name")"
    fi
  fi
done <<< "$all_changed"

# ============================================================
# 4. STALE FLAGS — current-state.md health
# ============================================================
stale_flags=""
CURRENT_STATE="$MEMORY_DIR/current-state.md"

if [[ -f "$CURRENT_STATE" ]]; then
  # Check last updated date
  last_updated=$(grep -i "last updated" "$CURRENT_STATE" | head -1 | grep -oP '\d{4}-\d{2}-\d{2}' || echo "unknown")
  if [[ "$last_updated" != "unknown" ]]; then
    days_old=$(( ($(date +%s) - $(date -d "$last_updated" +%s 2>/dev/null || echo 0)) / 86400 ))
    if (( days_old > 3 )); then
      stale_flags="${stale_flags:+$stale_flags,}{\"type\":\"state_stale\",\"detail\":\"current-state.md last updated $last_updated ($days_old days ago)\"}"
    fi
  fi

  # Count decisions older than 14 days
  old_decisions=$(python3 -c "
import re, sys
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=14)
count = 0
with open('$CURRENT_STATE') as f:
    for line in f:
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', line)
        for d in dates:
            try:
                if datetime.strptime(d, '%Y-%m-%d') < cutoff:
                    count += 1
                    break
            except: pass
print(count)
" 2>/dev/null || echo "0")

  if (( old_decisions > 0 )); then
    stale_flags="${stale_flags:+$stale_flags,}{\"type\":\"old_decisions\",\"detail\":\"$old_decisions entries with dates older than 14 days — review for pruning\"}"
  fi

  # Check for leftover notes-for-next-session
  has_next_notes=$(grep -c "Notes for Next Session" "$CURRENT_STATE" 2>/dev/null || echo "0")
  # Check if there's content under that header (not just the header itself)
  if (( has_next_notes > 0 )); then
    next_section_content=$(sed -n '/Notes for Next Session/,/^##/p' "$CURRENT_STATE" | grep -v '^#' | grep -v '^$' | head -5)
    if [[ -n "$next_section_content" ]]; then
      stale_flags="${stale_flags:+$stale_flags,}{\"type\":\"pending_notes\",\"detail\":\"Notes for next session exist — consume or clear them\"}"
    fi
  fi
fi

# ============================================================
# 5. SESSION INFO — Timestamps and metadata
# ============================================================
session_start=$(git log --oneline --format='%ci' -1 2>/dev/null | cut -d' ' -f2 | cut -d: -f1-2 || echo "unknown")
session_end=$(date +%H:%M)
today=$(date +%Y-%m-%d)

# Check MEMORY.md line count
memory_index_lines=0
if [[ -f "$MEMORY_DIR/MEMORY.md" ]]; then
  memory_index_lines=$(wc -l < "$MEMORY_DIR/MEMORY.md")
fi

# ============================================================
# 6. MEMORY.md CONSISTENCY — index vs actual files
# ============================================================
memory_issues=""
if [[ -f "$MEMORY_DIR/MEMORY.md" ]]; then
  # Files referenced in MEMORY.md but missing on disk
  while IFS= read -r ref_file; do
    [[ -z "$ref_file" ]] && continue
    if [[ ! -f "$MEMORY_DIR/$ref_file" ]]; then
      memory_issues="${memory_issues:+$memory_issues,}{\"type\":\"missing_file\",\"detail\":$(json_escape "$ref_file")}"
    fi
  done < <(grep -oP '\[.*?\]\(\K[^)]+' "$MEMORY_DIR/MEMORY.md" 2>/dev/null || true)

  # .md files in memory dir not referenced in MEMORY.md (excluding MEMORY.md itself)
  while IFS= read -r mem_file; do
    [[ -z "$mem_file" ]] && continue
    basename_file=$(basename "$mem_file")
    [[ "$basename_file" == "MEMORY.md" ]] && continue
    if ! grep -qF "$basename_file" "$MEMORY_DIR/MEMORY.md" 2>/dev/null; then
      memory_issues="${memory_issues:+$memory_issues,}{\"type\":\"unindexed\",\"detail\":$(json_escape "$basename_file")}"
    fi
  done < <(find "$MEMORY_DIR" -maxdepth 1 -name "*.md" 2>/dev/null || true)
fi

# ============================================================
# 7. SESSION MARKER — unique token the LLM can pass to postflight
# ============================================================
# Rationale: $HOME/.claude/history.jsonl is shared across all concurrent
# Claude Code sessions in a workspace, so /rename events from other sessions
# can collide when matching by sessionId alone. By emitting a unique marker
# on stdout here, that string is captured in THIS session's JSONL (as the
# bash tool_result). Postflight can then `grep -l MARKER ~/.claude/projects/*/*.jsonl`
# to deterministically identify the current session's JSONL — no heuristics.
session_marker="debrief_$(date +%s%N)_$$_$RANDOM"

# ============================================================
# OUTPUT — Structured JSON report
# ============================================================
cat <<REPORT
{
  "session_info": {
    "date": "$today",
    "approx_start": "$session_start",
    "end": "$session_end",
    "memory_index_lines": $memory_index_lines,
    "session_marker": "$session_marker"
  },
  "git_changes": {
    "files_changed": $all_changed_count,
    "recent_commits": $(json_escape "$git_recent_commits"),
    "touched_registered_dirs": [${touched_dirs}],
    "changed_files": $(python3 -c "import json,sys; print(json.dumps([l for l in sys.stdin.read().strip().split('\n') if l]))" <<< "$all_changed")
  },
  "registry_issues": [${registry_issues}],
  "sync_needed": [${sync_items}],
  "stale_flags": [${stale_flags}],
  "memory_issues": [${memory_issues}]
}
REPORT
