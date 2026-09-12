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

**Status:** ready-for-agent

Wizard:
- [ ] Tier 4 opens with no lane marked, whatever `lanes.json` holds
- [ ] A lane switched off on the carry page shows on no tier page, and space cannot mark it
- [ ] A lane assigned at tier N shows on no page below N
- [ ] After tier 1, a review page lists every carried lane with its tier; j/k moves, 1-4 sets the tier, enter goes to routing, and `b` from routing returns to it
- [ ] The routing page shows a description of the highlighted setting beside the table
- [ ] The start page shows the two output paths, the benchmark page path and the discovery notices, and no definition of a term; `--plain` prints the same facts; ticket 12's orientation tests and ticket 07b's snapshot tests pass against it
- [ ] Each page's layout is checked at 80x24 and at a wide terminal

Benchmark page:
- [ ] Each board has a description and a source URL taken from the source's methodology page, and `test_bench_page.py` checks that every board on the page has both
- [ ] Selecting a board in a plot's menu shows its description with that plot
- [ ] A comparison table of all boards sits below the plots
- [ ] The mouse wheel zooms each plot about the pointer; the reset button is always visible and restores the full view

Both:
- [ ] `test_setup_tui.py` covers wizard items 1-5 on fixtures, and the whole suite passes
- [ ] Orin runs the wizard once more, zooms a plot with a real mouse, and confirms

## Consolidated, 2026-09-12

Orin asked for fewer, larger tickets. The draft ticket 26 (never committed) (benchmark page
descriptions and zoom) and ticket 20's start-page half folded in here: all of it is
what the wizard and its page show, and it goes to the same agent.
