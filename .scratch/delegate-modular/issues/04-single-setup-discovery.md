# 04 Use one discovery result in setup

**Blocked by:** None — can start immediately.

**Source:** C4; part of M1. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Use discover.discover for setup facts. Remove discover.mjs from the default setup path. Make --no-discover skip all discovery. A missing or failing Harness produces a notice and allows other Harness results to continue. Preserve the current catalog when discovery fails.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/setup.py, scripts/discover.py; tests/test_setup.py, tests/test_discover.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`49a628b`); acceptance checks passed.

- [x] Fixture evidence shows exactly one acquisition path and no acquisition with --no-discover.
- [x] A single Harness failure does not abort setup or remove existing Lanes.
- [x] Setup and discovery tests pass without live vendor calls.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`49a628b` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.
