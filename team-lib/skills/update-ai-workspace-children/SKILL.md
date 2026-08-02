---
name: update-ai-workspace-children
description: Walk the whole my-lib → team-lib → public promotion chain in one pass — tidy and document the personal layer, decide what graduates, validate the shared layer, regenerate and validate the public layer, then push in the order the gates require. Use before a release, when onboarding someone onto team-lib, when the nightly cycle cues drift, or when asked whether the three layers are in sync.
template: skill-definition
version: 1.0.3
summary: "The judgment half of the promotion chain. executions/workspace_chain_audit.py runs every deterministic gate; this skill decides what the gates cannot — which layer an item belongs in, what should graduate, what to document — and drives the chain end to end to a pushed, proven state."
created: 2026-08-01
last_updated: 2026-08-01
maintainer: pvragon
---

# /update-ai-workspace-children

## What this is

One pass over the promotion chain:

```
my-lib  ──graduate──▶  team-lib  ──publish──▶  ai-workspace-reference
(mine)                 (ours)                  (anyone's)
```

The model those arrows encode — what belongs in each layer, what never leaves, why each hop
is a filter and not a copy — is **§4.6–4.7 of `context/indexed/workspace-reference.md`**. Read
it before making any graduate/leave call. `registry/mirror.yaml` is the authoritative machine
contract; when the prose and the file disagree, the file wins.

**The deterministic gates are already a script.** `executions/workspace_chain_audit.py` runs
all of them read-only and returns one verdict. This skill exists for the part a script must
not do: deciding which layer is right for a thing.

## The one rule that governs every decision here

**Graduation is a MOVE, never a copy.** Two live copies have no owner for the diff — both stay
individually valid while the comparison silently rots. Measured: a shared skill sat five minor
versions behind its personal twin for weeks, and three of five shared skills had drifted at
*identical version numbers*, so metadata could not reveal it. If you find yourself patching
both, you have already lost; collapse them first, then fix once.

## Run it

### Phase 0 — where are we

```bash
python3 ~/ai-workspace/team-lib/executions/workspace_chain_audit.py
```

Also check `/who`: peers share `my-lib@main` constantly, and this skill edits shared files.
If a peer is busy in a layer you are about to change, coordinate first.

**Then check what branch `team-lib` is actually on.**

```bash
git -C ~/ai-workspace/team-lib branch --show-current    # expect: main
```

The shared checkout is *shared*. A peer can leave it on a feature branch, and did — measured
2026-08-01, `team-lib` sat on `fix/waystar-creds-canonical-location` with six unpushed commits.
Two things follow, and both bit before the guard existed:

- **Your commits land on their branch.** A commit made here goes to whatever is checked out.
  Cherry-pick it onto `main` from a throwaway worktree rather than switching the shared tree
  under a working peer:
  `git -C ~/ai-workspace/team-lib worktree add /tmp/tl-main main` → commit/push there → remove.
  **A worktree push is invisible to `version_gate`** — the hook parses the command text, and a
  path built from a shell variable does not resolve, so it now skips rather than versioning
  whatever repo the session happens to sit in. Run the floor by hand afterwards:
  `python3 executions/version_gate.py --reconcile`.
- **Publication reads the checkout, not `main`.** `publish_public_reference.py` now REFUSES a
  non-main checkout (exit 2) for exactly this reason; before that guard, a publish would have
  shipped an unreviewed feature branch to the public repo and nothing would have flagged it.

If team-lib is not on main: do Phases 1–2, report, and stop before Phase 4. Publishing is not
urgent; publishing someone's half-finished branch is unrecoverable in the way public things are.

Take the audit's verdict as the worklist. Everything below is how to clear it — **do not
re-derive the checks by hand**; that sequence living only in someone's head is why the script
exists.

### Phase 1 — tidy and document the personal layer

Deterministic first:

- Registry currency: every file in a registered directory has an entry, every entry resolves.
  The audit reports unresolved entries; the reverse (files with no entry) is a judgment call —
  a scratch script does not need one, a reusable tool does.
- Frontmatter: agent-consumable files need `template`/`version`/`summary`/`created`/
  `last_updated`/`maintainer`. A missing `summary:` is the expensive one — it is what the
  progressive-disclosure indexes render.
- `runtime/.tmp/` items older than two weeks move to `_archive/`. **Never purge.**

Then the judgment: anything in `.tmp` that has started receiving human review has stopped
being disposable and is a draft deliverable — move it to `runtime/deliverables/`.

### Phase 2 — decide what graduates

The audit prints the ungraduated count. **That number is not debt.** `my-lib` is a laboratory;
59 ungraduated items was the correct state on 2026-08-01. Do not bulk-graduate — the pressure
to "clear the list" is exactly how personal, half-finished, or client-specific work ends up in
the shared layer.

Graduate an item only when all of these hold:

1. **Proven** — it has run for real, more than once, and you can say what it did.
2. **Generic** — no operator name, no client scoping, no absolute path to one machine. Check
   with `~/.claude/skills/<name>/` rather than a `my-lib/` path, which walks the whole symlink
   chain and needs no portability exemption.
3. **Whole** — it does not depend on something staying behind in `my-lib`. The pre-flight in
   `graduate_capability.py` refuses a graduation that would leave the shared layer holding a
   fragment.
4. **Wanted** — a teammate would plausibly reach for it.

Then move it, do not copy it:

```bash
python3 ~/ai-workspace/team-lib/executions/graduate_capability.py skills/<name> --apply
# layer-relative paths, not bare names: `skills/foo`, `executions/foo.py`
```

If two copies must genuinely differ, declare it two-sided as `mirror: divergent` in
`mirror.yaml`. An *undeclared* difference is always a bug.

### Phase 3 — validate the shared layer

```bash
bash ~/ai-workspace/team-lib/_admin/validate.sh
python3 ~/ai-workspace/team-lib/executions/link_skills.py     # every shared skill invocable
bash ~/ai-workspace/team-lib/_admin/update_external_pack_pins.sh   # after any submodule bump
```

The audit covers the harnesses and registry resolution. What it cannot judge: whether a newly
graduated item's *documentation* is true. Read the thing you just moved.

### Phase 4 — regenerate and validate the public layer

```bash
python3 ~/ai-workspace/team-lib/executions/publish_public_reference.py --apply
```

Then re-run the audit. It scans every released file against the blocklist — the only true leak
test, because the source containing a client name is not the same fact as having exposed one.

Publication is a **total function**: any tracked root file in neither `include_files` nor
`exclude_files` is itself a finding, and an exclusion with no written reason is too. If you
excluded something new, write why.

**After a rename or a delete in team-lib, publish with `--prune`.** Publication is otherwise
add/overwrite-only, so a renamed file leaves its old name behind in the public repo forever —
two guides where there is one, and the stale one still reads plausibly. `--prune` deletes only
published files whose source is gone and never touches excluded paths. Renaming
`ONBOARDING.md` to `GETTING_STARTED.md` on 2026-08-01 is exactly this case.

### Phase 5 — push, in this order

```bash
cd ~/ai-workspace/team-lib && git push        # its own command, never `commit && push`
cd ~/ai-workspace/projects/ai-workspace-reference && git push
```

**Order is load-bearing.** `version_gate` is a PreToolUse hook on `git push`, so it stamps
versions as team-lib goes out; `publish_gate` then fires on that same push and regenerates +
commits the public layer. Pushing public first ships a layer that is already stale.
`git commit && git push` in one command blinds the version gate — the hook runs *before* the
command, so the commit it must inspect does not exist yet.

Pushing the public repo is a release. **Ask first** unless the user has already said so in
this conversation.

### Phase 6 — prove it, when it is a release

The audit proves consistency. It does not prove *installability* — for that, the container
harness installs from the actual bytes onto a box with nothing:

```bash
# see harnesses/public_workspace_container_test.sh for the staging ritual
# stage teamlib.bundle -> tests the teammate's path; omit it -> tests the stranger's path
```

Run both before a release. A host machine cannot see these failures: it already has the
toolchain, the submodules, the symlinks and a populated agent. The first run found that a
fresh install could invoke **none** of 97 shared skills.

## Report like this

```
CHAIN: <PASS|BLOCKED>
  my-lib     tidied: N archived, N documented; N ungraduated (unchanged / +N graduated)
  team-lib   validate ✅  harnesses ✅  N skills invocable
  public     N files, 0 leaks, regenerated at <sha>
  pushed     team-lib <sha> → public <sha>
  proof      team <n>/<n>, public <n>/<n>   (or: not run — consistency only)
```

State what you did NOT do. "Consistency verified, installability not re-proven" is a useful
sentence; silence in its place is not.

## Do not

- **Bulk-graduate to clear the ungraduated list.** It is not a queue.
- **Hand-edit the public repo.** It is generated; edits are overwritten and their loss is silent.
- **Grow the portability exemption list** to silence a finding you could rewrite around. It is
  printed with every scan as a trust signal — a clean result is only as good as that number.
- **Push the public repo without being asked.** Publishing to the world stays a human decision.
- **Treat a green audit as proof a stranger can install it.** Different claim, different gate.

## See also

- `context/indexed/workspace-reference.md` §4.6–4.7 — the layer model this skill enforces
- `directives/graduate-to-team-library.md` — the move mechanics
- `skills/team-lib-currency/SKILL.md` — the narrower drift resolver this generalizes
- `registry/mirror.yaml` — the contract, authoritative over all of the above
