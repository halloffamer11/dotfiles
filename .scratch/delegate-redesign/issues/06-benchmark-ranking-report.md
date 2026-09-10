# 06 — Benchmark ranking report

**What to build:** `bench.py` pulls the Epoch AI CSV and the Artificial Analysis free endpoint, filters to the models named in the catalog, and writes a dated markdown ranking under the delegate cache with one mean-rank column per source and the columns named in spec section 8. The output is for Orin's eyes only: it is the input to setting tier by hand, and no skill, hook, or ranking code reads it. Known gaps (a model missing from a source, a score at max effort only) are printed as notes, not filled in.

**Blocked by:** 01 Lane catalog and validators.

**Status:** landed 2026-09-09 in the working tree (uncommitted); items left unticked are Orin's

- [x] Running `bench.py` writes one dated file under the cache directory with attribution lines for both sources
- [x] Only models present in the catalog appear; a catalog model missing from a source is listed with a gap note
- [x] The Artificial Analysis key is read from a file under the delegate config directory, never from the environment or the catalog
- [x] Without the key the Epoch columns still render and the report says which source was skipped
- [x] A grep of the skill, hooks, and ranking code finds no reference to the bench output path
- [ ] Orin reads one report and confirms it is enough to set tier from
