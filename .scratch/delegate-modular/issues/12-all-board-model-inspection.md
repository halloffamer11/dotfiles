# 12 Inspect model evidence across boards

**Blocked by:** 09 Complete shared setup and benchmark facts

**Source:** M5. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Add read-only model inspection beside collect and share evidence records with HTML. Show measured efforts, exact identities, source/version/date, score, within-board standing, uncertainty, cost basis and missing rows. Separate Model-family and Lane views. Reconcile boards.json relevance labels explicitly. Browser research notes remain linked evidence until ingestion is approved; do not present notes as accepted machine rows.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/bench.py, scripts/bench_page.py, assets/boards.json, assets/sources.json, SKILL.md; tests/test_bench.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** needs-triage

- [ ] Fixtures cover exact effort, absent data, conflicting identities and benchmark version separation.
- [ ] Cost labels distinguish source task sets and whole-run Terminal-Bench costs; no cross-source cost comparison or combined score.
- [ ] Unknown identity mappings remain unresolved and inspection changes no Tier, Order or carry policy.
- [ ] Benchmark and page tests pass; evidence availability limits are visible.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
