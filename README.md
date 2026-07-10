# Pvragon AI Workspace — Reference Architecture

An opinionated operating system for **agentic development** and **agentic automation**, built on plain files and folders.

This repository is a public reference implementation of the workspace architecture described in [`team-lib/context/indexed/workspace-reference.md`](team-lib/context/indexed/workspace-reference.md). It demonstrates the patterns, conventions, and directory structure without any proprietary content.

## What This Is

The Pvragon AI Workspace solves four problems that make AI agents unreliable over long-running work:

1. **Context amnesia** — agents forget everything between sessions
2. **Stochastic behavior** — agents do the same task differently each time
3. **No identity** — agents have no persistent context about your business
4. **Compounding errors** — without guardrails, small mistakes snowball

The solution is a four-layer hierarchy with clear boundaries, registry-driven execution, and a tiered memory system.

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

### Four-Tier Memory
| Tier | Lifetime | Example |
|------|----------|---------|
| **Long-term** | Persistent, versioned | Indexed context files, identity |
| **Mid-term** | Cross-session, curated | Agent memory topics (MEMORY.md) |
| **Near-term** | Within-initiative | .tmp files, project plans |
| **Session** | Single conversation | Active context window |

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

**Quick start** (Linux/WSL — see [the full guide](team-lib/GETTING_STARTED.md), or [the Mac guide](team-lib/GETTING_STARTED_MAC.md)):

```bash
cd ~
git clone https://github.com/Pvragon/ai-workspace-reference.git
sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh      # system deps
~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh        # workspace scaffold + team-lib + my-lib + toolchain
```

Then create your agent from the example (see [Getting Started, Phase 5](team-lib/GETTING_STARTED.md#phase-5-create-your-agent)):

```bash
cp -r ~/ai-workspace-reference/agents/example-agent ~/ai-workspace/agents/<agent-name>
```

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
