# 35 — Every current-generation Lane can be screened and placed on the page

**What to build:** in Orin's first `delegate global` run, 2026-09-22, he picked Tier 3
for `opus55-medium@claude` on the benchmark page, and the choice went nowhere: "For
some reason, Opus 5.5 isn't working." Three causes, all checked:

1. Ticket 33 made a successor Lane inherit its predecessor's `enabled`. `opus-*@claude`
   was carried only at `high`, so `opus55-low`, `-medium`, `-xhigh` and `-max` started
   off. The same is true for most `sol6-*` and `luna6-*` efforts. Orin's rule was "The
   expectation is for all models to be shown initially for screening."
2. The page places only Lanes that the catalog carries. `makeTierPanel` and "Copy as
   lines" (`assets/bench_page.js`, `data.lanes.filter((l) => l.carried)`, near line
   1289) drop a Tier picked on any other Lane's dot. The picker still accepts it.
3. The wizard writes the page once at start (`setup.py`, `bench_page.write`), and `o`
   only reopens that file. A Lane carried later on the carry page never reaches the
   page.

The wizard's side already works. `catalog.apply_tier_lines_to_doc` carries a Lane that
a `<lane> <1-4>` line names, so the fix is on the page and in the refresh.

**Blocked by:** None — can start immediately.

## Rule

The points below are session decisions; Orin may overrule them.

- **New Lanes start carried.** A new Lane the refresh adds starts carried, except
  `ultra` (settled, ticket 15). It still inherits `tier`, `order`, meter,
  `meter_weight` and `timeout` from its predecessor. It no longer inherits `enabled`.
  The pre-screen proposes the dominated efforts off, as it does for every carried Lane.
- **The page places any Lane that has rows.** A Tier picked on any Lane's dot places
  that Lane, whether or not the catalog carries it. The Tier panel lists it and counts
  it, and "Copy as lines" writes it. `ultra` stays unplaceable, because
  `parse_tier_lines` refuses it; the page should not offer it. Bands (`applyBands`)
  still auto-assign only Lanes that are carried on the page, so drawing a line never
  carries a Lane by itself.
- **`o` writes the page again from the wizard's current catalog before it opens it.**
  The page's catalog key must not change because of that. Tiers already drawn in the
  browser's `localStorage` must survive, so check how `catalogKey` is computed.
- **Correct wording.** The carry page's reason "off in the catalog" is false for a
  Lane the catalog does not have yet. A new Lane that starts off (only `ultra` after
  this ticket) says `new, off (ultra)` or similar, and no text claims catalog state
  that the file does not hold.

## Scope

Paths are relative to `agents/skills/delegate/`:
- `scripts/discover.py` (`refresh_catalog`: `enabled` is not inherited);
- `scripts/setup.py` and `scripts/setup_tui.py` (the `o` path writes the page, and the
  carry reason text);
- `scripts/bench_page.py`, if the data needs a field;
- `assets/bench_page.js`;
- tests: `tests/test_discover.py`, `tests/test_setup.py`, `tests/test_setup_tui.py`,
  `tests/test_bench_page.py`, and the JS tests `test_bench_page.py` already drives;
- the skill `CLAUDE.md` wizard and page entries, and ticket 33's rule line on
  inheritance (mark it as changed by ticket 35).

## Acceptance

**Status:** ready-for-agent

- [ ] On the 2026-09-22 fixtures, every new non-`ultra` Lane starts carried, with its
  predecessor's Tier and Order. Every `ultra` Lane starts off.
- [ ] On the page, a Tier picked on the dot of a Lane the catalog does not carry
  appears in the Tier panel and in "Copy as lines". Pasted into the wizard with `v`,
  or given with `--tiers-from`, it carries that Lane at that Tier. Show this with a
  test through `parse_tier_lines` and `apply_tier_lines_to_doc`, using the page's own
  text.
- [ ] A Lane carried on the carry page after start appears as carried the next time
  `o` opens the page, and tiers drawn earlier in the browser survive the rewrite
  (same catalog key).
- [ ] No carry-page reason says "in the catalog" for a Lane the catalog file does not
  hold.
- [ ] All 14 suites pass.
