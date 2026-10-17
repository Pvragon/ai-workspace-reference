#!/usr/bin/env bash
# ai-digest `primer` cron entry point — the concept-level rapid primer.
#
# Runs AFTER the M/W/F poll has landed its transcripts. The poll paces transcript
# fetches ~10 min apart (transcript_min_interval_sec), so a 15-fetch poll can take
# ~2.5h; this fires late enough that the primer sees that poll's transcripts.
#
# Reads ONLY from the on-disk transcript store — no YouTube calls, so it cannot
# contribute to a transcript-endpoint block no matter how often it runs.
#
# WIDE WINDOW ON PURPOSE. Convergence needs enough creators covering the same
# period to collide; measured 2026-07-30 on the same corpus:
#     30 videos  -> 171 ideas,  1 converging
#    136 videos  -> 536 ideas, 24 converging
# Concept extraction is cached per video, so a wide window only pays for
# transcripts fetched since the last run (~15/poll), not the whole window.
# Same robust-PATH approach as cron-poll.sh so gws/digest/node resolve under cron.
set -u
TOOL="$HOME/ai-workspace/team-lib/integrations/ai-digest"
PATH="$TOOL/.venv/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
for d in "$HOME"/.nvm/versions/node/*/bin; do [ -d "$d" ] && PATH="$d:$PATH"; done
export PATH
echo "=== $(date -Iseconds) ai-digest primer ==="
exec digest primer -n "${PRIMER_N:-120}"
