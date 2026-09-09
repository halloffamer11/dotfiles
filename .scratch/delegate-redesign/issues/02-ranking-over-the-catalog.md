# 02 — Ranking over the catalog

**What to build:** `rank.py <class>` reads the catalog, the effective routing, and the live meters, applies the selection rule, and prints the ordered lanes with one reason per lane. When no lane is eligible it stops with the reason. The rule, taken from the prototype (policy P4 plus trust):

```
need = classTier[class]
eligible = lanes with tier >= need, meter remaining >= gate, harness CLI present
sort eligible by (tier asc, trust desc, pace desc)
pick = eligible[0]
for L in eligible[1:]:
    if pace(L) >= pace(pick) + margin: pick = L
```

A meter whose probe returns unknown sorts last and never blocks. The cheapest allowed tier serves by default, the most trusted lane inside a tier serves, and a lane ahead of pace by the margin steals the job.

**Blocked by:** 01 Lane catalog and validators.

**Status:** landed 2026-09-09 in the working tree (uncommitted)

- [x] `rank.py impl` on the sample catalog prints terra first, with sol and grok listed and each lane carrying a reason (ceiling, gate, stolen by pace, or eligible)
- [x] A lane below the class tier is listed as vetoed by ceiling, never picked
- [x] A lane whose meter is under the gate is vetoed by gate
- [x] A higher-tier lane ahead of pace by the margin steals the pick and says so
- [x] Unknown meter status sorts last and the command still returns a pick
- [x] When every lane is vetoed the command exits non-zero with the reasons
- [x] Tests run the prototype cases against stubbed meters; no network in tests
