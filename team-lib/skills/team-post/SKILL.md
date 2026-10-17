---
name: team-post
description: "Write any message a teammate will read: a ClickUp task comment, a channel post, a Teams or Slack message, a PR description or review comment. First line is the outcome, short paragraphs with a list for parallel items, a hard length cap with no audience exception, every reference named at first use, nothing about the writer's own process. Run scripts/check_team_post.py on the draft before posting; it fails the draft on any hard rule."
summary: "The register for agent-written posts to teammates. Five rules that survive the reader skimming on a phone (outcome first, short paragraphs, a hard cap with no audience exception, references named, no self-narration), a checker script that fails a draft before it is posted, and before/after pairs from real posts that ran long."
version: 1.2.1
template: skill-definition
created: 2026-09-22
last_updated: 2026-10-16
maintainer: pvragon
tags: [writing, communication, clickup, teams, ai-speak, humanizer]
status: active
listing: name-only
category: messaging
---

# Team post

Use this before writing anything a teammate will read: a ClickUp task comment, a channel post, a
Teams or Slack message, a PR description or review comment, a status update. It does not govern
documents. A spec, a report, a ticket body and a page have their own standards, and the whole
point of this skill is that the post is not the place for that material.

## Why this exists

Measured 2026-09-22 across the 91 most recent comments on the active Northwind task list: median 659
characters, one comment in five over 1,500, the longest 4,228. The long ones were all written by
agents. They open with a status label, walk through a code read, and put the decision, if there is
one, in the last paragraph. In channels the same agents post release notices of 30 lines with a
dozen bold labels. The reader is on a phone between meetings. They read the first line and the
length, and they either act or scroll past.

A chat-compression plugin does not fix this. It shortens what the agent says in its own terminal.
The post is a tool argument and comes out at full length.

## The five rules

### 1. The first line is the outcome

A decision, a status, or an ask. Someone who reads only that line knows what changed and whether
they need to do anything. Not a greeting, not a heading, not a label that introduces a list, not
"quick update", not the method. If the post has a question for a named person, that person and
the question are in the first line.

### 2. Short paragraphs, and a list for parallel items

A paragraph is at most three sentences, and paragraphs are separated by a blank line. Three or
more parallel items, such as a set of rules, a set of PRs or a set of options, go in a list of
short items, not in a run of sentences. A post that fits the cap as one packed paragraph has
failed this rule; the reader skims paragraph openings and list items, and a wall gives them
nothing to skim.

Structure is not the same as decoration. A blank line and a list are structure. Headings, bold
labels and tables are decoration in a post, and a post that needs them is a document.

### 3. Hard length cap, no audience exception

| Kind | Cap |
|---|---|
| Task comment, PR comment, reply | 600 characters |
| Channel post, status update, PR description | 900 characters |

Measured on the rendered text, after mentions and links are reduced to their visible words.
Everything beyond the cap goes somewhere with a URL: the ticket body, a doc, the PR, a page. The
post carries one line that says what is there and links it.

"Technical audience" is not an exception. Audience decides which link you attach, not how long
the post is. An engineer reading a release notice wants the outcome first even more than a client
does, because they have twelve other things open. Link the trace for the engineer and the doc for
the client. The post has the same shape either way.

### 4. Every reference is named at first use

No bare ticket ID, commit hash, PR number, function name, table name or file path without the
thing it refers to, in the same sentence. "See 868abc123" tells the reader nothing on a phone.
"The pairing-model decision (868abc123) is still open" tells them what it is and whether it is
theirs. The same rule covers a conclusion: say what it is a conclusion about. "Confirmed" alone
is not a post.

### 5. Nothing about your own process

No "I read the code and", no "static code read, not an incident reconstruction", no "Note: the
screenshots could not be exported so this is a text writeup", no method defence, no sign-off
flourish. The one exception is the agent signature on the final line (`— Sent by Your Agent 🤖` or
`— Your Agent 🤖`), which identity.md requires; the checker strips it before checking. Say what is true and what to do. If a caveat changes what the reader does, keep it in
one clause. This is the stance half of the humanizer pass; the patterns are in
`skills/humanizer-supplement/SKILL.md`.

## The shape that fits under the cap

```
<outcome: decision / status / ask, with the person it is for>

<one short paragraph: the fact behind it, the thing that blocks it, or the next step>

<a list, only when there are three or more parallel items>

<one line pointing at where the detail lives, with a link>
```

Plain sentences, blank lines between paragraphs, one list at most. No headings, no bold labels,
no tables. A comment has at most six sentences outside a list, a channel post at most nine. A post
with a table is a document that took the wrong exit.

## How to use it

1. Draft the post.
2. Run the checker on the draft. It measures the rendered length, checks the first line, fails
   any paragraph over three sentences and any post over the sentence limit, finds bare
   identifiers and em dashes, counts headings and bold labels, and flags self-narration.

   ```bash
   python3 team-lib/skills/team-post/scripts/check_team_post.py draft.md --kind comment
   python3 team-lib/skills/team-post/scripts/check_team_post.py draft.md --kind channel --judge
   ```

   `--kind` is `comment` (600) or `channel` (900). `--judge` also runs one `claude -p` turn with
   the humanizer skill and the supplement loaded verbatim, for the tells a regex cannot see.
   Exit code 1 means the draft failed a hard rule and must not be posted as is.
3. Fix the draft. Move the overflow to the ticket body, the doc or the PR, and link it.
4. Post through the usual tool.

Never post around a failing check. If the cap is wrong for a case, the case is a document.

## Before and after, from real posts

Identifiers and names are changed. The shapes are exact.

### A status check on a ticket, 4,228 characters

**Before** (first and last lines of the original; the middle was a five-criterion code read)

> Status check by the dev agent, 2026-08-09. LEAVING IN BACKLOG — nothing has shipped for this. But
> this ticket is closer to done than it looks, and it is the one that genuinely does not need the
> root-cause read-out, exactly as its description argues.
>
> … 3,900 characters …
>
> CAVEAT: this is a static code read, not an incident reconstruction, and it does not explain the
> 0-mile symptom.

**After**

> Nothing shipped for this; leaving it in backlog.
>
> Route editing already refuses any driver or vehicle change once one leg on the route is closed,
> so completed rides are safe today. The not-yet-started legs on that route are frozen too, which
> fails criterion 2. Unfreezing them is the same change the mid-day switch ticket needs and waits
> on the pairing-model decision (868abc123).
>
> Full walk of the five criteria is in the ticket description.

### A QA re-test comment, 2,834 characters

**Before**

> Re-QA as tenant_admin + root cause — 2026-06-25
>
> Re-ran the Clients QA logged in as user_admin (tenant_admin) to separate "correctly hidden from a
> low-priv role" from real bugs. …
>
> … 2,400 characters of session grants, file paths and line numbers …
>
> Net: this is essentially one grant-provisioning fix, not column work.

**After**

> This is one grant-provisioning fix, not column work. Tenant admins are issued a client_portal
> grant while every Clients column and action checks for a client grant, so the SSN and Address
> columns and the Edit, Delete and Merge actions are all filtered out for everyone. Aligning the
> two names brings them all back at once. The session dump and the file references are in the
> ticket body.

### A release notice in a channel, 1,983 characters over 31 lines

**Before**

> **Production release — Monday** … fourteen bold labels, one per PR, each with a two-line
> description and a link.

**After**

> Production promotion starts at 10:00 CT and takes about 20 minutes, during which the app will
> show blank pages. Six PRs from main plus the coverage hotfix back-merge; the ones users will
> notice are route editing for not-started routes and the client-portal login. The full list with
> links is on the release ticket (868def456).

### The announcement of this skill, 881 characters, one paragraph

The first version of this skill produced this itself. It passed the checker, because the checker
measured characters and the post was under the cap. Eleven sentences in one paragraph.

**Before**

> There is a new skill in team-lib called team-post, and I would like everyone's agents to load it
> before they post anything in ClickUp for a while. The problem I keep seeing in tickets and
> channels is agent posts that run to thousands of characters and bury the decision at the bottom.
> They also drop ticket IDs, commit hashes and conclusions with nothing around them to say what
> they refer to. The skill is four rules. The first line is the outcome. There is a hard cap of
> 600 characters for a comment and 900 for a channel post, with no exception for a technical
> audience. Every reference is named the first time it appears. Nothing about how carefully the
> agent worked. It ships with a checker script that fails a draft before it goes out. I am
> testing it myself for a couple of weeks and will adjust the caps if they turn out wrong. Skill
> and checker: team-lib/skills/team-post.

**After**

> New skill in team-lib: team-post. It is a short register for anything an agent posts to a
> teammate, and I am going to try it on my own posts for a while.
>
> The rules:
> - first line is the outcome
> - a hard cap, 600 characters for a comment and 900 for a channel post
> - every reference named the first time it appears
> - nothing about how carefully the agent worked
>
> It ships with a checker that fails a draft before it goes out. If you want to try it too, it is
> at team-lib/skills/team-post.

## What this is not

- **Not a ban on detail.** Detail goes where the reader can find it when they need it, with a
  link. The post is the pointer.
- **Not a ban on warmth.** A greeting or a thank-you is fine. It just is not the first line.
- **Not a style preference.** Every rule here traces to a post a reader scrolled past.

## Related

- `skills/_external/blader-humanizer/SKILL.md` for vocabulary and rhythm tells.
- `skills/humanizer-supplement/SKILL.md` for stance: copy that talks about itself.
- `skills/markdown-to-branded-html` runs the same two references as a build gate for pages.
