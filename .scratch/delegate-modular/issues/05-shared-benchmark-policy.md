# 05 Move carry and display order policy out of the TUI

**Blocked by:** None — can start immediately.

**Source:** C5; part of M1. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Move dominating_effort, propose_enabled, group_lanes and lane_order beside bench.collect. Give both renderers structured carry decisions, including kind, source and competitor where applicable. Renderers own wording; HTML must not parse reason prose. Preserve the settled same-source carry arithmetic and existing human assignments.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/bench.py, scripts/setup_tui.py, scripts/bench_page.py; tests/test_bench.py, tests/test_setup_tui.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`49a628b`); acceptance checks passed.

- [x] TUI and HTML consume one shared policy result with no policy import from the TUI.
- [x] Unavailable evidence and an empty proposal remain distinct.
- [x] Domination fixtures preserve same-source cost comparisons and exclude the AA composite; affected benchmark and renderer tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`49a628b` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
