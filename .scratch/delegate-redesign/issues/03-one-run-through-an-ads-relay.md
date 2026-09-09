# 03 — One run through an ADS relay

**What to build:** The dispatch path. The four ADS relay skills (claude, codex, agy, grok) are installed and pinned at the recorded commit, called as pure executors with model, effort, timeout, read-only, and output directory flags, never with their lane or config. `delegate.py dispatch` builds the prompt (preamble, read-only or write clause, working directory, brief, return-schema request), allocates a fresh run directory that is never reused, writes the ledger start event, runs the relay, maps the relay status to done, partial, or blocked, parses the return block out of the final message, writes our `return.json`, writes the ledger finish event, re-probes meters, and prints one status line. Tests use a fake relay that can produce completed, failed, timeout, aborted, unavailable, and an empty agy reply.

The riskiest assumption in the design is a nested Claude run from inside Claude Code. It is smoke-tested here, first.

**Blocked by:** 01 Lane catalog and validators.

**Status:** landed 2026-09-09 in the working tree (uncommitted); items left unticked are Orin's

- [x] The ADS commit is recorded in the skill's context file and the install is reproducible from that record
- [x] Every run leaves a directory under the delegate cache that outlives the session, and two runs never share one
- [x] The brief reaches the relay byte for byte; no model rewrites it
- [x] Fake relay: timeout keeps partial output and maps to blocked with reason timeout; failed, aborted, and unavailable map to blocked with the relay error as reason
- [x] Fake relay: an empty agy reply is blocked with a reason, never done
- [x] A completed run with a valid return block maps to done or partial as the block says; a completed run with no block is partial with a reason
- [x] No run is bounded by a tool-call limit; the lane timeout is the only bound
- [x] Ledger events keep the existing schema and the TUI still renders them
- [x] Real smoke: one read-only run on the agy flash lane completes with a run directory
- [ ] Real smoke: one read-only run on a Claude lane completes from inside Claude Code (spec acceptance 8); Orin reviews the run directory and confirms the result before this ticket closes
