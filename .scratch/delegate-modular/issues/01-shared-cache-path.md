# 01 Share the Meter cache path

**Blocked by:** None — can start immediately.

**Source:** C1. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Use usage.get_cache_path as the common cache-path boundary. Make rank and report use the same default and existing environment override. This is a pure move; preserve probe math, cache validity and ranking behavior.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/usage.py, scripts/rank.py, scripts/report.py; tests/test_usage_reset.py, tests/test_rank.py, tests/test_report.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`53e453b`); acceptance checks passed.

- [x] Default and overridden cache paths agree across usage, ranking and reporting.
- [x] Missing-cache behavior is preserved; the affected usage, rank and report tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`53e453b` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
