# 01 — Prototype the project delegation dashboard

**What to build:** Implement the agreed throwaway Herdr plugin and project-pinned
delegation dashboard described in the
[project delegation dashboard prototype spec](../../../docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md).
The prototype must use delegate's effective catalog and ranking boundary, edit only
Project order, Gate, and Margin, and visibly mark one deterministic Tier leader in
each Tier.

**Broken into:** 02-09 in this directory. 02-04 (ranking prefactor, Tier leaders,
Project order) land on `main`; 05-09 (dashboard, plugin, live check) stay on the
throwaway branch. 09 closes this ticket's boxes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Acceptance

- [ ] The project routing schema accepts a validated Project order as one flat list of lane names, grouped by each lane's global Tier, and preserves global fallback when it is absent.
- [ ] A project can reorder globally carried lanes inside a Tier but cannot change Tier, restore an off lane, name an unknown lane, or list a lane twice.
- [ ] Existing rank and dispatch callers consume the effective Project order without a second ranking implementation.
- [ ] The canonical ranking boundary returns one deterministic Tier leader for each exact Tier with the existing eligibility and Margin-steal behavior.
- [ ] Project Gate and Margin remain valid hot-loaded overrides and measured Meter fields remain read-only.
- [ ] The terminal dashboard shows four Tier sections, lane identity, model, effort, harness, Meter observations, reasons, Project order, and a color-plus-marker Tier leader.
- [ ] Moving a lane with the keyboard stays inside its Tier, validates the complete policy, atomically saves it, and updates the marker immediately.
- [ ] Editing Gate or Margin validates, atomically saves, and updates affected Tier leaders immediately.
- [ ] Dashboard writes preserve unrelated project routing keys and do not overwrite a concurrent external edit silently.
- [ ] External project policy and Meter-cache changes reload without restarting the dashboard.
- [ ] The Herdr plugin opens the dashboard pinned to the invoking project in a targeted split and supports the same pane entrypoint in the other documented placements.
- [ ] One documented task-runner command builds or prepares, links, and opens the local prototype.
- [ ] Existing catalog and ranking tests pass, and new high-seam tests cover Project order, Gate, Margin, Tier leaders, invalid writes, and hot reload.
- [ ] A live Herdr check proves split plus one other placement without dispatching a worker or repeatedly probing a vendor.
- [ ] The prototype UI is committed only to a throwaway branch; this ticket records the tested question, verdict, and branch pointer.

## Notes

The accepted testing seam is the effective catalog-and-ranking boundary. Terminal
rendering details are not the contract. The live Herdr check covers only the plugin
host, project pinning, and interaction that cannot be established below that boundary.
