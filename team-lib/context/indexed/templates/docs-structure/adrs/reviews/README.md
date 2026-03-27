# ADR Reviews

> **Immutable** — Review documents are point-in-time records of decision inputs. Preserve as written; do not modify after the council session they informed.

This directory contains pre-decision review documents: structured analyses conducted by stakeholders (CEO, CTO, Council) before ADRs are formally accepted. They capture the open questions, trade-off evaluations, and stakeholder responses that shaped each decision.

## Why a Separate Subfolder

Reviews are not ADRs (they precede formal decisions), not specs (they are not implementation guidance), and not archive (they are active evidentiary records while decisions remain open). Physically adjacent to `adrs/`, they form the complete reasoning chain: review → decision → ADR.

## Contents

| Document | Author | Date | Scope |
|----------|--------|------|-------|
| *None yet* | | | |

## When to Read These

- When you need to understand *why* a proposed ADR was drafted the way it was
- When tracing a specific decision back to its original stakeholder context
- When preparing a new review and want to follow the established format

## Naming Convention

`YYMMDD-role-high-level-review.md` — date + author role + document type.

## Lifecycle

1. **Draft** — Active during stakeholder review sessions; open questions filled in
2. **Complete** — All stakeholder responses captured; document ready for council
3. **Archived** — After council decisions are incorporated into ADRs or spec updates, document is preserved unchanged
