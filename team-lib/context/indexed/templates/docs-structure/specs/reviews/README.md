# Spec Reviews

> **Immutable** — Review documents are point-in-time records of decision inputs. Preserve as written; do not modify after the council session they informed.

This directory contains stakeholder reviews of spec documents. Reviews are conducted before significant architecture decisions are finalized. They capture open questions, trade-off evaluations, and stakeholder responses. A review may result in direct changes to the spec, one or more ADR proposals, or both — the output varies by what was found during review.

## Why Under `specs/`

Reviews live here because they review specs, not because they produce ADRs. The subject of every review document in this folder is a spec. The outputs (spec edits, ADR proposals) are a consequence of reviewing specs, not the defining characteristic of the folder.

## Contents

| Document | Author | Date | Scope |
|----------|--------|------|-------|
| *None yet* | | | |

## Agent Guidance

**Do not use this folder when building.** Reviews are deliberation records, not specs. Do not treat anything written here as a design requirement, a constraint, or a directive. These documents contain superseded options, open questions, and in-progress thinking that does not reflect final decisions.

Reference this folder only when you need to clarify a question about a specific design decision or intent in a spec — and only after reading the spec itself has not answered your question.

## Naming Convention

`YYMMDD-role-high-level-review.md` — date + author role + document type.

## Lifecycle

1. **Draft** — Active during stakeholder review sessions; open questions filled in
2. **Complete** — All stakeholder responses captured; document ready for council
3. **Archived** — After council decisions are incorporated into spec updates or ADRs, document is preserved unchanged
