---
template: convention-standard
version: 1.0.0
created: 2026-02-18
last_updated: 2026-02-18
maintainer: pvragon
summary: "Defines the progressive disclosure convention for agent-consumable files: summary frontmatter field requirements, index aggregation pattern, and summary writing guidelines. Read when creating or updating any agent-consumable file."
---

# Progressive Disclosure Convention

> This convention improves context window efficiency by adding a `summary` frontmatter field to all agent-consumable files and evolving index files into aggregated discovery tables. Agents can scan summaries to assess file relevance before committing to a full read. The only file receiving an exec summary blockquote is `workspace-reference.md` (464 lines); all other files rely on the frontmatter field alone.

## The `summary` Frontmatter Field

All agent-consumable files over 15 lines MUST include a `summary` field in their YAML frontmatter. This is a required field alongside `template`, `version`, `created`, `last_updated`, and `maintainer`.

```yaml
---
template: [type]
version: [semver]
summary: "What this file is and when an agent needs it."
created: [YYYY-MM-DD]
last_updated: [YYYY-MM-DD]
maintainer: [team/person]
---
```

### Writing Guidelines

The `summary` field answers exactly one question: **"Should I open this file?"**

- 1-2 sentences maximum
- Name the concrete thing (not "this document covers..." but "Defines the execution script standard...")
- State the when/why ("Load when building new execution scripts.")
- Tool-agnostic (valid for Claude, Gemini, and future AI tools)
- Update the summary when bumping the file version

### Good Examples

- `"Canonical reference for workspace architecture, directory conventions, and agent operating rules. Load when an agent needs to understand where something belongs."`
- `"Procedure for graduating files from my-lib to team-lib. Follow when a local tool is ready for team-wide use."`
- `"Pvragon brand guidelines: colors, typography, logo usage, and document formatting. Required before generating any branded deliverable."`

### Bad Examples

- `"This document is about the workspace."` (too vague, no decision signal)
- `"Important information about various topics."` (useless)
- `"A comprehensive guide that covers many important topics related to the Pvragon AI Workspace architecture and its various components."` (verbose, no decision signal)

## Reference Files vs. Instruction Files

Both file types get the `summary` field, but agents use it differently.

**Reference files** (context/indexed/, business overviews, framework definitions): Agents use `summary` to decide whether to open the file. Partial reads are legitimate.

**Instruction files** (AGENTS.md, SKILL.md, directives, personas): Agents use `summary` for discovery ("which skill do I need?"), but once opened, they read the file in full. Every word matters. The `summary` never substitutes for reading the file.

## Index File Aggregation Pattern

Index files (`index.md` in each directory) should aggregate the `summary` fields from their sibling files into a discovery table:

```markdown
## Files

| File | Summary |
|------|---------|
| `filename.md` | [summary from that file's frontmatter] |
| `filename2.md` | [summary from that file's frontmatter] |
```

This lets agents scan one file to assess all siblings without opening any of them.

## Exempt Files

The following do not need a `summary` field:

- Files under 15 lines (e.g., CLAUDE.md/GEMINI.md stubs, workspace root AGENTS.md)
- Third-party files in `_external/` directories (must not be modified)
- CHANGELOG.md, README.md in project roots
- Registry YAML files (use comment-block summaries instead)

## Registry YAML Convention

YAML registry files use a comment-block summary at the top of the file:

```yaml
# summary: One-sentence description of what this registry covers.
# last_updated: YYYY-MM-DD
# entries: N
```

## Future Expansion

If practice reveals specific large files (200+ lines) that would benefit from an exec summary blockquote after the H1 title, they can be added individually. The current exception is `workspace-reference.md` only.
