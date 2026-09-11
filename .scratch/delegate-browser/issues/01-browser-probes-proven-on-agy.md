# 01 — Browser probes, proven on agy with a disposable browser

**What to build:** A repeatable answer to "can this harness's workers use a browser when delegate sends them?", on whichever machine runs it. Two probe briefs and a runner that sends them through the normal delegate dispatch path, once per harness, and prints a PASS/FAIL table. It is proven first on agy, which already has Playwright and its tool grants on the Mac, so no relay change is needed to see a pass.

Orin's goal: the dispatch path must not block a browser that a harness already has. No new config file, flag, detection or ranking change. Terms, decisions, setup rules and the facts behind this ticket: `../research/2026-09-10-browser-routes.md`. The v1 probes to build from are in tag `delegate-v1-last`.

**Blocked by:** None — can start immediately.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] Disposable probe: the worker reads a page title, then submits the `httpbin.org/forms/post` form and reports the value the response echoes back. The brief forbids web fetch, curl and built-in web tools, so a pass proves the browser was used, and it ends in an exact PASS or FAIL marker.
- [ ] Agent-profile probe: the worker reports the signed-in account name shown at `facebook.com/marketplace` and clicks nothing that changes state. Exact PASS or FAIL marker.
- [ ] The runner dispatches each probe through the normal dispatch path, once per harness, from a temporary working directory, and prints one table per machine: harness, CLI version, probe, PASS/FAIL, and a one-line reason. A harness with no CLI or no browser shows FAIL with its reason; nothing else changes.
- [ ] The runner forces low effort where the lane accepts an effort. This matters for claude, whose only lane is on the orchestrator meter. agy's effort is fixed by its model.
- [ ] The worker preamble allows reads and writes in a disposable browser only. Every other network write stays forbidden.
- [ ] The prompt for agy read-only runs no longer says "Use the file tools only". It permits browser tools, and its terminal rule matches what the current relay does.
- [ ] Dispatch tests cover both prompt changes. All delegate tests pass.
- [ ] The delegate skill's Health section says how to run the probes.
- [ ] Proof on the Mac: the agy row passes the disposable probe. The first full table is pasted into this ticket as the baseline for 02–04. Agent-profile rows are expected to fail until 06.
