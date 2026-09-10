# 17 — bench scores are attributed to lanes that did not produce them

**What is wrong:** `bench.py` groups the catalog by model (`catalog_models`) and
reports one row per *model*. The wizard's tier screens then look a score up by
`lane["model"]`, so every lane of a model shows the same numbers — including
lanes at efforts nobody measured.

Found by Orin 2026-09-10, running the wizard for the first time with the six
astra lanes in place. His words: "why do all the astra effort levels have a
score and identical? only the effort level scored should be reported here."

Measured against the live Epoch CSV the same day. Epoch has exactly three rows
for `gpt-6-astra`, and each was measured at a different effort:

    DeepSWE       0.7411  model_version gpt-6-astra_xhigh    -> effort xhigh
    FrontierCode  0.5326  model_version gpt-6-astra_max      -> effort max
    APEX-Agents   0.4670  model_version gpt-6-astra          -> effort unstated

The tier 4 screen showed all three against all six lanes:

    astra-low@codex     74.1  53.3  46.7   1.3 (n=3)
    astra-medium@codex  74.1  53.3  46.7   1.3 (n=3)
    astra-high@codex    74.1  53.3  46.7   1.3 (n=3)
    astra-xhigh@codex   74.1  53.3  46.7   1.3 (n=3)
    astra-max@codex     74.1  53.3  46.7   1.3 (n=3)
    astra-ultra@codex   74.1  53.3  46.7   1.3 (n=3)

So `astra-low@codex` displays a DeepSWE figure produced at xhigh and a
FrontierCode figure produced at max. This is ticket 16's defect in a second
place — a number attributed to a lane that did not produce it — and it is worse
than ticket 16's, because ticket 16 showed nothing while this shows something
false, at the moment a human is deciding which lanes to pay for.

**Why it went unnoticed:** until the astra sweep landed, every model in the
catalog had exactly one lane, so per-model and per-lane were the same thing.
`select_epoch_cell` even chooses an effort per model (`choose_effort`, then
`EFFORT_FALLBACK`), which reads as effort-awareness but only picks which single
figure the whole model shows.

**Related, latent:** `LANE_EFFORT_ORDER` is `(xhigh, high, medium, low)` — no
`max`, no `ultra`. `lane_effort_of` therefore cannot name the effort of a model
whose lanes are only `max`/`ultra`; it falls through to `efforts[0]`.

**The same loss happens twice more.** `build_aa_section` works out which effort
an Artificial Analysis figure was measured at (`matched_effort`, returned as
`"effort"`), and `collect()` copies only `cols`, `mean` and `mean_s` — so the
effort is dropped at the collect boundary and the AA table cannot say what it is
showing either. Found by the page redesign, 2026-09-10. And `select_epoch_cell`
picks one figure per model per benchmark via `choose_effort`, discarding any
other efforts Epoch measured for that same benchmark, so even a correct
attribution has nothing left to attribute.

**Contract agreed 2026-09-10**, so the two consumers can be built in parallel:

    epoch.cells[benchmark] = {<effort>: {performance, source, duplicates}}
        keyed by effort, with the literal key "unknown" for an unstated one,
        holding every effort measured rather than one pick
    aa[...]["effort"] = <effort> | None      carried through collect()
    bench["lanes"][lane_name] = {cells, mean, mean_s, n}
        figures effort-matched to that one lane, mean and n over those alone

`models` stays the model-level view, which is what a comparison against models
nobody runs needs. Attribution is one function in `bench.py` that both the
wizard and the page call, for the reason `dominating_row` is exported rather
than copied.

**Decisions to make**

1. An unstated-effort figure (`APEX-Agents` above) belongs to no lane. Dropping
   it loses a real measurement; showing it against every lane is the bug. It
   should be reported once against the model, visibly separate from the
   per-lane rows.
2. `n=` in the mean rank has to count the benchmarks that measured *that lane's*
   effort, not the model's, or the mean is a mean of things that never happened
   together.

- [ ] A benchmark figure reaches a lane only when the measured effort equals the lane's effort
- [ ] A figure whose effort is unstated reaches no lane, and is still visible somewhere
- [ ] The mean rank and its `n=` count only figures attributed to that lane
- [ ] `LANE_EFFORT_ORDER` covers every effort in `catalog.EFFORTS` that a source can report
- [ ] An Artificial Analysis figure carries the effort it was measured at, through `collect()`
- [ ] Every effort Epoch measured for one model and benchmark survives collection, not just one pick
- [ ] `tests/test_bench.py` covers a model with two lanes whose efforts were measured differently, from a fixture, no network
- [ ] The tier screen for the six astra lanes shows a figure only where one was measured at that effort

## The consuming side is already written 2026-09-10

`bench_page.py` reads a figure's own effort and attributes it per lane, and its
`_cell_figures` accepts both shapes: the current cell carrying `performance`
and `effort`, and the contract's cell keyed by measured effort with `unknown` a
literal key. So `bench.py` can be changed to emit the new shape without
touching the page, and `tests/test_bench_page.py` already asserts the new shape
renders — every effort shown in effort order, each attributed on its own, and
an Artificial Analysis figure attributed by `aa[...]["effort"]`. That test is
the page-side half of this ticket's last box; the wizard's tier screen is the
other half and is untouched.

**Status:** open, found 2026-09-10. Blocks a live tier pass: the numbers the
wizard offers for that decision are currently wrong.
