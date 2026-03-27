---
name: Example Agent
pronouns: they/them
created: 2026-01-15
---

# Identity

This is an example agent identity file. Each AI agent that operates in the workspace gets a dedicated directory here with:

- **identity.md** — Name, pronouns, communication defaults
- **memory/** — Consolidated topic memories (symlinked from vendor directories)
- **adapters/** — Vendor-specific symlink scripts

The agent's identity and memory are stored in Git, not inside any vendor-specific directory. Vendor tooling accesses this data via symlinks managed by adapter scripts.
