---
name: skill-autoresearch
description: "Iterative improvement loop for skills — launches executor agents that follow a skill procedure, scores output quantitatively, fixes issues, and repeats until stop criteria are met. Inspired by Karpathy's autoresearch pattern applied to agent skill procedures."
summary: "Meta-skill that stress-tests and improves other skills through an automated loop: create test scenario → executor agent follows skill in worktree → score confusion + output quality → fix skill files → repeat until convergence."
version: 1.0.0
template: skill-definition
created: 2026-03-16
last_updated: 2026-03-16
maintainer: pvragon
dependencies: []
tags: [meta-skill, quality, testing, autoresearch, self-improvement]
---

# Skill: Skill Autoresearch

## When to Use

- After building or significantly updating a skill, to validate it works end-to-end
- When a skill has known confusion points or failure modes
- Before promoting a skill from draft to production use
- When onboarding a skill written by someone else (stress-test before trusting)
- Periodically, to catch drift between SKILL.md instructions and actual tool behavior

## How It Works

```
                         ┌─────────────────────────┐
                         │   SETUP (one-time)       │
                         │                          │
                         │  1. Choose target skill   │
                         │  2. Create test brief     │
                         │  3. Define stop criteria  │
                         └──────────┬───────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │                                            │
              │   ITERATION LOOP                           │
              │                                            │
              │   ┌──────────────────────────────────┐     │
              │   │ Executor Agent (worktree)         │     │
              │   │ - Reads target SKILL.md           │     │
              │   │ - Follows procedure step by step  │     │
              │   │ - Uses test brief as input         │     │
              │   │ - Reports confusion log per step  │     │
              │   └──────────────┬─────────────────────┘    │
              │                  │                          │
              │   ┌──────────────▼─────────────────────┐    │
              │   │ Score (orchestrator)                │    │
              │   │ - Average clarity across steps      │    │
              │   │ - Tool/script success (0/1)         │    │
              │   │ - Output quality metrics            │    │
              │   │ - Compare to stop criteria          │    │
              │   └──────────────┬─────────────────────┘    │
              │                  │                          │
              │         ┌────────▼────────┐                 │
              │         │ Criteria met?    │                 │
              │         └───┬─────────┬───┘                 │
              │          No │         │ Yes                  │
              │   ┌────────▼──────┐  │                      │
              │   │ Fix skill     │  │                      │
              │   │ files based   │  │                      │
              │   │ on findings   │  │                      │
              │   └────────┬──────┘  │                      │
              │            │         │                      │
              └────────────┘    ┌────▼─────────────────┐    │
                                │ DONE                  │    │
                                │ Report final scores   │    │
                                │ + changelog           │    │
                                └───────────────────────┘
```

## Core Concepts

### The Executor Agent Is the Test

The key insight: instead of writing test scripts, you launch an agent that follows the skill procedure as a real user would. The agent's confusion IS the test signal. If it gets confused, the skill's instructions are unclear. If the output is wrong, the procedure has a gap.

### Confusion Score Is the Primary Metric

Each step in the target skill gets a clarity rating (1-10). The average across all steps is the primary optimization target. This is the equivalent of Karpathy's `val_bpb` — a single quantitative number that improves monotonically as the skill gets clearer.

### Worktree Isolation Keeps Experiments Clean

Each executor runs in a git worktree, so it can create files, run scripts, and make changes without affecting the working directory. Failed experiments are discarded automatically. This is analogous to Karpathy's branch-per-experiment pattern.

### 3-5 Iterations Is Typical

Skill procedures converge fast — unlike ML hyperparameter search (100+ experiments), prose clarity improvements plateau after 3-5 rounds. If you're still finding major issues after 5 iterations, the skill may need architectural changes, not instruction tweaks.

## Procedure

### Step 1: Choose the target skill and read it

Identify the skill to test. Read:
- The target skill's SKILL.md
- Any templates, scripts, or reference files it uses
- Any existing output examples (to understand what "good" looks like)

Note the skill's:
- **Steps**: How many steps does the procedure have?
- **Modes**: Does it have multiple modes (create/update/import)?
- **Tools/scripts**: Does it call external scripts? Which ones?
- **Outputs**: What files does it produce?

### Step 2: Create a test brief

A test brief is a simulated set of "source materials" that an executor agent uses as input. It replaces the real user.

**Requirements:**
- Must contain enough information to fill at least 80% of the skill's expected output
- Should include some intentional gaps (to test how the skill handles missing info)
- Should include at least one edge case (unusual value, ambiguous input, boundary condition)
- Must be self-contained — the executor should not need external resources

**Where to save:** `my-lib/runtime/.tmp/YYMMDD-autoresearch-{skill-name}-brief.md`

**Template:**

```markdown
# Test Brief: [Scenario Name]

> Simulated input for testing the [skill-name] skill.
> The executor agent treats this as what a real user would provide.

## Scenario
[Describe the test scenario — what is the user trying to accomplish?]

## Source Materials
[The actual content the executor will use as input — colors, text, data, files, etc.]

## Simulated User Behavior
[How the executor should respond when the skill asks for user input]
- When asked to confirm: [confirm / reject / partial]
- When asked to fill gaps: [provide values / skip / done]
- When asked to choose: [which option]

## Expected Output
[What the output should approximately contain — used by reviewer for validation]

## Edge Cases Included
[List the intentional edge cases and what correct handling looks like]
```

### Step 3: Define stop criteria

Every autoresearch loop needs explicit stop criteria. Without them, you'll iterate forever on diminishing returns.

**Default stop criteria** (use these unless the skill warrants different thresholds):

| Metric | Target | How Measured |
|--------|--------|-------------|
| Instruction clarity | >= 8.5/10 average | Executor confusion log |
| Script/tool success | 100% (all pass) | Exit codes from skill's scripts |
| Output completeness | >= 75% of expected fields | Parser/validator output or manual count |
| Mode coverage | All modes tested | At least one test per mode |
| No blocking issues | 0 remaining | Executor reports no confusion >= 3 steps below 7/10 |

**Custom metrics** for skills with measurable output:
- Coverage percentage (for skills that generate structured data)
- Validation pass rate (for skills that produce parseable output)
- Accessibility scores (for design/brand skills)
- Test pass rate (for skills that produce code)

### Step 4: Run the iteration loop

For each iteration:

#### 4a. Launch the executor agent

Use the Agent tool with:
- `isolation: "worktree"` — so changes don't affect the main workspace
- `mode: "auto"` — so the executor can create files and run scripts

**Executor prompt template** (copy and customize):

```
You are a test executor for iteration N of an autoresearch loop. Your job is to follow
the [SKILL NAME] skill procedure EXACTLY as written. Read all files fresh — do not
assume you know the contents.

## Your Task

1. Read the SKILL.md at [path to target SKILL.md]
2. Read any templates/reference files the skill uses
3. Read the test brief at [path to test brief]
4. Follow the procedure step by step in [MODE] mode
5. Complete ALL steps including validation/output generation

## Simulated User Behavior

[Copy from test brief]

## CRITICAL: Confusion Report

Rate each step on clarity (1-10). For EACH step, note:
- Was the instruction clear? (yes/no)
- Did you have to guess or interpret anything ambiguous?
- Were there contradictions between instructions and templates?
- Did any guidance added since the last iteration help?

## Output Format

### 1. Execution Result
- Skill completed end-to-end? (yes/no)
- Tool/script outputs (full text of validation, coverage, errors)
- Files created

### 2. Confusion Log
Step 1: Clarity X/10
- Issue: ...
(Continue for all steps)

### 3. Issues Found
- Template issues
- Script/tool issues
- Procedure gaps

### 4. Overall Assessment
- What worked well
- What is still confusing
- Suggestions for improvement
```

#### 4b. Score the results

After the executor returns, compute scores against stop criteria:

| Metric | Score | Pass? |
|--------|-------|-------|
| Instruction clarity | [avg of step scores] | [>= target?] |
| Script/tool success | [pass/fail] | [all pass?] |
| Output completeness | [%] | [>= target?] |
| Mode coverage | [modes tested / total modes] | [all covered?] |
| Blocking issues | [count of steps < 7/10] | [0?] |

#### 4c. Fix or stop

**If all criteria met:** Stop the loop. Report final scores and changelog.

**If criteria not met:** Analyze the executor's confusion log and fix the target skill files:
- Low-clarity steps → rewrite instructions for that step
- Script failures → fix the script
- Template confusion → clarify field descriptions, add notes
- Procedure gaps → add missing steps or guidance
- Contradictions → resolve in favor of the more specific instruction

**Bump the skill version** after each round of fixes (patch for minor clarifications, minor for new steps/guidance).

Then launch the next iteration.

### Step 5: Test additional modes

If the target skill has multiple modes (create/update, import/export, etc.), test each mode at least once. You can test secondary modes in the same iteration as the final create-mode pass.

For update mode specifically:
- Start from the output of a successful create-mode run
- Apply a targeted change (swap a value, add a field, remove a section)
- Verify the change propagated correctly through any downstream tools

### Step 6: Report final results

When the loop converges, present:

**Convergence summary:**
```
Autoresearch: [skill name]
Iterations: N
Clarity: [start] → [end]
Changes: [count of edits to SKILL.md, template, scripts]
Modes tested: [list]
Stop criteria: ALL MET
```

**Changelog** (what was fixed per iteration):
```
Iteration 1 (clarity X.X):
- [finding] → [fix applied]
- [finding] → [fix applied]

Iteration 2 (clarity X.X):
- [finding] → [fix applied]
```

**Version bumps:**
- SKILL.md: v[old] → v[new]
- Template: v[old] → v[new] (if applicable)

## Guidance

### When to run more iterations

- Any step below 7/10 → must fix and re-test
- Average below 8.5/10 → should fix and re-test
- Script/tool failures → must fix and re-test
- Mode not tested → must test

### When to stop

- Average >= 8.5/10 AND no step below 7/10 AND all scripts pass AND all modes tested
- OR: 5 iterations completed with diminishing returns (< 0.3 improvement per round)
- OR: Remaining issues are inherent to the skill's domain (e.g., a brand's accent color will always fail AA contrast — that's not the skill's fault)

### Common patterns from experience

1. **Token/field mapping tables** are the highest-ROI addition. If a skill expects structured input, provide a mapping guide from common source terminology to the skill's vocabulary.

2. **System-documentation columns** (like fallback/default values in tables) must be explicitly marked as read-only. Agents will try to edit them.

3. **Exit-code behavior** of called scripts should be documented in the procedure. A non-zero exit that's informational (not fatal) will confuse agents into thinking the step failed.

4. **Metadata/coverage fields** that depend on tool output need a write-back step at the end of the procedure. Don't say "filled automatically" when the agent has to do it.

5. **Sequential vs. parallel** tool execution should be called out when one tool's exit code can cancel the other.

## Notes

- This skill is orchestrator-level work — the agent running this skill is the researcher, not the executor. The executor is a subagent.
- Test briefs are intermediate files — save to `runtime/.tmp/`, not `deliverables/`.
- Worktree branches from executor agents are auto-cleaned if no changes were made. If changes persist, the worktree path is returned in the result.
- The skill produces no deliverable — its output is the improved target skill itself.
