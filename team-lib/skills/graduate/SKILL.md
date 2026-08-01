---
name: graduate
description: Move a proven capability from the personal library (my-lib) into the shared library (team-lib) so a teammate installs it — as a MOVE, never a copy. Runs graduate_capability.py's pre-flight (split detection, operator identifiers, personal-layer dependencies, content conflicts), interprets each refusal, applies the move, and verifies the layers agree afterwards. Use when a skill/execution/directive has proven itself locally and should become shared, or when the drift scan reports a never-graduated item worth promoting.
summary: "The judgment wrapper around graduate_capability.py. The tool refuses on four specific pre-flight conditions and each refusal means something different — this skill says which are real blockers, which are fix-then-retry, and which mean the item should not graduate at all. Enforces the half that keeps getting skipped: after graduation the personal copy stops existing."
version: 1.0.0
created: 2026-08-01
last_updated: 2026-08-01
maintainer: pvragon
---

# /graduate — promote a capability into the shared library

A capability is **born** personal (`my-lib/`) and enters `team-lib` only once it
has proven itself. The half that keeps getting skipped is the second one:
**graduating means the personal copy stops existing.**

Two copies have no owner for the diff. Both stay individually valid while the
*comparison* silently rots. Measured 2026-07-30: team-lib's `session-debrief` sat
five minor versions behind my-lib's, missing the memory groom entirely — so a
teammate installing from team-lib captured memories that never got an index row.
Three of five shared skills had drifted at **identical version numbers**, so
metadata could not have revealed it. On 2026-08-01 `choose-name` was found as a
real directory in both layers, the only one of 97 skills not symlinked back.

`executions/graduate_capability.py` does the mechanical move and refuses on four
pre-flight conditions. This skill supplies what the tool withholds: what each
refusal *means*, and whether the answer is fix-it, override, or don't graduate.

## When to run

- A local capability has proven itself and a teammate would benefit.
- `layer_drift_scan.py --severity info` lists a never-graduated item worth promoting.
- You are about to copy something into team-lib by hand. Stop and run this instead.

**When NOT to run.** Most of the personal layer should stay personal — 59
ungraduated items is correct by definition, not a backlog. Do not bulk-graduate.
Graduate one capability because someone needs it, never to reduce a number.

## Procedure

### 1. Dry-run the pre-flight

```bash
python3 ~/ai-workspace/team-lib/executions/graduate_capability.py skills/<name>
```

Dry run is the default. It reports REFUSED with reasons, or what it would move.

### 2. Interpret each refusal

| Refusal | What it means | What to do |
|---|---|---|
| `exists in the shared layer with DIFFERENT content` | Both layers have it and they disagree. This is drift, not graduation. | Resolve direction first with `/team-lib-currency`. If team-lib is already canonical, this is a **de-duplication**, not a graduation — collapse the personal copy to a symlink (see §4) rather than forcing the move. |
| `operator identifier /\bthe-operator\b/` | The content names a specific person or client, so it is not yet shareable. | Generalize the content, or decide it is legitimately personal and stop. Note that team-lib is ALSO published publicly — check `registry/mirror.yaml` `publication.scrub` before assuming a name is fine. |
| `personal-layer dependency` | It imports or calls something in `my-lib/` that the installer will not have. | Graduate the dependency first, or inline it. `my-lib/runtime/**` is NOT a defect — every install has a personal layer to write logs and scratch into. |
| `split capability` | Half of it already lives in team-lib. | Graduate the missing half in the same move. Splits are invisible to file-level drift — there is no pair to compare, so the scan reports zero. |

`--force` exists for a deliberate split you will record a reason for. Reaching
for it to silence any of the first three is how the layers rot.

### 3. Apply

```bash
python3 ~/ai-workspace/team-lib/executions/graduate_capability.py skills/<name> --apply
```

Skills graduate by **symlink**: `my-lib/skills/<name>` becomes a link to the
team-lib copy. `~/.claude/skills` → `my-lib/skills` is the only tree the harness
scans, so **archiving a skill silently uninstalls it**. Files archive under
`archive/` with a pointer; `archive/` is already prohibited from execution, which
makes the cutover enforced rather than merely intended.

### 4. Verify the layers agree

```bash
python3 ~/ai-workspace/team-lib/executions/layer_drift_scan.py --severity med
```

Expect **0 actionable**. Then confirm the capability still resolves **through the
harness's own tree**, not at its team-lib path — that walks the whole chain
(`~/.claude/skills` → the personal layer → team-lib) in one check:

```bash
head -3 ~/.claude/skills/<name>/SKILL.md
```

If that fails, the harness can no longer see the skill and you have uninstalled
it. Restore the symlink before doing anything else.

### 5. Update the registry and commit

Add the entry to `team-lib/registry/skills.yaml` (or `executions.yaml` /
`directives.yaml`) and remove the personal-layer entry. Commit the capability and
its registry entry **in the same commit** — they are one atomic change.

Push team-lib as its own command, never `git commit && git push` together: the
version gate is a PreToolUse hook, so a combined invocation shows it the state
before the commit exists.

## After graduation

- **Never edit the personal copy again.** Fix it in team-lib. If you find
  yourself patching both, you have already lost — collapse them first, then fix once.
- Deliberate divergence must be declared **two-sided** as `mirror: divergent` in
  `registry/mirror.yaml`, so an undeclared difference is always a bug.
- `layer_drift_scan.py` compares **body hashes, not versions**, and runs nightly
  in the dream cycle. That is what catches the identical-version case.

## Related

- `/team-lib-currency` — the resolver for drift that already exists. Run that
  when both layers have a copy; run this when only the personal layer does.
- `directives/graduate-to-team-library.md` — the full SOP this skill front-ends.
- `registry/mirror.yaml` — the contract: pairs, trees, exclusions, portability
  rules and their exemptions, publication include/exclude, scrub blocklist.
