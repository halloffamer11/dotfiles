# 29 — A Range served by one Meter stops the Class

**What to decide, then build:** what `/delegate` does when every Lane inside a Class
Range is vetoed by the Gate, and how the catalog tells Orin that a Tier depends on one
Meter. Raised by Orin 2026-09-18.

**Blocked by:** None — can start immediately.

## Evidence, 2026-09-18

`delegate.py run scout` printed `STOP: no lane eligible for scout`. The `scout` Range is
Tiers 1–2. The carried Lanes in those Tiers were `luna-high@codex` (Tier 1) and
`luna-max@codex`, `luna-xhigh@codex`, `terra-high@codex` (Tier 2): four Lanes, one Meter.
The `codex` Meter had 1% Remaining against a Gate of 5%, reset 2026-09-23. Every other
Tier 1–2 Lane is off. Carried Lanes on four other Meters were healthy, all in Tier 3 or 4:
`vetoed:ceiling`. `mechanical` has the same Range and the same exposure; `impl` and
`review` (Range 2–3) lose their floor Tier but still run.

Orin chose a named dispatch to `flash-high@agy` (Tier 3) and said it is acceptable for
that job. His framing: either (a) each Tier carries one Lane per Harness or Meter, or
(b) an exception mechanism admits a Lane when no in-Range Lane is inside its usage
limits. He also said agy is a workhorse that the Gate, Meter and ranking rules do not
use fully.

## Why agy is underused today (verified in the rank output and ticket 13 of
`.scratch/delegate-modular/`)

1. Both carried agy Lanes are Tier 3, so `scout` and `mechanical` never see them.
2. agy Remaining and Pace are reported unknown by decision (modular ticket 13: the 5-hour
   and weekly windows have no joint bound). An unknown Pace can never win a Margin steal.
   In Tier 3 the Order is grok, `flash-high@agy`, `opus-high@claude`; a measured Lane with
   a high Pace steals from grok, and agy cannot. agy runs only when the Lanes ahead of it
   are vetoed, or by name.

## Options

**A. Coverage in the catalog, and a warning.** No new routing rule. Orin carries Lanes
on a second Meter in Tiers 1 and 2. agy fits without a rule change, because each agy
effort is its own model and so its own Lane: `flash-low`, `flash-medium` and `flash-high`
can sit in three Tiers. `catalog.py check` and the wizard's review page warn when the
carried Lanes of one Tier all drain one Meter ("Tier 2 depends on Meter codex").

**B. Overflow past the ceiling.** When every in-Range Lane is vetoed and each veto is a
Gate veto, admit the next Tier above the ceiling, one Tier at a time, and rank it as
usual. Never below the floor; never into Tier 4, which stays named-only. The rank header
prints `overflow: ceiling 2 -> 3, all in-Range Lanes under Gate`. A `routing.json` key
(`overflow`, boolean, project-overridable) turns it off. The reasoning: the floor guards
quality and the ceiling guards cost. A better Lane on an easy job costs usage; a stop
costs the job.

**C. A Lane reaches down.** A Lane declares the lowest Tier it serves. It is eligible
below its own Tier at all times, sorts after the in-Range Lanes, and may steal by Margin.
This spends high-Tier usage on low work whenever a Pace gap opens, and it needs a Pace
that agy does not have.

## Recommendation

A and B together; not C. A is the actual fix and needs only Orin's Tier choices. B makes
a Gate-only outage degrade to a higher Tier and not stop the session. C duplicates A for
agy and widens spend everywhere else.

The agy Pace question is separate and stays with modular ticket 13: a weekly-only Pace
for agy would let it take Margin steals. Reopen it only with Orin's word.

## Acceptance

**Status:** ready-for-agent

- [x] Orin chooses A, B, or both, and whether `overflow` defaults on. (Both, 2026-09-18.)
- [ ] `catalog.py check` and the review page warn when one Meter serves every carried
      Lane of a Tier; fixtures cover it; the check never judges Orin's Tiers.
- [ ] With overflow on, a Range whose vetoes are all Gate vetoes ranks the next Tier and
      says so in the header; any other veto mix still stops; Tier 4 is never admitted.
- [ ] `SKILL.md` and `CONTEXT.md` carry the new term and rule.
- [ ] `tests/test_rank.py` and `tests/test_catalog.py` pass.

## Decision, 2026-09-18

Orin: "both". A, the one-Meter warning, and B, overflow past the ceiling, are both built.
`overflow` defaults on: the purpose of B is that a Gate-only outage does not stop a
session, and a default of off would keep today's stop. That default is the session's
choice, not Orin's word; he may overrule it. The Tier coverage itself (which Lanes he
carries in Tiers 1 and 2) stays his, on the wizard's Tier pages. C is not built.
