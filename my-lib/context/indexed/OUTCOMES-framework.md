---
template: framework-definition
version: 1.0.1
summary: "OUTCOMES framework: merges OKRs with RASCI role assignment into a single unified structure for goal-setting and accountability. Load when setting up objectives or assigning work."
created: 2026-02-12
last_updated: 2026-02-18
maintainer: pvragon
---

# The OUTCOMES Framework

OUTCOMES is a leadership and accountability framework that merges goal-setting (OKRs) with role assignment (RASCI) into a single unified structure. Every objective and its component work items are defined, measured, time-bound, and assigned in one place.

## The Acronym

| Letter | Component | Description |
| :--- | :--- | :--- |
| **O** | **Objective** | The goal to be achieved. |
| **U** | **Unit of Work** | A specific task or deliverable that contributes to the Objective. |
| **T** | **Timing** | The deadline or time constraint for the Objective or Unit of Work. |
| **C** | **Collaborators** | Those who must be consulted, informed, or who provide support. |
| **O** | **Owner** | The single person accountable for the Objective or Unit of Work succeeding. |
| **M** | **Metric** | How progress and success are quantitatively measured (Key Results, KPIs). |
| **E** | **Executor** | The person doing the work. |
| **S** | **Success** | The Definition of Done — qualitative criteria that confirm completion and quality. |

## How It Works

An OUTCOMES table combines an OKR table with a RASCI matrix. It reads like a flat file — every row has both an Objective and a Unit of Work column. The Objective value repeats on every row that belongs to it, making each row self-contained and filterable. The columns define what the work is, when it's due, how it's measured, and what "done" looks like. Person columns on the right side carry role assignments.

### Role Codes (used in person columns)

| Code | Role | Meaning |
| :--- | :--- | :--- |
| **O** | Owner | Accountable for success. One per row. The buck stops here. |
| **E** | Executor | Doing the work. Can (sparingly) be multiple per row. |
| **C** | Collaborator | Consulted, informed, or supporting. Can be multiple per row. |

### Table Format

```
| Objective | Unit of Work | Timing | Metric | Success | Alice | Bob | Carol |
|-----------|--------------|------------|--------|---------|-------|-----|-------|
```

- The **Objective** column groups rows by goal. The same objective appears on every row belonging to it.
- The **Unit of Work** column identifies the specific task. A row where Unit of Work is blank defines the objective-level ownership, metrics, and success criteria.

### Example

| Objective | Unit of Work | Timing | Metric | Success | Alice | Bob | Carol |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| Migrate to new payroll provider | | Q1 2026 | Migration complete, 0 payroll errors in first cycle | All employees paid correctly on new system, old system decommissioned | O | E | C |
| Migrate to new payroll provider | Evaluate vendor options | Jan 15 | 3+ vendors assessed | Recommendation doc delivered to Owner | C | E | |
| Migrate to new payroll provider | Execute data migration | Feb 15 | 100% employee records transferred | Data validated against source, no discrepancies | | E | C |
| Migrate to new payroll provider | Run parallel payroll cycle | Mar 1 | Old and new systems produce identical outputs | Sign-off from finance that outputs match | O | E | |
| Migrate to new payroll provider | Decommission old system | Mar 31 | System access revoked, data archived | Confirmation from IT, archive accessible for audit | | E | C |

In this example:
- The first row (blank Unit of Work) defines objective-level ownership: Alice owns it, Bob executes, Carol collaborates.
- Subsequent rows define the units of work with their own deadlines, metrics, success criteria, and role assignments.
- Every row carries the Objective value, so any single row is self-contained — you can filter, sort, or extract rows without losing context.

## Rules

1. **Every Objective must have exactly one Owner.** Shared ownership is no ownership.
2. **Every Unit of Work must have at least one Executor.** If nobody is doing the work, it won't get done.
3. **Metrics and Success are not the same thing.** Metrics are quantitative (numbers, percentages, counts). Success is the "Definition of Done" — the qualitative conditions that must be true for work to be considered complete. A metric might say "100% of records migrated," but Success says "data validated against source, no discrepancies, sign-off from finance." Metrics tell you if you're on track; Success tells you when you can stop.
4. **Blank cells are intentional.** Not everyone is involved in every unit of work. A blank cell means that person has no role on that row.
5. **Timing is required.** If there's no deadline, it's not a commitment — it's a wish.

## Using This Framework

When building an OUTCOMES table:

1. **Start with Objectives.** Define what you're trying to achieve.
2. **Ground each Objective immediately.** Set its Success criteria, Metrics, and Timing before moving on. This locks in a clear picture of what "done" looks like at the goal level.
3. **Decompose into Units of Work.** Ask: "What must get done for this Objective to succeed?"
4. **Ground each Unit of Work.** Set Success, Metrics, and Timing for every unit. The same discipline applies — define done before defining who.
5. **Assign roles last.** Once the work is fully defined, assign Owner, Executor, and Collaborator to each row.
