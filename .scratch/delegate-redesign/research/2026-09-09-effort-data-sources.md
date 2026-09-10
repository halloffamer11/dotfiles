# Per-effort benchmark data: what exists, 2026-09-09

Research for ticket 15 (one lane per effort level). The question was whether
published data covers model x reasoning-effort with cost, well enough to set
`tier`, `trust` and `meter_weight` for the ~30 lanes enumeration produces.

Four workers ran this: `sol-high@codex` swept the field, `terra-high@codex`
dug into two named benchmarks, `grok46-high@grok` swept recent prices and
announcements, and `flash-high@agy` independently re-fetched terra's URLs to
verify its figures. Run artifacts are under `~/.cache/delegate/runs/` dated
`20260909T2109*` and `20260909T2113*`.

## Answer: yes for low-max, never for ultra

## Sources that report effort x cost for catalog models

| Source | Effort sweep | Cost | Catalog models | Access |
|---|---|---|---|---|
| Artificial Analysis | yes | $/task + tokens | all seven | HTML; export API is commercial |
| CursorBench | yes, low-max | avg $/task + tokens | six, no astra | HTML only |
| ARC Prize | yes, five levels | $/task and totals | six incl. astra | HTML; replays as JSON |
| DeepSWE | yes, astra low-max | avg cost, tokens, steps | six | HTML, client-rendered |
| DataBench | yes, four levels | $/task + tokens | sol, terra, luna | HTML only |
| Terminal-Bench 2.1 | astra only | job cost + tokens | astra, terra, luna | HTML |
| SWE Refactor Bench | yes, none-max | $/task | sol, luna | HTML |
| VISTA | no, one effort per row | tokens, $, wall-clock | sol, terra, luna, grok | HTML; dataset gated |
| LiveBench / Epoch / LMArena | no controlled sweep | partial | most | **machine-readable** |
| Aider, SWE-bench, SWE-Lancer | no | no | none by exact name | - |

The pattern that matters: the sources with the data are HTML-only or
commercial, and the three properly machine-readable sources are exactly the
ones with no controlled effort sweep. Per-effort scoring is hand
transcription with a date stamp, not a feed. Do not extend `bench.py` to
chase it.

## Three findings that constrain ticket 15

**1. No source reports `ultra`.** Confirmed twice over: sol found no `ultra`
row on any of twelve sources, and grok established why - `ultra` exists only
on the Codex CLI surface, never in the API enum that benchmark harnesses
drive. Add that `ultra` is described as "maximum reasoning with automatic
task delegation", which contradicts the worker preamble's "do not delegate,
spawn subagents, or call other agents", and the three `ultra` lanes are both
unscoreable and contract-violating.

**2. Published effort labels are the API enum, not the CLI enum.** Every
sweep found runs `none -> max`. The codex CLI offers `low -> ultra`. So each
published sweep carries a `none` row no lane can select, and omits the one
level we most need. Verified locally with `codex debug models`:

| Model | CLI efforts | Count |
|---|---|---|
| gpt-6-astra | low, medium, high, xhigh, max, ultra | 6 |
| gpt-5.6-sol | low, medium, high, xhigh, max, ultra | 6 |
| gpt-5.6-terra | low, medium, high, xhigh, max, ultra | 6 |
| gpt-5.6-luna | low, medium, high, xhigh, max | 5 |

This confirms ticket 15's counts for astra, sol and luna, and settles the
open question on terra at six.

**3. Effort does not change the token rate.** Effort changes token volume.
All of a model's per-effort lanes therefore share one identical `price`
block, so `discover.py --efforts` can emit it rather than asking a human ~30
times. `meter_weight` is the only genuinely per-effort field, and no
published source can supply it - it is a property of the plan, not the model.

## Verified figures

`flash-high@agy` re-fetched all nine of terra's URLs: 8 of 8 claims VERIFIED,
including both sweeps checked digit by digit.

SWE Refactor Bench, gpt-5.6-sol, score / $ per task, `none` to `max`:
4.0/$2.9, 7.0/$5.9, 6.5/$6.0, 19.0/$7.7, 9.5/$19.1, 28.5/$143.5.
gpt-5.6-luna: 4.0/$1.6, 4.0/$1.7, 0.0/$1.7, 4.0/$1.8, 5.5/$2.9, 10.5/$2.8.

Caveat that survives verification: 20 runs per configuration, and "accepted"
means six verifiers found no counterexample, not that the migration is
correct. At that sample size sol's xhigh dip and luna's zero at medium are as
likely noise as signal. Use SWE-RB for the shape of the cost curve; use
Artificial Analysis's monotonic sol curve (28/34/39/42/44/47 at
-/$0.26/$0.50/$0.81/$1.18/$1.99 per task) for scoring.

## Token prices, read off the vendor pages 2026-09-09

Verified directly against developers.openai.com, not via a worker:

| Model | in | cached in | cache write | out |
|---|---|---|---|---|
| gpt-6-astra | 10.00 | 1.00 | 12.50 | 50.00 |
| gpt-5.6-sol | 4.00 | 0.40 | 5.00 | 20.00 |
| gpt-5.6-terra | 2.00 | 0.20 | 2.50 | 12.00 |
| gpt-5.6-luna | 0.20 | 0.02 | 0.25 | 1.20 |

Sol's is promotional at least through 2026-11-21. Long-context tiers roughly
double. The catalog's existing sol and terra entries match these exactly,
which is a useful check on both.

## Name hazard

DeepSWE, DataBench, Terminal-Bench and VISTA all label the Anthropic row
`Fable 5`, not `claude-fable-5-1`. Four boards, one ambiguous name. Do not
let that equivalence be assumed into a trust score.
