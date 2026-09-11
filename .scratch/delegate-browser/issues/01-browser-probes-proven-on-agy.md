# 01 — Browser probes, proven on agy with a disposable browser

**What to build:** A repeatable answer to "can this harness's workers use a browser when delegate sends them?", on whichever machine runs it. Two probe briefs and a runner that sends them through the normal delegate dispatch path, once per harness, and prints a PASS/FAIL table. It is proven first on agy, which already has Playwright and its tool grants on the Mac, so no relay change is needed to see a pass.

Orin's goal: the dispatch path must not block a browser that a harness already has. No new config file, flag, detection or ranking change. Terms, decisions, setup rules and the facts behind this ticket: `../research/2026-09-10-browser-routes.md`. The v1 probes to build from are in tag `delegate-v1-last`.

**Blocked by:** None — can start immediately.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [x] Disposable probe: the worker reads a page title, then submits the `httpbin.org/forms/post` form and reports the value the response echoes back. The brief forbids web fetch, curl and built-in web tools, so a pass proves the browser was used, and it ends in an exact PASS or FAIL marker.
- [x] Agent-profile probe: the worker reports the signed-in account name shown at `facebook.com/marketplace` and clicks nothing that changes state. Exact PASS or FAIL marker.
- [ ] The runner dispatches each probe through the normal dispatch path, once per harness, from a temporary working directory, and prints one table per machine: harness, CLI version, probe, PASS/FAIL, and a one-line reason. A harness with no CLI or no browser shows FAIL with its reason; nothing else changes. *Open:* since ticket 22, a claude lane dispatched from a Claude session prints a native spawn line and starts no relay, so the runner cannot run the claude row and would report `dispatch failed` for a reason unrelated to browsers.
- [x] The runner forces low effort where the lane accepts an effort. This matters for claude, whose only lane is on the orchestrator meter. agy's effort is fixed by its model.
- [x] The worker preamble allows reads and writes in a disposable browser only. Every other network write stays forbidden.
- [x] The prompt for agy read-only runs no longer says "Use the file tools only". It permits browser tools, and its terminal rule matches what the current relay does.
- [x] Dispatch tests cover both prompt changes (cases 32 and 33 after the merge of `main`). All delegate tests pass.
- [x] The delegate skill's Health section says how to run the probes.
- [ ] Proof on the Mac: the agy row passes the disposable probe. The first full table is pasted into this ticket as the baseline for 02–04. Agent-profile rows are expected to fail until 06. *The agy half is done (below); the full table waits on the claude row and on codex quota.*

## Proof, 2026-09-11 (Mac, agy only)

Built by run `20260911T185952Z-flash-high@agy-dbd98231`, reviewed and fixed by the lead (commits `9283367`, `b445ecb`), and merged with `main` (`14b76fd`). `python3 scripts/browser_probes.py --only agy`:

| harness | CLI version | probe | PASS/FAIL | reason |
|---|---|---|---|---|
| agy | 1.2.1 | disposable | PASS | title=Example Domain echoed=3de1a2fdc75c |
| agy | 1.2.1 | agent-profile | FAIL | Agent browser profile via browser extension is not available or supported in Antigravity CLI. |

hostname: Orins-MacBook-Pro.local · 2026-09-11 20:17 UTC · lane `flash-high@agy`, read-only.

Evidence the disposable pass used a browser (run `20260911T201523Z-flash-high@agy-c807cf76`, 42 s): Playwright left three page snapshots in the probe's temporary directory — `example.com` with heading "Example Domain", the httpbin form with its "Customer name" box, then httpbin's JSON echo with `"custname": "3de1a2fdc75c"`, the run's nonce.

Follow-ups found in the proof:

- The runner grades the worker's own marker, and the nonce is in the brief, so a worker could report it without submitting the form. Today the Playwright snapshots are the only proof. A later change could have the runner look for the nonce in the snapshots.
- agy's `playwright` server is `npx -y @playwright/mcp@latest` with no `--isolated` and no output directory, so it does not yet follow the setup rules in the research file.
