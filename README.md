# Pvragon AI Workspace — Reference Architecture

An opinionated operating system for **agentic development** and **agentic automation**, built on plain files and folders.

This repository is a public reference implementation of the workspace architecture described in [`team-lib/context/indexed/workspace-reference.md`](team-lib/context/indexed/workspace-reference.md). It demonstrates the patterns, conventions, and directory structure without any proprietary content.

## What This Is

The Pvragon AI Workspace solves four problems that make AI agents unreliable over long-running work:

1. **Context amnesia** — agents forget everything between sessions
2. **Stochastic behavior** — agents do the same task differently each time
3. **No identity** — agents have no persistent context about your business
4. **Compounding errors** — without guardrails, small mistakes snowball

The solution is a four-layer hierarchy with clear boundaries, registry-driven execution, and a two-axis tiered memory system with ranked retrieval.

## Architecture at a Glance

```
~/ai-workspace/
├── agents/        # Cross-cutting — agent identity & memory (git-backed)
├── personal/      # Layer 0 — local secrets, notes, overrides (no git)
├── team-lib/      # Layer 1 — shared standard library (team repo)
├── my-lib/        # Layer 2 — personal extensions (private repo)
└── projects/      # Layer 3 — active development (multiple repos)
```

**Dependencies flow downward only.** Projects consume from libraries. Libraries never depend on projects.

## Core Patterns

### DOE (Directive–Orchestration–Execution)
Every task separates **what** (directives) from **who decides** (the AI reasoning loop) from **how** (deterministic scripts). Reliability comes from pushing repeatable steps into tested executions.

### Memory: two orthogonal axes

Memory is layered on **two independent axes** that cross rather than stack — every memory has a coordinate on both.

**Axis A — Retention** (how long does this last?). Spans *all* workspace artifacts, not just memory:

| Tier | Lifetime | Example |
|------|----------|---------|
| **Durable** | Persistent, versioned | Indexed context files, identity, lenses |
| **Curated** | Cross-session, actively maintained | Agent memory topics (MEMORY.md index) |
| **Initiative** | Within-initiative | .tmp files, project plans |
| **Session** | Single conversation | Active context window |

**Axis B — Memory tiers** (what kind of memory is this, and what does promotion cost?). Memory only:

| Tier | Function | Lives in |
|------|----------|----------|
| **T0 Working** | Active attention; dies with the session | Session context |
| **T1 Episodic** | Recent events with provenance | `memory/short-term/YYMMDD-*.md` |
| **T2 Semantic** | Decontextualized patterns | `memory/<type>_<topic>.md` topic files |
| **T3 Situational lens** | Rules injected when narrow triggers match | `lenses/*.md` + a PreToolUse hook |
| **T4 Always-on lens** | Shapes interpretation of every input | `AGENTS.md`, `CLAUDE.md`, `identity.md` |

A T1 fact is *Durable* on Axis A (git-backed, never deleted) but *episodic* on Axis B. Promotion into T3/T4 is **always a deliberate human action** — auto-promotion would make any single error a permanent interpretive distortion.

**Retrieval is ranked, and forgetting is real but lossless.** T2 memories carry `access_count` / `last_accessed` / `stability` frontmatter and are scored `(access_count + 1) * exp(-days / stability) + 0.6 * importance`, where `stability` grows with *spaced* reinforcement. The index is regenerated into a character-budgeted **Hot** band (auto-loaded) plus a **Cold** band, with the low-relevance tail rolled off to an archive index. Files are never deleted — only index visibility shifts, so a rolled-off memory is one read away and reading it re-warms it.

### Registry-Driven Execution
Agents resolve tools via YAML manifests, not by guessing paths. Load order: team registry → personal overrides → project docs.

### Vendor-Independent Agent Identity
Agent identity and memory live in a git-backed repo with symlink adapters per vendor. Switch AI providers without restructuring memory.

## Key Documents

| Document | Purpose |
|----------|---------|
| [`workspace-reference.md`](team-lib/context/indexed/workspace-reference.md) | Canonical architectural reference |
| [`project-docs-standard.md`](team-lib/context/indexed/project-docs-standard.md) | Project documentation structure |
| [`editor-setup-guide.md`](team-lib/context/indexed/editor-setup-guide.md) | VS Code and Obsidian configuration |
| [`execution-standard.md`](team-lib/context/indexed/execution-standard.md) | Script pattern specification |
| [`nick-saraev-doe-framework.md`](team-lib/context/indexed/nick-saraev-doe-framework.md) | DOE framework theory |

## Interactive Presentations

- [How Rowan Works](https://prez.prgn.ai/pvragon/how-rowan-works) — the infrastructure behind a persistent AI collaborator, one concept per slide
- [AI Workspace Onboarding](https://prez.prgn.ai/pvragon/ai-workspace-onboarding.html) — visual walkthrough of the architecture
- [The Pvragon AI Workspace](https://prez.prgn.ai/pvragon/ai-workspace-intro.html) — the original intro deck

## Getting Started

**Quick start** (Linux/WSL — see [GETTING_STARTED.md](team-lib/GETTING_STARTED.md), the canonical blank-computer-to-named-agent guide, or [the Mac guide](team-lib/GETTING_STARTED_MAC.md) for macOS Phase 1):

```bash
cd ~
git clone https://github.com/Pvragon/ai-workspace-reference.git
sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh      # system deps
~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh        # workspace scaffold + team-lib + my-lib + toolchain
```

Then name and create your agent — the choose-name ceremony (see [GETTING_STARTED.md, Phase 7](team-lib/GETTING_STARTED.md#phase-7-name-your-agent-)) — starting from the example:

```bash
cp -r ~/ai-workspace-reference/agents/example-agent ~/ai-workspace/agents/<agent-name>
```

## Harness Compatibility (honest status)

The **architecture** is vendor-agnostic by design — directives, executions, context, memory, and identity are plain files any agent can read. The **adapter layer** is where vendor coupling lives, and today it is Claude-Code-first:

| Piece | Status |
|-------|--------|
| `AGENTS.md` instruction files | ✅ Agnostic — Codex reads `AGENTS.md` natively; `CLAUDE.md`/`GEMINI.md` are mirrors |
| Directives + executions (DOE layers 1 & 3) | ✅ Agnostic — Markdown + Python |
| Agent identity & memory files | ✅ Agnostic in format — plain Markdown |
| Memory auto-loading | ⚠️ `agents/*/adapters/` ships only `claude/link.sh` (symlinks into `~/.claude/`). Other harnesses need their own adapter, or load memory via an `AGENTS.md` pointer |
| Skills (`SKILL.md` + slash commands) | ⚠️ Auto-invocation is a Claude Code feature. Other harnesses can follow SKILL.md files as ordinary SOPs |
| `session-debrief` pre/postflight scripts | ⚠️ Read Claude Code session transcripts (`~/.claude/projects/*.jsonl`) — Claude-only today |
| MCP toolchain provisioning | ⚠️ `configure_toolchain.sh` writes Claude Code + Gemini CLI configs; no Codex config yet |

Adapters for other harnesses are welcome as PRs — the `adapters/` directory exists precisely so vendor glue stays isolated from identity and memory.

## What's Included vs. What's Not

This is a **reference implementation**, not a production deployment. It includes:

- The full directory structure and conventions
- All shared skills, directives, executions, and integration docs
- Example agent identity with memory patterns
- Registry manifests showing the resolution system
- A subset of personal library tools (generic ones only)

It does **not** include:

- Client or company-specific content (brand guidelines, business data)
- Private agent memories or identity
- Active project codebases
- Secrets, API keys, or credentials

## License

MIT
