# registry

## Purpose
Manifests cataloging team resources. Each YAML file is the single source of truth for its corresponding directory's file listing.

## What Belongs Here
- `workspace.yaml`: Workspace topology, rules, and execution signatures
- `directives.yaml`: Team directives (`directives/`)
- `skills.yaml`: Team skills (`skills/`)
- `personas.yaml`: Team personas (`personas/`)
- `executions.yaml`: Execution scripts (`executions/`)
- `context.yaml`: Indexed context files (`context/indexed/`)
- `context-packs.yaml`: Context package bundles

## What Does NOT Belong Here
- Actual resource files
- Runtime data

## File Naming Conventions
- `<resource-type>.yaml`

## How Agents Should Use This Folder
Query to discover available team resources. When adding, renaming, or deleting files in a registered directory, update the corresponding YAML file here.
