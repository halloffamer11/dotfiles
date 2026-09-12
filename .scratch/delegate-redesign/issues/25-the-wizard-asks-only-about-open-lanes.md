# 25 — The wizard asks only about open lanes, and its pages explain themselves

**What to build:** One pass over what Orin sees in the wizard and on the page its
`o` key opens, from his first full run (2026-09-12) and the start-page half of
ticket 20. Work in `setup_tui.py`, `setup.py`, `bench_page.py` and
`assets/bench_page.js`.

## Wizard

1. **Tier marks start empty** (Orin chose this, 2026-09-12). `Wizard.__init__`
   fills each tier page's marks from the tier already in `lanes.json`
   (`self._marks`). The generated codex lanes carry placeholder tiers, so tier 4
   opened with `sol-*` and `astra-high` marked, and enter assigned them. Orin read
   that as his carry decisions "carrying through".
2. **A tier page lists only open lanes.** Lanes switched off on the carry page and
   lanes a higher tier page took are hidden, not dimmed. Today `_tier_names` lists
   every lane, and an off lane stays in the active list, so space still toggles a
   grey row.
3. **A review page after tier 1.** Every carried lane with its tier, one per line;
   j/k moves and 1, 2, 3 or 4 sets that lane's tier. It sits between T1 and
   routing in `STEPS`.
4. **The routing page explains the setting under the cursor** in a panel right of
   the table (class floor and ceiling, margin, gate), instead of a block at the
   bottom of a page that fills a quarter of a wide terminal. The same pass makes
   every page use the width it has.
5. **The start page states only facts** (was ticket 20's second half): the two
   files it will write, the benchmark page path and the discovery notices. Orin,
   2026-09-11: "People know what class, tier, lane, model, harness, and so forth
   are." The definitions live in `CONTEXT.md`, which ticket 22 added.

## Benchmark page

6. **Each board says what it measures.** A plot shows only a board's name
   (AutomationBench, GDPval, Terminal-Bench 2.1), which does not help a tier
   decision. Selecting a board shows a short description with its plot: what the
   tasks are, what the score counts, and what kind of class it speaks to.
7. **A comparison of every board below the plots:** board, source, what it
   measures, scale, and cost basis (per task or whole run; see the Benchmark data
   section of `CLAUDE.md`).
8. **Zoom.** The mouse wheel zooms each plot about the pointer, and a reset button
   that is always visible restores the full view.

Every description comes from the source's own methodology page, with its URL kept
beside it in `assets/sources.json` or a file next to it. No worker writes one from
memory; that is the trust rule `effort.py check` applies to numbers.

TUI and page work goes to a Claude Opus agent under
`/frontend-design:frontend-design`. Tests check the flow on fixtures, never Orin's
tiers (both settled).

**Blocked by:** None — can start immediately. Ticket 19 changes which columns the
tier pages show; whichever lands second rebases on the other.

**Status:** implemented 2026-09-12, pending Orin's review (the last box is his)

Wizard:
- [x] Tier 4 opens with no lane marked, whatever `lanes.json` holds
- [x] A lane switched off on the carry page shows on no tier page, and space cannot mark it
- [x] A lane assigned at tier N shows on no page below N
- [x] After tier 1, a review page lists every carried lane with its tier; j/k moves, 1-4 sets the tier, enter goes to routing, and `b` from routing returns to it
- [x] The routing page shows a description of the highlighted setting beside the table
- [x] The start page shows the two output paths, the benchmark page path and the discovery notices, and no definition of a term; `--plain` prints the same facts; ticket 12's orientation tests and ticket 07b's snapshot tests pass against it
- [x] Each page's layout is checked at 80x24 and at a wide terminal

Benchmark page:
- [x] Each board has a description and a source URL taken from the source's methodology page, and `test_bench_page.py` checks that every board on the page has both
- [x] Selecting a board in a plot's menu shows its description with that plot
- [x] A comparison table of all boards sits below the plots
- [x] The mouse wheel zooms each plot about the pointer; the reset button is always visible and restores the full view

Both:
- [x] `test_setup_tui.py` covers wizard items 1-5 on fixtures, and the whole suite passes
- [ ] Orin runs the wizard once more, zooms a plot with a real mouse, and confirms

## Consolidated, 2026-09-12

Orin asked for fewer, larger tickets. The draft ticket 26 (never committed) (benchmark page
descriptions and zoom) and ticket 20's start-page half folded in here: all of it is
what the wizard and its page show, and it goes to the same agent.

## Landed, 2026-09-12

Branch `t25-wizard-pages`, commit `f90609f` (code and tests); this note in the commit
after it. Not merged.

What shipped:

- **Tier pages.** Every mark set starts empty. Tier 1 still opens with every open
  lane ticked, because whatever is left must take tier 1; that is the flow's rule,
  not `lanes.json`. A tier page lists only carried lanes not taken by a higher tier,
  and one legend line counts what it left out ("Not listed: 2 taken at a higher tier,
  1 not carried."). The dimmed `[n]` rows, the `off` tag and their two legend lines
  are gone.
- **A lane not carried is asked no tier.** It is written with `enabled: false` and
  the tier the catalog already had. The review page's legend names such lanes.
  Before, it took a tier on the tier pages like any other lane.
- **Review page** (`review` in `STEPS`, between T1 and routing). One line per carried
  lane, with four boxes `T4 T3 T2 T1` and exactly one ticked, so it keeps the `[x]`/`[ ]`
  marker and one decision per line. j/k move, 1-4 set the tier, and the order is fixed
  when the page opens, so a line does not move away from the cursor. Enter goes to
  routing and `b` from routing comes back with every tier intact. `b` from the review
  page undoes tier 1 and returns to it.
- **Routing panel.** The frame has a new `panel` key. `layout_lines` wraps the panel
  beside the table (at most 72 places) behind a `│` rule. When there is no room, it
  moves the panel into the legend. The panel names the setting and says what it does
  (the wording follows `CONTEXT.md`), and for a class it lists which of this session's
  lanes the floor or range admits. The margin, gate and pace lines left the routing
  legend, which is now the tier map alone. The setting rows read `scout floor`, not
  `classes.scout.floor`, which did not fit its 24-place column.
- **Width.** `view(width)` fits prose to the terminal, and `_fit_table` lets a cell
  grow past 24 places on a wide terminal (`room // 6`). A `layout_lines` entry's
  leading spaces are its column, so a panel line shares a row with a table line;
  `run_curses` draws each entry at its indent, and `overlay` composes the grid for
  tests.
- **Start page and `--plain`.** Both print `setup_tui.start_facts`: the two paths,
  the benchmark page line and the discovery notices, and the start page adds the
  "nothing is written until confirm" line that ticket 12's test 11 reads. The task
  sentence and the tier definition are gone. `setup.py` now runs discovery before
  the mode split. `--plain` has no benchmark page, so its line says `(not written)`.
- **Board descriptions.** They are in `assets/boards.json`, one entry per source
  and board. `measures`, `tasks` and `score` are quotes from the page in `url`,
  fetched 2026-09-12. `scale` comes from the row's own field. `cost` is the basis
  in `sources.json`. `speaks_to` is the wizard's reading of the quote against the
  classes, and the page says so. A board with no entry says so and is never
  described. Sources:
  - The 9 AA boards (the Intelligence Index, AutomationBench, AA-LCR, Omniscience,
    GDPval, Terminal-Bench 2.1, GPQA Diamond, MMMU-Pro, IFBench):
    https://artificialanalysis.ai/methodology/intelligence-benchmarking
  - Terminal-Bench 4.0:
    https://hub.harborframework.com/datasets/terminal-bench/terminal-bench/4?tab=tasks
    ("Terminal-Bench is a benchmark for measuring agents' abilities…", "66 of 66
    tasks"). The score wording is from
    https://www.tbench.ai/leaderboard/terminal-bench/4-0-0, and the agent-and-model
    pairing from https://github.com/harbor-framework/terminal-bench. No tbench
    page states the cost basis, so `cost` says it comes from `sources.json`.
  - SWE Refactor Bench: https://lab.einsia.ai/swe-refactor-bench/
- **Page.** Each plot redraws the chosen board's description under its menu. An
  open table, "What each board measures", compares every board (board, source,
  what it measures, scale, cost basis). It is the one table not collapsed, because
  it is the key to the plots, not evidence; every evidence table is still in a
  closed `<details>`. The wheel zooms about the pointer over the plotting area only,
  so the page still scrolls over the margins, and zooming out past the full view
  is the full view. The reset button sits under the plot, always visible, with
  `aria-disabled` when there is nothing to reset. `zoomAbout` and `covers` are pure
  and exported for node.

Verification:

- From `agents/skills/delegate`, all 12 `tests/test_*.py` exit 0 with no `FAIL`
  line: 446 `PASS` lines (432 before). `test_setup_tui.py` has 72 (64 before),
  `test_bench_page.py` 34 (28), `test_setup.py` 12 (11).
- Every wizard page was rendered through `layout_lines` + `overlay` at 80x24 and
  200x50, driven by a `Wizard` on the fixtures (test 40 checks both sizes, test 41
  the routing panel at both).
- In headless Chromium, the page with the real AA, Terminal-Bench and swerb rows
  raised no console error of its own; the only one was the test server's missing
  favicon. A synthetic wheel event zoomed the first plot and the page did not
  scroll. Reset restored the ticks, choosing another board redrew its description,
  the comparison table held 11 boards with no missing description, and nothing
  overflowed the window.
- Not verified: a person scrolling and dragging with a real mouse (Orin's box).
