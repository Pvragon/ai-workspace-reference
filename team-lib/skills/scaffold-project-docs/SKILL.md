---
template: skill-definition
version: 1.0.0
summary: "Bootstraps the standard docs/ structure (specs, adrs, reference, archive, .tmp) in new projects. Run when setting up a new project repository."
created: 2026-02-08
last_updated: 2026-02-08
maintainer: pvragon
---

# Skill: Scaffold Project Docs

## When to Use

Use this skill when initializing a new project in `projects/` that needs the standard documentation structure. This ensures every project follows the same docs/ convention with trust boundaries, mutability levels, and agent guidance.

## Prerequisites

- Target must be a directory inside `projects/`
- Python 3.10+

## Steps

### 1. Run the scaffolding script

```bash
python ~/ai-workspace/team-lib/executions/scaffold_project_docs.py <project_path> --name "Project Name"
```

If the project already has a `docs/` directory and you want to replace it:

```bash
python ~/ai-workspace/team-lib/executions/scaffold_project_docs.py <project_path> --name "Project Name" --force
```

### 2. Post-scaffolding checklist

After running the script, customize the generated files for the specific project:

- [ ] Update `docs/README.md` — add any project-specific documentation sections
- [ ] Update `docs/specs/architecture/README.md` — add the contents table as architecture docs are created
- [ ] Update `docs/specs/features/README.md` — adjust scope list for project-specific module names
- [ ] Update `docs/reference/README.md` — list the third-party services this project integrates with
- [ ] Add initial architecture spec if available
- [ ] Add initial ADR if a key technology decision has been made

## Structure Created

```
docs/
├── README.md                  # Trust boundary guide + agent reading priority
├── specs/
│   ├── README.md
│   ├── architecture/          # System-level specs (immutable after review)
│   │   └── README.md
│   ├── features/              # Feature specs (semi-permanent)
│   │   └── README.md
│   └── reviews/               # Stakeholder spec reviews (immutable)
│       └── README.md
├── adrs/                      # Architecture Decision Records (immutable)
│   ├── README.md
│   └── template.md
├── context/                   # Business context: stakeholder preferences, constraints (living)
│   └── README.md
├── reference/                 # Third-party docs (immutable by us)
│   └── README.md
├── archive/                   # Historical documents (do not use)
│   └── README.md
└── .tmp/                      # Working documents (transient)
    └── .gitkeep
```

## Notes

- The `{PROJECT_NAME}` placeholder is replaced with the `--name` argument (or the directory name if omitted)
- Template source lives at `team-lib/context/indexed/templates/docs-structure/`
