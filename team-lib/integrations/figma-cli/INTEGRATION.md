---
template: integration
version: 1.1.0
type: cli
summary: "Figma CLI via Restish and Figma's official OpenAPI spec (54 operations): read files, export images, read and post comments. Auth via personal access token (90-day expiry) injected by the figma-cli wrapper, since Restish v2 cannot reference env vars in credentials. REST cannot edit canvas content."
created: 2026-10-21
last_updated: 2026-10-21
maintainer: your-agent
---

# Figma CLI (Restish)

Use `figma-cli` (a thin wrapper over `restish figma ...`) to read Figma files, export node images and work with comments from the terminal.

## Prerequisites

1. Restish v2.3.0+ on PATH (`~/.local/bin/restish` or mise shim).
2. `FIGMA_TOKEN` in `~/ai-workspace/personal/secrets/.env`.
3. A `figma` API entry in `~/.config/restish/restish.json` (mode 600) and the spec at `~/.config/restish/figma-openapi.yaml`.
4. `figma-cli` on PATH: `ln -sf ~/ai-workspace/team-lib/integrations/figma-cli/figma-cli ~/.local/bin/figma-cli`.

## Setup

1. Download the spec: `curl -sSL https://raw.githubusercontent.com/figma/rest-api-spec/main/openapi/openapi.yaml -o ~/.config/restish/figma-openapi.yaml`
2. Merge `restish-apis-template.json` into `restish.json` under `apis`.
3. Restish v2 refuses every operation unless a credential binding exists for the spec's security scheme. Bind it (needs a TTY, e.g. `script -qc "restish api auth add figma PersonalAccessToken" /dev/null`), choosing api-key, in header, name `X-Figma-Token`. When asked for the value, enter any placeholder, NOT the real token.
4. Always call through `figma-cli`, which loads the token from `.env` and sends it with `-H`. A `-H` header overrides the credential value.

## Why a wrapper

Restish v2 sends a credential value literally: `${VAR}`, `$VAR`, `env:VAR` and template forms are not expanded (verified 2026-10-21; no env-reference syntax exists in the binary or README). The profile `headers` entry does expand env vars but the credential binding wins over it. The wrapper keeps the real token only in `.env`, never in `restish.json`.

## Token creation and rotation

1. Figma: Settings > Security > Personal access tokens > Generate new token.
2. Scopes: File content (read), File metadata (read), Comments (read and write), Current user (read).
3. Tokens expire after at most 90 days. Rotate before expiry: generate a new token with the same scopes, replace `FIGMA_TOKEN` in `.env`, run `figma-cli get-me -f status` (expect 200), revoke the old token in Figma.
4. Current token created 2026-10-21, expires 2027-01-19. The expiry date lives in `.env` as `FIGMA_TOKEN_EXPIRES=YYYY-MM-DD`; rotating means updating BOTH `FIGMA_TOKEN` and `FIGMA_TOKEN_EXPIRES`.
5. `figma-cli` warns on stderr (once a day) within 14 days of that date, and on a missing, 401 or 403 token prints the rotation steps and exits 3. On that message, tell the operator and open `micro ~/ai-workspace/personal/secrets/.env` for him.
6. Use `figma-cli`, never the Figma MCP. Nothing in the workspace currently tracks credential expiry centrally (checked 2026-10-21), so this wrapper is the only reminder.

## Common commands

```bash
figma-cli get-me                                   # who am I (smoke test)
figma-cli get-file FILE_KEY --depth 1 -f 'body.document.children[].name'
figma-cli get-images FILE_KEY 1:2,1:3 --format png --scale 2   # ids are positional; URLs expire after 30 days
figma-cli get-comments FILE_KEY -f 'body.comments[].{id,message,user:user.handle}'
echo '{"message":"Looks good"}' | figma-cli post-comment FILE_KEY
```

FILE_KEY is the segment after `/design/` (or `/file/`) in a Figma URL. Run `restish figma --help` for all 54 operations.

## Limits

- The REST API cannot create or edit canvas content (frames, layers, text). Editing needs a Figma plugin or the Figma MCP (Dev Mode).
- Image export URLs expire after 30 days; download what you need.
- Variables endpoints need Enterprise plan scopes; expect 403 otherwise.
- Other Restish v2 profiles (samsara, n8n) have the same unbound-credential problem and need their own bindings or a `-H` wrapper.

## Destructive operations: need the operator's explicit go

`delete-comment`, `delete-comment-reaction`, `post-webhook`, `put-webhook`, `delete-webhook`, `post-variables` (variables write), `post-dev-resources`, `put-dev-resources`, `delete-dev-resource`. Reads and `post-comment` on files the operator named are fine; anything else that writes, ask first.
