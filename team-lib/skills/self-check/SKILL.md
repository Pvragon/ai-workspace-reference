---
name: self-check
description: Run the deterministic memory-hygiene linter (the dream-cycle detector) and report findings — MEMORY.md↔file consistency, orphaned topic files, dead [[wikilinks]], frontmatter gaps, stale short-term. Optionally apply the safe incremental groom. Use when the user asks to check/groom memory health, or before a big memory reorganization.
summary: "On-demand memory-substrate hygiene check via executions/memory_self_check.py. Detection-only by default; --fix-safe applies deterministic frontmatter backfills. The manual entry point to the self-maintenance 'dream cycle' (backlog/260712-memory-system-framework.md, Scheduler layer)."
version: 1.0.0
created: 2026-07-12
last_updated: 2026-07-12
maintainer: pvragon
mirror: divergent
mirror_reason: >-
  Same split as the dream skill: my-lib is agent-bound, team-lib is the portable
  variant (`agents/<your-agent>/`) and carries the extra portability note about
  agent_paths.py. Keep the PROCEDURE identical — if a step changes, change it in both.
---

# /self-check — Memory Hygiene

> **Portable.** Every script below resolves the agent directory through
> `team-lib/executions/agent_paths.py`, so nothing here is specific to one agent or
> machine. If the agent cannot be resolved the scripts say so and exit rather than
> guessing. Install with `bootstrap_memory.py --apply` then
> `install_memory_hooks.py --apply`, and confirm with `verify_memory_install.py`.

The manual entry point to the self-maintenance **dream cycle** (Scheduler layer of `backlog/260712-memory-system-framework.md`). It runs a deterministic linter over the canonical memory dir and reports what needs grooming. The same detection runs automatically at every `/session-debrief`; this skill is for running it on demand.

## When to use
- The user asks to check, audit, or groom memory health.
- Before a large memory reorganization (baseline the state first).
- After bulk memory edits, to catch orphans / broken links / frontmatter gaps.

## What it checks (detection — no mutation)
`python3 ~/ai-workspace/team-lib/executions/memory_self_check.py`

- **missing_file** — a `MEMORY.md` row pointing at a file that doesn't exist.
- **orphan_file** — a topic file with no `MEMORY.md` row.
- **frontmatter** — a topic file missing its `---` block, or missing `name:` / `type:`.
- **stale_shortterm** — the newest `short-term/*.md` is older than 14 days.
- **dead_wikilink** — a `[[slug]]` with no matching `slug.md` (INFO; may be an intentional not-yet-written TODO — does not fail `--strict`).

Flags: `--json` (machine output), `--strict` (exit 1 on any hard finding).

## Procedure
1. Run the detection command above and present the findings grouped by category. Lead with the counts; list the specific files.
2. **Interpret, don't just dump.** Distinguish real problems (a missing-file row is a broken index) from expected noise (a `[[rc-cto]]` link points at a skill, not a memory — that's fine).
3. If there are safe, deterministic frontmatter gaps (missing `name:`/`type:`), offer the incremental groom:
   `python3 ~/ai-workspace/team-lib/executions/memory_self_check.py --fix-safe --limit <N>`
   This backfills ONLY filename-dictated `name:`/`type:` keys (reversible, judgment-free), capped at N. Confirm the count and re-run detection to show the reduction.
4. **Escalate the judgment calls** — a missing `---` block, ambiguous dead links, suspected duplicates — to the user. Those are the "dreamer wakes for judgment" cases; the linter deliberately won't auto-fix them.

## Guardrails
- Detection never mutates. `--fix-safe` mutates only frontmatter `name:`/`type:` and only when dictated by the filename.
- Never delete a memory file or a MEMORY.md row from this skill. Missing-file rows are surfaced for the user to reconcile, not auto-removed.
- Memory writes target the canonical path; the groom writes in place under `agents/<your-agent>/memory/` (allow-listed, prompt-free).
