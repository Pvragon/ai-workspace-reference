# {PROJECT_NAME} Documentation

This directory contains all documentation for {PROJECT_NAME}, organized by purpose and trust level.

## Documentation Structure

### [`specs/`](./specs/) — Implementation Guidance
The authoritative source for what we are building. Agents and developers should read this subtree for any implementation task.

- **[`specs/architecture/`](./specs/architecture/)** — System-level specifications (immutable after acceptance)
- **[`specs/features/`](./specs/features/)** — Feature-level specifications (evolve during development, stabilize after)
- **[`specs/reviews/`](./specs/reviews/)** — Stakeholder reviews of spec documents. **Not for implementation use.** Reviews are deliberation records, not specs — do not treat them as building guidance. Reference only to clarify questions about specific design decisions or intent.

### [`adrs/`](./adrs/) — Decision Records (Immutable)
Architecture Decision Records documenting what we decided and why. Read when you need rationale behind a choice, not for implementation guidance.

### [`reference/`](./reference/) — Third-Party Documentation (Immutable by us)
Documentation for external APIs, services, and integrations used by {PROJECT_NAME}. We don't modify these, but they may become outdated if third parties change.

### [`archive/`](./archive/) — Historical (Do not use for implementation)
Outdated documents preserved for historical context. Never read these for current implementation guidance.

### [`planning/`](./planning/) — Project Planning (Optional, Semi-permanent)
Investment summaries, resourcing scenarios, role descriptions, risk registers, kickoff agendas, and timelines. Read for project structure and team context. Stabilizes after project launch; updated only if team composition or scope changes significantly. Create this folder when the project has formal planning artifacts.

### [`context/`](./context/) — Business Context (Living)
Stakeholder constraints, product direction, and decision-making principles that inform architecture and feature decisions. Not implementation guidance — read this when evaluating trade-offs or preparing recommendations for leadership review.

### [`.tmp/`](./.tmp/) — Working Documents (Not authoritative)
Scratch files, review findings, working analyses, and in-progress documents. Useful for context but not authoritative specs. Files here use `YYMMDD-` prefix naming.

---

## Agent Guidance

When working on an implementation task:

1. **Read** the relevant documents under `docs/specs/` — this is your implementation guidance
2. **Consult** `docs/adrs/` only when you need to understand why a decision was made
3. **Consult** `docs/reference/` only when you need third-party API details
4. **Do not read** `docs/archive/` unless explicitly directed to
5. **Treat** `docs/.tmp/` as supporting context, not authoritative specs
6. **Consult** `docs/context/` when evaluating trade-offs that involve stakeholder preferences or business constraints
7. **Consult** `docs/planning/` (if it exists) when you need team structure, resourcing, or project timeline context

### Trust Boundary

Everything inside `specs/` is "this is what we are building." Everything outside `specs/` is supporting context. This distinction determines what an agent should load into its context window for development work.

---

## Mutability Legend

| Status | Meaning | Folder |
|--------|---------|--------|
| **Immutable** | Should not be modified after acceptance | `adrs/`, `specs/reviews/` |
| **Immutable (system-level)** | Stable after architecture review; changes require review | `specs/architecture/` |
| **Semi-permanent** | Updated during active development, then stabilizes | `specs/features/` |
| **Immutable (by us)** | We don't modify, but external sources may change | `reference/` |
| **Historical** | Outdated documents preserved for reference | `archive/` |
| **Transient** | Working documents, not authoritative | `.tmp/` |
| **Living** | Updated as stakeholder context evolves; not specs | `context/` |
| **Semi-permanent** | Stabilizes after project launch; updated if team/scope changes | `planning/` |

---

## Contributing

| Document Type | Location | Naming Convention |
|--------------|----------|-------------------|
| System architecture, infrastructure, security | `specs/architecture/` | `YYMMDD-descriptive-title.md` |
| Feature specs, implementation plans | `specs/features/` | `YYMMDD-descriptive-title.md` |
| Architecture decisions | `adrs/` | `YYMMDD-short-title.md` (accepted); `proposed-YYMMDD-…` / `rejected-YYMMDD-…` (other states) |
| Stakeholder spec reviews | `specs/reviews/` | `YYMMDD-role-high-level-review.md` |
| Third-party API docs | `reference/` | Organized by service |
| Superseded or outdated docs | `archive/` | Preserve original filename |
| Working notes, analyses, scratch | `.tmp/` | `YYMMDD-descriptive-title.md` |
| Project planning (roles, risk, resourcing, timelines) | `planning/` | `YYMMDD-descriptive-title.md` |
| Stakeholder preferences, product constraints, business context | `context/` | `YYMMDD-descriptive-title.md` |
