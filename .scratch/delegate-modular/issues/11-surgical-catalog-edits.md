# 11 Add focused catalog edits and previews

**Blocked by:** 09 Complete shared setup and benchmark facts; 10 Add a validated coding Class guide

**Source:** C11, C12 and M3. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Provide focused Tier, Order, paired Floor/Ceiling and Gate/Margin edits with explicit global or project scope where supported. Move bulk tier-line/order application to catalog in a separate pure commit. Preserve bulk semantics (omitted carried Lanes go off); focused edits preserve omitted fields. Support entry to one setup screen without replaying unseen carry proposals. CLI spellings in the research are proposals to settle during triage. Leave the meters field to ticket 08.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/catalog.py, scripts/setup.py, scripts/setup_tui.py, SKILL.md; tests/test_catalog.py, tests/test_setup.py, tests/test_setup_tui.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** needs-triage

- [ ] Preview shows actual file and resolved stow target, global/effective values, changed fields and affected Picks using one cached observation snapshot.
- [ ] Apply validates the full document, rejects intervening edits and preserves symlinks; no-op and invalid writes preserve file bytes.
- [ ] Paired Range writes avoid invalid intermediate states; project Order never leaks into global data.
- [ ] Focused edits preserve unrelated fields and carry choices; full bulk import semantics remain tested.
- [ ] Affected catalog, setup and renderer tests pass; the documented CLI contract is reviewable before implementation.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.
