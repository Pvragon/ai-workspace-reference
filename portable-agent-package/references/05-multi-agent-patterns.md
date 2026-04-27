---
template: portable-agent-reference
version: 0.1.0
summary: "Multi-agent coordination patterns: parallel reviewer council; chair synthesis (min not avg, anchored 1-5 levels); planner / generator / evaluator separation; deterministic pre-checks; bounded blast radius; grounding requirement; sub-agent isolation for context-heavy work."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 05 — Multi-Agent Patterns

When one agent isn't enough — for adversarial review, parallel work, or context-heavy isolation — these are the patterns that work. The harness pattern in [03-harness-design.md](03-harness-design.md) is one composition; this doc covers the others.

## Why Multi-Agent At All

A single agent has three structural weaknesses:

1. **Single perspective.** The same agent that produces an artifact is the worst critic of that artifact (it knows what was *intended*, not what was *delivered*).
2. **Context bloat.** A long Playwright session, a full codebase scan, a 200-row table parse — all bloat the parent's window.
3. **Sequential bottleneck.** Three reviews from one agent take 3x as long as three reviews from three parallel agents.

Multi-agent patterns address each weakness with a different decomposition.

## Pattern 1 — Parallel Review (Council)

Multiple agents independently review the same artifact, each with a different specialist persona and reference set. A chair agent synthesizes.

```
                         ┌──────────────┐
                         │   ARTIFACT   │
                         └──────┬───────┘
                                │
        ┌───────────────┬───────┼───────┬───────────────┐
        ▼               ▼       ▼       ▼               ▼
  ┌──────────┐   ┌──────────┐ ┌──────────┐  ┌──────────┐
  │  REV 1   │   │  REV 2   │ │  REV 3   │  │  REV 4   │
  │  UI/UX   │   │ Security │ │ DBA      │  │ Domain   │
  │  persona │   │ persona  │ │ persona  │  │ persona  │
  └────┬─────┘   └────┬─────┘ └────┬─────┘  └────┬─────┘
       │              │            │             │
       └──────────────┴─────┬──────┴─────────────┘
                            ▼
                     ┌──────────────┐
                     │    CHAIR     │
                     │  (synthesize)│
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │   VERDICT    │
                     │  + findings  │
                     └──────────────┘
```

### Critical Design Decisions

#### 1. Anchored 1-5 levels, not 0-100 scores

Each reviewer scores each dimension on a 1-5 scale, but the levels are **anchored to concrete descriptions**:

```yaml
dimension: completeness
description: Does the artifact cover all required sections?
levels:
  1: Multiple required sections missing or empty
  2: All sections present but most under-developed
  3: All sections present and meaningful (meets expectations)
  4: All sections complete; some go beyond minimum requirements
  5: Exceptional — adds context, examples, or analysis beyond what was asked. Should be rare.
```

Anchored levels solve **rater drift**: without anchors, "4 out of 5" means whatever the reviewer thinks. With anchors, every reviewer has the same definition of 4. Inter-rater reliability becomes possible.

> 0-100 scoring sounds more precise but is illusory. Reviewers can't reliably distinguish 73 from 78. They *can* reliably distinguish "meets expectations" from "exceeds expectations."

#### 2. Min, not average

When multiple reviewers score the same dimension, the **minimum** is the controlling score, not the average.

```
Reviewer A: 5
Reviewer B: 5
Reviewer C: 2     ← controlling score
Average:    4
```

The 2 is the blind spot. Reviewer C noticed something A and B didn't — averaging it away is how blind spots ship to production.

The chair may override a min only if they judge the finding driving it to be **fabricated**, **misapplied**, or a **calibration error**. Override is documented explicitly: `[CHAIR OVERRIDE: dimension=X, reason=...]`.

#### 3. Diverse references > diverse opinions

The reviewers' value comes from each reading **different reference documents**. UI/UX reviewer reads the design system. Security reviewer reads the threat model. DBA reads the schema. Without different inputs, you have one opinion echoed four times.

```yaml
reviewers:
  - role: UI/UX
    references:
      - context/design-system.md
      - context/figma-tokens.md
  - role: Security
    references:
      - context/threat-model.md
      - context/auth-rules.md
  - role: DBA
    references:
      - context/schema.md
      - context/query-conventions.md
```

#### 4. Grounding requirement

Every finding must cite content that **actually exists** in the artifact. Reviewers have been observed to hallucinate entire sections (e.g., quoting a "Routes" block from a sibling spec when the artifact doesn't have one).

The reviewer prompt must include:

> Before you write any finding that quotes or references specific content (a code block, a section subheading, a specific phrase, a table row), run a grep on the artifact path to verify the content exists. If grep returns no match, the finding is fabricated — delete it.

This guardrail alone eliminates a class of false findings.

#### 5. Pre-checks before LLM review

Before sending the artifact to the council, run **deterministic** checks. Cheap, fast, unambiguous:

- Required sections present? (string match)
- Required frontmatter fields filled? (YAML parse)
- IDs cross-referenced correctly? (lookup against canonical source)

Failing pre-checks blocks council review. Don't waste reviewer tokens on structural problems that a 20-line script can catch.

#### 6. Bounded blast radius

The review loop edits **only** the artifact under review. If a reviewer notices upstream drift (the canonical source-of-truth doc is stale, contradicting the artifact), this is an **upstream finding** — logged to an Open Issues queue, not silently fixed.

> A single-artifact review loop that edits N upstream docs becomes an unaudited rolling refactor. It can silently break other downstream artifacts that cite the old values.

The chair's job: classify each finding as artifact-local (fix in this iteration), upstream (log for human disposition), or calibration error (drop, log to skill-improvement queue).

### Chair Synthesis — Active Judgment

The chair is **not** a mechanical aggregator. It is a senior reviewer that:

1. Collects scores into a matrix (reviewer × dimension).
2. Applies the min-rule (with documented overrides).
3. Adds **its own findings** ("Chair Findings") for cross-cutting concerns the specialists couldn't catch.
4. Deduplicates / resolves conflicting reviewer findings.
5. Produces a **revision brief** for the next iteration: which dimensions are failing, what to change, what to leave alone.

The chair is also where calibration happens: if reviewer C consistently scores higher than reviewer A on the same dimension, the chair flags it for prompt tuning. Calibration drift is caught by humans-over-time, not by the loop.

## Pattern 2 — Planner / Generator / Evaluator (Adversarial)

Already covered in [03-harness-design.md](03-harness-design.md). The key idea repeated here: **the agent producing work and the agent verifying work must be different agents with different personas.** Self-review is GAN-style biased toward "passing."

This is the same insight as the council pattern (multiple perspectives), specialized to the case of "the perspective that *actively distrusts* the work."

## Pattern 3 — Sub-Agent Isolation For Context-Heavy Work

Some operations destroy context windows:

- A 30-minute Playwright session producing 500 console messages
- A full repo scan (10,000 files, even just paths)
- A multi-thousand-row CSV parse
- A long Pencil/Figma rendering session
- Compiling a 60K-LOC codebase

If the parent agent runs these directly, its context fills with intermediate output and recent work gets compacted away. The fix: **spawn a sub-agent**, hand it the task, get back **only a summary**.

```
Parent agent context (lean):
  "Spawn evaluator subagent to play a full game of Battleship and rate UI/UX 1-5."

Sub-agent context (heavy):
  [Playwright session, 500 console msgs, 50 screenshots, full DOM dumps...]
  Returns to parent: "UI/UX: 4/5. Findings: (1) Ship-placement drag UX confusing — see screenshot 5."

Parent agent receives: 4 lines. Original context preserved.
```

**When to spawn a sub-agent:**

| Spawn | Don't spawn |
|---|---|
| Playwright / browser automation > 5 min | One screenshot |
| Full codebase scan / large grep | Targeted file read |
| Independent parallel reviews | Sequential reads of one file |
| Long-running build / test / migration | Quick command |
| Anything that produces verbose tool output you don't need to read | A short, structured answer |

**Pass them what they need; nothing more.** The sub-agent's prompt should be self-contained: it doesn't have your conversation context. State the goal, the inputs, what to return. If you need a short response, say so.

## Pattern 4 — Pipeline (Linear Chain)

A specialized agent at each stage, output of stage N feeds stage N+1:

```
Researcher → Spec drafter → Implementor → Reviewer → Deployer
```

Each agent is small, specialized, and has a narrow context. The cost: state passing between stages must be explicit (files, not chat). The benefit: each stage is independently testable and replaceable.

The `/new-game` skill in this package's source repo is a worked example: research → spec + design → phased build → safety sweep → memory + exit. Five stages, each gating the next.

## When NOT To Use Multi-Agent

Multi-agent has overhead. Prefer single-agent when:

- The task is small (< 10 minutes).
- One perspective is enough.
- Sequential is fast enough.
- The user is watching synchronously and would prefer responsiveness over thoroughness.

A common failure mode is **over-spawning**: routing every small task through a council pattern. The council exists for high-stakes artifacts (specs, security reviews, architecture decisions). Most tasks aren't that.

Heuristic: if the artifact will be **read by humans and acted upon**, council it. If it's an intermediate or one-shot, single-agent it.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| One agent reviews its own work | Separate evaluator with skeptical persona |
| Reviewers all read the same docs | Each reviewer reads a different specialist set |
| Average scores | Min score (with documented chair overrides) |
| Free-form 0-100 scoring | Anchored 1-5 levels |
| Skip pre-checks "to save time" | Pre-checks first; cheap deterministic catch |
| Reviewer's findings include unverified quotes | Grounding requirement: grep before quoting |
| Review loop edits upstream docs silently | Upstream findings → OI log; revision touches artifact only |
| Chair averages reviewers without judgment | Chair adds own findings, filters fabrications, resolves conflicts |
| Playwright in parent agent context | Sub-agent absorbs the session; returns summary |
| Spawn a sub-agent for everything | Sub-agents are for context-heavy work, not every task |
| Sub-agent prompt assumes parent context | Self-contained prompt; state goal + inputs explicitly |

## Worked Example — Council Iteration

A typical iteration of a council loop on a spec:

```
ITERATION 1:
  Pre-checks: PASS (sections present, frontmatter valid)
  Council (parallel):
    UI/UX:      [completeness=3, clarity=4, alignment=3]  Findings: ...
    Security:   [completeness=2, clarity=3, alignment=4]  Findings: ...  ← 2 controls
    DBA:        [completeness=4, clarity=4, alignment=4]  Findings: ...
  Chair synthesis:
    Min scores: completeness=2, clarity=3, alignment=3
    Threshold: 4. Failing: completeness, clarity, alignment.
    Chair findings: [CHAIR-1: cross-cutting auth concern not in any reviewer's lens]
    Revision brief: {completeness: ..., clarity: ..., alignment: ..., do-not-change: ...}
  → Revise (artifact-local only) → ITERATION 2

ITERATION 2:
  Pre-checks: PASS
  Council:
    Min scores: completeness=4, clarity=4, alignment=4
  Chair: All dimensions ≥ threshold. CONVERGED.
  Promote artifact status: draft → needs-human-review.
```

Plateau detection: if iteration 3 produced the same min-scores as iteration 2, the loop stops and presents residuals to a human. Don't grind.

## Bootstrap Checklist

- [ ] Council skill scaffolded with: rubric file (anchored levels), personas file (one per reviewer with references), chair persona.
- [ ] Pre-check script exists for the artifact type.
- [ ] Reviewer prompt includes the grounding requirement.
- [ ] Chair prompt covers: min-rule, override discipline, own-findings expectation, upstream-vs-artifact-local partition.
- [ ] Loop has explicit exit conditions: converged / plateau / max-iter.
- [ ] First iteration exercised end-to-end on a real artifact.
- [ ] Sub-agent spawn pattern documented; tested for at least one context-heavy task.
