# 23 — The benchmark page is a few plots with settings, not a wall of charts

Numbered 23 because `main` landed its own ticket 22 (class range and native Claude
lanes) earlier the same day. This ticket's commit, `221283c`, still says 22.

**What to build:** The page the wizard's `o` key opens drew one static chart per
board (ten on the AA rows alone) and labelled nearly every point, so the labels
printed over each other, and the AA-LCR board pressed its scores into one thin
line on a 0-2 axis. Orin (2026-09-11, from two screenshots): make a couple of
plots, each with settings to turn models, harnesses and efforts on and off; keep
the tables but collapse them; and show the frontier at each cost, so the tiers
can suggest a model, effort and harness for each lane. The frontier is advice, not
a default, because the best score for the money is not the whole decision.

**Blocked by:** None.

**Status:** landed 2026-09-11 on `bench-aa-effort-slugs`. Orin read the page and
approved it ("much better").

- [x] Each plot shows one board, chosen from a menu grouped by source. The page opens on two plots: the board a decision is made on, and the best board from another source (or the next board of the same source). "Add a plot" adds more, and each plot can be removed.
- [x] Each plot has its own settings: the frontier of your lanes, of every point shown, or none; colour by kind of point, harness or tier; labels on the frontier, the frontier and your lanes, every point, or nothing; harness and effort chips; a model list with a name filter and All / Your catalog / None; drag to zoom. "Use these settings on every plot" copies them.
- [x] The frontier is every point that scores more than everything cheaper among the points shown. It is an amber step with the beaten region shaded under it, and a table under the plot lists it with lane, tier, and what each step buys.
- [x] A label that does not fit is dropped, never printed over another; the score axis fits the points shown, not zero.
- [x] Every table is in a closed `<details>` under the plots.
- [x] `setup.py --effort-rows` may be repeated, so AA and Terminal-Bench share one page.

## Built

Decisions:

- **The page has one inline script now.** It had none. Filtering needs one.
  `assets/bench_page.js` is inlined beside its data, which is inline JSON; there is
  still no remote resource, and the page still opens offline from a file:// URL.
  Every decision in the data (the kind of each point, what the pre-screen proposes
  off, which effort beats which, the sentence under each board) is still made in
  Python from `setup_tui` and `bench`. The script only filters, finds the frontier
  of what is shown, and lays it out. Text from a benchmark page goes in with
  `textContent` only, and the JSON is escaped so a model name cannot end its
  script element.
- **The frontier is a display aid, not a rule.** It is not the pre-screen's
  domination rule (same model, one source, a majority of benchmarks), and nothing
  reads it. It opens on "your lanes", because that is the frontier a lane mapping
  can use; "every point shown" shows what the catalog does not carry.
- **One cost axis per plot, as before.** A plot shows one source's benchmark, so no
  plot puts two sources' dollars on one axis.
- **The composite AA index opens first** among boards that tie on lanes: Orin found
  it the most readable board. It is labelled "(composite)" and the legend says the
  pre-screen never counts it.

Verification: `tests/test_bench_page.py` now tests the JSON the plots draw, the
collapsed tables, and the escaping. The frontier and the label layout run under
node when node is on PATH, and pass with a "skipped" note when it is not. 28 PASS
lines there (24 before), 1 new in `tests/test_setup.py`; suite 394 PASS lines
across 12 files, 0 failures. In headless Chrome with the real AA and Terminal-Bench
rows, the page loaded with no console error. A script drove the board menu, a zoom,
the filters, the tier colouring, "Add a plot" and "Use these settings on every
plot", with no error. In dark mode nothing overflowed at 1440 px; in light mode
nothing was wider than the viewport at 500 or 600 px (Chrome's narrowest window).
Not verified: a person hovering and dragging in a real browser.
