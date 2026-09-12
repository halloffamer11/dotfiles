# 26 — The benchmark page is where tiers are drawn

**Status:** implemented 2026-09-12, pending Orin's review (the last box is his)

**What to build:** From Orin's second wizard run (2026-09-12). While he assigned
tiers he kept the page's AA plot open: he read the frontier, dragged to a cost per
task, and compared a model's efforts inside each harness. The page becomes the
tool he draws tiers on; the wizard's tier and review pages stay the place tiers are
written. Nothing carries the page's tiers into the wizard yet: Orin reads them off
the page and sets them on the review page, and merging the two is later work. Work
in `bench_page.py`, `assets/bench_page.js`, `setup_tui.py` and their tests.

## Every list

1. **Lanes are grouped by model, and a group lists its efforts from most to
   least** (max, xhigh, high, medium, low), on every wizard page (carry, the four
   tier pages, review) and in every table on the page. Groups keep the order the
   page already has, taken at the group's first lane: the benchmark order on the
   tier pages, the tier on the review page. An agy model is one group across its
   slug family (`gemini-3.8-flash-high` and `-low` are one model). Today T4 shows
   `fable-medium` third and `fable-high` sixth.

## Benchmark page

2. **Pan.** When a plot is zoomed, a drag with the left button pans it, and so
   does a drag with the middle button. A press that does not move stays a click.
3. **Tier lines.** Orin adds the thresholds between tiers 1|2, 2|3 and 3|4 as
   vertical lines on the cost-per-task axis and drags each one. A line is a guide,
   not a rule: it proposes a tier for the dots in its band, and nothing stops a
   lane from taking another tier.
4. **Tiers are set per lane, on the page.** Selecting a dot (a model at an effort)
   sets its tier with 1-4 or a picker. A lane below the tier 3 line can be tier 3,
   because Orin knows things the estimate does not.
5. **Colour is the harness**, so load balance shows at a glance.
6. **Side by side.** Beside the plot, a panel lists tiers 4 to 1 with each
   harness's lanes in that tier, grouped as in item 1, and a count per tier per
   harness. It states counts; it does not judge them. A carried lane with no rows
   (today `haiku-high@claude`) cannot be a dot, so it is listed in the panel under
   "no rows" and can still take a tier there.
7. **Focus a tier.** A control per tier zooms the plot to that tier's band and
   dims the dots outside it.
8. **The tier view.** After the tiers are set, a button redraws the plot with a
   marker per tier (shape or ring) over the harness colour, to see the scatter of
   tiers across models and harnesses.
9. The page's tiers survive a reload (`localStorage`, keyed by the catalog), and a
   button copies them as plain lines, `lane tier`, in the review page's order.

## Decisions already made

- One decision per line in the wizard; the carry rule is the only thing that
  proposes a lane off; the frontier is a display aid (tickets 18, 24).
- Board descriptions stay as quoted in `assets/boards.json` (ticket 25).
- Tests check the rule on fixtures, never Orin's tiers.
- Haiku gets no AA row mapping: Orin judges it decidedly worse than luna for now
  (2026-09-12), so `haiku-high@claude` stays a lane with no rows.

## Round 2

From Orin's look at round 1 (2026-09-12). Item 3 above was his mistake, in his
words: the tier lines should be horizontal, "showing where things cut off".

10. **Tier lines are horizontal**, on the score axis, and replace the vertical
    cost lines. Sliding a line tiers at once: every carried lane whose dot is
    above that line and below the next line up takes that band's tier in the
    side panel. Orin then adjusts from there. A tier set by hand, on a dot or in
    the panel, stays set until he clears it; a line drag does not overwrite it.
11. **The panel and the plot highlight each other, for every lane.** Hovering or
    selecting a lane in the side panel (for example `opus-xhigh@claude`)
    highlights its dot with its label, including lanes whose dot has no label
    today; selecting a dot highlights its panel row.
12. **The plot fills its column's height** (round 1 left empty space under it).
13. **Group order without Epoch.** On the wizard's tier pages a model group with
    no Epoch figure is ordered by its best AA mean rank, not placed last.

## Boxes

- [x] 1 grouping on every wizard page and page table
- [x] 2 pan
- [x] 3 draggable tier lines
- [x] 4 per-lane tier on the page
- [x] 5 harness colours
- [x] 6 side-by-side tier panel with counts and the no-rows list
- [x] 7 focus a tier
- [x] 8 tier view
- [x] 9 reload survives, copy as lines
- [ ] 10 horizontal tier lines; a drag tiers its band; hand-set tiers survive
- [ ] 11 panel and plot highlight each other for every lane
- [ ] 12 plot fills its column
- [ ] 13 group order without Epoch uses AA mean rank
- [ ] Orin draws his tiers on the page and sets them in the wizard

## Landed, 2026-09-12

Branch `t26-page-tiers`, commit `05d0bb2` (code, tests, the skill's CLAUDE.md
paragraph on the page); this note in the commit after it. Not merged.

What shipped:

- **Grouping (1).** `setup_tui.group_lanes(names, lanes_doc)` regroups any order:
  a group sits where its first lane sat and lists its efforts most to least
  (`effort_rank`: ultra, max, xhigh, high, medium, low). `model_group` strips the
  effort suffix off a normalised slug, so `gemini-3.8-flash-high` and `-low` are
  one group. The carry page groups the catalog's order, the tier pages the
  benchmark order (`bench_order_key`, `lane_order`, now module functions the page
  reads too), and the review page the `(-tier, benchmark)` order, so a model's
  group sits where its best-tiered lane sits. On the page, every table lists a
  model's efforts most to least: the sweep table's step column is now what an
  effort buys over the one *below* it, so the figures are unchanged and only the
  row order flips; the rows table, the catalog table and the figures inside a
  scores cell follow. On the real catalog T4 now opens `fable-max, fable-xhigh,
  fable-high, fable-medium, fable-low, sol-max, ...` (the render is in the return).
- **Pan (2).** Once zoomed, a left drag pans; the middle button pans either way.
  `panBy` is pure: the content follows the pointer, in log space on the cost
  axis. A press that moves under 4 px stays a click. The pan accumulates from the
  pending domain, so two moves between frames do not undo each other.
- **Tier lines (3).** Three lines per *source*, since a source's dollar is the
  axis: a checkbox in each plot's rail draws them for that source at the log
  quartiles of the lane costs shown (`defaultLines`, rounded to two figures), and
  a drag on the line moves it on every plot of the source, clamped so lines never
  cross. The band names `tier 1`..`tier 4` sit at the top of the plot. The
  tooltip and the picker say what the band proposes (`bandTier`); one button per
  plot, "Give every lane on this plot its band's tier", applies it to the lanes
  drawn there, and any lane can be moved afterwards. Nothing else reads the lines.
- **Per-lane tier (4).** A click on a dot selects it (a ring) and opens a picker
  with the review page's boxes `4 3 2 1` and `none`; 1-4 from the keyboard set
  the selected lane, 0/Backspace clear it, Escape lets go. A dot carrying several
  lanes sets them all. A lane row in the panel selects its dot from the panel side.
- **Colour (5).** Colour is the harness on every plot; the "Colour by" radios are
  gone (kind is still the shape: X for proposed off, hollow for an effort no lane
  runs, diamond for a comparator, dashed for weak provenance). The legend names
  each harness.
- **Panel (6).** `<aside id="tiers">`, sticky beside the plots (stacked under
  62rem), with a counts matrix (one row per harness, one column per tier best
  first, `none`, `all`), then sections Tier 4 to Tier 1 and "Not placed", each
  with the harness's lanes grouped as in item 1 and a count per harness. Each lane
  line is `[4][3][2][1] name`, the review page's marker. A carried lane no board
  draws (`flash-low@agy` and `haiku-high@claude` on the accepted rows) is listed
  wherever its tier puts it with the tag `no rows`, rather than under a heading of
  its own, so a tier's list and its count agree; a lane the pre-screen proposes
  off is tagged `proposed off` and still takes a tier. Only carried lanes are
  listed (`enabled: false` and `ultra` are not). Python decides the list and its
  order (`plot_data` gains `lanes` in `lane_order`, each with `group`, `carried`,
  `off`, `rows`, and `catalogKey`); the script only filters and regroups.
- **Focus (7).** A "Focus" control on each tier heading zooms every plot to that
  tier's band (between its lines; with no lines, to the lanes given that tier)
  and dims every dot not given that tier (`focusDomain`). Reset zoom, a second
  press or a double-click clears it.
- **Tier view (8).** "Show tiers on the plots" toggles: a lane's dot grows and
  carries its tier's digit in the harness colour; a lane with no tier yet is
  hollow; a proposed-off lane keeps a red ring. The setting is kept with the tiers.
- **Reload and copy (9).** `localStorage` key `delegate-bench-page:<catalogKey>`,
  the key being twelve hex digits of the sorted lane names, holds `tiers`,
  `lines` per source and `tierView`; on load, names not in this catalog are
  dropped. Where storage throws (some file:// settings), the panel says the tiers
  last until the tab closes. "Copy as lines" writes `lane tier` lines to the
  clipboard where the browser allows and always shows them selected in a
  textarea. Their order is the review page's *given these tiers*: `-tier`, then
  benchmark order, then grouped; if the wizard's review page opens with different
  tiers (enter straight through puts every lane on tier 1), its order differs,
  and that gap is the "merging the two is later work" the ticket names.
- **Header.** "Read-only for the catalog: a tier drawn here stays in this
  browser, keyed to this catalog, until you set it in the wizard, which is the
  only thing that writes." `lanes.json` is not read or written by the page.
- **Not built.** No separate "no rows" heading (see panel above). No clear-all
  button: a pressed box pressed again clears one lane. The tier lines do not
  carry across sources, because costs are not comparable across sources.

Tests replaced (each with its replacement, none removed):

- `test_bench_page.py` "the page marks what the wizard marks ...": the sweep
  table's effort order `["low", ..., "max"]` became `["max", ..., "low"]`; the
  step figures it also checks are unchanged.
- `test_bench_page.py` "the post-fix cell shape reads ...": the figures in a
  scores cell now read `["at max, not carried", "at high", "effort not stated"]`.

Verification:

- From `agents/skills/delegate`, all 12 `tests/test_*.py` exit 0 with no `FAIL`
  line: 484 `PASS` lines (472 before). `test_setup_tui.py` 76 (72 before; tests
  43-45: `group_lanes` on a fixture with an agy family and an ultra, the carry and
  tier pages grouped, the review page grouped at the best tier, `lane_order`
  against the tier page). `test_bench_page.py` 42 (34 before): the lane list and
  its order, `catalogKey`, the catalog and rows tables' order, and under node the
  pan, the bands, `groupLanes` against `setup_tui.group_lanes` on the same
  fixture, the review order and copy text, the layout's lines, bands, per-point
  tier and dimming, `focusDomain`, and that the script has no network call and
  names no catalog file. No file's count fell.
- `bench_page.py` has no CLI (the brief said `--help` names the arguments; it
  prints nothing), so the page was generated by a driver calling
  `bench.collect` and `bench_page.write` on the stowed catalog with the accepted
  AA and Terminal-Bench rows: 10 boards, 43 lanes. In headless Chromium
  (Playwright, served from a local port because it blocks file://) with real
  mouse events: wheel zoom narrowed the ticks; a left drag while zoomed moved the
  domain toward cheaper costs and higher scores; the tier lines drew at
  `[0.052, 0.27, 1.4]` on `aa` and a 90 px drag on the middle line moved it to
  `0.70`; a click on `astra-low@codex` opened the picker ("The band proposes
  tier 3") and pressing 3 wrote it; a box in the panel put `haiku-high@claude`
  (no rows) on tier 1; Focus on tier 3 zoomed to `$0.6`-`$2` and dimmed 11 of 12
  dots in frame; the tier view drew the digit; "Copy as lines" gave
  `astra-low@codex 3` and `haiku-high@claude 1`; a reload kept tiers, lines and
  the view. The only console error over the session was the test server's
  missing favicon. Dark mode rendered; at 600 px nothing was wider than the
  viewport. Screenshots are in the session scratchpad, named in the return.
- The wizard's T4 and review pages were rendered at 200x50 through
  `layout_lines` and `overlay` on the real catalog and rows, with the Epoch
  columns from the test fixture CSV (no network); the grouping reads as item 1.
- Not verified: Orin with a real mouse, and his own tiers (his box).
