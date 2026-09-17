# 12 Inspect model evidence across boards

**Blocked by:** 09 Complete shared setup and benchmark facts

**Source:** M5. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Add read-only model inspection beside collect and share evidence records with HTML. Show measured efforts, exact identities, source/version/date, score, within-board standing, uncertainty, cost basis and missing rows. Separate Model-family and Lane views. Reconcile boards.json relevance labels explicitly. Browser research notes remain linked evidence until ingestion is approved; do not present notes as accepted machine rows.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/bench.py, scripts/bench_page.py, assets/boards.json, assets/sources.json, SKILL.md; tests/test_bench.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** landed

- [x] Fixtures cover exact effort, absent data, conflicting identities and benchmark version separation.
- [x] Cost labels distinguish source task sets and whole-run Terminal-Bench costs; no cross-source cost comparison or combined score.
- [x] Unknown identity mappings remain unresolved and inspection changes no Tier, Order or carry policy.
- [x] Benchmark and page tests pass; evidence availability limits are visible.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Implementation contract, 2026-09-16

Use `bench.py model MODEL` with `--config-dir`, repeatable `--effort-rows`,
optional local `--epoch-csv`, and `--json`. Preserve the existing report CLI.
Default model inspection is read-only and does not fetch sources implicitly.
The human-readable output and JSON expose the same evidence records, also used
by the HTML view. An accepted mixed-source row is evidence only when its
identity/effort can be attributed without guessing. Keep unresolved rows visible
with their reason. Standing is scoped to the loaded snapshot and board/version;
label direction and ties, and leave standing unknown when direction is unknown.
Web research notes remain reference links; this ticket does not authorize a new
scraper, new accepted dataset, or treating unsourced numbers as measurements.

## Landed, 2026-09-16

`9c15e0c` implements read-only `bench.py model`, shared evidence records for HTML,
source/version-scoped standing and explicit evidence limits. Root review fixed
canonical queries hiding unresolved candidate rows, exposed uncertainty and costs
in the family text view, and corrected the multimodal relevance label.

Independent checks: bench, bench_page, setup and setup_tui fixtures pass. A local
inspection of `gpt-5.6-sol` against all three accepted source files completed
without fetching. Quoted source descriptions and their dates are unchanged;
relevance labels are interpretations. No new dataset or Domain is enabled.

Terra’s separate read-only review found no actionable regression. It inspected
the changed surface and repeated a local three-source inspection. It did not
revalidate live source claims or the broader redesign.
