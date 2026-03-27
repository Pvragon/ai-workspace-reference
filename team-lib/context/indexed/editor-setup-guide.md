---
template: context-indexed
version: 1.0.0
summary: "Editor and IDE setup guidance for the Pvragon AI Workspace: Obsidian vault configuration, VS Code multi-root workspace setup, and recommended roots. Extracted from workspace-reference.md Section 9."
created: 2026-03-27
last_updated: 2026-03-27
maintainer: pvragon
see_also: workspace-reference.md
---

# Editor Setup Guide

> **Parent document:** [workspace-reference.md](workspace-reference.md) — canonical architectural reference for the AI Workspace.

Editors and IDEs are **navigation and development lenses** — Git remains the source of truth. Each tool offers a different view into the same underlying file system.

---

## Obsidian

Obsidian provides **semantic navigation** for the knowledge layer.

* Open `~/ai-workspace/` as a single vault to enable cross-linking (Context ↔ Backlog ↔ Personal)
* **Crucial Configuration:** Add these patterns to **Settings → Files & Links → Excluded files** to remove engineering noise:
    * `**/src/`
    * `**/node_modules/`
    * `**/_admin/`
    * `**/.git/`
* Use `index.md` files as directory landing pages
* Leverage backlinks and graph view to explore context relationships
* Git remains authoritative — Obsidian is read/write but not canonical

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
