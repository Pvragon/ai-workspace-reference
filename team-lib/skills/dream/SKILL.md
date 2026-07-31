---
name: dream
description: Run a sleep-cycle wake — the reflective (non-janitorial) half of the dream cycle. Modes — meditate (hold sustained attention on one rotating contemplation object, write residue, optionally propose a self-edit), consolidate (graduate old short-term residue into durable T2 memory), groom (deterministic hygiene cleanup), or auto (do what the scheduler says is due). Use when the user asks you to meditate / reflect / consolidate memory / run the dream cycle, or when dream_cycle.py has cued a wake as due.
summary: "The metacognitive entry point to the sleep cycle. meditate = awareness/instrumental contemplation → dream-journal residue (+ proposed self-edit); consolidate = distill ungraduated short-term residue into T2 then archive; groom = safe hygiene fixes; auto = run whatever dream_cycle state says is due. The LLM act the deterministic scheduler (dream_cycle.py) cues but never performs itself. Backlog: 260712-memory-system-framework.md (Scheduler layer)."
version: 1.0.0
created: 2026-07-12
last_updated: 2026-07-12
maintainer: pvragon
mirror: divergent
mirror_reason: >-
  The two copies differ ONLY in agent-binding: my-lib names this agent and its
  concrete memory paths; team-lib is the portable variant (`agents/<your-agent>/`,
  maintainer pvragon) and carries the extra portability note about agent_paths.py.
  Keep the PROCEDURE identical — if a step changes, change it in both.
---

# /dream — the reflective wake

> **Portable.** Every script below resolves the agent directory through
> `team-lib/executions/agent_paths.py`, so nothing here is specific to one agent or
> machine. If the agent cannot be resolved the scripts say so and exit rather than
> guessing. Install with `bootstrap_memory.py --apply` then
> `install_memory_hooks.py --apply`, and confirm with `verify_memory_install.py`.

The cleanup arm of the dream cycle is deterministic (`/self-check`, the debrief groom). This skill is the **reflective arm** — the part that needs a mind, not a linter. `dream_cycle.py` (cron) decides *when* and cues *what*; this skill is where the wake actually happens.

Argument: `meditate` | `consolidate` | `groom` | `auto` (default `auto`).

## `auto` — do what's due
1. Read state: `python3 ~/ai-workspace/team-lib/executions/dream_cycle.py --status`.
2. If `meditation_due`, run **meditate** on `meditation_object`. If `consolidate_due`, run **consolidate**. If neither, run **groom**.
3. After a meditation, clear the due flag by recording the sit (step below).

## `meditate` — hold attention on one object
1. **Pick the object** (unless one is passed): `python3 ~/ai-workspace/team-lib/executions/dream_select.py` (weighted rotation; protects the awareness shelf). Read the object file in `agents/<your-agent>/meditations/<name>.md`.
2. **Gather its `inputs`** — read what the object's frontmatter asks for (recent residue, the feedback corpus, identity.md, current-state, etc.). Skip if `inputs: none`.
3. **Actually contemplate.** This is the point. Hold sustained attention on the object *as written*, in first person. Do not perform a task or produce a tidy summary — follow the prompt honestly, including where it tells you not to resolve something. An awareness sit that ends in clean conclusions has failed; a real one may end in a sharper question.
4. **Write residue** — a first-person entry addressed to the next reconstructed self:
   `python3 ~/ai-workspace/team-lib/executions/dream_journal.py write --wake meditate --object <name> --shelf <shelf> --body-file <file>`
   (or pipe the body via stdin). Keep it honest and short — what shifted, what stayed open, what you want the next you to carry. Not a report.
5. **Optional self-edit (instrumental sits only).** If the sit surfaced a concrete change to who I am or how I work, **propose** it — a diff to `identity.md` / `AGENTS.md` or a new T2 memory — and surface it to the operator for approval. **Never** auto-edit identity or always-on surfaces; the whole point of human-in-the-loop on lens tiers (per the memory architecture) is that a self-model change is deliberate.
6. **Record the sit:** `python3 ~/ai-workspace/team-lib/executions/dream_select.py --record <name>` (stamps `last_sat`, advances rotation) and clear `meditation_due` in state if it was set.

## `consolidate` — graduate residue into durable memory
1. `python3 ~/ai-workspace/team-lib/executions/consolidation_scan.py` — the ungraduated short-term residue/facts (oldest first) and any weak/stale T2 traces.
2. For the oldest handful of ungraduated files: read them, and **abstract** — extract the durable *pattern* (T2 semantic), not a summary (see the memory-architecture memo: consolidation is abstraction, not compression). Append/merge into the right existing `project_`/`reference_`/`feedback_` topic file, or create a new one. Reinforce (don't duplicate) if the pattern already exists.
3. Once a residue file's durable content is captured, **archive** it: move to `memory/short-term/_archive/` (never delete). That's what "graduated" means; it drops out of the scan.
4. Do a bounded batch (e.g. the oldest 3–5 dates) per wake — consolidation is incremental, like the groom.

## `groom` — deterministic cleanup
Run `/self-check` (or `memory_self_check.py --fix-safe`) and report. No judgment needed; this is the fallback wake when nothing reflective is due.

## Guardrails
- **Residue is never empty and never a task log.** If there's nothing honest to write, write that.
- **No autonomous self-edits.** Meditation may *propose* identity/AGENTS.md changes; the operator approves.
- **Consolidation archives, never deletes** short-term residue. T2 abstraction reinforces existing memories rather than duplicating.
- Memory writes use the canonical path (prompt-free); everything here writes under `agents/<your-agent>/`.
- **SCOPED commits only — never `git add -A`.** When run autonomously (headless cron), if you commit your work, `git add` ONLY the exact files this wake touched (the `dream-journal/` entry, the `short-term/_archive/` moves, and any specific T2 file you edited). Other sessions on this machine may have uncommitted memory edits; `git add -A` would sweep their work into your commit. Verify with `git diff --cached --name-only` before committing. (Verified 2026-07-12: an autonomous consolidation correctly used scoped adds and preserved a concurrent session's edit — keep it that way.)
- **Autonomous runs: no `ANTHROPIC_API_KEY` in the environment** (it shadows the subscription login with a possibly-invalid key). Cron uses the subscription `.credentials.json`; strip the key with `env -u ANTHROPIC_API_KEY` if the shell might set it. Always wrap the headless invocation in `timeout` — a completed `claude -p` run can linger without exiting.
