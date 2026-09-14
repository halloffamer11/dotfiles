# 05 — Read-only dashboard pinned to one project

**What to build:** A throwaway terminal dashboard, run as a plain command with a
directory. It resolves the project at start and stays pinned to it for the life of the
process, with the project identity always visible. It shows four Tier sections; each
lane row shows lane, model, effort, harness, Meter, Remaining, Pace, eligibility and
reason, and each Tier's leader carries the Tier color plus a non-color marker. Gate and
Margin show as percentages. Meter figures are labelled as global subscription usage,
not project usage. All domain data comes from the Tier-leader operation (ticket 03);
the dashboard does no ranking arithmetic. It reloads when the project routing document
or the cached Meter document changes, with no daemon. It is visibly marked as a
prototype.

Part of [01 Prototype the project delegation dashboard](01-prototype-project-delegation-dashboard.md).
Throwaway branch only; never merged to `main`.

**Blocked by:** 03 Tier leaders from the ranking boundary

**Status:** ready-for-agent

- [ ] The command opens on a given directory, pins that project, and shows its identity.
- [ ] Four Tier sections show only globally carried lanes with the listed fields, reasons and a color-plus-marker Tier leader.
- [ ] Remaining, Pace and reset times are display-only.
- [ ] Changing the project routing fixture or the Meter fixture produces a new leader and reason in the dashboard model without a restart (tested as model state, not terminal output).
- [ ] The dashboard never dispatches and never forces a vendor re-probe.
- [ ] No snapshot tests of colors, borders or spacing.
