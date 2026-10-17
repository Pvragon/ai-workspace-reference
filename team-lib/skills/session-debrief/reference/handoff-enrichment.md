---
template: skill-reference
version: 1.0.0
summary: "Session-debrief step for debriefs that follow a /handoff: find the right handoff brief and append a Debrief addendum with what the debrief surfaced. Append-only; abstains when the brief is ambiguous."
created: 2026-10-06
last_updated: 2026-10-06
maintainer: pvragon
---

# Handoff Brief Enrichment

When this debrief follows a `/handoff`, the brief was written and the new window started before the debrief ran. Anything the debrief surfaced is invisible to the new session unless it goes into the brief.

## 1. Find the brief

Use the first that applies:
1. **The path the caller gave you** ("enrich the brief at …"). `/handoff` passes it explicitly, and it is the only method that cannot pick the wrong brief.
2. **`$AGENT_HOME/handoffs/.pending-enrichment/*.json`,** only if exactly one entry is less than 6 hours old. If two or more are, name the candidates to the user and append nothing.
3. **Nothing.** Skip this step; it is not an error.

Never pick the newest file in `handoffs/`. Concurrent sessions write their own briefs the same day, so the newest is often another thread's.

## 2. Append, never rewrite

Add one section at the very end of the brief:

```markdown
## Debrief addendum — YYYY-MM-DD HH:MM

Surfaced by the originating session's debrief, after this brief was written.

- <finding, and what it changes about the work queue above>
```

A person may have edited the brief, and the new session may already have read it. So do not touch anything above your section. If a finding invalidates a queue item, say so in the addendum ("item 5 is likely moot because …") instead of editing the item.

## 3. Append nothing if nothing surfaced

An empty addendum teaches the next session to skip addenda.

## 4. Consume the pointer

Delete the `.pending-enrichment/*.json` entry you used, so a later debrief does not enrich a stale brief.
