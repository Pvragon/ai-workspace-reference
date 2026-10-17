---
summary: "Index of team-lib configuration files: registry-map (what build_registry generates), the skill category vocabulary, the external-skill listing sidecar, and the name-spellings guard list. Scan before opening individual files."
---

# config

## Purpose
Configuration the shared team-lib tools read. Everything here is hand-authored and versioned; nothing here is a secret or a machine-specific backup (those live in `personal/secrets/` and `my-lib/config/`).

## Files
| File | What it is | Read by |
|---|---|---|
| `registry-map.yaml` | Which registries are generated from which globs, the derived fields of each, and the skill listing policy (`listing_values`, `listing_sidecars`, `listing_defaults` by provenance, `listing_required`, `category_vocabulary`). The personas spec derives `skill_categories`. | `build_registry.py`, `validate_registry.py`, `build_index.py` |
| `skill-categories.yaml` | The controlled vocabulary for a skill's `category:` and a persona's `skill_categories:`. Generic names only, so the public scrub passes. Add a category here before using it. | `build_registry.py`, `validate_registry.py`, `find_skill.py` (via `resolve_listing`) |
| `skill-listing.yaml` | `listing` and `category` for skills whose own files may not be edited: the third-party `_external/` packs, keyed by harness name (`ext-pdf`). Internal skills never appear here; they carry both fields in their SKILL.md frontmatter. | `build_registry.py`, `build_skill_overrides.py`, `find_skill.py` (via `resolve_listing`) |
| `name-spellings.yaml` | Misspellings of real people's names that the spelling guard blocks. | `guard_name_spellings.py` |

## Skill listing, in one paragraph
A skill's `listing` (`on` / `name-only` / `user-only`) decides what Claude Code shows the model for it. Resolution, first hit wins: the skill's frontmatter, then `my-lib/config/skill-listing.yaml` (personal), then this folder's `skill-listing.yaml`, then `listing_defaults` by provenance (externals `user-only`, internal `name-only`). When `my-lib/config/registry-map.yaml` declares no skills policy (a fresh teammate or public install), the skills stanza of this folder's `registry-map.yaml` is the default policy, so the listing tools work cold. `build_skill_overrides.py` renders the result into `my-lib/config/claude-skill-overrides.json`, and `install_skill_overrides.py --apply` merges it into `~/.claude/settings.json` `skillOverrides`. Never hand-edit the generated map or `skillOverrides` in settings: change the frontmatter or a sidecar and regenerate.

## What Does NOT Belong Here
- Secrets or API keys (use `personal/secrets/`)
- User-specific overrides (use `my-lib/config/`)
- Generated files
