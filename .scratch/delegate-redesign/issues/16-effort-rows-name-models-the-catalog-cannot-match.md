# 16 — effort.py returns display names, so the pre-screen sees no data

**What is wrong:** `effort.py` returns whatever the leaderboard prints in its model
column. Terminal-Bench prints display names — `GPT-6 Astra`, `Gemini 3.8 Flash`,
`Fable 5.1` — while the catalog keys on slugs: `gpt-6-astra`,
`gemini-3.8-flash-high`, `claude-fable-5-1`. The pre-screen matches
`row["model"] == lane["model"]`, so **none of it matches**, and every lane reads
"no rows for this lane; absence is not evidence against" while a full effort sweep
sits in the file.

Measured 2026-09-10 on the first real Terminal-Bench extraction
(`_data/tbench-accepted.json`, 18 rows, `check` accepted 18 and rejected 0):

    catalog slugs       gpt-6-astra, gemini-3.8-flash-high, claude-fable-5-1, …
    tbench row models   GPT-6 Astra, Gemini 3.8 Flash,     Fable 5.1,        …

    astra-low@codex     on   no rows for this lane; absence is not evidence against
    astra-medium@codex  on   no rows for this lane; absence is not evidence against
    astra-high@codex    on   no rows for this lane; absence is not evidence against
    astra-xhigh@codex   on   no rows for this lane; absence is not evidence against
    astra-max@codex     on   no rows for this lane; absence is not evidence against

**What that costs.** Those five rows are the only real per-effort sweep in the
packet, and they carry the finding the pre-screen exists to surface:

    gpt-6-astra  low     50.61  $1557
    gpt-6-astra  medium  54.24  $1915
    gpt-6-astra  high    57.88  $2269
    gpt-6-astra  xhigh   57.88  $2351   <- same score as high, more money
    gpt-6-astra  max     58.18  $3267   <- +0.30 points for +44% cost

`astra-xhigh@codex` is dominated by `astra-high@codex` on this source, and the
pre-screen should have said so. It said "no rows".

**This is source-dependent, which is why it went unnoticed.** SWE Refactor Bench
publishes slugs (`gpt-5.6-luna`), so the swerb rows match and the rule worked when
it was tested against them. Terminal-Bench and Artificial Analysis publish display
names.

**Where the fix belongs.** Not in the extraction prompt: asking a worker to
normalise a name is asking it to originate data, and `effort.py`'s own stage-3
comment is explicit that the LLM may not originate a number — the same reasoning
covers an identifier. `check` verifies numbers against the packet, and it cannot
verify a slug that is not in the packet. So the mapping is the catalog's job: it is
local knowledge about which published name denotes which lane model, it belongs
next to the lane, and a human should be able to see and correct it.

`bench.py` already faces this and solved it: `split_model_version` and
`model_matches_slug` reconcile AA's effort-suffixed slugs against catalog models.
Read those before inventing anything.

**Blocked by:** nothing. Note `effort.py` was being edited on 2026-09-10 for packet
chunking (a 656KB Artificial Analysis packet against agy's ~128KB prompt cap); land
that first or expect a conflict.

**Status:** landed 2026-09-10 on `bench-aa-effort-slugs`. Found the same day while
extracting Terminal-Bench to close the coverage gap.

- [x] A row whose model is a published display name is matched to the catalog lane it denotes
- [x] The mapping is data a human can read and correct, not a guess inside the extractor
- [x] `check` still verifies every number against the packet; no identifier is originated by a worker
- [x] The pre-screen proposes `astra-xhigh@codex` off against `_data/tbench-accepted.json`, for the stated reason
- [x] A published name with no catalog lane is ignored without a warning storm — Terminal-Bench lists GLM-5.3, Opus 4.8, Sonnet 5 and others that are nobody's lane
- [x] `tests/test_effort.py` or `tests/test_setup_tui.py` covers the match from a fixture, with no network

## Landed 2026-09-10

The mapping is `catalog.py`'s, in two parts. The derived part: a printed name
matches a lane model when they differ by formatting alone — case and the `-_. `
separators — reaching past the effort suffix some slugs carry, so
`GPT-6 Astra` → `gpt-6-astra` and `Gemini 3.8 Flash` → `gemini-3.8-flash-high`
need no configuration. The written part: the optional lane field `published_as`,
a list of the names sources print for that lane's model, which wins over the
derived rule and is the only way across a gap formatting cannot bridge —
`Fable 5.1` → `claude-fable-5-1`. `resolve_published_model(name, lanes_doc)`
returns the slug or `None`, and returns `None` rather than guessing when two
lane models could equally be meant. `validate_lanes` rejects one published name
claimed by two different models, naming both.

Review caught a hole in the first cut, and it was the same hole the ticket is
about, pointing the other way: the explicit map is read first, so
`"published_as": ["gpt-5.6-luna"]` typed on `sol-high@codex` passed validation
and read luna's rows as sol's — luna would report "no rows" while its own
numbers switched sol off as dominated. `validate_lanes` now refuses an entry
that names a model another lane runs, in either spelling, so the explicit map
can no longer contradict the derived rule. The first cut's own test had asserted
that precedence as intended behaviour; it now asserts the rejection.

Nothing was added to the extractor and `check` is untouched: `accepted.json`
still carries the name the page printed, and the reconciliation happens where
the rows are consumed. `bench.py` lost its private copies of `normalize_name`
and `strip_effort_suffix` and imports the catalog's.

The pre-screen re-keys each row through the catalog before comparing, drops rows
naming no lane model, and prints the dropped names on one capped line —
`no lane runs these, ignored: Fable 5.1, Opus 5, Fable 5, GLM-5.3 +4 more`. That
line is the point: a lane reading "no rows" while its model sits in the file is
the bug this ticket is, and one line a human can scan is what catches the next
missing `published_as`. It replaced no per-lane warning, so there is no storm.

Measured against the real `_data/tbench-accepted.json` (18 rows) with the live
catalog plus the four missing astra lanes:

    astra-low@codex     on   not dominated
    astra-medium@codex  on   not dominated
    astra-high@codex    on   not dominated
    astra-xhigh@codex   off  dominated by high of the same model
    astra-max@codex     on   not dominated

`stow/delegate/.config/delegate/lanes.json` gained the one entry the derived
rule cannot reach — `"published_as": ["Fable 5.1"]` on `fable-xhigh@claude`
(Orin, 2026-09-10). The live `~/.config/delegate/lanes.json` was left alone: it
is a regular file that nothing propagates to, and which of the two catalogs is
authoritative is still open, so writing to both would have answered that
quietly. The stowed catalog now differs from the live one by this field as well
as by `sol-high@codex`'s tier.

With that entry the Terminal-Bench `Fable 5.1` row attaches to
`claude-fable-5-1` and leaves the ignored line. `fable-xhigh@claude` still reads
"no rows for this lane", and correctly: the one Fable row is at `max` and the
lane runs `xhigh`. `Fable 5` stays ignored — it is the older model, nobody's
lane.

Tests: 22 new assertions in `tests/test_catalog.py` (validation, the collision,
and resolution including the ambiguous and the unknown name) and 6 in
`tests/test_setup_tui.py`, the latter against
`tests/fixtures/tbench-accepted.json`, a copy of the accepted extraction.

## Verified in the wizard 2026-09-10

Driving the real curses wizard on a pty — throwaway config dir seeded from the
live catalog plus the four missing astra lanes, fed `_data/tbench-accepted.json`
— exits 0 and writes a catalog that differs from the seed by one line:
`"enabled": false` on `astra-xhigh@codex`. So a display name in a packet now
reaches a written catalog decision. `published_as` survives the round trip.

Two defects were found by running it, both fixed on this branch:

- `--effort-rows` was read only in the TUI branch, so under `--plain` or any
  pipe it was accepted and ignored in silence (`4d08244`).
- At 80 columns the `why` column was not truncated but dropped entirely, so the
  pre-screen switched a lane off and gave no reason at the width the file
  targets (`b530b89`, which also faceted the benchmark page: fourteen series
  shared six colours and the astra pair plotted 5px apart with overprinted
  labels).

Suite 347 assertions, 0 failures. Still outstanding, and Orin's: the four astra
lanes exist in no catalog, so a live run cannot reproduce the finding until they
are added.
