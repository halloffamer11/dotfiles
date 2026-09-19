# Delegate dashboard prototype

This directory holds the throwaway project routing dashboard from
`.scratch/delegate-dashboard-plugin/issues/`. It is separate from the production Rust monitor in
`../delegate-mon/`.

The compatibility pass with current main is implemented (2026-09-18) and waits for
Orin's review; ticket 10 under `.scratch/delegate-dashboard-plugin/issues/` owns the
decisions, the review adjudication and the live evidence.

- `dashboard.py --cwd DIRECTORY [--config-dir DIRECTORY] [--meters FILE]` opens
  the terminal view. Add `--json` for one noninteractive diagnostic projection.
- Layout variants (throwaway, branch `worktree/delegate-monitor-herdr-layouts`):
  `--layout NAME` picks one and `v` cycles every `proto_layout_*.py` beside
  `dashboard.py`, in `LAYOUT_ORDER`. A variant exposes `NAME`, `render(state, *,
  width, height, selected_lane, editor, message, view)` returning exactly
  `height` painted strings, and an optional `handle_key(key, state, view)`. The
  host owns the model, the selected Lane, the editors and `j/k`, arrows, `J/K`,
  `g`, `m`, `r`, `q`, `v`; every other key goes to the variant. A variant that
  returns a carried Lane name from `handle_key` also moves the selection there.
  A variant may also expose `selectable(state, view)`, the carried Lane names
  `j`/`k` may stop on, so a row it hides is never walked; without it every
  carried Lane is a stop. A `handle_key` that accepts a `model` keyword is handed
  the host's `DashboardModel`, which is how a variant reaches a save path of its
  own; one that does not is called with the same three arguments as before.
  Left, right and Shift+Tab are in `KEY_SEQUENCES`, so a variant reads them as
  one key each instead of as `ESC`, `[` and a letter. An import failure is
  skipped and named in the footer
  message. `proto_layout_current.py` is the shipped rendering;
  `proto_layout_panel.py` is the instrument panel from
  `_work/tui-review/review-opus-high.md`; `proto_layout_deck.py` is the merge
  Orin's verdict asked for in ticket 11, and is the only variant that uses
  `selectable`. `deck` has three bodies that `Tab` cycles and `a` reaches
  directly: the Tier list, the Harness table (Harnesses down, Tiers across) and
  the Gate/Margin aid (per Meter, Remaining against the Gate mark and Pace
  against the Pick's Pace plus the Margin, the rule at `rank.py:177-183`).
  `h`/`j`/`k`/`l` and the arrows move the selection; in the table `j`/`k` walk
  down one Tier column and `h`/`l` cross to the nearest Lane one column over,
  and in the list `h`/`l` close and open a deck. `H`/`L` propose a Tier move and
  write only on `y`. `d` writes the terms and every reason code at the foot, `z`
  folds the deck or the Harness row under the cursor, and `?` lists the keys.
  `proto_dump.py --layout NAME --width N --height N` prints one frame with ANSI
  stripped; `--check` fails on an over-wide line. Do not add tests for variants.
- `model.py` exposes `DashboardModel.state`, `refresh()`, and
  `refresh_if_changed()`, plus project-policy editing through
  `move_lane()` and `save_project_policy()`, and the one global write,
  `preview_lane_tier()`/`apply_lane_tier()`. Construction resolves and pins one Git root. Refreshes
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

Every project save goes through `catalog.edit_catalog` preview/apply and keeps the
document shape it writes: a move names the complete moved Tier and leaves other Tiers
on their named or fallback Order. Keep the editor-opening snapshot (project bytes and
global signatures), fresh-global validation, unrelated keys, target checks before and
after preview, and project symlink refusal. `policy.meters` carries `value`, `display`,
`source` and `effect`; the view draws Gate, Margin and Pace as inactive when it is off.
A conflict reloads and requires a fresh action.
The final byte check is not a filesystem lock: a writer can race the rename.
Global routing and Meter observations remain read-only. A Lane's Tier is the one
exception, because a Tier belongs to the Lane and `catalog.edit_catalog` rejects
`lanes.<lane>.tier` at project scope: `preview_lane_tier()` previews it with
`scope='global'` and writes nothing, and only `apply_lane_tier()` writes, refusing a
catalog whose bytes or revision moved since the preview. The catalog renumbers the
Order of the destination Tier behind that one field, so the preview's `changed` list,
not the caller, says which Lanes move. `deck` is the only variant that calls it, and it
asks for `y` first.

For Herdr launch or placement changes, read `launcher.py`, `open.py`, and ticket 08.
From a managed project pane, run `make -C /path/to/this/checkout delegate-dashboard`.
`DELEGATE_DASHBOARD_PLACEMENT=tab` selects a tab; `open.py --help` lists placements
and disposable fixture overrides. Python 3.11+ is required. The opener preserves
the invoking pane's project and PATH even when Make runs in the plugin checkout.
For the accepted prototype verdict and prior live evidence, read ticket 09.
Ticket 10 holds the live check of the compatibility patch. `_work/` beside the tickets
(git-ignored) holds `make_live_fixture.py` and `verify_no_probes.py`.
