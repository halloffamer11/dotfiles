# 36 — Page: reset every tier, and a relative price per model; an off Lane never stops a project

**What to build:** four items. Orin gave the first three after his first refreshed
`delegate global` run, 2026-09-22. The session found the fourth the same day.

1. "In the tool I'd like to have a reset everything option in the tiers on the HTML."
2. "In the HTML I would like to have a graphical pricing, relative pricing of all these
   different models, and you don't need to price the effort levels, just the models.
   Effort is the same … just remove effort or collapse on effort for each model tier."
3. "specifying the specific effort level is important, but we don't have a great
   mechanism for allowing the orchestrating model during delegation to select an effort
   level. I think we should just hard code it in like we are. But if there becomes a
   way to do this, it would be good to know if there's an example of how this could be
   done … just a comment."
4. Orin's run turned `terra-high@codex` off. This checkout's `.delegate/routing.json`
   named it in `project_order`, and `rank.py` then stopped: "project_order lane
   'terra-high@codex': lane is globally off; project_order cannot restore it". Ticket
   33 made a *removed* Lane warn. A Lane turned *off* still stops routing. The session
   repaired this checkout's file by hand (now `["luna6-max@codex"]`).

**Blocked by:** None — can start immediately.

## Rule

The points below are session decisions; Orin may overrule them.

**1. Reset.** The page's Tier panel gets one "Reset every tier" button.
- It clears everything the page holds for this catalog:
  - every Tier and off drawn,
  - every manual mark,
  - the three Tier lines on each board, back to their defaults.
- The page then shows the catalog's own state again.
- It keeps the "Show tiers on the plots" toggle.
- It asks once before it clears (`window.confirm`), because it drops drawn work.
- It writes nothing outside the browser, as the page never does.

**2. Price per model.** A new section on the page, "Price per model", beside or below
the plots:
- One row per model. Efforts collapse into one row: every effort of a model has the
  same token price. For agy, the per-effort slugs join into their family through the
  page's `group` or `catalog.agy_family`.
- It shows every model the catalog has, and marks the ones with a carried Lane.
- It shows the input and output list price in USD per 1M tokens, on one shared log
  scale, so the relative price reads directly. Use a dot plot, not bars, because bars
  on a log scale need no zero.
- Sort by output price. Colour by harness with the page's existing meter colours.
- Label each dot with its value.
- A model with a `null` price says "no published price" on its row and has no dot.
- The data comes from the catalog's `price` fields, through `bench_page.py`. If two
  efforts of one model disagree, show the range and flag the row; this should not
  happen.
- Before you draw, load the `dataviz` skill if your tools allow it, and follow its
  mark and colour rules.
- Keep the page's light and dark themes working.

**3. A comment on effort, and no behaviour change.** Put a short comment at the point
where `rank.py` returns the Pick. Say that effort is fixed per Lane, because a Lane is
one model at one effort, and that the ranker picks a Lane and never an effort. Then
give the one path that exists if an orchestrator is ever trusted to choose:
- `delegate.py dispatch --lane <lane> --effort <e>` overrides the effort for one
  named job;
- agy ignores it, because agy carries the effort in the model name;
- example: `delegate.py dispatch --lane sol6-high@codex --effort xhigh --class impl`;
- a Class-to-effort rule in `assets/classes.md` would be where such a choice lives.

Add nothing else. No flag, no rule, no doc page.

**4. An off Lane in a project file.** On load, a project `project_order` entry, or a
`.delegate/lanes.json` entry, that names a globally off Lane is ignored with one
warning, the same as a removed Lane (`catalog.warn_stale_lane`, or a sibling with its
own wording). Turning a Lane off in the wizard must never stop routing in a project.
A new project save still refuses to name an off Lane, and the next project save drops
the entry, as ticket 33 does for a removed Lane.

## Scope

Paths are relative to `agents/skills/delegate/`:
- `assets/bench_page.js`;
- `scripts/bench_page.py` (the price data);
- `scripts/rank.py` (the comment only);
- `scripts/catalog.py` (item 4);
- tests: `tests/test_bench_page.py` (and the JS tests it drives) and
  `tests/test_catalog.py`;
- the skill `CLAUDE.md` page entry.

## Acceptance

**Status:** implemented 2026-09-22 (`47439fb`, `c3acf00`, `53261d4`, `bc18235`, `7b9c0b4`) on `worktree/delegate-redesign`, rebased onto Orin's `776df1a`; all boxes ticked. The merge is Orin's, and he may overrule the session decisions under Landed. Polish queued: the luna row's input label overlaps its link, and the value labels mix `$10.0` with `$2`.

- [x] "Reset every tier" asks once. After yes, the page holds no Tier, off, manual
  mark or moved line for this catalog key, and it shows the catalog's own state.
  Test the store logic.
- [x] "Price per model" shows one row per model, and no row per effort. Show it with a
  test over a catalog that has several efforts per model and an agy family.
- [x] Every priced model has an input dot and an output dot on one log axis, a model
  with a `null` price reads "no published price", and a row whose efforts disagree is
  flagged.
- [x] The rank.py comment is present, and nothing else in ranking or dispatch changes.
  The rank tests are unchanged and pass.
- [x] A project file that names a globally off Lane warns once, and `rank.py` still
  ranks there. A project save drops the entry.
- [x] All 14 suites pass.

## Landed, 2026-09-22

One commit per item.

1. **Reset.** `page.resetAll()` in `makeStore` empties the three things the page
   keeps for this catalog — tiers and offs, manual marks, and every board's tier
   lines — writes that back, and the button in the Tier panel asks once through
   `window.confirm` before calling it. The tier view toggle stays; the focused
   tier goes with the tiers, because there is nothing left to focus on. Tested
   through the store: what it clears is cleared in the browser too, so a reload
   draws nothing.
2. **Price per model.** `bench_page.price_rows(lanes_doc)` is the data, one row
   per model with efforts collapsed and an agy family joined through
   `catalog.agy_family`; `drawPrices` in `assets/bench_page.js` draws it. On the
   2026-09-22 fixture catalog that is 10 rows, dearest output first, and on a
   refreshed priced catalog 12, with `grok-4.7-build-fast` last and unpriced.
3. **The comment** sits where `rank()` returns the Pick. Nothing else changed:
   `tests/test_rank.py` and `tests/test_dispatch.py` are untouched and pass.
4. **An off Lane in a project file.** The reproduction stopped with
   "lane is globally off; project_order cannot restore it"; it now warns once and
   ranks. `.delegate/lanes.json` naming an off Lane was never an error and is
   tested so it stays that way.

Session decisions, Orin's to overrule:

- The price chart draws input as an open dot and output as a filled one, rather
  than a second hue for the same money. Colour stays the meter, and the row's own
  name is the identity, so colour carries nothing on its own.
- When two efforts disagree about a price, the dot sits on the dearer of the two
  and the label reads as the range (`$1–$2`). The dearer is the one a run might
  be charged, and the range in the label is the whole of what there is to say.
- The chart uses the page's `fmtMoney`, so $50 reads `$50.0`, the same as every
  other figure on the page.
- A model name longer than the name gutter is cut with an ellipsis and stays
  whole in the row's tooltip, rather than drawn off the edge.
- `dataviz` asks for selective labels; Orin asked for a value on every dot, and
  with one row per model there are few enough that both can be served. The labels
  wear text tokens, never the mark's colour, and flip sides rather than collide.
- The dashboard's `_validate_project_proposal` is the one caller that passes
  `proposal=True`. Its own test moves with it: a lane turned off behind the
  dashboard's back now reads as a conflict to reload and repeat, and the save is
  still refused.
