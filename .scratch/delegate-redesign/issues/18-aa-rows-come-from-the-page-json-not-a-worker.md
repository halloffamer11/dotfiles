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

**Status:** landed 2026-09-11 on `bench-aa-effort-slugs`.

- [x] `effort.py` (or a sibling it calls) fetches one model page, parses the flight payload, and emits rows in the accepted row schema: one row per variant per component score, with `cost_usd` = cost total per task, tokens, observed date, `provenance` naming the payload field
- [x] The row's `model` is the release name and `effort` is the word in the variant name, so `catalog.resolve_published_model` resolves every one of the 31 variants to a lane model, and the pre-screen's unmatched line names none of them
- [x] `(Non-reasoning)` becomes effort `none` with `uncertain: true`; the composite Intelligence Index is emitted as its own benchmark so a reader can see it, but the carry page's domination rule reads the component scores
- [x] `check` accepts every emitted row against the raw payload and rejects a row whose number is not in it, proven by a test that perturbs one value
- [x] A trimmed fixture payload (the 31 catalog variants plus two strangers) drives the tests; no network in the suite
- [x] The wizard run with the emitted rows proposes at least one dominated effort off on the carry page from Artificial Analysis data, and the reason names the source
- [x] The chunk path (`split_packet`, the per-chunk dispatch) stays only for sources whose packet exceeds the budget; the Artificial Analysis source no longer goes through it
- [x] `sources.json`'s Artificial Analysis entry says `reaches: embedded-json`, names the `/models/<slug>` page, and drops the release-page caution; the research note records why

## Landed

`python3 agents/skills/delegate/scripts/effort.py aa --out-dir <dir>` fetches the
page `sources.json` approves (`--url` for another, `--html` for a saved one),
writes `packet.txt` (the provenance header, then the whole flight payload
verbatim) and `rows.json`, and runs `check` over them. The live run on
2026-09-11 gave 137 variant objects, 77 with an effort word, and 606 rows;
`check` accepted all 606. All 31 catalog variants were present, and the
unmatched line named none of them. The rows and the packet are in
`.scratch/delegate-redesign/_data/aa-accepted.json` and `aa.packet.txt`.

Where the build differs from the text above:

- **`provenance` stays the enum.** `check` rejects any other value, and the bench
  page reads it. Each row says `unlabelled`, because the page has no per-row
  badge. The payload field behind each number is in a new key, `fields`, beside
  `variant`, the name the page printed. `composite: true` marks the index row.
- **The carry rule is a majority, not "any benchmark".** Eight components from the
  same runs made the old rule propose 12 lanes off, 9 of them on one component.
  Orin chose (2026-09-11): a lane is dominated when another effort of the same
  model, for no more money, beats it on more than half of the benchmarks that one
  source scored both on. A one-benchmark source reads as before. The bench page
  follows the rule through `dominating_row`, so a dominated effort is marked on
  every board of its source. Live: only `astra-xhigh@codex` is off, beaten by high
  on 4 of 7 components.
- **The reason reads `high wins on aa`, not "dominated by high (aa)".** The `why`
  column has 21 places at 80 columns, and "dominated by medium (tbench)" needs 28.
  The legend line defines "X wins on S". `setup_tui.is_dominated_reason` is now
  the one test for that phrase, and the bench page uses it.
- **`check` knows one printed synonym.** The page prints `Non-reasoning` and
  never `none`, so `EFFORT_PRINTED` lets `none` be sourced by either word. It adds
  no number and no model name.
- **`extract` refuses an AA packet** before it writes a brief. `split_packet` and
  the per-chunk dispatch are unchanged for other sources.

The wizard box is proven in the `Wizard` state machine (test 30b, fixture rows)
and by `propose_enabled` on the live rows with the stowed catalog. No human has
driven the TUI with these rows; that is Orin's next run.

Tests: 12 new assertions — 7 in `tests/test_effort.py` through `aa_extract`,
`check_rows` and the CLI; 4 in `tests/test_setup_tui.py` (majority rule, composite,
AA fixture on the carry page); 1 in `tests/test_bench_page.py`. Eight existing
expectations changed to the new reason text. Suite 389 PASS lines across 12
files, 0 failures.
