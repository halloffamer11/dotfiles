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

- [x] `rank.py impl` on the sample catalog prints terra first, with sol and grok listed and each lane carrying a reason (ceiling, gate, stolen by pace, or eligible) — **amended 2026-09-10: grok first, not terra; see the decisions below**
- [x] A lane below the class tier is listed as vetoed by ceiling, never picked
- [x] A lane whose meter is under the gate is vetoed by gate
- [x] A higher-tier lane ahead of pace by the margin steals the pick and says so
- [x] Unknown meter status sorts last and the command still returns a pick
- [x] When every lane is vetoed the command exits non-zero with the reasons
- [x] Tests run the prototype cases against stubbed meters; no network in tests

## Decisions 2026-09-10

**q1a — `trust` is removed entirely.** The sort key loses its middle term. The
rule above becomes:

```
need = classTier[class]
eligible = lanes with tier >= need, meter remaining >= gate, harness CLI present
sort eligible by (tier asc, pace desc, lane name asc)
pick = eligible[0]
for L in eligible[1:]:
    if pace(L) >= pace(pick) + margin: pick = L
```

Ties inside a tier are broken by pace, then by lane name ascending. Two lanes
alike on tier and pace are equivalent, so the last term is an arbitrary factor
chosen only to keep the pick deterministic — not a judgement, and not a place to
smuggle trust back in as file order. Drop trust from the reason strings and from
the report columns as well. This supersedes "plus trust" and "the most trusted lane inside a tier
serves" above.

### Two consequences found while implementing, 2026-09-10

**The default `impl` pick changed from terra to grok.** Terra led tier 2 on
trust 5 against grok's 3, while grok led on pace. With trust gone, pace decides
and grok is picked on the healthy-meter fixture. Acceptance criterion 1 above is
amended to match. This is the rule working as decided, not a defect: there is now
no way to express "inside tier 2, prefer terra over grok" except by moving one of
them to another tier.

**A steal can no longer happen inside a tier.** Sorting is `(tier asc, pace
desc)`, so `eligible[0]` already holds the highest pace of the lowest eligible
tier; nothing behind it in the same tier can out-pace it. The margin rule
therefore only ever fires across tiers. It is not dead — case 3 still steals from
tier 2 to tier 4 — but the "stolen by pace" reason can no longer appear between
two lanes of one tier. `rank.py` case 2 was rewritten to assert this.

**q1b — no class defaults to tier 4, and that is by design.** No class in
`routing.classTier` maps to 4; the highest default is `hard-impl` at 3, so
ranking never asks for tier 4 on its own. Tier-4 lanes are still in the catalog
and stay eligible for any lower need, since the ceiling is `tier >= need`. Tier
4 is reached only when the human raises the need by prompting, for example
"/delegate and increase tiers +1 for this work since it is critical" or
"/delegate and use tier 4 models for hard implementation or research tasks".
Do not raise a class tier to 4 to make a ranking case pass.
