# 03 Share ranking output formatting

**Blocked by:** 02 Remove the unused ranking effort argument

**Source:** C3. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Put the Class header and ranked-row formatting behind one function used by the rank CLI and delegate run. Remove delegate._print_rank_output duplication. Keep the existing output and STOP contract.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/rank.py, scripts/delegate.py; tests/test_rank.py, tests/test_dispatch.py. Inspect current callers before editing.

## Acceptance

**Status:** ready-for-agent

- [ ] Both commands use the shared formatter and preserve their established output.
- [ ] Rank CLI and run --dry-run fixtures pass, including no eligible Lane and exit 1.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
