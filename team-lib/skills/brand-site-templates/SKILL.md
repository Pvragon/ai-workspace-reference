---
name: brand-site-templates
description: "Stage 4 of build-brand-site. Build the reusable section library (hero, teaser/feature, split, stat, CTA band, FAQ, prose page, dividers) + page shells, with all copy moved OUT of JSX into per-brand content-data files. This is the second reusability seam (after the token bridge): content-as-data is what lets the same section components carry a different brand's copy with zero edits."
summary: "Section library + content-as-data. Invoke ext-frontend-design for section composition/rhythm; this adds the reuse discipline. Every section is a component that takes its copy as PROPS from a config/content data file — never inline strings. Sections live in components/marketing/sections/*; page shells compose them declaratively. Split server shells (static) from client islands (interactive: forms, disclosures, viewers) at the section boundary so the RSC rule from stage 1 stays clean. The proof: a second brand swaps content files + tokens and the sections reskin + re-copy with no component edits."
version: 1.0.0
template: skill-definition
created: 2026-07-22
last_updated: 2026-07-22
maintainer: your-agent
dependencies: [node]
tags: [templates, sections, content-as-data, reuse, rsc, marketing]
---

# Stage 4 — Page Templates / Section Library

The reuse seam for LAYOUT (the token bridge was the seam for STYLE). Copy becomes data.

## Compose first (don't re-derive)
- **Section composition, rhythm, structural devices**: `ext-frontend-design` (numbering /
  eyebrows / dividers must encode something true, not decorate).

## Steps
1. Build a small, composable section set — e.g. `hero`, `teaser`/`feature`, `split`,
   `stat`, `cta-band`, `faq`, `prose-page`, `section-heading`, `dot-divider`. Keep it lean;
   add a section only when a real page needs it.
2. **All copy is DATA, not JSX**: each section takes its text/links/labels as props sourced
   from a per-brand `config/*.ts` (or `content/*`) file. No inline strings in the component.
3. Page shells compose sections declaratively from the content data.
4. **Server shell / client island split at the section boundary**: static sections are
   server components; interactive ones (email form, viewers, disclosures) are the only
   `"use client"` islands — keeps the stage-1 RSC rule clean and the page mostly static.
5. Bake the responsive guards into the shell (img max-width, `min-width:0` on grid/flex
   children, `overflow-x` clip on body; wide content scrolls inside its own box).

## Bake in
- One primary CTA per view; ~60–75ch measure on prose; generous whitespace.
- A section that can't take content as props isn't reusable — refactor until it can.
- Don't over-build the library speculatively; extract sections FROM the real pages you need.

## Gate
Sections render from content-data with no inline copy; a dummy second content object
produces a different-copy page with zero component edits (the reuse proof, in miniature).
Then → `brand-site-pages`.
