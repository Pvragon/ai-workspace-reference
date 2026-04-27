---
template: portable-agent-reference
version: 0.1.0
summary: "Progressive disclosure: the summary frontmatter convention; index aggregation pattern; reference-vs-instruction file distinction; registry-as-bridge; how to keep large knowledge bases usable without bloating context."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 04 — Progressive Disclosure

The single technique that lets an agent's knowledge base grow without its context window growing. Without this, large knowledge bases are unusable: either everything is loaded (token bloat, displacement of recent work) or nothing is (the agent re-derives every conversation).

## The Core Idea

Every agent-consumable file has a one-line `summary` in YAML frontmatter. Index files aggregate sibling summaries into a discovery table. The agent **scans the index** to decide what to open, then **opens only what's needed**.

```
Cold-start context (always-on, ~minimal):
  identity.md
  AGENTS.md / operating instructions
  MEMORY.md (the index)
  registry/*.yaml (manifests)

On-demand context (loaded when relevant):
  context/indexed/*.md (long-term reference)
  memory/*.md (mid-term topic files)
  skills/<name>/SKILL.md (when a skill is invoked)
  directives/*.md (when work matches one)
```

The cold-start is small. Everything large is reachable but not pre-loaded.

## The summary Frontmatter Field

Every agent-consumable file over 15 lines MUST include `summary` in its YAML frontmatter:

```yaml
---
template: directive
version: 1.0.0
summary: "Weekly vendor price scrape. Outputs CSV diff vs. last week."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
---
```

`summary` answers exactly one question: **"Should I open this file?"**

### Writing Rules

- **1-2 sentences maximum.**
- **Name the concrete thing.** Not "this document covers various topics" — *"Defines the execution script standard."*
- **State when/why.** *"Load when building new execution scripts."*
- **Tool-agnostic.** Valid for any LLM, not Claude-specific.
- **Update on version bump.** If the file changed enough to bump version, the summary may need to change too.

### Good vs Bad

✅ Good
- "Canonical reference for workspace architecture, directory conventions, and agent operating rules. Load when an agent needs to understand where something belongs."
- "Procedure for graduating files from my-lib to team-lib. Follow when a local tool is ready for team-wide use."
- "Pvragon brand guidelines: colors, typography, logo usage. Required before generating any branded deliverable."

❌ Bad
- "This document is about the workspace." (vague; no decision signal)
- "Important information about various topics." (useless)
- "A comprehensive guide that covers many important topics related to the architecture and its various components." (verbose; no decision signal)

The bad ones share one failure: they don't help the agent **decide whether to open the file**. The agent ends up opening it just to find out what it is — defeating the purpose.

## Reference Files vs Instruction Files

Both file types use `summary`, but the agent uses it differently:

| Type | Where | How summary is used | After opening |
|---|---|---|---|
| **Reference** | `context/indexed/`, business overviews, framework definitions | Decide whether to open | Partial reads are fine — read only the relevant section |
| **Instruction** | `AGENTS.md`, `SKILL.md`, directives, personas | Decide *which* one is needed | **Read in full.** Every word matters; instructions are not skimmable |

When in doubt, treat a file as instruction (full read) rather than reference (skimmable). Underreading instructions causes silent rule violations.

## The Index Aggregation Pattern

Index files aggregate the `summary` fields from their sibling files into a discovery table:

```markdown
# directives/index.md

| File | Summary |
|------|---------|
| `vendor-price-scrape.md` | Weekly vendor price scrape; outputs CSV diff vs. last week |
| `inbound-email-triage.md` | Triage inbound email; route to action queue or archive |
| `release-announcement.md` | Draft release announcement from changelog |
```

The agent scans **one file** to assess all siblings without opening any of them. This is the same pattern as the MEMORY.md index — applied to long-term context.

## Registry As The Bridge

Indexes are human-readable. Registries are machine-readable.

```yaml
# registry/directives.yaml
# summary: Manifest of all directives for tool resolution.
# last_updated: 2026-04-27

directives:
  - path: directives/vendor-price-scrape.md
    summary: Weekly vendor price scrape; outputs CSV diff vs. last week
    tags: [scraping, finance, weekly]
  - path: directives/inbound-email-triage.md
    summary: Triage inbound email; route to action queue or archive
    tags: [email, triage]
```

The agent's lookup procedure:

1. User makes a request.
2. Agent searches `registry/directives.yaml`, `registry/skills.yaml`, etc. for matching tags / keywords.
3. Agent reads the matched file (in full if it's instruction, partial if reference).
4. Agent acts.

This is fast because the registry is small and structured. The agent doesn't grep the whole filesystem; it consults a curated index.

> **Anti-pattern:** Letting indexes and registries drift. When you add a directive, **add a registry entry in the same change**. Stale registries are worse than no registry — the agent trusts them and gets the wrong answer.

## What Goes In Index Vs File Body

| In the index | In the file body |
|---|---|
| One-line summary | Full procedure / detail |
| Tags / type / keywords | Examples |
| Path | Frontmatter (full) |
| Last-updated date | Anti-patterns, edge cases |

The index is **navigation**. The file is **content**. They serve different purposes; never duplicate the file body in the index.

## Hot vs Cold Context

A useful mental model:

- **Hot context** = always loaded at session start. Goal: minimal.
- **Cold context** = loadable on demand. Goal: large but indexed.

Hot context for the package described in this kit (illustrative):

```
identity.md               (~50 lines)
AGENTS.md                 (~300 lines)
MEMORY.md                 (~150 lines, mostly the index table)
registry/*.yaml           (~variable, but each entry is one line)
```

Total cold-start: maybe 1,000 lines. Manageable.

Cold context: the rest of the workspace. Hundreds or thousands of files. The agent reaches into it as needed.

**The math.** If hot context is 1k lines and cold is 100k lines, the agent's cold-start is 1k lines. With always-on context, it would be 100k+ lines — well beyond any model's window. Progressive disclosure makes the 100x scale possible.

## When To Promote A File To Always-On

Almost never. The default is on-demand.

Promote to always-on **only** when:

- The file is short (under ~300 lines).
- It is needed for **every** task, not most tasks. (Identity, operating instructions, memory index.)
- It changes infrequently (so it stays in the model's KV cache and doesn't trigger re-prefilling).

The temptation is to promote things "to be safe." Resist. Always-on context displaces session work; that displacement compounds across long sessions.

## Length Bands For Files

A useful set of defaults:

| File type | Target length | Why |
|---|---|---|
| Identity | ≤ 50 lines | Always-on; must be tiny |
| AGENTS.md | 200-400 lines | Always-on; the contract; needs depth but not bloat |
| MEMORY.md | ≤ 250 lines (mostly the index table) | Always-on; pure index |
| Topic memory | 20-100 lines | On-demand; one fact + why + how-to-apply |
| Reference doc | 100-500 lines | On-demand; can be deep, agent loads only what's needed |
| SKILL.md | 100-400 lines | Read in full when invoked; budget against typical skill complexity |
| Registry YAML | One line per entry | Machine-readable; no prose |

Files significantly over the band are a smell. Either split, or move detail to a sub-doc and reference.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Vague summary ("this file is about X") | Concrete summary ("Defines X. Load when Y.") |
| Always-on directory of every reference | Cold-start has minimal hot context; rest is on-demand |
| Index duplicates file body | Index is one-line navigation; body has detail |
| Registry drifted out of sync with files | Same change updates both file and registry |
| Skipping summary on a 200-line file because "the title is enough" | Every agent-consumable file > 15 lines has a summary |
| Reading a long reference cover-to-cover | Use the index / TOC; load relevant sections only |
| Writing a reference doc that's actually instruction (or vice versa) | Decide upfront; treat instruction as full-read |

## Bootstrap Checklist

- [ ] Frontmatter standard documented (template, version, summary, created, last_updated, maintainer).
- [ ] At least three real files have correct `summary` fields (not stubs).
- [ ] At least one `index.md` aggregates summaries from a directory.
- [ ] At least one `registry/*.yaml` provides machine-readable manifest.
- [ ] AGENTS.md (or equivalent) tells the agent: "consult registry first; load on-demand; never blanket-load a directory."
- [ ] Hot vs cold context mapped: list every file the agent loads at session start, confirm it's small.
