# 01 — Wizard rescan and layout fixes after the text redesign

**What to build:** Fix the defects a review found in the setup wizard's text and
colour redesign (`fc6d9ed`, `3d0ec8c`): the `r: rescan` key on the harnesses page,
the harnesses page layout, and the tests that should have caught them.

**Blocked by:** None.

**Category:** bug

**Status:** open. Review 2026-09-23 on `opus55-medium@claude` (verdict findings);
findings 1, 2 and 4 confirmed by reading the code.

## Decisions

- `r` is refused once any carry or Tier choice exists. The message says to quit
  and start again to rescan. A rescan never discards a choice (Orin, 2026-09-24,
  option a). A choice is a change against the state the last load built, so
  going back and forth with no change keeps `r`.

## Acceptance

- [ ] The save writes and removes native agent files from the plan the wizard
  holds after a rescan, not the launch plan (`setup.py` `save_native_agents`)
- [ ] `r` does nothing but show the refusal message once a carry or Tier choice
  exists; with no choice it rescans as before; the docstring claim matches
- [ ] A forced fetch that fails falls back to the rows launch used, not to the
  repo rows, and the note says so
- [ ] The harnesses page counts its body lines in the table's room: at 80x16
  every harness row shows (the legend gives way first)
- [ ] An exception in the rescan's state rebuild becomes a message and leaves
  the wizard as it was before `r`
- [ ] The `_palette` docstring is true in monochrome (or the monochrome table
  tells `why-data` apart from a plain cell)
- [ ] First run with no `lanes.json`: a code comment states that a rescan does
  not re-propose the sample Lanes of a harness found only by the rescan
- [ ] Tests: rescan after a choice is refused; the save after a rescan uses the
  new plan; rescan rebuilds the row-derived state (`_proposals`, `_reasons`,
  `_unmatched`) from new rows; a failed forced fetch keeps the launch rows; the
  harnesses page at 80x16; the pty smoke fails if `r` does not rescan
- [ ] Full suite green
