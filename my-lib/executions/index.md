# executions

## Purpose
Store deterministic, dual-purpose Python scripts for personal automation. Each script should be both CLI-runnable and Python-importable.

## What Belongs Here
- Personal automation scripts with a `run()` entry point
- Tools not yet ready for team-lib graduation
- Scripts that follow the [execution-standard](../context/indexed/execution-standard.md) (when available via team-lib)

## What Does NOT Belong Here
- Skill definitions (use `skills/`)
- Runtime outputs (use `runtime/`)
- Persona definitions (use `personas/`)

## File Naming Conventions
- `<script_name>.py` using `snake_case`
- Use action-oriented names (e.g., `graduate_files.py`)

## Dual-Purpose Pattern
All scripts should expose:
- **CLI:** `python3 script_name.py --arg value`
- **Import:** `from executions.script_name import run`

## How Agents Should Use This Folder
Import scripts via `run()` for programmatic chaining, or invoke via CLI for standalone use.

## Contents

See `registry/executions.yaml` for the current file manifest.
