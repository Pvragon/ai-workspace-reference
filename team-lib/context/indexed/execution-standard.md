---
version: 1.1.0
summary: "Defines the dual-purpose execution script pattern: CLI + importable run() function, comment-block frontmatter requirement, return contract, and chaining rules. Load when creating or reviewing execution scripts."
created: 2026-02-18
last_updated: 2026-02-25
maintainer: pvragon
tags: [execution, scripts, dual-purpose, context-efficiency]
---

# Execution Script Standard

Standard pattern for execution scripts in the Pvragon AI Workspace. All scripts in `executions/` directories should follow this pattern.

## The Dual-Purpose Pattern

Every execution script should be **both CLI-runnable and Python-importable**:

- **CLI:** Run from the terminal via `python3 script.py --arg value`
- **Import:** Call from Python code via `from executions.script_name import run`

This enables agents to chain multiple operations in a single script, keeping intermediate data out of the context window and reducing token usage.

### Why This Matters

When an agent orchestrates a multi-step workflow by making sequential tool calls, every intermediate result flows through the agent's context (its "working memory"). This:

- **Wastes tokens** — raw API responses, full file contents, and verbose logs consume context space
- **Increases latency** — each round-trip adds delay
- **Risks context loss** — large intermediate results can push earlier context out of the window

The dual-purpose pattern lets agents write a single script that chains operations internally. Only the final, curated summary returns to the agent.

> **Source:** [Anthropic — Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), [Anthropic — Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

---

## Frontmatter

Python files cannot use raw YAML frontmatter (`---`), so execution scripts use a **comment-block** convention. Place the frontmatter immediately after the shebang line, before the module docstring:

```python
#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "One-two sentence description answering 'what does this script do?'"
# created: YYYY-MM-DD
# last_updated: YYYY-MM-DD
# maintainer: pvragon
# ---
```

This applies to **all** Python scripts in `executions/` directories and any companion `.py` files inside `skills/` directories. The fields follow the same metadata standard as Markdown frontmatter (see AGENTS.md § File Metadata Standards).

---

## Script Structure

```python
#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Brief description of what this script does."
# created: YYYY-MM-DD
# last_updated: YYYY-MM-DD
# maintainer: pvragon
# ---
"""
Brief description of what this script does.

Usage:
    python3 script_name.py --arg1 value1 --arg2 value2
"""

import argparse
import sys
from pathlib import Path


def do_work(param: str) -> dict:
    """Core logic. Returns structured results."""
    # ... implementation ...
    return {"status": "ok", "result": "..."}


def run(param: str, option: str = None) -> dict:
    """Importable entry point for programmatic use.

    Args:
        param: Required parameter description.
        option: Optional parameter description.

    Returns:
        dict with keys: status, result, error (on failure)
    """
    # Validation, path resolution, etc.
    return do_work(param)


def main() -> None:
    """CLI entry point — thin wrapper around run()."""
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("param", help="...")
    parser.add_argument("--option", default=None, help="...")
    args = parser.parse_args()

    result = run(args.param, option=args.option)

    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"Success: {result['result']}")


if __name__ == "__main__":
    main()
```

---

## Key Rules

1. **`run()` is the single entry point** — All parameters are explicit Python arguments (no `sys.argv` parsing)
2. **`run()` returns a dict** — Always includes `"status"` key (`"ok"` or `"error"`)
3. **No `sys.exit()` in `run()`** — Return error dicts or raise exceptions instead
4. **No `print()` in `run()`** — Return data; let the caller decide how to display
5. **`main()` is the CLI wrapper** — Parses args, calls `run()`, formats output, handles `sys.exit()`
6. **Error handling via exceptions or error dicts** — Use `RuntimeError` for failures instead of `sys.exit(1)`

---

## Return Contract

All `run()` functions should return a dict with at minimum:

```python
# Success
{"status": "ok", "result_key": "value", ...}

# Error
{"status": "error", "error": "Human-readable error message"}
```

Additional keys are script-specific. Document them in the `run()` docstring.

---

## Chaining Example

An agent can chain multiple dual-purpose scripts in a single operation:

```python
# Agent writes this as a single script, runs it in one tool call
import sys
sys.path.insert(0, "/home/user/ai-workspace/team-lib")

from executions.scaffold_project_docs import run as scaffold
from executions.publish_github_release import run as publish

# Step 1: Scaffold docs
result = scaffold(target="/home/user/ai-workspace/projects/my-app", name="My App")
if result["status"] != "ok":
    print(f"Scaffold failed: {result}")
    sys.exit(1)

# Step 2: Only print what the agent needs to reason about
print(f"Created {result['files_created']} files at {result['docs_dir']}")
```

The agent gets a 1-line summary instead of the full file listing, template contents, and directory tree that would have flowed through context with sequential tool calls.

---

## Checklist for New Scripts

- [ ] Comment-block frontmatter with `template`, `version`, `summary`, `created`, `last_updated`, `maintainer`
- [ ] Module-level docstring with Usage examples
- [ ] Has a `run()` function with typed parameters and return type `-> dict`
- [ ] `run()` docstring documents all parameters and return keys
- [ ] `run()` never calls `sys.exit()` or `print()` for display
- [ ] `main()` is a thin CLI wrapper that calls `run()`
- [ ] Return dict always includes `"status"` key
- [ ] Error cases return `{"status": "error", "error": "..."}` instead of raising
