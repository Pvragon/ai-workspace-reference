---
name: send-pulse
description: "Send an on-demand manual pulse to the ClickUp Pulse channel and optionally register thread-to-task mappings."
summary: "Posts a concise work pulse to the Pulse channel. Can also register the current Claude thread as linked to a ClickUp task for downstream activity correlation."
version: 2.1.0
created: 2026-03-25
last_updated: 2026-03-26
maintainer: pvragon
related:
  - executions/pulse_activity_poster.py  # cron: posts to task activity threads
  - executions/pulse_aw_summary.py       # cron: AW summaries to Pulse channel
  - runtime/.tmp/pulse-thread-registry.jsonl  # thread→task mapping (ephemeral)
---

# Send Pulse

Post a concise manual pulse to the ClickUp Pulse channel and/or register a thread-to-task link.

## When to Use

- **Manual pulse**: User says "send a pulse", "pulse update", "post a pulse", or similar.
- **Task registration**: User says "this is task X", "link this to task X", "register this thread to X", or similar. This can be combined with a pulse in the same invocation.

## Message Format

```
JH Manual Pulse <HH:MM AM/PM>: <concise summary>
```

- Get current time via `date +"%I:%M %p"`.
- Keep it to **one sentence**, two max. Match the brevity of ActivityWatch pulses.
- Focus on what's happening right now or what just happened.
- No signature. No sign-off.
- Infer the summary from the conversation thread — do NOT ask the user what to write.

### Examples

```
JH Manual Pulse 02:15 PM: Built send-pulse skill v2 with thread-to-task registry for downstream ticket correlation.
JH Manual Pulse 10:30 AM: Reviewing Farhan's W1 infra plan against ADR 260323, found 3 issues so far.
JH Manual Pulse 04:45 PM: Wrapped schema review with Roman — all 5 tables approved, ready for migration script.
```

## Task Registration

When the user links the current thread to a ClickUp task, append a registration entry to the registry file at `~/ai-workspace/my-lib/runtime/.tmp/pulse-thread-registry.jsonl` (one JSON object per line):

```json
{"thread_name": "<Claude session/thread name>", "task_id": "<ClickUp task ID>", "task_name": "<task name if known>", "registered_at": "<ISO 8601 timestamp>"}
```

- The thread name should match what ActivityWatch sees in tmux (the Claude Code session title).
- If the user provides a task ID, look up the task name via restish if not already known.
- If the user provides a task name but no ID, try to match it against their assigned tasks.

When a registration happens, also post a pulse announcing the link:

```
JH Manual Pulse <HH:MM AM/PM>: Thread "<thread name>" registered to task <task_id> (<task name>).
```

## Posting

Post immediately without asking for confirmation.

```bash
source ~/ai-workspace/personal/secrets/.env && echo '{"type":"message","content":"<message>"}' | restish post clickup-v3/workspaces/9011906822/chat/channels/5-90117802942-8/messages
```

**Important**: Escape any double quotes in the message content with `\"`.

## Confirm Result

Tell the user whether the post succeeded or failed. If a registration was saved, confirm that too. Done.
