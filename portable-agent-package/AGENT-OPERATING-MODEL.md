---
template: portable-agent-package
version: 0.1.0
summary: "Platform-independent operating model for building reliable, long-running AI agents. Synthesizes DOE architecture, layered memory, Ralph-loop harnesses, multi-agent coordination, progressive disclosure, and anti-context-rot discipline into principles and recipes any agent on any runtime can absorb and reconstruct."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
audience: "AI agent receiving this as bootstrap context, OR engineer reviewing an agent's intended operating model"
runtime_neutral: true
---

# Agent Operating Model — Portable Handoff Package

> **Read this file end-to-end.** It is the entry point for the package. The companion files in `references/` go deep on individual topics; come back here to see how they connect.
>
> **Audience.** You are an AI agent (or the engineer who instructs one). Your runtime may be Claude Code, OpenAI Codex, Cursor, Aider, an in-house harness, or something not yet built. Nothing here depends on a specific runtime. Where Claude Code primitives appear, they are illustrative — substitute the equivalent in your runtime.
>
> **If your runtime is NOT Claude Code, read [`references/00-primitive-translation.md`](references/00-primitive-translation.md) FIRST.** It maps the seven generic primitives this package depends on (skill, sub-agent, slash invocation, registry, file-based state, hook, scheduler) onto Claude Code, OpenAI Codex, Cursor, Aider, MCP-only runtimes, and an in-house harness fallback. Doing the substitution pass once up front means every later doc reads cleanly. Skipping it causes silent rule violations later when concrete examples leak through.
>
> **Goal.** After absorbing this package, you should be able to:
> 1. Explain *why* this operating model exists (the failure modes it defends against).
> 2. Reproduce its structure (directories, files, conventions) on a fresh machine.
> 3. Apply its principles to a new task without re-deriving them.
> 4. Recognize when *not* to apply a principle (stated in the anti-patterns section of each topic).

## Table of Contents

1. [The Core Problem](#1-the-core-problem)
2. [Five Load-Bearing Principles](#2-five-load-bearing-principles)
3. [Architectural Skeleton](#3-architectural-skeleton)
4. [Topic Index — Read These In Order](#4-topic-index--read-these-in-order)
5. [Bootstrap Recipe — Rebuild From Scratch](#5-bootstrap-recipe--rebuild-from-scratch)
6. [Anti-Patterns Catalog](#6-anti-patterns-catalog)
7. [Source Lineage](#7-source-lineage)
8. [How To Use This Package As An Agent](#8-how-to-use-this-package-as-an-agent)

---

## 1. The Core Problem

LLMs are probabilistic. Most useful work is deterministic. An agent that does *everything itself* compounds error: 90% step-accuracy across 5 steps is **59% end-to-end success**. Across 20 steps it is 12%.

Long-running agents fail in five characteristic ways:

| Failure | What it looks like | What this package defends against it with |
|---|---|---|
| **Compounding error** | Agent makes 5 small judgment calls; 3rd one drifts; downstream cascades. | DOE: push deterministic work into code; the LLM only routes. |
| **Context rot** | Useful state evaporates on session end / compaction; agent re-discovers the same thing repeatedly. | Layered memory + file-first output discipline. |
| **Claimed-done-actually-broken** | Agent reports success without verification; failure surfaces 40 hours later. | Skeptical evaluator subagent + machine-checkable feature lists. |
| **Hallucinated context** | Agent invents content that "should be" in a file (e.g. quotes a section that never existed). | Grounding requirement: every claim must be grep-verified before stated. |
| **Token waste / blast-radius** | Verbose intermediate results bloat context; one agent silently edits N upstream docs. | Progressive disclosure + bounded blast radius + sub-agent isolation. |

Every principle below is a structural defense against one or more of these failures. The principles are not stylistic preferences; each one *prevents a specific failure mode that has actually occurred* in the projects this package was distilled from.

---

## 2. Five Load-Bearing Principles

If you only remember five things, remember these. Everything else in the package operationalizes them.

### 2.1 Push deterministic work into code, never into the LLM

The agent's job is to **route** — read a directive, choose tools in the right order, handle errors, ask for clarification. The agent's job is **not** to scrape, parse, transform, or compute. Those are deterministic; they go in scripts.

> **Why:** see "compounding error" above. A 100-line Python function is 100% reproducible. A 100-line LLM prompt is not.

> **How:** Directive → Orchestration → Execution (DOE) — see [§3.1](#31-three-layer-doe-architecture) and [`references/01-directives-orchestration-execution.md`](references/01-directives-orchestration-execution.md).

### 2.2 Memory is layered, not flat

Agent context is divided across four lifetimes — long-term (versioned), mid-term (cross-session), near-term (within-initiative), and session (volatile). Each tier has different storage, retrieval, and maintenance. Confusing them is how agents lose their state.

> **Why:** session memory dies on compaction; mid-term memory must survive vendor changes; long-term context must be version-controlled and auditable.

> **How:** four-tier hierarchy + index-with-pointers — see [§3.2](#32-layered-memory) and [`references/02-layered-memory.md`](references/02-layered-memory.md).

### 2.3 Surface area is on-demand, not always-on

You do not load every reference doc into context "just in case." Each agent-consumable file has a one-line `summary` in YAML frontmatter. Index files aggregate summaries into a discovery table. Agents scan the index, decide relevance, and load only what they need.

> **Why:** context windows are finite and expensive; large always-on contexts displace recent work; relevance ranking via humans-pre-selected tags beats LLM-search-every-time.

> **How:** progressive disclosure — see [`references/04-progressive-disclosure.md`](references/04-progressive-disclosure.md).

### 2.4 Long-running work uses a Ralph loop, not a single shot

For multi-hour or multi-day autonomous work, the runtime is a structured loop: **planner** generates a machine-checkable feature list; **generator** implements one feature at a time; **evaluator** independently verifies each feature with concrete signals (browser screenshots, tests, scripted checks); the loop exits when all features pass.

> **Why:** "claimed done, actually broken" is the dominant failure of unsupervised agents. Skeptical, browser-driven verification by a separate agent is the only reliable signal. Markdown checkboxes are model-judged and unreliable.

> **How:** Ralph loop architecture + 3-agent pattern from Anthropic's harness papers — see [`references/03-harness-design.md`](references/03-harness-design.md).

### 2.5 Treat errors as instruction-set updates (self-annealing)

When something breaks: fix it, then update the directive/skill so the next agent does not repeat the failure. Errors are the system's primary learning channel. A pristine directive that has never been corrected is a directive that has never been used.

> **Why:** prevents the same regression from recurring; turns single-instance failures into structural defenses.

> **How:** every directive carries a version + last_updated; every fix bumps it. See [§6.6](#66-self-annealing-failures).

---

## 3. Architectural Skeleton

The skeleton is small. Five concepts; everything else is detail.

### 3.1 Three-Layer DOE Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: DIRECTIVE — natural-language SOPs              │
│   Markdown. "What to do, why, success criteria."        │
│   Lives in directives/.                                  │
├─────────────────────────────────────────────────────────┤
│ Layer 2: ORCHESTRATION — the agent's reasoning loop     │
│   You (the LLM). Read directive, route to executions,   │
│   handle errors, ask for clarification, update directive│
│   on learning. NEVER perform deterministic work itself. │
├─────────────────────────────────────────────────────────┤
│ Layer 3: EXECUTION — deterministic scripts              │
│   Python (or Node/Go/Rust). Idempotent, testable, fast. │
│   Dual-purpose: CLI + importable run() function.        │
│   Lives in executions/.                                  │
└─────────────────────────────────────────────────────────┘
```

**The cardinal rule:** if a step is deterministic and repeatable, it goes in Layer 3. Not in the prompt. Not in the agent's head. In code. See [`references/01-directives-orchestration-execution.md`](references/01-directives-orchestration-execution.md).

### 3.2 Layered Memory

| Tier | Lifetime | Examples | Storage |
|---|---|---|---|
| **Long-term** | Persistent, versioned | Architecture refs, identity, governance docs | `context/indexed/`, git-backed, registry-driven, on-demand |
| **Mid-term** | Cross-session, curated | Topic memories, lessons learned, feedback rules | `memory/*.md` indexed by `MEMORY.md`, vendor-independent repo, symlinked into runtime |
| **Near-term** | Within-initiative | Working files, plans, screenshots, intermediate data | `runtime/.tmp/` — flat, prefixed, archived not deleted |
| **Session** | Single conversation | Loaded prompts, recent tool output | Volatile; subject to compaction |

**The cardinal rule:** anything you want to survive session end gets written to disk *first*, in the right tier. Chat output is ephemeral. Structured output longer than a few paragraphs is a file. See [`references/02-layered-memory.md`](references/02-layered-memory.md).

### 3.3 The Memory Index Pattern

A single `MEMORY.md` is auto-loaded at session start. It is **an index, not a memory**. Each entry is one line under ~150 chars:

```markdown
| Topic File | Summary |
|------------|---------|
| `feedback_naming.md` | Always self-document file/script names — clarity over brevity |
| `project_clientX.md` | Client X — V2 build, 2026-Q3 target, key contact Sarah |
```

The agent scans the index, decides which topic files are relevant to the current task, loads only those. This is the same progressive-disclosure pattern as long-term context — applied to mid-term memory. See [`references/02-layered-memory.md#index-pattern`](references/02-layered-memory.md).

### 3.4 The Harness (Ralph Loop)

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   PLANNER    │───▶│  GENERATOR   │───▶│  EVALUATOR   │
│ feature_list │    │ implements   │    │ skeptical;   │
│ .json        │    │ one feature  │    │ runs         │
│ {id, desc,   │    │ at a time    │    │ Playwright;  │
│  passes}     │    │ commits      │    │ writes       │
└──────────────┘    └──────────────┘    │ verdict      │
                            ▲            └──────┬───────┘
                            │                   │
                            └─── feedback ──────┘
                                                │
        loop until all features.passes == true ─┘
```

Three rules that matter more than the architecture diagram:

1. **The feature list is a JSON file with booleans, not a markdown checklist.** Completion is machine-checkable.
2. **The evaluator is a separate agent with a skeptical persona.** Same model can claim "done" and audit "done"; different roles do not.
3. **Verification is concrete.** Screenshots, HTTP responses, scripted assertions. Not "I think the build passed."

See [`references/03-harness-design.md`](references/03-harness-design.md).

### 3.5 Skills, Personas, and Sub-Agents

- A **skill** is a reusable capability bundle: a SKILL.md (procedure) + supporting files (templates, schemas, sub-agent prompts). Skills are *invoked*, not inlined.
- A **persona** is a stable identity (style, risk tolerance, domain expertise). Multiple skills may load the same persona.
- A **sub-agent** is a one-shot, isolated agent spawned for a context-heavy task (long Playwright session, large codebase scan, parallel review). Sub-agents protect the parent's context window — they return only a summary.

The Ralph loop above is a 3-skill / 3-sub-agent composition. Council-style review is a sibling pattern. See [`references/05-multi-agent-patterns.md`](references/05-multi-agent-patterns.md) and [`references/06-skills-system.md`](references/06-skills-system.md).

> **Runtime translation.** "Skill" and "sub-agent" are generic primitives. If your runtime has no native sub-agent tool, the fallback is a fresh CLI/API process whose stdout you capture and only the summary returns. If your runtime has no skill mechanism, a skill is just a Markdown file the orchestrator reads and follows step-by-step. The full mapping (including hooks, registries, slash invocation, scheduler) is in [`references/00-primitive-translation.md`](references/00-primitive-translation.md). Read that doc once before going further if you are not on Claude Code.

---

## 4. Topic Index — Read These In Order

Every topic doc has a `summary` frontmatter line; you can scan the table here without opening any of them.

| # | File | Summary |
|---|------|---------|
| 0 | [`references/00-primitive-translation.md`](references/00-primitive-translation.md) | **Read first if your runtime is not Claude Code.** Maps the seven generic primitives (skill, sub-agent, slash invocation, registry, file-based state, hook, scheduler) onto Claude Code, OpenAI Codex, Cursor, Aider, MCP-only, and in-house-harness fallbacks so every downstream doc translates cleanly. |
| 1 | [`references/01-directives-orchestration-execution.md`](references/01-directives-orchestration-execution.md) | Three-layer DOE pattern: when to write a directive vs. a skill vs. a script; the dual-purpose execution standard (CLI + `run()`); chaining; return contracts. |
| 2 | [`references/02-layered-memory.md`](references/02-layered-memory.md) | Four-tier memory; MEMORY.md index template; topic file frontmatter; what NOT to save; memory vs. plans vs. tasks vs. session state. |
| 3 | [`references/03-harness-design.md`](references/03-harness-design.md) | Ralph loop genealogy (Huntley → /loop → 2-agent paper → 3-agent paper); planner/generator/evaluator; feature_list.json schema; start-of-iteration verification; sprint contracts; confidence-scoring. |
| 4 | [`references/04-progressive-disclosure.md`](references/04-progressive-disclosure.md) | The summary frontmatter convention; index aggregation; reference-vs-instruction distinction; registry as bridge. |
| 5 | [`references/05-multi-agent-patterns.md`](references/05-multi-agent-patterns.md) | Council with parallel reviewers; chair synthesis (min not avg, anchored 1-5 levels); planner/generator/evaluator; pre-checks before LLM review; bounded blast radius; grounding requirement. |
| 6 | [`references/06-skills-system.md`](references/06-skills-system.md) | What a skill is; SKILL.md frontmatter; when to extract a skill; skill registry; internal-vs-external precedence; skill vs. directive vs. persona. |
| 7 | [`references/07-anti-context-rot.md`](references/07-anti-context-rot.md) | Artifact mirroring; structured-output-to-file-first; sub-agent isolation; YYMMDD prefix convention; archive-not-delete; hot-vs-cold context discipline. |
| 8 | [`references/08-recipes-and-templates.md`](references/08-recipes-and-templates.md) | Drop-in templates: minimal AGENTS.md; minimal MEMORY.md; minimal SKILL.md; minimal Ralph-loop pseudocode; minimal directive; minimal feature_list.json schema; minimal council rubric. |
| 9 | [`references/09-agent-behavioral-rules.md`](references/09-agent-behavioral-rules.md) | Four behavioral rules for every task — Think Before Acting, Simplicity First, Surgical Changes, Goal-Driven Execution. Adapted from Andrej Karpathy's Jan 2026 observations (via Forrest Chang) and generalized from coding to all agent work. |

---

## 5. Bootstrap Recipe — Rebuild From Scratch

You are an agent on a fresh machine. You have read this package. You want to instantiate the operating model. Here is the minimum sequence.

### 5.1 Directory layout

```
~/ai-workspace/                    # or any root
├── agents/
│   └── <your-name>/               # vendor-independent, git-backed
│       ├── identity.md            # name, pronouns, defaults (1-page)
│       ├── memory/
│       │   ├── MEMORY.md          # index, auto-loaded at session start
│       │   └── *.md               # topic files
│       └── adapters/
│           └── <vendor>/link.sh   # symlink memory into runtime location
├── lib/                           # your "standard library"
│   ├── AGENTS.md                  # operating instructions (this file's distillation)
│   ├── directives/                # Layer 1 — natural-language SOPs
│   ├── executions/                # Layer 3 — deterministic scripts (run() pattern)
│   ├── skills/                    # Reusable capability bundles
│   ├── personas/                  # Stable identities
│   ├── context/
│   │   ├── global/                # always-on
│   │   └── indexed/               # on-demand (registry-resolved)
│   ├── registry/                  # YAML manifests; SoT for discovery
│   │   ├── directives.yaml
│   │   ├── skills.yaml
│   │   ├── executions.yaml
│   │   └── context.yaml
│   └── runtime/
│       ├── .tmp/                  # near-term scratch
│       └── deliverables/          # final artifacts
└── projects/
    └── <project-name>/            # active work; consumes from lib/
```

The names are not sacred. The **separation** is. See [`references/08-recipes-and-templates.md`](references/08-recipes-and-templates.md) for templates of every file marked above.

### 5.2 Boot sequence (an agent's first session)

1. **Load identity** — `agents/<your-name>/identity.md`. Confirm name, pronouns, defaults.
2. **Load AGENTS.md** — operating instructions. This is the contract for *what you do, what you never do, and how you escalate*.
3. **Load MEMORY.md** — the index. Note which topics exist; do *not* open them yet.
4. **Wait for the user's first message.**
5. **On each user request:**
   a. Decide which memory topics are relevant; load only those.
   b. Decide whether a directive or skill exists for this work (consult registry). If yes, READ it before executing — your memory of its contents may be stale.
   c. Decide whether deterministic work belongs in a sub-script. If yes, write/use one.
   d. Execute. On error, fix the underlying issue and update the directive.
6. **At session end:** debrief. Update memory topics; commit changes to the agent repo.

This is the same loop, every session. Predictability is the point.

### 5.3 Minimum viable agent (one-week build)

If you have one week, build in this order. Each step compounds.

| Day | Build | Defends against |
|---|---|---|
| 1 | Directory skeleton + identity.md + minimal AGENTS.md | Cold-start amnesia |
| 2 | MEMORY.md index pattern + 2-3 topic files | Cross-session forgetting |
| 3 | First directive + first execution script (dual-purpose run() + CLI) | Compounding LLM error |
| 4 | First skill (SKILL.md + reference docs) + registry | Re-deriving procedures |
| 5 | Sub-agent spawn pattern + first parallel-reviewer skill | Single-perspective blind spots |
| 6 | First Ralph loop with feature_list.json + skeptical evaluator | "Claimed done, actually broken" |
| 7 | Session debrief skill (writes back to memory + commits) | All of the above, ongoing |

After day 7, you have a self-improving agent. Each subsequent task either uses an existing capability or creates a new one.

---

## 6. Anti-Patterns Catalog

Cross-cutting failures every topic doc warns against. Listed once here so you can pattern-match them.

### 6.1 Doing deterministic work in the LLM
- ❌ "Read this CSV and tell me the row count."
- ✅ Write a 5-line script; LLM calls it; LLM reads "1,247."

### 6.2 Always-on context bloat
- ❌ Loading every reference doc into the system prompt "in case it's needed."
- ✅ Index → summary scan → on-demand load.

### 6.3 Markdown checkboxes as completion signal
- ❌ `- [x] Implemented multiplayer` (model-judged; unverifiable).
- ✅ `feature_list.json` with `"passes": true` set only after evaluator screenshots.

### 6.4 Single-agent self-review
- ❌ Generator agent decides whether its own work passed.
- ✅ Separate evaluator agent with a skeptical persona and concrete signals.

### 6.5 Ephemeral structured output
- ❌ "Here is your 200-line implementation plan: …" (in chat).
- ✅ Write to `runtime/.tmp/YYMMDD-plan.md`; reference in chat with one-line summary.

### 6.6 Self-annealing failures
- ❌ Fix the bug, move on.
- ✅ Fix the bug, **update the directive** so the next agent does not encounter it.

### 6.7 Silent upstream edits
- ❌ Reviewing artifact A; notice doc B is stale; quietly edit B.
- ✅ Append to an Open Issues log with quoted canonical content; let a human disposition it.

### 6.8 Average-of-reviewer-scores
- ❌ "Three reviewers, scores 5, 5, 2 → average 4 → ship."
- ✅ Min score wins. The 2 is your blind spot.

### 6.9 Hallucinated grounding
- ❌ "The spec's `<Route>` block uses lazy loading…" (the spec has no `<Route>` block; you imagined it).
- ✅ Every claim that quotes content must be grep-verified against the file before it is written.

### 6.10 Vendor-locked identity
- ❌ Memory lives in `~/.claude/`. Switching tools = losing your agent.
- ✅ Memory lives in a git repo at `agents/<name>/`. Vendor tooling symlinks in.

---

## 7. Source Lineage

The principles in this package are not original. They are distilled from public research and battle-tested practice. Citations included so a reader can verify and go deeper.

| Concept | Source |
|---|---|
| DOE pattern | Internal Pvragon AI Workspace (`team-lib/context/indexed/workspace-reference.md`); echoes Robert C. Martin's separation-of-concerns and Joel Spolsky's "Joel Test." |
| Ralph loop | Geoffrey Huntley, [Ralph Wiggum As A Software Engineer](https://ghuntley.com/ralph/) — `while :; do cat PROMPT.md \| claude-code ; done`. |
| 2-agent harness (initializer + coding agent, feature_list.json) | Anthropic, [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), Nov 2025; open-source prompts at [`anthropics/claude-quickstarts/autonomous-coding/`](https://github.com/anthropics/claude-quickstarts). |
| 3-agent harness (planner + generator + evaluator, GAN-style skepticism) | Anthropic, [Harness Design for Long-Running Application Development](https://www.anthropic.com/engineering/harness-design-long-running-apps), Apr 2026. |
| Confidence-scoring (rate 0-100, only report ≥80) | Anthropic Claude Code [`code-reviewer`](https://github.com/anthropics/claude-code) plugin. |
| Code-as-orchestration (dual-purpose run() pattern) | Anthropic, [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp); [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use). |
| Progressive disclosure (summary frontmatter, index aggregation) | Internal — `team-lib/context/indexed/progressive-disclosure-convention.md`. |
| Council-converge (multi-reviewer + chair, anchored 1-5 rubric, min-score) | Internal — `my-lib/skills/echo1-council-converge/`; rubric design echoes IRR (inter-rater reliability) literature. |
| Bounded blast radius / upstream-drift logging | Internal — same skill, lessons from spec-review pipeline. |
| Vendor-independent agent identity | Internal — `agents/<name>/` pattern; conceptual sibling of [Anthropic's Memory Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/memory-tool). |
| Memory tier hierarchy | Internal; conceptual ancestor in OS memory hierarchy (registers → cache → RAM → disk). |
| Four behavioral rules (Think Before Acting, Simplicity First, Surgical Changes, Goal-Driven Execution) | Andrej Karpathy's Jan 2026 observations on agent coding pitfalls; distilled into a single CLAUDE.md by Forrest Chang at [github.com/forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills). Generalized from "coding" to "acting" in [`references/09-agent-behavioral-rules.md`](references/09-agent-behavioral-rules.md). |
| Skeptical evaluator with browser verification | Anthropic harness papers + Pvragon `skills/test-multiplayer/` (Playwright-driven adversarial review). |

This package adds the *synthesis*: the lineage above are individual tools; presenting them as one operating model with explicit interfaces is the contribution.

---

## 8. How To Use This Package As An Agent

You may be reading this package because:

(a) **You are bootstrapping on a new platform.** Read this file, then `references/` 1-8 in order, then build in the order described in [§5.3](#53-minimum-viable-agent-one-week-build). Map each principle onto your runtime's primitives. Where this package says "skill," your runtime may say "command," "tool," "function," "macro." The label does not matter; the separation does.

(b) **You are reviewing an agent's intended operating model.** Use the [REVIEWER-RUBRIC.md](REVIEWER-RUBRIC.md) in this directory. Score each of the ten dimensions 1-5 against anchored level descriptions. A package that scores 5 across all ten can be handed to any LLM-driven agent on any platform without further adaptation.

(c) **You are operating an existing agent and consulting this as a reference.** Use [§4](#4-topic-index--read-these-in-order) — open only the topic doc relevant to your current question. Each topic doc is independently readable.

> **One commitment from this package to you, the reader:** every claim here is either (i) cited to a public source, (ii) grounded in a concrete file in the repo this package was distilled from, or (iii) explicitly marked as opinion. There are no orphan principles.

---

*End of entry document. Open the `references/` files when you need depth on a specific topic.*
