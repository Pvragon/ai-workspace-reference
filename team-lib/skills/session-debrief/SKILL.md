---
name: session-debrief
description: "End-of-session procedure that captures learnings into memory topic files, verifies index consistency, updates current-state.md, and syncs changes to team-lib."
summary: "Run at end of a work session to persist learnings, check index health, update workspace current state, and propagate improvements to team-lib. Uses preflight/postflight scripts for speed and reliability."
version: 2.14.1
created: 2026-02-20
last_updated: 2026-07-31
maintainer: pvragon
---

> **Where to edit this.** my-lib is where this skill is worked on; team-lib holds the published
> copy teammates install. The two are **byte-identical** — there is no generalized derivative and
> no transform step, because this file names no operator, no agent directory and no layer: agent
> paths resolve through `$AGENT_MEMORY`/`$AGENT_HOME` (bound from preflight below) and the skill's
> own scripts through `~/.claude/skills/session-debrief/`, which points at whichever layer the
> reader installed. So **any** difference between the two copies is real drift, not expected
> divergence — fix it by re-copying from my-lib, never by editing team-lib directly.

# Session Debrief

Run this skill at the end of a work session to capture learnings and maintain workspace hygiene.

**Architecture:** Deterministic work is pushed to shell scripts (`preflight.sh`, `postflight.sh`). The LLM focuses only on judgment-requiring work (memory, state updates, summaries). This makes the debrief faster and more reliable.

## Phase 1: Preflight (deterministic)

Run the preflight script to collect all session data in one pass:

```bash
bash ~/.claude/skills/session-debrief/preflight.sh
```

This outputs a JSON report with:
- **`git_changes`** — files changed, recent commits, which registered dirs were touched
- **`registry_issues`** — files missing from registries or registry entries pointing to missing files
- **`sync_needed`** — AGENTS.md or skills that changed and also exist in team-lib
- **`stale_flags`** — current-state.md health (stale entries, pending notes, old decisions)
- **`memory_issues`** — MEMORY.md index inconsistencies (unindexed files, broken links)
- **`session_info`** — date, approximate timestamps, memory index line count, **and a `session_marker` token you must pass to postflight**

**Read the report carefully before proceeding.** It tells you exactly what needs attention.

**Grab `session_info.session_marker`** — you'll pass it to postflight so it can deterministically identify the current session's JSONL (needed for setting the /resume title correctly when multiple concurrent sessions exist).

### Path variables — resolve these once, from preflight

The rest of this skill refers to agent paths by variable. **Bind them from the preflight report;
never substitute a path you inferred, remembered, or pattern-matched from an example.**

| Variable | Bind from | What it is |
|---|---|---|
| `$AGENT_MEMORY` | `t1_files_staged.memory_dir_canonical` | the canonical agent memory dir |
| `$AGENT_HOME` | the parent of `$AGENT_MEMORY` | the agent's home (`memory/`, `handoffs/`, `transcripts/`, `system-state/` live under it) |

> **Why variables rather than a literal path.** Preflight computes these for *whichever* agent is
> running, so they are correct by construction — a literal path is only ever correct for one
> operator, and this file is published to team-lib byte-for-byte. It also keeps the two layers
> genuinely identical, so any difference between them is real drift rather than expected
> divergence. The memory paths specifically are load-bearing for the no-prompt guarantee below:
> guessing one reintroduces the permission-prompt regression, which is exactly why they are bound
> to a computed value instead of written out.

## Phase 2: LLM Judgment Work — parallel fan-out

With the preflight report in hand, work through these items. Most of the heavy lifting is delegated to **parallel Sonnet subagents** — the main agent (Opus) does session-summary synthesis + orchestration only.

### 2a. Auto-fixable preflight issues (sequential, usually empty)

Skim `registry_issues` and `memory_issues` from the preflight report:
- **`unregistered`** — Add the file to the appropriate `registry/*.yaml` row
- **`missing_file`** — Remove the stale entry
- **`unindexed`** — Add a row to `MEMORY.md` with a one-line summary

These are usually trivial. Apply them inline. If a finding is ambiguous (unclear category, unclear purpose), defer to the relevant subagent below.

### 2b. Compose session summary (3–5 sentences)

Read enough of the session to write a tight summary covering:
- What was the **goal** / starting question?
- What was **decided / built / discovered**?
- What's left **open**?

This summary primes the parallel subagents — they don't need to re-scan the full session for context. Keep it in your context window for use in 2c.

### 2c. Parallel subagent fan-out (memory + state + session-log/pulse)

**Spawn THREE subagents in a single tool-call message** so they run concurrently. All three use `model: "sonnet"` (per AGENTS.md Op #7 — these are scoped, narrow tasks). Use `general-purpose` subagent_type for full tool access. You do NOT need to pass any permission `mode` — the no-prompt guarantee comes from path + hook, not from the spawn mode (which in-process teammates don't honor per-spawn anyway).

> **🔑 Delivery contract — spawn SYNCHRONOUS, not background (root-caused 2026-07-14).**
> Debrief fan-outs repeatedly "hung": agents finished their disk work but went idle
> without reporting, because BACKGROUND teammates' plain final text is NOT delivered
> to the main agent — the mailbox harness requires an explicit `SendMessage` to
> `main`, which "your final message is the deliverable"-style prompts never trigger.
> (Observed 5/6 agents on 2026-07-14: 3 research agents + debrief-log + debrief-memory
> all completed silently; each needed a manual nudge. debrief-state additionally DIED
> silently — vanished from TaskList with no work landed.)
>
> **🚫 DO NOT pass `name:` on these Agent calls (root-caused 2026-07-30).**
> A named agent is **addressable for continuation** via `SendMessage({to: name})`, so it does not
> terminate and return — it finishes its task, stays alive as a peer, and emits
> `idle_notification / idleReason: "available"`. Its final text goes to the **mailbox**, not back
> as a tool result. Naming them is tempting because it makes them easy to refer to; it silently
> costs you the delivery contract.
>
> Measured, same skill, same `run_in_background: false`, one parameter different:
>
> | Run | `name:` passed | idle notifications | reports delivered |
> |---|---|---|---|
> | 2026-07-22 | no | 0 | **3 of 3** |
> | 2026-07-30 | yes | 8 | **1 of 3** |
>
> `run_in_background: false` works. It was **not** the problem — an earlier version of this note
> claimed it "did not hold" and blamed the harness. That was wrong, and wrong in the expensive
> direction: it would have taught every future debrief to stop expecting reports at all.
>
> **Fix, in order of preference:**
> 1. **Pass `run_in_background: false` and NO `name:`.** Three unnamed synchronous spawns in a
>    single message run concurrently and return their final text as tool results. This is the
>    documented contract and it works.
> 2. If a spawn must be background or named, its prompt MUST end with: "MANDATORY FINAL STEP:
>    deliver this report via SendMessage to 'main' — your plain final text is NOT visible to the
>    orchestrator."
> 3. Either way, treat agent reports as claims: Phase 2e verifies artifacts ON DISK, and the
>    findings-file contract below carries observations regardless of what the mailbox does.

> **🔑 No-prompt guarantee — ROOT CAUSE & FIX (verified empirically 2026-06-25).**
> The recurring memory-write permission prompts were NOT a missing allow-rule and NOT a spawn-`mode` problem. **Root cause: `.claude/` is a PROTECTED directory.** `permissions.allow` rules do not pre-approve writes anywhere under `.claude/`, and the memory dir `~/.claude/projects/<cwd>/memory` is a symlink *into* `.claude/`. So any memory write through that alias path prompts on every Edit/Write — regardless of allow-rules, regardless of permission mode, and a PreToolUse allow-hook **cannot** rescue it (the protected-dir check fired even with the hook returning `allow` — tested directly).
>
> **The fix is two layers, and BOTH matter:**
> 1. **Always write memory via the CANONICAL agent memory dir** (preflight emits the exact
>    absolute path as `t1_files_staged.memory_dir_canonical`) — NEVER the `~/.claude/projects/<cwd>/memory` alias. The canonical path is non-protected and allow-listed. Preflight now emits canonical absolute paths in `t1_files_staged`; **when you compose the subagent prompts below, hand them canonical `$AGENT_MEMORY/…` paths only.** This is the load-bearing rule — getting it wrong is exactly what caused the regression.
> 2. **A PreToolUse auto-allow hook** (`team-lib/executions/allow_memory_writes.py`, registered in `~/.claude/settings.json`) force-allows Edit/Write/MultiEdit whose `realpath` lands under any `memory/` dir within `~/ai-workspace` — making canonical memory writes frictionless in ANY permission mode (even plan/restrictive) and for in-process teammates. It defers (no-op) for everything else, so it doesn't over-broaden.
>
> Net: with canonical paths, neither the main agent nor the teammates prompt on memory writes. The subagents do no git / no network mutation / no destructive Bash (postflight does all git in the main agent), so there is nothing else for them to be prompted on.

Pass each subagent the preflight report (full JSON), the session summary from 2b, and its specific scope. Each returns a brief confirmation + any required outputs (pulse message, lens candidates, etc.). The main agent (Opus) waits for all three to return.

> **🔑 Findings must land on disk, not only in reports (added 2026-07-30).**
> Phase 2e verifies work ON DISK and deliberately doesn't wait on reports — correct, and it
> must stay that way. But disk-verification can only ever see **files**, never **observations**.
> On 2026-07-30 the single most important finding of the whole session — that new memories are
> born invisible, ranking #125 of 612 against ~49 visible slots — existed *only* in a subagent's
> report. No grep would have found it. It arrived after the debrief reported "complete" and
> would have died silently if the window had been closed.
>
> **The contract:** every subagent's LAST disk action, before it returns, is appending its
> findings to its OWN file:
>
> ```
> ~/ai-workspace/my-lib/runtime/.tmp/YYMMDD-debrief-findings-<agent>.md
> ```
>
> **One file per agent, never a shared one.** Three concurrent appenders to a single file is the
> exact contention class this architecture already solved twice (per-workstream `cs_section`
> flags; single-writer renderer). Don't reintroduce it here for tidiness.
>
> **`runtime/` is gitignored, so these files are TRANSPORT, not capture.** Nothing in `.tmp`
> survives; postflight will not stage it. Anything worth keeping must be promoted by the main
> agent in 2e into T1 facts or a memory file, or the finding still dies — just one step later
> than before. Promotion is the step that actually closes this gap.

#### Subagent A — Memory Capture

Prompt template:

```
You are a memory-capture subagent for this workspace's session-debrief.

PREFLIGHT REPORT:
<paste full JSON>

SESSION SUMMARY (from main agent):
<paste 3-5 sentence summary>

YOUR TASK — capture this session's content into the 5-tier memory architecture
(see $AGENT_MEMORY/project_memory-architecture-layers.md
for the full framing — especially §"T2 workstream-lifecycle metadata" for the
status / last_touched / resolves_when / resume_via fields):

**⚠️ PATH RULE (non-negotiable — this is the exact thing that re-fires permission prompts):**
EVERY memory file you touch — facts, residue, `project_*.md`, `MEMORY.md`, topic files — must be
written via an ABSOLUTE path under the CANONICAL memory dir.

**Bind `$AGENT_MEMORY` = the value of `t1_files_staged.memory_dir_canonical` in the preflight
report above.** Preflight computes it for whichever agent is running, so it is correct by
construction. Do NOT substitute a path you inferred, remembered, or pattern-matched — if the
field is missing from the report, stop and say so rather than guessing.
So `memory/project_<name>.md` MEANS `$AGENT_MEMORY/project_<name>.md`, and `MEMORY.md`
MEANS `$AGENT_MEMORY/MEMORY.md`. **NEVER** write through a
`~/.claude/projects/<cwd>/memory/…` path — that alias resolves to the SAME file, but its literal
`.claude/` prefix trips the protected-dir permission gate, which the allow-hook CANNOT rescue (the
gate fires before the hook's `allow`). Every bare `memory/…` reference in the steps below means
`$AGENT_MEMORY/…`. Getting this wrong on `MEMORY.md`/`project_*.md` is exactly the
regression that prompted during debrief on 2026-06-26.

1. T1 facts — append a `## HH:MM — <session-name>` block to the file at
   preflight.t1_files_staged.facts_path. Bullet-list the *specific facts*
   surfaced (decisions, observations, numbers, file:line refs). Date-keyed,
   provenance-bearing. Frontmatter is already there — append below the existing
   content, do not rewrite the file.

2. Residue — append a `## HH:MM — <session-name>` block to the file at
   preflight.t1_files_staged.residue_path. Use exactly this format:
     **Direction:** <1 sentence — where things were trending>
     **Unresolved:** <1 sentence — what's open / pending>
     **Salient:** <1 sentence — what felt important / surprising>
   Hard cap ~500 tokens. Texture, not facts.

3. T2 workstream-lifecycle updates — for each project/workstream this session
   actively touched, find or create its `memory/project_<name>.md` and update
   the lifecycle frontmatter:
     - `last_touched: YYYY-MM-DD` (today)
     - `status` if it changed this session:
         * `in-flight` — being driven this week
         * `handed-off` — ball is in someone else's court now (Roman, Areeba,
           PR reviewer, etc.)
         * `follow-on` — known cleanup item with no external trigger date
         * `archived` — resolved this session; no longer needs re-entry context
     - `resolves_when: <trigger>` — required for handed-off and follow-on.
       Free-text condition the session-log will eventually report. Example:
       "any session reports Stage 2 apply complete OR ClickUp 868jka9tx closed".
     - `resume_via: <path/command/link>` — single most useful cold-start pointer.
   ALSO append a one-liner to the file body under a `## Recent activity` section
   if the session changed substantive state.

4. T2 close/age sweep — run the deterministic sweep, then report what it changed:

       python3 ~/ai-workspace/team-lib/executions/sweep_workstreams.py --apply

   It scans every `memory/project_*.md` and uses each file's frontmatter:
     - **Pathway 1 (close detection, corpus-wide):** evaluates the `close_signal`
       list against LIVE sources (ClickUp task status via API, GitHub PR state via
       `gh`, file/grep markers). Any satisfied signal → flips `status: archived` +
       appends a note. This catches closes that happened in ANY thread at ANY time
       — it queries real state, not the last-5 session-log window.
     - **Pathway 2 (dormancy, corpus-wide):** any still-open item older than
       `--age-days` (default 20) and not `pin: true` → flips `status: dormant`.
       A workstream untouched for four weeks is closed: not finished, not queued,
       moved on from. No backlog stub, no disposition step, no review — nothing is
       required of anyone. The T2 file and its MEMORY.md row stay exactly where
       they are, so ordinary recall still finds it. Dormancy removes an item from
       ATTENTION, never from MEMORY.
     - **Pathway 3 (revival):** a dormant item whose `last_touched` moves past its
       `dormant_since` returns to `in-flight` automatically — working on it IS the
       revival signal. `--revive NAME` forces it without an edit. This is what makes
       closing on a timer safe, so never treat dormancy as a decision to agonise
       over: a wrong one costs one edit to undo.
   Read the JSON it prints and surface `closed_by_signal`, `went_dormant`,
   `revived`, `needs_attention`, and `errors` in your return so the user sees what
   left current-state and why.

   Then, for items still open that have NO machine-checkable `close_signal`, do the
   legacy soft check: grep the last 5 session-log entries against `resolves_when`;
   on a clear match, flip `status: archived` + append a `## Archived YYYY-MM-DD`
   note. When you set up/adjust a handed-off or follow-on item in step 3, add a
   `close_signal:` wherever an objective trigger exists (`clickup:<id>`,
   `pr:<owner>/<repo>#<n>`, `file:<path>`, `grep:<path>::<regex>`) so pathway 1 can
   retire it automatically later, from whatever thread eventually closes it.

5. T2 topic files / reusable assets — only if the session produced a
   CROSS-SESSION pattern worth reusing. Most sessions do not. Two sub-cases:
   (a) a reusable *fact/pattern* → create/update `memory/<topic>.md` + MEMORY.md row.
   (b) a reusable *method / procedure / template* (a multi-step workflow, a
       scoring rubric, an orchestration shape, a how-to) → this is **T2
       procedural knowledge, NOT a lens**. Note it as a "reusable-method
       candidate"; if it has a concrete artifact (e.g. a workflow script),
       suggest generalizing that artifact into a skill / Workflow template
       rather than a memory file. Gate on a SECOND use case before generalizing.
   Heuristic: if you want to write "during this session..." — it's T1, NOT T2.

6. Lens candidates (T3/T4) — ONLY surface something as a lens candidate if it
   passes ALL THREE clauses of the placement rule in
   `project_memory-architecture-layers.md` §"Placement rule (T2 vs T3 vs T4)":
   (i)  it's a LENS that colors how you INTERPRET inputs — not a fact to look up,
        and not a method/procedure you apply;
   (ii) forgetting it would cause a WRONG decision, not merely a slower or
        less-rigorous one;
   (iii) for T3, a tight `tool_match` + `path_pattern` can fire it only when it
        matters (if it applies everywhere, it's T4).
   If it fails ANY clause, it is NOT a lens — route it to step 5 instead (T2
   fact, or reusable-method/template). In particular, a reusable workflow /
   orchestration pattern, a scoring rubric, or a how-to procedure is **T2, not a
   lens** — surfacing those as lens candidates is the common mistake this step
   exists to prevent. DO NOT promote; return passing items as "Lens candidates"
   so the main agent can surface to the user. Lens promotion is always
   deliberate human curation.

FINAL DISK ACTION — do this LAST, before you return. Not optional.
Append your findings to
`~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-memory.md`
(create it if absent; YYMMDD = today's date). Format:

    ## memory — HH:MM
    - <finding>

A FINDING is something the orchestrator could NOT learn by grepping the files you
wrote: a surprise, a contradiction, a measurement, a number that looks wrong, a rule
that fired when it shouldn't have, a gap you had to work around, a thing you believe
is broken. If you genuinely have none, write `- none`. Do NOT log routine chatter —
"wrote 3 files", "sweep ran clean" is already visible on disk and is noise here.
Your report may never be read; this file will be.

WHAT TO RETURN (last lines of your response):
- "Files written: <comma-separated list of repo-relative paths>"
- "Workstreams updated: <name=status, ...>"
- "Workstreams archived (resolves-when fired): <names, or 'none'>"
- "Reusable-method candidates (T2): <list, or 'none'>"
- "Lens candidates (T3/T4): <list, or 'none'>"
- "MEMORY.md updated: <yes/no>"

What to do, what NOT to do:
- DO append to existing T1 files (frontmatter present)
- DO update T2 lifecycle fields aggressively — current-state.md depends on them
- DO create T2 topic files when the workstream is meaningful enough to track
- DO NOT modify AGENTS.md, CLAUDE.md, identity.md (T3/T4 — return as candidates only)
- DO NOT touch current-state.md or session-log.md (other subagents own those)
```

#### Subagent B — Current State Update

Prompt template:

```
You are a current-state-update subagent for this workspace's session-debrief.

PREFLIGHT REPORT:
<paste full JSON — pay attention to stale_flags + git_changes>

SESSION SUMMARY (from main agent):
<paste 3-5 sentence summary>

YOUR TASK — refresh current-state.md as a **thin INDEX over T2 project files**.
current-state.md is now DERIVED: you do NOT hand-edit it. You set per-workstream
flags on the T2 files, then run the single-writer renderer. This is the concurrency
fix — parallel debriefs can no longer clobber the file (see
`project_memory-architecture-layers.md` §"Concurrency model").

🚫 **NEVER edit current-state.md directly.** The renderer
(`executions/regen_current_state.py`) is its only writer (flock + atomic). Editing
it by hand reintroduces the clobber bug and will be overwritten.

The workstream membership + line text live on each T2 file's frontmatter:
- `cs_section: in_flight | handed_off | follow_on`  (presence ⇒ shown in that section)
- `cs_headline: "**Name** — <≤25-word status>"`     (the exact rendered line; link derived)

WORKFLOW:

**Bind `$AGENT_MEMORY` = the value of `t1_files_staged.memory_dir_canonical` in the preflight
report above** — every memory file named below lives under it. Do not infer a path.

1. **Read the 5 NEWEST entries from `$AGENT_MEMORY/session-log.md`** (top of file, just below the
   `<!-- entries below -->` marker — "last 5" reads as file-tail and produced a bogus staleness
   signal on 2026-07-14) — the signal for what's actually active.

2. **For each workstream this session touched:** on its T2 file set/update
   `cs_section` + `cs_headline` (In Flight = actively driven; handed_off = ball in
   someone else's court; follow_on = parked cleanup). Keep the headline ≤25 words —
   depth belongs in the T2 body, not the index. This is a per-file edit, so two
   sessions touching different workstreams never collide.

3. **Demote/remove — decide from `last_touched`, not from the session log.** For every
   item carrying `cs_section: in_flight`, apply exactly this predicate:

       demote if (today − last_touched) > 14 days     [missing last_touched counts as stale]

   Nothing else demotes an item. In particular, **how many session-log entries mention
   it is irrelevant** — one session's work is still work. Two worked examples, one on
   each side:
     - `last_touched: <today>`, mentioned in exactly **one** of the newest 5 session-log
       entries → **stays In Flight.** It was touched today.
     - `last_touched: <32 days ago>`, mentioned in **three** entries → **demotes.** Stale
       is stale no matter how much it was discussed.

   > **Why the predicate, and why not to "improve" it back into prose:** this paragraph
   > has produced three separate wording bugs. The last one — *"wasn't touched in ≥2 of
   > the last 5 session-log entries"* — inverted the rule, requiring 2+ mentions to
   > *survive*. On 2026-07-30 that would have demoted both surviving In Flight items,
   > each touched that same day — the subagent noticed the rule was backwards, silently
   > reinterpreted it as a staleness filter, and was right. Relying on the reader to
   > correct the instruction is not a control. `last_touched` is machine-readable frontmatter
   > that the sweep stamps and the renderer already sorts on. Read the field; don't
   > re-derive staleness by grepping prose.

   Demote by changing `cs_section` to `handed_off`/`follow_on`, or delete
   `cs_section`/`cs_headline` to drop it from the index entirely (state stays in the T2
   body). The close/age sweep (Subagent A pass 4) already cleared `cs_section` on
   anything it archived/backlogged, so those fall out automatically.

   > **Re-check `git status` for NEW untracked `project_*.md` immediately before you render,
   > not just at the start.** Subagent A runs concurrently and may create this session's
   > dedicated T2 file *after* you have already picked a home for the session's flags. On
   > 2026-07-30 that happened: flags were set on an older generic file, A then created the
   > dedicated one, and the only signal was an untracked file in `git status` — A sent no
   > notification. Caught and corrected before the render; it would otherwise have put the
   > session's headline on the wrong workstream.

4. **The In Flight cap of 5 is enforced by the renderer — you do not have to count.**
   If more than 5 items carry `cs_section: in_flight`, it keeps the 5 freshest by
   `last_touched` and emits a line naming the ones it withheld (it will not silently
   truncate). That line appearing in the output means the stalest items still need a
   real disposition via step 3 — the cap is a backstop, not a substitute for it.

5. **Render** — this WRITES the file, and is the only step that does:

       python3 ~/ai-workspace/team-lib/executions/regen_current_state.py \
         --today YYYY-MM-DD \
         --add-decision "YYYY-MM-DD: <decision from this session>" \
         --add-note "<1-3 items pointing at the next actual work, or omit>"

   Pass one `--add-decision` per decision worth logging (it prepends, prunes >14 d,
   caps ~10). Pass `--add-note` per note, or `--clear-notes` to reset. Blockers are
   preserved verbatim; omit unless you need to change them. The three workstream
   sections + `Last updated` are rebuilt deterministically from the T2 flags.

   **Both flags are idempotent — re-running with the same text is a no-op.** Don't
   grep to check whether a decision already landed; you cannot do it correctly, because
   a concurrent writer can commit between your check and your write. The script does
   the check inside its flock, where it is race-correct.

FINAL DISK ACTION — do this LAST, before you return. Not optional.
Append your findings to
`~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-state.md`
(create it if absent; YYMMDD = today's date). Format:

    ## state — HH:MM
    - <finding>

A FINDING is something the orchestrator could NOT learn by grepping the files you
wrote: a surprise, a contradiction, a measurement, a rule that fired when it
shouldn't have (say so — the demotion predicate in step 3 has been wrong three
times), an item you demoted that you suspect is actually live, a gap you had to work
around. If you genuinely have none, write `- none`. Do NOT log routine chatter.
Your report may never be read; this file will be.

WHAT TO RETURN (last lines):
- "current-state.md updated: yes/no"
- "In Flight count: <N>"
- "Items demoted: <count> (<workstream → section>...)"
- "Items archived/removed: <count>"
- "Flagged for user attention: <list, or 'none'>"
```

#### Subagent C — Session Log + Pulse Compose

Prompt template:

```
You are a session-log + pulse-compose subagent for this workspace's session-debrief.

PREFLIGHT REPORT:
<paste full JSON — note session_info.approx_start and .end>

SESSION SUMMARY (from main agent):
<paste 3-5 sentence summary>

SESSION NAME: <name from /rename, or 2-4 word descriptive name if unrenamed>

YOUR TASK:

**Bind `$AGENT_MEMORY` = the value of `t1_files_staged.memory_dir_canonical` in the preflight
report above.** It is computed for whichever agent is running. Do NOT infer a memory path: writing
through a `~/.claude/projects/<cwd>/memory/…` alias instead trips the protected-dir permission gate
on every write, which the allow-hook cannot rescue. If the field is missing, stop and say so.

1. Append ONE LINE (not a paragraph) to $AGENT_MEMORY/session-log.md
   immediately after the `<!-- entries below -->` marker (newest at top):
     YYYY-MM-DD | <session-name> | <key topics/outcomes>

   **STRICT FORMAT: ≤200 characters total, single physical line, no line breaks.**
   This convention drifted to multi-paragraph essays causing 156KB→26KB cleanup
   2026-05-04. If you have more to say, write it to `short-term/YYMMDD-facts.md`
   (where verbose detail belongs) and keep this entry to a one-line headline.

2. Compose the pulse-channel debrief message in this exact format:
     JH Claude Debrief [<start time> - <end time>]: <summary>
   Use session_info.approx_start and .end for the time range. Summary is
   1-3 sentences covering outcomes, decisions, next steps.

FINAL DISK ACTION — do this LAST, before you return. Not optional.
Append your findings to
`~/ai-workspace/my-lib/runtime/.tmp/<YYMMDD>-debrief-findings-log.md`
(create it if absent; YYMMDD = today's date). Format:

    ## log — HH:MM
    - <finding>

A FINDING is something the orchestrator could NOT learn by grepping the files you
wrote: a surprise, a contradiction, a session-log entry that contradicts what the
summary claims, a timestamp that looks wrong, a gap you had to work around. If you
genuinely have none, write `- none`. Do NOT log routine chatter.
Your report may never be read; this file will be.

WHAT TO RETURN (last lines):
- "session-log.md updated: yes"
- "PULSE_MESSAGE: <the full pulse message — single line, no trailing newline>"
```

### 2d. Sync to Team-Lib (only if needed)

If `sync_needed` is non-empty:
- **`agents_md`** → Run the `push-agents-to-template` skill.
- **`skill:<name>`** → Review whether the changes should propagate. Only promote stable, generally-useful changes; workspace-specific tweaks stay in my-lib.

Most sessions skip this entirely.

### 2e. Confirm and proceed — verify ON DISK, not by report

Do NOT trust (or wait on) subagent self-reports — verify the artifacts directly
(fast greps, one Bash call):
- Subagent A: today's `## HH:MM — <session>` block present in BOTH `short-term/YYMMDD-facts.md`
  and `-residue.md`; touched `project_*.md` files have `last_touched: <today>`.
- Subagent B: `current-state.md` line 1 `Last updated: <today>` and this session's
  workstream headline present.
- Subagent C: today's one-line entry present in `session-log.md` after the marker.

**Then READ the findings files — this is the other half of the on-disk check:**

```bash
cat ~/ai-workspace/my-lib/runtime/.tmp/$(date +%y%m%d)-debrief-findings-*.md 2>/dev/null
```

Artifact-greps prove work *happened*; the findings files are the only channel through which
what an agent *noticed* reaches you. Treat a missing file the same as a missing artifact —
the agent didn't complete its contract; check whether its other work landed.

**Promote anything worth keeping — `runtime/` is gitignored, so these files do not survive.**
For each finding, one of three dispositions, and do it now rather than "later":
- **Durable pattern or a thing that is broken** → append to today's `short-term/YYMMDD-facts.md`
  (canonical memory path), or a T2 topic file if it's a cross-session pattern. This is what
  makes it survive.
- **Actionable but not yet decided** → a `my-lib/backlog/YYMMDD-<slug>.md` item.
- **Routine/noise** → drop it silently.

Then **route each promoted finding into the findings inbox** rather than reporting it at
close:

```bash
python3 ~/ai-workspace/team-lib/executions/findings.py record \
  --source debrief --key "<stable-slug>" --text "<one line>" [--severity critical]
```

**Only `--severity critical` is surfaced in Phase 4** — a breaking bug, data loss, or a live
production risk. Everything else waits in the inbox behind an ambient statusline count and a
`findings.py list` pull.

> **Why the close is the wrong moment (the operator, 2026-07-30).** These findings are legitimate
> and were being surfaced at the exact point where context is highest and we are actively
> trying to end a thread — *"basically like someone saying 'ok I need to go' and the person
> they say it to saying 'wait but also this this and this'."* Session start is no better: you
> arrive with a goal and get derailed before touching it.
>
> So the queue is never announced. It is read when there is space, on a pull.
>
> **Keep writing findings to disk exactly as before.** The disk write is what made findings
> survive at all; only the READ moved. Narrowing what subagents record would restore the
> precise failure this replaced — an observation dying with the window.
>
> Most of what this filter suppresses is the debrief auditing ITSELF — races between its own
> concurrent subagents, its own preflight window. That is telemetry, and it was never work
> for the user.

**Enrich the active handoff brief, if there is one.** When this debrief follows a `/handoff`,
the brief was written and the new window spawned BEFORE you ran — so everything you just
surfaced is invisible to the session that inherits the work unless you put it there.

1. **Locate the brief.** In order:
   - The path the caller gave you ("enrich the brief at …"). `/handoff` step 5 passes it
     explicitly; this is the only method that cannot pick the wrong brief.
   - Else `$AGENT_HOME/handoffs/.pending-enrichment/*.json` — use it
     **only if exactly one entry is < 6 h old.** If two or more are, ABSTAIN: name the
     candidates to the user and append nothing.
   - Else nothing. Skip this step; it is not an error.
   - **Never pick the newest file in `handoffs/`.** 60+ briefs live there and sibling sessions
     fork their own the same day — on 2026-07-30 another thread's brief sorted above the
     relevant one within hours. Guessing here writes into the wrong thread's instructions.

2. **Append, never rewrite.** Add ONE section at the very end of the brief:

   ```markdown
   ## Debrief addendum — YYYY-MM-DD HH:MM

   Surfaced by the originating session's debrief, after this brief was written.

   - <finding, and what it changes about the work queue above>
   ```

   Append-only, because a human may have edited the brief since it was written and the new
   session may already have read it. Do not touch the work queue, the startup checklist, or
   anything above your section — if a finding invalidates a queue item, say so *in the
   addendum* ("item 5 is likely moot — …") rather than editing the item.

3. **If nothing was surfaced, append nothing.** An empty addendum trains the next session to
   stop reading them.

4. **Consume the pointer** — delete the `.pending-enrichment/*.json` entry you used, so a later
   debrief doesn't re-enrich a stale brief.

Failure handling (root-caused 2026-07-14; refined same day):
- **Idle-without-report but work on disk** → fine; compose the pulse message yourself
  from the 2b summary (its format is fully specified). Don't ping-pong nudges.
- **No artifacts + not in `TaskList`** → CAUTION: a slow in-process teammate can be
  INVISIBLE to TaskList while still running (observed: "dead" debrief-state delivered
  10 min later, racing the main agent's inline fallback). The inline fallback is still
  right — user-facing progress beats waiting — but make it RACE-TOLERANT: re-check the
  target files immediately before writing, and treat an "file modified since read" Edit
  error as probable concurrent completion (re-read, keep whichever version is correct,
  don't duplicate). A late report from the "dead" agent may arrive — reconcile, don't
  re-apply.
  **`regen_current_state.py --add-decision/--add-note` is safe to re-run** as of
  2026-07-30 — exact-duplicate text is a no-op, checked inside the flock. The old
  warning here asked you to grep first, which cannot work: a concurrent writer can
  commit between your check and your write, which is precisely how both decisions and
  both notes duplicated that day. Don't reintroduce the warning; the tool owns it now.
- Never re-run the agents whose writes already landed.
- Prompt-wording note: say "the 5 NEWEST session-log entries (top of file, just below
  the marker)" — "last 5 entries" reads as file-tail (oldest) and produced a bogus
  staleness signal on 2026-07-14.

Collect:
- Pulse message string from Subagent C (you'll pass it to postflight as `--pulse-message`)
- Lens candidates (T3/T4) and reusable-method candidates (T2) from Subagent A — surface to the user before postflight, but do NOT act on them automatically. Reusable-method candidates (workflows, rubrics, procedures) are T2 and gate on a second use case; only genuine interpretive lenses that pass all three placement-rule clauses should be offered for T3/T4 promotion.

**Touched-files enumeration is now AUTOMATED.** Postflight runs `executions/extract_touched_files.py` against the session JSONL to derive `--mylib-files` and `--agents-files` automatically. You no longer need to track them manually. (The flags are still accepted as overrides if you need surgical control over what gets staged.)

### Quality discipline (parallel-fan-out version)

The fan-out trades main-agent quality for wall-clock speed. To preserve quality:
- The session summary in 2b is load-bearing — make it specific, not generic. "Architectural memory rework + transcript extractor + 3 backlog items shipped + 2 commits pushed" beats "discussed memory and made commits."
- If a subagent's output looks weak or off-axis, re-spawn it with sharper input rather than rewriting the output yourself in the main context.
- **The fan-out is the pattern. There is no stakes-based fallback** — a clause telling you to go serial for "unusually high-stakes sessions (cross-team commits, architecture decisions, public-facing artifacts)" lived here until 2026-07-30 and was deleted. It never once fired: the 2026-07-30 session met all three of its criteria and the fan-out ran anyway, because the trigger asked for a judgment call at the end of a long session, which is exactly when judgment is worst. What actually went wrong that day was two *mechanical* failures — duplicate writes and findings stranded in agent reports — and both are now closed in the tools (idempotent renderer, 2c.5 findings files). A rule that never fires and cannot be falsified is worse than no rule, because it reads as a safeguard. If a fallback is ever wanted again, make preflight detect the condition and say which mode to use; don't ask the tired operator.

## Phase 3: Postflight (deterministic)

Run the postflight script with the composed pulse message. **File-list args are now OPTIONAL** — postflight auto-extracts touched files from the session JSONL via `executions/extract_touched_files.py`.

Default invocation:

```bash
bash ~/.claude/skills/session-debrief/postflight.sh \
  --session-name "<session-name>" \
  --session-marker "<value from preflight's session_info.session_marker>" \
  --pulse-message "<debrief message from Subagent C>"
```

**Optional overrides** (only when you need surgical control — e.g., excluding a file from the commit, or bypassing autodetection):
- `--mylib-files "backlog/foo.md skills/bar/SKILL.md"` — explicit override; pass `""` to skip my-lib commit
- `--agents-files "memory/foo.md"` — explicit override; pass `""` to skip agents commit

**IMPORTANT:** Pass `--session-marker` from the preflight report's `session_info.session_marker`. Postflight will grep JSONLs for that marker to identify the current session deterministically — no guessing, safe with any number of concurrent sessions. (`--session-id <uuid>` is still accepted as an explicit override if you already know the UUID.)

This handles in one pass:
1. Workspace hygiene — removes WSL `*:Zone.Identifier` junk files across `~/ai-workspace` (via `executions/clean_zone_identifiers.sh`)
1b. **Session transcript extraction** (added 2026-04-30) — runs `executions/extract_session_transcripts.py` to convert any new/updated session JSONLs into filtered markdown transcripts at the agent's `transcripts/`. Idempotent, stdlib-only, ~97% size reduction. Skipping is non-fatal.
1c. **System state dump** (added 2026-04-30) — runs `executions/dump_system_state.py` to refresh git-backed snapshots at the agent's `system-state/` (crontab, Claude Code hooks, settings, MCP servers). Pairs with `my-lib/context/indexed/active-systems.md` (manual overview). Idempotent — only stages diffs when infrastructure actually drifted. Skipping is non-fatal.
1e. **Fleet snapshot** (added 2026-07-24) — preflight fires `executions/session_snapshots.py store --tag debrief --keep 40` in the background, recording which Claude sessions are **OPEN** right now (`/resume-sessions` rebuilds from these). Debrief time is exactly when a workstream rotates generation via `/handoff`, which is what rots the nightly midnight snapshot between reboots. **This cannot be reconstructed from the JSONL logs after the fact:** log mtime shows *activity*, not openness, so an open-but-idle window is indistinguishable from a closed one — and the only record of session *names*, `~/.claude/sessions/<pid>.json`, is PID-keyed and gets overwritten as PIDs are reused after each reboot. `--tag debrief` prunes in its own retention bucket, so frequent debrief snapshots never evict the nightly `--auto` ones. Non-fatal. Origin: 2026-07-24 WSL/VS Code restart — the 00:00 snapshot pointed at waystar `-13` / mahjong-constituents `-4` while `-14` / `-5` were the live windows.
1d. **Transcript archive** (added 2026-06-11) — runs `executions/archive_old_transcripts.sh` to move session JSONLs older than 14 days out of `~/.claude/projects/` (→ `projects-archive/`, move-not-delete) so the statusline's ccusage meter can't re-parse a multi-GB corpus → swap-thrash → freeze. Self-throttles to ≤once/24h (stamp file), idempotent, non-fatal. See memory `reference_ccusage-statusline-swap-thrash-crash`.
2. Session title prepend (custom-title at line 1 of session JSONL for /resume)
3. Claude adapters (symlinks + config backup)
4. Agent identity repo commit + push — auto-stages `transcripts/` + `system-state/` from steps 1b/1c on top of `--agents-files`
5. my-lib repo commit, no push (only the files in `--mylib-files`)
6. Pulse channel post

**Title logic:** If the user did `/rename`, uses that name verbatim. Otherwise, prepends `YYMMDD-HH:MM <session-name>` to the JSONL head so `/resume` shows a meaningful name.

**Options:**
- `--mylib-files "<paths>"` — **REQUIRED** unless `--skip-commit` or `--legacy-add-all`. Space-separated repo-relative paths to stage for the my-lib commit. Pass `""` to skip that repo cleanly.
- `--agents-files "<paths>"` — **REQUIRED** unless `--skip-commit` or `--legacy-add-all`. Same shape as `--mylib-files`, for the agents identity repo.
- `--legacy-add-all` — Escape hatch: revert to the old `git add -A` catch-all behavior. **Use only when explicitly justified** (e.g., recovering after extensive uncommitted work that genuinely all belongs to this debrief). Logs a prominent warning. Prefer explicit file lists.
- `--session-marker "<token>"` — Marker from preflight output; resolves to the current session's UUID via JSONL grep (**preferred**)
- `--session-id "<uuid>"` — Explicit session UUID (skip marker lookup; use only if you already know it)
- `--skip-pulse` — Skip posting (e.g., if the user declines)
- `--skip-commit` — Dry run (adapters only, no git commits — also bypasses the file-list requirement)

## Phase 4: Confirm

Summarize to the user what was updated:
- Memory topic files modified or created
- Registry/index corrections made
- What changed in current-state.md
- Whether anything was synced to team-lib
- Git commit results (agents repo + my-lib)
- Any items flagged for attention
- **CRITICAL findings only** — a breaking bug, data loss, or a live production risk. Report
  those in full. Everything else went to the findings inbox and must NOT be listed here.
  On a clean run, say nothing at all about findings. A close-out is for leaving, not for
  opening new work.

**Then, LAST, the stale-findings offer.** Run:

```bash
python3 ~/ai-workspace/team-lib/executions/findings.py escalations --json
```

If it returns anything, add **one line at the very end** — an offer, never the content:

> *"There are N findings waiting, oldest Xd. Want me to open a session to go through them?"*

If yes, spawn a dedicated window:

```bash
bash ~/.claude/skills/handoff/handoff.sh findings-worklist \
  --seed "Run /findings and work the list with me." --dir ~/ai-workspace/my-lib
```

> **Why an offer and not a report (the operator, 2026-07-31).** Every earlier attempt put the
> findings themselves somewhere inside a live thread — at close, at start, at a Stop hook —
> and all of them derail, because there is no good moment to hand someone new work inside
> work they are already doing.
>
> An offer is different in kind. It opens nothing. It costs one line and one word to decline,
> and if accepted the work happens in a session that exists only for it, competing with
> nothing. **Do not list the findings here even if it seems helpful** — the moment you name
> three of them, the close-out has become the thing this design exists to prevent.
>
> Only `escalations` (really old, or critical) triggers the offer. A fresh inbox stays
> silent; the ambient statusline count is doing its job.
- Whether a handoff brief was enriched with a `## Debrief addendum` (and which one), or why not
- Session-log entry added
- Pulse debrief posted (or skipped)
