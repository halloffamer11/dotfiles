# 28 — An order inside each tier

**Status:** ready-for-agent

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

- [ ] 1 not named goes off, counted in the summary
- [ ] 2 lines' order is the starting order
- [ ] 3 review page by tier, J/K moves inside a tier
- [ ] 4 enter writes `order`
- [ ] 5 `order` validated
- [ ] 6 rank sort with `order`; no-order catalogs unchanged
- [ ] 7 every statement of the rule agrees
- [ ] Orin orders his tiers in the wizard
