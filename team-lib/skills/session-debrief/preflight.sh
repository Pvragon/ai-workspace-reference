#!/usr/bin/env bash
# ---
# template: execution
# version: 1.2.1
# summary: "Deterministic pre-flight for session-debrief: collects git changes, checks registry consistency, detects sync needs, flags stale state, pre-stages today's T1 facts/residue files, head-starts background transcript+state-dump jobs. Outputs structured JSON."
# created: 2026-03-31
# last_updated: 2026-07-31
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

# Resolve a script across BOTH layers, personal first. Mirrors postflight's
# helper. Needed because shared tooling graduates to team-lib over time, and a
# hardcoded "$MYLIB/executions/..." silently no-ops the moment it does.
resolve_script() {
  local relpath="$1"
  for root in "$MYLIB" "$TEAMLIB"; do
    [[ -z "$root" ]] && continue
    if [[ -x "$root/$relpath" ]]; then
      echo "$root/$relpath"
      return 0
    fi
  done
  return 1
}
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

  # Count decisions older than 14 days.
  #
  # This scanned EVERY line of current-state.md for ANY date substring, which made it a
  # false positive by construction — it conflated "a date appears somewhere in this file"
  # with "a stale decision exists." On 2026-07-31 it reported 3; all three were legitimate:
  # two ship-dates cited in Follow-On workstream prose, and one date quoted INSIDE a
  # same-day decision ("retiring the 2026-04-30 un-graduation rationale").
  #
  # Two independent bugs, and scoping alone fixes only the first:
  #   1. no section scoping — Follow-On/Handed-Off prose was being counted as decisions;
  #   2. no anchoring — a FRESH decision that merely mentions an old date still misfires.
  # So: read only the `## Recent Decisions` section, and only the leading `- YYYY-MM-DD:`
  # entry stamp. A date in the body of a decision is prose, not the decision's age.
  #
  # Same family as feedback_probe-must-not-collapse-unknown-into-a-value: a probe that
  # measures something adjacent to what it claims to measure. Here it over-reported, which
  # is the benign direction — it spends attention rather than withholding it — but a flag
  # that cries wolf every run is one the operator learns to skip, and then it protects
  # nothing on the day a decision really has gone stale.
  old_decisions=$(python3 -c "
import re
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=14)
count, in_section = 0, False
with open('$CURRENT_STATE') as f:
    for line in f:
        if line.startswith('## '):
            in_section = line.startswith('## Recent Decisions')
            continue
        if not in_section:
            continue
        m = re.match(r'\s*-\s*(\d{4}-\d{2}-\d{2}):', line)   # the entry stamp ONLY
        if not m:
            continue
        try:
            if datetime.strptime(m.group(1), '%Y-%m-%d') < cutoff:
                count += 1
        except ValueError:
            pass
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
# Session start comes from THIS session's own transcript, not from git.
#
# It used to be `git log -1` — the timestamp of the most RECENT commit. Since a debrief
# almost always runs just after committing, that reported the session as starting seconds
# ago: on 2026-07-30 it claimed 15:47->15:49, a two-minute window, for a session that
# shipped 20+ commits across four repos. Anything downstream reasoning about session
# duration from that field was reading noise.
#
# $CLAUDE_CODE_SESSION_ID identifies our own JSONL unambiguously, even with a dozen
# concurrent sessions — no guessing by mtime, which picks whichever peer wrote last.
session_start="unknown"
_proj_dir="$HOME/.claude/projects/$(pwd | sed 's#/#-#g')"
_sid="${CLAUDE_CODE_SESSION_ID:-}"
if [[ -n "$_sid" && -f "$_proj_dir/$_sid.jsonl" ]]; then
  session_start=$(python3 -c '
import json, sys
from datetime import datetime
# JSONL timestamps are UTC ("...Z"); session_end is LOCAL (date +%H:%M). Comparing them
# raw produced a start AFTER the end (20:05 -> 16:22). Convert to local before printing.
#
# And print the DATE too when the session did not start today. Bare "%H:%M" silently
# reports a cross-midnight session as if it began this morning: on 2026-07-31 a session
# that actually started 2026-07-30 13:46 and ran ~28h reported "13:46", which a debrief
# subagent then used to conclude that the sessions own earlier work belonged to some
# previous session. Same failure family as the UTC/local bug fixed above — a correct
# clock time carrying an implied-and-wrong date.
try:
    with open(sys.argv[1]) as f:
        for line in f:
            try: rec = json.loads(line)
            except Exception: continue
            ts = rec.get("timestamp")
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
                today = datetime.now().astimezone().date()
                print(dt.strftime("%H:%M") if dt.date() == today
                      else dt.strftime("%m-%d %H:%M"))
                break
except Exception:
    pass
' "$_proj_dir/$_sid.jsonl" 2>/dev/null || echo "unknown")
fi
# Fall back to the oldest commit in the last 48h — still a proxy, but an OLDEST one, so
# it errs toward over-reporting the window rather than collapsing it to nothing.
# NOT scoped to "today": that truncates a session which began yesterday to whatever it
# happened to do after midnight, which is the same defect the primary path had.
if [[ -z "$session_start" || "$session_start" == "unknown" ]]; then
  _oldest=$(git log --format='%ci' --since="48 hours ago" 2>/dev/null | tail -1)
  if [[ -n "$_oldest" ]]; then
    _od=$(echo "$_oldest" | cut -d' ' -f1)
    _ot=$(echo "$_oldest" | cut -d' ' -f2 | cut -d: -f1-2)
    if [[ "$_od" == "$(date +%Y-%m-%d)" ]]; then
      session_start="$_ot"
    else
      session_start="$(echo "$_od" | cut -d- -f2-3) $_ot"
    fi
  fi
  [[ -z "$session_start" ]] && session_start="unknown"
fi
# Machine-readable companions, so downstream never has to re-derive this.
if [[ "$session_start" == *" "* ]]; then session_spans_midnight=true; else session_spans_midnight=false; fi
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

  # .md files in memory dir not referenced in EITHER index (MEMORY.md OR the
  # rolled-off MEMORY-archive.md). Both index files are excluded from the scan.
  while IFS= read -r mem_file; do
    [[ -z "$mem_file" ]] && continue
    basename_file=$(basename "$mem_file")
    [[ "$basename_file" == "MEMORY.md" || "$basename_file" == "MEMORY-archive.md" ]] && continue
    if ! grep -qF "$basename_file" "$MEMORY_DIR/MEMORY.md" 2>/dev/null \
       && ! grep -qF "$basename_file" "$MEMORY_DIR/MEMORY-archive.md" 2>/dev/null; then
      memory_issues="${memory_issues:+$memory_issues,}{\"type\":\"unindexed\",\"detail\":$(json_escape "$basename_file")}"
    fi
  done < <(find "$MEMORY_DIR" -maxdepth 1 -name "*.md" 2>/dev/null || true)
fi

# ============================================================
# 7. PRE-STAGE T1 FILES — today's facts + residue scaffolds
# ============================================================
# Saves the LLM a tool call per debrief: today's `short-term/YYMMDD-{facts,residue}.md`
# files exist with frontmatter; the LLM just appends content during memory capture.
# Idempotent: skip if already created (multi-session day).
SHORT_TERM_DIR="$MEMORY_DIR/short-term"
mkdir -p "$SHORT_TERM_DIR" 2>/dev/null || true

YYMMDD=$(date +%y%m%d)
YYYY_MM_DD=$(date +%Y-%m-%d)
T1_FACTS_PATH="memory/short-term/${YYMMDD}-facts.md"
T1_RESIDUE_PATH="memory/short-term/${YYMMDD}-residue.md"
T1_FACTS_ABS="$MEMORY_DIR/short-term/${YYMMDD}-facts.md"
T1_RESIDUE_ABS="$MEMORY_DIR/short-term/${YYMMDD}-residue.md"

t1_facts_created="false"
t1_residue_created="false"

if [[ ! -f "$T1_FACTS_ABS" ]]; then
  cat > "$T1_FACTS_ABS" <<EOF
---
name: ${YYMMDD}-facts
description: T1 episodic facts captured at session-debrief on ${YYYY_MM_DD}. One block per session within the day. Sibling to ${YYMMDD}-residue.md (texture/pickup-state).
type: facts
date: ${YYYY_MM_DD}
version: 1.0.0
---

# Facts — ${YYYY_MM_DD}

T1 episodic facts. One block per session.

EOF
  t1_facts_created="true"
fi

if [[ ! -f "$T1_RESIDUE_ABS" ]]; then
  cat > "$T1_RESIDUE_ABS" <<EOF
---
name: ${YYMMDD}-residue
description: Per-session texture/pickup-state residue blocks for ${YYYY_MM_DD}. Append per session. Sibling to ${YYMMDD}-facts.md.
type: residue
date: ${YYYY_MM_DD}
version: 1.0.0
---

# Residue — ${YYYY_MM_DD}

Per-session texture / pickup-state. Anchors *where things were trending* on this date. Append for each session.

EOF
  t1_residue_created="true"
fi

# ============================================================
# 8. BACKGROUND HEAD-START — transcripts + system-state dump
# ============================================================
# Kick off deterministic postflight work (transcript extraction, system-state dump)
# in the background while the LLM does Phase 2 work. Postflight will re-run them
# (idempotent skip-by-mtime) — the head start just means most of the work is done
# by the time postflight reaches step 0b/0c. Saves ~5-15s wall-clock.
EXTRACT_TRANSCRIPTS=$(resolve_script "executions/extract_session_transcripts.py" || true)
DUMP_STATE=$(resolve_script "executions/dump_system_state.py" || true)

BG_LOG_DIR="$MYLIB/runtime/logs"
mkdir -p "$BG_LOG_DIR" 2>/dev/null || true

[[ -n "$EXTRACT_TRANSCRIPTS" ]] || echo "WARNING: extract_session_transcripts.py not found in my-lib or team-lib" >&2
if [[ -x "$EXTRACT_TRANSCRIPTS" ]]; then
  nohup python3 "$EXTRACT_TRANSCRIPTS" >> "$BG_LOG_DIR/preflight_bg_transcripts.log" 2>&1 </dev/null &
  disown 2>/dev/null || true
fi

[[ -n "$DUMP_STATE" ]] || echo "WARNING: dump_system_state.py not found in my-lib or team-lib" >&2
if [[ -x "$DUMP_STATE" ]]; then
  nohup python3 "$DUMP_STATE" --quiet >> "$BG_LOG_DIR/preflight_bg_state.log" 2>&1 </dev/null &
  disown 2>/dev/null || true
fi

# Fleet snapshot (added 2026-07-24). Debrief time is exactly when a workstream
# rotates generation via /handoff, which is what silently staleness-rots the
# nightly midnight snapshot: on 2026-07-24 a WSL/VS Code restart found the 00:00
# snapshot pointing at waystar -13 and mahjong-constituents -4 while -14 and -5
# were the live windows. Snapshotting here keeps a same-day record of which
# sessions were actually OPEN — a signal that does NOT survive on disk and cannot
# be reconstructed from the JSONL logs afterward (mtime shows *activity*, not
# openness, so open-but-idle windows are indistinguishable from closed ones).
# --tag debrief prunes in its own bucket, so it never evicts the nightly snapshots.
SNAPSHOT_FLEET=$(resolve_script "executions/session_snapshots.py" || true)
[[ -n "$SNAPSHOT_FLEET" ]] || echo "WARNING: session_snapshots.py not found in my-lib or team-lib" >&2
if [[ -f "$SNAPSHOT_FLEET" ]]; then
  nohup python3 "$SNAPSHOT_FLEET" store --tag debrief --keep 40 \
    >> "$BG_LOG_DIR/preflight_bg_snapshot.log" 2>&1 </dev/null &
  disown 2>/dev/null || true
fi

# ============================================================
# 8b. MACHINE LOAD — the pre-fan-out check, made non-optional
# ============================================================
# feedback_concurrent-load-freeze-260713 says to check `/who` AND `free -h` before
# running >=3 workers. The machine froze by that exact mechanism twice (2026-07-13,
# 2026-07-30). The second time the rule was current, had been read that same day, and
# `/who` was checked — `free -h` was not. A safeguard phrased as "remember to check X
# first" fails precisely when it matters: about to fan out, late in a long session.
#
# So nobody is asked to run a command. Preflight already runs before every debrief and
# already shells out; it now REPORTS the numbers and states which fan-out mode is safe.
# It never blocks — combined load across sessions is not observable from inside one
# session, so the value is in surfacing the number, not in refusing.
# The thresholds live in ONE place — team-lib/executions/machine_load.py — because the
# PreToolUse advisory on Agent spawns needs the same numbers, and two copies of a
# threshold is how they start disagreeing (AGENTS.md principle 15).
_load_script=""
for _root in "$TEAMLIB" "$WS_MYLIB" "$MYLIB"; do
  [[ -n "$_root" && -f "$_root/executions/machine_load.py" ]] && { _load_script="$_root/executions/machine_load.py"; break; }
done
if [[ -n "$_load_script" ]]; then
  _machine_load=$(python3 "$_load_script" 2>/dev/null)
fi
# Never let a failed probe read as a healthy machine.
[[ -z "${_machine_load:-}" ]] && _machine_load='{"fanout_verdict":"unknown","safe_parallel_workers":0,"why":"machine_load.py unavailable — assume nothing"}'

# ============================================================
# 9. SESSION MARKER — unique token the LLM can pass to postflight
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
    "spans_midnight": $session_spans_midnight,
    "end": "$session_end",
    "memory_index_lines": $memory_index_lines,
    "session_marker": "$session_marker",
    "machine_load": $(python3 -c '
import json,sys
d = json.loads(sys.stdin.read())
d["note"] = ("READ THIS BEFORE ANY FAN-OUT. Do not spawn more than safe_parallel_workers "
             "concurrent subagents; verdict serial-only means one at a time. Advisory, never "
             "blocking — combined load across concurrent sessions is not observable from inside "
             "one session. Two whole-machine freezes (2026-07-13, 2026-07-30) came from ignoring "
             "exactly this; the second time the operator checked peers but not memory.")
print(json.dumps(d))' <<< "$_machine_load")
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
  "memory_issues": [${memory_issues}],
  "t1_files_staged": {
    "facts_path": "$T1_FACTS_ABS",
    "residue_path": "$T1_RESIDUE_ABS",
    "memory_dir_canonical": "$MEMORY_DIR",
    "facts_created_now": $t1_facts_created,
    "residue_created_now": $t1_residue_created,
    "note": "Paths are CANONICAL absolute paths under the canonical agent memory dir (emitted above as memory_dir_canonical). ALWAYS write memory via these canonical paths. NEVER write via the ~/.claude/projects/<cwd>/memory symlink alias — that path is inside the PROTECTED .claude/ directory, so writes there prompt for permission on EVERY Edit/Write regardless of allow-rules or permission mode (a PreToolUse allow-hook cannot rescue protected-dir writes; verified 2026-06-25). Both files exist with frontmatter; the memory-capture subagent appends content."
  },
  "background_jobs": {
    "transcripts": "head-started; postflight step 0b will mostly skip-as-up-to-date",
    "system_state": "head-started; postflight step 0c will mostly skip-as-up-to-date",
    "log_dir": "runtime/logs/"
  }
}
REPORT
