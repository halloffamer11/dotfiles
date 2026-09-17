# 11 Add focused catalog edits and previews

**Blocked by:** 09 Complete shared setup and benchmark facts; 10 Add a validated coding Class guide

**Source:** C11, C12 and M3. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Provide focused Tier, Order, paired Floor/Ceiling and Gate/Margin edits with explicit global or project scope where supported. Move bulk tier-line/order application to catalog in a separate pure commit. Preserve bulk semantics (omitted carried Lanes go off); focused edits preserve omitted fields. Support entry to one setup screen without replaying unseen carry proposals. CLI spellings in the research are proposals to settle during triage. Leave the meters field to ticket 08.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/catalog.py, scripts/setup.py, scripts/setup_tui.py, SKILL.md; tests/test_catalog.py, tests/test_setup.py, tests/test_setup_tui.py, tests/test_bench_page.py. Inspect current callers before editing.

## Acceptance

**Status:** landed

- [x] Preview shows actual file and resolved stow target, global/effective values, changed fields and affected Picks using one cached observation snapshot.
- [x] Apply validates the full document, rejects intervening edits and preserves symlinks; no-op and invalid writes preserve file bytes.
- [x] Paired Range writes avoid invalid intermediate states; project Order never leaks into global data.
- [x] Focused edits preserve unrelated fields and carry choices; full bulk import semantics remain tested.
- [x] Affected catalog, setup and renderer tests pass; the documented CLI contract is reviewable before implementation.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Implementation contract, 2026-09-16

Use explicit CLI operations: `set FIELD JSON_VALUE --scope global|project`,
`range CLASS FLOOR CEILING --scope global|project`, and
`order LANE POSITION --scope global|project`. All accept `--cwd` and
`--config-dir`. Default to a JSON preview; applying requires the same operation
with `--apply --expect REVISION`, where REVISION is returned by the preview.
An explicit instruction supplying the desired value authorizes preview and apply
without asking again. No generic transaction service or saved executable proposal.

Allow `lanes.<lane>.tier` globally and `routing.gate`/`routing.margin` in either
scope. Lane names contain dots, so parse using the known prefix and final field,
not a naive split. Range changes set both bounds at once. Reserve
`routing.meters` for ticket 08. Lane carry and arbitrary JSON fields are outside
this command's allowlist. Reject project Lane Tier writes.

The revision covers both global source documents, the project document's
presence/content and their resolved paths. Re-read and compare immediately
before writing; a changed source or symlink target requires a fresh preview.
Only the chosen source document is written. Resolve its real path, preserve the
symlink, validate global and effective views, and skip the write for a semantic
no-op. The preview includes original and resulting values, a changed-field list,
resolved target, and before/after per-Class Picks and exact-Tier leaders from the
same cached observation snapshot. Report unavailable Harnesses and missing
observations. This protects against an intervening edit between commands; it is
not a cross-process transaction guarantee.

Order POSITION is one-based within the Lane's current Tier among carried Lanes.
A global move renumbers that Tier only. A project move starts from effective
Order, changes only the selected Tier's relative sequence, and preserves the
other Tiers' effective order. Existing catalog projection remains authoritative.
Moving Tier puts the Lane at the new Tier's end and shows that Order consequence
in the preview; unrelated Tier membership and carry stay unchanged.

For `setup.py --screen`, use the existing screen names (start, carry, tier1–tier4,
review, routing). Start preserves the full wizard. A focused screen starts with
current decisions, does not apply carry proposals on entry, and goes to a review
of the chosen edits before confirm. Reject incompatible plain/non-TTY use with
a clear suggestion to use the surgical CLI. Move bulk tier-line helpers in a
separate pure change; keep compatibility imports for current callers.

## CLI landed, 2026-09-16

`43f3eb1` adds `set`, paired `range`, and `order` previews and revision-checked
apply. Root review corrected the immediate pre-write revision check and Tier
moves into a destination with unordered Lanes. Catalog and rank fixtures pass;
all 13 delegate script suites passed after integration. Focused setup screens
and bulk helper relocation are still in the active setup worker.

## Landed, 2026-09-16

`6173d51` moves bulk helpers in a pure commit. `561aca4` adds focused screens and
metering control. Root corrected focused no-op Order normalization, Tier unmark,
changed-field confirmation, and source-revision/stow-preserving saves before
integration. Meter-off fixtures cover callers, project overrides, deterministic
ranking, preserved Gate/Margin and explicit refresh.

All 13 delegate script suites pass on the integrated changes. Full-wizard PTY
and focused Routing/Tier/Review/Carry no-op checks pass; a real focused PTY toggle
writes routing only and preserves stow links. Terra's independent review found
no actionable regression in these commits. Final label/layout checks preserve
the existing TUI design and make focused navigation and metering state explicit.
