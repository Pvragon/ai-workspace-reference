# Feature Specifications

> **Semi-permanent** — These documents represent the current state of feature-level blueprints. They evolve during development, then stabilize.

Feature-level specifications covering individual capabilities, modules, and implementation plans for {PROJECT_NAME}.

## Contents

*Feature specifications will be added as features move from planning to implementation.*

## Scope

Documents in this folder describe:
- Individual feature implementation plans
- Module-level design
- Data models specific to a feature
- Integration patterns for specific third-party services
- UI/UX specifications for specific workflows

## Agent Guidance

Read the relevant feature spec when you are implementing or modifying a specific capability. Feature specs must conform to the constraints defined in `specs/architecture/` — if a conflict exists, architecture takes precedence unless an ADR documents the exception.

## Contributing

When creating a feature spec:
- Use `YYMMDD-descriptive-title.md` naming
- Start with problem statement and goals
- Reference the architecture spec where relevant
- Include data model changes, API surface, and UI impact
- Document alternatives considered
- Move superseded versions to `docs/archive/`
