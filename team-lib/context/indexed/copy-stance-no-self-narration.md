---
template: business-context
version: 2.0.0
summary: "POINTER ONLY. The stance rules moved to skills/humanizer-supplement/SKILL.md on 2026-09-20, where they are three patterns rather than four. Kept so older references resolve; do not edit it and do not load it as the rule."
created: 2026-09-17
last_updated: 2026-09-20
maintainer: your-agent
entity_type: writing-standard
tags: [writing, presentations, humanizer, ai-speak, deliverables]
status: active
---

# Moved

The stance rules now live in **`team-lib/skills/humanizer-supplement/SKILL.md`**.

Together with `skills/_external/blader-humanizer`, that is **the humanizer pass**: the external
skill for vocabulary and rhythm, the supplement for stance. The copy gate in
`skills/markdown-to-branded-html` loads both.

One of the original four shapes, the knowing aside that closes a paragraph, was retired on
2026-09-20 when the upstream humanizer was bumped to v3.0.0, which covers it as pattern 2. The
other three remain ours. `skills/humanizer-supplement/UPSTREAM.md` tracks what has been proposed
upstream and what should be deleted here when a pull request lands.
