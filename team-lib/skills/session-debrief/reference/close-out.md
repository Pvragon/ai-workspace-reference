---
template: skill-reference
version: 1.0.0
summary: "Session-debrief Phase 4 wording rules: findings get one line of keys unless recorded critical, subagent flags are mechanical facts only, and stale findings get a one-line offer of a dedicated session, never a list."
created: 2026-10-06
last_updated: 2026-10-06
maintainer: pvragon
---

# Phase 4: Close-out Rules

The close is where the user is trying to leave. Anything that hands them new work there derails them, so findings are filed, not announced.

## Findings: one line of keys

If you filed findings in 2e, say exactly this and nothing more:

> *"Added to the findings inbox: `<key>`, `<key>`, `<key>`."*

No summaries, no "worth a look", no severity commentary. If you filed nothing, say nothing about findings.

You may write more about a finding only if you recorded it with `--severity critical` in 2e. Do not re-judge severity at close. The test was made earlier, with the tool: would anything be materially worse if the user read this tomorrow?

## Subagent flags: mechanical facts only

Report only mechanical facts a subagent flagged: a headline shortened, a file changed under an edit, a render that withheld an item. An observation about the workspace is a finding, and goes to the inbox under the rule above.

## The stale-findings offer, last

```bash
python3 ~/ai-workspace/team-lib/executions/findings.py escalations --json
```

If it returns anything, end with one line, an offer and never the content:

> *"There are N findings waiting, oldest Xd. Want me to open a session to go through them?"*

Do not list the findings, even briefly; naming them turns the close into the derailment this rule prevents. If the user says yes:

```bash
bash ~/.claude/skills/handoff/handoff.sh findings-worklist \
  --seed "Run /findings and work the list with me." --dir ~/ai-workspace/my-lib
```

A fresh inbox stays silent; only `escalations` (very old or critical) triggers the offer.
