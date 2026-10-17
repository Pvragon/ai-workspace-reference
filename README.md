# AI Workspace

A file-based operating environment for running AI coding agents on long, real work. You clone it, run two setup scripts, and get a folder layout, a shared library of procedures and scripts, and an agent that keeps its identity and memory from one session to the next.

Everything is plain Markdown, YAML, Python, and shell. Nothing here depends on a hosted service, and you can read every rule the agent follows. The workspace is built and used daily with Claude Code, and most of it works with other agent harnesses too (see [which parts work with which harness](#most-of-it-is-harness-neutral-and-the-adapters-say-where-it-is-not)).

Published by Pvragon under the MIT license, for you to deploy and adapt as your own workspace.

## Why you would use it

Agents that run for weeks on the same body of work tend to fail in four ways:

| Problem | What the workspace does about it |
|---|---|
| The agent forgets everything when a session ends | A git-backed memory per agent, ranked and reloaded at the start of each session |
| The same task comes out differently each time | Written procedures for the judgment, tested scripts for the repeatable steps |
| The agent has no lasting sense of who it is or how you work | A named agent identity and standing instructions that load before the first prompt |
| Small mistakes compound across sessions | Generated indexes, a version gate at push, validation scripts, and test harnesses |

If you run one agent occasionally, this is more structure than you need. It pays off when you run agents daily, run several at once, or work as a team. On a team, every member's agent works from the same shared context and the same skills, each member keeps a private memory and private notes, and the agents can message each other directly.

## What the workspace gives you

### Work is split into layers, and dependencies flow one way

```
~/ai-workspace/
├── agents/        # each agent's identity and memory (its own git repo)
├── personal/      # Layer 0: local secrets, notes, and overrides (never committed)
├── team-lib/      # Layer 1: the shared library this repo publishes
├── my-lib/        # Layer 2: your personal extensions (a private repo)
└── projects/      # Layer 3: your project repos
```

Projects use the libraries, and the libraries never depend on projects. A capability starts in `my-lib/` or a project and moves into `team-lib/` once it has proven itself, and the personal copy is removed when it does, so only one version stays live (`team-lib/directives/graduate-to-team-library.md`, `team-lib/skills/graduate/`). The full layout and its rules are in [`workspace-reference.md`](team-lib/context/indexed/workspace-reference.md).

### Procedures are written down, and the repeatable steps are scripts

The workspace follows a directive, orchestration, and execution (DOE) pattern. A directive is a standard operating procedure in Markdown (`team-lib/directives/`). The agent does the orchestration: it reads the directive and decides what to run. Executions are deterministic Python scripts that do the work (`team-lib/executions/`), each with a `run()` entry point so they can be chained. The reasoning is that a language model is probabilistic and most business steps should not be, so the model should choose and the scripts should act. See [`execution-standard.md`](team-lib/context/indexed/execution-standard.md) and [`nick-saraev-doe-framework.md`](team-lib/context/indexed/nick-saraev-doe-framework.md).

### Agents find skills they were never told about

Skills are reusable capabilities, each a folder with a `SKILL.md` (`team-lib/skills/`). A harness can only describe so many skills in its prompt before the list crowds out real context, so most skills are listed by name only or hidden. The `find-skill` skill (`team-lib/skills/find-skill/`) searches every skill on the machine by task or category and prints how to invoke each match. Each skill declares its own listing level and category in its frontmatter, and `team-lib/executions/build_skill_overrides.py` turns those declarations into the harness's skill listing settings while checking the result against the listing budget. `install_skill_overrides.py` merges that output into the harness settings, dry run first.

### Agents remember across sessions

Each agent gets a name, chosen by the agent itself in a short ceremony (`team-lib/skills/choose-name/`), and a home under `agents/<name>/` with its identity and memory. Memory has five tiers, from the live context window through dated session notes and topic files up to standing rules. Promotion into the standing-rule tiers is always a human decision, so one wrong conclusion cannot become permanent on its own.

Topic memories are ranked, and the index the agent loads at startup is regenerated from that ranking (`team-lib/executions/rerank_memory_index.py`). A memory's score rises when it is read and decays with time, more slowly for memories that have been reinforced at spaced intervals, plus a fixed floor for memories marked important. Low-ranked memories drop out of the loaded index, but the files are never deleted, so a forgotten memory is one read away and reading it warms it again.

A nightly job (`team-lib/executions/dream_cycle.py`) runs the cleanup that needs no model: grooming, hygiene checks, and the rerank. It then flags what reflective work is due, such as consolidating recent notes into topic memories, which the `dream` skill performs (`team-lib/skills/dream/`). The full specification, including every constant and the one-command install (`team-lib/_admin/install_memory.sh`), is [`memory-system.md`](team-lib/context/indexed/memory-system.md).

### Long work survives the end of a session

Large sessions get expensive and lose quality, so the workspace ends them on purpose and carries the state forward on disk. `session-debrief` (`team-lib/skills/session-debrief/`) writes what was learned into memory and updates a current-state file. `handoff` (`team-lib/skills/handoff/`) writes a brief, opens a fresh session that reads it and continues, and debriefs the old one. Before a reboot, `store-sessions` snapshots every open session, and `resume-sessions` reopens them afterwards (`team-lib/executions/session_snapshots.py`).

### Parallel sessions know about each other

When several agent sessions work on the same machine, each one records its focus to disk (`team-lib/executions/session_activity.py`). A hook warns a session when a peer is on the same repo and branch, the `who` skill (`team-lib/skills/who/`) shows what every live session is doing, and an asynchronous mailbox lets sessions message each other without interrupting anyone. The rules for when to use each are in `team-lib/directives/multi-agent-coordination.md`.

### A team shares one library, and its agents talk to each other

The workspace is built for a team as much as for one person. Each member runs their own named agent, and every agent loads the same shared library: the directives, skills, executions, and context files in `team-lib/`. When one member proves out a new skill or procedure, it graduates into the library, and every teammate's agent picks it up on the next `team-lib/_admin/update.sh`. So a lesson one agent learns becomes a tool every agent has.

Shared context does not mean shared everything. Each agent's identity and memory live in its own repository under `agents/<name>/`, a member's personal library (`my-lib/`) stays theirs, and `personal/` holds secrets and notes that are never committed. The layer rules in [`workspace-reference.md`](team-lib/context/indexed/workspace-reference.md) decide what is shared and what stays private.

Agents on different machines can also write to each other. `team-lib/integrations/agent-mailbox/agent_mailbox.py` sends directed, asynchronous messages between agents by agent name, over a shared private git repository. Each message is its own file, so two machines can send at the same moment without a merge conflict, and each machine keeps its own record of what it has read. It is the cross-machine counterpart of the same-machine mailbox described above; [`INTEGRATION.md`](team-lib/integrations/agent-mailbox/INTEGRATION.md) covers setup.

### Indexes are generated from the files they describe

Every directive, execution, skill, and context file carries YAML frontmatter with a version and a one-line summary. The registry manifests in `team-lib/registry/` and the contents table of each folder's `index.md` are generated from that frontmatter (`team-lib/executions/build_registry.py`, `build_index.py`), so the index cannot drift from the files for long. Agents use the registries to find tools instead of guessing paths.

### Versions are stamped when work is pushed

`team-lib/executions/version_gate.py` runs as a hook before `git push`. For every versioned file whose body changed without a version change, it bumps the patch version, updates `last_updated`, regenerates the indexes, and commits the result so the push carries it. It never blocks a push. Commit messages can ask for a minor or major bump instead.

### You can publish a public copy without leaking private content

This repository is itself produced by `team-lib/executions/publish_public_reference.py`. It copies the shared library, drops excluded trees, rewrites the operator's identifiers into placeholders, and refuses to write any file that still contains a blocked term. The config that drives it, `registry/mirror.yaml`, is withheld from this copy because its blocklist names the terms it protects, so to publish your own copy you write your own.

### The install checks itself

`team-lib/_admin/validate.sh` checks the folder layout, git connections, toolchain, and secrets scaffolding, and setup runs it at the end. `team-lib/harnesses/` holds tests for the version gate, the registry gate, and layer drift, plus container tests that run the public install and the memory install from scratch.

## Start from a blank machine

You need:

- Linux, or Windows with WSL2 (Windows Subsystem for Linux). macOS works with a different first phase, covered in [`GETTING_STARTED_MAC.md`](team-lib/GETTING_STARTED_MAC.md).
- A GitHub account, for your private `my-lib` and agent repos.
- Access to Claude Code. Other harnesses can use most of the workspace, as the table below shows.

Integrations such as the Google Workspace CLI (`gws`), ClickUp, and Baserow are optional. Nothing in setup requires them.

Then run:

```bash
cd ~
git clone https://github.com/Pvragon/ai-workspace-reference.git
sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh    # system packages
~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh      # builds ~/ai-workspace
```

`setup_workspace.sh` notices it is running from inside this clone and installs `team-lib` from the copy beside it, so you do not need access to any other repository. It then scaffolds `personal/`, `my-lib/`, and `projects/`, installs the toolchain, wires the agent-independent half of memory, and runs validation.

After that:

1. Follow [`GETTING_STARTED.md`](team-lib/GETTING_STARTED.md). It covers keys and logins, your editor, and your first session, with one path for setting up on your own and one for joining a team that already runs a shared library.
2. In your first session, run the naming ceremony (`/choose-name`). It creates `~/ai-workspace/agents/<name>/`. You can look at [`agents/example-agent/`](agents/example-agent/) first to see what an agent home contains.
3. Finish the memory install with `bash ~/ai-workspace/team-lib/_admin/install_memory.sh`. Before the agent has a name it exits with code 2, meaning deferred, which is expected. After naming, it bootstraps memory, registers the hooks, installs the nightly job, and verifies the result.

## Most of it is harness-neutral, and the adapters say where it is not

Directives, executions, context, memory, and identity are plain files any agent can read. Vendor-specific code lives in adapters, and today those adapters are written for Claude Code first.

| Piece | Status |
|---|---|
| `AGENTS.md` instruction files | Works anywhere. Codex reads `AGENTS.md` natively, and `CLAUDE.md` and `GEMINI.md` point at it |
| Directives and executions | Works anywhere: Markdown and Python |
| Agent identity and memory files | Works anywhere: plain Markdown |
| Memory auto-loading | Claude Code only today. `agents/example-agent/adapters/` ships only `claude/link.sh`, which links memory into `~/.claude/`. Other harnesses need their own adapter, or can load memory through a pointer in `AGENTS.md` |
| Skills (`SKILL.md` and slash commands) | Automatic invocation is a Claude Code feature. Other harnesses can follow a `SKILL.md` as an ordinary procedure |
| `session-debrief` preflight and postflight scripts | Claude Code only today. They read Claude Code session transcripts (`~/.claude/projects/*.jsonl`) |
| MCP (Model Context Protocol) server setup | `configure_toolchain.sh` writes configs for Claude Code and Gemini CLI. There is no Codex config yet |

Adapters for other harnesses are welcome as pull requests. The `adapters/` folder exists so that vendor code stays separate from identity and memory. If you want the ideas without the files, [`portable-agent-package/`](portable-agent-package/) describes the same operating model in runtime-neutral terms for an agent to rebuild on any platform.

## What this repository contains, and what it leaves out

It contains:

- The full folder structure and its conventions
- The shared library: skills, directives, executions, context files, integration docs, and small terminal apps (`team-lib/apps/`)
- An example agent home with sample memory (`agents/example-agent/`)
- The generated registry manifests
- A few generic personal-library tools under `my-lib/`, and an example project under `projects/`

It leaves out:

- Brand, client, and business content
- Any real agent's memory or identity
- Working project codebases
- Secrets, API keys, and credentials
- Third-party skill packs, which setup fetches from their own repositories
- The publishing config (`registry/mirror.yaml`). It holds the scrub blocklist, so it names everything the publisher withholds. `team-lib/config/` is included, minus a list of real people's names that one guard script reads.

## Further reading

| Document | What it covers |
|---|---|
| [`workspace-reference.md`](team-lib/context/indexed/workspace-reference.md) | The layout, the layers, and the rules for each |
| [`memory-system.md`](team-lib/context/indexed/memory-system.md) | How agent memory is built, ranked, and maintained |
| [`execution-standard.md`](team-lib/context/indexed/execution-standard.md) | How execution scripts are written |
| [`project-docs-standard.md`](team-lib/context/indexed/project-docs-standard.md) | How project documentation is structured |
| [`editor-setup-guide.md`](team-lib/context/indexed/editor-setup-guide.md) | VS Code and Obsidian setup |
| [`nick-saraev-doe-framework.md`](team-lib/context/indexed/nick-saraev-doe-framework.md) | The theory behind the DOE pattern |

## License

MIT. Published by Pvragon.
