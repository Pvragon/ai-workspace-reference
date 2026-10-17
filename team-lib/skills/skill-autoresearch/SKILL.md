---
name: skill-autoresearch
description: "Karpathy's autoresearch loop, reproduced faithfully and made reusable: an agent edits ONE artifact, runs an IMMUTABLE evaluator under a FIXED budget, reads ONE scalar metric, keeps the commit if it improved and reverts if not, logs every experiment to results.tsv, and never stops to ask. A program file (programs/*.md, human-edited) points the loop at an artifact, an evaluator and a metric. Ships two programs: output-style (Your Agent's chat voice, blind-judged against frozen references) and skill-clarity (a SKILL.md, scored by an executor's per-step confusion). Use it to improve any artifact whose quality can be measured by a command."
summary: "Faithful, reusable implementation of karpathy/autoresearch: program.md-driven loop (branch per run, one editable file, immutable evaluator, fixed budget, one metric, commit-then-run, keep or git-reset, results.tsv ledger, simplicity criterion, NEVER STOP), plus a ledger/revert helper, two scripted evaluators, and two ready programs (output-style, skill-clarity). Departures from the original are listed and justified."
version: 2.1.2
template: skill-definition
created: 2026-03-16
last_updated: 2026-10-16
maintainer: pvragon
dependencies: []
tags: [meta-skill, autoresearch, self-improvement, evaluation, karpathy]
listing: name-only
category: ai-tooling
---

# Skill: Autoresearch

## What this is

Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) (March 2026) gives an
agent a small real training setup and a one-page `program.md`, then lets it run experiments
overnight: edit `train.py`, train for a fixed 5 minutes, read `val_bpb`, keep the commit if the
number improved, `git reset` if not, log a row to `results.tsv`, repeat, never stop. The human's
job is to edit `program.md` between runs. The README calls that file "essentially a super
lightweight skill".

This skill is that design with the training setup swapped for a **program**: a human-edited file
that names the artifact to edit, the evaluator command that is never edited, the metric line to
grep, and the budget. Two programs ship ready to run, and a template makes a third. The original
`program.md` and README are kept verbatim under `reference/` so fidelity can be checked rather
than remembered.

## Karpathy's design, element by element

| Element of the original | What it does | Here |
|---|---|---|
| `program.md`, human-edited | Sets up the run and states the loop | `programs/<name>.md`, same sections in the same order |
| `train.py`, the only file the agent edits | Keeps scope small and diffs reviewable | The program's artifact file. One file. |
| `prepare.py` + `evaluate_bpb`, read-only | Ground-truth metric the agent cannot game | `evaluate_*.py` plus its assets, read-only by program rule |
| Fixed 5-minute budget | Every experiment comparable | Fixed prompt set x runs x judges, or one executor pass |
| `val_bpb`, one scalar, lower is better | One number to optimise | `score:` or `clarity:`, one line, grep-able |
| VRAM as a soft constraint | Second column, watched not optimised | `words` or `issues`, the ledger's aux column |
| Branch `autoresearch/<tag>` | Isolates the run, reviewable afterwards | Same, in the artifact's repo |
| Commit, then run | Every experiment has a hash | `git commit -am "autoresearch: <idea>"` |
| Keep if improved, else `git reset` | Only evidence advances the branch | `autoresearch_ledger.py decide` and `revert` |
| `results.tsv`, 5 columns, untracked | The research output | Same columns, same rules, helper-written |
| Simplicity criterion | Stops the artifact bloating | Restated per program with domain examples |
| Crash handling, 2x timeout | Failures logged, not debugged forever | Same |
| Baseline first | Row one is the artifact as is | Same |
| NEVER STOP | Human may be asleep | Same wording, plus a rotation note (see departures) |
| Output to `run.log`, grep the metric | Keeps the agent's context small | Same; evaluators print a `---` block for grep |

## Files

```
SKILL.md                         this file
programs/TEMPLATE.md             fill-in program, section for section with the original
programs/output-style.md         Your Agent chat-voice style, blind-judged against frozen references
programs/skill-clarity.md        a SKILL.md, scored by an executor's per-step confusion (the v1 use case)
autoresearch_ledger.py           init / record / best / decide / revert, deterministic
evaluate_output_style_pairwise.py  immutable evaluator for output-style lineage v2 (prints score: = pairwise win fraction, score_se:, guards_ok:)
evaluate_output_style.py         lineage v1 evaluator, kept for the record (Likert composite; saturates near 4.5)
evaluate_skill_clarity.py        immutable evaluator for skill-clarity (prints clarity:)
evaluators/output-style-v2/      17 prompts, fixture/, judge_brief_pairwise.md, reference/ (68 frozen transcripts), build_references.py
evaluators/output-style/         lineage v1 assets (8 prompts, 48 frozen transcripts); operator home paths in transcript text scrubbed to /home/<user> 2026-09-05
reference/karpathy-program.md    the original program.md, verbatim
reference/karpathy-README.md     the original README, verbatim
```

Everything under `evaluators/` and `reference/` is frozen. Changing an evaluator or its assets
starts a new lineage: results before and after are not comparable and must not share a ledger.
Lineage v1 of output-style used an absolute 1-5 composite and saturated near 4.5 with a noise
floor around 0.08, leaving three or four distinguishable steps to the ceiling. Lineage v2 judges
pairwise in both orders, prints a bootstrapped standard error, widens the prompt set into the
territory the complaints come from, and uses deterministic prose tells as guards so the vote
cannot be won by regressing them.

## Procedure

### 1. Pick or write the program

- An existing program: `programs/output-style.md` or `programs/skill-clarity.md`.
- A new one: copy `programs/TEMPLATE.md`, fill every angle-bracket field, and write the evaluator
  it names. The evaluator must be one command that exits 0, prints a `---` block, and puts the
  metric on its own `name: value` line. Non-zero exit is a crash. Nothing the evaluator reads may
  be something the agent can edit. Measure the noise floor before the first real run: evaluate the
  unchanged artifact twice and set the program's threshold above the difference.

### 2. Run the setup section with the user

Exactly as the program says: agree a tag, create the branch, read the in-scope files, verify the
evaluator runs, initialise the ledger, confirm. The human is present for setup and absent after.

### 3. Run the loop

The program's "The experiment loop" section is the procedure. Do not paraphrase it from memory:
open the program and follow it step by step, every iteration. The loop is:

1. Look at the git state.
2. Edit the artifact with one idea.
3. Commit with the `autoresearch:` prefix.
4. Run the evaluator, everything redirected to `run.log`.
5. Grep the metric line.
6. Empty grep is a crash: tail the log, fix if trivial, else log `crash` and move on.
7. Record the row with the helper.
8. `decide` says keep: advance.
9. `decide` says discard: `revert`.

Then go to 1. Never ask whether to continue.

### 4. When the human returns

Hand them `results.tsv` and the branch. The ledger is the deliverable; the branch tip is the best
artifact found. Merging the branch, or cherry-picking from it, is the human's decision.

## Helper reference

```
autoresearch_ledger.py init   --ledger PATH --metric NAME --aux NAME
autoresearch_ledger.py record --ledger PATH --repo DIR --metric V --aux V --status keep|discard|crash --note "..."
autoresearch_ledger.py best   --ledger PATH --direction lower|higher
autoresearch_ledger.py decide --ledger PATH --direction lower|higher --metric V [--threshold T] [--simpler]
autoresearch_ledger.py revert --repo DIR
```

`decide` keeps only a strict improvement larger than the threshold, or any equal-or-better result
when `--simpler` is passed. `revert` runs `git reset --hard HEAD~1` only when HEAD's subject starts
with `autoresearch:` and no tracked file is modified; it never touches an ordinary commit.

## Departures from the original, and why

These are the only places this skill is not a line-for-line reproduction. Each is a consequence
of running it on this workspace rather than a GPU box, not a design opinion.

1. **A program parameter instead of one hard-coded program.** The original has exactly one
   artifact and one evaluator. Reuse needs the loop to be told which. The program file keeps the
   original's sections and order so a reader of his `program.md` recognises ours.
2. **A noise threshold in `decide`.** `val_bpb` on a fixed seed is near-deterministic; a judged
   or executor-scored metric is not (measured 2026-09-04: composite moved about 0.15 on identical
   inputs with one judge). "Improved" therefore means improved by more than the measured floor,
   and each program states its floor. Without this the loop keeps luck.
3. **`--simpler` on `decide`.** His simplicity criterion is prose; ours has a switch so an
   equal-or-better result that removed complexity can be kept mechanically.
4. **The ledger lives under `my-lib/runtime/deliverables/`, not the artifact repo root.** He
   leaves `results.tsv` untracked at the repo root. The runtime file rule here puts every runtime
   artifact under `my-lib/runtime/`, and the ledger is the run's deliverable. It is still untracked
   by the artifact repo.
5. **Two lines about context rotation.** A Claude Code session has a context ceiling. With output
   kept in `run.log` an experiment costs a few thousand tokens, so a night's run fits, but the
   program says what state survives a rotation (branch, ledger, program) so a rotated session
   continues rather than stops. NEVER STOP is otherwise verbatim.
6. **Evaluators are `claude -p` scripts, not Agent-tool subagents.** His evaluator is a Python
   script; ours had to be too. A subagent's return message is not reliably delivered to the
   orchestrator (measured 2026-07-30, delivery fell from 3 of 3 to 1 of 3 with a `name:`), which
   loses whole iterations. A script that writes its report to disk before returning cannot.

## Guidance

- **Read only the summary block.** An evaluator's stdout is for `run.log`. The agent reads the
  grep, the ledger, and for skill-clarity the executor's per-step issues. Nothing else.
- **One idea per experiment.** A commit that changes three things produces a ledger row that
  explains nothing. Karpathy's descriptions are five words long for a reason.
- **Delete things.** The most informative experiments remove a rule, a step, or a paragraph and
  watch whether the metric cares. Half the ideas in a run should be deletions.
- **Do not edit the program mid-run.** If the program is wrong, stop the run, fix it, start a new
  tag. A ledger whose rows were produced under two programs is not one experiment.
- **Fan-out.** Evaluators run `claude -p` in parallel (default 3 jobs). Check `/who` and
  `free -h` before starting a run; this machine has frozen under combined load.
- **Prefer pairwise to absolute.** A model judge is far more consistent at "which is better" than at "rate this 1 to 5", and a win fraction has resolution of one over the ballot count instead of a five-point ceiling. Show both orders so position bias cancels.
- **The judges are Claude.** Any metric a model produces can be optimised for the model's taste.
  The human reading the branch tip against the ledger is the check. Keep it in the loop at the
  end, not in the middle.

## Notes

- The agent running this skill is the researcher. Executors and judges are `claude -p` children
  started by the evaluator.
- Test briefs, ledgers and run logs are run artifacts: `runtime/deliverables/<YYMMDD>-autoresearch-<name>/`.
- The skill produces no deliverable of its own. Its output is the ledger and the improved artifact.
- v1 of this skill (March to August 2026) was a fix-and-rerun loop with self-reported clarity as the
  score and no revert, ledger, budget or simplicity rule. Its use case survives as
  `programs/skill-clarity.md`; its harness lore survives in that program's last section.
