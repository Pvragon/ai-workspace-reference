---
name: humanizer-supplement
description: "The stance half of the humanizer pass. Catches copy that talks about itself instead of its subject: explaining its own conventions, narrating how carefully it was made, or dressing a plain label as a flourish. Run it after the blader-humanizer skill, which covers vocabulary and rhythm but not stance."
summary: "Three stance patterns the upstream humanizer misses, found after it had declared a page clean, plus words its vocabulary list (pattern 12) lacks. Each has before/after pairs from real artifacts. Retired pattern by pattern as upstream accepts them; UPSTREAM.md tracks what has been proposed."
version: 1.1.3
template: skill-definition
created: 2026-09-20
last_updated: 2026-10-16
maintainer: pvragon
tags: [writing, editing, ai-speak, humanizer, deliverables]
status: active
listing: name-only
category: writing
---

# Humanizer supplement

Together with `_external/blader-humanizer`, this is what we mean by **the humanizer pass**. Run
that skill first for vocabulary and rhythm, then this one for stance. One name, two files, until
upstream accepts these patterns and this file shrinks to nothing.

## Why a second pass exists

A clean humanizer report is not evidence that copy is clean. Proven 2026-09-15: the
`prez.example.com/travel` San Diego guide was run through the humanizer, reported clean with zero
tells, and the reader then flagged nine instances by hand. His words: *"this is ai-speak FYI.
people don't say this."*

The humanizer's patterns are about **word choice and rhythm**. These are about **stance**: the
writer standing beside the reader, explaining the document to them, instead of just telling them
the thing.

## The test

Read every sentence and ask: **is this about the subject, or about the document?**

If it explains the legend, defends the method, or dresses up a label, cut it. The page should
behave like a person who knows the material and is simply telling you about it.

## Pattern S1. Explaining the document's own conventions

**Watch for:** a sentence that describes the page's own legend, layout, structure or navigation.
"Price is a relative scale", "the table below compares", "click any item to jump", "this section
is organised by owner".

**Problem:** The reader can see the convention. Stating it signals that a machine built the
legend. A reader who can see a grid knows what a link does.

**Before:**
> Price is a relative scale: $ is the cheapest tier on this list and $$$$$ the priciest.

**After:**
> (nothing; the column header already says Price)

**Before:**
> Ratings are Google's, with the review count, because a 4.9 from 30 people is not a 4.4 from 800.

**After:**
> Ratings are Google's, with the review count.

State the convention when the reader needs it to act. Do not defend it.

## Pattern S2. Narrating your own method or integrity

**Watch for:** claims about how carefully you worked, where your inputs came from, what pipeline
assembled the page, or which parts you chose not to guess at. "Generated from", "derived by",
"compiled from a set of 27, narrowed to six", "anything unconfirmed is flagged rather than
guessed".

**Problem:** Nobody asked how carefully you worked. The reader is being told about the factory
instead of the product.

**Before:**
> Prices below are what each operator publishes; anything unconfirmed is flagged rather than guessed.

**After:**
> (nothing; flag the unconfirmed ones and let the flag speak)

**Before:**
> Generated from the 260917 Priorities sheet and the item descriptions kept with the deliverable.

**After:**
> Source: the 260917 Priorities sheet.

A **source credit** is a pointer the reader can act on and stays. A **build narration** goes. A
caveat stays where it changes what the reader does ("call to confirm") and goes where it is a
statement about your process.

Upstream pattern 25, "Writing about the previous version", is the same family but only covers
references to a prior draft. This is the general case.

## Pattern S3. Flourish where a plain label was the job

**Watch for:** a heading or closing line written for effect when a name was what the slot needed.

**Problem:** The clever framing costs the reader a beat and returns nothing. Upstream pattern 20
covers heading *typography*, title case and emojis. This covers heading *content*.

**Before:**
> The decision, on one screen

**After:**
> How the six compare

**Before:**
> The coast, to scale

**After:**
> The coast, north to south

**Before (closing line, where the sentence above had already finished the thought):**
> Everything else was negotiable. This is what survived.

**After:**
> (nothing)

## Pattern V. Words upstream's list does not carry

Upstream pattern 12 is the only vocabulary list in that skill, and it says a formal word outside
it is not a tell by itself. These are words that behave exactly like the ones on that list, in
our own output, and are not on it yet.

**Watch for:** load-bearing (figurative; keep structural engineering uses)

**Problem:** A metaphor standing in for a plain claim. "Load-bearing" says a thing matters
without saying what depends on it or what breaks without it. Say the dependency. Added by the operator,
2026-09-22.

**Before:**
> The first-line rule is load-bearing.

**After:**
> Without the first-line rule, a reader on a phone never reaches the decision.

**Watch for:** in force (on a date), for a setting, version, rate, or configuration; keep it
for a law, regulation, or contract term, where it is the idiom

**Problem:** A legal register borrowed for ordinary settings. People say a setting or a price is
"in effect on" a date; "in force" belongs to statutes and contracts. Used for configuration, it
reads as machine-written. Added by the operator, 2026-10-06, from the payer configuration page.

**Before:**
> Billing finds the payer's settings in force on the service date, or stops.

**After:**
> Billing finds the payer's settings in effect on the service date, or stops.

Add a word here only when it has been caught in a real artifact, with the pair that shows the
plain replacement. A word list without evidence grows into a ban on formal English.

## Two adjacent failures worth checking at the same time

- **Redundant column.** If a column restates what another column already encodes, cut it. A
  "Fees / night" column beside a $–$$$$$ scale was cut on sight.
- **Overclaiming to sound confident.** A section labelled "Already on their list" when nobody had
  booked anything, and the reader had only said a dinner cruise sounded fun. Confident framing
  that asserts a fact not in evidence is a hallucinated number in a softer form.

## What this is not

- **Not a ban on voice.** Self-commentary is not the same thing as voice. A dry aside about the
  *subject* is fine.
- **Not a ban on caveats.** A caveat that changes what the reader does stays.
- **Not a style preference.** Every example above was cut on sight by the person who commissioned
  the artifact.

## Where this runs

`skills/markdown-to-branded-html` loads this file and the blader-humanizer `SKILL.md` verbatim
into a judging run before it will render a page, and fails the build on findings. Override with
`--copy-ok`, skip with `--no-copy-pass`.

## Retirement

Each pattern here is a candidate for upstream. `UPSTREAM.md` tracks what has been proposed, what
upstream already covers, and what should be deleted from this file when a PR lands.
