#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Finds and removes WSL Zone.Identifier alternate-data-stream files (*:Zone.Identifier) across a workspace root. Defaults to ~/ai-workspace. Supports --dry-run."
# created: 2026-04-09
# last_updated: 2026-04-09
# maintainer: pvragon
# ---
#
# clean_zone_identifiers.sh — Remove WSL Zone.Identifier junk files
#
# WSL creates `*:Zone.Identifier` alternate-data-stream files for anything
# downloaded via Windows/browser. These are harmless metadata but pollute
# git repos, file listings, and backups. This script finds and removes
# them across a workspace root.
#
# Usage:
#   bash clean_zone_identifiers.sh [--dry-run] [--root PATH] [--quiet]
#
# Options:
#   --root PATH    Root directory to scan (default: $HOME/ai-workspace)
#   --dry-run      List files that would be removed; do not delete
#   --quiet        Suppress per-file output; print summary only
#
# Exit codes:
#   0  Success (nothing to clean OR cleanup completed)
#   1  Invalid arguments or root directory missing
#
# Examples:
#   bash clean_zone_identifiers.sh
#   bash clean_zone_identifiers.sh --dry-run
#   bash clean_zone_identifiers.sh --root ~/ai-workspace/personal --quiet

set -euo pipefail

ROOT="${HOME}/ai-workspace"
DRY_RUN=false
QUIET=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --quiet)
      QUIET=true
      shift
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$ROOT" ]]; then
  echo "ERROR: root directory does not exist: $ROOT" >&2
  exit 1
fi

# Find all Zone.Identifier files. The `-name '*:Zone.Identifier'` pattern
# is the canonical WSL form. Use -print0 to safely handle spaces in paths.
mapfile -d '' -t FILES < <(find "$ROOT" -type f -name '*:Zone.Identifier' -print0 2>/dev/null || true)

COUNT=${#FILES[@]}

if (( COUNT == 0 )); then
  [[ "$QUIET" == true ]] || echo "No Zone.Identifier files found under $ROOT"
  exit 0
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "[DRY-RUN] Would remove $COUNT Zone.Identifier file(s) under $ROOT:"
  if [[ "$QUIET" != true ]]; then
    for f in "${FILES[@]}"; do
      echo "  $f"
    done
  fi
  exit 0
fi

# Actually remove them
REMOVED=0
FAILED=0
for f in "${FILES[@]}"; do
  if rm -- "$f" 2>/dev/null; then
    REMOVED=$((REMOVED + 1))
    [[ "$QUIET" == true ]] || echo "  removed: $f"
  else
    FAILED=$((FAILED + 1))
    echo "  FAILED: $f" >&2
  fi
done

echo "Removed $REMOVED Zone.Identifier file(s) under $ROOT${FAILED:+ ($FAILED failed)}"
exit 0
