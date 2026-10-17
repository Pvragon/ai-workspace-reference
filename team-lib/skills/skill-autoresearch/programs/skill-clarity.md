---
template: autoresearch-program
version: 2.0.0
summary: Autoresearch program for improving a SKILL.md — the agent edits the target skill, the evaluator runs a claude -p executor in a throwaway worktree against a fixed test brief and reports per-step clarity. Metric is mean clarity 1-10, higher is better. This is the original (v1) use of this skill, recast as a faithful autoresearch program.
created: 2026-03-16
last_updated: 2026-09-04
maintainer: pvragon
---

# autoresearch: skill-clarity

This is an experiment to have the LLM do its own research on how clearly a skill procedure reads to an agent that has never seen it. The executor's confusion IS the test signal: if it has to guess, the skill's instructions are the problem, not the executor.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date and the skill (e.g. `sep4-debrief`). The branch `autoresearch/<tag>` must not already exist in the repo that holds the target skill.
2. **Create the branch**: `git -C <skill repo> checkout -b autoresearch/<tag>`.
3. **Read the in-scope files**:
   - `<skill repo>/skills/<name>/SKILL.md` and its templates, scripts and reference files — the files you modify.
   - `~/ai-workspace/team-lib/skills/skill-autoresearch/evaluate_skill_clarity.py` — the fixed evaluation. Do not modify.
   - The test brief (below). Once written it is frozen for the run.
   - This program.
4. **Write the test brief** at `~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-<skill>/brief.md` using the template at the end of this program. It must let the executor fill at least 80% of the skill's expected output, include some intentional gaps and at least one edge case, and be self-contained. Freeze it: the brief is part of the evaluator.
5. **Initialize results.tsv**: `python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/autoresearch_ledger.py init --ledger ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-<skill>/results.tsv --metric clarity --aux issues`.
6. **Confirm and go**.

## Experimentation

Each experiment runs one executor in a fresh worktree with a **fixed budget of one full pass of the skill in one mode** on `claude-opus-5`:

```
python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/evaluate_skill_clarity.py \
  --repo <skill repo> --skill <skill repo>/skills/<name>/SKILL.md \
  --brief ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-<skill>/brief.md \
  --out ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-<skill>/exp-<n> --mode create > run.log 2>&1
```

**What you CAN do:**
- Modify the target skill's SKILL.md, its templates, and its scripts. Rewrite low-clarity steps, fix scripts that fail, clarify template fields, add missing steps, resolve contradictions in favour of the more specific instruction, document exit-code behaviour.

**What you CANNOT do:**
- Modify the evaluator, the brief, this program, or the executor prompt inside the evaluator.
- Change `--mode` or `--model` between experiments. Test a second mode as a separate run with its own tag and ledger.

**The goal is simple: get the highest clarity.** `clarity` is the executor's mean per-step score, 1 to 10. `completed` must be 1 and `min_step` must be at least 7 for a keep, whatever the mean says: an executor that finished with one step it had to guess at has found a defect the mean averaged away.

**Issues** is a soft constraint; it is the aux column.

**Simplicity criterion**: All else being equal, simpler is better. Skills accrete caveats. A clarity gain that adds a page of warnings is not worth it; a gain from deleting a contradictory paragraph is a great outcome. The highest-ROI additions seen so far are field-mapping tables (source terminology to the skill's vocabulary), read-only markers on system-documentation columns, and explicit exit-code behaviour for called scripts; the lowest are restated warnings.

**Noise floor**: one executor per experiment. Identical skills re-run score within about 0.5. Threshold: `--threshold 0.5`. Pass `--simpler` when the change removed text.

**The first run**: establish the baseline by evaluating the skill as is.

## Output format

```
---
clarity:          8.4000
min_step:         7
steps:            9
completed:        1
blocking_steps:   0
issues:           3
```

```
grep "^clarity:\|^min_step:\|^completed:" run.log
```

The full executor report (per-step issues, what worked, suggestions) is at `<out>/executor_report.json`. Read it to choose the next idea; it is what Karpathy's `tail -n 50 run.log` is for.

## Logging results

```
python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/autoresearch_ledger.py record --ledger <ledger> --repo <skill repo> --metric <clarity> --aux <issues> --status keep|discard|crash --note "<what this experiment tried>"
```

## The experiment loop

LOOP FOREVER:

1. `git -C <skill repo> log --oneline -3`
2. Edit the skill files with one idea, drawn from the last executor report's lowest-clarity step.
3. `git -C <skill repo> commit -am "autoresearch: <one-line idea>"`
4. Run the evaluator, output to run.log.
5. `grep "^clarity:\|^min_step:\|^completed:" run.log`
6. Empty grep means crash: `tail -n 50 run.log`.
7. Record the row.
8. `autoresearch_ledger.py decide --direction higher --metric <clarity> --threshold 0.5 [--simpler]`, and keep only if `completed` is 1 and `min_step` is at least 7.
9. Otherwise `autoresearch_ledger.py revert --repo <skill repo>`.

**Timeout**: about 10 to 20 minutes per experiment depending on the skill. Over 40, kill and discard.

**Crashes**: exit 2 means no parseable executor report; the stdout is in `<out>/executor_stdout.json`. An executor that stops to ask a question has hit a brief gap: fix the brief only before the baseline, never mid-run.

**NEVER STOP** once the loop has begun. If you run out of ideas, re-read the executor's `suggestions`, combine near-misses from the ledger, or delete something.

**Context**: read only the summary block and the report's per-step issues, never the executor's stdout. Rotation is not a stop.

## Test brief template

```markdown
# Test Brief: [Scenario Name]

> Simulated input for testing the [skill-name] skill. The executor treats this as what a real user would provide.

## Scenario
[What is the user trying to accomplish?]

## Source Materials
[The actual content the executor will use as input: colours, text, data, files.]

## Simulated User Behavior
- When asked to confirm: [confirm / reject / partial]
- When asked to fill gaps: [provide values / skip / done]
- When asked to choose: [which option]

## Expected Output
[What the output should approximately contain.]

## Edge Cases Included
[Each intentional edge case and what correct handling looks like.]
```

## Why the evaluator is a script and not an Agent-tool subagent

The v1 skill spawned the executor with the Agent tool and scored from its return message. Measured 2026-07-30: a background subagent's final text is not delivered to the orchestrator, and adding `name:` alone dropped delivery from 3 of 3 to 1 of 3, so whole iterations vanished with their worktree. A `claude -p` executor writes its report to a path outside the worktree before returning, and the evaluator scores from that file. There is no return message to lose.
