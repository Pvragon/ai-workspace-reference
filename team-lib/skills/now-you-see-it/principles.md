---
template: skill-reference
version: 0.1.0
summary: Stephen Few's data-visualization principles as checkable rules, each with an ID, a one-line why, and a source at book or chapter level. Used by now-you-see-it in both build and review mode.
created: 2026-10-22
last_updated: 2026-10-22
maintainer: pvragon
---

# Few's principles as checkable rules

Sources, abbreviated:
- **NYSI**: *Now You See It: Simple Visualization Techniques for Quantitative Analysis* (2009).
- **IDD**: *Information Dashboard Design* (2006; 2nd ed. 2013).
- **SMTN**: *Show Me the Numbers: Designing Tables and Graphs to Enlighten* (2004; 2nd ed. 2012).
- **PE**: Few's Perceptual Edge papers and newsletter.

Citations are at book or chapter level only. Nothing below is a quotation unless it is in quote marks with a source. Where a rule is our house practice rather than Few's, it is marked **(house)**: these came from the two review threads where the approach worked (2026-10-09 and 2026-10-22).

Each rule is phrased so a reviewer can answer pass or fail by looking at the rendered artifact.

## A. Purpose: the question comes first

| ID | Rule | Why | Source |
|---|---|---|---|
| A1 | The readers and the 1-3 questions the view must answer are written down before building or reviewing. | A display is judged by whether it answers its question, and there is no judging without one. | SMTN, early chapters on the purpose of tables and graphs; IDD on defining dashboard requirements |
| A2 | The default view, with no interaction, answers the main question within about 10 seconds. | Readers glance. Anything that needs a click to reach the point has lost most of them. | IDD (dashboards are monitored at a glance) |
| A3 | Every element earns its place by serving a stated question; anything that serves none is cut. | Each extra element competes for the attention the main point needs. | IDD, ch. on simplicity; (house) "less is more" |
| A4 | When the user names an existing view as the model, reproduce it. Do not expand it. | Additions to a view someone already trusts read as damage (house, 2026-10-09). | (house) |
| A5 | The title states the point or the question ("Crisis waits rose 18% in October"), not just the measure name. | The title is the first thing read; making it the takeaway saves the reader the inference. | (house), consistent with SMTN on titles and text |

## B. Form follows the relationship

Few names the quantitative relationships a graph can show and matches each to forms (SMTN, chapters on quantitative relationships and on graph design; NYSI Part II has a chapter per analysis type).

| ID | Relationship | Use | Avoid | Source |
|---|---|---|---|---|
| B1 | Time series | Line (continuous change); bars only for few, discrete periods. Time runs left to right. | Pies per period; vertical time | SMTN; NYSI, time-series chapter |
| B2 | Ranking | Bars sorted by value (largest first unless the question is "the worst") | Unsorted bars; alphabetical order when value is the point | SMTN; NYSI, ranking and part-to-whole chapter |
| B3 | Part-to-whole | Sorted bars of shares, or a single stacked bar for 2-3 parts | Pies and donuts with more than 2-3 slices; 3D anything | SMTN; PE "Save the Pies for Dessert" (2007) |
| B4 | Deviation | Bars or a line of the difference from a reference (target, plan, prior), with the reference at zero | Two series the reader must subtract by eye | SMTN; NYSI, deviation chapter |
| B5 | Distribution | Histogram, frequency polygon, strip plot, box plot | Averages alone when spread matters | SMTN; NYSI, distribution chapter |
| B6 | Correlation | Scatterplot, with a trend line when it helps | Dual-axis lines as a proxy for correlation | SMTN; NYSI, correlation chapter |
| B7 | Nominal comparison | Bars (horizontal when labels are long) | Pies; color-only comparison | SMTN |
| B8 | Geospatial | A map only when location itself is the question; otherwise a sorted bar by region | Choropleth for counts that only track population | SMTN (2nd ed.) |
| B9 | Several variables | Small multiples with shared scales; a table if exact values matter | One chart with many overlapping series | NYSI, multivariate chapter; SMTN on small multiples |
| B10 | One number | A number with its context (target, prior, direction), or a sparkline beside it; a sorted table when lookup is the job | A chart for a single value; gauges and dials | IDD, chapter on display media |
| B11 | Table vs graph | Table when readers look up exact values; graph when the shape (trend, pattern, exception) is the message | A graph used as a lookup table, or the reverse | SMTN, chapter on the roles of tables and graphs |

## C. Encode with the most accurate attribute available

| ID | Rule | Why | Source |
|---|---|---|---|
| C1 | Quantities the reader must compare go on position along a common scale, then length. | People judge position and length far more accurately than angle, area or color intensity. | SMTN; NYSI, ch. on visual perception |
| C2 | Area, angle and color intensity encode only rough or secondary quantities. | Errors in judging them are large and vary by reader. | SMTN; IDD |
| C3 | No 3D, perspective, shadows or depth on data marks. | Depth distorts length and hides marks behind others while adding no information. | SMTN; IDD, common mistakes chapter |
| C4 | One variable per visual attribute; one attribute per variable. | If color means area on one chart and status on the next, the reader decodes twice. | SMTN |

## D. Data ink and non-data ink

Few adopts Tufte's data-ink idea and turns it into a two-step method (IDD, chapter on simplicity; SMTN): first reduce non-data ink, then enhance the data ink that matters.

| ID | Rule | Why | Source |
|---|---|---|---|
| D1 | Remove non-data ink that carries nothing: backgrounds, borders, boxes, heavy gridlines, decoration, ornamental icons. | Every non-data mark competes with the data for attention. | IDD; SMTN |
| D2 | Mute the non-data ink that stays: thin, light gray gridlines and axes, or none. | Needed structure should be visible on demand to the eye, not before the data. | IDD; SMTN |
| D3 | No per-element badges, footnotes or caveat lines on the default view; definitions, provenance and caveats live in one collapsed panel. | Clutter around each number slows every glance (house, 2026-10-09: "all the badges, small text, etc are too much"). | (house), consistent with IDD |
| D4 | No redundant encoding that adds marks without adding meaning (two color bars on one line, a legend repeating direct labels). | Redundant ink is still ink. | IDD |
| D5 | A key or legend lists only encodings that appear in the current view. | A key entry for an absent mark is non-data ink and makes readers hunt for it. | (house, priorities review R1) |

## E. Preattentive attributes, used deliberately and sparingly

| ID | Rule | Why | Source |
|---|---|---|---|
| E1 | The most important data is the most salient thing on the view. Check what the eye lands on first. | Salience directs reading; if it is spent on the wrong thing, the point is missed. | NYSI and IDD, chapters on visual perception |
| E2 | One highlight per view (a hue, or weight), marking the exception; everything else neutral. | Preattentive pop-out works only when the marked item is rare. | IDD |
| E3 | Every highlight can be explained in one sentence a reader could guess ("orange = needs a data fix, not a queue"). | An unexplained highlight reads as a bug (house, 2026-10-09). | (house) |
| E4 | No attribute carries more than one meaning on the page (one hue for slips only, not slips plus risk plus hover). | Overloaded encodings collide as soon as both meanings appear. | IDD; (house, priorities review) |
| E5 | De-emphasis must stay readable (muted text about 3:1 contrast or better; muting by color, not by opacity that also fades children). | Muted is not invisible; done items still get checked. | (house, priorities review R1-R2) |
| E6 | Group with Gestalt cues (proximity, similarity, enclosure, connection) before adding lines or boxes. | Spacing groups at no ink cost. | SMTN; NYSI, ch. on visual perception |

## F. Comparison and context

| ID | Rule | Why | Source |
|---|---|---|---|
| F1 | Every key number has context: a target, the prior period of the same length, a benchmark, or a reference line. | A number alone cannot be judged good or bad. | IDD; SMTN |
| F2 | Show the comparison directly (the difference, "+5 wk", "▲ 4% vs Sep"), not two values the reader must subtract. | Arithmetic in the reader's head is slow and error-prone. | SMTN, deviation; (house) |
| F3 | Things meant to be compared sit close together on a common scale. | Comparison across distance or different scales is inaccurate. | SMTN; NYSI |
| F4 | Comparison direction color only where good or bad is unambiguous, and always paired with a sign or arrow. | Color alone fails for colorblind readers and for print. | (house, 2026-10-09); SMTN on color |
| F5 | No comparison is shown when its baseline is missing or not like-for-like; show nothing rather than a misleading delta. | A wrong comparison is worse than none. | (house, 2026-10-09) |
| F6 | Prefer a faint reference line or band (target, prior average) to an extra series. | Context without clutter. | IDD (bullet graph logic); (house) |

## G. Scales and axes

| ID | Rule | Why | Source |
|---|---|---|---|
| G1 | Bars start at zero. Always. | Bar length is the encoding; a cut baseline makes length lie. | SMTN |
| G2 | Lines and dots may use a non-zero baseline when the variation is the point, and the axis says so. | Position, not length, carries the value for lines. | SMTN |
| G3 | No dual value axes on one chart. Use two aligned charts, an indexed common base, or small multiples. | The crossing point and relative slopes are artifacts of the scale choice. | PE "Dual-Scaled Axes in Graphs: Are They Ever the Best Solution?" (2008) |
| G4 | Small multiples share scales unless the question is shape alone, and then the change of scale is stated. | Different scales across panels invite false comparison. | NYSI; SMTN |
| G5 | Log scales only for readers who read them, and labeled as log. | Most business readers read a log axis as linear. | SMTN; NYSI |
| G6 | Tick labels are round, few, and formatted (units, thousands separators, %). | The axis should be read in a glance, not parsed. | SMTN |

## H. Labels, sorting, legends

| ID | Rule | Why | Source |
|---|---|---|---|
| H1 | Label series and key marks directly; use a legend only when direct labels would collide. | A legend forces eye travel back and forth. | SMTN; IDD |
| H2 | Identity is never color alone: a label, a shape or a position also carries it. | Colorblind readers, grayscale print and projectors. | SMTN; (bundled `dataviz` agrees) |
| H3 | Sort bars and table rows by the value that answers the question, unless the categories have a natural order (time, scale steps). | Sorting makes ranking and outliers preattentive. | SMTN; NYSI |
| H4 | Label selectively: values on the few marks that matter, not on every point. | A number on every point is a table drawn badly. | SMTN |
| H5 | Units and the time window are stated once, near the top. | Readers should not guess "per day or per week, which month". | SMTN |
| H6 | Text is horizontal. Long category labels go on a horizontal bar chart, not rotated. | Rotated text is slow to read. | SMTN |

## I. Color

| ID | Rule | Why | Source |
|---|---|---|---|
| I1 | Neutral (gray) base; one accent hue for the highlight; a second only if a second category of emphasis is truly needed. | Color is the strongest preattentive attribute and is spent quickly. | IDD; SMTN |
| I2 | Categorical hues: few (about 5-8 at most), distinct in lightness as well as hue; beyond that, group into "Other" or use small multiples. | Readers cannot hold more categories in mind or tell them apart. | SMTN |
| I3 | Sequential magnitude in one hue, light to dark; diverging uses two hues with a neutral midpoint. Never a rainbow. | Rainbows have no perceptual order. | SMTN; NYSI |
| I4 | Colorblind safe: avoid red/green as the only distinction; run the bundled `dataviz` validator on any categorical palette (path in SKILL.md, "Palette validator"). | About 8% of men have red-green color vision deficiency; assume at least one of your readers does. | SMTN on color; (house) |
| I5 | Status colors (good, warning, bad) are reserved for status and come with an icon or label. | Reusing status red for "series 4" makes the reader see alarms. | (bundled `dataviz`), consistent with IDD |
| I6 | Fully saturated color only for the highlight; large areas (bars, fills, backgrounds) use soft tones. | Saturated large areas dominate the view and tire the eye. | IDD; SMTN |

## J. Tables

| ID | Rule | Why | Source |
|---|---|---|---|
| J1 | Numbers right-aligned, same decimals per column, units in the header. | Aligned digits compare by eye. | SMTN, table design chapters |
| J2 | Light or no grid: white space or faint row banding separates rows. | Grid lines are non-data ink. | SMTN |
| J3 | Only the columns the reader needs, ordered by importance; detail behind a drill. | A 20-column table is a database, not a display (house, 2026-10-09). | SMTN; (house) |
| J4 | Sorted by the value that matters, with the sort visible. | Same as H3. | SMTN |
| J5 | Headers stay visible on long tables (sticky) or are repeated. | A lookup table without column labels fails the lookup (house, priorities review R1). | (house) |
| J6 | A small inline graphic (bar, sparkline) may sit in a column when the pattern matters more than the exact digits. | Combines lookup with shape. | IDD (sparklines, bullet graphs) |

## K. Dashboards

| ID | Rule | Why | Source |
|---|---|---|---|
| K1 | A dashboard shows the most important information for its objective on a single screen, monitored at a glance (Few's definition, paraphrased). No scrolling at the target size (we use 1440x900 desktop). | Scrolling hides information from the glance the dashboard exists for. | IDD, definition chapter |
| K2 | Overview first; details on demand by click, never on the face. | The face is for monitoring; analysis happens one level down. | IDD; NYSI, interaction chapter |
| K3 | Per view: 3-4 key numbers at most, 1-2 large charts, one compact table. | Managers and executives read for the takeaway in seconds (house, 2026-10-09). | (house), consistent with IDD |
| K4 | Bullet graphs and sparklines instead of gauges, dials, thermometers and traffic-light cartoons. | Gauges spend large areas to show one number with little context. | IDD, display media chapter; PE bullet graph spec |
| K5 | The most important item sits top left (for left-to-right readers); related items are grouped and placed near each other. | Reading order and proximity set what gets seen first and compared. | IDD, chapter on placement |
| K6 | Consistent design across tabs: one term means one thing everywhere, measured the same way, defined once. | Readers compare across tabs; inconsistent definitions break trust. | IDD; (house, Reports ticket) |
| K7 | Avoid the classic dashboard mistakes: too much fragmentation, too little context, excessive detail, poorly chosen measures, meaningless variety of chart types, decoration, poor arrangement, misuse of color. | Few's catalogue of common mistakes, paraphrased and grouped. | IDD, common mistakes chapter |

## L. Interaction and detail on demand

| ID | Rule | Why | Source |
|---|---|---|---|
| L1 | Tooltips carry the exact values behind a mark and, for shares, the numerator and denominator. | Detail when wanted, absent when not. | NYSI, interaction chapter; (house) |
| L2 | Nothing essential is hover-only: every fact reachable by hover is also reachable by tap, keyboard focus, or a visible table. | Touch devices and keyboard users get no hover. | (house, priorities review R2) |
| L3 | Filters sit in one row above the content; every count, title and empty state follows the filter. | A count that ignores the filter tells the wrong story (house, priorities review R4). | (house) |
| L4 | Every filter combination is valid: no empty grids without a message, no misplaced marks, no stale counts. | Filtered views are exactly the views built to answer specific questions. | (house, priorities review R2) |
| L5 | Highlight on hover or focus brings the item forward and pushes the rest back, without moving layout. | Focus plus context; motion and reflow cost orientation. | NYSI, interaction chapter |
| L6 | Interaction modes (show only X, expand earlier periods) do not recreate the clutter the default view removed. | A "show all" mode that draws everything is the busy view again (house, priorities thread). | (house) |

## M. Surfaces and accessibility (house)

| ID | Rule | Why |
|---|---|---|
| M1 | Checked at desktop (1440x900), slide (1280x720), phone (390x844) and print media, plus every state that changes the view (expanded, filtered, hovered, tapped). | Each surface fails differently; the priorities page had bugs that appeared only under a filter or on touch. |
| M2 | No horizontal page scroll at phone width; on phones, lists group by the reader's lookup key (owner, area). | Grouping by lookup key is what makes a long list scannable. |
| M3 | Text contrast meets WCAG AA for body text; chart text at least 12px at the target size (projected slides larger). | Executives read on laptops in daylight and on projectors. |
| M4 | Light and dark modes are each designed and checked, not auto-inverted. | Inverted palettes lose their meaning. |
| M5 | The hosted page is checked once after publishing (share headers, auth walls, fonts). | The priorities page lost a column header under the prez share pill only when hosted. |
