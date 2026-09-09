# 01 — Lane catalog and validators

**What to build:** The two configuration files the redesign runs on. A global `lanes.json` holds meters and lanes (harness, model, effort, meter, meter weight, timeout, price, tier, trust, basis). A global `routing.json` holds class tiers, margin, and gate, and a project file under `.delegate/` overrides any key. One command prints the effective catalog for the current directory. A broken file is rejected with a plain-language message that names the field and the rule. Files are formatted on write. The starting catalog from spec section 3 ships as the sample the setup wizard later edits.

Tier and trust values are human-set. Nothing in this ticket computes them.

**Blocked by:** None — can start immediately.

**Status:** landed 2026-09-09 in the working tree (uncommitted)

- [x] The sample catalog from the spec loads and prints without error
- [x] A lane that names a missing meter, a tier outside 1..4, or a trust outside 1..5 is rejected with a message naming the lane and the rule
- [x] An unknown top-level or lane field is rejected, not ignored
- [x] A project routing file with one key overrides only that key; the rest falls back to global
- [x] `note` fields are accepted everywhere and ignored by logic
- [x] Tests cover each rejection and the override merge
