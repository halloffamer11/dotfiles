# Delegate dashboard prototype

This directory holds the throwaway project routing dashboard from
`.scratch/delegate-dashboard-plugin/issues/`. It is separate from the production Rust monitor in
`../delegate-mon/`.

Compatibility WIP is paused at Orin's fresh-context request (2026-09-17).
Before editing, read ticket 10 under `.scratch/delegate-dashboard-plugin/issues/`:
it owns the partial patch, two failing checks, remaining work, worker runs, and
approved Claude fallback. Resume from that record; do not treat this WIP as accepted.

- `dashboard.py --cwd DIRECTORY [--config-dir DIRECTORY] [--meters FILE]` opens
  the terminal view. Add `--json` for one noninteractive diagnostic projection.
- `model.py` exposes `DashboardModel.state`, `refresh()`, and
  `refresh_if_changed()`, plus project-policy editing through
  `move_lane()` and `save_project_policy()`. Construction resolves and pins one Git root. Refreshes
  read the effective catalog and call delegate's canonical `tier_leaders()`;
  they use cached observations and never acquire Meter data or run a vendor probe.
- `j/k` or arrows select; `J/K` or Shift-arrows move within a Tier. `g/m` opens
  Gate/Margin percentage entry, Enter saves, and Escape cancels. Percentage edits
  keep their opening policy snapshot across hot reloads. `q` closes the pane.
- The public state contains `project`, sourced `policy`, read-only `usage`, four
  `tiers`, `revision`, and `error`. Rows remain in effective Order even though
  the canonical ranking result puts its Pick first. Each row's `order_source`
  comes from the effective catalog. `p` marks project Order; `g` marks global
  Order/fallback. A fallback position can be derived, not literally stored.
- Project policy, global catalog, and Meter cache watches compare file bytes. Invalid policy
  reloads retain the last valid view with an error; missing or malformed Meter
  data becomes explicit unknown observations through `rank.meter_observations()`;
  the dashboard does not maintain a separate validity rule.
- Run `python3 test_dashboard.py`. Tests stay at the public model boundary; do
  not add terminal-spacing or color snapshots.

The WIP save adapter uses `catalog.edit_catalog` preview/apply for project edits.
Keep the editor-opening policy snapshot, fresh-global validation, unrelated keys,
and project symlink refusal. Ticket 10 records the incomplete Order compatibility.
A conflict reloads and requires a fresh action.
The final byte check is not a filesystem lock: a writer can race the rename.
Global policy and Meter observations remain read-only.

For Herdr launch or placement changes, read `launcher.py`, `open.py`, and ticket 08.
From a managed project pane, run `make -C /path/to/this/checkout delegate-dashboard`.
`DELEGATE_DASHBOARD_PLACEMENT=tab` selects a tab; `open.py --help` lists placements
and disposable fixture overrides. Python 3.11+ is required. The opener preserves
the invoking pane's project and PATH even when Make runs in the plugin checkout.
For the accepted prototype verdict and prior live evidence, read ticket 09.
Ticket 10 requires a new live check of the compatibility patch after it passes tests.
