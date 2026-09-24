# 37 — Tier coverage and the Order inside a Tier

**Blocked by:** None — can start immediately.

**What to decide:** three open items, moved verbatim from the root `CLAUDE.md` on
2026-09-23. They are one decision space, Orin's: which Lanes each Tier holds, in what
Order, and what cost figure would decide it.

1. **Tier 1 depends on codex alone.** It holds only `luna6-high@codex`, and
   `catalog.py check` warns about that. When codex is under the Gate, `scout` and
   `mechanical` overflow to Tier 3 (ticket 29). The coverage is Orin's to set, in the
   wizard or per project.
2. **Order inside a Tier:** Orin's open question (capability against cost), not yet a
   ticket. The session's position (2026-09-22):
   - capability belongs in the Tier boundaries, and inside a Tier the cheapest Lane
     comes first;
   - Pace and Margin then spread the load;
   - the real cost is `meter_weight`, which is not measured; the page's "Price per
     model" chart shows only list price, as a stand-in.
3. **Unmeasured figures:** `meter_weight` and `timeout` on the generated Lanes are
   copies, and each Lane's note says `UNMEASURED` and names the source Lane. The grok and
   agy cache-write prices are not published.

The new Lanes are priced from
`.scratch/delegate-redesign/research/2026-09-22-new-model-prices.md`. The exception is
`grok47fast-high`, which has no published price.

**Status:** ready-for-human

- [ ] Orin sets Tier 1 coverage, in the wizard or per project.
- [ ] Orin answers the Order question, or makes it a ticket of its own.
