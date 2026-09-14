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

**Status:** implemented as `b2f7122`, integrated as `a3fc419`; live checks recorded in ticket 09

- [x] The command opens on a given directory, pins that project, and shows its identity.
- [x] Four Tier sections show only globally carried lanes with the listed fields, reasons and a color-plus-marker Tier leader.
- [x] Remaining, Pace and reset times are display-only.
- [x] Changing the project routing fixture or the Meter fixture produces a new leader and reason in the dashboard model without a restart (tested as model state, not terminal output).
- [x] The dashboard never dispatches and never forces a vendor re-probe.
- [x] No snapshot tests of colors, borders or spacing.

## Implemented, 2026-09-14

`tools/delegate-dashboard/dashboard.py` is the stdlib terminal entrypoint and
`model.py` is its public, JSON-safe state boundary. The model resolves one Git root
at construction, reads the effective catalog, calls `rank.tier_leaders`, restores
effective Order for display, and watches the pinned project policy and cached Meter
file by content bytes. Missing or malformed Meter data is shown as unknown rather
than synthesized. `test_dashboard.py` covers fixed identity, carried filtering,
four Tier previews, both hot-reload inputs, malformed caches, and the JSON command.

Verified in the ticket worktree (no commit):

- `python3 tools/delegate-dashboard/test_dashboard.py`
- `python3 agents/skills/delegate/tests/test_rank.py`
- `python3 -m py_compile tools/delegate-dashboard/dashboard.py tools/delegate-dashboard/model.py tools/delegate-dashboard/test_dashboard.py`
- `python3 tools/delegate-dashboard/dashboard.py --help`
- `python3 tools/delegate-dashboard/dashboard.py --cwd . --config-dir stow/delegate/.config/delegate --meters /tmp/delegate-dashboard-missing-meter.json --json`

The plain terminal view was inspected at 80 columns. Live split/placement checks,
plugin installation, and the prototype verdict remain exclusively in ticket 09.
