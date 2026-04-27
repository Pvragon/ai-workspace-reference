---
template: portable-agent-reference
version: 0.1.0
summary: "Four-tier memory hierarchy (long-term / mid-term / near-term / session); MEMORY.md index pattern; topic file conventions; what NOT to save; vendor-independent storage; dual-write to graph (optional, future)."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 02 — Layered Memory

Memory is the agent's continuity across sessions. Get it wrong and the agent re-discovers the same thing every conversation. Get it right and the agent compounds learning.

## The Four Tiers

| Tier | Lifetime | Examples | Storage | Maintenance |
|---|---|---|---|---|
| **Long-term** | Persistent, versioned | Architecture refs, governance docs, identity | `context/indexed/`, git-backed, registry-driven | PR / direct push, version-bumped |
| **Mid-term** | Cross-session, curated | Topic memories, lessons learned, feedback rules | `memory/*.md` indexed by `MEMORY.md`, vendor-independent repo | Session debrief; pruned by distillation |
| **Near-term** | Within-initiative | Working files, plans, screenshots, intermediate data | `runtime/.tmp/` — flat, YYMMDD-prefixed | Archived (not deleted) on initiative completion |
| **Session** | Single conversation | Loaded prompts, recent tool output | Volatile; subject to compaction | Automatic by runtime |

**Each tier has a different lifetime. Never confuse them.**

- Putting a long-running invariant in session memory → lost on next session.
- Putting a one-shot task plan in mid-term memory → memory bloat, future-you wades through it.
- Putting source-of-truth governance in mid-term memory → no version control, no audit trail.
- Putting `runtime/.tmp/` content in version control → repo bloat, secrets risk.

## Long-Term Tier — Versioned Reference

Lives in `context/indexed/` (or whatever your equivalent is). Examples:

- Architecture references (workspace topology, system design)
- Governance docs (file placement rules, naming conventions)
- Long-lived integration docs (vendor APIs, deployment ops)
- Persona definitions
- Identity files (the agent's name, defaults)

**Properties:**

- Git-backed.
- Versioned (`version` field in frontmatter, bumped on change).
- Loaded **on-demand** via the registry (see [progressive disclosure](04-progressive-disclosure.md)). Never always-on.
- Reviewed via PR if shared, or direct-pushed if personal.

**Anti-pattern:** Loading every long-term doc into the system prompt at session start. The point of indexed long-term context is that you scan the index → decide → load only relevant files. Always-on context means the doc set fights for token budget.

## Mid-Term Tier — Cross-Session Curated Memory

This is the tier most agents underbuild. Mid-term memory is **what the agent has learned about the user, the project, the world, and itself, that would be lost if not written down.**

### The Index Pattern

A single `MEMORY.md` is auto-loaded at session start. It is **an index, not a memory.** Each entry is one line:

```markdown
# Memory Index

| Topic File | Summary |
|------------|---------|
| `user_role.md` | User is a senior backend engineer; deep Go expertise, new to React |
| `feedback_no-mocks.md` | Integration tests must hit real DB — prior mock/prod divergence incident |
| `project_acme-q3.md` | ACME Q3 build — May 15 target, Sprint 1 kickoff April 24 |
| `reference_alerts-grafana.md` | grafana.internal/d/api-latency is the oncall dashboard |
| `feedback_naming.md` | Always self-document file/script names |
```

**Rules of the index:**

1. **One file per topic, semantically organized** (not chronologically). `user_*`, `feedback_*`, `project_*`, `reference_*` prefixes make scanning fast.
2. **One line per entry, under ~150 chars.** Long entries break the load-the-index-only optimization.
3. **The index is auto-loaded.** Topic files are loaded on demand.
4. **Stale entries get removed**, not just superseded. Prune aggressively.

### Topic File Format

Each topic file lives in `memory/<file>.md` with this frontmatter:

```markdown
---
name: feedback no-mocks
description: Integration tests must hit a real database, not mocks
type: feedback
---

Integration tests in this codebase must hit a real database, not mocks.

**Why:** Q1 incident — mocked tests passed but the production migration failed.
The mock allowed an old API surface; prod hit the new schema.

**How to apply:** Whenever I propose a test that mocks the DB, replace it with a
test against the test container. If a user requests a mock test, raise the prior
incident and ask for explicit override.
```

The body has three parts when the memory type is feedback or project:

1. **The rule/fact** — the literal thing to remember.
2. **Why** — the reason. Often a past incident or strong preference. *Without the why, edge cases trip the rule.*
3. **How to apply** — when this kicks in.

### Memory Types

| Type | Use For | When To Save |
|---|---|---|
| **user** | Role, preferences, knowledge, working style | First time the user reveals something durable about themselves |
| **feedback** | Behavioral guidance — corrections AND validations | User corrects you; user accepts an unusual approach without pushback |
| **project** | Active work, deadlines, motivations, stakeholders | User states a fact about ongoing work that isn't in the code |
| **reference** | Pointers to external systems | User references a Linear board, Slack channel, dashboard, etc. |

**The asymmetry to watch:** feedback memories are easy to save when the user corrects you. They are easy to *miss* when the user **validates** an unusual choice. ("Yeah, that single-bundled PR was the right call here, splitting would've been churn.") That's a memory, not a one-off.

### What NOT To Save

These look like memories but aren't:

- ❌ **Code patterns, conventions, file paths.** The code is authoritative; reading it gives you the answer.
- ❌ **Git history.** `git log` and `git blame` are authoritative.
- ❌ **Debug recipes.** The fix is in the code; the commit message has the context.
- ❌ **In-progress work.** That's near-term — `runtime/.tmp/`, not memory.
- ❌ **Anything already documented in CLAUDE.md / AGENTS.md.** Don't duplicate the operating instructions.

When the user asks you to save *X* and *X* falls in the above, **push back gently and ask what was surprising about it**. The surprising thing is the memory.

## Near-Term Tier — Within-Initiative Working Memory

Lives in `runtime/.tmp/`. Examples:

- Today's task list
- An implementation plan still being iterated
- Screenshots from a Playwright session
- Scraped HTML, intermediate CSVs
- A migration script you may need to re-run

**Properties:**

- **Flat directory.** No deep subfolder hierarchy; flat YYMMDD-prefixed files.
- **Archived, not deleted.** When an initiative completes, move into `runtime/.tmp/_archive/` rather than rm. Storage is cheap; reconstructing context is not.
- **Not version-controlled** (or, if so, gitignored from sync).
- **Mirroring.** If your runtime puts ephemeral artifacts in a session-specific directory (e.g. `~/.claude/projects/<session>/brain/`), copy them to `runtime/.tmp/` *as you create them*, not retroactively.

**The structured-output-to-file-first rule:**

> Before producing structured content (>3 paragraphs, headers, tables, numbered steps), write it to a file. Chat output is ephemeral. References can be re-read; chat output cannot.

Example flow:

```
User: "Give me a 7-step migration plan."
You: [Write runtime/.tmp/260427-migration-plan.md]
You: "I've drafted the plan at runtime/.tmp/260427-migration-plan.md.
      The TL;DR: <three sentences>. Want me to walk through it?"
```

Not:

```
You: [Outputs 800-word plan in chat]
You: [Optionally, retroactively writes it to a file]
```

## Session Tier — Volatile Working Set

This is what's currently in your context window. You don't manage it directly; the runtime does.

**The principles you can control:**

1. **Keep it lean.** The bigger the session context, the more compaction risk.
2. **Write back to disk early.** See structured-output-to-file-first.
3. **Don't paste large data into chat.** If a file is 5,000 lines, summarize and reference; don't dump.
4. **Use sub-agents to absorb context-heavy work.** A long Playwright session, a large codebase scan, a 200-row table parse — spawn a sub-agent, have it return only a summary.
5. **Treat compaction as inevitable.** Don't store anything you need to remember in chat — store it in files.

## Vendor-Independent Storage (Identity Repository Pattern)

Your memory should not live inside vendor-specific directories. It should live in a **git repository at `agents/<your-name>/`**, and the vendor's runtime should access it via symlink.

```
agents/
  <your-name>/                  ← git repo
    identity.md                 ← name, pronouns, defaults
    memory/
      MEMORY.md                 ← index
      *.md                      ← topic files
    adapters/
      <vendor>/link.sh          ← symlinks vendor's expected paths to memory/
```

**Why:**

- **Backup.** Push to a private remote regularly. If your laptop dies, your memory survives.
- **Audit.** Every memory change is a commit.
- **Vendor independence.** Switch from Vendor A to Vendor B by writing a new adapter; memory is unchanged.
- **Multi-runtime.** If you operate from multiple cwds (multiple project directories), they all symlink to the same memory pool. One agent, one memory.

**Anti-pattern:** Writing memory directly into `~/.claude/`, `~/.cursor/`, or any vendor directory. You will lose it the day you switch tools.

## Maintenance — Session Debrief

At the end of every session, an agent runs a debrief:

1. **What did we do?** One-line entry in `memory/session-log.md` (chronological, ungated).
2. **What did we learn?** New memories — append to existing topic files or create new ones. Update the MEMORY.md index.
3. **What changed in the system?** If you updated a directive, skill, or script, commit it.
4. **What's next?** A `current-state.md` file (one paragraph) updated with active work, blockers, decisions awaiting input.
5. **Commit.** All changes in `agents/<your-name>/` get committed; optionally pushed.

This is the only reliable way to make memory accumulate. Without a debrief ritual, mid-term memory atrophies.

## Optional: Graph Layer Over Markdown

A future-state extension worth knowing exists:

```
Layer 3 (workflow): skills, debrief, progressive disclosure (this package)
Layer 2 (query):    semantic search, temporal queries, contradiction detection
Layer 1 (storage):  knowledge graph (FalkorDB, Neo4j, etc.) + vector embeddings
─────────────────────
Source of truth:    markdown files (this package's mid-term memory)
```

The markdown files remain the source of truth. The graph is a *derived, rebuildable index*. If the graph is lost, it can be reconstructed from the files. Tools to consider when scaling: Graphiti, Cognee, Hindsight, Mem0.

**Don't build this on day one.** Markdown + grep handles thousands of memories before semantic search becomes load-bearing. The graph layer is for when you have N agents, M projects, and grep stops being enough.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Memory entries chronologically organized | Memory entries semantically organized (by topic) |
| Long entries inline in MEMORY.md | One-line summary in MEMORY.md; detail in topic file |
| Saving "the user said hello yesterday" | Saving "user prefers terse responses, no trailing summaries" |
| Saving `git log` -style activity | Saving the *surprising* facts; verifiable history goes in git |
| Memory in `~/.claude/` | Memory in `agents/<name>/`, symlinked into vendor path |
| Never debriefing | Debriefing every session; memory drifts when you don't |
| Recommending a memory without verifying it's still true | Verifying the memory against current state before acting on it |
| Stuffing the index with 200 entries | Pruning aggressively; old/stale entries removed, not just marked |

## Stale-Memory Discipline

A memory is a snapshot in time. Before you act on a memory:

- If it names a file path, **check the file exists**.
- If it names a function or flag, **grep for it**.
- If the user is about to act on a memory-derived recommendation, **verify the underlying reality matches before recommending**.

> "The memory says X exists" ≠ "X exists now."

When you find a stale memory, **update or remove it** rather than acting on it.

## Bootstrap Checklist

- [ ] `agents/<your-name>/` directory created as a git repo.
- [ ] `identity.md` written (name, pronouns, defaults — under 50 lines).
- [ ] `memory/MEMORY.md` index file exists with at least one entry.
- [ ] At least one topic file written using the frontmatter + body structure above.
- [ ] Vendor adapter (`adapters/<vendor>/link.sh`) creates symlinks from runtime memory paths to `memory/`.
- [ ] Session-debrief skill or routine in place; tested at the end of one real session.
- [ ] First commit + push to a private remote.
