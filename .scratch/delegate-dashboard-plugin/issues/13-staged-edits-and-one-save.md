# 13 — Staged edits and one save

**What to build:** Orin asked for "a way to save the configuration" and chose staged
edits, 2026-09-20. Today each `J`/`K`, `H`/`L`, Gate and Margin action writes the project
file at once. A control surface where Orin tries different Orders must not write a file on
each key press.

**Blocked by:** 12 `deck` is the production dashboard

## Behaviour

- `J`/`K` (Order inside a Tier), `H`/`L` (a Lane's Tier for this project) and the Gate and
  Margin editors change a staged project policy held in `DashboardModel`. Nothing is
  written.
- The screen draws the staged state: Tiers, Order, Picks and Tier leaders are ranked from
  the staged policy with cached Meter observations, never a vendor probe. A changed Lane
  or value carries a mark that is not colour alone, and the header shows the count of
  unsaved changes.
- `w` saves all staged changes. `u` drops the last staged change. `U` drops all of them
  after one confirm key. `q` with unsaved changes asks: save, drop, or stay.
- A save goes through `catalog.edit_catalog` at project scope, as today: preview, then
  apply with the expected revision. It writes `<project>/.delegate/routing.json` and
  `<project>/.delegate/lanes.json` only. It never writes the global catalog. Unrelated
  keys, the project symlink refusal and the no-op rule stay.
- Conflict: staging records the project bytes and the global signatures when the first
  change is staged. If either changed on disk before the save, the save is refused, the
  screen says which file changed, and the staged changes stay so Orin can reload (`r`
  asks before it drops staged changes) or save again after a look.
- A save that would write several documents either writes all or none that it can
  detect: preview every document first, apply only when every preview passes.

## Acceptance

**Status:** ready-for-agent

- [ ] With staged changes and no save, the bytes of every file under `.delegate/` and of
      the global catalog are unchanged (test at the public model boundary).
- [ ] The staged view ranks from the staged policy: a staged Order move changes the shown
      Pick when it should, with no file written.
- [ ] `w` writes what the same sequence of immediate saves wrote before, byte for byte,
      for an Order move, a Tier move, a Gate edit and a Margin edit.
- [ ] `u`, `U` and the `q` prompt behave as written above.
- [ ] A changed project file or global catalog between staging and `w` refuses the save
      and keeps the staged changes.
- [ ] `verify_no_probes`-style check: staging, undo and save start no process, socket or
      URL call.
- [ ] `python3 tools/delegate-dashboard/test_dashboard.py` passes; the context file and the
      `?` help list the new keys.
- [ ] Orin drives staging, undo and save once in a Herdr pane.
