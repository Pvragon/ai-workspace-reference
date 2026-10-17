---
template: directive
version: 1.0.0
summary: "Procedure for designing contractor trial projects: 4-phase workflow from discovery to deliverable creation, with trial brief template and role-specific examples."
created: 2026-01-12
last_updated: 2026-01-14
maintainer: pvragon
---

# Directive: Scope Contractor Trial Project

**Purpose:** Collaboratively design a ~4-hour paid trial project to evaluate a contractor candidate.

---

## When to Use

- Evaluating a new contractor before committing to ongoing work
- Testing specific skills relevant to the role (not just generic coding ability)
- Creating a fair, time-boxed assessment with clear success criteria

---

## Workflow

### Phase 1: Discovery (5-10 min conversation)

Gather context from the user:

1. **Role overview**
   - What's the job title/function?
   - What's the hourly rate / time commitment?
   - What are the 3-5 core skills needed?

2. **Work sample context**
   - What kind of work will they do day-to-day?
   - What tools/platforms are must-haves? (e.g., n8n, Google Workspace, specific APIs)
   - Any existing trial projects they've done before?

3. **Candidate context**
   - Experience level (junior/mid/senior)?
   - Any prior work samples or red flags to probe?
   - What specifically are you trying to validate?

---

### Phase 2: Generate Trial Options (propose 2-3)

Based on discovery, propose 2-3 trial project options. Each should:

- **Time-boxed:** 3-4 hours max
- **Skill-aligned:** Directly tests the core competencies for the role
- **Realistic:** Mirrors actual work they'd do on the job
- **Clear deliverables:** Specific outputs, not vague "build something"
- **Evaluation criteria:** What does good/bad look like?

**Format for each option:**
```
## Option [N]: [Name]
**Tests:** [skills being evaluated]
**Trigger/Input:** [what starts the task]
**Expected Output:** [specific deliverables]
**Time:** [hours]
**Difficulty:** [Easy / Medium / Hard]
**Why this one:** [1 sentence rationale]
```

---

### Phase 3: Refine Selected Option

Once user picks an option:

1. Flesh out full requirements
2. Define explicit evaluation criteria
3. Add bonus points (stretch goals)
4. Include "what success looks like" and "red flags" sections
5. Add interview questions for the follow-up call

---

### Phase 4: Create Deliverables

Generate the following to `runtime/deliverables/contractor-trial-scopes/`:

| Deliverable | Filename Format | Purpose |
|-------------|-----------------|---------|
| **Trial Brief** | `YYMMDD-trial-[name]-HHMM.md` | Send to candidate |

> **Example:** `260112-trial-lead-enrichment-0136.md`

---

## Trial Brief Template

```markdown
# Trial Project: [Name]

**Candidate:** [Name]
**Rate:** $[X]/hr (paid trial)
**Time Box:** [N] hours (hard limit)
**Date Assigned:** [Date]
**Due:** [Date/Time]

---

## Objective

[1-2 sentences describing the goal]

---

## Requirements

[Detailed requirements with table or numbered list]

---

## Deliverables

1. [Specific output #1]
2. [Specific output #2]
3. [Short documentation: what worked, what you'd improve]

---

## Evaluation Criteria

| Skill | What We're Looking For |
|-------|------------------------|
| [Skill 1] | [Observable behavior] |
| [Skill 2] | [Observable behavior] |

---

## Bonus Points (not required)

- [ ] [Stretch goal 1]
- [ ] [Stretch goal 2]

---

## What Success Looks Like

✅ [Criterion 1]
✅ [Criterion 2]

---

## Notes for Evaluator

**Interview questions:**
- [Question 1]
- [Question 2]

**Red flags:**
- [Warning sign 1]
- [Warning sign 2]
```

---

## Example Trial Projects by Role

### Ops + Automation Generalist
- Lead enrichment workflow (n8n + APIs + AI)
- Onboarding checklist automation (Google Workspace + notifications)
- Invoice follow-up sequence (AP/AR + Slack alerts)

### Content / Marketing
- Blog post outline generator (AI + research)
- Social media repurposing workflow (long-form → threads/posts)
- Competitive content audit (scraping + analysis)

### Data / Analytics
- Dashboard refresh automation (API → Google Sheets)
- Data cleanup pipeline (deduplication, normalization)
- Reporting email generator (data pull + AI summary)

---

## Principles

1. **Time-box strictly** — If they can't deliver in 4 hours, that's signal
2. **Test leverage, not heroics** — Do they find existing tools or build from scratch?
3. **Realistic > clever** — Practical tasks beat puzzle problems
4. **Clear criteria** — Both you and the candidate should know what "good" looks like
5. **Paid trials** — Respect their time; it also filters out tire-kickers
