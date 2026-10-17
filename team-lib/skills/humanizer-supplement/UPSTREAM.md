---
template: reference
version: 1.2.0
summary: "Tracks the relationship between humanizer-supplement and github.com/blader/humanizer: which of our stance shapes upstream already covers, which are proposed, and what to delete from SKILL.md when a PR lands."
created: 2026-09-20
last_updated: 2026-09-20
maintainer: pvragon
---

# Upstream relationship

Upstream: `github.com/blader/humanizer`, vendored at `team-lib/skills/_external/blader-humanizer`.
Pinned at `9862685` (2026-09-06, SKILL.md v3.0.0), bumped 2026-09-20 from `c78047b` (2026-01-22,
v2.1.0), 67 commits and 18 merged PRs behind.

The repo is actively maintained by the community. Twenty-plus contributors, merged PRs numbered in
the 230s to 260s, last commit two weeks before we bumped. Proposing patterns upstream is the right
default; keeping a private fork is not.

## Coverage as of upstream v3.0.0

| Our shape | Upstream | Status |
|---|---|---|
| Knowing aside that closes a paragraph | Pattern 2, one-line closers | Covered, dropped from our skill |
| Explaining the document's own conventions | none | Ours, S1 |
| Narrating your own method or integrity | Pattern 25, previous-version only | Partly ours, S2 |
| Flourish where a plain label was the job | Pattern 20, typography only | Partly ours, S3 |

Upstream's v3.0.0 rebuild retired one of our four shapes outright. Pattern 2 covers the knowing
aside better than our own writeup did, so it is gone from `SKILL.md`.

Two upstream patterns sit next to ours without covering them. Pattern 25 is about describing what
the text replaced, which is our method-narration shape restricted to a prior draft. Pattern 20 is
about title case, emojis and horizontal rules, not about a heading written for effect.

### Vocabulary

| Word | Upstream | Status |
|---|---|---|
| load-bearing (figurative) | not on the pattern 12 list | Ours, V; candidate for the §12 list once #290 settles |

## Proposed upstream

All three submitted 2026-09-20 in one pull request,
[blader/humanizer#290](https://github.com/blader/humanizer/pull/290), from branch
`your-username:stance-patterns`.

| Pattern | Proposed as | State |
|---|---|---|
| S1 | New §26, explaining the document's own conventions | open |
| S2 | Widened §25, writing about the document instead of its subject | open |
| S3 | One added pair under §20, heading written for effect | open |

The PR validates at upstream 3.1.0 and keeps SKILL.md inside its 400-line limit. Every example was
rewritten as a generic equivalent, so nothing traceable to our own documents left the building.

When it merges, bump the submodule, delete those patterns from `SKILL.md`, and record it here. When
all three are upstream, delete this skill and leave a pointer.

## Sources behind the patterns

Every example is from a real artifact that had already passed the humanizer. The origin case is
the `prez.example.com/travel` San Diego guide, 2026-09-15, nine instances flagged by hand after the
page was reported clean. See `context/indexed/copy-stance-no-self-narration.md` for the longer
writeup and `memory/feedback_deck-copy-never-narrates-itself.md` for the session record.
