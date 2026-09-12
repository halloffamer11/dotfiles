# 19 — Every effort is a lane, and every lane gets its own benchmark rows

**What to build:** One pass over lanes and their data, so the wizard shows every
model at every effort with the figures measured at that effort:

1. **Efforts on all four harnesses.** Discovery knows each harness's effort list,
   so `--efforts` prints a stanza per effort for a claude, agy or grok model the
   way it already does for codex, and the catalog refuses a lane at an effort its
   harness does not offer. The carry page then shows Fable, Opus 5, Sonnet 5,
   Haiku 4.5, Grok 4.6 and Gemini 3.8 Flash at every effort their CLIs accept
   (Orin, 2026-09-12: "Fable is only shown as extra high", "we only have Opus High").
2. **Every Claude model reaches its rows** (from a draft ticket, never committed). Terminal-Bench's
   `Opus 5` and `Sonnet 5` are dropped as unmatched, and Haiku has no rows at all.
3. **The tier pages and the benchmark page read the per-effort AA rows** (was
   ticket 21), instead of the free API's one entry per model.

## Efforts per harness

Ticket 15 enumerated efforts from the one place `discover.py` reads them: the JSON
of `codex debug models`. The other three harnesses were never given an effort list,
so the catalog has 29 lanes, 24 of them codex. What each harness offers, verified
2026-09-11 with `--help` and the pinned relays:

    harness  efforts the CLI accepts                     discover.py reads   lanes today
    codex    low medium high xhigh max ultra (its JSON)  the JSON            6 per model
    claude   --effort low medium high xhigh max          nothing             one per model
    grok     --reasoning-effort (alias --effort);        nothing             high only
             values not listed in --help
    agy      effort is in the slug: gemini-3.8-flash-    three separate      high only
             high / -medium / -low; --effort low|medium|  models
             high also exists but the relay does not
             pass it and delegate.py ignores an override

The relays already forward the effort for claude and grok. Artificial Analysis
measures Grok 4.6 at low, medium, high and xhigh, but that is a benchmark's list,
not the harness's: one verified probe of grok's accepted values comes first.
`catalog.py` accepts any of the six efforts on any harness, and `delegate.py
--effort` does too; the rule is a small table beside the effort lists. Each Claude
lane made here also needs a `lane-*` agent file in `agents/agents/` (ticket 22).

## Claude rows, checked 2026-09-12

- `aa-accepted.json` holds Claude Opus 5, Sonnet 5 and Fable 5.1 at low, medium,
  high, xhigh and max, and `catalog.resolve_published_model` maps `Claude Opus 5`,
  `Claude Sonnet 5` and `Claude Fable 5.1` to their lanes. So the AA rows attach;
  Opus 5 is missing from the tier pages only because those columns come from the
  free API (section below).
- Terminal-Bench prints `Opus 5` and `Sonnet 5`; both resolve to `None`, because
  only `fable-xhigh@claude` has a `published_as` entry.
- `aa.packet.txt` names Haiku (`Haiku (Reasoning)`, `Haiku (Non-reasoning)`, slugs
  `haiku`, `haiku-reasoning`), but `aa-accepted.json` has no Haiku row, and why
  `effort.py aa` drops it is not known yet. `Claude 4.5 Haiku` also resolves to
  `None` against `claude-haiku-4-5-20251001`.
- **Found 2026-09-12:** the payload's Haiku 4.5 variants are `Claude 4.5 Haiku
  (Reasoning)` (slug `claude-4-5-haiku-reasoning`) and `Claude 4.5 Haiku
  (Non-reasoning)`. `effort._aa_effort` returns `None` for the first, because
  `(Reasoning)` names no effort, so its rows are skipped, and `none` for the second,
  which no lane can select. The reader is right: AA does not measure Haiku at a
  lane's effort. Recorded in `sources.json`. Claude Code itself runs Haiku with no
  effort level: its docs list the models that take effort, say "Models not
  listed here do not support effort", and do not list Haiku
  (https://code.claude.com/docs/en/model-config, read 2026-09-12).

## AA rows in the report

The free API returns one entry per model per effort, but only 200 entries on the
first page, with a pagination key `bench.py` does not follow; on 2026-09-11 that
page held 11 of the 31 catalog variants. `build_aa_section` then keeps the one entry
nearest the lane's effort and drops the rest, so every AA figure carries a caveat
and `flash-high@agy` has none. The tier pages meanwhile show Epoch and swerb columns
that are empty for most lanes (Orin, 2026-09-12). Ticket 17's rule
(`effort_attributes`) already keeps only figures measured at a lane's own effort;
with per-effort rows it has one for every lane. The page payload carries component
scores (Terminal-Bench 2.1, AutomationBench, AA-LCR, IFBench, Omniscience, GPQA
Diamond, GDPval, MMMU-Pro), so the AA columns can be components, as the sources file
asks.

**Blocked by:** None — can start immediately.

**Status:** implemented 2026-09-12, pending Orin's review

Efforts:
- [x] `discover.py` has one effort list per harness: codex from its JSON, claude from its CLI, agy from the slug suffix family (`strip_effort_suffix` already knows it), grok from a probe of its accepted values recorded here with the command that proved it. Claude: `claude --help` (Claude Code 2.1.269) prints `--effort <level>` and, on the next line, `(low, medium, high, xhigh, max)`; `parse_claude_help` reads that line, and the fixture is a copy of the real output. The same five are in https://code.claude.com/docs/en/model-config. If the help ever lists none, `catalog.HARNESS_EFFORTS["claude"]` stands in and discovery says so. Grok: `grok --help` prints `--reasoning-effort <EFFORT>` with no values, and `grok --reasoning-effort bogus models` exits 0, so the CLI checks nothing locally and no non-paid probe proves a value. Grok stays at `high`, the effort `grok46-high@grok` has run at; proving more costs a paid run, and grok's meter was at 12%. Agy: `agy --help` prints `--effort (low|medium|high)`, and `agy models` lists `-low`, `-medium` and `-high` slugs.
- [x] `--efforts` for `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`, `grok-4.6` and `gemini-3.8-flash-high` prints ready-to-paste stanzas, one per effort, with the shared price block; an agy stanza puts the effort in the model slug. There is one exception: Haiku prints the "does not offer reasoning effort levels" message and quotes the docs, because Haiku takes no effort. A `claude-` model that no lane runs yet also gets its stanzas, because the operator named it.
- [x] Discovery reports the agy slug family as one model with efforts, so the harness page and the start page stop listing `flash-medium` and `flash-low` as models with no lane (`group_agy_models`; each model entry now carries `efforts`)
- [x] `catalog.py check` rejects a lane whose effort its harness does not offer, and `delegate.py --effort` rejects the same override, each with a message naming the harness's list
- [x] The new stanzas are in the stowed catalog, generated with provisional tiers and a `note` saying so, each Claude one with its `lane-*` agent file; `check` passes and the carry page lists each with a `why`. Added: `fable-low/medium/high/max@claude`, `opus-low/medium/xhigh/max@claude`, `sonnet-low/medium/xhigh/max@claude`, `flash-low/medium@agy`. Each lane copies its model's meter, `meter_weight`, `timeout` and price. It takes tier 1 when its effort is below the existing lane's effort, and the existing lane's tier when its effort is above. No Haiku lanes were added: Haiku takes no effort, so each would be the same lane under another name. Against the real rows, every new lane has a `why`, and `flash-low@agy` shows "no rows for this lane". One limit: the carry rule compares efforts of one model string, and agy uses one string per effort, so the rule never proposes a flash lane off.

Rows:
- [x] Find why `effort.py aa` writes no Haiku rows; fix the reader, or record in `sources.json` that AA does not measure Haiku at a lane's effort (recorded in `sources.json`; see "Found 2026-09-12" above)
- [x] Every Claude lane carries `published_as` for each printed name an approved source uses, so the wizard's unmatched note lists no Claude model; a test resolves each Claude name in the accepted rows files to its lane model. `published_as` holds only the names that case and separators cannot bridge: `Fable 5.1`, `Opus 5`, `Sonnet 5` and `Claude 4.5 Haiku`, on every lane of each model. `Claude Opus 5` and the other AA names already resolve. The unmatched note still lists `Claude Opus 4.8`, `Claude Fable 5`, `Claude Sonnet 4.6`, `Fable 5` and `Opus 4.8`. Those are other versions that no lane runs, and test 7.9 fixes that each resolves to none.

Report:
- [x] `bench.py collect` takes the AA rows file and fills the `lanes` view with one figure per lane per AA column, measured at that lane's effort; the `models` view keeps one figure per model per column (`collect(lanes_doc, epoch_csv, effort_rows)`; `bench.py --effort-rows` can be repeated)
- [x] The AA columns in the report, the tier pages and the HTML page are component scores with cost per task beside them; the composite index is not a column, and a column no shown lane has a figure for is not shown. Scores are shown as the rows carry them, mostly fractions (`0.873`), and Omniscience is signed.
- [x] No "used effort X (lane effort Y)" line for Artificial Analysis remains in the report's notes. When a model's AA figures stand at an effort no lane runs, the report says that no lane claims them.
- [x] The free API fetch, `AA_URL`, `load_key` and the key-file argument are removed from `bench.py`; nothing reads `~/.config/delegate/aa-key` any more, and `CLAUDE.md` says so (`setup.py --aa-json` is gone as well)
- [x] Epoch AI handling is unchanged and its tests still pass
- [x] The whole suite passes

## Consolidated, 2026-09-12

Orin asked for fewer, larger tickets. Ticket 21 (per-effort AA rows in the report)
and a draft ticket on Claude rows, never committed, folded in here: all three
change the lanes and the data the wizard reads, not the wizard's pages.

## Landed, 2026-09-12

On branch `t19-efforts-and-rows`, commit `5614d9c` (code, tests, catalog, agent
files, `sources.json`, skill `CLAUDE.md`) and the commit that carries this note
(ticket, root `CLAUDE.md`). Not merged.

- **Efforts.** `catalog.HARNESS_EFFORTS` holds each harness's list, with the command or
  page that proved it. `catalog.py check` and `delegate.py --effort` refuse an
  effort outside the list and name the list. `discover.py` reads the claude list
  from `claude --help`, groups agy slugs into families, gives grok its table row,
  and gives Haiku no effort.
- **Lanes.** 14 lanes were added to the stowed catalog, which now has 43. The 12
  Claude lanes each have an agent file, `agents/agents/lane-<model>-<effort>.md`.
  Every tier, `meter_weight` and `timeout` on them is provisional, and each lane's
  `note` says so.
- **Rows.** `published_as` now covers the Terminal-Bench names and AA's Haiku name.
  `resolve_published_model(..., effort=)` picks the agy family member at the row's
  effort. Without it, the new flash lanes would have made "Gemini 3.8 Flash"
  resolve to none, and `flash-high@agy` would have lost its rows.
- **Report.** `bench.py` reads AA only from the accepted rows. On the real rows, 38
  of the 43 lanes have AA figures at their own effort. The five without are
  `haiku-high`, `flash-low` and the three `ultra` lanes.
- **Tests.** The tests for the free-API path were replaced one for one. Old name →
  new name:
  - "both attribution lines present with --aa-json" → "... with --effort-rows"
  - "missing key file skips AA and still renders Epoch" → "no effort rows skips AA
    with the reason and still renders Epoch"
  - "AA key detection names nested and top-level keys" → "AA columns are the
    component benchmarks, in row order, with cost per task; the composite is not
    one"
  - "AA JSON with no metric keys prints first object key names" → "effort rows
    with no Artificial Analysis row skip AA and name the flag that gives them"
  - the four "AA matching: ..." slug tests → name resolution, lane-effort choice,
    xhigh with a signed component, and none never standing for a model
  - the two "AA notes: effort note ..." tests → "no 'Artificial Analysis used
    effort' note ..." and "an AA figure at a lane's effort appears with its cost
    per task and mean rank"

  New tests cover the key-free CLI, a malformed rows file, per-lane cost and rank,
  hidden columns, agy family attribution, the per-harness effort refusals (catalog
  and dispatch), claude help parsing, agy grouping, the claude, Haiku, grok and agy
  `--efforts` output, the stowed lanes and their agent files, and the Claude name
  resolution (7.9). Discover test 16 now expects agy stanzas, and 16b keeps the
  old "does not offer" case. Catalog 1e moved its six-effort loop to a codex lane.
- **Verification.**
  - Both `catalog.py check lanes.json` and `check routing.json` print `ok`.
  - `discover.py --efforts claude-opus-5` prints five stanzas.
  - The suite, with `NO_COLOR` unset, has no FAIL. PASS counts: bench 34 (was 29),
    bench_page 28, catalog 87 (was 76), discover 28 (was 19), dispatch 39 (was 38),
    effort 49, events 1, rank 28, report 87, setup 11, setup_tui 64, usage_reset 1.
    The report count was 87 at `b1e1125` in this environment as well.
