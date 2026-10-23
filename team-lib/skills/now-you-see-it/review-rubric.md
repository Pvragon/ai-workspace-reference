---
template: skill-reference
version: 0.2.0
summary: The now-you-see-it review rubric. Severity scale, the ordered checklist a reviewer walks on the rendered artifact, the sign-off bar, the reviewer brief template for a fresh subagent, and the review report template.
created: 2026-10-22
last_updated: 2026-10-22
maintainer: pvragon
---

# Review rubric

Rule IDs (A1, G1, ...) refer to `principles.md`.

## Severity

| Level | Meaning | Examples |
|---|---|---|
| **S1 blocks** | The view misleads, or fails its main question. | Wrong numbers or wrong binding (a value under the wrong owner or series); information lost against the source; a bar chart with a cut baseline (G1); dual axes (G3); the key fact cannot be found in the default view (A2); a filter state that shows wrong data (L4). |
| **S2 should fix** | The point gets through, but slowly or not for everyone. | Salience inverted, the important thing muted (E1); clutter on the face (D1, D3); a number without context (F1); comparison left to arithmetic (F2); color-only identity (H2, I4); hover-only facts with no touch path (L2); broken phone or slide surface (M1, M2); unsorted ranking (H3). |
| **S3 polish** | Small gains in speed or finish. | Tick formatting (G6), a legend that could be direct labels (H1), minor contrast, spacing. |
| **Taste** | Defensible either way. Reported separately, never blocks. | Hue choice within a passing palette, strikethrough vs check mark. |

**SIGN-OFF** = no S1 and no S2 remaining. Otherwise **REVISE**, with at most 8 fixes ranked by impact on communication. If there are more than 8, say so and give the top 8; the rest come next round.

## Checklist, in this order

Work on the rendered artifact (PNG or live page). Read code only to explain a cause you already saw.

0. **Setup.** Readers, questions (A1), source of truth for content. Render all surfaces with `scripts/render_for_review.py`, adding a `--state` per tab, filter or expanded section that changes the view. Use Playwright (MCP, or Python if the MCP browser is locked by another session) for hover and touch. Open each PNG with the Read tool and look.
1. **10-second read (A2).** Before reading closely, write down what the default view tells you and where your eye landed first. Compare with the intended questions. This is the most important finding; do it before you know the builder's intent.
2. **Form (B).** For each chart: which relationship is it showing, and is the form right for it? Would a sorted table or a single number with context do better?
3. **Encoding and scales (C, G).** Position and length for comparisons; zero baselines on bars; no dual axes; shared scales on small multiples; no 3D.
4. **Ink (D).** List the non-data ink that can go. Badges, captions, borders, backgrounds, gridlines, legends for absent encodings.
5. **Salience (E).** What pops out? Is it the most important thing? Count the meanings each hue carries. Is every highlight explainable in a sentence?
6. **Context (F).** Every key number: compared with what? Shown directly? Any delta with a bad baseline?
7. **Labels and sorting (H), color (I), tables (J).** Direct labels, sorted by value, units stated, colorblind safety (run `dataviz`'s `validate_palette.js` on categorical palettes when hex values are known).
8. **Dashboard fit (K).** One screen at 1440x900? Overview first? 3-4 key numbers? Consistent definitions across tabs?
9. **Interaction (L).** Hover, focus, touch (first tap), every filter and combination including empty results, expanded and collapsed sections, counts following filters. Measure positions when something looks misplaced.
10. **Surfaces (M).** Desktop, slide, phone, print; light and dark if both exist; overflow numbers from the render helper; the hosted URL if published.
11. **Content preservation** (when the view replaces or restyles another, or is built from a source): re-derive the counts from the raw source with your own extraction. Never trust the builder's numbers or build script.

## Reviewer brief template (for a fresh subagent)

Fill the angle brackets; do not add the builder's design rationale. Pass `model: "opus"` for a dashboard or anything executives will see; `sonnet` is fine for a single chart.

```
You are an independent reviewer: an experienced <program manager / analyst / exec-facing
designer> who is also a careful student of Stephen Few (Now You See It, Information
Dashboard Design, Show Me the Numbers). Decide whether this visualization communicates
<what> to <readers> well, WITHOUT losing information, and either SIGN OFF or give ranked
fixes. You did not build it; you have not seen the builder's reasoning, and should not
look for it until your first pass is written.

Read first: <skill dir>/principles.md and <skill dir>/review-rubric.md.

ARTIFACT (read-only, do not edit any files): <path or URL>
Render it: python3 <skill dir>/scripts/render_for_review.py <path or URL> --out <dir>
(add --state NAME='selector;selector' for each tab or filter state). Then LOOK at every
PNG with the Read tool. For hover and touch use Playwright on the live page (MCP tools, or
Python Playwright if another session holds the MCP browser).

READERS AND QUESTIONS (it must answer these at a glance):
- <reader>: <question>
SOURCE OF TRUTH for content (re-derive counts yourself): <path or "none">
MUST BE PRESERVED: <list, or "n/a">

Write your review to <out path> using the report template in review-rubric.md.
Final message: first line exactly "VERDICT: SIGN-OFF" or "VERDICT: REVISE", then at most
8 ranked fixes (what you saw / why, with the rule ID / concrete change), taste separately,
then one or two lines on what you did not check.
```

Later rounds go to the same reviewer by SendMessage, in two lists: **"What changed (verify, don't trust)"** and **"Not changed, by design (argue if you disagree)"**. Only now may the builder's reasoning enter, and only for the items it disputes.

## Report template

```markdown
---
template: working-artifact
version: 0.1.0
summary: <one sentence: artifact, verdict, top finding>
created: <YYYY-MM-DD>
last_updated: <YYYY-MM-DD>
maintainer: pvragon
---

# Review round <N>: <artifact>

## Verdict
**SIGN-OFF | REVISE.** <two sentences: does it answer its questions, and what most stands in the way>

## The 10-second read
- Eye lands first on: <...>
- The default view says: <...>
- Intended questions answered at a glance: <question: yes / partly / no>

## How it was checked
- Surfaces and widths: <...>  States: <filters, hover, touch, expanded ...>
- Renders: <paths>   Data checks: <own extraction scripts, if any>

## Content preservation   (omit if n/a)
| Check | Result |

## Ranked fixes
### 1. [S1|S2|S3] <short title>
- **What I saw:** <specific, measurable where possible>
- **Why it matters:** <rule ID and plain reason>
- **Change:** <concrete, implementable>

## Matters of taste (not blocking)
## Not checked
```
