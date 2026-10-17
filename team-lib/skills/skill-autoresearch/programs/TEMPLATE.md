---
template: autoresearch-program
version: 2.0.0
summary: Template for an autoresearch program — the one file a human edits to point the loop at an artifact, an immutable evaluator and a metric. Mirrors karpathy/autoresearch program.md section for section; fill every <angle> field.
created: 2026-09-04
last_updated: 2026-09-04
maintainer: pvragon
---

# autoresearch: <program name>

This is an experiment to have the LLM do its own research on <what>.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `sep4`). The branch `autoresearch/<tag>` must not already exist in `<artifact repo>` — this is a fresh run.
2. **Create the branch**: `git -C <artifact repo> checkout -b autoresearch/<tag>` from the current default branch.
3. **Read the in-scope files**:
   - `<artifact file>` — the file you modify.
   - `<evaluator script>` and everything under `<evaluator assets dir>` — the fixed evaluation. Do not modify.
   - This program.
4. **Verify the evaluator runs**: `<evaluator command> --help` exits 0. If it does not, tell the human.
5. **Initialize results.tsv**: `python3 <skill dir>/autoresearch_ledger.py init --ledger <ledger path> --metric <metric name> --aux <aux name>`. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs the evaluator with a **fixed budget of <budget: N prompts x M runs x K judges, or N minutes>**. You launch it as: `<evaluator command> > run.log 2>&1`.

**What you CAN do:**
- Modify `<artifact file>` — this is the only file you edit. Everything in it is fair game: <examples of what may change>.

**What you CANNOT do:**
- Modify the evaluator script, its assets, the prompt set, the rubric, or the reference set. They are the ground truth.
- Modify this program. The human edits it between runs.
- Change the budget, the model, or any evaluator flag between experiments.

**The goal is simple: get the <lowest|highest> <metric>.** Since the budget is fixed, every experiment is directly comparable.

**<Aux constraint>** is a soft constraint. <e.g. Words per reply may rise for a meaningful score gain, but should not blow up.>

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome — that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude. A tiny gain that adds a paragraph of rules? Probably not worth it. A tiny gain from deleting a rule? Definitely keep. An improvement of ~0 but a much simpler file? Keep.

**Noise floor**: the evaluator is not deterministic. Two runs of the same artifact differ by about <measured noise>. An improvement smaller than `<threshold>` is not an improvement; the ledger helper enforces this: `autoresearch_ledger.py decide --threshold <threshold>`. Pass `--simpler` when the change removed complexity, which lets an equal-or-better result through (the simplicity criterion).

**The first run**: Your very first run should always be to establish the baseline, so you will run the evaluator on the artifact as is.

## Output format

Once the evaluator finishes it prints a summary like this:

```
---
<metric>:         <example>
<aux>:            <example>
...
```

Extract the key metric from the log file:

```
grep "^<metric>:" run.log
```

## Logging results

When an experiment is done, log it to results.tsv (tab-separated, NOT comma-separated — commas break in descriptions). Use the helper so the row is well-formed:

```
python3 <skill dir>/autoresearch_ledger.py record --ledger <ledger path> --repo <artifact repo> --metric <value> --aux <value> --status keep|discard|crash --note "<what this experiment tried>"
```

The TSV has a header row and 5 columns: `commit  <metric>  <aux>  status  description`. Use 0.000000 for the metric and 0.0 for aux on crashes. Do not commit results.tsv; it lives at `<ledger path>` under my-lib/runtime, outside the artifact repo.

## The experiment loop

The experiment runs on a dedicated branch (`autoresearch/<tag>`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on.
2. Tune `<artifact file>` with an experimental idea by directly editing it.
3. `git commit -am "autoresearch: <one-line idea>"` (the `autoresearch:` prefix is what lets the revert helper recognise an experiment commit).
4. Run the experiment: `<evaluator command> > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context).
5. Read out the results: `grep "^<metric>:\|^<aux>:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the error and attempt a fix. If you can't get things to work after more than a few attempts, give up.
7. Record the results in the tsv with the helper.
8. If the metric improved beyond the noise floor (`autoresearch_ledger.py decide` prints keep), you "advance" the branch, keeping the git commit.
9. If it is equal or worse, revert: `python3 <skill dir>/autoresearch_ledger.py revert --repo <artifact repo>` (it refuses unless HEAD is an `autoresearch:` commit).

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate. If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever).

**Timeout**: Each experiment should take about <expected minutes>. If a run exceeds twice that, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes, use your judgment: if it's something dumb and easy to fix, fix it and re-run. If the idea itself is fundamentally broken, skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — re-read the in-scope files for new angles, re-read the ledger for near-misses worth combining, try more radical changes. The loop runs until the human interrupts you, period.

**Context**: keep every evaluator's output in run.log, never in your context. An experiment costs a few thousand tokens of context when done this way, so a session can run <N> experiments before it needs rotating. If context must be rotated, the branch and results.tsv are the whole state: the next session reads this program, the ledger and the branch tip and continues the loop. Rotation is not a stop.
