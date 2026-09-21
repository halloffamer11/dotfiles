# Delegate dashboard

The project routing dashboard. It is one terminal view, `deck`, pinned to one Git
project: a tote board of the carried Lanes, their Tier, Order, Remaining and Pace, and
the project's Gate and Margin. It reads delegate's catalog and ranking boundary and
writes only project scope. `../delegate-mon/` is a separate program, the `delegate-mon`
Rust monitor, and shares no code with this directory.

Orin accepted `deck` on 2026-09-19 and locked it as the production view on 2026-09-20.
The history is `.scratch/delegate-dashboard-plugin/issues/`: ticket 11 holds the layout
verdicts and the key map, ticket 12 the lock-in.

## How to open it

- `dashboard.py --cwd DIRECTORY [--config-dir DIRECTORY] [--meters FILE]` opens the
  view. Add `--json` for one noninteractive diagnostic projection. There is no layout
  argument. Python 3.11+ is required.
- From a managed project pane, run `make -C /path/to/this/checkout delegate-dashboard`.
  It links the plugin and calls `open.py`. `DELEGATE_DASHBOARD_PLACEMENT=tab` selects a
  tab; `open.py --help` lists the placements and the fixture overrides. The opener keeps
  the invoking pane's project and PATH even when Make runs in the plugin checkout.
- `herdr-plugin.toml` is the Herdr plugin manifest and runs `launcher.py`, which resolves
  the project from Herdr's invocation context and execs `dashboard.py`. For launch or
  placement changes read `launcher.py`, `open.py` and ticket 08.

## The host and the view

`dashboard.py` is the host and `deck.py` is the view; the split stays. The host owns the
model, the selected Lane and the percentage editors, and it handles `j`/`k` and the up
and down arrows, `J`/`K` and the Shift arrows, `g`, `m`, `r` and `q`. Every other key
goes to `deck.handle_key`. The view exposes `NAME`, `render(state, *, width, height,
selected_lane, editor, message, view)` returning exactly `height` painted strings,
`handle_key(key, state, view, model=None)` and `selectable(state, view)`.

- `selectable` names the carried Lanes `j`/`k` may stop on, so a folded row is never
  walked. A Lane name returned from `handle_key` moves the selection to that Lane.
- `handle_key` takes a `model` keyword, which is how `H`/`L` reach a save path.
- Left, right and Shift+Tab are in `KEY_SEQUENCES`, so the view reads each as one key
  instead of as `ESC`, `[` and a letter.
- A render that raises is caught and painted as one line, so a fault never closes the
  pane.

## Keys

- `j`/`k` or the arrows select; `J`/`K` or the Shift arrows move the Lane inside its
  Tier's Order and save at once.
- `H`/`L` move the Lane one Tier left or right for this project only, and save at once.
  Tier 1 has nothing to its left and Tier 4 nothing to its right.
- `g`/`m` open Gate or Margin percentage entry; Enter saves and Escape cancels. A
  percentage edit keeps its opening policy snapshot across hot reloads.
- `Tab` and `Shift+Tab` cycle the three bodies: the Tier list, the Harness table
  (Harnesses down, Tiers across) and the Gate/Margin aid, which draws per Meter the
  Remaining against the Gate mark and the Pace against the Pick's Pace plus the Margin,
  the rule at `rank.py:177-183`. `a` reaches the aid and returns.
- In the list `h`/`l` close and open a deck. In the table `j`/`k` walk down one Tier
  column and `h`/`l` cross to the nearest Lane one column over.
- `d` writes the terms and every reason code at the foot, `z` folds the deck or the
  Harness row under the cursor, `?` lists the keys, `r` reloads, `q` closes the pane.

## The model boundary

`model.py` exposes `DashboardModel.state`, `refresh()` and `refresh_if_changed()`, plus
project-policy editing through `move_lane()`, `move_lane_tier()` and
`save_project_policy()`. Construction resolves and pins one Git root. Refreshes read the
effective catalog and call delegate's canonical `tier_leaders()`; they use cached
observations and never acquire Meter data or run a vendor probe.

The public state contains `project`, sourced `policy`, read-only `usage`, four `tiers`,
`project_tiers`, `revision` and `error`. Rows remain in effective Order even though the
canonical ranking result puts its Pick first. Each row's `order_source` comes from the
effective catalog: `p` marks project Order and `g` marks global Order or fallback. A
fallback position can be derived, not literally stored. `project_tiers` is
`catalog.project_tier_changes()`, `{lane: {from, to}}`, and each row's `tier_source` is
`project` or `global` from it. A project Tier drops the Lane's global Order, so such a
row shows `—` in Ord and sorts after the placed Lanes in its new Tier.

Project policy, project Lanes, global catalog and Meter cache watches compare file
bytes. An invalid policy reload retains the last valid view with an error; missing or
malformed Meter data becomes explicit unknown observations through
`rank.meter_observations()`. The dashboard does not maintain a separate validity rule.

## The save rules

Every project save goes through `catalog.edit_catalog` preview/apply and keeps the
document shape it writes: a move names the complete moved Tier and leaves other Tiers on
their named or fallback Order. Keep the editor-opening snapshot (project bytes and
global signatures), fresh-global validation, unrelated keys, target checks before and
after preview, and project symlink refusal. `policy.meters` carries `value`, `display`,
`source` and `effect`; the view draws Gate, Margin and Pace as inactive when it is off.
A conflict reloads and requires a fresh action. The final byte check is not a filesystem
lock: a writer can race the rename.

The global catalog and Meter observations stay read-only: every dashboard write is
`scope='project'`. `move_lane_tier()` is the Tier write, through ticket 32's project
Lanes document `<git-root>/.delegate/lanes.json` and its `set lanes.<lane>.tier N` at
project scope, on the same preview/`expect`/apply contract; it checks the target against
`project_lanes_path`, and `_unsafe_lanes_target()` gives that file the three refusals the
project policy already has. Setting a Lane back to its global Tier removes the entry,
which the catalog does, not this method. An installation without the backend raises `is
global-only` at the preview and the method reports `Tier move needs the project Lanes
backend (ticket 32)` without writing; do not reach for `scope='global'` to get around
that. `deck`'s `H`/`L` is the only caller and answers the Tier 1 and Tier 4 edges before
the catalog is asked.

A project Lanes path that resolves onto a global document is refused at construction,
not at each save, because `load_catalog` reads that file as a lane customization and
rejects a global catalog for carrying a version: there is no view to open. A project
routing path that resolves onto a global document still opens and is refused at each
save, which is where that rule has always lived.

## Tests

Run `python3 test_dashboard.py`. Tests stay at the public model boundary; do not add
terminal-spacing or color snapshots and do not add drawing tests. `_work/` beside the
tickets (git-ignored) holds `make_live_fixture.py` and `verify_no_probes.py`.
