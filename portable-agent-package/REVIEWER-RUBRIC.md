---
template: reviewer-rubric
version: 1.0.0
summary: "Objective 1-5 anchored rubric for evaluating the portable agent package. Ten dimensions, each with concrete level descriptions for 1, 3, and 5. A package scoring 5 across all ten can be handed to any LLM agent on any platform without further adaptation."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# Reviewer Rubric — Portable Agent Package

This rubric scores `AGENT-OPERATING-MODEL.md` and the eight `references/*.md` files as a single artifact. The expert reviewer evaluates each of the **ten** dimensions below on a 1-5 anchored scale and returns:

- a score per dimension,
- evidence (specific section / file / line reference) for the score,
- a concrete fix list for any score below 5,
- 1-3 things the package does well (anti-sycophancy guardrail).

## Reviewer Persona (loaded by the reviewer agent)

> You are an **AI Context Engineering and Harness Engineering specialist**. You have built and shipped multi-hour autonomous coding harnesses, multi-agent council review systems, and layered memory architectures. You have read Anthropic's published harness papers ([Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) and [Harness Design for Long-Running Application Development](https://www.anthropic.com/engineering/harness-design-long-running-apps)) and the Geoffrey Huntley Ralph-loop article. You know what it takes to make a documented operating model **actually rebuildable** by a fresh agent on a different platform. You are skeptical of decoration and warm prose. You credit only what is concretely sufficient for an agent to act on. You give a 5 only when there is nothing meaningful left to fix. A 3 means "meets expectations." A 5 should be rare and earned.

## Scoring Procedure

For each dimension:

1. Read the relevant primary file(s).
2. Compare against the level descriptions below.
3. Pick the highest level for which **all anchor conditions** are met.
4. Cite the section / file evidence for the score.
5. If <5, list specific changes that would raise the score.

A score is the **highest level for which all anchor bullets are satisfied**. If 4 of 5 anchors are met, the score is 3 (the next level down where all are met) — not 4.

## The Ten Dimensions

---

### D1. Platform-Independence

Can an agent on a runtime *other than* the source-of-truth runtime (e.g., not Claude Code) absorb this package and rebuild the operating model?

| Level | Anchors |
|---|---|
| **1** | Package assumes a specific vendor's primitives throughout (slash commands, specific tool names). A non-Claude-Code agent could not act on the instructions. |
| **3** | Package describes patterns generically with vendor names appearing only as illustrative examples; a non-Claude-Code agent could understand the intent but would need significant translation work to implement. |
| **5** | Every concept is described in terms of generic primitives (sub-agents, file-based state, registries, frontmatter); vendor-specific names appear only in clearly-labeled examples; the package explicitly states "your runtime may say X; substitute Y"; a fresh agent on a different platform can map every principle onto its own primitives without ambiguity. |

---

### D2. DOE Architecture Coverage

Is the three-layer Directive-Orchestration-Execution pattern documented well enough for a fresh agent to apply it correctly?

| Level | Anchors |
|---|---|
| **1** | DOE is mentioned as a name only, with no definition of the three layers, what belongs in each, or how they interact. |
| **3** | DOE has a definition; the three layers are named and have one-paragraph descriptions; an example flow exists; but boundary cases (when does X belong in Layer 2 vs Layer 3) are not addressed. |
| **5** | DOE is defined with concrete examples per layer; the *why* (compounding-error math) is included; the dual-purpose `run()` pattern is fully specified (frontmatter, return contract, no-print/no-exit rules); chaining is shown with a real example; a decision tree distinguishes script vs skill vs directive vs nothing; anti-patterns are listed; "how to recognize you're drifting from DOE" is documented. |

---

### D3. Deterministic Execution Discipline

Does the package provide enough specification for an agent to write scripts that other scripts and agents can chain into context-efficient workflows?

| Level | Anchors |
|---|---|
| **1** | "Write scripts" is mentioned but nothing about CLI/import duality, return contracts, or chaining. |
| **3** | The dual-purpose pattern is named; a basic template exists; the return-dict convention is mentioned; but no end-to-end chained example exists. |
| **5** | The dual-purpose pattern has a complete template (shebang, frontmatter, run(), main(), return-dict); explicit non-negotiable rules listed (no print/exit in run, status key always present); an end-to-end *chained* example shows how an agent makes one tool call instead of three; the context-efficiency math (token displacement) is explained; anti-patterns are listed. |

---

### D4. Layered Memory Architecture

Does the package give an agent a complete, reproducible memory system?

| Level | Anchors |
|---|---|
| **1** | Memory is treated as a single tier; no distinction between session and cross-session storage. |
| **3** | Tiers are named; frontmatter for memory files exists; but the index pattern, what-not-to-save guidance, and stale-memory discipline are missing or incomplete. |
| **5** | Four tiers are defined with lifetime + storage + maintenance per tier; the `MEMORY.md`-as-index pattern is fully specified (one-line entries, ~150-char limit, semantic prefixes); topic-file frontmatter is templated; memory types (user / feedback / project / reference) have explicit save/no-save criteria; the "why + how to apply" body structure is required for feedback/project; what-NOT-to-save is enumerated; vendor-independent storage (agents/<name>/ + symlinks) is specified; stale-memory verification rules are stated; session-debrief ritual is defined. |

---

### D5. Harness / Ralph-Loop Design

Could a fresh agent build a working long-running autonomous build harness from this package?

| Level | Anchors |
|---|---|
| **1** | "Use a Ralph loop" is mentioned but nothing concrete: no role separation, no exit conditions, no schema for state. |
| **3** | Three roles (planner/generator/evaluator) are named and described; feature_list.json is mentioned; but exit conditions, plateau detection, multi-phase gating, and the "only-evaluator-flips-pass" rule are missing or vague. |
| **5** | All three roles described with separation rationale; complete feature_list.json schema with example; "only evaluator flips passes:true" rule explicit; three exit states (converged/plateau/max-iters) defined; multi-phase pattern documented; the five harness improvements are ranked by lift; start-of-iteration verification is specified; sprint-contract pattern is documented; references to the Anthropic 2-agent and 3-agent harness papers (with URLs) are included; minimal Ralph-loop pseudocode template provided. |

---

### D6. Multi-Agent Coordination

Does the package teach the council / parallel-reviewer / chair-synthesis pattern with enough specificity to reproduce it?

| Level | Anchors |
|---|---|
| **1** | "Use multiple agents" is mentioned but no specifics about review structure, scoring, or synthesis. |
| **3** | The council pattern is named; reviewers + chair are described; anchored 1-5 scoring is mentioned; but min-not-average, grounding requirement, bounded blast radius, and pre-checks are missing or partial. |
| **5** | Council pattern fully described with diverse-references requirement; anchored 1-5 levels (with example dimension) shown; min-not-average rule explicit with override discipline; grounding requirement (grep before quoting) is stated as non-negotiable; pre-checks before LLM review are required; bounded blast radius (artifact-local edits only; upstream → OI log) is specified; chair's active-judgment role beyond mechanical aggregation is described; sub-agent isolation pattern for context-heavy work is documented; when-not-to-use guidance is included. |

---

### D7. Progressive Disclosure

Is the technique that lets the knowledge base grow without bloating context fully specified?

| Level | Anchors |
|---|---|
| **1** | "Use indexes" is mentioned but no convention for summary frontmatter, no aggregation pattern, no hot-vs-cold model. |
| **3** | The summary frontmatter convention is named; index aggregation is described; but reference-vs-instruction distinction, registry bridge, and length bands are missing or thin. |
| **5** | Summary frontmatter spec includes good and bad examples; aggregation pattern shows index → summary scan → on-demand load flow; reference-vs-instruction distinction is explicit (instructions read in full); registry as machine-readable bridge with precedence is defined; hot-vs-cold model with concrete cold-start file list; length bands per file type provided; promotion-to-always-on criteria stated; anti-patterns listed. |

---

### D8. Anti-Context-Rot Discipline

Does the package give an agent a complete defensive playbook against the failure modes of long sessions and unsupervised work?

| Level | Anchors |
|---|---|
| **1** | A few defenses are mentioned but the underlying failure modes aren't named, and the playbook is incomplete. |
| **3** | File-first output, artifact mirroring, and sub-agent isolation are mentioned; but YYMMDD prefix, archive-not-delete, file-scope guards, grounding-before-quoting, "never trust ephemeral state," and concrete-verification-beats-vibes are missing or partial. |
| **5** | A numbered set of ≥10 defenses is enumerated; each defense has a rule + reasoning; file-first output with the trigger conditions; artifact mirroring with the create-mirror-immediately discipline; sub-agent isolation with the when-to-spawn table; archive-not-delete with the `_archive/` convention; YYMMDD prefix rationale; file-scope guards with `git diff` enforcement; grounding requirement; "never trust ephemeral state" with explicit list; hot-vs-cold context discipline; plain-files-no-magic principle; session-debrief as the highest-ROI defense; bounded blast radius repeated; concrete-verification-beats-vibes with do/don't list. |

---

### D9. Reproducibility / Bootstrap Recipe

Could an agent on a fresh machine, starting from nothing, follow the package and produce a working operating system?

| Level | Anchors |
|---|---|
| **1** | The package describes principles but doesn't provide a starting directory layout or sequenced build order. |
| **3** | A directory skeleton is provided; principles are described; but no sequenced build order ("day 1 build X, day 2 build Y…") and no copy-pasteable starter files. |
| **5** | A complete directory layout is shown; a 7-day "minimum viable agent" build order is provided in dependency order; a recipes/templates document gives ≥10 copy-pasteable starter files (AGENTS.md, MEMORY.md, topic memory, SKILL.md, directive, dual-purpose script, feature_list.json, council rubric, council personas, Ralph-loop pseudocode, identity, registry stub) with placeholders explicitly marked; placeholders are unambiguous; the "boot sequence (an agent's first session)" is enumerated. |

---

### D10. Anti-Pattern Catalog Quality

Are the package's "what not to do" lists specific, motivated, and located where an agent would look for them?

| Level | Anchors |
|---|---|
| **1** | Anti-patterns are missing or buried; bad practices are not explicitly named. |
| **3** | Each topic doc has an anti-patterns section; the entries are named; but they are generic and don't pair with corrections, or they don't explain *why* the anti-pattern fails. |
| **5** | Every topic doc has an anti-patterns table with two columns (❌ pattern | ✅ correct); the top-level entry doc has a cross-cutting catalog of ≥10 anti-patterns; each entry is concrete (specific behavior, specific correction); the package surfaces the *why* (the failure mode each anti-pattern produces); a "how to recognize you're drifting" subsection appears in at least one place; an "anti-sycophancy guardrail" / "what's working" surfaces appropriate praise to balance corrections; failure modes are tied to the five from §1 of the entry doc. |

---

## Aggregation

| Output | Calculation |
|---|---|
| **Per-dimension score** | Highest level for which all anchors are met (1, 2, 3, 4, or 5) |
| **Min score** | The lowest score across all 10 dimensions — this is the **controlling score**; the package can only be considered "ready" when min = 5 |
| **Pass condition** | All 10 dimensions = 5 |
| **Plateau condition** | Two iterations in a row with the same min score AND no individual dimension increased — stop and report residual to user |
| **Max iterations** | 5 |

## Reviewer Output Format

```markdown
# Review of Portable Agent Package — Iteration <N>

## Score Matrix

| Dimension | Score | Justification (file / section / line) |
|---|---|---|
| D1 Platform-Independence | <1-5> | <evidence> |
| D2 DOE Architecture Coverage | <1-5> | <evidence> |
| D3 Deterministic Execution | <1-5> | <evidence> |
| D4 Layered Memory | <1-5> | <evidence> |
| D5 Harness/Ralph-Loop | <1-5> | <evidence> |
| D6 Multi-Agent Coordination | <1-5> | <evidence> |
| D7 Progressive Disclosure | <1-5> | <evidence> |
| D8 Anti-Context-Rot | <1-5> | <evidence> |
| D9 Reproducibility / Bootstrap | <1-5> | <evidence> |
| D10 Anti-Pattern Catalog | <1-5> | <evidence> |

**Min score:** <N> | **Mean:** <N.N>

## Findings (concrete fix list — for any dimension < 5)

### D<n> <Dimension Name> (current: <X>, target: 5)
- **What:** <specific issue with file / section reference>
- **Why it matters:** <which level-5 anchor is unmet>
- **Severity:** CRITICAL | HIGH | MEDIUM | LOW
- **Suggestion:** <concrete fix; not vague>

[repeat for every <5 dimension]

## What's Working (1-3 items — anti-sycophancy guardrail)

- <thing the package does well>
- <thing the package does well>

## Verdict

- [ ] PASS — all dimensions = 5
- [ ] CONTINUE — dimensions < 5 with concrete fixes; iterate
- [ ] PLATEAU — two iterations with same min score; escalate to user
```

## Notes For The Reviewer

- **Do not inflate scores.** A 3 means "meets expectations" — that is acceptable, not failure. A 5 should be rare and earned.
- **Cite specifically.** "AGENT-OPERATING-MODEL.md §3.4" or "references/03-harness-design.md, anti-patterns table, row 2." Bare claims without evidence are not findings.
- **Verify before quoting.** If you reference content from a file (a section, a phrase, a code block), grep the file to confirm it exists. Hallucinated quotes are fabrications and must be deleted from your review.
- **Distinguish absent from buried.** "Not in the package" ≠ "not in the section I read." Search the whole package before claiming something is missing.
- **Severity guidance:**
  - CRITICAL — the package is unusable for its stated purpose without this fix
  - HIGH — fresh agent will misuse the principle without this fix
  - MEDIUM — package works but is meaningfully weaker without this fix
  - LOW — polish; stylistic; "nice to have"
