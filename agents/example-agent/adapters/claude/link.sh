#!/usr/bin/env bash
# Creates/refreshes symlinks from Claude Code's vendor directories
# to this agent's consolidated memory pool.
#
# Usage: bash link.sh
#
# This script scans ~/.claude/projects/ for project directories and
# creates symlinks so that all Claude Code sessions — regardless of
# which working directory they were launched from — share the same
# agent memory.

set -euo pipefail

AGENT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
MEMORY_DIR="$AGENT_DIR/memory"
CLAUDE_PROJECTS="$HOME/.claude/projects"

if [ ! -d "$CLAUDE_PROJECTS" ]; then
    echo "No Claude projects directory found at $CLAUDE_PROJECTS"
    exit 0
fi

for project_dir in "$CLAUDE_PROJECTS"/*/; do
    [ -d "$project_dir" ] || continue
    target="$project_dir/memory"

    if [ -L "$target" ]; then
        # Already a symlink — check if it points to the right place
        current=$(readlink -f "$target" 2>/dev/null || true)
        if [ "$current" = "$(readlink -f "$MEMORY_DIR")" ]; then
            continue
        fi
        rm "$target"
    elif [ -d "$target" ]; then
        echo "WARNING: $target is a real directory, skipping (back up and remove to link)"
        continue
    fi

    ln -s "$MEMORY_DIR" "$target"
    echo "Linked: $target -> $MEMORY_DIR"
done
