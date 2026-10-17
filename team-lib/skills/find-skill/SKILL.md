---
name: find-skill
description: "Search all skills, including name-only and hidden ones, by task or category. Use before a task a skill might cover when no listed description fits."
template: skill-definition
version: 1.2.0
summary: "Searches all ~200 skills (harness links, both registries, disk, and the cwd project's own skills) by free text and/or category. Prints each hit's invocation name, listing level, category, summary, SKILL.md path and how to use it. Personas run it at startup with their skill_categories."
created: 2026-10-16
last_updated: 2026-10-16
maintainer: pvragon
listing: "on"
category: ai-tooling
---

# find-skill

The skill list in your context shows only about a dozen skills with descriptions. Most others are listed by name only, and third-party skills are hidden. This skill searches all of them.

## When to use

- A request might match a skill, but no listed description clearly covers it.
- A skill's name looks relevant but has no description, and you need to know what it does.
- A persona is loading. Run it with the persona's `skill_categories` to get its current skill set.

Skip it when a listed description already fits, or when the task obviously needs no procedure.

## Run

```bash
python3 ~/ai-workspace/team-lib/skills/find-skill/find_skill.py "<what the user wants, in plain words>"
python3 ~/ai-workspace/team-lib/skills/find-skill/find_skill.py --categories messaging,personal-admin
python3 ~/ai-workspace/team-lib/skills/find-skill/find_skill.py "<query>" --categories billing-audit --cwd "$PWD"
```

- `--categories` takes keys from `~/ai-workspace/team-lib/config/skill-categories.yaml`. With no query, it lists every skill in those categories.
- `--cwd` defaults to the current directory. Skills of the project you are in (its `.claude/skills/` and `registry/skills.yaml`) are included. With `--categories`, a project skill that has no `category:` is included when its name or description contains a word of a requested category, or matches the query.
- `--brief` prints one line per hit, for a persona's startup list; a hidden or unlinked hit ends with its Read path. `--json` gives machine-readable output, and `--limit N` caps the hits for a text query (default 8; `0` means all).

## Read the result

Each hit shows its name, `[listing · category · layer/source]`, a one-line summary, the absolute SKILL.md path, and a `use:` line. Follow the `use:` line:

| Listing | How to use it |
|---|---|
| `on`, `name-only` | Invoke it with the Skill tool by name. |
| `user-only`, `off`, `unlinked` | Read the SKILL.md at the printed path and follow it. The Skill tool refuses these, but the file is readable. |

Hits are ranked by match quality first: an exact name, then how many query words hit the name. A name that matches only after dropping `ext-` or `anthropic-skills:` does not count as exact. Within equal quality the skill search hierarchy in the workspace `AGENTS.md` (Operating Principle #1) decides: Local (my-lib, projects) beats Team and System, those beat Account (the synced `anthropic-skills:*`), and Account beats External. Generic words such as "make", "open" and "file" add to the score but do not decide whether a skill matches.

Superseded skills (description starts `[SUPERSEDED`) sink to the bottom and never come in through `--categories`. A skill whose sidecar entry says `search: exclude` is never offered; today that is `anthropic-skills:google-workspace`, because CLAUDE.md bans the Google Workspace connectors.

If nothing matches, say so and do the task directly. Do not invent a skill.

## Self-check

`python3 find_skill.py --self-check` runs a synthetic workspace through these cases, each checked both ways: a hit, a miss, the category filter, a user-only Read path, an unlinked skill, project scope, archive exclusion, internal over external and over synced, synced over external, generic verbs, banned and superseded skills, phrase matches, `--brief` paths, the System label, and uncategorized project skills under `--categories`.

`--self-check --live` adds read-only checks against this machine: a persona's category load from a project that has one, plus four real queries. A case is skipped when its data is absent.
