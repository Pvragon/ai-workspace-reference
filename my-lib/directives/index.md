---
summary: "Index of directives in my-lib. Scan to find relevant files before opening individual documents."
---

# directives

## Purpose
Store high-level instructions, behavioral rules, and operational guidelines for AI agents.

## What Belongs Here
- Global behavioral directives
- Task-specific instruction sets
- Safety and constraint rules
- Workflow guidelines

## What Does NOT Belong Here
- Persona definitions (use `personas/`)
- Skill implementations (use `skills/`)
- Runtime data or logs

## File Naming Conventions
- `<scope>-<name>.md` (e.g., `global-safety-rules.md`, `task-code-review.md`)

## How Agents Should Use This Folder
Agents should load relevant directives before task execution to understand operational constraints and expected behaviors.

## Contents

See `registry/directives.yaml` for the current file manifest.
