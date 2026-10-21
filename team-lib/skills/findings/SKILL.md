---
name: findings
description: >-
  Open the findings inbox and WORK it — the audit observations the nightly cycle collected,
  presented one at a time with a proposed action for each. Use when you have space to clear
  maintenance debt, or when a debrief offered a findings session. Not a report: the point is to
  close items, and each one ends dismissed, fixed, or explicitly deferred.
template: skill-definition
version: 1.1.0
summary: "The pull side of the findings inbox. Loads open findings via findings.py, groups them, and works them one at a time — propose, act, dismiss. Documents the three lanes (auto, ask, hands-off), the nightly findings_resolver.py that works the auto lane, and the one-line morning readout the brief quotes."
created: 2026-07-31
last_updated: 2026-10-20
maintainer: pvragon
listing: name-only
category: workspace
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

## Lanes: who each finding belongs to

Every finding is in one of three lanes (`findings.py list` shows it in brackets, `--lane` filters):

| Lane | Meaning | Who acts |
|---|---|---|
| `auto` | Stale-verifiable findings, mechanical fixes in Your Agent's own tooling, memory hygiene, version/registry upkeep, publication housekeeping, and free-form debrief findings with no decision in them. | The nightly resolver, then Your Agent in a session. the operator only hears a count. |
| `ask` | A decision that is the operator's: money, people, outward messages, authorship (including writing a summary), a choice between two reasonable options, or a question filed with `--hold`. | the operator. These are the only findings the statusline counts. |
| `hands-off` | An open workstream (current-state In Flight / Just Handed Off) or a live peer session owns it. | Nobody here. Recorded only; never acted on and never escalated. |

The lane comes from the first matching rule in `team-lib/config/findings-lanes.yaml`, plus the personal
overlay `my-lib/config/findings-lanes.yaml` (client names and team repos, which must not appear in the
published file). Rows recorded before lanes existed are classified by the same rules. A lane set by
hand sticks: `findings.py lane <id> <auto|ask|hands-off> --note "why"`. A recorder that already knows
can pass `record --lane ask`.

**The statusline counts only `ask`.** A number there means "needs the operator"; its format is unchanged.

## The nightly resolver

`team-lib/executions/findings_resolver.py` runs inside the dream cycle, after findings are recorded and
swept. No LLM: deterministic re-checks and fix kinds only. For each open finding:

- **hands-off**: skipped.
- **ownership first**: a finding a workstream or live session owns moves to hands-off (a strong match
  — a workstream slug, its first two words, a live session's name — for any lane except `--hold`; a
  weak one-word match only for `auto`).
- **re-check**: each known kind re-runs the check that produced it (layer_drift_scan, memory_self_check,
  the sweep, the census, git ahead-of-upstream, and so on). Proven stale -> dismissed with a note
  starting `resolver <date>`. This also applies to `ask` findings of a known kind; nothing else
  is ever done to an `ask` finding.
- **fix (live mode only)**: a whitelist — push the cycle's own version/registry commits (only to
  `push_repos`, only when every commit ahead is the cycle's own by subject, only with `allow_push:
  true`), `memory_self_check --fix-safe` (not while a session is writing memory), re-pin external
  skill packs (commit `.gitmodules` only). A fix that a hard-line pattern matches is never applied.
- **two failed nights** (still true, no fix or the fix did not take) -> moved to `ask`.
- **unknown kind** (most debrief findings): left open and counted as waiting for a session. That is
  this skill's job.

Hard lines the resolver has no code path for: production data writes, client/billing/investigation
files, sending messages or emails, other sessions' commits, pushing the public reference repo,
deleting files, team repos.

**Shadow mode** (`mode: shadow` in the config, the default since 2026-10-20) dismisses stale findings
and nothing else; every fix, lane move and attempt is logged as what it WOULD do. After a week of
`agents/your-agent/runtime/logs/findings_resolver.log` (note `live_after: 2026-10-27`), the operator or
Your Agent reviews it and sets `mode: live` (and `allow_push: true` if pushes looked right). Nothing flips
automatically. Manual runs: `findings_resolver.py --shadow` or `--live` override the config for that
run; `--only <id>` restricts it; `--json` prints the full result.

## The morning readout

Each run writes `agents/your-agent/runtime/state/findings-resolver-last.txt`, one line, and
`findings-resolver-last.json` with the detail (`handled`, `stale_dismissed`, `would`, `needs_you`,
`needs_you_open`, `waiting`, `hands_off`, `errors`). Live line: `Handled 4 overnight; 1 needs you:
<text>`. Shadow line: `Shadow: closed 2 stale, would fix 1; nothing needs you`.

**How the morning brief quotes it:** read the `.txt` and say that line, verbatim or nearly, as one
sentence — a brief verbal readout, nothing more. Only if it says something needs the operator, name that
item (from `needs_you_open` in the `.json`) and offer this skill. Never read out the auto or
hands-off lists unless asked. If the file's date (`date` in the `.json`) is not today, say the
resolver did not run last night instead of quoting a stale line.

## How to work the list

0. **Start with what the resolver left.** `findings.py list --lane ask` is what needs the operator;
   `--lane auto` is Your Agent's own backlog. When the operator says "take care of these with your best
   judgement", work the auto lane without asking and bring only the ask lane to him.

1. **Read the whole list first, then group it.** Several findings usually share one root —
   three dangling wikilinks are one broken rename, not three problems. Say so, and fix the
   root once.

2. **Order by cost-to-fix, not by age.** The statusline sorts by age because age is what
   escalation means; a work session should open with the things that close in one command.
   Momentum matters more than seniority here.

3. **For each finding, propose ONE concrete action, then do it.** Not options. The user
   opened this session to spend attention on decisions that need them, not to arbitrate
   between three ways to fix a dangling link. Every finding ends in exactly one of:
   - **Fixed** — do the work, then `findings.py dismiss <id> --note "<what was done or decided>"`. The note is the receipt: a closed status alone does not say an answer happened.
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

- `team-lib/executions/findings.py` — the store, the two clocks, the lanes, the statusline segment.
- `team-lib/executions/findings_resolver.py` — the nightly resolver for the auto lane.
- `team-lib/config/findings-lanes.yaml` — the lane rules, the mode switch, the push whitelist.
- `team-lib/executions/dream_cycle.py` — what records findings, nightly.
- `skills/session-debrief/SKILL.md` — surfaces CRITICAL only, and offers this session when
  something has gone stale.
