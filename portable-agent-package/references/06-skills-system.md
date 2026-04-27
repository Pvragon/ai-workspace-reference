---
template: portable-agent-reference
version: 0.1.0
summary: "What a skill is and isn't. SKILL.md frontmatter and structure. When to extract a skill from inline work. Skill registry; precedence order (local > internal > external). Skill vs. directive vs. persona vs. script — the boundaries."
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
runtime_neutral: true
---

# 06 — Skills System

A skill is a **reusable capability bundle**: a procedure (`SKILL.md`) plus the supporting files that make it executable (templates, schemas, sub-agent prompts, scripts). Skills are the unit of "I built a thing once; now I can invoke it by name forever."

## What A Skill Is

```
~/lib/skills/<skill-name>/
├── SKILL.md            ← the procedure (entry point; frontmatter + body)
├── references/         ← reference docs the skill loads on demand
│   └── *.md
├── agents/             ← sub-agent prompts spawned by the skill
│   └── *.md
├── scripts/            ← execution scripts the skill calls
│   └── *.py
└── state/              ← if the skill is stateful (Ralph-style), state files live here
    └── *.json
```

The skill name is **invokable**. In a Claude Code-shaped runtime: `/skill-name`. In other runtimes: a tool name, a command, a function. The label varies; the encapsulation is the point.

## The SKILL.md Structure

```markdown
---
name: weekly-vendor-scrape
description: Weekly vendor price scrape; outputs CSV diff vs. last week with movement-threshold alerts.
summary: "One-line summary for index aggregation."
version: 1.0.0
created: 2026-04-27
last_updated: 2026-04-27
maintainer: pvragon
argument-hint: "[--vendors <path>] [--alert-threshold <pct>]"
related:
  - executions/scrape_vendors.py
  - executions/diff_vendor_snapshots.py
---

# weekly-vendor-scrape

One-paragraph orientation: what this skill does, when to invoke it, what it produces.

## Inputs
- `--vendors`: path to vendor list CSV (default: `data/vendor_list.csv`)
- `--alert-threshold`: pct change to flag (default: 5)

## Outputs
- `runtime/deliverables/YYMMDD-vendor-prices.csv`
- `runtime/deliverables/YYMMDD-vendor-deltas.csv`
- Slack alerts if any movement > threshold

## Procedure

### Step 1 — Pre-flight
- Confirm `--vendors` file exists; bail with clear message if not.
- Confirm last-week's snapshot exists; if not, this is a first-run — note it and skip diff.

### Step 2 — Scrape
Run `executions/scrape_vendors.py --input <vendors>` → snapshot CSV.

### Step 3 — Diff
Run `executions/diff_vendor_snapshots.py --new <today> --old <last_week>` → deltas CSV.

### Step 4 — Alert
If any delta > threshold, post via `executions/post_alert.py`.

### Step 5 — Archive
Move last-week's snapshot to `_archive/`.

## Anti-patterns
- Don't fetch prices yourself — the script handles retries/rate-limiting.
- Don't skip Step 3 even if today's snapshot looks fine — alerts are downstream.
- Don't run on a public holiday without confirming vendors are open.

## Edge cases
- Vendor X uses JS-rendered prices; the script falls back to Playwright.
- Vendor Y's site is unstable; rate-limited retry is built-in.
```

**Required structure rules:**

1. **Frontmatter has `name`, `description`, `summary`.** `name` is what the runtime invokes. `description` is what the agent sees in the skill list. `summary` is for index aggregation.
2. **Inputs and Outputs sections.** Explicit. Always.
3. **Procedure is numbered, not paragraphs.** Each step is a discrete action.
4. **Anti-patterns and Edge cases sections.** Skills accumulate scar tissue. Document it.

## When To Extract A Skill

You extract a skill when **all three** are true:

1. You've done this work at least twice.
2. The shape is the same each time (inputs, outputs, procedure).
3. Some of the steps require LLM judgment (otherwise it's just a script).

Otherwise:

- Same shape, no LLM judgment → just a script (`executions/`).
- LLM judgment but never going to repeat → don't formalize.
- Repeating but each time is different → maybe a directive (the *what*, not the *how*).

## Skill vs Directive vs Persona vs Script

This is the question most new agents get wrong. The boundaries:

| | Directive | Skill | Persona | Script |
|---|---|---|---|---|
| **Form** | Markdown SOP | Markdown procedure + bundle | Markdown identity profile | Python/Node/Go |
| **Purpose** | Defines what + why for a recurring process | Reusable capability with steps + tooling | Stable identity (style, expertise, risk tolerance) | Deterministic work |
| **LLM involved?** | Yes — agent reads, routes | Yes — agent invokes, executes | Yes — agent loads as voice/role | No — deterministic |
| **Stateful?** | Usually no | Optional (`state/`) | No | Optional |
| **Composes?** | Calls scripts and skills | Calls scripts; may load personas; may spawn sub-agents | Loaded by skills/directives | Called by scripts/skills/directives |

**One rule that resolves most confusion:** a directive is *what to do*; a skill is *how to do something*; a persona is *who is doing it*; a script is *the deterministic part of the doing*.

A weekly vendor scrape can be all four:

- **Directive** "weekly-vendor-monitoring.md" says "every Monday at 9am, run the vendor scrape and triage alerts."
- **Skill** "weekly-vendor-scrape" packages the multi-step procedure (scrape, diff, alert, archive).
- **Persona** "vendor-analyst" defines the voice for alert messages and the threshold for "this matters."
- **Script** `scrape_vendors.py` deterministically fetches the prices.

You can have any of these without the others if the task doesn't warrant them.

## The Skill Registry

A YAML manifest of all skills, machine-readable, single source of truth:

```yaml
# registry/skills.yaml
# summary: All available skills, source-tagged for precedence resolution.
# last_updated: 2026-04-27

skills:
  - name: weekly-vendor-scrape
    path: skills/weekly-vendor-scrape/SKILL.md
    source: local              # local | internal | external
    summary: Weekly vendor price scrape; outputs CSV diff vs. last week
    tags: [scraping, finance, weekly]

  - name: humanizer
    path: skills/_external/blader-humanizer/SKILL.md
    source: external
    summary: Remove signs of AI-generated writing
    tags: [writing, polish]
```

When the agent searches for a skill, it consults this registry before scanning the filesystem.

## Skill Precedence

When multiple skills could match a request, resolve in this order:

1. **Local** (`./skills/`) — workspace-specific
2. **Team internal** (`team-lib/skills/` excluding `_external/`) — your team's custom skills
3. **Team external** (`team-lib/skills/_external/`) — third-party submodules

Internal skills always beat external skills with similar names. If a third-party "brand-guidelines" skill exists and your team has one too, your team's wins. The external one might do generic work; yours encodes your specific brand.

> **Why precedence matters:** as you install third-party skill libraries, name collisions are likely. Without explicit precedence, the agent picks the wrong one and you get mysterious wrong outputs.

## Sub-Agents Inside Skills

Skills frequently spawn sub-agents. Two cases:

### Case A — Deterministic role separation (council pattern)

```
skill: code-review
  ├── agents/security-reviewer.md
  ├── agents/maintainability-reviewer.md
  └── agents/perf-reviewer.md
```

The skill spawns one sub-agent per persona, in parallel. Pattern from [05-multi-agent-patterns.md](05-multi-agent-patterns.md).

### Case B — Context absorption

```
skill: full-app-test
  └── agents/playwright-driver.md
```

The skill spawns a sub-agent for the heavy task (browser automation, full repo scan) so the parent's context stays clean.

In both cases, the sub-agent prompt is **a Markdown file in the skill's `agents/` directory**, not inlined in the SKILL.md. This makes prompts versionable, diff-able, and reusable across skills.

## State Files

Some skills are stateful — they iterate, resume, or accumulate. State files live in `skills/<name>/state/<run-id>.json`:

```json
{
  "run_id": "260427-vendor-scrape-001",
  "stage": "diff",
  "started_at": "2026-04-27T09:00:00Z",
  "vendors_scraped": 47,
  "alerts_pending": 3,
  "snapshot_path": "runtime/deliverables/260427-vendor-prices.csv"
}
```

The skill writes state at every checkpoint. On resume (`--resume <run-id>`), it reads state and jumps to the right stage. This is the Ralph-loop resume property applied at skill granularity.

## When To Externalize / Open-Source A Skill

A skill graduates from `local/` to `team-lib/skills/` (or to a public repo) when:

- It's been stable for 2+ weeks of real use.
- It has explicit Inputs, Outputs, Anti-patterns, Edge cases sections.
- At least one team member other than the author has invoked it successfully.
- It doesn't depend on anything in `personal/` (the skill must be portable).

The graduation step is a PR. Treat the skill as library code.

## Common Skills To Build Early

Skills you'll want regardless of domain:

| Skill | Purpose |
|---|---|
| `session-debrief` | Update memory, current-state, commit; runs at session end |
| `init-project` | Scaffold new project with standard docs structure |
| `find-skill` | Search the registry by keyword (avoids re-deriving capabilities) |
| `code-review` | Multi-reviewer council for PRs |
| `harness` | The Ralph-loop pattern from [03-harness-design.md](03-harness-design.md) |
| `humanizer` | Strip AI-tells from human-facing prose (mandatory pre-delivery filter) |

These compose. A `release-notes` skill might invoke `humanizer` as a final step. An `oncall-triage` skill might invoke `code-review`.

## Anti-Patterns

| ❌ Anti-pattern | ✅ Correct |
|---|---|
| Inlining a 5-step procedure in conversation, every time | Extract to a skill once, invoke by name |
| One huge "general-purpose" skill | One narrowly-scoped skill per capability; compose them |
| Skill names that don't say what they do | `weekly-vendor-scrape`, not `vendor-thing` |
| SKILL.md missing Inputs/Outputs/Anti-patterns | All three are non-negotiable |
| Skill ignores the registry; runs by filesystem path | Skill is registered; agent invokes by name |
| External skill silently overrides internal one | Precedence enforced; internal wins |
| Sub-agent prompt inlined in SKILL.md text | Sub-agent prompts in `agents/<role>.md` |
| Skill depends on user's `~/.bashrc` aliases | Skill is hermetic; uses absolute paths and explicit env |
| State stored in chat | State stored in `state/<run-id>.json`; resumable |
| Skill builds for a year before first invocation | Build minimum viable; iterate via real use |

## Bootstrap Checklist

- [ ] `skills/` directory exists with at least one real skill (not a stub).
- [ ] That skill has SKILL.md with name, description, summary, version + Inputs / Outputs / Procedure / Anti-patterns / Edge cases.
- [ ] `registry/skills.yaml` lists the skill with source-tag and tags.
- [ ] Operating instructions tell the agent: "consult registry before improvising; load SKILL.md in full when invoked."
- [ ] At least one skill has been invoked end-to-end successfully.
- [ ] At least one skill has been updated based on real-use feedback (version bumped).
