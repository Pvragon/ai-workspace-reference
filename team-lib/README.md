# Pvragon AI Library

**The shared standard library for agentic development.**

This repository is the **team-lib** layer of the Pvragon AI Workspace. It provides the shared tooling, context, directives, and skills that enable consistent, high-quality agent performance across the team.

---

## Quick Start

### [**Start Here: Getting Started Guide (Windows)**](GETTING_STARTED.md)
*Follow this guide to set up your environment from zero to fully functional.*

### [**Getting Started (macOS)**](GETTING_STARTED_MAC.md)
*Mac-specific setup instructions.*

### [**Operating Manual: Workspace Reference**](context/indexed/workspace-reference.md)
*The definitive guide to the workspace topology, layers, and usage rules.*

### [**Interactive Intro: The AI Workspace**](https://prez.prgn.ai/pvragon/ai-workspace-onboarding.html)
*A visual walkthrough of the workspace architecture — opens in any browser.*

---

## Functional Stack

A high-level overview of the standard library components:

| Layer | Directory | Purpose |
|-------|-----------|---------|
| **Directives** | `directives/` | High-level instructions and behavioral rules (SOPs) |
| **Context** | `context/` | Team knowledge base (Global + Indexed packs) |
| **Personas** | `personas/` | Team-approved agent identities |
| **Skills** | `skills/` | Shared capability modules and tools |
| **Executions** | `executions/` | Deterministic scripts for reliable automation |
| **Harnesses** | `harnesses/` | Test frameworks and evaluation suites |
| **Registry** | `registry/` | Manifests cataloging available resources |
| **Logs** | `logs/` | Team execution audits |

## Directory Structure

```
team-lib/
├── _admin/             # Bootstrap, validation, and setup scripts
├── directives/         # Behavioral rules (SOPs)
├── context/            # Knowledge base
│   ├── global/         # Always-on context
│   └── indexed/        # On-demand context packs
├── personas/           # Agent configurations
├── skills/             # Capability modules (Tools)
├── executions/         # Scripts (Actions)
├── harnesses/          # Testing frameworks
├── registry/           # Resource manifests (YAML)
└── logs/               # Execution logs
```

## Governance & Standards

**This library is governed by strict quality controls.**
Before contributing, you **must** read the [**Team Library Governance Directive**](directives/team-library-governance.md).

**Key Rules:**
1.  **No Personal Code:** If it has your name or hardcoded home path, it doesn't belong here.
2.  **Pull Request Required:** Direct pushes to `main` are forbidden.
3.  **Strict Naming:** `kebab-case` for files, `snake_case` for python.

## How to Contribute

1.  **Create** resources in the appropriate directory (e.g., new SOP in `directives/`).
2.  **Register** new resources in the relevant `registry/` manifest.
3.  **Test** using `harnesses/` before deployment.
4.  **Submit** a Pull Request for review.
