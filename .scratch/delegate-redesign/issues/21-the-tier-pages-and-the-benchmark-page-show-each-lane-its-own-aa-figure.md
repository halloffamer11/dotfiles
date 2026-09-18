# 21 — The tier pages and the benchmark page show each lane its own AA figure

**What to build:** `bench.py` reads Artificial Analysis from the per-effort rows
ticket 18 produces, so the `lanes` view holds a figure for every lane at its own
effort. The tier pages and the HTML benchmark page render those columns, and no
lane prints "used effort medium (lane effort high)" any more. The free API path
and the key it needs are deleted from the report.

**Why.** The free API returns one entry per model per effort, but only 200 entries
on the first page, with a pagination key `bench.py` does not follow; on
2026-09-11 that page held 11 of the 31 catalog variants. `build_aa_section` then
keeps the one entry nearest the lane's effort and drops the rest. The report of
2026-09-10 shows the result: every Artificial Analysis figure is attributed with
a caveat, and `flash-high@agy` has none at all. Ticket 17's rule
(`effort_attributes`) already keeps only the figures measured at a lane's own
effort; with per-effort rows it has a figure for every lane instead of one per
model.

The free API's evaluations are three composite indexes. The page payload carries
the component scores (Terminal-Bench 2.1, AutomationBench, AA-LCR, IFBench,
Omniscience, GPQA Diamond, GDPval, MMMU-Pro), so the report's AA columns can be
component scores, as the sources file asks.

**Blocked by:** 18 Artificial Analysis rows come from the page's own JSON, not
from a worker.

**Status:** closed 2026-09-12, folded into ticket 19. The boxes below stay unticked here; they are tracked in ticket 19.

- [ ] `bench.py collect` takes the AA rows file and fills the `lanes` view with one figure per lane per AA column, measured at that lane's effort; the `models` view keeps one figure per model per column for comparison against models nobody runs
- [ ] The AA columns in the report, the tier pages and the HTML page are component scores, with cost per task beside them; the composite index is not a column
- [ ] The report's notes list no "used effort X (lane effort Y)" line for Artificial Analysis, because every figure is at the lane's effort
- [ ] The free API fetch, `AA_URL`, `load_key` and the key-file argument are removed from `bench.py`; the AA key at `~/.config/delegate/aa-key` is no longer read by anything, and the project `CLAUDE.md` says so
- [ ] Epoch AI handling is unchanged and its tests still pass
- [ ] The benchmark page opened from the wizard's `o` key shows the per-effort AA points for one model as one series
