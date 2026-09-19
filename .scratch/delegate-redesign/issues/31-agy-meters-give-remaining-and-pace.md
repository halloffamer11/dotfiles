# 31 — agy Meters give a Remaining and a Pace

**What to build:** agy Meters report a combined Remaining and a Pace like every other
Meter, so the Gate applies to them, a Margin steal can go to them, and the status line,
`report.py limits` and the dashboard stop printing `unknown` for them. This reverses
`.scratch/delegate-modular/issues/13-agy-unknown-bound.md` (`fe4286c`).

**Blocked by:** None — can start immediately.

## Why

Modular ticket 13 made agy Remaining and Pace unknown "until a vendor joint bound
exists", after quota-axi's own refusal to publish one. The effect (ticket 29, evidence):
agy sorts last in its Tier, can never win a Margin steal, and is never under the Gate.
Orin, 2026-09-18, on seeing the dashboard's `no Meter reading` rows: "fix the agy meter,
gate, and usage monitor"; earlier the same day: "agy is a workhorse and tends to be
underutilized". That is his word to reopen ticket 13.

## Rule (session decision; Orin may overrule)

Treat an agy Meter as the Claude Meters are treated, which also have a 5-hour and a
weekly Window:

- Remaining is the lower of the two Window fractions. For the Gate this is the safe
  side: if the two Windows do not bind the same spend, the rule vetoes early, never late.
- Pace comes from the weekly Window and its reset time, by the same formula as the
  other Meters.
- The raw Window values stay visible. The note says the combined figure is the lower
  Window, an assumption, not a vendor bound.
- Known limit, not in scope: every Meter divides by a seven-day week (consultation
  item 2); an agy cycle that is not seven days skews Pace near its reset, as for grok.

## Scope

Paths relative to `agents/skills/delegate/`: `scripts/usage.py` (remove the agy
normalization: `_agy_unknown_combined`, `_normalize_agy_document`, their callers, the
`AGY_COMBINED_NOTE`), `scripts/rank.py` and `scripts/report.py` as needed,
`tests/test_usage_reset.py`, `tests/test_rank.py`, `tests/test_report.py`, the skill
`CLAUDE.md`, and the Pace, Remaining or Meter entry of the root `CONTEXT.md` if one names
the agy exception. A cached observation written under the old rule (Remaining and Pace
null, Windows present) must give the new figures with no fresh probe.

## Acceptance

**Status:** implemented 2026-09-18 (`50e8035`) on `worktree/delegate-redesign`; all boxes ticked. The merge to `main` is Orin's, and the rule is a session decision he may overrule.

- [x] A fresh and a cached agy observation with both Windows give Remaining = the lower
      fraction and a Pace; with one Window missing, the documented fallback of the other
      Meters applies.
- [x] An agy Lane under the Gate is vetoed `gate`; an agy Lane with the needed Pace wins a
      Margin steal; fixtures only, no live probe, and no test reads Orin's Tiers.
- [x] `report.py statusline` and `report.py limits` print agy figures, not `unknown`.
- [x] Every suite under `tests/` exits 0.
- [x] The Landed note records the live `rank.py scout` and `rank.py impl` Picks before
      and after, from the cached Meters.

## Landed, 2026-09-18

`50e8035`, by `opus-high@claude` (ranked `impl --tier 3`, a Margin steal from grok), run
`20260919T023415Z-opus-high@claude-6290a1c5`, about 900 s, verdict clean. `usage.combined()`
is now the one arithmetic for every Meter; the agy normalization is gone, and
`_fill_document()` derives the figures for a cache written under the old rule.

Checked by the session: all 13 suites under `tests/` exit 0. `rank.py impl` on the cached
Meters, before: `flash-high@agy pace=? r=? unknown meter, sorted last`; after:
`flash-high@agy pace=0.99 r=63% eligible`. The Pick is `opus-high@claude` both times. The
steal line changed from `1.349 >= 0.315 + 0.2` to `1.314 >= 0.993 + 0.2`: agy (Order 2) now
takes the job from grok (Order 1, Pace 0.32) and Opus takes it from agy. With Opus under
about 1.19, agy holds the Pick. The implementer reports the same for `scout`, and
`report.py statusline` prints `agy 5h 100%  wk 63%`.

Three effects the implementer flagged, accepted with the rule: a repaired cached
observation computes Pace at read time, so two reads differ slightly until the next probe
writes the figure; the Gate now reaches agy through the 5-hour Window, which is a rate
cap, so a nearly spent 5-hour Window is a new stop for agy; the seven-day divisor skews
the agy Pace when its cycle is not seven days (consultation item 2, still open).
