# 15 — One lane per effort level, and a way to switch lanes off

**What to build:** Today one model appears once, at one effort chosen when the lane was authored — `luna-low@codex` exists and `luna-medium@codex` does not, so the medium setting is unreachable without hand-editing the catalog. Orin wants every effort level a harness offers to be its own lane, and a way to switch off the ones he does not want in play.

`codex debug models` reports six efforts for `gpt-6-astra`, `gpt-5.6-sol` and `gpt-5.6-terra` (`low, medium, high, xhigh, max, ultra`) and five for `gpt-5.6-luna` (no `ultra`), confirmed 2026-09-09. Enumerating them turns six lanes into roughly thirty. That is fine for ranking, which is a sort, but it makes the wizard's tier screens long and most of those rows will never be used — hence the switch.

**Lane identity stays honest.** The effort is in the key (`luna-low@codex`), so one lane per effort keeps the key matching its contents. This is why effort must not become an editable field on an existing lane: editing it would either make every log line name a lane that lies, or force a key rename mid-wizard. Enumerate instead.

**What the research settled** (`../research/2026-09-09-effort-data-sources.md`).
Published per-effort data exists with cost for `low` through `max` — Artificial
Analysis, CursorBench, ARC Prize and four others — but **no source reports
`ultra`**, on any benchmark, for any model. It exists only on the Codex CLI
surface; the API enum that benchmark harnesses drive runs `none` to `max`, so
every published sweep also carries a `none` row that no lane can select. On top
of that, `ultra` is "maximum reasoning with automatic task delegation", which
contradicts the worker preamble's "do not delegate, spawn subagents, or call
other agents". So the three `ultra` lanes are unscoreable *and* would break the
return contract by construction: **generate them with `enabled: false`.**

That turns `enabled` from a convenience for shortening wizard screens into the
mechanism that keeps an unscoreable lane out of the ranking, which is why the
default matters and cannot simply be true for everything.

Reasoning effort does not change the token rate — it changes token volume — so
all of a model's per-effort lanes share one identical `price` block.
`meter_weight` is the only field that genuinely varies per effort, and no
published source can ever supply it: it is a property of the plan, not the
model.

**An `enabled` field** on each lane, defaulting to true. `rank.py` treats a disabled lane as ineligible with reason `disabled`, alongside the existing ceiling and gate reasons, so `--dry-run` still explains itself. `catalog.py` validates it as a boolean. The wizard toggles it, and disabled lanes are dimmed on the tier screens rather than hidden — a lane you switched off should stay visible enough to switch back on.

Generating the lanes is `discover.py`'s job (ticket 13): it already lists every model each harness offers, and knows which have no lane. Extend it to emit a lane stanza per effort for a named model, printed for the human to paste, not written to the catalog. Meter, weight, timeout and price still need a human.

**The data question is answered** (`../research/2026-09-09-effort-data-sources.md`, and
`agents/skills/delegate/assets/sources.json` for the approved sources). Three sources carry
score-and-cost by effort for catalog models: SWE Refactor Bench, Artificial Analysis, and
Terminal-Bench 4.0. `scripts/effort.py` extracts them — `pack` is deterministic and proven against
all three live pages, `check` rejects any number not on the page.

**The pipeline is proven end to end, 2026-09-09.** One `extract` run against the SWE Refactor Bench
packet on `flash-high@agy` (121s, run `20260910T015628Z-flash-high@agy-940185dd`) returned 26 rows;
`check` accepted 26 and rejected 0. Those 26 are every per-effort label the packet carries, and the
twelve catalog rows — `gpt-5.6-sol` and `gpt-5.6-luna`, `none` through `max` — match the page value
for value. All 26 came back `unlabelled`, which is the honest answer: swerb publishes no provenance
badge. So there is now structured score-and-cost data to set tier from.

`extract` could not run at all before this: it invoked a bare `delegate.py`, which is on nobody's
PATH. It now resolves the sibling script beside `effort.py` and falls back to PATH.

**And one field this can never answer.** `meter_weight` is a property of the ChatGPT Plus plan, not
of the model. No benchmark reports it. Those ~30 values stay hand-set or locally measured whatever
the research says.

## Decision 2026-09-10 — what the pre-screen is

CLAUDE.md referred to "the ticket-15 pre-screen" as settled, but this ticket
never defined it and no other file did either. Confirmed by Orin 2026-09-10:

**The pre-screen is a narrowing pass that runs before the tier screens.** It
takes the ~30 enumerated per-effort lanes and proposes which ones are worth
carrying, by running `effort.py` over the approved sources and setting
`enabled` from what it finds. Thirty tier rows is unusable, and this ticket
already says the `enabled` default "cannot simply be true for everything" — the
pre-screen is what decides it. `ultra` lanes are the settled case: unscoreable
by any source and in breach of the worker preamble, so `enabled: false` by
construction.

It proposes; the human disposes. The pre-screen never writes the catalog on its
own — its output is the starting mark state on the tier screens, which the human
overrides with the toggle. Orin ruled on 2026-09-10 that there is no constraint
on what it may write (see CLAUDE.md), since `lanes.json` carries nothing
sensitive.

**Blocked by:** 13 (discovery), 12 (the wizard screens this adds a toggle to).

**Status:** open, raised by Orin 2026-09-09: "we should have each level. so luna-low, luna-med, luna-high would all be lanes. add an option to disable or turn off certain lanes."

- [ ] `enabled` is a validated boolean on every lane, defaulting to true when absent so existing catalogs keep working
- [ ] `rank.py` reports a disabled lane as ineligible with reason `disabled`, and never picks one
- [ ] The wizard toggles `enabled` on the cursor row and shows disabled lanes dimmed, not hidden
- [ ] `discover.py --efforts <model>` prints a ready-to-paste lane stanza per effort the harness reports
- [ ] A generated `ultra` stanza carries `enabled: false`, with the reason in its `basis`
- [ ] `discover.py --efforts` emits one shared `price` block across a model's efforts, not a prompt per lane
- [ ] `tests/test_rank.py` covers a disabled lane that would otherwise be the pick
- [x] `effort.py extract` completes one real run end to end, so the pipeline is proven, not half-proven
- [ ] A pre-screen runs before the tier screens, proposes `enabled` per lane from `effort.py` output, and sets the starting mark state rather than writing the catalog
- [ ] Orin enumerates the codex efforts he wants and switches off the rest in one wizard run
