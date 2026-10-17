# team-lib: the shared library

`team-lib` is Layer 1 of the AI Workspace: the procedures, scripts, skills, and reference documents that every agent and every person on the workspace shares. Your personal tools live in `my-lib/` and your projects in `projects/`. Both build on this library, and it depends on neither.

Install it with the workspace setup rather than on its own. [`GETTING_STARTED.md`](GETTING_STARTED.md) covers setting up alone and joining a team that already runs a shared library. macOS users start Phase 1 from [`GETTING_STARTED_MAC.md`](GETTING_STARTED_MAC.md).

## What the library lets an agent do

| Capability | Where it lives |
|---|---|
| Follow a written procedure and run tested scripts for the repeatable steps | `directives/`, `executions/` |
| Find any skill on the machine, including ones its prompt never listed | `skills/find-skill/` |
| Keep a name, an identity, and a ranked memory across sessions | `skills/choose-name/`, `_admin/install_memory.sh`, [`context/indexed/memory-system.md`](context/indexed/memory-system.md) |
| Consolidate and tidy its memory overnight | `executions/dream_cycle.py`, `skills/dream/` |
| End a session cleanly and continue in a fresh one | `skills/session-debrief/`, `skills/handoff/` |
| Rebuild every open session after a reboot | `skills/store-sessions/`, `skills/resume-sessions/` |
| See and message the other sessions running on the same machine | `executions/session_activity.py`, `skills/who/`, `directives/multi-agent-coordination.md` |
| Look up tools in an index that is generated from the tools themselves | `registry/`, `executions/build_registry.py`, `executions/build_index.py` |
| Get versions bumped automatically at push time | `executions/version_gate.py` |
| Publish a scrubbed public copy of the library | `executions/publish_public_reference.py` |

The workspace layout and the rules for each layer are in [`context/indexed/workspace-reference.md`](context/indexed/workspace-reference.md).

## How the library is organized

```
team-lib/
├── _admin/       # setup, update, validation, and memory install scripts
├── directives/   # standard operating procedures (SOPs) in Markdown
├── executions/   # deterministic Python scripts
├── skills/       # reusable capabilities, one folder with a SKILL.md each
├── context/
│   ├── global/   # context every agent loads
│   └── indexed/  # reference documents loaded on demand
├── personas/     # shared agent personas
├── integrations/ # command-line wrappers and docs for outside services
├── apps/         # small tools a person runs directly, such as terminal panes
├── harnesses/    # tests and container install checks
├── registry/     # generated manifests of everything above
└── config/       # maps and vocabularies the generators read
```

Directives say what to do and why. Executions do the work, and each exposes a `run()` function so they can be chained (see [`context/indexed/execution-standard.md`](context/indexed/execution-standard.md)). The agent sits between them: it reads the directive, picks the scripts, and handles errors. This split is the directive, orchestration, and execution (DOE) pattern.

The integrations, such as the Google Workspace CLI (`gws`) and ClickUp, are optional. A workspace runs without any of them.

## Indexes are generated, so edit the file

Every directive, execution, skill, and context file starts with YAML frontmatter that includes `version` and a one-line `summary`. The manifests in `registry/` and the contents table in each folder's `index.md` are generated from that frontmatter by `executions/build_registry.py` and `executions/build_index.py`. A hand edit to a manifest is overwritten on the next build. To change what the index says, change the file's frontmatter.

Skills also declare a `listing` level and a `category`. `executions/build_skill_overrides.py` turns those into the harness's skill listing settings and checks them against the listing budget, and `executions/install_skill_overrides.py` merges the result into the harness settings after a dry run.

## Versions are set when you push

Commit as often as you like. When you push, `executions/version_gate.py` runs as a pre-push hook: it bumps the patch version of every file whose body changed, stamps `last_updated`, regenerates the indexes, and commits that so the push carries it. Put `[minor]`, `[major]`, or `[no-version]` in a commit message to override. `python3 executions/version_gate.py --self-check` confirms the hook is wired.

## Checking that it works

- `_admin/validate.sh` checks the folder layout, git connections, toolchain, and secrets scaffolding. Setup runs it at the end, and you can run it any time.
- `harnesses/` holds tests for the version gate, the registry gate, and layer drift, plus container tests that run the public install and the memory install from a clean machine.
- `executions/layer_drift_scan.py` compares content hashes between `my-lib` and `team-lib` to catch a capability that exists in both layers and has drifted apart.

## Contributing to the library

Read [`directives/team-library-governance.md`](directives/team-library-governance.md) before you add anything. In short:

1. Keep personal details out. A file with your name or a hardcoded home path belongs in `my-lib`.
2. Name files in `kebab-case` and Python modules in `snake_case`.
3. Give every new file its frontmatter, including `summary` and `version`. The registry and index pick it up from there.
4. Graduate a proven capability from `my-lib` by moving it, so only one copy stays live. The `graduate` skill (`skills/graduate/`) and [`directives/graduate-to-team-library.md`](directives/graduate-to-team-library.md) walk through it.
5. Run the relevant tests in `harnesses/`, then open a pull request. The governance directive does not allow direct pushes to `main`.
