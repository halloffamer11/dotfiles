# 27 — The page is the first input

**Status:** ready-for-agent

**What to build:** From Orin's use of the ticket 26 page (2026-09-12): "The HTML has
now surpassed the TUI." The page becomes where carry and tier decisions are made,
and the wizard takes them in one paste. The wizard stays the place files are
written; retiring its carry and tier pages is later work. Work in `bench_page.py`,
`assets/bench_page.js`, `setup_tui.py`, `setup.py` and their tests.

## Page to wizard

1. **Off is a choice on the page.** Each lane line in the tier panel offers `off`
   beside `4 3 2 1`; `none` stays "not placed". An off lane is listed under its own
   heading and counted there.
2. **Copy as lines** writes one line per decided lane, `<lane> <1-4|off>`, in the
   review page's order. Lanes not placed are not written.
3. **The wizard takes the lines.** On the review page, `v` reads the macOS
   clipboard (`pbpaste`) and applies each line: a tier line carries the lane and
   sets its tier, an `off` line sets it not carried. A lane with no line keeps what
   it has. The wizard then states, on one line, how many lanes took a tier, how
   many went off, how many were not named, and names any lane it does not know,
   which it ignores. `setup.py --tiers-from <file>` applies the same lines at
   start, for a terminal without a clipboard, and one parser serves both.

## Page

4. **Sensitivity across boards.** A table under the tier panel's plots: one row per
   placed lane, grouped as the panel groups; one column per board the page plots.
   A cell is the tier that board alone would give the lane if each tier held the
   share of lanes Orin gave it: rank the placed lanes that board measured by
   score, and cut them in the proportions of Orin's tier counts. A cell that
   differs from the lane's tier is marked. The last column is how many boards
   agree out of how many measured the lane. The composite index is shown and
   never counted in that column (ticket 18). It updates as tiers change.
5. **Beaten by another model, shown.** On the board shown, a lane that another
   carried lane of any model beats on score for no more cost per task says
   "beaten by <lane>" in its tooltip and on its panel line. It is a display aid
   like the frontier: the carry rule is unchanged and still compares only efforts
   of one model (ticket 18). Costs are compared only inside one board, since
   sources measure cost differently (root `CLAUDE.md`, Benchmark data).
6. **Colour is the meter, not the harness.** Load balance is across quotas, and
   Fable has its own (`claude-fable`). Same shapes; `claude-fable` is a distinct
   shade of the claude colour. The panel's counts are per meter.

## Decisions already made

- Tests check behaviour on fixtures, never Orin's tiers.
- Nothing on the page writes `lanes.json`; the wizard writes it.
- The frontier and item 5 are display aids; the carry rule is the only thing that
  proposes a lane off.
- How the ranker orders lanes inside a tier is not changed here; Orin decides that
  separately (question raised 2026-09-12).

## Boxes

- [ ] 1 off on the page
- [ ] 2 copy writes tiers and off
- [ ] 3 review page `v` and `--tiers-from`, one parser, one summary line
- [ ] 4 sensitivity table
- [ ] 5 beaten by another model, shown
- [ ] 6 colour by meter, Fable its own shade
- [ ] Orin pastes his page decisions into the wizard
