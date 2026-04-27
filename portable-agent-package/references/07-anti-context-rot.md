---
template: portable-agent-reference
version: 0.1.0
summary: "Defenses against context rot: artifact mirroring, structured-output-to-file-first, sub-agent isolation, archive-not-delete, hot-vs-cold context discipline, YYMMDD prefix convention, never-trust-ephemeral, grounding-before-quoting, file-scope guards."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 07 — Anti-Context-Rot Discipline

"Context rot" is the slow degradation of an agent's effective working state across a session. It causes:

- Recent decisions getting compacted away.
- Useful files becoming "lost" because they were referenced in chat but never written down.
- Agents re-deriving things they already figured out.
- Verdicts and findings disappearing into chat history.
- Hallucinated quotes from files that don't exist (the chat said it once, no one verified, the agent now believes it).

These defenses are cheap. Adopt all of them.

## Defense 1 — File-First Output Discipline

> **Rule:** Before producing structured output longer than a few paragraphs, write it to a file.

Triggers:

- Multi-step plans
- Investigation reports
- Action lists / triage checklists
- Reviews with multiple findings
- Any document with headers, tables, or numbered steps

Anti-flow:

```
You: [Outputs 800-word plan in chat]
You: [User asks follow-up]
You: [Plan is now 60% scrolled away; agent paraphrases from memory]
You: [Paraphrase loses load-bearing detail; user gets a degraded plan]
```

Correct flow:

```
You: [Writes runtime/.tmp/260427-migration-plan.md]
You: "Plan at runtime/.tmp/260427-migration-plan.md.
      TL;DR: <three sentences>. Want to walk through it?"
You: [User asks follow-up]
You: [Re-read the file; never paraphrase from memory]
```

This is one of the highest-ROI discipline shifts an agent can make.

## Defense 2 — Artifact Mirroring

If your runtime puts ephemeral artifacts in a session-specific directory (`~/.claude/projects/<id>/brain/`, `/tmp/<session>/`, etc.), **those files die when the session ends.**

> **Rule:** When you create a file in a session-specific directory, **immediately** copy it to a permanent location.

```
final deliverables  →  runtime/deliverables/YYMMDD-<name>.<ext>
intermediates       →  runtime/.tmp/YYMMDD-<name>.<ext>
```

The mirror is part of the create step, not a retroactive cleanup. By the time you "remember to mirror," compaction may have already eaten the path.

## Defense 3 — Sub-Agent Isolation For Heavy Work

Repeating from [05-multi-agent-patterns.md](05-multi-agent-patterns.md):

A long Playwright session, a full codebase scan, a 30K-row CSV parse — these *destroy* the parent's context window. Spawn a sub-agent. Hand it the task. Get back **only a summary**.

Cost: the parent loses depth on the heavy work.
Benefit: the parent's context is preserved for everything else.

The trade-off is almost always worth it.

## Defense 4 — Archive, Don't Delete

When cleaning up `runtime/.tmp/` or stale deliverables, **move to `_archive/`**. Don't `rm`.

```
runtime/.tmp/                 ← active
runtime/.tmp/_archive/        ← stale; same flat structure, YYMMDD-prefixed
```

Reasoning: when the user comes back six months later asking "remember that plan we did for X?", the answer is in `_archive/`. Disk is cheap; reconstructing context is expensive. Be a data pack rat with intermediates.

## Defense 5 — YYMMDD Prefix Everything

`YYMMDD-` prefixes give you free chronological sort and instant temporal context:

```
runtime/.tmp/260424-pente-spec.md
runtime/.tmp/260427-migration-plan.md
runtime/.tmp/260501-investigation-results.md
```

Compared to:

```
runtime/.tmp/pente-spec.md
runtime/.tmp/migration-plan.md
runtime/.tmp/investigation-results.md
```

The first form tells you when each thing happened, sorts naturally, and survives "I have 47 files in .tmp from over the last 3 months." The second loses temporal context.

## Defense 6 — File-Scope Guards On Mutating Skills

Before declaring an autonomous skill done, run:

```bash
git diff --name-only <pre-skill-sha>..HEAD
```

Every changed path must match a pre-declared whitelist. Anything outside the whitelist → BLOCK and report.

This catches:

- Sub-agents wandering outside their assigned scope
- Refactor sprawl during what was supposed to be a focused change
- Migrations that touched more than the migration directory

If your skill's scope is `src/games/<slug>/` + a few specific glue files, encode that as a whitelist and enforce it. The whitelist is the safety net.

## Defense 7 — Grounding Before Quoting

> **Rule:** Before you quote, reference, or describe specific content from a file (a section heading, a code block, a table row, a phrase), grep the file to verify the content exists.

The failure mode this catches: hallucinated content. Reviewer agents have been observed to "find" sections in artifacts that aren't there — apparently drawing from sibling files in the same directory or from training-data priors. The fabrication looks plausible because it's the kind of thing that *would* be there.

Grep is cheap. Use it.

## Defense 8 — Never Trust Ephemeral State

A non-exhaustive list of things you should not trust to survive:

- Chat output (will be compacted)
- Sub-agent return summaries (only the summary survives; the depth is gone)
- The fact that "we just decided X" five turns ago (compaction window may have moved)
- Tool results from earlier in the session (may be summarized away)
- Your own memory of what a file contained (re-read it before quoting)

If anything in this list matters for downstream work, **write it to a file**.

## Defense 9 — Hot vs Cold Context Discipline

Repeating from [04-progressive-disclosure.md](04-progressive-disclosure.md):

- **Hot context** = always-on. Goal: minimal.
- **Cold context** = on-demand. Goal: large but indexed.

Promote things to hot context only when they are needed for **every** task. The temptation is to promote things "to be safe." Resist. Always-on context displaces session work.

## Defense 10 — Plain Files, No Magic

Storage that is opaque to humans and tools is fragile. Prefer:

- ✅ Markdown files in directories
- ✅ YAML / JSON for structured data
- ✅ git as the source of truth
- ✅ Symlinks for vendor adapters

Avoid:

- ❌ Vendor-proprietary databases for memory
- ❌ "Magic" tools that hide where state lives
- ❌ Storage you can't read with `cat` or `Read`

When state is in plain files in directories, you can grep, diff, version, restore, and migrate. When state is in a vendor-managed opaque blob, you depend on the vendor's tooling — and you lose if that tooling changes.

## Defense 11 — Session Debrief Ritual

The single most effective defense against memory rot is **doing a debrief at session end.**

A debrief takes 2-5 minutes:

1. What did we do? → one-line entry to `memory/session-log.md`.
2. What did we learn? → new or updated topic memories.
3. What changed in the system? → commit any directive/skill/script edits.
4. What's pending? → update `memory/current-state.md` with active work, blockers, decisions awaiting input.
5. Commit. Push.

Without this ritual, mid-term memory atrophies. With it, the next session opens with a known starting point.

## Defense 12 — Versioned Frontmatter

Every agent-consumable file has frontmatter with `version` and `last_updated`. When you fix a bug or learn something:

- Update the file.
- Bump the version (patch / minor / major per semver semantics).
- Update `last_updated`.

This protects against "I remember that directive said X" — the version field tells you whether your memory is stale.

## Defense 13 — Concrete Verification Beats Vibes

Don't trust:

- "I think the build passed."
- "It looks like the migration ran cleanly."
- "Pretty sure that endpoint returned 200."

Do trust:

- A captured exit code.
- A grep against the actual log file.
- A screenshot of the response.
- An assertion in a test.

For autonomous loops, this is the single most important defense (see [03-harness-design.md](03-harness-design.md)). For interactive work, it's still the right discipline — your gut feel of "looks fine" is wrong more often than the discipline of checking.

## Defense 14 — Bounded Blast Radius

Repeating from [05-multi-agent-patterns.md](05-multi-agent-patterns.md):

A skill, sub-agent, or revision pass should edit **a known set of files**. If a finding implies an upstream edit, log it for human disposition; don't silently propagate.

The reasoning: silent upstream edits become unaudited refactors. They break downstream consumers in ways that don't surface until much later, when the link to the original change is lost.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Producing structured output in chat, planning to mirror later | Write to file first; chat is just the pointer |
| Cleaning up `.tmp/` with `rm` | Move to `_archive/` |
| Files without YYMMDD prefix | YYMMDD prefix on every dated artifact |
| Skill with implicit scope ("don't touch other files") | Whitelist + post-run `git diff` check |
| Quoting content from memory | Grep first, then quote |
| Always-on directory of "important" docs | Tiny hot context; rest indexed and on-demand |
| Memory in vendor-opaque storage | Plain markdown in a git repo |
| No session debrief | Debrief every session; commit; push |
| Believing "the build passed" without checking | Capture exit code or grep the log |
| Sub-agent edits files outside its assigned scope | Bounded blast radius enforced |

## Bootstrap Checklist

- [ ] AGENTS.md (or equivalent) requires file-first output discipline; specifies which directories.
- [ ] Artifact-mirroring rule documented; tested with one session-specific artifact.
- [ ] `runtime/.tmp/` and `runtime/.tmp/_archive/` exist and are used.
- [ ] All artifacts use YYMMDD prefixes.
- [ ] At least one skill has a file-scope guard (whitelist + post-run git diff).
- [ ] Reviewer/critic prompts include the grounding requirement.
- [ ] Session-debrief skill in place; tested at the end of one real session.
- [ ] All agent-consumable files have versioned frontmatter.
- [ ] Memory lives in a vendor-independent, plain-markdown, git-backed location.
