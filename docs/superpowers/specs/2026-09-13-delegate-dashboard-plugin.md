# Project delegation dashboard prototype

Date: 2026-09-13. Status: prototype implemented on `worktree/delegate-monitor-herdr`
and technically checked 2026-09-14; independent review and human usability verdict pending.

## Problem Statement

The user can inspect delegate usage and ranking through separate command-line and
status-line views, but cannot keep one project-specific control surface open beside
the orchestrator harness. Changing Order requires leaving the active project workflow,
and the existing monitor does not show one live Tier leader for each Tier.

The user wants to change the Project order, Gate, and Margin while working, see the
deterministic result immediately, and have the next delegate ranking read the same
project policy. The control surface must not duplicate the ranking algorithm or turn
Herdr into the owner of delegate policy.

## Solution

Build a throwaway terminal dashboard hosted by a Herdr plugin pane. The plugin supplies
placement and invocation context. The dashboard stays pinned to the project from which
it opened and uses delegate's catalog and ranking boundary for all domain behavior.

The dashboard shows the four Tiers, the globally carried lanes in their effective
Project order, current Meter observations, and one clearly marked Tier leader per
Tier. The user can move lanes within a Tier and edit the project's Gate and Margin.
Every accepted edit is validated and atomically written to the project routing
document. The dashboard then recalculates the Tier leaders from the same deterministic
rules used by delegate.

The prototype answers two questions: whether a Herdr plugin is the correct host for a
persistent delegation control surface, and whether project-level Order, Gate, and
Margin controls provide useful manual steering. It is not the production dashboard.

## User Stories

1. As an orchestrator, I want to open a delegation dashboard beside my active pane, so that I can inspect routing without leaving my project workflow.
2. As an orchestrator, I want to open the same dashboard as a split, tab, zoomed pane, overlay, or popup, so that I can choose a suitable terminal layout.
3. As an orchestrator, I want the dashboard to stay pinned to its launch project, so that changing Herdr focus does not silently change the policy I am editing.
4. As an orchestrator, I want the pinned project identity to remain visible, so that I know which project an edit affects.
5. As an orchestrator, I want one section for each Tier, so that capability remains separate from Class.
6. As an orchestrator, I want lanes to remain in their global Tiers, so that the dashboard cannot redefine capability evidence.
7. As an orchestrator, I want to see only globally carried lanes, so that project policy cannot restore a lane that global setup turned off.
8. As an orchestrator, I want to see each lane's model, effort, harness, and Meter, so that I know what execution path an Order change affects.
9. As an orchestrator, I want to see current Remaining and Pace beside each lane, so that I can understand how usage affects selection.
10. As an orchestrator, I want a visible Gate value, so that I know the absolute Remaining threshold for eligibility.
11. As an orchestrator, I want a visible Margin value, so that I know how much Pace advantage permits a later lane to steal.
12. As an orchestrator, I want measured Remaining and Pace to stay read-only, so that policy edits cannot falsify vendor observations.
13. As an orchestrator, I want to move a lane up or down only within its Tier, so that Project order cannot change capability.
14. As an orchestrator, I want one Project order for the project rather than one per Class, so that Classes remain only floor-and-ceiling ranges.
15. As an orchestrator, I want a missing Project order to fall back to global Order, so that a project needs no configuration before the dashboard is useful.
16. As an orchestrator, I want newly carried global lanes to receive a deterministic fallback position, so that an older project policy remains usable after catalog growth.
17. As an orchestrator, I want each valid move to save immediately, so that the next delegate call uses it without an Apply step.
18. As an orchestrator, I want each Gate or Margin edit to save immediately, so that the next calculation and delegate call use the same values.
19. As an orchestrator, I want invalid edits rejected before the project file changes, so that the dashboard cannot block delegate with malformed policy.
20. As an orchestrator, I want writes to preserve unrelated project routing settings, so that a dashboard edit does not remove Class ranges or notes.
21. As an orchestrator, I want writes to be atomic, so that another process never reads a partial routing document.
22. As an orchestrator, I want a clear saved or error state, so that I know whether the next delegate call will see my change.
23. As an orchestrator, I want the dashboard to reload external policy changes, so that it does not show stale Order, Gate, or Margin values.
24. As an orchestrator, I want the dashboard to reload new Meter observations, so that Tier leaders follow current usage without reopening the pane.
25. As an orchestrator, I want one non-color marker on the Tier leader, so that selection is clear even without color.
26. As an orchestrator, I want Tier color to reinforce the section and leader marker, so that I can scan the four Tiers quickly.
27. As an orchestrator, I want a veto or selection reason visible for each relevant lane, so that a surprising Tier leader is explainable.
28. As an orchestrator, I want the first eligible lane in Project order to be the initial Tier leader, so that moving a lane has a predictable effect.
29. As an orchestrator, I want the existing Pace-and-Margin steal rule preserved, so that the prototype matches delegate's deterministic behavior.
30. As an orchestrator, I want a lane below Gate to remain vetoed even when it is first in Project order, so that manual ordering does not bypass capacity protection.
31. As an orchestrator, I want lowering Gate to recalculate eligibility immediately, so that a newly allowed lane can become the Tier leader.
32. As an orchestrator, I want changing Margin to recalculate steals immediately, so that the marker shows the new deterministic result.
33. As an orchestrator, I want an unknown Meter observation to retain the existing safe ranking behavior, so that the dashboard does not invent capacity data.
34. As an orchestrator, I want the dashboard to use delegate's ranking implementation, so that the displayed leader cannot drift from the next scripted choice.
35. As an orchestrator, I want the prototype to avoid dispatching work, so that I can test the controls without spending subscription usage.
36. As a maintainer, I want one documented command to link and open the local plugin, so that the prototype is trivial to run.
37. As a maintainer, I want the plugin manifest to remain a thin launcher, so that delegate can later use the same dashboard outside Herdr.
38. As a maintainer, I want the prototype visibly marked as throwaway, so that it is not mistaken for the production monitor.
39. As a maintainer, I want the prototype verdict recorded before production work begins, so that implementation follows evidence from the control surface.

## Implementation Decisions

- Herdr is the presentation and lifecycle layer only. Delegate remains the owner of
  Lane, Tier, Order, Meter, eligibility, and ranking behavior.
- Use a Herdr plugin v1 manifest with one terminal pane entrypoint. Do not build a
  native non-terminal Herdr UI or a plugin-specific ranking engine.
- The pane entrypoint must accept Herdr's supported placements. The normal launch is a
  targeted split beside the invoking pane; the same entrypoint must also be openable as
  a tab, zoomed pane, overlay, or popup.
- Resolve the project from the Herdr invocation worktree or working-directory context at
  launch. Pin that resolved project for the life of the dashboard process.
- Build the dashboard as throwaway terminal code separate from the production Rust
  monitor. Reuse delegate's Python catalog and ranking modules instead of repairing or
  extending the production monitor during this experiment.
- Add Project order to the project routing schema as one flat ordered list of lane
  names. It has no Tier keys: each named lane is grouped by its global Tier, and its
  place in the list gives its place inside that Tier. It is not Class-specific and does
  not copy lane records.
- A Project order overlays global Order. Lanes not named by a project keep a stable
  fallback order based on global Order, after the named lanes of their Tier. A project
  cannot move a lane to another Tier, because the list carries no Tier, and cannot
  restore a globally off lane.
- Validate Project order against the effective global catalog. Reject duplicates,
  unknown lanes, and globally off lanes with a message that identifies the lane and
  rule.
- The dashboard writes the complete list back in Tier-then-position sequence, so a
  move inside one Tier never changes the relative order of any other Tier.
- Extend the effective catalog projection so existing rank callers automatically see
  Project order. Preserve field-level source provenance for displayed policy.
- Keep Gate and Margin as project routing overrides. Display them as percentages while
  preserving their existing numeric meaning and validation rules.
- Do not make Remaining, Pace, reset time, or other Meter observations editable.
- Expose one canonical Tier-leader operation from the ranking boundary. It restricts
  candidates to exactly one Tier, then applies the existing carried-state, Gate,
  harness-availability, unknown-Meter, Order, Pace, name tie-break, and Margin-steal
  behavior. The dashboard must not reproduce this arithmetic.
- A Tier leader is a preview for an exact Tier. It is not the current Pick for a Class
  range, because the current dispatcher returns one Pick across the Class floor and
  ceiling and a per-job Tier raises only the floor.
- Show four Tier sections. Each lane row shows Lane identity, model, effort, harness,
  Meter, Remaining, Pace, eligibility, and reason. Use the established Tier colors and
  an additional non-color marker for each Tier leader.
- Provide keyboard movement within a Tier and concise key help. Movement cannot cross
  a Tier boundary.
- Recalculate the affected Tier leader after every accepted Order, Gate, or Margin
  edit. Recalculate all Tier leaders when shared policy or Meter observations change.
- Validate a complete proposed project routing document before saving. Save atomically,
  preserve unrelated keys, and never leave malformed or partial JSON.
- Detect an external file change before overwriting it. Reload when safe; otherwise
  show a conflict and require a fresh user action instead of silently losing data.
- Watch the project routing document and cached Meter document for changes. Do not add
  a daemon or a usage-history store.
- Provide one task-runner entry point for local build/link/open. Local plugin linking is
  the prototype installation path; publishing to the Herdr marketplace is not required.
- Keep the current Shift-U status popup unchanged during the prototype.
- Capture the prototype on a throwaway branch rather than merging its UI into main.
  Record the question, verdict, and branch pointer on the implementation ticket.

## Testing Decisions

- The main automated seam is the effective catalog-and-ranking boundary. Tests provide
  a global catalog, a project routing document, Meter fixtures, and available harnesses,
  then assert externally visible effective Order, eligibility, Tier leader, Pick reason,
  and saved project policy.
- Prefer this high seam over tests of terminal drawing internals. A Project order change
  must be proven by reloading the project through the same public catalog boundary used
  by the dispatcher.
- Extend the existing catalog tests for a valid partial list spanning several Tiers,
  global fallback, new global lanes, duplicates, unknown lanes, off lanes, preservation of
  unrelated routing keys, and atomic rejection of invalid writes.
- Extend the existing ranking tests for one Tier leader per Tier, a first-in-Order
  leader, a Gate veto selecting the next lane, Margin stealing within a Tier, unknown
  Meter behavior, unavailable harnesses, and deterministic name tie-breaking.
- Add one end-to-end command test that changes Project order, reloads the effective
  catalog, and proves that both the Tier-leader projection and the normal dispatcher
  ranking consume the new Order.
- Add end-to-end cases in which Gate and Margin changes alter the highlighted Tier
  leader exactly as the existing ranking rule specifies.
- Test that a failed validation or detected concurrent edit leaves the existing project
  routing document byte-for-byte intact.
- Test hot reload as observable dashboard state: changing the project routing fixture or
  Meter fixture causes a new leader and reason without restarting the dashboard model.
- Do not add snapshot tests for colors, borders, or exact terminal spacing. The
  prototype exists to test the interaction and hosting decision, not visual polish.
- Perform a live Herdr acceptance check: link the local plugin, open it as a targeted
  split, open the same entrypoint in at least one other supported placement, confirm the
  pinned project identity, change Order/Gate/Margin in a disposable project policy, and
  verify the file and Tier leader update together.
- The live acceptance check must not dispatch a worker or trigger repeated vendor probes.
- Run the existing catalog and ranking suites after the new project projection is added;
  all prior global and project routing behavior must remain unchanged when Project order
  is absent.

## Out of Scope

- Productionizing or refactoring the existing Rust monitor.
- Dispatching, stopping, resuming, or killing workers from the dashboard.
- Monitoring running agents or mapping Herdr panes to delegate lanes.
- Usage history, burn charts, traffic plots, or new ledger events.
- Project exclusions or restoring globally off lanes.
- Moving a lane between Tiers or editing Tier assignments.
- Editing Classes, Class floor, or Class ceiling.
- Adding, removing, or redefining Classes.
- Editing global Lane, routing, Gate, Margin, or Meter configuration.
- Editing measured Remaining, Pace, reset times, or vendor responses.
- A global or per-project preferred Meter or harness control.
- Changing the current dispatcher so a requested Tier means exactly that Tier.
- Changing the existing deterministic sort or Margin-steal rule.
- Changing the Shift-U status popup.
- Installing or publishing a marketplace plugin.
- Long-term plugin process restoration after a full Herdr server restart.

## Further Notes

- Verified against Herdr 0.9.0. Herdr plugin panes support split, tab, zoomed,
  overlay, and popup placements. Split, tab, zoomed, and overlay placements are normal
  panes; a popup is modal and has no pane identity. See the
  [Herdr plugin documentation](https://herdr.dev/docs/plugins/) and
  [CLI reference](https://herdr.dev/docs/cli-reference/).
- Project routing already hot-loads for each rank and dispatch. Gate and Margin already
  support project overrides. Project order and an exact-Tier leader projection are the
  new delegate-domain seams.
- The current status-line badges do not calculate one winner per Tier. They rank every
  Class, group each Class Pick by Meter, and display the picked lane's Tier. The new
  Tier leader must therefore use the canonical ranking boundary rather than that badge
  projection.
- The existing production monitor has known catalog and Class drift. It is evidence that
  the delegate-domain boundary must be repaired independently of the throwaway pane UI.
- Meter usage is global subscription usage even when shown in a project dashboard. The
  dashboard must not label it as project usage.
- The prototype is successful if the same pane entrypoint works in Herdr's managed
  placements, project edits affect the next canonical ranking, and the user can predict
  the marked Tier leader after changing Order, Gate, or Margin.
