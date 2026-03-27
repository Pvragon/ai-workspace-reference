# Specifications

> The authoritative source for what we are building. Read this subtree for any implementation task.

This directory contains all implementation specifications for {PROJECT_NAME}, organized by scope:

- **[`architecture/`](./architecture/)** — System-level specifications (immutable after acceptance)
- **[`features/`](./features/)** — Feature-level specifications (evolve during development, stabilize after)
- **[`reviews/`](./reviews/)** — Stakeholder reviews of spec documents. May result in direct spec changes, ADR proposals, or both. Immutable once the council session they informed is complete.

## Agent Guidance

Start here when working on any implementation task. Architecture specs define system-wide constraints; feature specs define individual capabilities. If a conflict exists between the two, architecture takes precedence unless an ADR documents the exception.
