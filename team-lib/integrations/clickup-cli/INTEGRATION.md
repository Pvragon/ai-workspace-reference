---
template: integration
version: 1.0.0
type: cli
summary: "ClickUp CLI integration via Restish — covers full v2 + v3 API surface including task comments with @mentions and Chat messaging. Replaces the ClickUp MCP."
created: 2026-03-19
last_updated: 2026-03-20
maintainer: pvragon
---

# ClickUp CLI (Restish)

Use Restish to interact with the ClickUp API directly from the terminal. Covers the full v2 and v3 API surface — tasks, comments, chat messages, members, sprints, and more.

## Why Restish over the MCP

| | MCP | Restish |
|---|---|---|
| Reliability | ~72% | ~100% |
| Token cost | High (schema overhead) | Low (JSON in/out) |
| Task comments with @mentions | No | **Yes** |
| Chat messages (v3) | Yes (plain text only) | **Yes** |
| Chat @mentions | No | No (ClickUp API limitation) |
| Speed | Slow (MCP protocol overhead) | Fast (~0.6s per call) |

## Prerequisites

1. **Restish** installed at `~/.local/bin/restish` (or on PATH)
2. **ClickUp API token** (`pk_...`) in `~/ai-workspace/personal/secrets/.env` as `CLICKUP_API_TOKEN`
3. **Restish config** at `~/.config/restish/apis.json` (see Setup below)

## Setup

### 1. Install Restish

```bash
# Download pre-built binary (Linux amd64)
gh release download --repo rest-sh/restish --pattern 'restish-*-linux-amd64.tar.gz' --dir /tmp
tar -xzf /tmp/restish-*-linux-amd64.tar.gz -C /tmp
mv /tmp/restish ~/.local/bin/restish
chmod +x ~/.local/bin/restish
```

### 2. Configure APIs

Copy the template config:

```bash
mkdir -p ~/.config/restish
cp team-lib/skills/clickup-cli/restish-apis-template.json ~/.config/restish/apis.json
```

Then edit `~/.config/restish/apis.json` and replace `YOUR_TOKEN_HERE` with your ClickUp API token.

### 3. Verify

```bash
# List workspace members
restish clickup-v2/team/YOUR_WORKSPACE_ID -f 'team.members[].user.{id, username, email}'

# List chat channels
restish clickup-v3/workspaces/YOUR_WORKSPACE_ID/chat/channels
```

## Common Operations

### Task Comments

```bash
# Plain text comment
echo '{"comment_text": "Deployed to staging"}' | restish post clickup-v2/task/TASK_ID/comment

# Comment with @mention (use clickup_mention_comment.py wrapper)
python3 team-lib/skills/clickup-cli/clickup_mention_comment.py \
  --task TASK_ID \
  --message "Hey @Jane Smith can you review this?"

# Multiple @mentions
python3 team-lib/skills/clickup-cli/clickup_mention_comment.py \
  --task TASK_ID \
  --message "@Sam Lee @Alex Kim ready for QA"
```

### Chat Messages (v3)

```bash
# Send a message to a channel
restish post clickup-v3/workspaces/YOUR_WORKSPACE_ID/chat/channels/CHANNEL_ID/messages \
  type: message, content: "Hello from the CLI"

# List channels (find channel IDs)
restish clickup-v3/workspaces/YOUR_WORKSPACE_ID/chat/channels -f 'data[].{id, name, type}'
```

### Tasks

```bash
# Get a task
restish clickup-v2/task/TASK_ID

# Create a task
echo '{"name": "New task", "description": "Details here"}' | restish post clickup-v2/list/LIST_ID/task

# Update a task
echo '{"status": "in progress"}' | restish put clickup-v2/task/TASK_ID
```

### Members

```bash
# List all workspace members
restish clickup-v2/team/YOUR_WORKSPACE_ID -f 'team.members[].user.{id, username, email}'
```

## Known Limitations

- **Chat @mentions are not possible** — the ClickUp v3 Chat API does not support structured mention tags. This is a ClickUp API limitation, not a tooling gap.
- **Task comment @mentions require the wrapper script** — Restish alone can post the structured JSON, but you'd need to manually construct the `comment` array with user IDs. The wrapper resolves `@Name` automatically.

## Key Channel IDs (record yours here)

| Channel | ID |
|---|---|
| general | `X-XXXXXXXXXXXX-X` |
| my-project | `X-XXXXXXXXXXXX-X` |
| pulse | `X-XXXXXXXXXXXX-X` |

Use `restish clickup-v3/workspaces/YOUR_WORKSPACE_ID/chat/channels` for the full list.
