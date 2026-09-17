# 10 Add a validated coding Class guide

**Blocked by:** None — can start immediately.

**Source:** C9, C10 and M2. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Create a guide for the existing five Classes with intent, signals, examples, counter-examples and qualitative reasons to raise the Floor inside the live Range. Keep numeric Floor/Ceiling policy in routing.json. Load an optional project .delegate/classes.md overlay by matching Class section. Validate Class section headings against the closed registry and overlay headings as a subset; distinguish guide metadata headings. Replace the stale scout --tier 3 example. After STOP, skill prose shows veto reasons and asks the user for direction; the script keeps exit 1.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: SKILL.md, proposed assets/classes.md, scripts/catalog.py; tests/test_catalog.py and existing STOP tests in tests/test_rank.py. Inspect current callers before editing.

## Acceptance

**Status:** landed; code checks pass and Orin accepted the guide examples.

- [x] Guide covers exactly the existing Classes; overlay cannot create a Class or change numeric policy.
- [x] Validation rejects unknown/missing Class sections and duplicated numeric Floor/Ceiling declarations.
- [x] The skill loads the guide at classification and states the STOP interaction without an interactive Python prompt.
- [x] Catalog and existing STOP tests pass; Orin accepted the guide examples.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`ca03156` adds the guide and check-guide CLI. The grok worker return was
reviewed against the ticket; root removed an unrequested Class-section-order
constraint, corrected the guide hierarchy and a glossary inconsistency, and
made the missing-file fixture use its own temporary directory. Root reran
catalog and rank tests and the skill validator; all pass. At landing, only
Orin's review of the examples remained.

## Maintainer acceptance and redraft

Orin accepted the guide and requested a humanizer redraft. The revision keeps
all five Classes and their examples, combines overlapping selection advice,
and removes repeated Floor/Ceiling, routing and dispatch instructions already
owned by SKILL.md. Class-specific reasons to use a higher Tier remain.

The redrafted guide passes `catalog.py check-guide`; all Class headings and
examples are preserved.
