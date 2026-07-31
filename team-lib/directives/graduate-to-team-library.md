---
template: directive
version: 2.0.0
summary: "How a capability graduates from the personal layer to the shared one. Graduation is a MOVE, never a copy: skills move and are symlinked back, files move and the personal copy is archived behind a pointer. Pre-flight refuses a graduation that would leave the shared layer holding a fragment. Run team-lib/executions/graduate_capability.py."
created: 2026-01-15
last_updated: 2026-07-31
maintainer: pvragon
---

# Directive: Graduate a Capability to the Shared Library

**Purpose:** move a proven capability from the personal layer (`my-lib`) into the
shared layer (`team-lib`), so teammates get it — without creating drift or
shipping something they cannot use.

---

## The two rules that matter

### 1. Graduation is a MOVE, not a copy

Two copies have no owner for the diff. Both stay individually valid while the
*comparison* silently rots. Measured 2026-07-30: `session-debrief` sat five minor
versions behind in team-lib, missing the memory groom and index rerank entirely,
so a teammate installing from team-lib captured memories that never got an index
row. Nothing detected it for weeks — and three of five shared skills had drifted
at **identical version numbers**, so metadata could never have revealed it.

So the personal copy stops existing:

| Kind | How it moves | Why |
|---|---|---|
| **Skill** (a directory) | moved to team-lib, then **symlinked back** | `~/.claude/skills` is a symlink to `my-lib/skills`, the only tree the harness scans. A plain move silently **uninstalls** the skill. |
| **Execution / directive** (a file) | moved, personal copy **archived** with a README pointer | `archive/` is prohibited from execution, so the cutover is *enforced*, not merely intended. |

### 2. A capability graduates WHOLE, or not at all

A capability can appear as several kinds sharing a stem: `findings.py` (an
execution), `findings/` (a skill), `findings.md` (a directive). Graduating one
kind and leaving its siblings ships a fragment.

That is not hypothetical. On 2026-07-31 team-lib held `findings.py`, its two
clocks and its statusline segment, with no `/findings` skill to work the list —
so findings accumulated and nothing could drain them. File-level drift detection
is blind to this: there is no pair to compare, so it produces **zero** findings.

The rule is about **shared-layer completeness**, not personal-layer purity. A
personal skill driving a shared execution is perfectly legitimate. What is not
legitimate is the shared layer shipping half a thing.

---

## Procedure

### 1. Pre-flight (dry run — the default)

```bash
python3 ~/ai-workspace/team-lib/executions/graduate_capability.py skills/<name>
```

It refuses on:

- **split capability** — siblings of the same stem would stay behind;
- **operator identifiers** — the agent name, the operator's name or username;
- **personal-layer code dependency** — the shared copy would not be standalone
  (writing to `my-lib/runtime/**` is fine; every install has a personal layer);
- **content conflict** — it already exists in team-lib with different content,
  compared by **content hash, never by version**.

Fix what it reports. `--force` exists for a deliberate split; if you use it,
record why in the commit.

### 2. Apply

```bash
python3 ~/ai-workspace/team-lib/executions/graduate_capability.py skills/<name> --apply
```

### 3. Update BOTH registries — same commit

The registries are hand-curated YAML with prose, so this step is deliberately not
automated. Remove the entry from the personal registry, leaving a **pointer
comment** rather than a silent deletion, and add it to the shared registry. Then:

```bash
python3 ~/ai-workspace/team-lib/executions/layer_drift_scan.py --tree registry
```

`registry-dangling` must be clear. That check validates path-shaped
`dependencies:` entries too — three skills once pointed at paths that no longer
existed and a `path`-only check called the registry clean.

### 4. Verify, then commit

```bash
python3 ~/ai-workspace/team-lib/executions/layer_drift_scan.py --severity med
```

Run the thing from its new home before believing it moved. Post-move verification
is what caught `session_snapshots.py` importing `list_claude_sessions`, which had
been left behind — review had not.

Commit each layer separately, saying which direction each item went and why.
**Push is the only step needing explicit go-ahead.** At push, `version_gate.py`
re-runs the split-capability check as a backstop and warns loudly, because the
graduation script is bypassable by hand and a gate nobody invokes catches nothing.

### 5. Publish

If it should reach the public reference repo:

```bash
python3 ~/ai-workspace/team-lib/executions/publish_public_reference.py --apply
```

---

## Not eligible

Secrets, client-specific work, personal projects, machine-specific context, and
anything under `runtime/`. Most of the personal layer should stay personal —
graduation is for what is **proven and generally useful**. Currency is the goal,
not volume in team-lib.

## Related

- `team-lib/executions/graduate_capability.py` — the tool
- `team-lib/executions/layer_drift_scan.py` — detection, incl. split-capability
- `team-lib/registry/mirror.yaml` — the mirror + publication contract
- `team-lib/directives/team-library-governance.md` — what qualifies as shared
