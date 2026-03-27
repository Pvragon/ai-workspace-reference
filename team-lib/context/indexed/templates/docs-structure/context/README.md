# Context

> **Living** — Updated as stakeholder context evolves. Not implementation guidance.

This directory contains business context, stakeholder constraints, and product direction that inform architecture and feature decisions. Documents here explain the *why behind the why* — the business reasoning that sits above ADRs and specs.

## What Belongs Here

- Stakeholder preferences and decision-making principles (CEO, CTO, investors)
- Product constraints and non-negotiables (compliance, market, operational)
- Business context that agents and reviewers should understand when evaluating trade-offs

## What Does NOT Belong Here

- Implementation guidance → `specs/`
- Architecture decisions (already made) → `adrs/`
- Third-party API documentation → `reference/`
- Working notes and scratch → `.tmp/`

## Contents

| Document | Subject |
|----------|---------|
| *None yet* | |

## Agent Guidance

Read context documents when:
- Evaluating architectural trade-offs that require understanding stakeholder priorities
- Preparing recommendations for leadership or council review
- Resolving ambiguity about which of two valid approaches better fits this project

Do not read context documents for routine implementation tasks — consult `specs/` instead.

## Naming Convention

`YYMMDD-descriptive-title.md` — same as `.tmp/`, but these documents are durable, not transient.
