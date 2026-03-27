---
template: integration
version: 1.0.0
type: cli
summary: "Google Workspace CLI (@googleworkspace/cli) — covers Drive, Docs, Sheets, Gmail, Calendar, and Admin Reports. Replaces the Google Workspace MCP, which was removed due to singleton session issues, missing Docs formatting tools, and high token consumption."
created: 2026-03-12
last_updated: 2026-03-27
maintainer: pvragon
---

# Google Workspace CLI (gws)

Use `gws` to interact with Google Workspace APIs directly from the terminal. Covers Drive, Docs, Sheets, Gmail, Calendar, and Admin Reports.

## Why CLI over the MCP

| | MCP | gws CLI |
|---|---|---|
| Reliability | ~72% (singleton sessions, port conflicts) | ~100% |
| Token cost | High (schema overhead per call) | Low (JSON in/out) |
| Docs formatting | Missing (`insertAutoText`, table formatting) | Full via `batchUpdate` |
| Multi-window | Broken (auth stealing between sessions) | Works (OAuth per user) |
| Speed | Slow (MCP protocol overhead) | Fast (~0.5s per call) |

**Decision context:** Google shipped `gws` with MCP mode in v0.5.0, then deliberately removed all 1,151 lines of MCP code in v0.8.0 two days later — context window limits were irreconcilable.

## Prerequisites

1. **Node.js** (v18+) via nvm
2. **Install gws:** `npm install -g @googleworkspace/cli`
3. **OAuth client credentials** at `~/.config/gws/client_secret.json` (Desktop OAuth client from GCP project `pvragon-ai-workspace`)
4. **Authenticate:** `gws auth login` (opens browser for OAuth consent)

## Common Commands

```bash
# Drive
gws drive files list --params '{"q": "name contains '\''report'\''", "pageSize": 10}'
gws drive files get --params '{"fileId": "abc123"}'

# Docs
gws docs documents get --params '{"documentId": "abc123"}'
gws docs documents batchUpdate --params '{"documentId": "abc123"}' --json '{"requests": [...]}'

# Sheets
gws sheets spreadsheets get --params '{"spreadsheetId": "abc123"}'
gws sheets spreadsheets.values get --params '{"spreadsheetId": "abc123", "range": "Sheet1!A1:D10"}'

# Gmail
gws gmail users messages list --params '{"userId": "me", "q": "is:unread"}'
gws gmail users messages send --params '{"userId": "me"}' --json '{"raw": "..."}'

# Calendar
gws calendar events list --params '{"calendarId": "primary", "timeMin": "2026-03-27T00:00:00Z"}'

# Schema discovery
gws schema docs.documents.batchUpdate --resolve-refs
```

## Output Formats

```bash
--format json    # Default — structured JSON
--format table   # Human-readable table
--format yaml    # YAML output
--format csv     # CSV output
```

## Pagination

```bash
--page-all              # Auto-paginate, NDJSON output (one JSON per page)
--page-limit <N>        # Max pages (default: 10)
--page-delay <MS>       # Delay between pages in ms (default: 100)
```

## How Skills Consume This

The `markdown-to-branded-doc` skill uses gws for the full document creation pipeline:

```bash
# Create a new doc
gws docs documents create --json '{"title": "My Document"}'

# Apply formatting via batchUpdate
gws docs documents batchUpdate --params '{"documentId": "..."}' --json @requests.json
```

The `execute-gdoc.js` execution script builds batchUpdate request arrays and pipes them through `gws docs documents batchUpdate`.

## Troubleshooting

- **Auth expired:** Run `gws auth login` to re-authenticate
- **Wrong account:** Check `~/.config/gws/` for stored credentials. Remove and re-auth if needed.
- **Schema discovery:** Use `gws schema <service.resource.method> --resolve-refs` to inspect any API method's parameters and request body
