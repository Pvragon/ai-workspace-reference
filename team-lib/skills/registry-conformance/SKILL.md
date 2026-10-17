---
name: registry-conformance
description: Bring a repo's registry/ manifests back into agreement with what is actually on disk — by REGENERATING the manifests that are derivable from file frontmatter and VALIDATING the ones that are not. Use when a registry looks stale, after adding or renaming indexed files, before a push that publishes a manifest, when a drift check reports non-zero, or when onboarding a repo that has manifests but no generator.
template: skill-definition
version: 1.5.0
summary: >-
  The judgment wrapper around build_registry.py and build_index.py (generate) and
  validate_registry.py (validate). Decides which of a repo's manifests are frontmatter-derivable
  and which encode human grouping judgement, interprets each refusal, and fixes the FILE rather
  than the index when they disagree.
created: 2026-08-08
last_updated: 2026-10-16
maintainer: pvragon
listing: name-only
category: workspace
---

# /registry-conformance — the index must be true when someone else reads it

A registry is a **build artifact, not a document**. Two owners for one fact is the whole bug, and
both layers proved it in opposite directions on 2026-08-07:

- **acme-health-main** wrote content *into* the index until it outgrew the documents —
  `analyze-billing.yaml` ran a 170-word median and a 768-word max, several `docs.yaml` summaries
  were 10-16% of the entire document they indexed.
- **my-lib** kept the index short but let it drift *away* from the files — 27 of 30 skills
  descriptions were independent of the file's own `summary:`, and 11 of 30 carried a version the
  file disagreed with (`review-mode` registered 1.0.0 against a real 2.2.0).

Same disease. Generation removes the second owner; validation covers what generation can't.

## The split — decide this FIRST, per manifest

**Not every manifest can be generated, and forcing one that can't is destructive.**

| | Derivable → **generate** | Not derivable → **validate** |
|---|---|---|
| Shape | one entry per file | sections, buckets, `covers:`, `excluded:` |
| Entry fields | come from the file's frontmatter | encode a human's grouping decision |
| Examples | `skills`, `executions`, `directives`, `personas`, `context` | `docs.yaml`, `mirror.yaml`, `workspace.yaml`, `data.yaml` |
| Tool | `build_registry.py` | `validate_registry.py` |

The test is not "is it a manifest" but **"is every field in it recoverable from somewhere else?"**
If an entry carries a reason, a bucket, an exclusion rationale or a publication contract, that
knowledge lives in NO other place — regenerating it deletes it. Those manifests get validated, and
the comments in them are documentation, not tombstones.

⚑ **Do not add a non-derivable manifest to `registry-map.yaml` to make coverage look complete.**
Mapping it prematurely either refuses every run or discards real content. Leaving it out and
validating it instead is the correct end state, not a gap.

## Procedure

### 1. See the drift (read-only — this is the default)

```bash
python3 ~/ai-workspace/team-lib/executions/build_registry.py --repo <REPO> \
    --config <REPO>/config/registry-map.yaml
python3 ~/ai-workspace/team-lib/executions/validate_registry.py --repo <REPO>
```

Neither writes anything without `--apply`. `build_registry` prints a rebuild-and-diff line count
per manifest; `validate_registry` exits non-zero on a broken one.

### 2. Read what it found — most findings are fixed in the FILE, not the index

| Report | What it means | Where the fix goes |
|---|---|---|
| `VERSION drift` | file and registry disagree | **the file wins**; nothing to do, the rebuild carries it |
| `⚑ DOWNGRADE — registry was AHEAD` | registry version > file version | **stop.** Usually a bulk registry bump that never stamped the files. Check whether the FILES need the bump before letting the rebuild lower the number |
| `SUMMARY drift` | registry text ≠ file's `summary:` | the file wins — but read both first; the registry text is sometimes the better one and belongs *in the file* |
| `OVER BUDGET` | a `summary:` is longer than a pointer | shorten the `summary:` **in the file**. Never trim it in the registry — that re-creates the second owner |
| `⚑ MALFORMED frontmatter` | present and no parser can read it | run the repairer (step 2b) — it is almost always an unquoted `: ` inside a plain scalar |
| `no frontmatter` | file has none | add it, or exclude the tree with a reason |
| `preserved field -> MISSING path` | a hand-authored field names a file that is gone | fix or drop the field |
| `ℹ path OUTSIDE this repo` | cross-layer pointer, and it resolves | informational — a coupling worth seeing, not an error |
| `present but UNINDEXED` / `indexed but ABSENT` | disk and manifest disagree on membership | the rebuild fixes it; an entry whose file is gone is **tombstoned into `retired:`**, never dropped |
| `LISTING missing` | an internal skill has no `listing:` (the provenance default was applied) | add `listing:` to the **SKILL.md** frontmatter (`name-only` unless there is a reason; see the AGENTS.md metadata standard). Third-party skills: `config/skill-listing.yaml` |
| `LISTING value not allowed` | not `on` / `name-only` / `user-only` (`off` is sidecar-only) | fix the value **in the file** |
| `CATEGORY not in the vocabulary` | a skill's `category:` or a persona's `skill_categories:` names something `team-lib/config/skill-categories.yaml` does not define | use an existing name, or add the category to the vocabulary first (generic names only: the public scrub blocks client names) |
| `ℹ no category` | a skill resolves no `category` | add one to the file (or the sidecar for a third-party skill); find-skill cannot filter to it until then |
| `⚑ LISTING POLICY unreadable` | a declared sidecar or the vocabulary is missing or does not parse | fix the file: until then every override in it silently reverts to the default |

### 2b. Repair malformed frontmatter before anything else

A malformed block is the highest-value finding here, because it is the one that looks fine. The
keys are there, `summary:` is there — and to every `yaml.safe_load` consumer the file has no
metadata at all. Measured in acme-health-main 2026-08-08: 22 such documents, all reported compliant
by a census that matched the literal string `summary:` instead of parsing.

```bash
python3 ~/ai-workspace/team-lib/executions/repair_frontmatter.py --repo <REPO>          # dry run
python3 ~/ai-workspace/team-lib/executions/repair_frontmatter.py --repo <REPO> --apply
```

It re-emits the block through the YAML emitter rather than hand-quoting, and refuses anything it
cannot round-trip verify — top-level lists, nested mappings, block scalars, duplicate keys — so a
refusal means *a human should look*, not *force it*. The document body is guaranteed byte-identical.

⚑ **Spot-check five before `--apply`.** On the run that repaired those 22, five-file spot-checking
caught two type-preservation bugs that the tool's own verification structurally could not see
(both happen during reconstruction, so the round-trip agrees with itself): an already-quoted
`summary:` gaining its quote characters as literal content, and a `tags: [a, b]` flow list demoted
to a string. Both are fixed and tested now — but the reason they were caught is the rule, not the
tool.

### 2c. The directory indexes, from the same map

A manifest and an `index.md` are two renderings of one fact. `build_index.py` regenerates the
`## Contents` table of each registered directory's `index.md` from the same specs — so publishing
the manifest true and the index stale would just move the drift.

```bash
python3 ~/ai-workspace/team-lib/executions/build_index.py --repo <REPO>            # dry run
python3 ~/ai-workspace/team-lib/executions/build_index.py --repo <REPO> --apply
```

| Report | What it means | Where the fix goes |
|---|---|---|
| `no pointer field` | neither `summary:` nor `description:` | add a `summary:`; the row says so meanwhile |
| `ℹ fell back to description:` | no `summary:`, used the harness field | fine for `_external/`; add a `summary:` for anything we own |
| `ℹ over budget in _external/` | third-party file, too long | **nothing** — we may not edit those; it is not a defect we can close |
| `⚑ no index target` | the spec's globs span two directories | declare `index: <path>` or `index: false` in the spec, with the reason |
| `REFUSING to write` | `## Contents` holds hand-authored text | move it to its own `##` section; do not reach for `--force` |

⚑ **Only `## Contents` is generated.** Everything else in an `index.md` — Purpose, What Belongs
Here, naming conventions — is a human's and is preserved byte-for-byte.

### 2d. The frontmatter census — the half that measures FILES, not manifests

Everything above checks whether the index matches the files. This checks whether the files are
indexable at all: which agent-consumable documents carry no `summary:`.

```bash
python3 ~/ai-workspace/team-lib/executions/validate_registry.py --repo <REPO> --frontmatter
```

Exits 1 when the gap is non-zero. Two dispositions, and only two:

- **Add the frontmatter** — it is a real document someone should be able to discover.
- **DECLARE the tree** in `config/registry-map.yaml` under `validate.census_exclude`, **with a
  reason**. An exclusion is a deletion decision: it removes a tree from the gate permanently, so
  an entry without a `reason:` is refused.

It already honours the convention's Exempt Files list (`_external/`, ≤15 lines, project-root
README/CHANGELOG), so anything it still reports is genuinely ours to decide about.

⚑ **This is the one part a scheduled job will not fix for you.** The nightly runs it and raises a
finding (`dream_cycle.py` v1.5.0+), but writing a summary is authorship, not a deterministic
transform — no 3am job may invent one. Manifests and index tables self-heal; this does not.

### 2e. The skill listing map (skills manifests only)

A skill's `listing` has a third rendering besides the manifest: the Claude Code `skillOverrides`
map, generated into `my-lib/config/claude-skill-overrides.json` and installed into
`~/.claude/settings.json`. Check both halves:

```bash
python3 ~/ai-workspace/team-lib/executions/build_skill_overrides.py --check       # map vs a rebuild
python3 ~/ai-workspace/team-lib/executions/build_skill_overrides.py --installed   # settings vs the map
```

| Report | What it means | Where the fix goes |
|---|---|---|
| map `STALE` | a SKILL.md or sidecar changed since the map was generated | regenerate it (`build_skill_overrides.py`, writes my-lib/config only) and commit; the nightly does this too |
| managed key not installed | settings.json predates the map | the agent runs `install_skill_overrides.py --apply`; it writes settings.json, so it takes one approval |
| `⚑ FOREIGN key` | someone set `skillOverrides` by hand (e.g. via `/skills`) | move the decision into the SKILL.md frontmatter or a sidecar; the installer keeps foreign keys but they now disagree with the source of truth |
| skills `unlinked` | in my-lib/skills but not in `~/.claude/skills` | `link_skills.py` (writes under `~/.claude`, one approval) |

Never fix any of these by editing `skillOverrides` in settings.json: that is the second owner.

### 3. Apply

```bash
python3 ~/ai-workspace/team-lib/executions/build_registry.py --repo <REPO> \
    --config <REPO>/config/registry-map.yaml --apply
```

**Fix the over-budget and malformed findings BEFORE applying**, not after — they are defects in
the files, and applying first just bakes today's text into the index.

### 4. Interpret the one refusal

> `REFUSING to write — this manifest has comments below its header block`

PyYAML cannot round-trip comments, so writing would silently delete them. This is a real refusal,
not a nuisance: in acme-health-main those comments are load-bearing documentation about the
manifest's own scope. Either move them into the header block, or conclude the manifest belongs on
the **validate** side of the split above. `--force` discards them — reach for it only when you
have read them and they are genuinely dead.

⚑ The comment guard decides **by deletion**, not lexically: a line is a comment iff removing it
leaves the parsed data identical. It used to decide by leading `#`, and flagged `#NAME?, #VALUE!,
#DIV/0!` — a wrapped continuation inside a folded scalar — as a comment, refusing a safe write.

### 5. Verify, and commit the manifest with what it indexes

Re-run step 1; expect `clean`. Then commit the indexed file and its registry entry **in the same
commit** — they are one atomic change, and splitting them is how a registry ends up describing a
state that never existed.

## What runs WITHOUT you (wired 2026-08-08)

You mostly should not need this skill, because two mechanisms already run. Know what they cover
so you can tell "clean" from "never checked".

| When | What runs | Scope |
|---|---|---|
| every `git push` | `version_gate.py` → `registry_gate()` | PARSE-checks every manifest in the pushed repo; REGENERATES the manifests **and the `## Contents` of each directory index** only where a `config/registry-map.yaml` exists, and commits both so the push carries them |
| nightly (`dream_cycle.py`, 03:47) | `--reconcile` + `validate_registry.py` + **the frontmatter census** | my-lib and team-lib reconcile **and commit**; project repos are `--dry-run` and raise a **finding**. The census is report-only in EVERY layer — a summary is authorship, not a transform |

Three things about that table are load-bearing:

- **The push gate rewrites; the nightly project pass only reports.** A scheduled job that rewrote
  a manifest inside a live worktree would be fixing the index by corrupting the state around it.
  So detection runs everywhere and mutation only in the layers we own.
- **`[no-version]` opts out of VERSIONS, never the index.** These are separate promises. The gate
  shipped conflating them for exactly one push, on 2026-08-08: the mirror commit sets
  `[no-version]` by design, so 11 mirrored version bumps reached the remote with
  `registry/skills.yaml` still naming the old numbers.
- **A repo with no `registry-map.yaml` is parse-checked and coverage-checked, never rebuilt.**
  That is the correct end state for the validate-side manifests, not a gap waiting to be closed.

**A gate that stops firing looks exactly like a gate with nothing to do.** Check it is alive:

```bash
python3 ~/ai-workspace/team-lib/executions/version_gate.py --self-check   # logs every invocation
python3 ~/ai-workspace/team-lib/harnesses/test_registry_gate.py           # 6 sandbox scenarios
```

## Don'ts

- **Don't hand-edit a generated manifest.** The next rebuild overwrites it, so the edit is lost
  and, worse, was briefly believed. Change the file's frontmatter instead.
- **Don't trust `clean` as proof the registry is RIGHT.** It proves the index matches the files.
  If a file's own `summary:` is wrong, a clean registry faithfully reproduces the wrong summary.
- **Don't report "the tool ran" as "the thing is correct."** Say which manifests were applied and
  which still carry drift; a run over four manifests where one was skipped is not a clean repo.
- **Don't let a `--force` become routine.** It is the only operation here that destroys content.

## Related

- `executions/build_registry.py` — the manifest generator; `--self-check` is two-sided
- `executions/build_index.py` — the `index.md` `## Contents` generator; shares `build_registry`'s
  frontmatter reader and file discovery so the index and the manifest cannot disagree
- `executions/validate_registry.py` — the validator; `--frontmatter` runs the census
- `executions/repair_frontmatter.py` — the repairer; dry-run by default, refuses what it cannot verify
- `harnesses/test_registry_gate.py` — the six sandbox scenarios behind the push gate
- `config/registry-map.yaml` (per repo) — which files each manifest indexes, which fields are
  derived, and the summary budget. Judgement lives in data, not in the tool.
- `context/indexed/progressive-disclosure-convention.md` — what a `summary:` is FOR, and the
  budget the generator enforces
