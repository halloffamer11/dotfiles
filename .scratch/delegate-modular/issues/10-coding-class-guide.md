# 10 Add a validated coding Class guide

**Blocked by:** None — can start immediately.

**Source:** C9, C10 and M2. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Create a guide for the existing five Classes with intent, signals, examples, counter-examples and qualitative reasons to raise the Floor inside the live Range. Keep numeric Floor/Ceiling policy in routing.json. Load an optional project .delegate/classes.md overlay by matching Class section. Validate Class section headings against the closed registry and overlay headings as a subset; distinguish guide metadata headings. Replace the stale scout --tier 3 example. After STOP, skill prose shows veto reasons and asks the user for direction; the script keeps exit 1.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: SKILL.md, proposed assets/classes.md, scripts/catalog.py; tests/test_catalog.py and existing STOP tests in tests/test_rank.py. Inspect current callers before editing.

## Acceptance

**Status:** needs-triage

- [ ] Guide covers exactly the existing Classes; overlay cannot create a Class or change numeric policy.
- [ ] Validation rejects unknown/missing Class sections and duplicated numeric Floor/Ceiling declarations.
- [ ] The skill loads the guide at classification and states the STOP interaction without an interactive Python prompt.
- [ ] Catalog and existing STOP tests pass; guide examples receive maintainer review.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
