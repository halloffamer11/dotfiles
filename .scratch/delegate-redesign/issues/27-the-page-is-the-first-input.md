# 27 — The page is the first input

**Status:** implemented 2026-09-12, pending Orin's review (the last box is his)

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

- [x] 1 off on the page
- [x] 2 copy writes tiers and off
- [x] 3 review page `v` and `--tiers-from`, one parser, one summary line
- [x] 4 sensitivity table
- [x] 5 beaten by another model, shown
- [x] 6 colour by meter, Fable its own shade
- [ ] Orin pastes his page decisions into the wizard

## Landed, 2026-09-12

Branch `t27-page-first`, commit `c3d0548` (code, tests, the skill's CLAUDE.md
paragraph); this note in the commit after it. Not merged.

What shipped:

- **Off (1).** Each lane line in the tier panel, and the dot picker, has `off`
  after `4 3 2 1`; `o` sets it on a selected dot. The page keeps `off` in place of
  a tier (`localStorage`, as tiers), and a tier-line drag never overwrites it,
  since a box press is a hand-set choice. Off lanes are listed under "Off", between
  Tier 1 and "Not placed", and the counts table has an `off` column. An off lane is
  no tier on a dot (`pointTier`); in the tier view its dot is struck.
- **Copy (2).** "Copy as lines" writes `<lane> <1-4|off>`: the placed lanes in the
  review page's order, then the off lanes (which the review page does not list) in
  benchmark order grouped by model. Lanes not placed are not written. The note
  under the box counts tiers and offs and names `v` and `--tiers-from`.
- **Wizard (3).** `setup_tui.parse_tier_lines(text, lanes_doc)` is the one parser:
  blank lines are skipped, the last line for a lane wins (`repeated`), a name the
  catalog lacks is `unknown`, a line that is not a name and one of 1-4 or `off`
  (case-insensitive) is `bad` by line number, and a tier line for an `ultra` lane
  is `refused` (ticket 15). `tier_lines_summary` is the one line, for example
  `Lines: 10 took a tier; 1 went off; 32 not named.`, with "named twice, last line
  kept", "unknown, ignored", "ultra, never carried, ignored" and
  "not <lane> <1-4|off>, ignored: line n" added only when they occur. "Not named"
  counts every catalog lane with no line. On the review page `v` calls
  `read_clipboard` (`pbpaste`) and nothing else does; a missing or failing
  `pbpaste` or an empty clipboard puts `v: ...; nothing changed` in the message.
  A tier line carries the lane and sets its tier, an off line sets it not carried,
  the order is taken again and the cursor stays on its lane. The footer reads
  `v: paste` (79 places). `setup.py --tiers-from <file>` applies the same lines at
  start: in the TUI through `Wizard.apply_tier_lines`, so the tier pages list only
  what no line decided and the start page shows the summary; under `--plain` the
  lines set the prompts' default tiers and write `enabled: false` for an off line.
  A file that cannot be read stops the run with exit 1 before anything is shown.
- **Sensitivity (4).** A table under the plots (`#sensitivity`, in the plot column):
  one row per placed lane, grouped as the panel groups (tier, then meter, then
  model), one column per board, then "Agree". `sensitivity()` ranks the placed
  lanes a board measured by score (a lane on two points takes its best) and cuts
  that ranking at `round(n * cumulative share)`, tier 4 first, with the shares
  being the page's tier counts; lanes that tie on score take the better tier. A
  differing cell is boxed in the flag colour with a title. The composite column
  is shaded, says "not counted", and is left out of Agree. It redraws with every
  tier change.
- **Beaten by (5).** `beatenByLane(board, carried)`: on one board, a carried lane
  (carried in the catalog and not off on the page) beaten by another carried lane
  of any model, at least the score for no more cost and better in one, is named by
  the beater that scores most, then costs least. A lane never beats itself on a
  second point. The tooltip says `beaten by <lane> on this board`; the panel line
  says `beaten by <lane>` on a line of its own under the name, over every board a
  plot shows, with a per-board title. Costs never cross boards. The carry rule and
  `propose_enabled` are untouched.
- **Colour (6).** `bench_page.meter_shades(lanes_doc)`: within a harness, the meter
  most of its lanes use takes the harness colour (shade 0), the next shade 1, with
  ties broken by name. `--h-<harness>-1` is defined for every harness in the light,
  system-dark and toggled-dark palettes; a shade 2 would fall back to the harness
  colour. On the stowed catalog `claude-general` (11 lanes) is `#7a4cc2` and
  `claude-fable` (5) is `#43207e` (dark theme `#a784e6` / `#dccafb`). Points,
  panel swatches, the counts table (now one row per meter) and the legend
  ("a claude-fable lane") use the meter.
- **Not built.** No page control writes `lanes.json`. The wizard's own carry and
  tier pages are unchanged, since retiring them is later work.

Tests. The one replaced assertion is `test_bench_page.py` "the page lists every
lane in the tier page's order ...". It checked the lane record's exact key set,
which now also holds `meter`; the rest of that test is unchanged. No test was
removed. New: `test_bench_page.py` 27.6 meter shades on a two-meter fixture; under
node 27.1 off in the store, drag and dots, 27.2 the copy and its read-back through
`parse_tier_lines`, 27.4 the sensitivity cut, ties, marks, Agree and grouping,
27.5 beaten-by with an off lane, an uncarried lane and a lane on two points, 27.6
meter colours, and the page's sensitivity section. `test_setup_tui.py` 47 the
parser (blank lines, a duplicate, an unknown lane, a tier of 5, a missing tier, an
extra field, a non-tier, an ultra), 48 `v` on the review page (the reader called
once and only on `v`, the rows, the cursor, the summary on screen, the written
catalog), 49 `pbpaste` missing (stub and real PATH), exiting 3, and an empty
clipboard, 50 lines applied at start. `test_setup.py`: `--tiers-from` under
`--plain`, and an unreadable file.

Verification:

- From `agents/skills/delegate`, all 12 `tests/test_*.py` exit 0 with no `FAIL`:
  499 `PASS` lines (486 before). `test_bench_page.py` 50 (43), `test_setup_tui.py`
  81 (77), `test_setup.py` 14 (12); no file's count fell.
- The page was generated on the stowed catalog (43 lanes) with the 624 accepted AA
  and Terminal-Bench rows and the Epoch fixture CSV (no network), served from a
  local port, and driven in Playwright with real clicks. Ten tiers and one off
  (`astra-xhigh@codex`) were set from the panel's boxes. Counts read T4 2, T3 2,
  T2 3, T1 3, off 1, none 29 of 40, per meter. Copy gave 11 lines, and the note
  said "10 with a tier and 1 off". The sensitivity table drew 10 boards with the
  composite shaded. Hovering `opus-max@claude` on the AA index said
  `beaten by astra-max@codex on this board`, and the panel line said the same. The
  Fable dots use `var(--h-claude-1, ...)` (`#43207e`), the opus and sonnet dots
  `var(--h-claude, ...)`. A reload kept all 11 decisions. At 600 px the page was
  600 px wide. The only console error was the test server's missing favicon. These
  tiers are a fixture for the check, not Orin's.
- The copied lines were fed to `setup.py --plain --tiers-from` against a scratch
  copy of `stow/delegate/.config/delegate`. It printed
  `Lines: 10 took a tier; 1 went off; 32 not named.` and wrote nothing (stdin
  closed). The same lines through `Wizard.apply_tier_lines`, walked to the review
  page and pasted again with a stubbed clipboard, rendered at 200x50: the named
  lanes kept their tiers, `astra-xhigh@codex` moved to "Not carried", and the
  unnamed lanes took tier 1 through T1's opening rule (ticket 25). The render is in
  the return.
- Not verified: the curses TUI under a real terminal with a real `pbpaste`, and
  Orin's own decisions (his box).
