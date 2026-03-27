---
summary: "Index of third-party skill collections. These are read-only — do not modify files in this directory."
---

# External Skills

Third-party skill collections integrated into the workspace. These files are **read-only** and must not be modified.

## Collections

| Collection | Contents | README |
|-----------|----------|--------|
| `anthropics/` | 16 Anthropic-provided skills: canvas-design, brand-guidelines, algorithmic-art, doc-coauthoring, docx, frontend-design, internal-comms, mcp-builder, pdf, pptx, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder, webapp-testing, xlsx | See `anthropics/skills/` for individual SKILL.md files |
| `rezvani-claude-skills/` | Multi-domain Claude skills organized by team: c-level-advisor, engineering-team, marketing-skill, product-team, project-management, ra-qm-team | See `rezvani-claude-skills/README.md` |
| `blader-humanizer/` | Humanizer skill (v2.1.1): detects and rewrites 24 AI writing patterns in agent-produced text. Based on Wikipedia's WikiProject AI Cleanup. | See `blader-humanizer/SKILL.md` |

## Usage

- Browse this index to find relevant external skills
- Read individual SKILL.md files within each collection for usage details
- External skills can be referenced as dependencies (e.g., `/_external/anthropics/skills/docx`)
- Do **not** modify, rename, or restructure files in this directory
