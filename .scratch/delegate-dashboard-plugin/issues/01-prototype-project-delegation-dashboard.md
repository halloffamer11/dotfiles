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

**Status:** ready-for-human — technical acceptance passed; usability verdict and independent review pending

## Acceptance

- [x] The project routing schema accepts a validated Project order as one flat list of lane names, grouped by each lane's global Tier, and preserves global fallback when it is absent.
- [x] A project can reorder globally carried lanes inside a Tier but cannot change Tier, restore an off lane, name an unknown lane, or list a lane twice.
- [x] Existing rank and dispatch callers consume the effective Project order without a second ranking implementation.
- [x] The canonical ranking boundary returns one deterministic Tier leader for each exact Tier with the existing eligibility and Margin-steal behavior.
- [x] Project Gate and Margin remain valid hot-loaded overrides and measured Meter fields remain read-only.
- [x] The terminal dashboard shows four Tier sections, lane identity, model, effort, harness, Meter observations, reasons, Project order, and a color-plus-marker Tier leader.
- [x] Moving a lane with the keyboard stays inside its Tier, validates the complete policy, atomically saves it, and updates the marker immediately.
- [x] Editing Gate or Margin validates, atomically saves, and updates affected Tier leaders immediately.
- [x] Dashboard writes preserve unrelated project routing keys and do not overwrite a concurrent external edit silently.
- [x] External project policy and Meter-cache changes reload without restarting the dashboard.
- [x] The Herdr plugin opens the dashboard pinned to the invoking project in a targeted split and supports the same pane entrypoint in the other documented placements.
- [x] One documented task-runner command builds or prepares, links, and opens the local prototype.
- [x] Existing catalog and ranking tests pass, and new high-seam tests cover Project order, Gate, Margin, Tier leaders, invalid writes, and hot reload.
- [x] A live Herdr check proves split plus one other placement without dispatching a worker or repeatedly probing a vendor.
- [x] The prototype UI is committed only to a throwaway branch; this ticket records the tested question, verdict, and branch pointer.

## Notes

The accepted testing seam is the effective catalog-and-ranking boundary. Terminal
rendering details are not the contract. The live Herdr check covers only the plugin
host, project pinning, and interaction that cannot be established below that boundary.

## Landed, 2026-09-14

Scope: committed on `worktree/delegate-monitor-herdr`, not merged to `main`.

Branch: `worktree/delegate-monitor-herdr`. Backend commits for eventual `main`
integration are `06a2f27`, `71eb342`, `bea657d`, and the validation fix `aceaf2f`.
The UI and launcher remain on the prototype branch. No merge to `main` or push
was performed.

The seven completed ticket checkouts and Herdr workspaces were removed after
clean-status checks; `delegate-dashboard-t02` through `delegate-dashboard-t08`
branches remain available. The prototype checkout and local plugin link remain.

Questions: Is Herdr the right host for this persistent control surface? Do
Project order, Gate, and Margin provide useful manual steering?

Technical verdict: Herdr is suitable for this prototype. The same entrypoint
worked as a split and tab, stayed pinned, and saved all three controls with the
predicted canonical leader changes. Invalid and stale input preserved existing
bytes. This establishes correct hosting and steering behavior, not Orin's
usability verdict or production readiness. Ticket 09 records the live evidence;
Orin's prediction check remains open.

Verification: all 13 delegate test scripts passed, as did all 20 dashboard tests,
Python compilation, and `git diff --check`. The report tests ran with
`NO_COLOR=` because the session's inherited `NO_COLOR=1` suppresses their color
fixture output.

Independent two-axis review is pending. The requested `implement` skill calls
for `code-review`; briefs are prepared as `../brief-review-standards.md` and
`../brief-review-spec.md`, against pre-implementation baseline `ea60b33`.
Eligible non-author-family routing is blocked by the repository's no-bypass
rule: Antigravity's read-only relay uses sandboxed tool auto-approval, while
Claude and Grok are below Gate. A narrow exception was requested from Orin and
has not been granted. No independent review result is claimed.
