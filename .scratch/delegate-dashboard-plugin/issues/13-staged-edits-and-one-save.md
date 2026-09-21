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

**Status:** implemented 2026-09-20 (`b2d0c0d`) on `worktree/delegate-dashboard-plugin`. The last box is Orin's: drive staging, undo and save once in a Herdr pane.

- [x] With staged changes and no save, the bytes of every file under `.delegate/` and of
      the global catalog are unchanged (test at the public model boundary).
- [x] The staged view ranks from the staged policy: a staged Order move changes the shown
      Pick when it should, with no file written.
- [x] `w` writes what the same sequence of immediate saves wrote before, byte for byte,
      for an Order move, a Tier move, a Gate edit and a Margin edit.
- [x] `u`, `U` and the `q` prompt behave as written above.
- [x] A changed project file or global catalog between staging and `w` refuses the save
      and keeps the staged changes.
- [x] `verify_no_probes`-style check: staging, undo and save start no process, socket or
      URL call.
- [x] `python3 tools/delegate-dashboard/test_dashboard.py` passes; the context file and the
      `?` help list the new keys.
- [ ] Orin drives staging, undo and save once in a Herdr pane.

## Landed, 2026-09-20

`b2d0c0d`. Named dispatch to `opus-high@claude` (TUI work goes to a Claude Opus agent), run
`20260921T011459Z-opus-high@claude-8f070bec`, verdict clean after review. Independent
review on another Model family: `flash-high@agy`, run
`20260921T013314Z-flash-high@agy-c4b95f7a`, 394 s, verdict findings. The ranked `review`
pick was `opus-high@claude` by a Margin steal; the session dropped it as the implementer's
family.

Review: five risk areas clean (no write or lost staging without a key; no global write or
symlink follow; a several-document save replays before the first write and reports `Saved X
of Y`; a changed project file or global catalog refuses the save and keeps the staging; the
staged view and the saved files rank the same). Three test gaps, all fixed by the
implementer: the quit prompt is tested through the real key step, now `dashboard.Session`
(`run_terminal` keeps only the screen and the keyboard); a no-probe test traps process,
socket and URL calls across stage, undo and save; the staged-ranking test asserts the Pick
reason. The fourth finding, private `catalog._` helpers read by tuple position, is ticket 14.

Decisions the ticket did not settle, all the worker's, all open to Orin: the old immediate
writers stay in the model with no key bound, as the byte-for-byte reference; on a conflict
the first `w` reports and reloads and keeps the staging, and a second `w` saves onto the
new state; two edits of one field are two changes, so `u` steps back one edit; `r` asks
before it drops staging, and the file watch replays the staging onto new bytes; Ctrl-C quits
without the prompt; the unsaved mark is `•` in a new one-cell column, paid for by the
Remaining bar (24 to 22 cells). Fixed on the way: the watch signature had four items
against five, so the pane reloaded the catalog twice a second.

Note for the drive: the pane opens on the first carried Lane, which may be alone in its
Tier, and `J` there stages nothing.

Checked by the session: `test_dashboard.py` runs 66 tests, `OK` (44 before); `--json` exits
0; every suite under `agents/skills/delegate/tests/` exits 0; nothing under
`agents/skills/delegate/` changed.
