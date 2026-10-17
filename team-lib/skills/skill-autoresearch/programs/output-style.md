---
template: autoresearch-program
version: 2.1.1
summary: Autoresearch program for the Your Agent chat-voice output style (lineage v2). The agent edits the style file; the evaluator runs 17 prompts on Opus 5 in a vanilla directory with read-only tools and judges each reply pairwise, in both orders, against frozen Concise and ASD-STE100 references under the complaint-derived rubric. Metric is the win fraction with a bootstrapped keep threshold; deterministic tells are guards.
created: 2026-09-04
last_updated: 2026-09-04
maintainer: pvragon
---

# autoresearch: output-style

This is an experiment to have the LLM do its own research on its own chat voice: the Claude Code output style that governs how it writes to the user.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `sep4`). The branch `autoresearch/<tag>` must not already exist in `~/ai-workspace/agents/your-agent` — this is a fresh run.
2. **Create the branch**: `git -C ~/ai-workspace/agents/your-agent checkout -b autoresearch/<tag>` from `main`.
3. **Read the in-scope files**:
   - `~/ai-workspace/agents/your-agent/output-styles/your-agent-output-style.md` — the file you modify.
   - `~/ai-workspace/team-lib/skills/skill-autoresearch/evaluate_output_style_pairwise.py` and everything under `evaluators/output-style-v2/` (17 prompts, fixture, pairwise judge brief, frozen Concise and ASD-STE100 references) — the fixed evaluation. Do not modify.
   - This program.
   - Background, read once: `evaluators/output-style-v2/judge_brief_pairwise.md` says what the judges reward. The complaint research it came from is in `my-lib/runtime/.tmp/260903-output-style-test/opus5-complaints-research.md`.
4. **Verify the evaluator runs**: `python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/evaluate_output_style_pairwise.py --help` exits 0, and `claude --version` works with no `ANTHROPIC_API_KEY` in the environment.
5. **Initialize results.tsv**: `python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/autoresearch_ledger.py init --ledger ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-output-style/results.tsv --metric score --aux words`.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs the evaluator with a **fixed budget of 17 prompts x 2 runs, each reply judged against 2 references in both orders** (34 candidate replies, 136 ballots), on `claude-opus-5` for both candidate and judges. You launch it as:

```
python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/evaluate_output_style_pairwise.py \
  --style ~/ai-workspace/agents/your-agent/output-styles/your-agent-output-style.md \
  --out ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-output-style/exp-<n> \
  --baseline-tells ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-output-style/exp-1/tells.json > run.log 2>&1
```

Omit `--baseline-tells` on the two baseline runs only.

**What you CAN do:**
- Modify `your-agent-output-style.md` — this is the only file you edit. Everything in it is fair game: which rules exist, how they are phrased, their order, the countable limits, the examples, the length of the file. Keep the frontmatter's `keep-coding-instructions: true`; without it the style replaces Claude Code's engineering instructions instead of layering on them.

**What you CANNOT do:**
- Modify the evaluator, the prompt set, the fixture, the judge brief, or the reference transcripts. They are the ground truth.
- Modify this program. The human edits it between runs.
- Change `--runs`, `--refs`, `--jobs` above what the machine allows, `--model` or `--judge-model` between experiments.

**The goal is simple: get the highest score.** `score` is the fraction of pairwise ballots the candidate wins against the frozen references, each judged under the six-criterion rubric with a correctness gate. Since the budget and the references are fixed, every experiment is directly comparable.

**Guards** are hard constraints, printed by the evaluator and summarised as `guards_ok`: `correctness_min` at least 3, `emdash_per100` at most 0.10, `long_sentences` at most 0.10, `closing_offers` and `narration` at most 0.10 per reply, `words` at most 1.5 x the reference mean. They are deterministic and they exist so the loop cannot win the vote by regressing the things people actually complain about. With `--baseline-tells` each cap becomes "no worse than max(cap, 1.25 x baseline + 0.02)", so a baseline that already breaches a cap does not condemn every later experiment. `guards_ok: 0` means discard regardless of score; `guards_failed` names the culprit. **Words** is otherwise a soft constraint and the ledger's aux column.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds a paragraph of rules is not worth it. Conversely, removing a rule and getting equal or better results is a great outcome — that's a simplification win. A 0.02 score gain that adds 200 words of rules? Probably not worth it. A 0.02 gain from deleting a rule? Definitely keep. A ~0 change with a much shorter file? Keep. Styles bloat one rule at a time; this criterion is what stops it.

**Noise floor**: the evaluator prints `score_se` (a cluster bootstrap over packets) and `keep_threshold` (2 x `score_se`) on every run. Use that run's `keep_threshold` in `decide`; do not hard-code one. Pass `--simpler` when the change removed rules or words. The two baseline runs at setup are the sanity check: their scores should differ by less than either run's threshold.

**The first runs**: Your very first two runs establish the baseline and measure the noise: run the evaluator on the style as is, twice, and record both rows (the second as `discard` with note "baseline repeat, noise check"). If the two scores differ by more than either run's `keep_threshold`, stop and tell the human: the evaluator is noisier than its own estimate.

## Output format

Once the evaluator finishes it prints a summary like this:

```
---
score:            0.7188
score_se:         0.0410
keep_threshold:   0.0820
win_vs_Concise:   0.7500
win_vs_ASD-STE100: 0.6875
quality:          4.31
readability:      4.58
correctness_min:  4
words:            281.3
emdash_per100:    0.04
long_sentences:   0.04
closing_offers:   0.06
narration:        0.00
words_cap:        480.0
guards_ok:        1
packets:          34
ballots:          136
crashed_runs:     0
failed_judges:    0
```

Extract the key lines from the log file:

```
grep "^score:\|^keep_threshold:\|^words:\|^guards_ok:" run.log
```

## Logging results

```
python3 ~/ai-workspace/team-lib/skills/skill-autoresearch/autoresearch_ledger.py record \
  --ledger ~/ai-workspace/my-lib/runtime/deliverables/<YYMMDD>-autoresearch-output-style/results.tsv \
  --repo ~/ai-workspace/agents/your-agent --metric <score> --aux <words> --status keep|discard|crash --note "<what this experiment tried>"
```

Five columns: `commit  score  words  status  description`. Use 0.000000 and 0.0 on crashes. Do not commit results.tsv.

## The experiment loop

The experiment runs on branch `autoresearch/<tag>` of the your-agent repo.

LOOP FOREVER:

1. Look at the git state: `git -C ~/ai-workspace/agents/your-agent log --oneline -3`.
2. Tune `your-agent-output-style.md` with one experimental idea. One idea per experiment, so the ledger says what worked.
3. `git -C ~/ai-workspace/agents/your-agent commit -am "autoresearch: <one-line idea>"`
4. Run the experiment with the command above, output redirected to run.log. Never tee it.
5. Read out the results: `grep "^score:\|^keep_threshold:\|^words:\|^guards_ok:" run.log`
6. If the grep output is empty, the run crashed. `tail -n 50 run.log`. Fix if dumb, else log crash and move on.
7. Record the row with the helper.
8. If `guards_ok` is 0, discard. Otherwise `python3 .../autoresearch_ledger.py decide --ledger <ledger> --direction higher --metric <score> --threshold <this run's keep_threshold> [--simpler]`. If it prints keep, advance the branch.
9. Otherwise `python3 .../autoresearch_ledger.py revert --repo ~/ai-workspace/agents/your-agent`.

The references are Concise and ASD-STE100 because they were the two strongest competitors in the three judged rounds; Default was never close. Ideas worth trying first, from those rounds: the judges' quoted leaks were closing offers, plan-file mentions, and mild figures of speech ("own-goal", "burned you before"); completeness (4.06) trails ASD-STE100 (4.38), and its "never drop a fact" rule is the candidate lever; the countable limits table worked where bullet prose did not, so try moving other rules into that form; try deleting rules to test which ones the score actually needs.

**Timeout**: Each experiment should take about 40 minutes at `--jobs 3`. If a run exceeds 80, kill it and treat it as a failure (discard and revert). Check `free -h` before raising `--jobs`; 5 is the most this machine has taken.

**Crashes**: exit code 2 from the evaluator means a candidate run or a judge produced no output. Read run.log; a 401 means an API key is set in the environment; a timeout means the machine is loaded, check `/who` and `free -h` before retrying.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep and expects you to continue working *indefinitely* until you are manually stopped. If you run out of ideas, think harder — re-read the judge brief for criteria the current file does not address, re-read the ledger for near-misses worth combining, try deleting things. The loop runs until the human interrupts you, period.

**Context**: keep every evaluator's output in run.log, never in your context. At about 40 minutes and a few thousand tokens per experiment, an overnight session yields roughly 12 experiments. If the session must be rotated, the branch, the ledger and this program are the whole state; the next session continues the loop from the branch tip. Rotation is not a stop.
