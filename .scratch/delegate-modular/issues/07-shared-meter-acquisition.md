# 07 Separate cached Meter reads from refresh

**Blocked by:** 06 Use one Gate predicate and observation reader

**Source:** C7. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Provide one cached-only path and one explicit refresh path. Replace duplicated acquisition handling in callers while preserving probe math and refresh behavior. A cache read emits no acquisition event; rank tiers reads cache without probing.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/usage.py, scripts/rank.py, scripts/delegate.py, scripts/report.py; tests/test_usage_reset.py, tests/test_rank.py, tests/test_dispatch.py, tests/test_report.py. Inspect current callers before editing.

## Acceptance

**Status:** ready-for-agent

- [ ] Cached-only calls neither launch vendor processes nor record acquisition events.
- [ ] Refresh callers share the acquisition boundary and preserve timeout/failure handling.
- [ ] Fixture tests verify rank tiers never probes and affected consumer tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
