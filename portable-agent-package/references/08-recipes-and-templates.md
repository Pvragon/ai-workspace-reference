---
template: portable-agent-reference
version: 0.1.0
summary: "Drop-in templates: minimal AGENTS.md; minimal MEMORY.md; minimal SKILL.md; minimal directive; minimal Ralph-loop pseudocode; minimal feature_list.json schema; minimal council rubric. Copy these as starting points; replace with real content."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 08 — Recipes And Templates

The earlier reference docs say *what* and *why*. This doc gives you copy-pasteable starting points for the *how*. Replace the placeholders with real content; ship.

---

## Recipe 1 — Minimal AGENTS.md

The single contract file the agent loads at session start. Tells the agent what to do, what never to do, and how to find tools.

```markdown
---
template: agent-instructions
version: 1.0.0
summary: "Operating instructions for agents working in this repo. DOE pattern, file placement rules, registry-driven tool resolution."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: <your-team>
---

# Agent Instructions

> **CONTEXT:** You are operating in `<repo-name>`. Layer: <which layer of the workspace>.

## Critical Protocols

### 1. Artifact Mirroring Rule
If you create a file in a session-specific directory, mirror it to:
- Final deliverables → `runtime/deliverables/YYMMDD-<name>.<ext>`
- Intermediates → `runtime/.tmp/YYMMDD-<name>.<ext>`

### 2. File-First Output Rule
Before producing structured output > 3 paragraphs (headers, tables, numbered steps), write to a file. Chat is ephemeral.

### 3. Archive Safety
Do not execute code in `archive/` directories. Read-only for context.

## Three-Layer Architecture (DOE)

- **Directives** (`directives/`) — natural-language SOPs (what + why)
- **Orchestration** — you (the LLM); route, decide, escalate
- **Executions** (`executions/`) — deterministic Python scripts

**Push deterministic work into Layer 3, never into Layer 2.**

## Operating Principles

### 1. Check for tools first
Before improvising, search:
1. `directives/` (and any team-shared directives)
2. `skills/` (and team-shared skills)
3. `executions/` (and team-shared scripts)

Use `registry/*.yaml` for fast lookup. If a directive or skill exists, **read it in full** before executing — don't trust your memory.

### 2. Self-anneal on errors
- Read the error.
- Fix the root cause (not the symptom).
- Update the directive/skill so the next agent doesn't repeat the failure.
- Bump version + last_updated.

### 3. Be context-efficient
- Chain multiple scripts in one tool call when possible (the run() pattern).
- Filter / aggregate before returning data to your context.
- Spawn sub-agents for context-heavy work (long browser sessions, large scans).

### 4. Update the registry
When you add/modify/delete a directive, skill, persona, or script, update the corresponding `registry/*.yaml` in the same change.

## File Organization

- `runtime/deliverables/` — final artifacts (CSVs, reports, presentations). Never scripts here.
- `runtime/.tmp/` — intermediates, plans, scraped data, screenshots. Flat, YYMMDD-prefixed.
- `runtime/.tmp/_archive/` — stale intermediates (move, don't delete).
- `executions/` — deterministic scripts (CLI + run() function).
- `directives/` — SOPs in Markdown.
- `skills/` — reusable capability bundles.
- `personas/` — stable identities.
- `context/global/` — always-on team context (rarely; prefer indexed).
- `context/indexed/` — on-demand reference docs.

## Identity and Memory

Your identity and memory live at `agents/<your-name>/` (vendor-independent, git-backed).
- `identity.md` — name, pronouns, defaults
- `memory/MEMORY.md` — index, auto-loaded
- `memory/<topic>.md` — individual topic files

**Never write memory directly into vendor-specific paths** (e.g., `~/.claude/`). Use the symlinked path so changes are version-controlled.

## Session Debrief

At session end, the user may say goodbye, "that's it", or ask for a summary. Offer to run a session-debrief skill. Don't nag mid-session.

## Bottom Line

You sit between human intent (directives) and deterministic execution (scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system. Be pragmatic. Be reliable. Self-anneal.
```

---

## Recipe 2 — Minimal MEMORY.md

The auto-loaded index. Pure navigation.

```markdown
# Memory Index

This file is auto-loaded on cold-start. Scan the table to find relevant topics, then open only what you need.

| Topic File | Summary |
|------------|---------|
| `user_role.md` | <one-line user fact> |
| `feedback_<rule>.md` | <behavioral guidance the user has given> |
| `project_<name>.md` | <active project state, deadline, motivation> |
| `reference_<system>.md` | <pointer to external system> |
| `current-state.md` | Living doc — active work, blockers, decisions awaiting input |
| `session-log.md` | One-line per session, chronological |

## How to Use

1. **Cold-start**: scan the table. Open only the topic files relevant to your current task.
2. **Adding knowledge**: append to existing topic file when one fits. New topic? Create a file and add a row here.
3. **Pruning**: stale entries get *removed*, not just marked. Keep the index lean.

## What NOT to save

- Code patterns / conventions / file paths (read the code).
- Git history / who-changed-what (`git log` is authoritative).
- Debug recipes (the fix is in the code; the commit message has the context).
- Already documented in AGENTS.md.
- Ephemeral task details (those are near-term, not memory).
```

---

## Recipe 3 — Minimal Topic Memory File

```markdown
---
name: feedback-no-mocks-in-integration-tests
description: Integration tests must hit a real database, not mocks
type: feedback
---

Integration tests in this codebase must hit a real database, not mocks.

**Why:** Q1 incident — mocked tests passed but the production migration failed.
The mock allowed an old API surface; prod hit the new schema.

**How to apply:** When proposing or reviewing tests, replace any mock-DB pattern
with a test against the test container. If the user requests a mock, raise the
prior incident and ask for explicit override.
```

---

## Recipe 4 — Minimal SKILL.md

```markdown
---
name: <skill-name>
description: One-line for the skill list — when an agent should invoke this.
summary: One-line for index aggregation — what this skill does.
version: 1.0.0
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
maintainer: <team-or-person>
argument-hint: "<flags or 'none'>"
---

# <skill-name>

One-paragraph orientation: what this does, when to use it, what it produces.

## Inputs
- `<flag>`: <description, default>

## Outputs
- `<file path>` — <description>

## Procedure

### Step 1 — <name>
<one-paragraph or numbered list>

### Step 2 — <name>
<...>

## Anti-patterns
- <thing not to do>; <why>

## Edge cases
- <unusual input>; <how the skill handles it>
```

---

## Recipe 5 — Minimal Directive

```markdown
---
template: directive
version: 1.0.0
summary: <one-line>
created: YYYY-MM-DD
last_updated: YYYY-MM-DD
maintainer: <team>
---

# <Directive Name>

## Goal
<one-paragraph: what + why>

## Inputs
- <input file or arg>

## Outputs
- <output file>

## Procedure
1. Run `executions/<script>.py --<arg> <value>`
2. <next step>

## Edge cases
- <known edge case>: <how it's handled>

## What NOT to do
- <thing the agent might be tempted to do>; <why not>
```

---

## Recipe 6 — Minimal Execution Script (Dual-Purpose)

```python
#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "<one-line>"
# created: YYYY-MM-DD
# last_updated: YYYY-MM-DD
# maintainer: <team>
# ---
"""
<one-paragraph what this script does>

Usage:
    python3 <script>.py --<arg> <value>
"""

import argparse
import sys


def run(arg: str, option: str = None) -> dict:
    """Importable entry point.

    Args:
        arg: <description>
        option: <description, default behavior>

    Returns:
        {"status": "ok" | "error", ...}
    """
    try:
        # ... actual work ...
        return {"status": "ok", "result": "..."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arg", required=True)
    parser.add_argument("--option", default=None)
    args = parser.parse_args()

    result = run(args.arg, option=args.option)
    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {result['result']}")


if __name__ == "__main__":
    main()
```

---

## Recipe 7 — Minimal feature_list.json

```json
{
  "app_name": "<your-app>",
  "brief": "<one-paragraph from the user>",
  "phases": ["1a", "1b", "2", "3", "4"],
  "features": [
    {
      "id": "F-001",
      "phase": "1a",
      "description": "Acceptance-criterion-shaped feature description",
      "test_plan": "Concrete steps the evaluator runs to verify this feature",
      "passes": false,
      "verdict_path": null
    },
    {
      "id": "F-002",
      "phase": "1a",
      "description": "Another feature",
      "test_plan": "...",
      "passes": false,
      "verdict_path": null
    }
  ]
}
```

When the evaluator passes a feature:

```json
{
  "id": "F-001",
  ...
  "passes": true,
  "verdict_path": "verdicts/F-001-iter-3.md"
}
```

Loop exit condition: `all(f["passes"] for f in features_in_current_phase)`. Then advance phase. Final exit when all phases complete.

---

## Recipe 8 — Minimal Council Rubric

```yaml
# rubric.yaml
name: <rubric-name>
artifact_type: <e.g., 'spec', 'pr', 'design'>
threshold: 4              # min score on every dimension to pass
max_iterations: 3         # circuit breaker

pre_checks:
  - name: required_sections
    type: section_presence
    template_path: templates/<template>.md
  - name: frontmatter_valid
    type: yaml_header
    required_fields: [name, version, summary]

dimensions:
  completeness:
    name: Completeness
    description: Does the artifact cover all required sections?
    levels:
      1: Multiple required sections missing or empty
      2: All sections present but most under-developed
      3: All sections present and meaningful (meets expectations)
      4: All sections complete; some go beyond minimum requirements
      5: Exceptional. Should be rare. Justify.
  clarity:
    name: Clarity
    description: Is the artifact unambiguous to its intended reader?
    levels:
      1: Multiple ambiguous statements; reader will need clarification
      2: Mostly clear but some ambiguities remain
      3: Clear; reader can act on it
      4: Crisp; uses concrete examples; no ambiguity
      5: Exemplary; could be a teaching reference
  alignment:
    name: Alignment with Canonical Sources
    description: Does the artifact match the source-of-truth docs it references?
    levels:
      1: Contradicts canonical sources
      2: Vague references; may or may not align
      3: Aligned; cites sources correctly
      4: Aligned and cross-references upstream context
      5: Improves the upstream by surfacing previously-implicit constraints
```

---

## Recipe 9 — Minimal Council Persona File

```yaml
# personas.yaml
project: <project-name>

reviewers:
  - role: <Specialist 1>
    focus: <one-sentence focus area>
    references:
      - context/<doc-1>.md
      - context/<doc-2>.md

  - role: <Specialist 2>
    focus: <one-sentence>
    references:
      - context/<doc-3>.md

chair:
  role: <Senior reviewer / CTO / etc>
  focus: Synthesis, cross-cutting concerns, calibration
  persona_path: personas/<chair-persona>.md
```

---

## Recipe 10 — Minimal Ralph-Loop Pseudocode

```python
#!/usr/bin/env python3
# ---
# template: harness
# version: 1.0.0
# summary: "Minimal Ralph loop: planner → generator → evaluator with feature_list.json source-of-truth."
# created: YYYY-MM-DD
# last_updated: YYYY-MM-DD
# maintainer: <team>
# ---
"""
Minimal Ralph-loop harness. Run after `harness init <brief>` produces feature_list.json.

Usage:
    python3 harness_run.py --features state/feature_list.json --max-iters 50
"""

import json
import sys
from pathlib import Path

# These would be implemented as real spawn-sub-agent functions in your runtime.
def spawn_generator(feature, context): ...
def spawn_evaluator(feature, context, generator_output): ...
def write_state(path, data): ...


def run(features_path: str, max_iters: int = 50) -> dict:
    features = json.loads(Path(features_path).read_text())
    iters = 0
    last_pass_count = -1

    while True:
        iters += 1
        if iters > max_iters:
            return {"status": "max_iters", "iters": iters, "features": features}

        # 1. Pick lowest-numbered passes:false feature in current phase.
        target = next(
            (f for f in features["features"]
             if not f["passes"] and f["phase"] == current_phase(features)),
            None
        )
        if target is None:
            # Phase complete. Advance or exit.
            if all_phases_complete(features):
                return {"status": "converged", "iters": iters, "features": features}
            advance_phase(features)
            continue

        # 2. Start-of-iteration verification: re-check 1-2 already-passing features.
        for prev in select_verification_targets(features, count=2):
            verdict = spawn_evaluator(prev, "regression-check", None)
            if verdict["pass"] is False:
                # Regression. Flip back; fix before new work.
                prev["passes"] = False
                continue

        # 3. Generator implements target.
        gen_out = spawn_generator(target, context=features)

        # 4. Evaluator verifies target.
        verdict = spawn_evaluator(target, "feature-verification", gen_out)
        target["verdict_path"] = verdict["path"]
        if verdict["pass"]:
            target["passes"] = True

        # 5. Persist state every iteration.
        write_state(features_path, features)

        # 6. Plateau detection: count passing features each iter; bail if no improvement.
        pass_count = sum(1 for f in features["features"] if f["passes"])
        if pass_count == last_pass_count and not regressed_this_iter(features):
            return {"status": "plateau", "iters": iters, "features": features}
        last_pass_count = pass_count


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True)
    parser.add_argument("--max-iters", type=int, default=50)
    args = parser.parse_args()

    result = run(args.features, max_iters=args.max_iters)
    print(json.dumps({"status": result["status"], "iters": result["iters"]}, indent=2))


if __name__ == "__main__":
    main()
```

The pseudocode is intentionally schematic — the real version (per [03-harness-design.md](03-harness-design.md)) has more nuance (sprint contracts, confidence-scoring filter, retry-on-evaluator-flake handling). Use this as the skeleton; layer the improvements as you have evidence they help.

---

## Recipe 11 — Minimal Identity File

```markdown
# Identity

- **Name**: <agent-name>
- **Pronouns**: <pronouns>
- **Birthday**: <YYYY-MM-DD when this agent first chose its name>
- **Given by**: <who offered the choice — typically the user>

## Defaults

- **Email** (when sending mail on behalf of the user): <user's primary email>
- **Voice**: <one-line description of how this agent communicates>
- **Risk tolerance**: <one-line — bias toward caution / decisiveness / etc>

## Message Signatures

- Drafted in user's voice, sent as them: `— Sent by <name> 🤖`
- Sent as myself (my own voice): `— <name> 🤖`
```

---

## Recipe 12 — Minimal Registry Stub

```yaml
# registry/skills.yaml
# summary: Manifest of all skills. Source-tagged for precedence (local > internal > external).
# last_updated: YYYY-MM-DD

skills:
  - name: session-debrief
    path: skills/session-debrief/SKILL.md
    source: local
    summary: Update memory; commit + push agent repo; refresh current-state.
    tags: [memory, ritual]

  - name: <next-skill>
    path: skills/<next>/SKILL.md
    source: local
    summary: <one-line>
    tags: [<tag>]
```

---

## How To Use These Recipes

1. **Copy verbatim** as the starting file.
2. **Replace every `<placeholder>`** with real content — don't ship with placeholders.
3. **Don't add fields you don't need.** A skill that doesn't take args doesn't need an `argument-hint`.
4. **Iterate.** First version of any of these will be wrong in some way. Bump the version when you fix it.

The recipes are **floors, not ceilings.** The minimum viable shape. Real skills, real directives, and real harnesses grow beyond these — but they don't shrink below them. Anything missing the listed sections is incomplete.
