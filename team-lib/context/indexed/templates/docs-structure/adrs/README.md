# Architecture Decision Records (ADRs)

> **Immutable** — ADRs are permanent records that should not be modified after acceptance.

This directory contains Architecture Decision Records documenting what we decided and why throughout the {PROJECT_NAME} project.

## Contents

| ADR | Title | Status |
|-----|-------|--------|
| *None yet* | | |

See [`template.md`](./template.md) for the standard ADR template.


## What is an ADR?

An Architecture Decision Record captures an important architectural decision along with its context, options considered, and rationale — so you can look back later and understand *why* a choice was made, not just *what* was chosen.

## When to Create an ADR

Create an ADR when making decisions about:
- Technology stack choices (frameworks, libraries, services)
- Architectural patterns and approaches
- Infrastructure and deployment strategies
- Security and compliance approaches
- Major refactoring or migration decisions
- API design patterns
- Data modeling approaches
- Deviations from the system architecture spec

## Naming Convention

ADRs use date-based naming with a status prefix for non-accepted records:

| State | Filename Pattern | Notes |
|-------|-----------------|-------|
| Accepted | `YYMMDD-short-title.md` | No prefix — clean name signals approval |
| Proposed | `proposed-YYMMDD-short-title.md` | Drop the prefix when accepted (one rename) |
| Rejected | `rejected-YYMMDD-short-title.md` | Prefix is permanent; file stays in this folder |

Example: `proposed-260208-adr-fargate-first-compute.md` → `260208-adr-fargate-first-compute.md` upon acceptance.

## Agent Guidance

Read ADRs when you need to understand why a specific technical decision was made. Do not read the full ADR directory for routine implementation tasks — consult `specs/` instead. ADRs are context, not instructions.
