# 04 — Project order overlays global Order

**What to build:** A project routing document can carry a Project order: one flat
ordered list of lane names, with no Tier keys. Each named lane stays in its global Tier,
and its place in the list gives its place inside that Tier. Named lanes come first in
their Tier; lanes the list does not name follow in global Order. The effective catalog
applies the overlay, so Class ranking, dispatch and the Tier leaders all read it with no
second implementation. `show` reports where each lane's effective Order came from.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Lands on `main`.

**Blocked by:** 03 Tier leaders from the ranking boundary

**Status:** implemented 2026-09-14 (`0c293b9`, integrated as `bea657d`); not landed on `main`

- [x] Project routing validation accepts Project order as a list of lane names and rejects duplicates, unknown lanes and globally off lanes, each with a message naming the lane and the rule.
- [x] A project cannot change a lane's Tier or restore an off lane through Project order.
- [x] A lane added to the global catalog after the project list was written gets a deterministic fallback place after the named lanes of its Tier.
- [x] The effective catalog exposes the overlaid Order with field-level source provenance, and `show` displays it.
- [x] One end-to-end test writes a Project order into a fixture project, reloads the effective catalog, and proves that both Class ranking and the Tier leaders consume the new Order.
- [x] With no Project order, every existing global and project routing behavior and test is unchanged.

## Implemented, 2026-09-14

The ticket worktree adds `project_order` at the public catalog seam.
`validate_project_routing` validates a proposed project document together with the
global lane and routing documents, including the complete merged Class ranges. The
effective lane projection groups the flat list by the existing global Tier, puts named
carried lanes first, and falls back to global Order then lane name. Order provenance is
reported through `sources` and by `catalog.py show`; Tier and `enabled` remain global.

Evidence is in `agents/skills/delegate/tests/test_catalog.py` section 8, including the
fixture-project reload that changes both `rank("impl", ...)` and
`tier_leaders(...)[1]`. Verified in this worktree with:

- `python3 agents/skills/delegate/tests/test_catalog.py`
- `python3 agents/skills/delegate/tests/test_rank.py`
- `python3 -m py_compile agents/skills/delegate/scripts/catalog.py`
- `git diff --check`

## Integration check, 2026-09-14

The lead repeated the catalog and ranking suites. A new regression test showed
that the routing-only boundary raised `TypeError` for a non-object project
document. Shape validation now runs before inspecting Project order, so this
case raises the usual plain-language `CatalogError`. Both suites pass.
