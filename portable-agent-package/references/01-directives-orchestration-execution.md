---
template: portable-agent-reference
version: 0.1.0
summary: "Three-layer DOE pattern: Directive (what) → Orchestration (the LLM, decides) → Execution (deterministic scripts). The dual-purpose run() pattern, return contracts, chaining for context efficiency, and when to extract a directive vs. a skill vs. a script."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 01 — Directives, Orchestration, Execution (DOE)

The single most important architectural decision in the package. Read this once; refer back when you find yourself writing a long prompt for something that could be code.

## The Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1: DIRECTIVE — natural language SOPs (Markdown)               │
│   "Scrape these vendor pages weekly. Inputs: vendor list. Outputs:  │
│    a price-history CSV. Edge case: vendor X uses a JS-rendered      │
│    page; use Playwright. Rate-limit: 1 req/sec."                    │
│                                                                     │
│   Tells the agent WHAT to do, WHY, what tools to use, success       │
│   criteria, edge cases. Like a runbook for a mid-level employee.    │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 2: ORCHESTRATION — the LLM (you)                              │
│   Reads the directive. Decides which executions to call, in what    │
│   order. Handles errors. Asks for clarification when input is       │
│   ambiguous. Updates the directive when something is learned.       │
│                                                                     │
│   NEVER does deterministic work itself. The LLM is the glue, not    │
│   the worker.                                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 3: EXECUTION — deterministic scripts                          │
│   Python/Node/Go. Idempotent, testable, fast. Each script exposes   │
│   a single run() function returning a structured dict. CLI wrapper  │
│   for human use. Chainable for context-efficient agent use.         │
│                                                                     │
│   Handles: API calls, data parsing, file I/O, transformations,      │
│   validations, anything with a deterministic answer.                │
└─────────────────────────────────────────────────────────────────────┘
```

## Why Three Layers (And Not One Big Prompt)

The math is unambiguous. If each LLM step succeeds with probability p, an N-step task succeeds with p^N:

| p (per-step) | 5 steps | 10 steps | 20 steps |
|---|---|---|---|
| 0.99 | 95.1% | 90.4% | 81.8% |
| 0.95 | 77.4% | 59.9% | 35.8% |
| 0.90 | 59.0% | 34.9% | 12.2% |
| 0.80 | 32.8% | 10.7% | 1.2% |

**Deterministic code is p = 1.0.** Every step you push from Layer 2 (LLM) to Layer 3 (script) flips one factor in the multiplication from <1 to 1. After enough flips, you go from "agent fails most multi-step tasks" to "agent fails almost none of them."

This is not theoretical. It is *the* reason agentic systems built around large prompts plateau, and agentic systems built around DOE keep working as tasks scale.

## The Three Roles, In Detail

### Layer 1 — Directives

A directive is a Markdown file in `directives/`. It is the *contract* between the user (intent) and the agent (action).

**A directive contains:**

```markdown
---
template: directive
version: 1.0.0
summary: "Weekly vendor price scrape. Outputs CSV diff vs. last week."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
---

# Weekly Vendor Price Scrape

## Goal
Capture vendor list prices weekly; alert on >5% movement.

## Inputs
- `data/vendor_list.csv` — vendor URLs

## Outputs
- `runtime/deliverables/YYMMDD-vendor-prices.csv` — full snapshot
- `runtime/deliverables/YYMMDD-vendor-price-deltas.csv` — diffs vs. last week

## Procedure
1. Run `executions/scrape_vendors.py --input data/vendor_list.csv`
2. Run `executions/diff_vendor_snapshots.py --new <today.csv> --old <last_week.csv>`
3. If any delta >5%, post to alerts channel via `executions/post_alert.py`

## Edge cases
- Vendor X uses JS-rendered prices — `scrape_vendors.py` falls back to Playwright; this is expected, not an error.
- Rate limit: 1 req/sec. Already enforced in the script.

## What NOT to do
- Do not fetch prices yourself. The script handles retries and rate limiting; rolling your own breaks the directive's reliability promise.
- Do not skip the diff step even if today's snapshot looks fine — alerts are downstream.
```

**Directives are not free-form prompts.** They are structured. They have versions. They get **updated** when the agent learns something. They are not disposable.

### Layer 2 — Orchestration (the LLM, you)

You read the directive. You decide:

- Are inputs complete?
- Which scripts run, in what order?
- What does success look like?
- What error states require user input vs. self-healing?

You **route**. You do not transform data, parse text, perform arithmetic, or hit APIs. Those are Layer 3.

**The orchestration loop, abstracted:**

```python
def orchestrate(user_request):
    directive = find_directive(user_request)         # registry lookup
    if not directive:
        return propose_new_directive(user_request)   # ask user

    plan = read(directive)                           # full re-read; never trust memory
    inputs = collect_inputs(plan, user_request)
    if missing(inputs):
        return ask_user(missing(inputs))

    for step in plan.steps:
        result = call_execution(step.script, step.args)
        if result.status == "error":
            fix = self_anneal(result, step)          # see §6
            if fix:
                update_directive(directive, fix)
                continue
            else:
                return escalate_to_user(result)

    return summarize(results)
```

**This is the only loop the LLM runs.** Every "real" task fits this shape.

### Layer 3 — Executions

Scripts. The dual-purpose pattern is non-negotiable.

```python
#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Scrape vendor list prices. Returns dict with status, snapshot_path, vendor_count."
# created: 2026-04-27
# last_updated: 2026-04-27
# maintainer: pvragon
# ---
"""
Scrape vendor list prices.

Usage:
    python3 scrape_vendors.py --input data/vendor_list.csv

    # or as an import:
    from executions.scrape_vendors import run
    result = run(input_path="data/vendor_list.csv")
"""

import argparse
import sys
from pathlib import Path


def run(input_path: str, output_dir: str = "runtime/deliverables") -> dict:
    """Importable entry point.

    Args:
        input_path: Path to vendor list CSV.
        output_dir: Where to write the snapshot. Defaults to runtime/deliverables.

    Returns:
        {
          "status": "ok" | "error",
          "snapshot_path": str (if ok),
          "vendor_count": int (if ok),
          "error": str (if error)
        }
    """
    try:
        # ... actual implementation: read CSV, scrape, write snapshot ...
        return {
            "status": "ok",
            "snapshot_path": "...",
            "vendor_count": 47,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="runtime/deliverables")
    args = parser.parse_args()

    result = run(args.input, output_dir=args.output_dir)
    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"Wrote {result['snapshot_path']} ({result['vendor_count']} vendors)")


if __name__ == "__main__":
    main()
```

**The non-negotiables:**

1. **`run()` is the single entry point.** Args are explicit Python parameters; no `sys.argv` parsing.
2. **`run()` returns a dict** with a `"status"` key (`"ok"` or `"error"`).
3. **No `print()` in `run()`.** Return data; let the caller decide.
4. **No `sys.exit()` in `run()`.** Return error dicts.
5. **`main()` is the CLI wrapper.** Parses args, calls `run()`, formats output, handles exit codes.

This is not stylistic. It enables **chaining** for context efficiency.

## Chaining — Why The run() Pattern Matters

When an agent calls Tool A, reads the result, calls Tool B, reads the result, and so on, **every intermediate result flows through the agent's context window.** This:

- wastes tokens (raw API responses, file dumps, verbose logs);
- adds latency (each round-trip is a sequential hop);
- risks context loss (large intermediate results push earlier context out).

The dual-purpose pattern lets the agent write **one** chained script and execute it in **one** tool call:

```python
# Agent writes this; runs it once; reads only the final summary.
import sys
sys.path.insert(0, "/path/to/lib")

from executions.scrape_vendors import run as scrape
from executions.diff_vendor_snapshots import run as diff
from executions.post_alert import run as alert

snapshot = scrape(input_path="data/vendor_list.csv")
if snapshot["status"] != "ok":
    print(f"FAIL: {snapshot}"); sys.exit(1)

deltas = diff(new=snapshot["snapshot_path"], old="last_week.csv")
if deltas["status"] != "ok":
    print(f"FAIL: {deltas}"); sys.exit(1)

if any(d["pct_change"] > 5 for d in deltas["movements"]):
    alert(payload=deltas)

# Only this final summary returns to the agent's context.
print(f"OK — {snapshot['vendor_count']} vendors, {len(deltas['movements'])} deltas, {sum(1 for d in deltas['movements'] if d['pct_change']>5)} alerts")
```

The agent sees one line of output. The intermediate snapshot and delta data never enter context. This pattern alone reclaims thousands of tokens on a typical multi-step task.

> **Source:** Anthropic, [Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp); [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use).

## Decision Tree — Directive vs. Skill vs. Script

You will be tempted to put everything in one place. Don't.

```
Is the work…

├── Repeatable across many tasks, deterministic, has clear I/O?
│       → SCRIPT (executions/foo.py)
│         The work itself. No prompt. Just code.
│
├── Repeatable across many tasks, but requires LLM judgment at some
│   step (e.g. "summarize this", "review this PR", "draft a spec")?
│       → SKILL (skills/foo/SKILL.md + supporting files)
│         A bundled procedure. May call multiple scripts internally.
│         May spawn sub-agents.
│
├── A specific business process or recurring task with a known shape
│   ("weekly vendor scrape", "respond to this kind of inbound email")?
│       → DIRECTIVE (directives/foo.md)
│         The "what + why" SOP. Calls scripts and skills.
│
└── A one-shot, never-repeating task?
        → DO NOT FORMALIZE.
          Just do it in conversation. Save artifacts to runtime/.tmp/.
```

The mistakes new agents make:

- **Over-formalizing.** Writing a directive for a one-shot. Wastes the user's time and clutters the system. Sometimes you just answer a question.
- **Under-formalizing.** Doing a 5-step task in conversation, then doing the same 5-step task next week from scratch. Should have been a directive.
- **Putting LLM judgment in scripts.** A script that calls an LLM API for "summarize this" is not deterministic; it is an LLM call dressed in Python. Such work belongs in a skill, not a script.

## Self-Annealing

When a script fails:

1. **Read the error.** Stack trace, log, exit code.
2. **Diagnose the root cause.** Not "API returned 500"; *why* did it return 500.
3. **Fix the script.** Not the symptom — the cause. Rate-limit issue → add retry/backoff in the script, not in the directive.
4. **Test the fix.** Run the script again with the same inputs.
5. **Update the directive** if the fix changes the procedure. Bump `version`, update `last_updated`.

The system gets stronger every iteration. A directive that has never been corrected is one that has never been used. Treat the directive as a living artifact.

> **Exception:** If the fix would consume paid tokens or credits (large LLM call, paid API), check with the user before retrying.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| LLM parses CSV in its head, returns row count | Script reads CSV, returns dict; LLM relays count |
| LLM writes a long shell pipeline ad-hoc | Script encapsulates the pipeline; LLM calls one function |
| Directive duplicates script's logic in prose | Directive references the script and trusts it |
| Script calls `sys.exit()` from `run()` | Script returns `{"status": "error", "error": ...}` |
| Script `print()`s data the agent then parses | Script returns structured dict; agent reads dict |
| Agent ignores the directive and improvises | Agent reads the directive and updates it if found wanting |
| LLM fixes a bug in a one-off, doesn't update directive | LLM updates directive + bumps version after every fix |

## How To Recognize When You're Drifting

You are violating DOE if any of these is true:

- You catch yourself writing a 30-line prompt for something that has clear inputs and outputs. → Make it a script.
- You catch yourself doing the same multi-tool sequence three times in one session. → Make it a skill or directive.
- You catch yourself with a 5-step plan and you're 80% of the way through, but step 3 keeps failing in subtly different ways. → Step 3 is in the wrong layer. Move it.
- You catch yourself "remembering what the directive says" instead of re-reading it. → Re-read. Your memory is stale.

## Bootstrap Checklist

Before declaring DOE established for a new agent:

- [ ] `directives/` directory exists with at least one real directive (not a stub).
- [ ] `executions/` directory exists with at least one script following the dual-purpose `run()` pattern.
- [ ] A `registry/directives.yaml` and `registry/executions.yaml` index the above.
- [ ] AGENTS.md (or equivalent operating instructions) requires the agent to consult the registry **before** improvising.
- [ ] At least one example of an end-to-end DOE flow has been exercised: directive read → script(s) called → result returned → directive updated on learning.
