# 02 Remove the unused ranking effort argument

**Blocked by:** None — can start immediately.

**Source:** C2. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Remove the unused effort argument from rank and update its callers. Lane identity still includes Effort; this change removes only the unused ranking parameter.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/rank.py and its callers; tests/test_rank.py. Inspect current callers before editing.

## Acceptance

**Status:** ready-for-agent

- [ ] All rank call sites are inspected and updated; no caller depends on the removed parameter.
- [ ] Ranking fixture outputs and existing rank tests remain unchanged.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
