# 18 — Artificial Analysis rows come from the page's own JSON, not from a worker

**What to build:** One command fetches one Artificial Analysis model page, reads
the dataset the page embeds, and writes accepted per-effort rows for every
catalog model the page measures. No worker, no chunking, no agy quota. The wizard,
run with those rows, proposes dominated efforts off from Artificial Analysis data
on the carry page.

**Why this and not the chunk fix.** Both live Artificial Analysis runs on
2026-09-10 died at chunk 6 of 7 when the agy 5-hour meter reached 0%, and the rows
that did come back carried only the composite Intelligence Index, which the
sources file says not to use. The text path was the wrong tool: every
`/models/<slug>` page on artificialanalysis.ai embeds the complete comparison
dataset as JSON in its Next.js flight payload (`self.__next_f.push` chunks). This
is how llm-cost-frontier (catalystneuro, BSD-3, standard library only) updates
four times a day; its `update.py` is the reference implementation.

Measured 2026-09-11 with that parser on `/models/gpt-5-6-sol-high`:

    one request                 3.5 MB, about 1 s
    models parsed               130
    catalog variants present    31 of 32 (Gemini 3.8 Flash low absent that day)
    per variant                 intelligenceIndexCostPerTask.cost.{total,input,output,
                                reasoning,answer}, intelligenceIndexOutputTokensPerTask,
                                intelligenceIndexTimePerTask, intelligenceIndex,
                                and component scores

    component fields            terminalbenchV21, automationBenchPartialScore, lcr,
                                ifbench, omniscience, gpqa, gdpvalNormalized, mmmuPro

The variant name carries the effort: `GPT-5.6 Sol (high)`,
`Grok 4.6 (xhigh)`, `Gemini 3.8 Flash (medium)`,
`Claude Fable 5.1 (Adaptive Reasoning, High Effort, Default Fallback)`. The
payload also carries `release.name` (`GPT-5.6 Sol`), which is the clean model
name. `(Non-reasoning)` is the `none` effort and stays uncertain, as ticket 15
requires.

**The trust boundary holds.** `check` still verifies every number against the
page: a parser cannot originate a number, and the raw payload is the packet the
rows are checked against. The sources file's caution "use `/models/releases/`,
not `/models/<slug>`" was written for the text path, where the model page packed
to 2960 lines with almost no cost data. For the JSON path it is backwards: the
release page payload holds 25 models, the model page holds them all.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `effort.py` (or a sibling it calls) fetches one model page, parses the flight payload, and emits rows in the accepted row schema: one row per variant per component score, with `cost_usd` = cost total per task, tokens, observed date, `provenance` naming the payload field
- [ ] The row's `model` is the release name and `effort` is the word in the variant name, so `catalog.resolve_published_model` resolves every one of the 31 variants to a lane model, and the pre-screen's unmatched line names none of them
- [ ] `(Non-reasoning)` becomes effort `none` with `uncertain: true`; the composite Intelligence Index is emitted as its own benchmark so a reader can see it, but the carry page's domination rule reads the component scores
- [ ] `check` accepts every emitted row against the raw payload and rejects a row whose number is not in it, proven by a test that perturbs one value
- [ ] A trimmed fixture payload (the 31 catalog variants plus two strangers) drives the tests; no network in the suite
- [ ] The wizard run with the emitted rows proposes at least one dominated effort off on the carry page from Artificial Analysis data, and the reason names the source
- [ ] The chunk path (`split_packet`, the per-chunk dispatch) stays only for sources whose packet exceeds the budget; the Artificial Analysis source no longer goes through it
- [ ] `sources.json`'s Artificial Analysis entry says `reaches: embedded-json`, names the `/models/<slug>` page, and drops the release-page caution; the research note records why
