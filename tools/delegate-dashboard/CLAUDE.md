# Delegate dashboard prototype

This directory holds the throwaway project routing dashboard from
`.scratch/delegate-dashboard-plugin/issues/`. It is separate from the production Rust monitor in
`../delegate-mon/`.

- `dashboard.py --cwd DIRECTORY [--config-dir DIRECTORY] [--meters FILE]` opens
  the terminal view. Add `--json` for one noninteractive diagnostic projection.
- `model.py` exposes `DashboardModel.state`, `refresh()`, and
  `refresh_if_changed()`, plus project-policy editing through
  `move_lane()` and `save_project_policy()`. Construction resolves and pins one Git root. Refreshes
  read the effective catalog and call delegate's canonical `tier_leaders()`;
  they never run `usage.py` or a vendor probe.
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

Saves reread the original global documents before validating complete project policy,
preserve unrelated keys, compare the loaded policy bytes, and use the catalog's
same-directory atomic writer. A conflict reloads and requires a fresh action.
The final byte check is not a filesystem lock: a writer can race the rename.
Global policy and Meter observations remain read-only.

For Herdr launch or placement changes, read `launcher.py`, `open.py`, and ticket 08.
From a managed project pane, run `make -C /path/to/this/checkout delegate-dashboard`.
`DELEGATE_DASHBOARD_PLACEMENT=tab` selects a tab; `open.py --help` lists placements
and disposable fixture overrides. Python 3.11+ is required. The opener preserves
the invoking pane's project and PATH even when Make runs in the plugin checkout.
For live acceptance evidence and the pending human verdict, read ticket 09.
