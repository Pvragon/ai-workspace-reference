---
template: workspace-reference
version: 1.11.1
summary: "Canonical architectural reference for the Pvragon AI Workspace: 4-layer hierarchy, directory conventions, functional stack (including integrations/ for CLIs, MCPs, and remote execution interfaces), agent identity system, registry strategy, governance, project docs structure, live-infrastructure documentation pattern, and T3/T4 memory split (situational hook-triggered lens vs always-on baked-in lens). v1.10.0 (2026-06-11): personal/ is now a private per-user repo and the Obsidian vault root (notes-shaped content only); added projects/personal monorepo for personal-domain micro-projects with ideation→build→standalone lifecycle."
created: 2026-01-15
last_updated: 2026-08-01
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
5b. [Live Infrastructure (Active Systems)](#5b-live-infrastructure-active-systems)
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

### Memory Hierarchy — Two Orthogonal Axes

Memory in this workspace is layered along **two independent axes**. Both are useful; they compose.

#### Axis A — Retention (spans all workspace artifacts, not just memory)

| Tier | Lifetime | Examples | Mechanism |
|------|----------|----------|-----------|
| **Durable** | Persistent, versioned | Indexed context files (`*/context/indexed/`), identity.md, situational lenses, team-lib global context | Git-backed, registry-driven, progressive disclosure — loaded on-demand via index lookup |
| **Curated** | Cross-session, actively maintained | Agent memory topic files (MEMORY.md index), lessons-learned | Agent memory system — survives across conversations. Curated at debrief; ranked and rolled off by the two-strength policy (`rerank_memory_index.py`). **Nothing is deleted** — only index visibility shifts |
| **Initiative** | Within-initiative | `.tmp/` working files, project plans, intermediate deliverables, current-state.md | Filesystem — cleared when the initiative completes |
| **Session** | Single conversation | Everything actively loaded in the agent's context window | Volatile — lost when the session ends. Auto-compaction is **disabled by policy** (it rebuilds the prompt cache at ~1.25x input rate); sessions are rotated deliberately via `/session-debrief` + `/handoff`, re-establishing from disk |

#### Axis B — Memory Type (added 2026-04-30, neuroscience-grounded)

Borrowed from human memory research and validated against prior art (Generative Agents 2023; MemGPT/Letta). Full architecture notes live in the maintaining agent's memory (topic: memory-architecture-layers).

| Tier | Brain analogue | Function | Where (current Rowan implementation) |
|------|----------------|----------|--------------------------------------|
| **T0 Working** | Phonological loop / visuospatial sketchpad | Active attention, current task | In-session conversation context |
| **T1 Short-term retrievable (episodic)** | Hippocampal episodic memory | Recent specific events, with provenance ("when did I learn X?") | `agents/<agent>/memory/short-term/YYMMDD-facts.md` + `YYMMDD-residue.md`; verbatim transcripts in `agents/<agent>/transcripts/` |
| **T2 Long-term retrievable (semantic)** | Cortical semantic memory (anterior temporal) | Decontextualized patterns, entity-property facts ("what's true of X?") | `agents/<agent>/memory/<topic>.md` topic files; future Graphiti graph |
| **T3 Situational lens** | Domain-specific schemas | Lens-strength rules with **narrow trigger conditions**; activated at the moment they apply | `agents/<agent>/lenses/<topic>.md` with self-declared triggers; injected via PreToolUse hook (`inject_lens.py`) when matching tool fires |
| **T4 Core / always-on lens** | Schemas, scripts, worldview | The LENS for everything — shapes interpretation of every input | `CLAUDE.md`, `AGENTS.md`, `identity.md`, skill base prompts |

**Retrieval policy (added 2026-07-12, substrate-agnostic).** Which T2 memories are *accessible* is
governed by a two-strength model (Bjork & Bjork 1992): `score = (access_count + 1) *
exp(-days_since_last_access / stability) + 0.6 * importance`, where `stability` is a per-file decay
time-constant that **grows with spaced reinforcement** (14d base → 365d cap, x1.6 per reinforcement
gated at 20h so cramming doesn't count). A `Read`/`Edit`/`Write` of a topic file reinforces it
(`update_memory_access.py`, PreToolUse hook); `rerank_memory_index.py` regenerates MEMORY.md into a
char-budgeted **Hot** band (auto-loaded) + **Cold** band, rolling the low-relevance tail to
`MEMORY-archive.md`. A nightly **dream cycle** (`dream_cycle.py`, 03:47 cron) runs the deterministic
grooming and cues one reflective wake (`/dream` — meditation + T1→T2 consolidation). Full design:
`my-lib/backlog/260712-memory-system-framework.md`.

**Key property:** T2 is *abstraction, not summary* — semantic facts persist after every contributing episodic memory has aged out. T1, T2, T3, T4 fail independently (the neurodegeneration argument), so they live in separate file trees with separate update disciplines.

**T3 vs T4:** T3 is loaded *only when triggers match* — pay per-fire cost when relevant. T4 is loaded *every session* regardless of context — pay the always-on context cost. Both are lens-strength (authoritative when loaded). Use T3 for domain-scoped rules whose triggers are crisp (specific tool + path patterns); use T4 for workspace-wide rules that apply universally. See `backlog/260430-lenses-hook-triggered-injection.md` for the trigger-discipline + integration spec.

(Naming history: v1.8.0 used T3a/T3b for what are now T4/T3. v1.9.0 renumbered for monotonic graduation ordering.)

#### How the two axes compose

A T1 episodic fact in `memory/short-term/` is **long-term** on Axis A (git-backed, never deleted) but **episodic** on Axis B (date-keyed, with provenance). A T3 lens in AGENTS.md is **long-term** on Axis A *and* **core** on Axis B. A current session's working memory is **session** on Axis A and **T0** on Axis B. The two axes answer different questions: Axis A answers "how long does this last?"; Axis B answers "what kind of memory is this?" They **cross rather than stack** — every memory has a coordinate on both.

Axis A deliberately says nothing about *kind*: a lens and a static context file are both **Durable**, and T1 and T2 are both **Curated**, because on this axis they have identical lifetimes. Everything about episodic-vs-semantic, and about what promotion costs, lives on Axis B.

**Design principles** (apply to both axes):

* **Progressive disclosure governs loading.** Agents start with a minimal hot set (identity, memory index, current state, recent T1 episodic) and pull in additional context only when the index signals relevance. This keeps the context window focused regardless of how large the total corpus grows.
* **Each tier has a different maintenance cadence.** Durable context (Axis A) is updated via PR (team) or direct push (personal). Curated memory is maintained during session debriefs. T2 → T3 promotion (Axis B) is **always deliberate human action** — never automatic — because T3 is the lens and errors there compound.
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
|     0 | `personal/`        | Personal knowledge vault (second brain) + secrets   | Private repo (secrets gitignored) |
|     1 | `team-lib/` | System Standard Library (shared OS)                 | Team repo      |
|     2 | `my-lib/` | User Extension Library (personal automations/tools) | Private repo   |
|     3 | `projects/`       | Active Development Factory (projects)               | Multiple repos |

**Rule:** Projects never live in libraries.

### 4.1 Layer 0 — `personal/` (Personal Knowledge Vault)

The **second brain layer**. Backed by a **private per-user repo** (e.g. `<user>/personal-ai-workspace`) — never shared with the team, with `secrets/` excluded from version control via `.gitignore`. It serves two primary functions:

**Secrets & Configuration**
* `secrets/` — Machine-specific `.env` files, API keys, OAuth credentials. **Gitignored — never committed**, even though the surrounding folder is a repo.
* `preferences/` — Local tool configurations and overrides

**Personal Knowledge Base (the Obsidian vault)**
* `notes/` — Private knowledge repository
* `scratch/` — Temporary working space for experiments and drafts
* `backlog/` — Personal-life initiatives (markdown)
* `personas/` + `registry/` — Personal-life-domain personas (legal, health, family) that don't belong in `my-lib/` or `team-lib/`
* `agents/<agent-name>` — Gitignored symlink to the agent's repo so identity and topic memories join the vault graph (vault link names mirror real workspace paths)

**Content rule: notes-shaped only.** Everything here should be prose/markdown (plus small attachments). Scripts belong in `my-lib/executions/` or `my-lib/config/`; build artifacts belong in `projects/` (see the `projects/personal` monorepo in Section 4.4). This keeps the layer valid as an Obsidian vault root — see the [Editor Setup Guide](editor-setup-guide.md).

This layer enables the "AI-assisted second brain" pattern: your personal notes, thoughts, and private context live here and can be referenced by agents when working in your workspace—without ever being shared with teammates.

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

**`projects/personal/` — personal-domain micro-projects monorepo.** One private repo (e.g. `<user>/personal-projects`), one subfolder per personal build too small to warrant a standalone repo. Personal projects follow a three-stage lifecycle:

1. **Ideation** → `personal/` (prose-only design notes, inside the Obsidian vault)
2. **Active build** → `projects/personal/<name>/` — promoted the moment a project accumulates *build artifacts* (code, design files, renders, datasets) rather than just prose
3. **Standalone** → `projects/<name>/` as its own repo, once it gains CI, deploys, collaborators, or an independent release cadence

Work-domain micro-tools do **not** go here — those belong in `my-lib/`.

Each project follows a standard `docs/` structure with trust boundaries, mutability rules, and naming conventions. See **[Project Documentation Structure](project-docs-standard.md)** for the complete guide. Use `team-lib/executions/scaffold_project_docs.py` to bootstrap the standard structure for new projects.

### 4.5 `agents/` — Agent Identity & Memory

A **cross-cutting concern** that sits alongside the four layers, not within them. Each agent that operates in the workspace has a dedicated subdirectory here.

```text
agents/
└── <agent-name>/           ← Private repo per agent (e.g. your-agent)
    ├── identity.md          ← Name, pronouns, defaults. ALSO the marker that
    │                          identifies a directory as an agent home.
    ├── memory/              ← Consolidated topic memories
    │   ├── MEMORY.md        ← Index (auto-loaded on cold-start)
    │   ├── current-state.md ← Derived index over T2 project files
    │   ├── short-term/      ← T1 episodic: YYMMDD-facts.md + YYMMDD-residue.md
    │   ├── dream-journal/   ← Residue from reflective wakes
    │   └── *.md             ← Individual topic files
    ├── handoffs/            ← Session-rotation briefs (/handoff writes,
    │   └── .pending-enrichment/   /session-debrief reads back to append its addendum)
    ├── lenses/              ← T3 situational lenses, hook-injected on trigger match
    ├── meditations/         ← Contemplation-object library
    ├── reflections/         ← Reflective-wake output
    ├── transcripts/         ← Extracted session transcripts (~97% smaller than JSONL)
    ├── system-state/        ← Auto-dumped snapshots: crontab, hooks, settings, MCP
    ├── runtime/state/       ← Scheduler/hook scratch; inside the home so it travels
    └── adapters/
        └── claude/          ← Vendor-specific symlink adapter
            └── link.sh      ← Creates/refreshes symlinks
```

> **Resolve these paths, never hardcode them.** `team-lib/executions/agent_paths.py` is the single
> source of truth: `agent_home()`, `memory_dir()`, `shortterm_dir()`, `journal_dir()`,
> `lenses_dir()`, `meditations_dir()`, `handoffs_dir()`, `state_dir()`. It locates the agent home by
> the `identity.md` marker and **raises rather than guessing** when zero or several candidates
> exist, because writing one agent's memory into another's is unrecoverable. It exists because
> eleven scripts had each hardcoded one agent's directory — fine on one machine, fatal for reuse.
> Skills that cannot import Python read the same values from its CLI
> (`python3 agent_paths.py [--json]`).
>
> This tree drifted badly once: it listed three children while the home actually had eleven, so
> `handoffs/`, `lenses/`, `transcripts/` and `system-state/` were load-bearing but undocumented
> (corrected 2026-07-30). If you add a directory here, add it to `agent_paths.py` too — the
> resolver is executable and therefore the copy that cannot silently rot.

**Key design decisions:**

* **Vendor-independent** — Identity and memory live in Git, not inside `~/.claude/` or any vendor directory. Vendor tooling accesses the data via symlinks managed by adapter scripts.
* **Consolidated memory** — All vendor project directories (regardless of launch `cwd`) symlink to the same `memory/` directory. One agent, one memory pool.
* **Git-backed** — Every memory change is version-controlled and pushed to a private remote. Provides backup, audit trail, and rollback capability.
* **Adapter pattern** — Each vendor integration lives in `adapters/<vendor>/` with a `link.sh` that creates the necessary symlinks. Adding support for a new vendor means adding a new adapter, not restructuring memory.

**Maintenance:** The `session-debrief` skill (`my-lib/skills/session-debrief/`) runs `link.sh` at the end of each session to catch any new vendor project directories and commits/pushes changes to the agent repo.

---

### 4.6 The Publication Layer — `ai-workspace-reference` (public)

A fourth link in the chain, and the one most easily forgotten because nobody works in it:
the **public reference repo** (`Pvragon/ai-workspace-reference`), a generated mirror of
`team-lib` with everything proprietary removed. It is never edited by hand. It is produced by
`executions/publish_public_reference.py` from the contract in `registry/mirror.yaml`.

### 4.7 How the layers relate — the promotion chain

```
my-lib  ──graduate──▶  team-lib  ──publish──▶  ai-workspace-reference
(mine)                 (ours)                  (anyone's)
```

**One direction, and each hop is a FILTER, not a copy.** That distinction is the thing people
get wrong, so it is stated twice:

- **`team-lib` is NOT a mirror of `my-lib`.** It holds only what has *graduated*. Measured
  2026-08-01: 591 tracked files in `my-lib` against 487 in `team-lib`, with **59 ungraduated
  items** (executions, skills, context, directives, personas) that are correctly personal.
  A drift scan reporting ungraduated items is reporting normality, not debt. The verifiable
  claim is narrower and stronger: *everything `mirror.yaml` declares mirrored must agree*.
- **The public repo IS a derived mirror of `team-lib`** — a total function over the contract.
  Measured the same day: 487 → 358 files through 8 published trees, 18 exclude globs, 4
  excluded root files (each carrying a written reason), 13 scrub terms and 28 generalization
  rules. Everything published is current; everything absent is absent on purpose.

**What belongs where**

| | `my-lib` | `team-lib` | public |
|---|---|---|---|
| Personal experiments, half-built tools | ✅ born here | only once proven | — |
| Client/project-specific work | ✅ | ❌ (belongs in `projects/`) | ❌ |
| Generic capability others would use | graduate it out | ✅ | ✅ |
| Operator identity, real names, emails | ✅ | ✅ | ❌ generalized to placeholders |
| Client names, client infrastructure | ✅ | ✅ | ❌ scrub-blocked; publication REFUSES the file |
| Third-party skill packs (`skills/_external/`) | ❌ | ✅ as submodules | ❌ fetched from source, never redistributed |
| `mirror.yaml` itself | — | ✅ | ❌ it contains the blocklist, so it names every client |
| Secrets | `personal/secrets/` only | ❌ | ❌ |

**Graduation is a MOVE, never a copy.** Two live copies have no owner for the diff; both stay
individually valid while the comparison silently rots. See
[graduate-to-team-library.md](../../directives/graduate-to-team-library.md) and Operating
Principle #15. The same rule governs the publish hop: the public repo carries no hand-edits, so
there is nothing there to drift.

**The contract is machine-readable, and it is authoritative.** `registry/mirror.yaml` declares
the mirror mapping, the publication trees, the exclusions (each with a written reason), the
scrub blocklist and the generalization rules. When this document and that file disagree, the
file wins — it is what the tools execute. Note the deliberate asymmetry: `mirror.yaml` is
itself excluded from publication, because a blocklist enumerates exactly what it protects.

**How it is kept true**

| Concern | Mechanism | When |
|---|---|---|
| Layers disagree on a mirrored item | `executions/layer_drift_scan.py` (content hashes, not versions) | nightly + on demand |
| Public layer fell behind | `executions/publish_gate.py` | on every `team-lib` push, + nightly floor |
| Versions stale at the publish boundary | `executions/version_gate.py` | PreToolUse on `git push` |
| Third-party packs unpinned | `_admin/update_external_pack_pins.sh --check` | nightly |
| A stranger cannot actually install it | `harnesses/public_workspace_container_test.sh` | before a release |
| The whole chain, end to end | **skill: `update-ai-workspace-children`** | before a release, or when asked |

## 5. Workspace Directory Map

```text
~/ai-workspace/
├── agents/                   # Cross-cutting — agent identity & memory
│   └── <agent-name>/         # Private repo per agent
│       ├── identity.md
│       ├── memory/            # Consolidated memories (symlinked from vendor dirs)
│       └── adapters/claude/   # Vendor-specific symlink adapter
│
├── personal/                 # Layer 0 — personal knowledge vault (private repo; Obsidian vault root)
│   ├── backlog/              # personal-life initiatives
│   ├── agents/<name> -> ../agents/<name>/   # gitignored symlink (vault graph)
│   ├── notes/
│   ├── personas/             # personal-life-domain personas
│   ├── preferences/
│   ├── registry/
│   ├── scratch/
│   └── secrets/              # gitignored — never committed
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
    ├── personal/            # personal-domain micro-projects monorepo (private repo; see §4.4)
    │   └── <name>/          # one subfolder per micro-project, each with index.md
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

## 5b. Live Infrastructure (Active Systems)

The directory map (Section 5) shows *what files exist*; this section names the pattern for *what runs against them* — cron jobs, hooks (including the lens-injector for T3 situational lenses), background services, and skill-driven automation. **Live infrastructure is user-specific** (each operator has their own cron entries, MCP servers, hook configurations, and lens collection), so the canonical content lives in user space, not team-lib.

### Where live-infrastructure documentation lives

Three layers, by convention:

| Layer | Where | What it holds | Maintenance |
|-------|-------|---------------|-------------|
| **Manual overview** ("the *why*") | `<workspace>/context/indexed/active-systems.md` (e.g., `my-lib/context/indexed/active-systems.md`) | Curated overview of cron jobs, hooks, skill-driven automation, background services, lens collection, and config-sync mechanisms — with purpose, trigger, source script, log location, failure mode | Edited by hand whenever new automation is added; updated at debrief if it drifts |
| **Auto-dumped state** ("the *exact what*") | `agents/<agent>/system-state/` | Deterministic snapshots: `crontab.txt`, `claude-hooks.json`, `claude-settings-public.json`, `installed-mcp-servers.txt` | Refreshed at every debrief by `executions/dump_system_state.py`; auto-staged on agents commit |
| **Situational lenses** (T3) | `agents/<agent>/lenses/<topic>.md` | Lens-strength rules with self-declared triggers; injected via PreToolUse hook when triggers match. See Memory Hierarchy Axis B (T3). | Deliberate human curation; can graduate from feedback memories during T2→T3 audits |

### Why both layers

- The manual overview alone drifts (manual docs always do).
- The auto-dump alone is unreadable (raw configs don't tell you why things exist).
- Together: the overview explains intent; the dump verifies current configuration; git holds the history.

### Discovery

When sitting down to work, check `<workspace>/context/indexed/active-systems.md` first to understand what's running. When something stops working or behaves unexpectedly, compare the dump (`agents/<agent>/system-state/`) against the overview to catch drift. **If they diverge, the dump is the truth and the overview is stale — fix the overview.**

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
