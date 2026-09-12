# 28 — An order inside each tier

**Status:** implemented 2026-09-12, pending Orin's review (the last box is his)

**What to build:** From Orin's review of ticket 27 (2026-09-12). The page places
lanes in tiers; the wizard's review page, where j/k already works, becomes where he
orders the lanes inside each tier: "stacked ranking, which is probably the right
way about it within each tier." Today the ranker orders a tier by pace and then by
lane name, so on one meter (every codex lane shares `codex`) the alphabetically
first lane always wins and the rest never run. Work in `setup_tui.py`, `setup.py`,
`catalog.py`, `rank.py`, their tests, and the docs that state the rule.

## Paste

1. **A carried lane the lines do not name goes off.** Orin, 2026-09-12: "if it's
   not in the tier list, it's not used, so it drops off." The summary line says how
   many went off because they were not named. This replaces ticket 27's "a lane with
   no line keeps what it has", and with it the case where such a lane took tier 1 on
   the review page.
2. **The lines' order inside a tier is the starting order** on the review page (the
   page copies lanes in its panel order).

## Review page

3. **Grouped by tier, 4 to 1**, each tier a section in its current order, numbered.
   j/k moves the cursor; J/K (and shift-up/down) moves the lane under the cursor up
   or down inside its tier; 1-4 moves it to that tier, at the bottom; the key line
   says so. The model grouping of ticket 26 does not apply on this page, since the
   order is Orin's.
4. **Enter writes the order**: each carried lane gets `order`, its position inside
   its tier from 1.

## Catalog and ranker

5. **`order` is an optional positive integer on a lane.** `catalog.py check`
   rejects anything else with a plain-language message naming the lane and the rule.
6. **The sort is tier ascending, `order` ascending (a lane without `order` after
   every lane with one), pace descending, lane name ascending.** The first is the
   pick unless a later lane's pace beats the pick's pace by `margin`, which steals
   the job, as today. Because pace no longer orders a tier, a steal can now happen
   inside a tier: that is the load balance, a lane lower in Orin's order runs when
   its meter is well ahead of the pick's. A catalog with no `order` field ranks
   exactly as before.
7. **Every statement of the rule agrees**: `SKILL.md`, `CONTEXT.md`, the skill's
   `CLAUDE.md`, the `rank.py` docstring, and the root `CLAUDE.md` "Settled" bullet,
   which becomes this rule (it named tickets 01 and 02; it now names 28 too).

## Decisions already made

- Tests check the rule on fixtures, never Orin's tiers or order.
- The page places tiers and off; the wizard orders and writes (tickets 26, 27).
- The Fable meter needs no change: `usage.py` already reads its weekly figure as
  the smaller of Claude's all-models week and the Fable week, which matches
  Anthropic's "draw from your plan's regular weekly usage limits"
  (support.claude.com/en/articles/15424964, 2026-09-12).

## Boxes

- [x] 1 not named goes off, counted in the summary
- [x] 2 lines' order is the starting order
- [x] 3 review page by tier, J/K moves inside a tier
- [x] 4 enter writes `order`
- [x] 5 `order` validated
- [x] 6 rank sort with `order`; no-order catalogs unchanged
- [x] 7 every statement of the rule agrees
- [ ] Orin orders his tiers in the wizard

## Landed, 2026-09-12

Branch `t28-tier-order` (on ticket 27's branch), commit `4868a88` (code, tests,
docs); this note in the commit after it. Not merged.

What shipped:

- **Not named goes off (1).** `setup_tui.unnamed_carried(parsed, carried)` gives the
  carried lanes no line names; `Wizard.apply_tier_lines` (the `v` key and
  `--tiers-from` in the TUI) and `apply_tier_lines_to_doc` (`--plain`) set them off.
  `tier_lines_summary(parsed, dropped)` says `Lines: 2 took a tier; 1 went off;
  3 not named, so off.` Lines that name no lane in the catalog decide nothing, so
  nothing goes off and the line says `no line names a lane in this catalog, so
  nothing changed` (a decision made here: a clipboard with the wrong text must not
  switch every lane off).
- **Starting order (2).** A lane's first place in its tier is its line's position,
  then an `order` the catalog already gives it at that same tier, then benchmark
  order (`Wizard._start_key`). Applying lines again resets the order to the lines.
  Under `--plain`, which has no review page, `write_order_from_lines` writes the
  lines' order inside each tier after the prompts, and the confirm listing prints
  `<lane>: tier N, order M`.
- **Review page (3).** Title "Order each tier". A section line per tier, 4 to 1,
  `Tier 3 (3 lanes)` or `Tier 2 (no lanes)` (drawn bold by `layout_lines` from a
  row's `section` key, `section_row`), then the tier's lanes with a `#` column,
  their place from 1. j/k moves the cursor; J/K and shift-up/down (curses `KEY_SF`
  and `KEY_SR`) swap the lane with its neighbour inside its tier, and do nothing at
  the tier's top or bottom; 1-4 moves it to the end of that tier, its own tier
  included; the cursor stays on the lane. Moves survive routing and back. The
  footer is `j/k: cursor  J/K: move lane  1-4: tier  v: paste  enter: next
  b: back  q: quit` (79 places); two legend lines spell out the moves and what the
  order does to ranking. Model grouping does not apply here. Two choices Orin may
  want to check: the four `T4 T3 T2 T1` boxes are gone, since the section states
  the tier and the line's decision is now its place (the root "Settled" bullet on
  one `[x]`/`[ ]` marker per page was written before this page ordered anything);
  and `o: bench` left the footer to make room, though `o` still works.
- **Enter writes order (4).** At confirm `y`, each carried lane gets `order`, its
  place in its tier; a lane not carried is written with no `order`.
- **Validated (5).** `order` is an allowed lane field; anything but a whole number
  from 1 is refused: `lane '<name>': order is the lane's place inside its tier and
  must be a whole number from 1 up, got <value>`.
- **Rank (6).** The sort key is (unknown pace last, tier, no `order` last, `order`,
  pace desc, lane name); the steal loop is unchanged. Each row carries `order` in
  `--json`; the text form prints `order=N` (or `order=-`) only when some lane has an
  order, so a catalog without one prints as before.
- **Rule statements (7).** `SKILL.md`, `CONTEXT.md` (a new **Order** term; **Margin**
  and **Pick** restated), the skill's `CLAUDE.md`, the `rank.py` docstring, and the
  root `CLAUDE.md` "Settled" bullet, which names tickets 01, 02 and 28. The spec
  `docs/superpowers/specs/2026-09-08-delegate-redesign.md` (lines 95 and 102) still
  states the earlier rule; it was outside this ticket's list and is left as written.

Tests. No test was removed. Replaced assertions: `test_rank.py` case 12 (the row key
set now has `order`); `test_setup_tui.py` 2, 2b, 6 and 26 (the written catalog equals
the old one once `order` is stripped, and each tier's orders are 1..n), 39 (sections
and numbers instead of four boxes; 1-4 moves a lane to a tier), 44b (the review page
starts a tier in benchmark order without model grouping, replacing the grouping
check), 47 (the summary's not-named count), 48 (a lane with no line goes off instead
of keeping tier 1), 50 (lines at start leave every tier page empty); `test_setup.py`
"tiers-from applies the page lines" (unnamed lanes off, the lines' order written).
New: `test_rank.py` 18 (on 11 meter fixtures, 3 catalogs and all 5 classes, 165
rankings, a catalog with no `order` ranks exactly as a separate copy of the rule from
before ticket 28, and the text has no order column) and 19 (order ahead of pace, a
steal inside a tier, unordered after ordered, order never across tiers, and the CLI);
`test_catalog.py` 11 `order` checks; `test_setup_tui.py` 51 (lines' order), 52 (J/K
inside a tier and never across, 1-4, back through routing, `order` written and
validated), 53 (catalog `order` as the starting order, with a gap closed up), 54 (the
render at 80x24 and 200x50).

Verification:

- From `agents/skills/delegate`, all 12 `tests/test_*.py` exit 0 with no `FAIL`:
  517 `PASS` lines (499 before). `test_catalog.py` 98 (87), `test_rank.py` 31 (28),
  `test_setup_tui.py` 85 (81), `test_setup.py` 14 (14); no file's count fell.
- `catalog.py check` prints `ok` for the stowed `lanes.json` and `routing.json`.
- On a scratch copy of `stow/delegate/.config/delegate`, lines
  `terra-xhigh@codex 3`, `opus-high@claude 3`, `grok46-high@grok 3`,
  `sonnet-high@claude 2`, `flash-high@agy 2`, `astra-xhigh@codex off` through
  `setup.py --plain --no-bench --no-discover --tiers-from` with every prompt left at
  its default printed `Lines: 5 took a tier; 1 went off; 34 not named, so off.` and
  wrote both files. All 34 carried lanes not named were `enabled: false`; the five
  named lanes were written with `order` terra 3/1, opus 3/2, grok 3/3, sonnet 2/1,
  flash 2/2. `rank.py impl --json` on fixture meters (claude-general pace 0.80,
  agy-gemini 0.90) picked `sonnet-high@claude` (tier 2, order 1) over
  `flash-high@agy` (order 2, higher pace); with agy-gemini at 1.10 it picked
  `flash-high@agy`, `stolen by pace: 1.1 >= 0.8 + 0.2`, inside tier 2. These tiers
  and meters are fixtures, not Orin's.
- The same lines through `Wizard.apply_tier_lines` on the stowed catalog, walked to
  the review page with one J, rendered at 200x50 through `layout_lines`: tier 3 read
  terra, grok, opus after opus moved down one place. The render is in the return.
- Not verified: the curses page under a real terminal. Whether a given terminal
  sends `KEY_SF`/`KEY_SR` for shift-down/up was not checked; J/K do not depend on it.
  Orin's own order is his box.
