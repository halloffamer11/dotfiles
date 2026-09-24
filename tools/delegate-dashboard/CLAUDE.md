# Delegate dashboard

The project routing dashboard. It is one terminal view, `deck`, pinned to one Git
project: a tote board of the carried Lanes, their Tier, Order, Remaining and Pace, and
the project's Gate and Margin. It reads delegate's catalog and ranking boundary and
writes only project scope. `../delegate-mon/` is a separate program, the `delegate-mon`
Rust monitor, and shares no code with this directory.

`deck` is the production view. The history is `.scratch/delegate-dashboard-plugin/issues/`: ticket 11 holds the layout
verdicts and the key map, ticket 12 the lock-in.

## How to open it

- `delegate project` is the short way: it opens this view for the Git project of the
  current directory, in the current terminal, with no Herdr and no checkout path to
  type, and passes anything further to `dashboard.py`. Outside a Git project it says so
  and exits 1. The command is `stow/delegate/.local/bin/delegate`, which `make configs`
  links into `~/.local/bin` (ticket 34).
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
model, the selected Lane, the percentage editors and the one open question, and it
handles `j`/`k` and the up and down arrows, `J`/`K` and the Shift arrows, `g`, `m`, `w`,
`u`, `U`, `r` and `q`. Every other key goes to `deck.handle_key`. The view exposes
`NAME`, `render(state, *, width, height, selected_lane, editor, message, view)`
returning exactly `height` painted strings, `handle_key(key, state, view, model=None)`
and `selectable(state, view)`.

The host is itself two halves. `Session` owns what a key does — the model, the
selection, the editor, the question — and `Session.key(key)` returns `'quit'` when the
pane should close; `run_terminal` owns the screen and the keyboard and nothing else.
Keep the terminal out of `Session`: that split is what lets the key map be driven from a
test the way a person drives it, `q` and its answer included.

- `selectable` names the carried Lanes `j`/`k` may stop on, so a folded row is never
  walked. A Lane name returned from `handle_key` moves the selection to that Lane.
- `handle_key` takes a `model` keyword, which is how `H`/`L` reach a staging path.
- A question is one `Confirm` in `view['prompt']`, which the view draws in its footer;
  an unlisted key leaves it open and Escape always means stay.
- Left, right and Shift+Tab are in `KEY_SEQUENCES`, so the view reads each as one key
  instead of as `ESC`, `[` and a letter.
- A render that raises is caught and painted as one line, so a fault never closes the
  pane.

## Keys

- `j`/`k` or the arrows select; `J`/`K` or the Shift arrows move the Lane inside its
  Tier's Order.
- `H`/`L` move the Lane one Tier left or right for this project only. Tier 1 has
  nothing to its left and Tier 4 nothing to its right.
- `g`/`m` open Gate or Margin percentage entry; Enter stages and Escape cancels. A
  percentage edit keeps its opening policy snapshot across hot reloads.
- Every one of those four stages a change and writes nothing. `w` saves all of them,
  `u` drops the last, and `U` drops all of them after one confirm key. `r` and `q`
  ask first when changes are unsaved, and the `q` prompt offers save, drop or stay.
  The header counts what is unsaved and a mark, not colour alone, names each Lane
  and value in the count.
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
staged editing through `stage_move_lane()`, `stage_move_lane_tier()`,
`stage_percentage_edit()`, `undo_staged()`, `discard_staged()` and `save_staged()`.
`move_lane()`, `move_lane_tier()` and `save_project_policy()` are the immediate writers
underneath; no key reaches them any more, and they stay as the reference a staged save
is compared against byte for byte. Construction resolves and pins one Git root.
Refreshes read the effective catalog and call delegate's canonical `tier_leaders()`;
they use cached observations and never acquire Meter data or run a vendor probe.

The public state contains `project`, sourced `policy`, read-only `usage`, four `tiers`,
`project_tiers`, `staged`, `revision` and `error`. Rows remain in effective Order even though the
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

## Staged edits

A key changes a staged policy held in the model and writes nothing (ticket 13). Each
staged change carries the `catalog.edit_catalog` call it will make, and the staged
documents come from `catalog.plan_edits`, which plans that list of calls onto the
documents on disk and returns the planned documents and the effective catalog they
produce (ticket 14). It is the catalog's one planning path, the one `edit_catalog`
writes through, and the staged view is ranked from its catalog by `tier_leaders()`,
so it is the one ranking rule reading the documents the save will write. The
dashboard calls no private catalog name. `save_staged()` makes the same
calls in the same order, which is why a staged sequence and the same sequence of
immediate saves leave the same bytes.

Staging pins the two project files and both global files when the first change is made.
A save answers the conflict, then the symlink refusals for each document it would
write, then one replay of the whole list, before the first write; a change leaves the
staged list only once it is on disk, so a write that fails part way keeps itself and
everything after it staged. A conflict is reported once, reloads, and re-pins, so a
second `w` saves onto what is there now. Row `staged`, `policy.gate.staged`,
`policy.margin.staged` and the `staged` block (`count`, `changes`, `lanes`, `fields`,
`conflict`) are what the view marks and counts.

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

Run `python3 test_dashboard.py`. Tests stay at the public model boundary and at the
host's key boundary, `Session.key`; do not add terminal-spacing or color snapshots and
do not add drawing tests. The no-probe rule is a test there as well as in `_work/`:
staging, undo and save run with the process, socket and URL entry points trapped.
`_work/` beside the tickets (git-ignored) holds `make_live_fixture.py` and
`verify_no_probes.py`, which walk the same path over the live fixture.
