---
name: session-debrief
description: "Graduated to team-lib — see team-lib/skills/session-debrief/. This stub demonstrates the my-lib → team-lib graduation pattern."
summary: "This skill started life in my-lib and was promoted to the shared library once it stabilized. The canonical version (with preflight/postflight scripts) now lives in team-lib/skills/session-debrief/."
version: 2.0.0
created: 2026-02-20
last_updated: 2026-07-09
maintainer: pvragon
status: graduated
---

# Session Debrief (graduated)

This skill has **graduated to the shared library**: see [`team-lib/skills/session-debrief/`](../../../team-lib/skills/session-debrief/SKILL.md) for the canonical, current version — including the `preflight.sh` / `postflight.sh` scripts that do the deterministic work.

## Why this stub exists

It demonstrates the **graduation lifecycle** that keeps the workspace healthy:

1. A capability starts as a personal skill in `my-lib/skills/` — fast to iterate, only you depend on it.
2. Once it stabilizes and proves useful beyond one person, it's promoted to `team-lib/skills/` via the [`graduate-to-team-library`](../../directives/graduate-to-team-library.md) directive.
3. The my-lib copy becomes a pointer (this file) so nothing links to a stale duplicate.

If you're building your own workspace from this reference: run the debrief from the team-lib copy.
