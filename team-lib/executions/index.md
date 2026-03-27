# executions

## Purpose
Deterministic, dual-purpose Python scripts that handle API calls, data processing, file operations, and other repeatable tasks. Each script is both CLI-runnable and Python-importable.

## What Belongs Here
- Deterministic Python scripts with a `run()` entry point
- Automation tools (scaffolding, releasing, data pipelines)
- Scripts that follow the [execution-standard](../context/indexed/execution-standard.md)

## What Does NOT Belong Here
- Personal workflows (use `my-lib/executions/`)
- Runtime outputs (use `runtime/`)
- Skill definitions (use `skills/`)

## File Naming Conventions
- `<script_name>.py` using `snake_case`

## Dual-Purpose Pattern
All scripts expose:
- **CLI:** `python3 script_name.py --arg value`
- **Import:** `from executions.script_name import run`

See `context/indexed/execution-standard.md` for the full standard.

## Contents

See `registry/executions.yaml` for the current file manifest.

## How Agents Should Use This Folder
Import scripts via `run()` for programmatic chaining, or invoke via CLI for standalone use.
