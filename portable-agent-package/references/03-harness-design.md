---
template: portable-agent-reference
version: 0.1.0
summary: "Ralph-loop / harness design for long-running autonomous work. Genealogy (Huntley → /loop → Anthropic 2-agent → 3-agent paper). Planner / generator / evaluator separation, feature_list.json schema, start-of-iteration verification, sprint contracts, confidence-scoring, exit conditions, plateau handling."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 03 — Harness Design (Ralph Loops)

For a single short task, the LLM in a single shot is fine. For multi-hour or multi-day autonomous work, you need a **harness**: a structured loop with role separation, machine-checkable progress, and skeptical verification. This doc covers the design.

## Genealogy — Where The Pattern Comes From

The pattern matters because each generation closed a specific failure mode.

| Generation | What it added | Failure it closed |
|---|---|---|
| **1. Ralph Wiggum loop** (Huntley, mid-2025) | `while :; do cat PROMPT.md \| llm ; done` — dumb bash loop, single agent, file-based state. Philosophy: "deterministically bad in an undeterministic world." | Single-shot prompts run out of context; no progress accumulation. |
| **2. /loop primitive** (Anthropic Claude Code, late 2025) | Productized Ralph: scheduled wakeup, interval-or-self-paced, runtime-supported. BYO state files. | Manual bash loops were brittle; resume after crash was painful. |
| **3. 2-agent harness** ([Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), Nov 2025) | **Initializer agent** generates `feature_list.json` (machine-checkable). **Coding agent** implements features one at a time, verifies in-browser, only then flips `passes: true`. | "Claimed done, actually broken" — markdown-checkbox completion is model-judged and unreliable. |
| **4. 3-agent harness** ([Harness Design for Long-Running Application Development](https://www.anthropic.com/engineering/harness-design-long-running-apps), Apr 2026) | Splits **Generator** and **Evaluator** into separate agents. Adds a **Planner** that expands briefs into feature specs. Evaluator runs Playwright against a running app. | Single agent verifying its own work has GAN-style bias toward passing. Separating roles introduces skepticism. |

**Open-source prompts** for generation 3 live at [`anthropics/claude-quickstarts/autonomous-coding/`](https://github.com/anthropics/claude-quickstarts) — the `initializer_prompt.md` and `coding_prompt.md` files are the closest thing to a published harness reference. Generation 4's evaluator prompt is not published; the architecture is described but the prompt is kept private (likely productized as Anthropic's Managed Agents).

## The Three Roles

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   PLANNER    │───▶│  GENERATOR   │───▶│  EVALUATOR   │
│ Expands brief│    │ Implements   │    │ Skeptical;   │
│ → 30-200 fe- │    │ ONE feature  │    │ runs the app │
│ ature JSON   │    │ at a time;   │    │ in a browser │
│ {id, desc,   │    │ commits;     │    │ or under     │
│  passes:    }│    │ runs tests.  │    │ tests; emits │
│              │    │              │    │ verdict file │
└──────────────┘    └──────────────┘    └──────┬───────┘
                            ▲                  │
                            │                  ▼
                            └─── feedback ─── verdict
                                                │
        loop until ALL features.passes == true ─┘
```

### Planner

Runs once at the start. Reads a brief (a paragraph from the user, or a spec). Produces:

- A **feature_list.json** with 30-200 features (granularity matters — too coarse is unverifiable, too fine is overhead).
- An **app_spec.txt** that the generator and evaluator both anchor on.

**Schema (minimal):**

```json
{
  "app_name": "vendor-portal",
  "features": [
    {
      "id": "F-001",
      "description": "User can log in with email + password and lands on /dashboard",
      "phase": "1a",
      "passes": false,
      "test_plan": "Visit /login. Submit valid creds. Assert URL becomes /dashboard. Assert email visible in nav."
    },
    {
      "id": "F-002",
      "description": "Invalid credentials show error toast and stay on /login",
      "phase": "1a",
      "passes": false,
      "test_plan": "Visit /login. Submit wrong password. Assert URL stays /login. Assert toast contains 'Invalid'."
    }
  ]
}
```

**Key design decisions:**

- `id` is stable and ordered (`F-001`, `F-002`). Features can be referenced across logs and commits.
- `description` is **acceptance-criterion-shaped**, not a task. "User can log in" is verifiable; "Implement login" is not.
- `phase` lets you batch: e.g. `1a` = pure logic, `1b` = solo UI, `2` = multiplayer shell, `3` = full server. Phases gate progression.
- `passes` is the boolean source of truth. Loop exit: all `passes: true`.
- `test_plan` is the evaluator's instructions for *this specific feature*. Pre-written, not improvised.

### Generator

The "main" implementation agent. Each iteration:

1. Pick the lowest-numbered `passes: false` feature.
2. **Run start-of-iteration verification** (see below) to confirm previously-passing features still pass.
3. Draft a **sprint contract** (acceptance criteria, evaluator's test plan).
4. Implement the feature in code.
5. Commit with a meaningful message.
6. Hand off to the evaluator.

**The generator never flips `passes: true` itself.** Only the evaluator does.

### Evaluator

A separate agent. Skeptical persona. Has access to:

- Browser automation (Playwright, Puppeteer, or equivalent).
- The running app (deployed URL or `localhost:N`).
- The feature's `test_plan`.
- The current feature_list.json.

Each iteration:

1. Read the feature under evaluation.
2. Drive the live app via the test plan.
3. Take screenshots / capture HTTP responses / check console errors.
4. Emit a verdict file: `verdicts/F-NNN-iter-M.md` with PASS/FAIL, evidence, and findings.
5. **Only flip `passes: true`** if PASS. On FAIL, write feedback for the next generator iteration.

**The evaluator's persona is non-negotiable: skeptical, evidence-driven, not deferential.** The evaluator's job is to catch what the generator missed. A polite evaluator that defers to the generator is worse than no evaluator.

> **Borrowed reference prompts** — Anthropic's `coding_prompt.md` Steps 5-7 (browser-verification discipline) and `code-reviewer.md` (confidence-scoring, "rate 0-100, only report ≥80") are the closest published evaluator-style protocols. Use them as starting points.

## The Five Improvements (Ranked By Lift)

If you build only two of these on top of a raw `/loop`, build the first two.

### 1. Skeptical evaluator with browser verification — HIGH LIFT

**Closes:** "claimed done, actually broken." `bun run build` passing ≠ feature working. Tests passing locally ≠ feature working in deployed app.

**Mechanism:** evaluator subagent + Playwright + verdict file. See above.

### 2. Enumerated pass/fail feature list (JSON, not markdown) — HIGH LIFT

**Closes:** model-judged completion. Markdown checkboxes are vibes; `feature_list.json` `passes: true/false` is a fact.

**Mechanism:** planner → JSON file → only-evaluator-flips-pass. Loop exit is `all(f.passes for f in features)`. Machine-checkable.

### 3. Start-of-iteration verification — MEDIUM LIFT

**Closes:** silent regression. A bug introduced in hour 3 surfaces in hour 40 when half the app is built on top of it.

**Mechanism:** every iteration starts by re-verifying 1-2 previously-passing features. If any fail, flip them to `passes: false` and fix before new work.

> **Borrowed:** `coding_prompt.md` Step 3 ("VERIFICATION TEST — MANDATORY BEFORE NEW WORK") is verbatim this.

### 4. Sprint contract per feature — MEDIUM LIFT

**Closes:** scope drift within a feature. "Implement login" is ambiguous; the generator may build something the evaluator can't test.

**Mechanism:** before implementation, generator drafts a short `sprint-contract.md` per feature listing acceptance criteria and the evaluator's test plan. Evaluator annotates/approves. Only then does the generator write code.

### 5. Confidence-scoring in evaluator reports — MARGINAL LIFT

**Closes:** noisy evaluator reports. Reduces false positives.

**Mechanism:** evaluator rates each finding 0-100 on confidence; only reports ≥80. Filters cosmetic findings.

## Loop Exit Conditions

A Ralph loop exits in **exactly one of three** states. No others.

| Exit | Meaning | Action |
|---|---|---|
| **CONVERGED** | All features `passes: true` AND start-of-iteration verification clean | Commit final state; report success |
| **PLATEAU** | At least one iteration where no feature flipped `false → true` AND no improvement in evaluator findings | Stop; present residual findings to human |
| **MAX_ITERATIONS** | Iteration count reached configured cap | Stop; present current state and unmet features |

**Critical:** the loop **never asks the user between iterations** while progress is being made. Only on the three exits above. Pausing after every iteration is a sign of an immature harness.

**Critical:** the loop **never silently expands scope**. If during iteration the generator notices a missing feature, it does *not* invent it. It logs the gap as an Open Issue and continues with the planned features. Scope expansion goes through the planner, not the generator.

## State Files

A harness should track state in version-controlled files, not in agent memory:

```
runtime/<task-slug>/
├── brief.md                    # original user request
├── feature_list.json           # generator + evaluator both read this
├── verdicts/
│   ├── F-001-iter-1.md
│   ├── F-001-iter-2.md
│   └── ...
├── progress.md                 # human-readable status
└── state.json                  # iteration counter, current feature, etc.
```

**Resume property.** A well-designed harness can be killed and resumed. The agent reads state.json + feature_list.json + the most recent verdict and continues from where it left off. No state should live exclusively in chat.

## When To Build A Harness — And When Not To

| Use harness | Don't bother |
|---|---|
| Multi-day autonomous build | Single-conversation task |
| Build will run unattended overnight | Synchronous, user-watching task |
| ≥10 distinct features | A handful of edits |
| Live verification surface (deployed app, browser, API) | Pure data transformation, where the script *is* the verification |
| You'll regret a silent regression more than you'll regret an over-cautious flag | You can re-run the whole thing in 5 minutes |

A harness is overhead. It pays back when the task is large and unattended. It's pure cost on a 30-minute task.

## Multi-Phase Harnesses

Real apps don't have flat feature lists. They have phases:

- `1a` — pure logic / engine / scoring
- `1b` — solo / single-user UI
- `2` — multi-user shell (rooms, presence, lobby)
- `3` — full authoritative gameplay (server RPCs, realtime sync)
- `4` — polish / nice-to-haves / toggles

Each phase gates the next. The loop processes one phase at a time:

```
For each phase in order:
  Loop:
    Pick lowest-numbered feature in this phase with passes: false
    Generator: implement
    Evaluator: verify
  Until: all features in this phase pass

Then proceed to next phase.
```

This prevents the loop from "tackling the easy bits across all phases" and ending up with a UI shell with no engine, or an engine with no UI, or both with no auth.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Markdown checkboxes as the source of truth | `feature_list.json` with booleans |
| Generator agent flips `passes: true` itself | Only evaluator flips it |
| Evaluator is the same agent as generator | Separate agent, skeptical persona, separate context |
| No start-of-iteration verification | Re-verify 1-2 passing features each iter |
| Loop pauses for user every iteration | Loop runs to converged / plateau / max-iter without pausing |
| One giant feature ("implement multiplayer") | 5-15 small features that compose into multiplayer |
| Verification = "build passes" | Verification = browser screenshots + asserted DOM state |
| State in chat / agent memory | State in version-controlled files; resumable |
| Silent scope expansion | New features go through planner; gaps logged as Open Issues |
| One agent reads its own evaluator verdicts and rationalizes | Separate agents per role; verdicts are concrete and quoted |

## Worked Example — Minimal Harness

A minimum viable harness has six files:

```
~/lib/skills/harness/
├── SKILL.md                # /harness init, /harness run, /harness status
├── references/
│   ├── features-schema.md  # JSON schema for feature_list.json
│   └── sprint-contract-template.md
└── agents/
    ├── planner.md          # expands brief → feature_list.json
    └── evaluator.md        # skeptical, browser-driven, confidence-≥80 filter
# generator = the main agent invoked under /harness run; no separate prompt file needed
```

**User flow:**

1. `/harness init "build a foo app"` — spawns planner; emits feature_list.json; user reviews before authorizing.
2. `/loop /harness run` — main agent picks next `passes: false` feature, drafts sprint contract, spawns evaluator for contract review, implements, commits, spawns evaluator for verification, writes verdict.
3. Loop exits at converged / plateau / max-iter.
4. `/harness status` — summary table.

This is enough to defeat the "claimed done, actually broken" failure mode. Subsequent improvements (per-feature confidence scoring, multi-phase gating, plateau detection) are layered on top.

## Calibration

The evaluator's persona is the hard-won part. Plan for iterative tuning against a corpus of "generator claimed done but actually wrong" cases. The first version of any evaluator will under- or over-catch. After 5-10 real runs, you can tune by:

- Adding cases the evaluator missed → tighten the persona.
- Filtering cases the evaluator over-flagged → raise the confidence threshold or refine wording.

Treat the evaluator prompt as the most important asset in the harness. Version it. Track its performance over time.

## Bootstrap Checklist

- [ ] Decide whether the task warrants a harness (use the table above; default = no).
- [ ] Brief written (one paragraph, machine-readable).
- [ ] Planner agent prompt prepared (start from `initializer_prompt.md` if available).
- [ ] feature_list.json schema agreed; first version generated and human-reviewed.
- [ ] Evaluator agent prompt prepared; skeptical persona; concrete verification mechanism.
- [ ] State directory established (brief.md, feature_list.json, verdicts/, progress.md, state.json).
- [ ] First feature exercised end-to-end (generator implements, evaluator verifies, JSON updated).
- [ ] Loop exit conditions documented and tested (force a plateau; verify the loop stops).
