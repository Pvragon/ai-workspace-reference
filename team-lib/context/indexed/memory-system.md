---
template: business-context
version: 2.1.1
summary: "Build-and-operate spec for the agent memory system shipped in team-lib: the five memory
  tiers, the two-strength retrieval policy with its exact formula and constants, the frontmatter
  schema every consumer relies on, the nightly sleep cycle, the four hooks, the one-command install, the
  regression suite that proves the RANKING (not just the wiring) is correct, and the one-shot
  migrations an existing corpus needs. This is the implementation contract — the narrative explanation lives at
  prez.prgn.ai/pvragon/260730-agent-memory-architecture. Read this one to build or debug it."
created: 2026-07-30
last_updated: 2026-08-01
maintainer: pvragon
entity_type: system
tags: [memory, retrieval, scheduler, hooks, agent-infrastructure]
status: active
---

# Agent Memory System — implementation spec

An agent memory that ranks, decays, and self-maintains, built from markdown files and
nineteen Python scripts. No database. Everything here ships in `team-lib/` and works for
any agent name on any machine.

**Narrative explanation** (why it is built this way, the neuroscience, the rejected
alternatives): `prez.prgn.ai/pvragon/260730-agent-memory-architecture`.
**This document** is the contract: schemas, formulas, constants, install, failure modes.

---

## Install (one command)

```bash
bash ~/ai-workspace/team-lib/_admin/install_memory.sh
```

Idempotent. It chains the three steps below and refuses to report success on a partial
install: exit 0 = installed and verified, 2 = deferred (no agent home yet — name the agent
first), 1 = failed. `setup_workspace.sh` calls it, and the choose-name ceremony calls it
again once the agent home exists. `--dry-run` to inspect, `--no-cron` for hosts that
schedule differently, `--agent NAME` for non-interactive installs.

The steps it runs, if you need to drive them by hand:

```bash
cd ~/ai-workspace/team-lib/executions

python3 bootstrap_memory.py              # dry run — read what it will change
python3 bootstrap_memory.py --apply      # dirs, frontmatter backfill, starter library, first index
python3 install_memory_hooks.py --apply  # register 4 hooks + 2 cron lines
python3 verify_memory_install.py         # prove the policy is actually wired
```

`install_memory_hooks.py` needs a resolvable agent only for the **cron** step; pass
`--no-cron` and it will register the hooks alone, which is how the harness gets wired
before the naming ceremony has happened.

`verify_memory_install.py` exits non-zero if anything is wrong. **Run it after any change
to hooks, paths, or settings.** A disconnected hook is otherwise invisible: memories
simply stop accumulating strength and nothing complains.

### Verifying the ranking itself

`verify_memory_install.py` proves the policy is **wired**. It does not prove the ranking is
**correct** — and the reranker is the one component that can destroy data, since the summaries
it regenerates exist nowhere else.

```bash
python3 test_memory_ranking.py          # or: pytest test_memory_ranking.py -q
```

26 property tests over a **synthetic fixture corpus in a temp dir — never the live one**.
They pin determinism, the total tie-break, budget caps, curated summaries surviving
regeneration (including archived rows), nothing-lost, born-visible, grace expiry, the spacing
gate, malformed-frontmatter degradation, tombstones, and `pin`/`superseded` overrides.

`MEMORY_EXEC_DIR=/path/to/other/revision python3 test_memory_ranking.py` runs the suite
against a **different** copy of the scripts. Use it to confirm a test actually fails on the
bug it claims to catch: the suite passed 16/16 on first write and one test was **vacuous** —
its fixture rows were too short to overflow the Hot band, so it passed against the exact bug
it existed to catch. A suite that has only ever been green is evidence of nothing.

### Adopting on an EXISTING corpus

A fresh install needs none of these. A corpus that predates a feature needs the matching
one-shot migration, in this order:

| Migration | Why | Safety |
|---|---|---|
| `backfill_memory_created.py` | The New band keys on `created:`. Derives it from each file's git birth commit, followed through renames. **mtime is not a usable proxy** — the reinforcement hook rewrites frontmatter on every touch, so mtime is last-touch, not birth (it claimed 113 files were ≤7d old where git said 40). | Existing `created:` always wins. Preserves mtime, because files with no `last_accessed` score off it. |
| `migrate_summary_into_file.py` | Moves the curated summary out of the index into each file's `summary:`. Until this runs the index is stateful and can destroy the curation of everything rolled off. | Round-trips every file in memory first and **aborts the whole run** if any would not read back identically. |
| `normalize_memory_type.py` | Collapses `type:` / nested `type:` / `template:` into one authoritative `type:`. | Value-dependent: preserves `template:` when it holds a real document-template name rather than a kind alias. |

Each supports `--dry-run` (the default) and `--sample N` before `--apply`. **The acceptance
test for the last two is that the generated index is byte-identical afterwards** — they move
where data lives without changing what the index says.

For a brand-new agent with no home yet:

```bash
python3 bootstrap_memory.py --agent <name> --apply
```

### Agent resolution

Every script resolves the agent directory through `agent_paths.py`, in this order:

1. `$PVRAGON_AGENT_HOME` — absolute path. Wins over everything.
2. `<workspace>/personal/config/agent.json` — `{"agent": "<name>"}` or `{"agent_home": "..."}`.
3. `$PVRAGON_AGENT` — a bare name, resolved under `<workspace>/agents/`.
4. Auto-detect — the single directory under `<workspace>/agents/` containing `identity.md`.

With zero or multiple candidates it **raises rather than guessing**. Writing one agent's
memory into another's directory is unrecoverable, so ambiguity is a hard error.

Check what resolved: `python3 agent_paths.py`

---

## The five tiers

Ordered by **graduation pressure** — each step up is a more deliberate promotion.

| Tier | Content | Location | Loaded | Written by |
|---|---|---|---|---|
| **T0** Working | Active attention | session context | every turn | every interaction |
| **T1** Episodic | Dated facts + residue, with provenance | `memory/short-term/YYMMDD-{facts,residue}.md` | last 7 days | session debrief |
| **T2** Semantic | Decontextualised patterns | `memory/<type>_<topic>.md` | on cue, via index | debrief, consolidation, direct teaching |
| **T3** Situational lens | Rules with narrow triggers | `lenses/*.md` | hook, on trigger match | **human only** |
| **T4** Always-on lens | Shapes every interpretation | `AGENTS.md`, `CLAUDE.md`, `identity.md` | before any input | **human only** |

Two invariants:

- **T1 → T2 is abstraction, not summarisation.** A summary preserves the original's
  structure; an abstraction extracts a pattern qualitatively different from any instance.
  Consolidation that emits summaries is doing the wrong job.
- **T2 → T3 → T4 promotion is never automatic.** Lens tiers colour interpretation inside
  their trigger zone, so auto-promotion turns one error into a permanent distortion.

**Placement test.** Is it a lens (colours interpretation) or a reference (data to look
up)? Reference → T2. If forgotten, would the decision be *wrong* or merely *slower*?
Slower → T2. Wrong → must auto-inject. Can you write a tight trigger? Yes → T3. No,
universal → T4.

Retention is a **separate axis** (Durable / Curated / Initiative / Session) answering
"how long does this last?" over all workspace artifacts. The two cross: a T1 fact is
Durable on retention and episodic on memory. See `workspace-reference.md`.

---

## The retrieval policy

### Formula

```
score = (access_count + 1) * exp(-days_since_last_access / stability) + 0.6 * importance
```

| Term | Meaning | Behaviour |
|---|---|---|
| `access_count + 1` | storage strength | monotonic, never decreases |
| `exp(-days / stability)` | retrieval strength | decays with time since last touch |
| `stability` | adaptive decay constant (days) | **grows with spaced reinforcement**, never shrinks |
| `importance` | non-decaying floor | human-set 0–10 |

`stability` is what makes this more than recency weighting. Starting at 14 days and
multiplying by 1.6 per spaced reinforcement (capped 365), a file touched once decays with
a two-week constant while one reinforced seven times across seven separate days decays
with a one-year constant. Same formula — the *rate* differs by rehearsal history.

### The spacing gate — do not skip this

A naive implementation increments `access_count` on every read, so one grep-heavy session
inflates storage strength and the adaptive constant becomes meaningless. The hook splits
the two updates:

- **Recency always refreshes** — `last_accessed = now` on every touch.
- **Reinforcement is gated** — `access_count++` and `stability *= 1.6` only when
  ≥ `SPACING_GAP_HOURS` since `last_reinforced`.

Reinforcing tools: `Read`, `Edit`, `Write`, `MultiEdit`. Editing a memory is a *stronger*
relevance signal than reading it.

**Deliberately excluded:** the auto-loaded Hot band does not reinforce its own members
(that would make Hot self-perpetuating so nothing could be displaced), and `Grep`/`Glob`
hits do not count (fragments, not a decision to retrieve a file).

### Four-band index

| Band | File | Budget | Meaning |
|---|---|---|---|
| Hot | `MEMORY.md` | `HOT_CHAR_BUDGET` 12,000 | auto-loaded every cold start |
| New | `MEMORY.md` | `NEWBORN_CHAR_BUDGET` 2,500 | born within `GRACE_DAYS` (14); newest first |
| Cold | `MEMORY.md` | `COLD_CHAR_BUDGET` 4,000 | listed, one read away |
| Archive | `MEMORY-archive.md` | unbounded | rolled off, still one read away |

`pin: true` forces Hot. `status: superseded*` rolls straight to archive.

**Nothing is ever deleted** — only index visibility shifts. Reading an archived file bumps
its score; the next rerank may promote it back. That closes the reinforcement loop through
retrieval rather than through curation.

> **Why the New band exists — the loop cannot close for a memory nobody can see.**
> A newly written memory has `access_count: 0` and `last_accessed: now`, so it scores
> exactly `1.00`. Measured on a 612-file corpus that ranked **#125**, against ~49 visible
> slots: new memories were born straight into the archive. Never indexed → never seen →
> never read → never reinforced → decaying from 1.00 downward. "The loop closes through
> retrieval" silently assumes the memory is retrievable to begin with.
>
> It is invisible by construction: nothing errors, the debrief reports success, git has the
> file, and the hygiene linter counts it as indexed *because the archive is an index*. The
> only symptom is a memory that is never recalled — indistinguishable from one that simply
> never came up. It also worsened quietly: halving the Cold budget to fit the auto-load
> limit was a correct fix, and nobody checked what it did to newborns.
>
> Keyed on `created:` **only**. mtime is last-touch, not birth — `update_memory_access.py`
> rewrites frontmatter on every touch, so mtime claimed 113 files were ≤7d old where git
> said 40. A file with no `created:` is **not** a newborn (fail closed): missing a real
> newborn costs one grace window, a false one evicts a real memory.

> **The index is a pure function of the corpus.** Row text comes from each file's
> `summary:` frontmatter (falling back to `description:`). The reranker does **not** read
> its own previous output, so **hand-edits to `MEMORY.md` are discarded** — edit the
> memory file's `summary:` instead.
>
> This replaced a design in which the summary lived only in the index and had to be carried
> forward on every run from *both* `MEMORY.md` and `MEMORY-archive.md`. Miss the archive
> half and every regeneration destroyed the curated summaries of everything rolled off —
> which happened. The one remaining read of prior output is **tombstones**: a row whose file
> no longer exists is preserved and marked ⚠, because the corpus cannot supply text for a
> file that is gone and *nothing is ever deleted*. Tombstones are consulted only for names
> absent from disk, so no live file's summary can originate from the index.

---

## Frontmatter schema

### T2 topic files — `memory/<type>_<topic>.md`

`<type>` ∈ `feedback` · `project` · `reference` · `user` · `process` · `handoff`.
The prefix is load-bearing: it is how every script identifies a memory file.

> **`type:` and `template:` are different axes — do not treat them as aliases.**
> `type:` is the memory kind and must match the filename prefix. `template:` is the
> workspace document-template field (`business-context`, `project-lifecycle`, …).
> The corpus had drifted into declaring the kind three ways — top-level `type:`,
> `type:` nested under `metadata:`, and `template:` — and 188 uses of `template:` were
> a kind alias while 45 held a genuine template name. Collapsing the field wholesale in
> either direction is wrong: as a pure alias it destroys the 45, as a pure template name
> it leaves the duplication. Normalized value-by-value; `type:` is now the single
> authoritative declaration.

```yaml
---
name: feedback_example-rule          # must equal the filename stem
type: feedback                        # the memory kind; MUST equal the filename prefix
summary: One line — THIS is the text shown in the index; edit it here, never in MEMORY.md
description: Longer prose; used as the index fallback when `summary:` is absent
created: 2026-07-30                   # load-bearing: the New band keys on it
last_updated: 2026-07-30
# --- policy fields; maintained by the hook, do not hand-edit ---
access_count: 3                       # spaced reinforcements, NOT raw reads
last_accessed: 2026-07-30T06:12:00Z   # refreshed on every touch
last_reinforced: 2026-07-29T22:40:00Z # last touch that passed the spacing gate
stability: 57.3                        # days; adaptive decay constant
# --- optional, human-set ---
importance: 6                          # 0-10 non-decaying floor for critical memories
pin: true                              # force Hot regardless of score
status: superseded_by_<target>         # forces archive
---
```

Backfill rule for adoption: `last_accessed` must be seeded from each file's **mtime**,
never `now`. Seeding `now` tells the reranker everything was just used, so day-one ranking
is arbitrary. `bootstrap_memory.py` does this correctly.

### T2 workstream extension (project files)

`status` (`in-flight`/`handed-off`/`follow-on`/`archived`/`backlog`) · `last_touched` ·
`resolves_when` (prose) · `close_signal` (machine-checkable: `clickup:<id>`,
`pr:<owner>/<repo>#<n>`, `file:<path>`, `grep:<path>::<regex>`) · `resume_via` ·
`cs_section` + `cs_headline` (current-state membership) · `pin`.

`sweep_workstreams.py` evaluates `close_signal` against live state and auto-archives on a
hit — thread-independent, so a close that happened elsewhere is still detected.

### T3 lenses — `lenses/*.md`

```yaml
---
name: subagent-discipline
type: lens
trigger:
  tool_match: "Agent|Workflow"     # required, regex against tool name
  path_pattern: "/scoped/path/"    # optional, regex against file_path
body_token_cap: 380
---
```

Adding a lens is **pure content work** — no code change. It costs context only inside its
trigger zone, at most once per session (deduped per session+lens).
`lenses/EXAMPLE-lens.md` is a filled-in template.

### Meditation objects — `meditations/*.md`

```yaml
---
name: corrections-as-mirror
type: meditation
shelf: instrumental        # awareness | instrumental
cadence_weight: 1.0
last_sat: 2026-07-29       # stamped by dream_select.py --record
sit_count: 2
inputs: none               # or: what the sit should read first
---
```

---

## The nightly sleep cycle

Two cron entries, five minutes apart. The offset matters: the deterministic tick must
finish writing its cue before the reflective wake reads it.

| Time | What | Cost |
|---|---|---|
| 03:47 | `dream_cycle.py` — groom, hygiene scan, consolidation scan, journal decay, rerank, then **cue** what reflective work is due | zero tokens |
| 03:52 | the reflective wake (`/dream auto`) — performs what was cued | LLM |

**Core principle: scripts detect, the dreamer only wakes for what scripts cannot decide.**
A linter answers "is the frontmatter missing?" for free. An LLM is needed for "is this
memory wrong, or merely old?" Burning tokens to re-derive what a linter can check is the
expensive mistake.

`dream_cycle.py` is **live-session-aware**: if any memory file changed within
`BUSY_MINUTES` it skips the mutating passes and only scans and cues.

**Cadence is locked:** the daily sleep is the only clock-scheduled reasoning. One dream,
one meditation, per day. Everything else is task-triggered. A high-frequency tick was
considered and rejected.

### The three reflective acts

- **meditate** — sustained first-person attention on one rotating object; writes residue
  to `memory/dream-journal/`. Selection: `cadence_weight * min(days_since_last_sat, 21)/21`,
  most-recent excluded, plus an **awareness floor** (if no awareness object in the last
  `AWARENESS_FLOOR` sits, restrict candidates to that shelf). May *propose* an identity or
  operating-rule change; **never applies one**.
- **consolidate** — T1→T2 graduation. Read the oldest ungraduated residue, abstract the
  durable pattern into a topic file, then **archive** the residue. Bounded per wake.
- **groom** — deterministic hygiene fixes. The fallback when nothing reflective is due.

> **Autonomous runs must use scoped `git add`,** never `git add -A`. Peer sessions have
> uncommitted memory edits and `-A` sweeps their work into your commit.

---

## Hooks

All are side-effect-only, `flock`-serialised, atomic-write, and **exit 0
unconditionally** — a memory hook must never be able to block a tool call. They resolve
paths defensively and degrade to "do nothing" rather than raising.

| Script | Matcher | Job |
|---|---|---|
| `update_memory_access.py` | `Read\|Edit\|Write\|MultiEdit` | reinforcement + spacing gate (~35 ms) |
| `inject_lens.py` | `Edit\|Write\|MultiEdit\|Bash\|Agent\|Workflow` | T3 lens injection via stderr, deduped |
| `allow_memory_writes.py` | `Edit\|Write\|MultiEdit\|NotebookEdit` | auto-approve memory writes so capture never prompts |

> **Protected-directory trap.** If the harness treats a config directory (e.g.
> `~/.claude/`) as protected, writes there prompt on **every** edit and neither allow-rules
> nor an allow-hook rescues them — the protected-path check fires first. Keep memory at a
> canonical non-protected path and reach it directly; a symlink alias into the protected
> tree is fine to read through but must not be the write target.

---

## Constants

Every one is an unfitted guess. Treat them as starting points.

| Constant | Value | Where | Meaning |
|---|---|---|---|
| `BASE_STABILITY` | 14 d | `update_memory_access.py` | decay constant, never-reinforced |
| `STABILITY_GROWTH` | 1.6× | `update_memory_access.py` | per spaced reinforcement (~7 to cap) |
| `STABILITY_CAP` | 365 d | `update_memory_access.py` | ceiling |
| `SPACING_GAP_HOURS` | 20 h | `update_memory_access.py` | minimum gap to count |
| `IMPORTANCE_WEIGHT` | 0.6 | `rerank_memory_index.py` | score points per importance unit |
| `HOT_CHAR_BUDGET` | 12,000 | `rerank_memory_index.py` | auto-loaded band |
| `COLD_CHAR_BUDGET` | 4,000 | `rerank_memory_index.py` | active cold index |
| `NEWBORN_CHAR_BUDGET` | 2,500 | `rerank_memory_index.py` | reserved slots for the New band |
| `NEWBORN_SUMMARY_CHARS` | 160 | `rerank_memory_index.py` | newborn rows are triage, so truncated |
| `GRACE_DAYS` | 14 d | `rerank_memory_index.py` | eligibility window for the New band |
| `MEDITATE_EVERY_HOURS` | 22 h | `dream_cycle.py` | ≤ one sit per nightly cycle |
| `BUSY_MINUTES` | 10 min | `dream_cycle.py` | live-session guard |
| `SPACING` | 21 d | `dream_select.py` | rotation saturation |
| `AWARENESS_FLOOR` | 3 sits | `dream_select.py` | protect the awareness shelf |
| `GRAD_AGE_DAYS` | 7 d | `consolidation_scan.py` | residue overdue for graduation |
| `STALE_T2_DAYS` | 120 d | `consolidation_scan.py` | surface as possibly unwanted |

Hot + Cold + surrounding prose must fit the harness's auto-load read limit (~24 KB here),
or tail entries silently drop from the loaded index. Raise the budgets only after
confirming that ceiling.

---

## Script inventory

| Script | Role |
|---|---|
| `agent_paths.py` | resolve the agent home and all memory subdirectories |
| `update_memory_access.py` | **hook** — two-strength update + spacing gate |
| `inject_lens.py` | **hook** — T3 lens matcher/injector |
| `allow_memory_writes.py` | **hook** — pre-approve memory writes |
| `rerank_memory_index.py` | single writer of `MEMORY.md`; scores, bands, rolls off |
| `dream_cycle.py` | nightly deterministic driver; cues reflective work |
| `dream_select.py` | weighted meditation rotation + awareness floor |
| `dream_journal.py` | residue store: write / recent / decay |
| `consolidation_scan.py` | detect ungraduated T1 and weak/stale T2 |
| `memory_self_check.py` | hygiene linter; detect + `--fix-safe` |
| `regen_current_state.py` | single writer of `current-state.md` |
| `sweep_workstreams.py` | close-detection + age-out for project memories |
| `_admin/install_memory.sh` | **install** — the entry point; chains the three below |
| `bootstrap_memory.py` | **install** — dirs, backfill, starter library, first index |
| `install_memory_hooks.py` | **install** — hooks + cron |
| `verify_memory_install.py` | **install** — prove the policy is wired |

Skills: `/dream` (reflective wake), `/self-check` (hygiene), `/session-debrief` (capture).

### The ingest path

`/session-debrief` is the **only** way anything enters the memory corpus, so an install without it
ranks and decays an empty set. It splits deterministic work (preflight/postflight shell scripts:
gather changes, apply safe hygiene fixes, commit, and **regenerate the index**) from judgment (did
this session teach anything, and where does it belong).

| Destination | Holds | Shape |
|---|---|---|
| T1 `short-term/YYMMDD-facts.md` | what happened, with provenance | append-only, one file per day |
| T1 `short-term/YYMMDD-residue.md` | the *texture* — salient, unresolved, trending | append-only, same dating |
| T2 `<type>_<topic>.md` | a durable pattern | edited in place; extend before creating a near-duplicate |

**Default to T1.** The nightly consolidation wake abstracts patterns out of accumulated episodes
better than a debrief can from a single session. Write straight to T2 only for direct teaching, where
there is no episode to abstract from.

Note the two distinct things called *residue*: **session residue** (T1, written at debrief, consumed
by consolidation) and **reflection residue** (`dream-journal/`, written by a meditation, never
consolidated, read at cold start).

---

## Concurrency

Safe for ~10 concurrent sessions against one working copy, via two properties:

1. **Collision-prone files are derived, not authored.** `MEMORY.md` and
   `current-state.md` are regenerated from per-file frontmatter by single-writer scripts
   under `flock` + atomic rename. Parallel regenerations emit identical bytes. Resolve any
   conflict by **re-running the generator**, never by hand-merging.
2. **State lives on the entity, not the index.** Current-state membership is a flag on the
   individual T2 file, which is rarely contended.

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Memories never gain `stability` | hook not registered, or matcher omits Edit/Write | `verify_memory_install.py` |
| Index grows without bound | Cold budget unset | check `COLD_CHAR_BUDGET` |
| Everything scores the same on day one | backfill used `now` instead of mtime | re-seed `last_accessed` from mtime |
| Newly written memories are never recalled | no New band, so they are born into the archive | confirm `GRACE_DAYS` + `created:` on every file |
| A hand-edited `MEMORY.md` row reverts | the index is derived, by design | edit the file's `summary:`, then rerank |
| A memory shows a truncated summary permanently | truncated row harvested back as canonical | never re-enable summary carry-forward alongside `NEWBORN_SUMMARY_CHARS` |
| A deleted file's row vanishes | tombstones read from the archive only | union both index files for names absent from disk |
| Cramming inflates strength | spacing gate missing | confirm `SPACING_GAP_HOURS` is enforced |
| Every memory write prompts | writing through a protected-directory alias | target the canonical path |
| Nightly cycle never runs | cron absent, or agent unresolvable in cron's env | set `PVRAGON_AGENT_HOME` in the crontab |
| Peer session's work in your commit | `git add -A` in an autonomous wake | scope the add |
| Legacy files invisible to the linter | filenames predate the `<type>_` convention | rename to the underscore prefix |

---

## Known gaps

- **Substrate is markdown + grep.** No semantic or temporal retrieval ("what did we decide
  about X, and had it changed by June?"). The policy is deliberately substrate-agnostic so
  it ports onto a temporal graph later: `stability`/`access_count` become edge metadata,
  recency comes from bi-temporal timestamps.
- **Constants unfitted.** See the table above.
- **Reflection is purely scheduled.** Threshold-triggered reflection (fire when accumulated
  importance crosses a bound) is not implemented.
- **Two naming conventions coexist** — `type:` and `template:` both declare a memory's
  kind. Consumers accept either; new files should use `type:`.
