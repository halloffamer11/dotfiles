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

**Status:** ready-for-agent

- [ ] Project routing validation accepts Project order as a list of lane names and rejects duplicates, unknown lanes and globally off lanes, each with a message naming the lane and the rule.
- [ ] A project cannot change a lane's Tier or restore an off lane through Project order.
- [ ] A lane added to the global catalog after the project list was written gets a deterministic fallback place after the named lanes of its Tier.
- [ ] The effective catalog exposes the overlaid Order with field-level source provenance, and `show` displays it.
- [ ] One end-to-end test writes a Project order into a fixture project, reloads the effective catalog, and proves that both Class ranking and the Tier leaders consume the new Order.
- [ ] With no Project order, every existing global and project routing behavior and test is unchanged.
