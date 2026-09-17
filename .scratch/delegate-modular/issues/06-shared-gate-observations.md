# 06 Use one Gate predicate and observation reader

**Blocked by:** 01 Share the Meter cache path

**Source:** C6. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Own observation validity and eligible(observation, gate) in usage.py; retain a rank compatibility export if needed by existing consumers. Ranking, limits --eligible and statusline use effective routing.gate at Meter granularity. Remove eligibility dependence on cached status and hard-coded 10% checks. Unknown Remaining does not veto; Remaining equal to Gate is eligible.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/usage.py, scripts/rank.py, scripts/report.py; tests/test_usage_reset.py, tests/test_rank.py, tests/test_report.py. Inspect current callers before editing.

## Acceptance

**Status:** landed 2026-09-16 (`fe4286c`); acceptance checks passed.

- [x] Rank, limits and statusline agree below, at and above Gate, including a project override.
- [x] Stale, malformed and missing cache observations follow one validity policy.
- [x] Unknown observations remain eligible and sort unknown-last; measured no-eligible cases still STOP with exit 1.
- [x] Affected usage, rank and report fixture tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Landed, 2026-09-16

`fe4286c` implements this ticket. Root reviewed the worker diff and reran the
affected suites against local fixtures. The Meter work additionally fixes
import-time timestamps, validates before agy normalization, and preserves bounded
acquisition; setup saved-discovery inputs perform no live probes. Independent
review of the integrated foundation is running; any findings will be recorded
with their follow-up fixes. No live catalog policy was edited by this work.

## Independent review, 2026-09-16

Terra’s read-only Meter/catalog review found missing envelope timestamp and
unvalidated display-number gaps. `9a74a4f` rejects those documents at the shared
boundary; legacy bare maps still need no timestamp. Usage, rank, report, dispatch
and catalog fixtures pass. A valid-envelope Tier fixture now includes its timestamp.
