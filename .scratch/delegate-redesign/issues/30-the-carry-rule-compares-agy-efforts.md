# 30 — The carry rule compares agy efforts

**What to build:** the carry rule proposes a Lane off when another effort of the same
model beats it. It matches rows by the Lane's `model` string. agy names each effort as
its own model (`gemini-3.8-flash-low`, `-medium`, `-high`), so no agy Lane ever has
"another effort of the same model" and the rule never proposes a flash Lane off. Recorded
as a limit in ticket 19; open item 2 in the root `CLAUDE.md`.

**Blocked by:** None — can start immediately.

## Scope

Paths are relative to `agents/skills/delegate/`.

- `scripts/bench.py`: `dominating_effort`, `dominating_row`, `_first_domination` and the
  `KIND_NO_ROWS` test in `propose_enabled` compare `row["model"]` with the Lane's
  `model`. Compare a model family key instead. For every Harness but agy the key is the
  model string. For agy the key is the slug with its trailing effort removed, the same
  grouping `scripts/discover.py: group_agy_models` already uses; reuse that rule, do not
  write a second one.
- The benchmark page draws the rule through `dominating_row` (ticket 24), so it follows
  with no second implementation.
- The rule itself does not change: same source, more than half of the shared benchmarks,
  for no more money; the AA composite index is shown and never counted; an explicit
  `enabled` is never undone.

## Acceptance

**Status:** implemented 2026-09-18 (`4177aa5`) on `worktree/delegate-redesign`; all boxes ticked. The merge to `main` is Orin's.

- [x] A fixture with two agy efforts scored by one source, one beating the other for no
      more money, proposes the beaten Lane off and names the competitor effort.
- [x] A fixture where the two agy efforts share no benchmark proposes nothing.
- [x] Codex, claude and grok fixtures give the same proposals as before.
- [x] The benchmark page marks the dominated agy point the way it marks a codex one.
- [x] `python3 tests/test_bench.py`, `tests/test_setup.py` and `tests/test_setup_tui.py`
      pass.
- [x] Run against the accepted rows in `.scratch/delegate-redesign/_data/` and record in
      the Landed note which agy Lanes, if any, the rule now proposes off. The stowed
      catalog is not edited: a proposal is Orin's to accept on the carry page.

## Landed, 2026-09-18

Dispatched by `/delegate run impl`: Tier 2 was under the Gate (codex 1%), and in Tier 3
`opus-high@claude` took a Margin steal from `grok46-high@grok`. Run
`20260918T154806Z-opus-high@claude-cd8e5d70`, 505 s, verdict clean.

`catalog.agy_family(slug)` is the one family rule; `discover.group_agy_models` now calls
it. `bench.model_families(lanes_doc)` maps each Lane model to its family key (the model
string, or the agy slug without its effort), and `dominating_effort`, `dominating_row`,
`_first_domination` and the no-rows test in `propose_enabled` compare that key.
`bench_page._annotate` passes the same map. Tests were written first and failed first.

Checked by the session: all 13 suites under `agents/skills/delegate/tests/` exit 0. Against
the accepted rows in `_data/`, the proposals before and after are identical, and no agy
Lane is proposed off: AA scores Gemini 3.8 Flash at medium and high, medium is cheaper and
scores lower, so neither beats the other; `flash-low@agy` is already recorded off. The
rule now can propose a flash Lane off; today's rows give it no reason to.
