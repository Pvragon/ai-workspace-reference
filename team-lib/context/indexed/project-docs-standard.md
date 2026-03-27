---
template: context-indexed
version: 1.0.0
summary: "Standard structure for the docs/ directory within any project in projects/. Covers trust boundaries, mutability rules, naming conventions, and scaffolding. Extracted from workspace-reference.md Appendix A."
created: 2026-03-27
last_updated: 2026-03-27
maintainer: pvragon
see_also: workspace-reference.md
---

# Project Documentation Structure

> **Parent document:** [workspace-reference.md](workspace-reference.md) — canonical architectural reference for the AI Workspace.

This standard applies to the `docs/` directory within any project in `projects/`. It ensures agents and humans can navigate any project with the same mental model.

---

## Trust Boundaries

Documentation is separated by **trust level** to prevent agents from hallucinating based on outdated or non-authoritative information.

| Folder | Trust Level | Agent Guidance |
| :--- | :--- | :--- |
| **`specs/`** | **High (Authoritative)** | "This is what we are building." Read this for implementation tasks. |
| `adrs/` | Medium (Context) | Read only to understand *why* a decision was made. |
| `specs/reviews/` | Medium (Context) | Read to understand *why* a spec was reviewed and what decisions resulted. |
| `planning/` | Medium (Project Planning) | Resourcing, roles, risk registers, timelines, kickoff agendas. Read for project structure context. |
| `context/` | Medium (Business Context) | Read when evaluating trade-offs involving stakeholder priorities or product constraints. |
| `reference/` | Low (External) | Third-party docs. Useful for API details but we don't control them. |
| `.tmp/` | Low (Transient) | Working notes. Use for context, not as authority. |
| `archive/` | None (Historical) | **Do not use** for implementation. |

---

## Directory Map

```text
projects/<name>/docs/
├── specs/                   # The Definition of Done
│   ├── architecture/        # System-level constraints (e.g. security, stack)
│   ├── features/            # Feature-level implementation plans
│   └── reviews/             # Stakeholder spec reviews (immutable)
├── adrs/                    # Architecture Decision Records (immutable)
├── planning/                # Project planning: resourcing, roles, risk, timelines (optional)
├── context/                 # Business context: stakeholder preferences, constraints (living)
├── reference/               # Third-party API docs & manuals
├── archive/                 # Superseded documents (graveyard)
└── .tmp/                    # Scratchpad & working docs
```

---

## Mutability Legend

| Status | Meaning | Folder |
| :--- | :--- | :--- |
| **Immutable** | Should not be modified after acceptance | `adrs/`, `specs/reviews/` |
| **Immutable (system)** | Stable after architecture review; changes require review | `specs/architecture/` |
| **Semi-permanent** | Updated during active development, then stabilizes | `specs/features/` |
| **Immutable (by us)** | We don't modify, but external sources may change | `reference/` |
| **Historical** | Outdated documents preserved for reference | `archive/` |
| **Transient** | Working documents, not authoritative | `.tmp/` |
| **Living** | Updated as stakeholder context evolves; not specs | `context/` |
| **Semi-permanent** | Stabilizes after project launch; updated if team/scope changes | `planning/` |

---

## Contributing & Naming

| Document Type | Location | Naming Convention |
| :--- | :--- | :--- |
| System architecture | `specs/architecture/` | `YYMMDD-descriptive-title.md` |
| Feature specs | `specs/features/` | `YYMMDD-descriptive-title.md` |
| Architecture decisions | `adrs/` | `YYMMDD-short-title.md` (accepted); `proposed-YYMMDD-…` / `rejected-YYMMDD-…` (other states) |
| Stakeholder spec reviews | `specs/reviews/` | `YYMMDD-role-high-level-review.md` |
| Project planning (roles, risk, resourcing) | `planning/` | `YYMMDD-descriptive-title.md` |
| Business context, stakeholder preferences | `context/` | `YYMMDD-descriptive-title.md` |
| Working notes | `.tmp/` | `YYMMDD-descriptive-title.md` |

---

## Quick Start: Scaffolding

To add this structure to a new or existing project, use the shared scaffold tool in `team-lib`.

```bash
# From workspace root
python3 team-lib/executions/scaffold_project_docs.py projects/my-new-project
```

This will:
1. Create the full directory tree
2. Populate READMEs with the correct project name
3. Add `.gitkeep` files to preserve structure
