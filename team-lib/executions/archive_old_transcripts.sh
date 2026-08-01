#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.2
# summary: "Archives old Claude Code session artifacts: moves ~/.claude/projects/**/*.jsonl AND the per-session artifact dirs (tool-results/, subagents/, workflows/, logs/) older than N days (default 14) into ~/.claude/projects-archive/, preserving structure. Scoped to those dirs on purpose — the project dir itself holds live state (sessions-index.json, which /resume reads), so a blanket non-jsonl sweep would break session listing. Keeps the live corpus small so the statusline's ccusage cost meter can't re-parse a multi-GB pile, balloon RAM, and thrash swap → freeze the box. Throttled to at most once per 24h via a stamp file (fast no-op otherwise), so it's cheap to call from every session-debrief. Idempotent, same-filesystem renames, --dry-run / --force. Skipping is non-fatal."
# created: 2026-06-11
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# archive_old_transcripts.sh — bound the ~/.claude transcript corpus
#
# WHY: the Claude statusline shells out to `ccusage`, which RE-PARSES the entire
# ~/.claude/projects/**/*.jsonl corpus on every refresh. As that corpus grows
# (long sessions → many 20-31MB transcripts), each ccusage run balloons to ~6GB
# RSS; with several concurrent sessions the kernel overcommits RAM and swaps hard
# → disk-write pegs at 100% → WSL freeze/crash. (See memory:
# reference_ccusage-statusline-swap-thrash-crash.) Keeping only the recent window
# live caps ccusage's per-run cost permanently. The session-debrief postflight
# calls this as a hygiene step so the corpus stays bounded by the normal
# "end clean" act — no cron needed.
#
# WHAT: moves (never deletes — pack-rat rule) *.jsonl AND per-session artifact
# dirs older than N days out of
# the live projects dir into a parallel archive dir, preserving relative paths so
# any session can be restored with a single `mv` back. Archived sessions drop out
# of `/resume` and ccusage history (acceptable: they're older than the kept
# window; ccusage's 5h/7d figures only need recent data).
#
# USAGE:
#   archive_old_transcripts.sh [--days N] [--min-interval-hours H] [--dry-run] [--force]
#     --days N                age threshold in days (default 14)
#     --min-interval-hours H  fast no-op if a real run happened within H hours (default 24)
#     --dry-run               report what would move; change nothing (ignores throttle)
#     --force                 bypass the min-interval throttle
#
# RESTORE a single session:
#   mv ~/.claude/projects-archive/<relpath>.jsonl ~/.claude/projects/<relpath>.jsonl

set -uo pipefail

DAYS=14
DRY_RUN=0
FORCE=0
MIN_INTERVAL_HOURS=24
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)    DAYS="${2:?--days needs a value}"; shift 2 ;;
    --days=*)  DAYS="${1#*=}"; shift ;;
    --min-interval-hours)   MIN_INTERVAL_HOURS="${2:?--min-interval-hours needs a value}"; shift 2 ;;
    --min-interval-hours=*) MIN_INTERVAL_HOURS="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force)   FORCE=1; shift ;;
    -h|--help) sed -n '2,46p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
PROJECTS="$CLAUDE_DIR/projects"
ARCHIVE="$CLAUDE_DIR/projects-archive"
MANIFEST="$ARCHIVE/manifest.tsv"

# Nothing to do if there's no projects dir (fresh machine / non-standard layout).
if [[ ! -d "$PROJECTS" ]]; then
  echo "archive_old_transcripts: no $PROJECTS — nothing to do"
  exit 0
fi

mkdir -p "$ARCHIVE"
STAMP="$ARCHIVE/.last-run"

# Throttle: if a real run happened within MIN_INTERVAL_HOURS, skip in milliseconds.
# (--dry-run and --force bypass.) Lets session-debrief call this every time cheaply.
if (( ! DRY_RUN && ! FORCE )) && [[ -f "$STAMP" ]]; then
  age_s=$(( $(date +%s) - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0) ))
  if (( age_s < MIN_INTERVAL_HOURS * 3600 )); then
    printf 'archive_old_transcripts: skipped (ran %dh ago; min interval %dh)\n' \
      "$(( age_s / 3600 ))" "$MIN_INTERVAL_HOURS"
    exit 0
  fi
fi

moved=0
moved_bytes=0
ts="$(date +%Y-%m-%dT%H:%M:%S 2>/dev/null || echo unknown)"

# Move every *.jsonl older than DAYS, plus the per-session ARTIFACT DIRECTORIES,
# preserving the relative path under projects/.
# -mtime +DAYS excludes anything touched within the window (incl. the active
# session, which is being written right now), so live sessions are never moved.
#
# Why the artifact dirs matter: this used to glob '*.jsonl' ONLY, so everything else
# under projects/ was bounded by nothing. Measured 2026-07-30 — 0.55 GB of managed
# JSONL against 1.20 GB of un-archived residue in 8,428 files, dominated by
# tool-results/*.txt (a tool output too large to inline is spilled to disk and never
# read again; individual spills up to 64 MB). It was invisible because every hygiene
# pass globbed *.jsonl too.
#
# SCOPED DELIBERATELY, not by "everything that is not .jsonl": the project directory
# itself holds LIVE state — sessions-index.json (which /resume reads), its backups,
# and .pool-hook.log. A blanket non-jsonl sweep would archive the session index and
# break session listing. Only the per-session artifact subdirectories are eligible.
while IFS= read -r -d '' f; do
  rel="${f#"$PROJECTS"/}"
  dest="$ARCHIVE/$rel"
  sz=$(stat -c %s "$f" 2>/dev/null || echo 0)
  if (( DRY_RUN )); then
    echo "  would move: $rel (${sz} bytes)"
  else
    mkdir -p "$(dirname "$dest")"
    if mv "$f" "$dest" 2>/dev/null; then
      printf '%s\t%s\t%s\n' "$ts" "$sz" "$rel" >> "$MANIFEST"
    else
      echo "  WARN: failed to move $rel" >&2
      continue
    fi
  fi
  moved=$((moved + 1))
  moved_bytes=$((moved_bytes + sz))
done < <(find "$PROJECTS" -type f -mtime +"$DAYS" \
           \( -name '*.jsonl' \
              -o -path '*/tool-results/*' \
              -o -path '*/subagents/*' \
              -o -path '*/workflows/*' \
              -o -path '*/logs/*' \) -print0 2>/dev/null)

# Stamp a real run so the throttle can fast-skip the next call within the interval.
(( DRY_RUN )) || touch "$STAMP"

# Remaining live-corpus size (what ccusage will re-parse).
live_mb=$(find "$PROJECTS" -type f -name '*.jsonl' -printf '%s\n' 2>/dev/null \
  | awk '{s+=$1} END{printf "%d", s/1024/1024}')

verb=$([[ $DRY_RUN -eq 1 ]] && echo "would archive" || echo "archived")
printf 'archive_old_transcripts: %s %d files (%d MB) older than %dd → %s; live corpus now ~%s MB\n' \
  "$verb" "$moved" "$((moved_bytes/1024/1024))" "$DAYS" "$ARCHIVE" "${live_mb:-?}"
exit 0
