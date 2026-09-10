# 07 — Setup wizard

**What to build:** `/delegate setup` walks Orin through building or revising the catalog. It runs the ADS discovery script to find installed CLIs, proposes lane records from the current catalog and the installed harnesses, runs the benchmark report and shows it, then asks tier for every lane one at a time with the current value as default. It writes both configuration files only after a final yes. Tier never comes from a script; the wizard only presents evidence and records the human's answer.

**Blocked by:** 03 One run through an ADS relay; 06 Benchmark ranking report.

**Status:** plain-prompt wizard landed 2026-09-09 (commit 7c76843); Orin asked for a selectable TUI (best tier first, benchmarks beside each row, placed lanes de-emphasized below): rebuild in flight on sol-high@codex, brief in the session scratchpad as brief-ticket-07b.md

- [x] With no catalog present, the wizard proposes lanes for every installed harness and writes a valid catalog after yes
- [x] With a catalog present, the existing tier is the default and a plain enter keeps it
- [x] The benchmark ranking is shown before the tier questions, and the wizard never pre-fills a tier from it
- [x] Answering no at the end writes nothing
- [x] The written files pass the validators from ticket 01 and are formatted
- [ ] Orin runs the wizard once on this machine and confirms the resulting catalog
