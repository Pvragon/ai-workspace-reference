---
name: team-lib-currency
description: Audit and repair drift between the personal library (my-lib) and the shared library (team-lib) — the copies a teammate actually installs. Runs the deterministic layer-drift scan, then decides direction PER ITEM (graduate, pull back, merge, or declare intentionally divergent) and applies it. Use when the nightly dream cycle has cued drift_due, before onboarding someone onto team-lib, after landing a change to workspace documentation / architecture / background tooling / registries, or when asked whether team-lib is current.
summary: "The resolver half of layer-drift detection. layer_drift_scan.py finds divergence deterministically every night; this skill supplies the judgment the scan deliberately withholds — which layer is right for each item — and applies the fix under the graduation-is-a-move convention. Detection is scheduled; resolution is task-triggered."
version: 1.0.0
created: 2026-07-30
last_updated: 2026-07-30
maintainer: pvragon
---

# /team-lib-currency — keep the shared library current

`team-lib` is what a teammate installs. When it drifts behind `my-lib`, nobody
gets an error — they just quietly run an older system. On 2026-07-30 every one of
the five skills present in both layers had diverged, three of them at **identical
version numbers**, so nothing about the metadata looked wrong.

The detector (`executions/layer_drift_scan.py`) runs nightly inside the dream
cycle and answers *what differs*. This skill answers *which way each difference
should go* — a judgment call that must never be automated, because the answer is
routinely "pull the shared copy back into my-lib" or "these are supposed to
differ," not "copy my-lib over team-lib."

## When to run

- The dream cycle set `drift_due` (check: `dream_cycle.py --status`).
- Before pointing anyone at team-lib for onboarding.
- After changing workspace documentation, system architecture, background tooling
  (hooks, crons, executions), or registries — the surfaces that MUST be mirrored.
- On request ("is team-lib current?").

## Procedure

### 1. Scan

```bash
python3 ~/ai-workspace/team-lib/executions/layer_drift_scan.py --severity med
```

Read the whole report before touching anything. `--severity info` also lists
never-graduated and shared-only items; those are inventory, not defects.

Findings you will see:

| Kind | Means |
|---|---|
| `silent-drift` | Content differs, metadata does not. The dangerous one. |
| `known-drift` | Content and versions both differ. Visible, unreconciled. |
| `derived-behind` | A generalized shared copy is missing whole sections. |
| `pair-missing` | A declared mirror does not exist in one layer. |
| `registry-dangling` | A registry entry points at nothing. |
| `ungraduated` | Personal-layer only. Usually fine — most things should stay local. |
| `declared-divergent` | Accepted. Someone declared it on **both** sides. |

### 2. Decide direction per item — do NOT assume team-lib is the stale one

For each finding, open **both** copies and diff them. Then pick one:

- **Graduate (my-lib → team-lib)** — the capability is proven and generally
  useful. Do it as a **MOVE**: copy to team-lib, then archive the my-lib copy
  under `my-lib/archive/YYMMDD-graduated-to-team-lib/` with a README pointing at
  the live location. Leaving the personal copy in place is exactly what lets the
  two drift again, and AGENTS.md prohibits executing anything under `archive/`,
  so archiving makes the cutover enforced rather than merely intended.
- **Pull back (team-lib → my-lib)** — the shared copy is ahead. This happens more
  than people expect; check before assuming.
- **Merge** — each layer has something the other lost. Diff in both directions
  before copying either way. A blind copy here silently deletes a fix.
- **Declare divergent** — the difference is intentional. Add to the frontmatter of
  **BOTH** files:

  ```yaml
  mirror: divergent
  mirror_reason: >-
    <what differs and why it must stay that way>
  ```

  One-sided declarations are rejected by the scan on purpose. An undocumented
  intentional difference is indistinguishable from rot.
- **Declare local** — a personal-layer file that should never graduate gets
  `mirror: local`, which silences the `ungraduated` finding for it.

Before graduating anything, check it against `directives/team-library-governance.md`
§3 "Definition of Done" — no operator-specific paths, names, hosts, or secrets.
A copy that carries those does not belong in the shared layer.

### 3. Watch for derived files

Some shared files are a **generalization** of a personal one, not a copy — the
agent template is `my-lib/AGENTS.md` with the agent name, the operator's name,
and operator-specific repo/host policies stripped out. `mirror.yaml` marks these
`policy: derived` and the scan compares section structure instead of content.

**Never `cp` a derived file.** Port the substance of the missing sections and
generalize as you go, then confirm nothing leaked:

```bash
grep -nEi '<operator-name>|<agent-name>|<private-host>|/home/[a-z]+' \
  ~/ai-workspace/team-lib/context/indexed/templates/template-agent-automation-user.md
```

### 4. Update registries in the same commit

Any file you moved, added, or renamed must be reflected in that layer's
`registry/*.yaml` (AGENTS.md operating principle 6). For a graduated file, replace
the personal-layer entry with a comment pointing at the new location rather than
deleting it silently — the next reader needs to know where it went.

Re-run the scan; `registry-dangling` must be clear.

### 5. Verify, then record

```bash
python3 ~/ai-workspace/team-lib/executions/layer_drift_scan.py --severity med
python3 ~/ai-workspace/team-lib/harnesses/test_layer_drift_scan.py
python3 ~/ai-workspace/team-lib/executions/dream_cycle.py --record-drift-review
```

The harness matters: it proves the scan can still *fail*. A detector that has
quietly stopped detecting reports the same "clean" as a healthy one.

Commit each layer separately with a scoped message saying which direction each
item went and why. Push only on explicit go-ahead.

### 6. If you deferred something

Recording the review clears `drift_due` even when findings remain. If you left
work behind, say so in the commit and write it down — a cleared flag with an
unwritten follow-up is how this rots in the first place.

## What NOT to do

- **Don't bulk-promote.** Most of the personal layer should stay personal; a skill
  graduates when it is proven and generally useful, not because it exists.
  Currency is the goal, not volume in team-lib.
- **Don't "fix" the registries' entry counts.** team-lib's skills registry counts
  `_external` submodule skills, so it legitimately exceeds the top-level directory
  count. The check that matters is whether entries resolve on disk.
- **Don't resolve drift from inside the nightly tick.** Detection is deterministic
  and scheduled; resolution is reasoning and stays task-triggered. That split is
  what keeps the daily sleep the only clock-scheduled reasoning in the system.
- **Don't edit shared files without checking `/who`** — several sessions routinely
  share `my-lib@main`, and this skill touches files other threads may own.

## Related

- `executions/layer_drift_scan.py` — the detector
- `registry/mirror.yaml` — the mirror contract and declaration syntax
- `harnesses/test_layer_drift_scan.py` — proves the detector can fail
- `directives/team-library-governance.md` — what qualifies for the shared layer
- `my-lib/directives/graduate-to-team-library.md` — the graduation SOP
