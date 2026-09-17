# 09 Complete shared setup and benchmark facts

**Blocked by:** 04 Use one discovery result in setup; 05 Move carry and display order policy out of the TUI

**Source:** C13 and the remainder of M1. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Make plain setup call bench.collect and the Markdown renderer directly. Collection should produce shared evidence data without constructing a discarded display table. Together with tickets 04 and 05 this completes M1; keep these pure moves separate from new setup behavior.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/bench.py, scripts/setup.py; tests/test_bench.py, tests/test_setup.py, tests/test_discover.py, tests/test_setup_tui.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`49a628b`); acceptance checks passed.

- [x] Plain setup no longer shells out to bench.py for collection.
- [x] Plain, TUI and HTML consumers use shared facts and carry policy; output retains existing evidence.
- [x] Affected setup and benchmark tests pass, including per-Harness errors.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`49a628b` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
