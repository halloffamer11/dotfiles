# 08 Make metering switchable

**Blocked by:** 07 Separate cached Meter reads from refresh; 11 Add focused catalog edits and previews

**Source:** C8 and M4. See the [consultation](../research/2026-09-15-refactoring-consultation.md), [scope](../research/2026-09-15-multi-domain-tiers-scope.md), and [verification notes](../research/2026-09-15-verification-notes.md).

## Scope

Add routing.meters as an explicit boolean, default true when absent, with project override. Wire the surgical setter from ticket 11. Off skips vendor probes, Gate vetoes and Margin steals; ordering reduces to Tier, Order and Lane name. Keep stored Gate and Margin. Cached Remaining may remain visible, with metering-off state and no gated mark. A user refresh may still collect observations. Ship coding-only.

**Affected surface:** Paths below are relative to `agents/skills/delegate/`: scripts/catalog.py, scripts/usage.py, scripts/rank.py, scripts/report.py, scripts/setup.py, scripts/setup_tui.py, assets/samples/routing.json; affected catalog/usage/rank/report/setup tests. Inspect current callers before editing.

## Acceptance

**Status:** landed

- [x] Validators accept booleans and reject other types; legacy documents default on.
- [x] Off performs no automatic probe and gives deterministic Tier/Order/name selection; on restores the existing policy.
- [x] Project override, cache absence and retained Gate/Margin are covered by fixtures.
- [x] Setup controls and the surgical setter agree; affected tests pass.

## Recorded, 2026-09-16

Cut after Orin accepted the agy recommendation and instructed Fable to proceed with consultation C1–C8 plus scope M1–M5. Ticket creation was interrupted by Claude access failure. This ticket records work to do, not implementation or acceptance of the deferred Domain design.

## Implementation contract, 2026-09-16

Use the ticket 11 setter for `routing.meters` with JSON `true` or `false`.
The existing setup routing screen exposes the same boolean; use its established
marker and keyboard conventions. Preserve absence on a no-op edit of legacy
routing rather than rewriting the catalog just to add the default. Dispatch
must honor the effective switch at both run start and finish, including named
dispatch automatic probes. Ranking still validates the Class and Range when off.
Fixture checks must cover that a subsequent caller cannot reintroduce a probe.

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
