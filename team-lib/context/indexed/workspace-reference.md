---
template: workspace-reference
version: 1.6.0
summary: "Canonical architectural reference for the Pvragon AI Workspace: 4-layer hierarchy, directory conventions, functional stack (including integrations/ for CLIs, MCPs, and remote execution interfaces), agent identity system, registry strategy, governance, and project docs structure. Load when an agent needs to understand where something belongs or how the system is structured."
created: 2026-01-15
last_updated: 2026-03-27
maintainer: pvragon
---

# workspace-reference.md — Pvragon Comprehensive AI Workspace

> This is the authoritative reference for the 4-layer workspace architecture (personal / team-lib / my-lib / projects), the DOE pattern, registry-driven execution, and directory conventions. It is designed for on-demand loading, not always-on context. Agents needing to understand where something belongs or how the system works should load this file.

### Table of Contents

1. [Purpose](#1-purpose)
2. [Origin Frameworks](#2-origin-frameworks-as-implemented)
3. [Core Design Principles](#3-core-design-principles)
4. [The Four-Layer Functional Hierarchy](#4-the-four-layer-functional-hierarchy)
5. [Workspace Directory Map](#5-workspace-directory-map)
6. [The Functional Stack](#6-the-functional-stack-conceptual)
7. [Registry Bridge Strategy](#7-registry-bridge-strategy)
8. [Operational Modes](#8-operational-modes-signposts)
9. [Editor Lenses](#9-editor-lenses)
10. [Governance Models](#10-governance-models)
11. [Summary](#11-summary)

---

## 1. Purpose

The **Pvragon Comprehensive AI Workspace** is an opinionated operating system for **agentic development** and **agentic automation**.

Its goals are to:

* Eliminate context amnesia in long-running AI work
* Reduce LLM stochasticity through clear separation of concerns
* Enable private experimentation without fragmenting shared systems
* Provide deterministic, auditable agent behavior
* Create a consistent developer experience across all types of work

The system is intentionally built on **plain files and folders**, so it works across IDEs (VS Code), Obsidian (semantic navigation), Git (system of record), and AI agents (deterministic file readers and tool callers).

---

## 2. Origin Frameworks (as implemented)

### Directive–Orchestration–Execution (DOE)

Work is separated into three concerns:

* **Directives (What):** Natural-language instructions defining intent, constraints, and success criteria
* **Orchestration (Who):** The agent's reasoning loop that routes work and handles control flow
* **Execution (How):** Deterministic scripts and tools that perform the actual work

Reliability comes from pushing repeatable steps into executions while keeping intent readable.

---

### Four-Tier Memory Hierarchy

The workspace treats memory as a layered system with different lifetimes and loading strategies:

| Tier | Lifetime | Examples | Mechanism |
|------|----------|----------|-----------|
| **Long-term** | Persistent, versioned | Indexed context files (`*/context/indexed/`), identity.md, team-lib global context | Git-backed, registry-driven, progressive disclosure — loaded on-demand via index lookup |
| **Mid-term** | Cross-session, curated | Agent memory topic files (MEMORY.md index), lessons-learned | Agent memory system — survives across conversations, pruned by distillation |
| **Near-term** | Within-initiative | `.tmp/` working files, project plans, intermediate deliverables, current-state.md | Filesystem — cleared when the initiative completes |
| **Session** | Single conversation | Everything actively loaded in the agent's context window | Volatile — subject to auto-compaction, lost when the session ends |

**Design principles:**

* **Progressive disclosure governs loading.** Agents start with a minimal hot set (identity, memory index, current state) and pull in additional context only when the index signals relevance. This keeps the context window focused regardless of how large the total corpus grows.
* **Each tier has a different maintenance cadence.** Long-term context is updated via PR (team) or direct push (personal). Mid-term memory is curated during session debriefs. Near-term artifacts are ephemeral by design. Session memory is managed automatically by the agent runtime.
* **Vendor-independent storage.** Agent identity and memory are stored in a git-backed repo (`agents/<agent-name>/`) rather than inside vendor-specific directories (e.g., `~/.claude/`). Vendor tooling accesses the data via symlinks, keeping the canonical data version-controlled and portable. See [Section 4.5](#45-agents--agent-identity--memory) for details.

---

### Spec-Driven Development (SDD)

* Specs define the *definition of done*
* Agents are evaluated against specs, not conversational quality
* Specs live next to the code they govern

---

### Personas & Skills

* **Personas:** stable identities and behavioral constraints
* **Skills:** reusable capability bundles (prompt + tooling contract)

---

## 3. Core Design Principles

1. **Functional topology over ownership** — directories are organized by what they do.
2. **Strict dependency direction** — foundational layers load first; higher layers consume them.
3. **One standard library, many extensions** — shared capabilities are canonical; users extend privately.
4. **Registry-driven execution** — agents do not guess paths or scan heuristically.
5. **Deterministic work boundaries** — agent behavior is inferred from location-based constitutions.
6. **Plain files, no magic** — Obsidian is a lens; Git is the source of truth.

---

## 4. The Four-Layer Functional Hierarchy

Dependencies flow **downward only**.

| Layer | Directory             | Role                                                | Git            |
| ----: | --------------------- | --------------------------------------------------- | -------------- |
|     — | `agents/`          | Agent identity & memory (cross-cutting)             | Private repo(s)|
|     0 | `personal/`        | Local machine overrides                             | No Git         |
|     1 | `team-lib/` | System Standard Library (shared OS)                 | Team repo      |
|     2 | `my-lib/` | User Extension Library (personal automations/tools) | Private repo   |
|     3 | `projects/`       | Active Development Factory (projects)               | Multiple repos |

**Rule:** Projects never live in libraries.

### 4.1 Layer 0 — `personal/` (Local Overrides)

The **second brain layer**. This folder is local-only, never versioned, and never shared. It serves two primary functions:

**Secrets & Configuration**
* Machine-specific `.env` files and API keys
* Local preferences that override shared defaults
* Credentials that must never enter version control

**Personal Knowledge Base**
* `notes/` — Integrates with Obsidian or any AI-enabled note-taking system as your private knowledge repository
* `scratch/` — Temporary working space for experiments and drafts
* `preferences/` — Local tool configurations and overrides

This layer enables the "AI-assisted second brain" pattern: your personal notes, thoughts, and private context live here and can be referenced by agents when working in your workspace—without ever being shared with teammates or committed to Git.

### 4.2 Layer 1 — `team-lib/` (System Standard Library)

The **shared operating system** for agentic work. Everything here is canonical and team-owned.

* **Source:** `pvragon-ai-library` repo.
* **Protocol:** Do not push experimental code here. All changes require a Pull Request.
* **Directives, personas, skills, executions** — Shared automation primitives
* **Harnesses** — Standardized orchestration patterns
* **Context sources** — Team knowledge base (global always-on + indexed on-demand)
* **Registry** — Absolute-path manifest for tool resolution

Changes here affect all team members. Treat it like a shared library: stable, documented, reviewed.

### 4.3 Layer 2 — `my-lib/` (User Extension Library)

Your **personal extensions** to the shared library. Same structure as `team-lib/`, but privately versioned.

* **Source:** Your personal repo (e.g., `your-username/private-ai-library`).
* **Protocol:** **Push here while working.** Use this space to develop and test new automations.
* **Graduation:** Once mature, move to `team-lib` via PR.
* Override or extend team-provided automations
* Experiment with new skills before proposing them to the team
* Store personal productivity tools that don't belong in the shared library
* Track future plans and paused projects in `backlog/`
* Keep historical records of completed work in `archive/`
* Back up machine configs (bashrc, dotfiles) in `config/` for Git versioning

This layer loads *after* `team-lib/`, so your definitions can override team defaults when needed.

### 4.4 Layer 3 — `projects/` (Active Development Factory)

The **workbench** where real work happens. Each subdirectory is an independent project with its own Git repository. Projects consume from the libraries above but never define reusable automations — those belong in `my-lib/` or `team-lib/`.

Each project follows a standard `docs/` structure with trust boundaries, mutability rules, and naming conventions. See **[Project Documentation Structure](project-docs-standard.md)** for the complete guide. Use `team-lib/executions/scaffold_project_docs.py` to bootstrap the standard structure for new projects.

### 4.5 `agents/` — Agent Identity & Memory

A **cross-cutting concern** that sits alongside the four layers, not within them. Each agent that operates in the workspace has a dedicated subdirectory here.

```text
agents/
└── rowan-anicca/           ← Private repo per agent
    ├── identity.md          ← Name, pronouns, defaults
    ├── memory/              ← Consolidated topic memories
    │   ├── MEMORY.md        ← Index (auto-loaded on cold-start)
    │   └── *.md             ← Individual topic files
    └── adapters/
        └── claude/          ← Vendor-specific symlink adapter
            └── link.sh      ← Creates/refreshes symlinks
```

**Key design decisions:**

* **Vendor-independent** — Identity and memory live in Git, not inside `~/.claude/` or any vendor directory. Vendor tooling accesses the data via symlinks managed by adapter scripts.
* **Consolidated memory** — All vendor project directories (regardless of launch `cwd`) symlink to the same `memory/` directory. One agent, one memory pool.
* **Git-backed** — Every memory change is version-controlled and pushed to a private remote. Provides backup, audit trail, and rollback capability.
* **Adapter pattern** — Each vendor integration lives in `adapters/<vendor>/` with a `link.sh` that creates the necessary symlinks. Adding support for a new vendor means adding a new adapter, not restructuring memory.

**Maintenance:** The `session-debrief` skill (`my-lib/skills/session-debrief/`) runs `link.sh` at the end of each session to catch any new vendor project directories and commits/pushes changes to the agent repo.

---

## 5. Workspace Directory Map

```text
~/ai-workspace/
├── agents/                   # Cross-cutting — agent identity & memory
│   └── rowan-anicca/         # Private repo per agent
│       ├── identity.md
│       ├── memory/            # Consolidated memories (symlinked from vendor dirs)
│       └── adapters/claude/   # Vendor-specific symlink adapter
│
├── personal/                 # Layer 0 — local overrides
│   ├── notes/
│   ├── preferences/
│   ├── scratch/
│   └── secrets/
│
├── team-lib/          # Layer 1 — shared standard library
│   ├── _admin/                  # bootstrap & validation scripts
│   ├── context/
│   │   ├── global/
│   │   └── indexed/
│   ├── directives/
│   ├── executions/
│   ├── harnesses/
│   ├── integrations/              # bridges to external services
│   │   ├── apps-script/           # remote execution (Google Apps Script via clasp)
│   │   ├── clickup-cli/           # CLI (ClickUp API via Restish)
│   │   └── gws-cli/               # CLI (Google Workspace via @googleworkspace/cli)
│   ├── logs/
│   ├── personas/
│   ├── registry/
│   │   ├── workspace.yaml       # workspace topology & rules
│   │   ├── directives.yaml      # directives manifest
│   │   ├── skills.yaml          # skills manifest
│   │   ├── personas.yaml        # personas manifest
│   │   ├── executions.yaml      # executions manifest
│   │   ├── integrations.yaml    # integrations manifest
│   │   └── context.yaml         # indexed context manifest
│   └── skills/
│       └── _external/           # Third-party skills (e.g. Anthropic)
│
├── my-lib/                       # Layer 2 — personal extensions
│   ├── archive/                  # completed/retired work
│   ├── backlog/                  # planned/paused initiatives
│   ├── config/                   # machine config backups
│   ├── context/                  # personal knowledge base
│   ├── directives/               # personal automation SOPs
│   ├── executions/               # personal scripts/tools
│   ├── harnesses/                # personal orchestration patterns
│   ├── logs/                     # run logs and audit trails
│   ├── personas/                 # personal agent identities
│   ├── registry/                 # local tool/skill manifests
│   ├── runtime/                  # temp files and deliverables
│   └── skills/                   # personal capability bundles
│
└── projects/                # Layer 3 — all projects
    └── my-app/              # Each project is an independent git repo
        ├── docs/            # See project-docs-standard.md
        │   ├── specs/
        │   │   ├── architecture/
        │   │   ├── features/
        │   │   └── reviews/
        │   ├── adrs/
        │   ├── planning/
        │   ├── context/
        │   ├── reference/
        │   ├── archive/
        │   └── .tmp/
        └── src/
```

---

## 6. The Functional Stack (Conceptual)

Agentic work follows this conceptual stack. Each layer has a distinct responsibility:

| Layer | Directory | Role |
|-------|-----------|------|
| **Directives** (What) | `*/directives/` | Natural-language instructions defining intent, constraints, and success criteria — the "contract" between human and agent |
| **Context** (Memory) | `*/context/`, `projects/*/docs/context/` | Persistent knowledge agents load to remain coherent. `global/` is always-on; `indexed/` is on-demand via registry |
| **Harnesses** (Engine) | `*/harnesses/` | Orchestration wrappers that configure the agent's session: persona, skills, tools, exit conditions — the "main()" for a workflow |
| **Personas** (Driver) | `*/personas/` | Stable identities and behavioral constraints — communication style, risk tolerance, domain expertise |
| **Skills** (Technique) | `*/skills/` | Reusable capability bundles (prompt + tooling contract). Modular and composable — agents load multiple skills per session |
| **Executions** (Tool) | `*/executions/` | Deterministic scripts that perform actual work. Idempotent, testable, with required comment-block frontmatter. See [execution-standard.md](execution-standard.md) |
| **Integrations** (Bridge) | `*/integrations/` | Bridges to external services. Skills and executions consume integrations; they don't call external services directly |
| **Specs** (Target) | `projects/*/docs/specs/` | The definition of done. Agents are evaluated against specs, not conversational quality |

**Notable conventions:**

* The **humanizer** skill (`skills/_external/blader-humanizer/SKILL.md`) is a mandatory quality gate for all human-facing deliverables. It detects and rewrites 24 common AI writing patterns sourced from Wikipedia's WikiProject AI Cleanup.
* **Integrations** come in three flavors: **CLIs** (local binaries like `gws`, `restish`), **MCPs** (server processes over Model Context Protocol like Playwright, Baserow), and **remote execution interfaces** (your code on external infrastructure like Apps Script via `clasp`, n8n, GitHub Actions). Each has an `INTEGRATION.md` and is registered in `registry/integrations.yaml`.
* All execution scripts must include comment-block frontmatter (`# ---` ... `# ---`) with `template`, `version`, `summary`, `created`, `last_updated`, and `maintainer` fields.

### 6.1 Context-Efficient Execution

When agents orchestrate multi-step workflows by making sequential tool calls, every intermediate result flows through the agent's context window. This wastes tokens, increases latency, and can push earlier context out of the window.

**The solution: Code as Orchestration.** Instead of calling Tool A → reading result → calling Tool B → reading result, the agent writes a *single script* that calls A and B internally, processes the intermediate data locally, and returns only a concise summary.

All execution scripts expose a `run()` function that returns structured data. Agents can `import` and chain multiple scripts in a single `run_command` call. The `if __name__ == "__main__"` block remains for human CLI usage.

```python
# One tool call instead of three — summary only in context
from executions.scaffold_project_docs import run as scaffold
result = scaffold(target="/path/to/project", name="My Project")
# result = {"status": "ok", "files_created": 12}  — one line vs. 50+
```

> **Reference:** [execution-standard.md](execution-standard.md) for the full pattern specification.

---

## 7. Registry Bridge Strategy

Shared tools are consumed via **absolute paths**, not symlinks.

* Global registry: Loaded via manifest from `team-lib/registry/workspace.yaml`
* Per-type registries: `registry/directives.yaml`, `registry/skills.yaml`, `registry/personas.yaml`, `registry/executions.yaml`, `registry/context.yaml`
* Project doc registries: `projects/*/docs/registry.yaml` (indexes project documentation for on-demand loading)

Registry YAML files are the single source of truth for file manifests. Each registered directory (`skills/`, `directives/`, `personas/`, `executions/`, `context/indexed/`) has a corresponding `registry/*.yaml` file. The `index.md` files in each directory serve as GitHub-friendly folder READMEs and link to the registry — they do not contain file listings.

### Load order

1. Shared registry (Layer 1)
2. Private overrides (Layer 2)
3. Project-local docs (Layer 3)

Agents resolve tools via the registry and execute them directly.

---

## 8. Operational Modes (Signposts)

Agent behavior is inferred from location-based constitutions (`CLAUDE.md`).

| Mode        | Location            | Behavior                                      |
| ----------- | ------------------- | --------------------------------------------- |
| STOP        | Workspace root      | Refuse execution; route user to correct layer |
| Automation  | Libraries (`team-lib/`, `my-lib/`) | DOE automator; focus on reliability           |
| Engineering | `projects/*`    | Builder mode; read specs/context, write code  |

---

## 9. Editor Lenses

Editors and IDEs are navigation lenses — Git remains the source of truth. See **[Editor Setup Guide](editor-setup-guide.md)** for detailed configuration instructions for Obsidian and VS Code multi-root workspaces.

---

## 10. Governance Models

To prevent entropy and "junk drawer" accumulation, the workspace enforces strict governance.

### 10.1 Team Library (`team-lib`)
**Strict Rule:** Shared Infrastructure Only.
*   **Directive:** [team-library-governance.md](../../directives/team-library-governance.md)
*   **Enforcement:** Automated by `graduate_files.py` and GitHub Branch Protection.
*   **Protocol:**
    *   **No Direct Pushes:** All changes must go through Pull Request.
    *   **No Personal Scoping:** Scripts must be generic (no `user-` prefixes).
    *   **Definition of Done:** Required frontmatter, docstrings, and tests.

### 10.2 Private Library (`my-lib`)
**Loose Rule:** User Sandbox.
*   Maximize velocity.
*   Use `directives/` and `runtime/` freely.
*   **Constraint:** Do not commit secrets or large binaries.

### 10.3 Projects (`projects/`)
**Engineering Rule:** Repo-specific standards.
*   Follow the style guide of the specific project.
*   Enforce via CI/CD pipelines defined in the project repo.

---

## 11. Summary

This functional topology:

* Separates libraries from active work
* Keeps all projects in one consistent workbench
* Uses registries instead of symlinks
* Uses signposts to prevent scope errors
* Stores agent identity and memory in vendor-independent, git-backed repos

The result is a workspace that is understandable to humans, predictable for agents, and scalable across an organization.

**Companion documents:**
* **[Project Documentation Structure](project-docs-standard.md)** — trust boundaries, mutability rules, naming conventions for project `docs/` directories
* **[Editor Setup Guide](editor-setup-guide.md)** — Obsidian and VS Code configuration for the workspace
