---
name: now-you-see-it
description: "Build or independently review any chart, dashboard, report tab or data table so it communicates at a glance, per Stephen Few (Now You See It). Use when making or changing a data visualization, or asked to review, critique or sign off on one."
template: skill-definition
version: 0.2.0
summary: "Stephen Few builder and independent reviewer for any data visualization (charts, dashboards, tables, slide charts, HTML/SVG/matplotlib/Sheets, prez pages), optimized for communication. BUILD mode: question first, form by relationship, strip non-data ink, one highlight, context, multi-surface pass. REVIEW mode: blind fresh-agent review of the rendered artifact with severity-ranked fixes and SIGN-OFF/REVISE."
created: 2026-10-22
last_updated: 2026-10-22
maintainer: pvragon
listing: on
category: design
dependencies: [python-playwright, Pillow]
---

# Now You See It: build or review a data visualization

Channels Stephen Few: *Now You See It* (2009), *Information Dashboard Design* and *Show Me the Numbers*. The name is the instruction that started it: "Now you see it. Channel it." The goal is communication. The reader gets the point in seconds and nothing is lost.

It worked twice before it was a skill: an operations reports prototype (2026-10-09, "this looks really clean now") and a priorities page (2026-10-22, four independent review rounds, "Formatting looks awesome").

## Files

| File | Use |
|---|---|
| `principles.md` | Few's rules as checkable items with IDs (A1...M5), each with a one-line reason and its source. Read it in either mode. |
| `review-rubric.md` | Severity scale, the ordered checklist, the sign-off bar, the brief for a fresh reviewer, and the report template. |
| `scripts/render_for_review.py` | Renders an HTML, SVG or URL to PNGs (desktop 1440x900, slide 1280x720, phone 390x844, print), in the default state and in any `--state NAME='sel;sel'` click state (tabs, filters, expanded sections). Reports horizontal overflow, console errors and blank renders. `--self-check` tests it. |

## What other skills it works with

- **`dataviz`** (bundled with Claude Code): use it for construction mechanics: mark specs, hover layer, and its palette validator `scripts/validate_palette.js` for colorblind safety. Do not edit it. Where it says "a legend always present for 2 or more series", Few's direct labels win when they fit (H1). Identity is never color alone, which both agree on.
- **`artifact-design`**: the page contract when the output is a published artifact. Finished pages go wherever your workspace publishes them (for example `publish-to-prez`).
- **`mobile-overflow-audit`**: per-slide overflow on decks.

### Palette validator

The `dataviz` validator lives in the bundled skill's directory, which is versioned and only extracted under `/tmp` once that skill has been loaded in some session. Find it with `ls /tmp/claude-1000/bundled-skills/*/*/dataviz/scripts/validate_palette.js`. If nothing is found, load `dataviz` with the Skill tool (its base directory is printed) and run `node <base>/scripts/validate_palette.js "<hex,hex,...>" --mode light`, then again with `--mode dark`. If it still cannot be run, say so in the review rather than eyeballing contrast.

## Pick the mode

- **BUILD**: you are making or changing the visualization.
- **REVIEW**: someone (you included) made it and it needs a verdict. If you built it, you never review it yourself. Spawn a fresh subagent.

A build always ends with a review. Every round on the priorities page caught something the builder would have shipped.

## BUILD

1. **Write down the question.** Who reads it, which 1-3 questions they must answer at a glance, and what decision it supports (A1). If the user points at an existing view as the model, reproduce it and do not expand it (A4).
2. **Choose the form from the relationship** (B1-B11): time series, ranking, part-to-whole, deviation, distribution, correlation, nominal comparison, geospatial, several variables. Sometimes the answer is a number with context or a sorted table, not a chart.
3. **Encode for accuracy.** Use position, then length, for anything compared (C1). Bars start at zero (G1). Never use dual axes (G3) or 3D (C3).
4. **Strip, then mute.** Remove non-data ink, then lighten what has to stay (D1-D2). Definitions, provenance and caveats go in one collapsed "What each number means" panel, never as badges on each number (D3).
5. **Highlight one thing.** Use one accent per view, on the exception. Everything else is gray (E2, I1). Be able to say in one sentence why it is highlighted (E3). One meaning per hue (E4).
6. **Give every number context.** Show a target, the prior period or a reference line, and show the difference directly (F1-F2). Color a direction only when good or bad is unambiguous, and always with an arrow or sign (F4). If the baseline is not like-for-like, show no comparison (F5).
7. **Label and sort.** Label directly (H1), sort by the value that answers the question (H3), and state units and the time window once (H5). Titles state the point (A5).
8. **Dashboards:** one screen at 1440x900, 3-4 key numbers, 1-2 large charts, one compact table. Overview first and details on click (K1-K3). Use bullet graphs and sparklines, not gauges (K4).
9. **Detail on demand.** Tooltips show the values behind a mark, with numerator and denominator for shares (L1). Nothing essential is hover-only (L2). Every filter state is valid, and its counts follow the filter (L3-L4).
10. **Color last.** Gray base and one accent. Check categorical palettes with `dataviz`'s validator, and never use red against green alone (I1-I5).
11. **Multi-surface pass.** Check the default view, hover and focus, touch (first tap), every filter and filter combination including empty ones, collapsed and expanded sections, slide or print, and phone (M1-M2). Render with the helper and LOOK at every PNG with the Read tool:
    ```bash
    python3 ~/ai-workspace/team-lib/skills/now-you-see-it/scripts/render_for_review.py <file|URL> --full-page \
      --state demand='text=Demand' --state crisis='text=Demand;text=Crisis'   # one PNG per surface per state
    ```
    Add `--scheme dark` for a second pass when the page has dark mode.
    Then ask whether an executive would get the point in five seconds. If not, cut more.
12. **Hand off to REVIEW** with a fresh subagent. Fix the findings. Re-review until it signs off. After publishing, check the hosted page once (M5).

When you brief a build subagent, say "less is more" explicitly and list the cuts. Subagents default to dense, fully caveated output.

## REVIEW

Independence comes from three rules:

1. **Blind first.** The reviewer gets the artifact, the readers and their questions, and the source of truth for content. It does not get the builder's rationale. It writes its 10-second read before it learns what was intended.
2. **Judge the rendered artifact, not the code.** Render to PNG on every surface and look with the Read tool. Use `--state` clicks for tabs and filters. Use the Playwright MCP tools, or Python Playwright when another session holds the MCP browser, for hover and touch. Measure computed styles and bounding boxes for anything that looks off. Read code only to explain a cause it has already seen. A 15%-opacity arrow on the priorities page looked fine in the code.
3. **Re-derive, don't trust.** Content checks use the reviewer's own extraction from the raw source, never the builder's script or counts.

Procedure:

- **Fresh subagent:** fill the brief template in `review-rubric.md` and spawn it with `model: "opus"` for dashboards and anything executives see. Use `sonnet` for a single chart. Give it a narrow lane: the stated readers and questions.
- **Reviewing it yourself** (the user hands you someone else's artifact): walk the `review-rubric.md` checklist in order, starting with the 10-second read.
- **Non-HTML artifacts** (matplotlib, Sheets, slide images): review the exported PNG directly with the Read tool. Ask for or produce one export per surface the reader will use.
- **Output:** a report in the template from `review-rubric.md`, saved to `my-lib/runtime/.tmp/YYMMDD-review-<artifact>-round-N.md`. The reply opens with `VERDICT: SIGN-OFF` or `VERDICT: REVISE`, then at most 8 fixes ranked by severity (S1 blocks, S2 should fix, S3 polish), each as what I saw / why (rule ID) / change. Taste comes separately. End with what was not checked.
- **Later rounds:** send them by SendMessage to the same reviewer, split into "What changed (verify, don't trust)" and "Not changed, by design (argue if you disagree)".

## Graduation

Graduated to team-lib on 2026-10-22. Fix it here, in team-lib; the personal-layer path is a symlink.
