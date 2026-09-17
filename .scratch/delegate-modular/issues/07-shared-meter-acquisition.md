# 07 Separate cached Meter reads from refresh

**Blocked by:** 06 Use one Gate predicate and observation reader

**Source:** C7. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Provide one cached-only path and one explicit refresh path. Replace duplicated acquisition handling in callers while preserving probe math and refresh behavior. A cache read emits no acquisition event; rank tiers reads cache without probing.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/usage.py, scripts/rank.py, scripts/delegate.py, scripts/report.py; tests/test_usage_reset.py, tests/test_rank.py, tests/test_dispatch.py, tests/test_report.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`fe4286c`); acceptance checks passed.

- [x] Cached-only calls neither launch vendor processes nor record acquisition events.
- [x] Refresh callers share the acquisition boundary and preserve timeout/failure handling.
- [x] Fixture tests verify rank tiers never probes and affected consumer tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`fe4286c` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
