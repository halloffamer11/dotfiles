# Delegate dashboard prototype

This directory holds the throwaway, read-only terminal dashboard from delegate
dashboard ticket 05. It is separate from the production Rust monitor in
`../delegate-mon/`.

- `dashboard.py --cwd DIRECTORY [--config-dir DIRECTORY] [--meters FILE]` opens
  the terminal view. Add `--json` for one noninteractive diagnostic projection.
- `model.py` exposes `DashboardModel.state`, `refresh()`, and
  `refresh_if_changed()`. Construction resolves and pins one Git root. Refreshes
  read the effective catalog and call delegate's canonical `tier_leaders()`;
  they never run `usage.py` or a vendor probe.
- The public state contains `project`, sourced `policy`, read-only `usage`, four
  `tiers`, `revision`, and `error`. Rows remain in effective Order even though
  the canonical ranking result puts its Pick first.
- Project policy and Meter cache watches compare file bytes. Invalid policy
  reloads retain the last valid view with an error; missing or malformed Meter
  data becomes explicit unknown observations.
- Run `python3 test_dashboard.py`. Tests stay at the public model boundary; do
  not add terminal-spacing or color snapshots.

Tickets 06 and 07 may add safe project-policy edits here. Keep ranking arithmetic
in delegate's catalog/ranking modules and preserve this read-only state projection.
