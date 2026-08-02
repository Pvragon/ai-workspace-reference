---
name: who
description: "Show which other Claude Code sessions are live right now, what each is doing (busy/idle + repo@branch + cwd), and whether each is reachable for messaging (bridged to Remote Control vs local-only). On-demand multi-instance awareness — the active-query companion to the passive PreToolUse roster advisory. Use when about to edit shared files, before starting parallel work, or when the user asks 'what are my other sessions doing?'."
template: skill-definition
version: 1.0.0
summary: "Shows which other Claude Code sessions are live right now, what each is doing (busy/idle + repo@branch + cwd) and whether it is reachable for messaging — the active-query companion to the passive PreToolUse roster advisory."
created: 2026-07-11
last_updated: 2026-08-01
maintainer: pvragon
template: skill-definition
version: 1.0.0
created: 2026-07-11
last_updated: 2026-07-11
maintainer: pvragon
tags: [multi-agent, coordination, session, awareness, observability]
---

# /who — live session awareness

Answers "what are all my other instantiations doing right now?" on demand.

## What it does

Runs `executions/session_activity.py who`, which composes
`list_claude_sessions.run()` (disk = source of truth — works for every live
session, including ones started before the coordination hooks were wired) and
enriches each with:

- **status** — busy / idle
- **repo@branch** — the collision-relevant location
- **reach** — `bridge` (Remote-Control-bridged → addressable for Tier 3
  session-to-session messaging via its `bridgeSessionId`) or `local` (not
  reachable for messaging)
- **cwd** — full working directory; `*` marks the current session

## Run

```bash
python3 ~/ai-workspace/team-lib/executions/session_activity.py who
```

Present the result as a compact table. Call out any **repo+branch shared by 2+
sessions** — that's an active edit-collision zone worth coordinating.

## Relationship to the rest of the coordination layer

- **Passive half** (always on): the PreToolUse roster advisory in
  `session_activity.py` warns you at edit time when a peer shares your
  repo+branch. See `backlog/260429-multi-agent-coordination-tiers.md`.
- **This (active half)**: pull the full picture whenever you want it.
- **Tier 3 (planned)**: `reach=bridge` sessions can be sent a question via the
  native Remote Control trigger API (`create_trigger`/`fire_trigger` with
  `persistent_session_id = bridgeSessionId`) and woken to answer.
