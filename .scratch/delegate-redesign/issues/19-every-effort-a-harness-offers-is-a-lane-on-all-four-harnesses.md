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

**Status:** ready-for-agent

Efforts:
- [ ] `discover.py` has one effort list per harness: codex from its JSON, claude from its CLI, agy from the slug suffix family (`strip_effort_suffix` already knows it), grok from a probe of its accepted values recorded here with the command that proved it
- [ ] `--efforts` for `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`, `grok-4.6` and `gemini-3.8-flash-high` prints ready-to-paste stanzas, one per effort, with the shared price block; an agy stanza puts the effort in the model slug
- [ ] Discovery reports the agy slug family as one model with efforts, so the harness page and the start page stop listing `flash-medium` and `flash-low` as models with no lane
- [ ] `catalog.py check` rejects a lane whose effort its harness does not offer, and `delegate.py --effort` rejects the same override, each with a message naming the harness's list
- [ ] The new stanzas are in the stowed catalog, generated with provisional tiers and a `note` saying so, each Claude one with its `lane-*` agent file; `check` passes and the carry page lists each with a `why`

Rows:
- [ ] Find why `effort.py aa` writes no Haiku rows; fix the reader, or record in `sources.json` that AA does not measure Haiku at a lane's effort
- [ ] Every Claude lane carries `published_as` for each printed name an approved source uses, so the wizard's unmatched note lists no Claude model; a test resolves each Claude name in the accepted rows files to its lane model

Report:
- [ ] `bench.py collect` takes the AA rows file and fills the `lanes` view with one figure per lane per AA column, measured at that lane's effort; the `models` view keeps one figure per model per column
- [ ] The AA columns in the report, the tier pages and the HTML page are component scores with cost per task beside them; the composite index is not a column, and a column no shown lane has a figure for is not shown
- [ ] No "used effort X (lane effort Y)" line for Artificial Analysis remains in the report's notes
- [ ] The free API fetch, `AA_URL`, `load_key` and the key-file argument are removed from `bench.py`; nothing reads `~/.config/delegate/aa-key` any more, and `CLAUDE.md` says so
- [ ] Epoch AI handling is unchanged and its tests still pass
- [ ] The whole suite passes

## Consolidated, 2026-09-12

Orin asked for fewer, larger tickets. Ticket 21 (per-effort AA rows in the report)
and a draft ticket on Claude rows, never committed, folded in here: all three
change the lanes and the data the wizard reads, not the wizard's pages.
