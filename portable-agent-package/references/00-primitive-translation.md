---
template: portable-agent-reference
version: 1.0.0
summary: "Translation table mapping the package's generic primitives (skill, sub-agent, slash invocation, registry, file-based state, hook, scheduler) onto concrete platforms — Claude Code, OpenAI Codex, Cursor, Aider, MCP-only, and in-house harness fallbacks. Read this FIRST if your runtime is not Claude Code so every later reference doc can be mapped to your own primitives without ambiguity."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 00 — Primitive Translation Table

> **Read this BEFORE the other reference docs.** The rest of the package describes patterns in terms of seven generic primitives. This doc tells you what each primitive is called — and what to do if your runtime doesn't have a native version of it.
>
> If you skip this doc, every "skill" / "sub-agent" / "slash command" / "hook" mention later will quietly assume a Claude-Code-shaped runtime. Read this once; substitute the equivalent everywhere downstream.

## How To Use This Table

1. **Find your runtime in the column header.**
2. **For each row, note your runtime's term and the fallback mechanism.**
3. **Re-read the rest of the package with mental substitution.** When AGENTS.md says "spawn a sub-agent," read it as "do whatever your runtime calls **subprocess+isolated-context**" — column-3 of row "sub-agent."
4. **If your runtime has no native version of a primitive, use the fallback column.** The fallback is *always* a path that requires no runtime support — typically a shell script + file state.

## The Translation Table

| Generic Primitive | This Package's Term | Claude Code | OpenAI Codex | Cursor | Aider (CLI) | MCP-only Runtime | In-House Harness Fallback (no runtime support) |
|---|---|---|---|---|---|---|---|
| **Skill** — reusable, named procedure | "Skill" — `skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md`; invoked via `/<name>` | Custom function or "Tool" entry; invoked by name in a chat directive | Custom command in `.cursor/rules/`; invoked by `@command` | A documented prompt in a Markdown file the user pastes | An MCP server tool exposing the procedure | A Markdown file the orchestrator reads and follows step-by-step; "invocation" = `cat skills/<name>.md \| stdin-to-llm` |
| **Sub-agent** — separate, isolated agent invocation that returns a summary | "Sub-agent" via the Task / Agent tool | `Agent` tool with `subagent_type` parameter (Claude Code) | Spawn a second OpenAI API call with a fresh system prompt; pipe output back | Same: spawn a fresh API call from a script | Out-of-process: spawn `aider --message "..." --no-stream` and capture stdout | Spawn another MCP-side LLM call with isolated context | Shell script that invokes a fresh LLM CLI with a self-contained prompt; capture stdout; only return the last line / summary block to the parent |
| **Slash invocation / command** — short verb that triggers a skill | `/<skill-name>` | `/<skill-name>` (built-in) | Magic phrase ("run skill X") matched by the system prompt's instruction set | `@<command>` or palette command | Trigger phrase parsed by a wrapper script | MCP `tool call` by tool name | Bash alias / wrapper script: `myagent <skill-name> <args>` |
| **Registry** — machine-readable manifest of available capabilities | `registry/*.yaml` (skills, directives, executions, etc.) | YAML/JSON read from disk by the orchestrator | YAML/JSON loaded into the system prompt at session start | YAML in `.cursor/` consumed by Cursor's command palette | Markdown index file the user grep's | MCP `list_tools` natively (the protocol *is* the registry) | A single `registry.yaml` the orchestrator `cat`s + parses with `yq` before answering each request |
| **File-based state** — durable state surviving session end | `runtime/<task>/state.json`, `feature_list.json`, etc. | Plain files on disk; runtime-agnostic | Plain files on disk; runtime-agnostic | Plain files on disk; runtime-agnostic | Plain files on disk; runtime-agnostic | Plain files on disk; MCP can read/write them | Plain files on disk — this is the *universal* substrate; every other column should ultimately reduce to this |
| **Hook** — code that runs in response to a runtime event (start, stop, before-tool, after-tool) | "Hook" — declarative trigger in runtime config | `~/.claude/settings.json` `hooks` section (PreToolUse, PostToolUse, Stop, etc.) | OpenAI-side: not native; emulate by wrapping each tool call in your own dispatcher | Cursor-side: `.cursor/rules` partial coverage; otherwise wrap your invocation | Wrapper shell script that intercepts each `aider` call | MCP middleware proxy | A wrapper script around the LLM invocation: pre-call hook = lines before the call; post-call hook = lines after |
| **Scheduler** — recurring or delayed agent runs | `/loop`, `/schedule`, `cron` | `/loop <interval>`, `/schedule`, `ScheduleWakeup` tool | OS cron or systemd timer invoking the OpenAI CLI | OS cron or systemd timer invoking Cursor CLI | OS cron invoking `aider` non-interactively | OS cron invoking the MCP-driven entrypoint | OS cron invoking your wrapper shell script |

## Notes On Specific Primitives

### Skill — when your runtime doesn't have one

A "skill" in this package is just **a structured Markdown procedure file plus its supporting files**. The runtime adds invocation sugar (slash commands, palette entries) but the skill itself is filesystem-portable.

If your runtime has no native skill mechanism, the fallback is:

```
1. Keep skills as `skills/<name>/SKILL.md` + supporting files exactly as documented.
2. The orchestrator reads `registry/skills.yaml` at session start.
3. When the user asks for something matching a skill, the orchestrator
   `cat`s the SKILL.md into its working context and follows the procedure.
4. There is no special invocation syntax — natural-language match against the
   registry is enough.
```

You lose UX polish (no autocomplete, no `/skill-name`). You keep all the architectural value.

### Sub-agent — when your runtime doesn't have one

Sub-agents are the most platform-divergent primitive. The package's intent is **isolated context + summary-only return**. Different ways to achieve it:

- **Native sub-agent tool** (Claude Code's `Agent` tool) — easiest; intended primitive.
- **Fresh API call** (any LLM API client) — open a new client session with a self-contained prompt; capture and parse the response.
- **Spawn another CLI process** (Aider, OpenAI CLI, your own wrapper) — `subprocess.run([...], capture_output=True)`; isolation is the OS process boundary.
- **Same-process call with hard context reset** (only viable for very short tasks) — clear the conversation, run the task, capture, restore context. Fragile; avoid.

The non-negotiable: **the parent's context must NOT see the sub-agent's intermediate work**. Only the final summary returns. Any of the above patterns satisfies this if implemented correctly.

### Hook — when your runtime doesn't have one

Hooks let the runtime invoke your code automatically (before each tool call, on session stop, etc.). If your runtime doesn't expose hook configuration:

- **Wrap every LLM invocation** in a script. Pre-hooks become lines at the top of the script; post-hooks become lines at the bottom.
- **Wrap each tool call** in a dispatcher you control. Inside the dispatcher: pre-hook code → tool → post-hook code → return.
- **Don't try to retrofit hooks via prompt instructions.** ("Always run X before Y" in the system prompt is unreliable; hooks must be enforced by code, not asked of the LLM.)

### Registry — when your runtime is MCP-only

If your runtime is MCP-driven, the registry is implicit: `tools/list` *is* the registry. You may still keep a YAML registry on disk for human-readable indexing — but the agent should query MCP for current capabilities rather than trusting a file that may be stale.

In this case, treat the on-disk registry as the *human's* index and MCP's `list_tools` as the *agent's* index.

## Concept-To-Primitive Map (For Cross-Reference)

When the rest of the package mentions one of these concepts, here is which primitive it leans on. Use the table above to translate.

| Concept (where mentioned) | Leans on primitive | Notes |
|---|---|---|
| Council pattern (05-multi-agent-patterns.md) | sub-agent (parallel) + file-based state | Each reviewer is a sub-agent; chair synthesizes their on-disk verdict files |
| Ralph loop (03-harness-design.md) | sub-agent + scheduler + file-based state | Planner / generator / evaluator are sub-agents; loop is scheduled; feature_list.json is state |
| Session debrief (02-layered-memory.md, 07-anti-context-rot.md) | hook (Stop event) + skill | Triggered automatically on session end if the runtime has a Stop hook; otherwise an invocation the user runs |
| Artifact mirroring (07-anti-context-rot.md) | hook (PostToolUse on file create) | Cleanest as a hook; otherwise discipline of "write to permanent path immediately" |
| Skill registry lookup (06-skills-system.md, AGENTS.md recipe) | registry | Read-only at session start; the orchestrator scans before improvising |
| Sub-agent isolation for Playwright (05-multi-agent-patterns.md, 07-anti-context-rot.md) | sub-agent | Mandatory; do not run heavy automation in the parent |
| Slash invocation of skills (AGENTS.md) | slash invocation / command | Sugar; the underlying mechanism is "find skill in registry, read SKILL.md, follow procedure" |

## What If Your Runtime Has Primitives We Didn't List?

You probably have **more** primitives than this table covers, not fewer. Examples:

- **Claude Code** also has `MCP servers`, `IDE integrations`, `keyboard shortcuts`. The table covers the load-bearing primitives for *this package*; ignore others unless a downstream reference doc uses them.
- **OpenAI Assistants API** has `threads`, `runs`, `code interpreter`. Map "thread" → file-based state; "run" → sub-agent invocation; "code interpreter" → execution layer.
- **Custom in-house harness** likely has a job queue, a database, and worker pools. Map the job queue → scheduler; the database → file-based state (with richer queries); workers → sub-agents.

The table's purpose is **floor coverage** — every primitive the rest of the package depends on appears here. If your runtime's mechanism doesn't appear, ask: which row does it implement? Map accordingly.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Skipping this doc and pattern-matching "skill" / "sub-agent" / "registry" to whatever your runtime calls them | Read this doc first; do an explicit substitution pass before applying the principles |
| Translating only some primitives, leaving others to "I'll figure it out" | Translate all seven before starting; the gaps cause silent rule violations later |
| Using prompt instructions to emulate hooks ("always run X before Y") | Hooks must be enforced by code (wrappers, dispatchers); LLM-asked discipline is unreliable |
| Skipping sub-agent isolation because your runtime "doesn't have sub-agents" | Use the fallback column — spawn a process, capture stdout, return only the summary |
| Hard-coding `registry/*.yaml` paths when MCP `list_tools` would be more current | When MCP is your runtime, treat the on-disk registry as a human index, not the source of truth |

## Bootstrap Checklist

- [ ] Identified your runtime in the column header (or selected the closest match for translation).
- [ ] For every row, noted your runtime's term and (if no native support) the fallback mechanism.
- [ ] If using MCP, decided whether to also keep a human-readable registry file.
- [ ] If your runtime has no hook mechanism, established a wrapper script as the sole entry point.
- [ ] Sub-agent isolation mechanism chosen (native tool, fresh API client, subprocess) and tested with one real heavy task.
- [ ] Read the rest of the package with the substitution pass actually performed (not just intended).
