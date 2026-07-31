---
name: findings
description: Open the findings inbox and WORK it — the audit observations the nightly cycle collected, presented one at a time with a proposed action for each. Use when you have space to clear maintenance debt, or when a debrief offered a findings session. Not a report: the point is to close items, and each one ends dismissed, fixed, or explicitly deferred.
template: skill-definition
version: 1.0.0
summary: "The pull side of the findings inbox. Loads open findings via findings.py, groups them, and works them one at a time — propose, act, dismiss. Exists because findings must never be raised inside another thread: this skill IS the thread."
created: 2026-07-31
last_updated: 2026-07-31
maintainer: pvragon
---

# /findings — work the inbox

## What this is for

The findings inbox collects observations from the nightly audits. It is **pull-only by
design**: findings are never raised inside another thread, because every moment inside
another thread is the wrong one. Session close is *"I need to go"* answered with *"wait,
also this."* Session start is arriving with a goal and being derailed before touching it.

**This skill is the moment.** Nothing else has to be happening. The user came here to clear
debt, so behave accordingly: propose actions, do them, close items. A list read aloud is a
failure — the inbox should be shorter when this ends.

## Run it

```bash
python3 ~/ai-workspace/team-lib/executions/findings.py list
```

## How to work the list

1. **Read the whole list first, then group it.** Several findings usually share one root —
   three dangling wikilinks are one broken rename, not three problems. Say so, and fix the
   root once.

2. **Order by cost-to-fix, not by age.** The statusline sorts by age because age is what
   escalation means; a work session should open with the things that close in one command.
   Momentum matters more than seniority here.

3. **For each finding, propose ONE concrete action, then do it.** Not options. The user
   opened this session to spend attention on decisions that need them, not to arbitrate
   between three ways to fix a dangling link. Every finding ends in exactly one of:
   - **Fixed** — do the work, then `findings.py dismiss <id>`.
   - **Not a problem** — say why in one line, then dismiss. Dismissing is a real outcome;
     an inbox where nothing is ever dismissed is one nobody will open twice.
   - **Real but not now** — leave it open and say what it is waiting on. If it needs to
     become tracked work, write a `my-lib/backlog/YYMMDD-<slug>.md` item and dismiss the
     finding, so it stops occupying two queues.

4. **Do not let this become a new investigation.** If a finding opens something genuinely
   large, capture it as a backlog item and move on. The failure mode of a worklist session
   is finishing one item and calling it a success.

5. **Close with the count.** `N were open, M closed, K remain and why.` The user should be
   able to tell whether this was worth doing.

## Rules

- **Never re-record a finding you just dismissed.** The nightly audit re-detects live
  conditions; if you dismiss something still true, it returns tomorrow. That is correct
  behaviour and not a bug — but if you find yourself dismissing the same finding twice, the
  underlying condition is real and needs a fix or a backlog item, not a third dismissal.
- **Findings that resolve themselves need no action.** `last_seen` going stale closes them
  automatically on the next nightly sweep. If a finding looks already-fixed, verify and
  dismiss rather than waiting.
- **Anything critical should already have been raised at debrief.** If a `[CRITICAL]` item
  is sitting here unmentioned, that is itself worth reporting — the severity gate missed.

## Related

- `team-lib/executions/findings.py` — the store, the two clocks, the statusline segment.
- `team-lib/executions/dream_cycle.py` — what records findings, nightly.
- `skills/session-debrief/SKILL.md` — surfaces CRITICAL only, and offers this session when
  something has gone stale.
