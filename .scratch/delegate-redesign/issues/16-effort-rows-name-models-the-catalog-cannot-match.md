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

**Status:** open, found 2026-09-10 while extracting Terminal-Bench to close the
coverage gap.

- [ ] A row whose model is a published display name is matched to the catalog lane it denotes
- [ ] The mapping is data a human can read and correct, not a guess inside the extractor
- [ ] `check` still verifies every number against the packet; no identifier is originated by a worker
- [ ] The pre-screen proposes `astra-xhigh@codex` off against `_data/tbench-accepted.json`, for the stated reason
- [ ] A published name with no catalog lane is ignored without a warning storm — Terminal-Bench lists GLM-5.3, Opus 4.8, Sonnet 5 and others that are nobody's lane
- [ ] `tests/test_effort.py` or `tests/test_setup_tui.py` covers the match from a fixture, with no network
