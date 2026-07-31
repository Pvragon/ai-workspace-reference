#!/usr/bin/env bash
# ai-digest M/W/F cron entry point. Builds a PATH that finds gws (nvm node),
# yt-dlp + digest (venv), and node (js_runtime) under cron's minimal env.
set -u
TOOL="$HOME/ai-workspace/team-lib/integrations/ai-digest"
PATH="$TOOL/.venv/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
for d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$d" ] && PATH="$d:$PATH"; done
export PATH
echo "=== $(date -Iseconds) ai-digest poll ==="
exec digest poll
