#!/usr/bin/bash
# ---
# name: mailbox_triage.sh
# summary: Periodic agent-mailbox check. Cheap deterministic poll of the cross-machine
#          mailbox; spawns a Claude triage session ONLY when unread mail exists, so empty
#          checks cost ~nothing. Reply/escalation policy lives in mailbox_triage_prompt.md
#          (and directives/agent-mailbox.md). Wire it to cron at whatever cadence you want.
# version: 1.0.0
# created: 2026-07-22
# maintainer: pvragon
# ---
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_BIN:-$(command -v claude || echo claude)}"
WORKDIR="${MAILBOX_TRIAGE_CWD:-$HOME/ai-workspace/my-lib}"
TS="$(date '+%Y-%m-%d %H:%M:%S %Z')"

# Cheap deterministic check (also pulls the shared repo). No LLM cost.
UNREAD="$(python3 -c "import sys; sys.path.insert(0,'$HERE'); from agent_mailbox import run; print(len(run('inbox').get('messages',[])))" 2>/dev/null || echo 0)"

if [ "${UNREAD:-0}" -eq 0 ]; then
    echo "$TS  no new mail (0 unread) — skipping triage session"
    exit 0
fi

echo "$TS  $UNREAD unread message(s) — launching triage session"
cd "$WORKDIR" || exit 1
# env -u ANTHROPIC_API_KEY => use the Max/Pro subscription, not metered API billing.
env -u ANTHROPIC_API_KEY timeout 600 "$CLAUDE" -p "$(cat "$HERE/mailbox_triage_prompt.md")" --dangerously-skip-permissions
echo "$TS  triage session finished"
