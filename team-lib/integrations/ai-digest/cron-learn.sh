#!/usr/bin/env bash
# ai-digest hourly `learn` cron entry point (playlist learnings summaries).
# Same robust-PATH approach as cron-poll.sh so gws/yt-dlp/digest/node resolve.
set -u
TOOL="$HOME/ai-workspace/team-lib/integrations/ai-digest"
PATH="$TOOL/.venv/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
for d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$d" ] && PATH="$d:$PATH"; done
export PATH
echo "=== $(date -Iseconds) ai-digest learn ==="
exec digest learn
