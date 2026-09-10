# 08 — Cost in the report

**What to build:** `report.py` shows what each dispatched job cost. From the lane's price record and the run's token counts it derives dollars per job, and from the meter's plan price and weight it shows the share of the monthly subscription consumed. Where a relay reports no tokens (Codex today) the row says unmeasured rather than zero. The report stays a plain terminal table and the ledger schema is unchanged so the TUI keeps working.

**Blocked by:** 01 Lane catalog and validators; 03 One run through an ADS relay.

**Status:** landed 2026-09-09 in the working tree (uncommitted)

- [x] A Grok run with reported usage shows an input, output, and total dollar figure that matches the catalog price by hand
- [x] A Codex run shows unmeasured, not zero
- [x] A meter summary row shows plan, monthly price, and share consumed this cycle
- [x] Existing report tests still pass and the TUI renders the same ledger
