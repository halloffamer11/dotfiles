# 02 Remove the unused ranking effort argument

**Blocked by:** None — can start immediately.

**Source:** C2. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Remove the unused effort argument from rank and update its callers. Lane identity still includes Effort; this change removes only the unused ranking parameter.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/rank.py and its callers; tests/test_rank.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`7934c95`); acceptance checks passed.

- [x] All rank call sites are inspected and updated; no caller depends on the removed parameter.
- [x] Ranking fixture outputs and existing rank tests remain unchanged.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`7934c95` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
