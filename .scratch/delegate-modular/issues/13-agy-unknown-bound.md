# 13 Treat agy combined Remaining and Pace as unknown

**Blocked by:** 06 Use one Gate predicate and observation reader; 07 Separate cached Meter reads from refresh

**Source:** Accepted agy decision; grok quota-axi comparison opportunity 8. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Keep observed agy window values for display, but emit unknown combined Remaining and Pace until evidence establishes a joint bound. Do not derive min(5h, weekly) or a seven-day Pace for agy selection. Normalize existing cached agy observations so pre-change derived numbers cannot drive selection until cache expiry. Keep other Meters unchanged. This is a separate behavior change, not part of a pure acquisition move.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/usage.py, scripts/rank.py, scripts/report.py as needed; tests/test_usage_reset.py, tests/test_rank.py, tests/test_report.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`fe4286c`); acceptance checks passed.

- [x] Both fresh and existing cached agy observations yield unknown combined Remaining and Pace, with an explanatory note.
- [x] agy sorts unknown-last, cannot take a Margin steal using invented Pace and is not vetoed by an unknown Remaining.
- [x] An otherwise eligible agy Lane can still be picked when measured alternatives are unavailable; raw window values remain visible without a combined bound claim.
- [x] Usage, ranking and report fixtures cover these cases without live probes.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

The accepted decision is recorded in the [grok comparison](../research/2026-09-15-quota-axi-comparison-grok.md), opportunity 8 and maintainer question 5. Orin answered “1/ per rec 2/ proceed” in Fable session `e64493bf-d730-47f6-a381-b2320973452f` at 2026-09-16 01:17 UTC (September 15 local time).

## Landed, 2026-09-16

`fe4286c` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
