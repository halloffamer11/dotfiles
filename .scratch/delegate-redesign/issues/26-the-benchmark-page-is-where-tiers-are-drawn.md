# 26 — The benchmark page is where tiers are drawn

**Status:** ready-for-agent

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

## Boxes

- [ ] 1 grouping on every wizard page and page table
- [ ] 2 pan
- [ ] 3 draggable tier lines
- [ ] 4 per-lane tier on the page
- [ ] 5 harness colours
- [ ] 6 side-by-side tier panel with counts and the no-rows list
- [ ] 7 focus a tier
- [ ] 8 tier view
- [ ] 9 reload survives, copy as lines
- [ ] Orin draws his tiers on the page and sets them in the wizard
