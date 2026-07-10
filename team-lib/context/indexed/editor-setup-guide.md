---
template: context-indexed
version: 2.0.0
summary: "Editor and IDE setup guidance for the Pvragon AI Workspace: Obsidian vault configuration, VS Code multi-root workspace setup, and recommended roots. Extracted from workspace-reference.md Section 9. v2.0.0 (2026-06-11): vault root moved from workspace root to personal/ — the workspace grew to ~900k files, which Obsidian cannot exclude from scanning; cross-silo linking now via gitignored symlinks."
created: 2026-03-27
last_updated: 2026-06-11
maintainer: pvragon
see_also: workspace-reference.md
---

# Editor Setup Guide

> **Parent document:** [workspace-reference.md](workspace-reference.md) — canonical architectural reference for the AI Workspace.

Editors and IDEs are **navigation and development lenses** — Git remains the source of truth. Each tool offers a different view into the same underlying file system.

---

## Obsidian

Obsidian provides **semantic navigation** for the knowledge layer.

**Vault root: `~/ai-workspace/personal/`** — NOT the workspace root.

> **Why not the workspace root?** Earlier guidance (v1.x) recommended opening `~/ai-workspace/` as a single vault. The workspace has since grown to ~900k files (data stores, node_modules, worktrees), of which under 2% are notes-shaped. Obsidian's *Excluded files* setting only hides entries from search and link suggestions — it does **not** prevent the initial vault scan or file watching, so a root vault now means indexing ~900k files on every launch (dramatically worse if Obsidian runs on the Windows side against a WSL filesystem). `personal/` is notes-shaped by construction (see workspace-reference §4.1), so it makes a clean, fast vault.

* Open `~/ai-workspace/personal/` as the vault
* **Cross-silo linking via symlinks:** Obsidian follows symlinked folders, so other knowledge silos join the vault graph through gitignored symlinks inside `personal/` whose names mirror the real workspace paths — e.g. `personal/agents/<agent-name> -> ../agents/<agent-name>/`, `personal/my-lib -> ../my-lib/`, and per-project `personal/projects/<name>/docs` links. Two scan rules make this work: Obsidian skips dot-NAMED entries unconditionally, but follows symlinks through to their targets — so an un-dotted link name (e.g. `agents -> .agents/`) is what exposes a project's dot-named agent control plane. Each symlink target stays canonical in its own repo; gitignore the link names and define the tree in an idempotent setup script (the links are never committed — the script is their canonical definition).
    * *Caveat:* Obsidian's file watcher can be slow to notice changes made outside Obsidian inside symlinked folders — a vault refresh picks them up. Acceptable for a lens.
* **Commit `.obsidian/`** to the personal repo so vault configuration is version-controlled
* Use `index.md` files as directory landing pages
* Leverage backlinks and graph view to explore context relationships
* Git remains authoritative — Obsidian is read/write but not canonical; `personal/` content never reaches team repos

---

## VS Code (Multi-Root Workspace)

For agentic coding, use the **multi-root workspace** configuration rather than opening `~/ai-workspace/` as a single folder project.

**Why multi-root is preferable:**

* **Scoped agent context** — Each workspace root gets its own `CLAUDE.md` constitution, allowing agents to behave differently in `team-lib/` vs a project directory
* **Cleaner file navigation** — Each root appears as a top-level entry in the Explorer, reducing nesting depth
* **Independent Git tracking** — VS Code recognizes each root's Git status separately
* **Focused indexing** — Language services and search scope to relevant roots

**Setup:**

1. Open any folder in VS Code
2. Use **File → Add Folder to Workspace** to add additional roots
3. Save as `~/ai-workspace/pvragon-workspace.code-workspace`
4. Thereafter, open the `.code-workspace` file directly

**Recommended roots:**

| Root | Purpose |
|------|---------|
| `personal/` | Local overrides and notes |
| `team-lib/` | Shared standard library |
| `my-lib/` | Personal extensions |
| `agents/<name>/` | Agent identity & memory (private repo) |
| `projects/<name>/` | Active project (add one per project) |
