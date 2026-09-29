# 39 — A percent of one Meter is not a percent of another

**What to decide:** Pace compares fractions across Meters, as if 1% of Claude's week
were the same work as 1% of codex's or grok's. It is not, and a plan change moves it:
going from Codex Pro to Codex Plus shrinks what 100% of the codex Meter buys. The Meters
are different currencies and need a conversion factor, so that Pace, and the steal that
compares it, compare like with like. Raised by Orin 2026-09-27: "Let's not add that in
now, but put that in the backlog."

What exists today:
- `meter_weight` is set on each Lane and is "a property of the plan, not the model"
  (`discover.py`). It is unmeasured on the generated Lanes (ticket 37, item 3), and
  `rank.py` does not read it.
- The codex probe already reports its plan in the Meter note (`plan=prolite`), a
  possible key for a factor per plan.

**Blocked by:** None — can start immediately.

**Status:** needs-triage

- [ ] Orin decides the common unit, and how each Meter's factor is set and updated when
      a plan changes.
- [ ] Ranking compares converted quota, and a plan change needs only its factor changed.
