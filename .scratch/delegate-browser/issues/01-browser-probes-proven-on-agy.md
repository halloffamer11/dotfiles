# 01 — Browser probes, proven on agy with a disposable browser

**What to build:** A repeatable answer to "can this harness's workers use a browser when delegate sends them?", on whichever machine runs it. Two probe briefs and a runner that sends them through the normal delegate dispatch path, once per harness, and prints a PASS/FAIL table. It is proven first on agy, which already has Playwright and its tool grants on the Mac, so no relay change is needed to see a pass.

Orin's goal: the dispatch path must not block a browser that a harness already has. No new config file, flag, detection or ranking change. Terms, decisions, setup rules and the facts behind this ticket: `../research/2026-09-10-browser-routes.md`. The v1 probes to build from are in tag `delegate-v1-last`.

**Blocked by:** None — can start immediately.

**Status:** done 2026-09-11 on branch `worktree/silver-river-1847` (not merged); raised by Orin 2026-09-10

- [x] Disposable probe: the worker reads a page title, then submits the `httpbin.org/forms/post` form and reports the value the response echoes back. The brief forbids web fetch, curl and built-in web tools, so a pass proves the browser was used, and it ends in an exact PASS or FAIL marker.
- [x] Agent-profile probe: the worker reports the signed-in account name shown at `facebook.com/marketplace` and clicks nothing that changes state. Exact PASS or FAIL marker.
- [x] The runner dispatches each probe through the normal dispatch path, once per harness, from a temporary working directory, and prints one table per machine: harness, CLI version, probe, PASS/FAIL, and a one-line reason. A harness with no CLI or no browser shows FAIL with its reason; nothing else changes. Since ticket 22 a claude lane dispatched from a Claude session is native — dispatch prints a spawn line and starts no relay — so the runner marks that row `NATIVE` and names the agent, and the session probes the lane itself (Orin, 2026-09-11).
- [x] The runner forces low effort where the lane accepts an effort. This matters for claude, whose only lane is on the orchestrator meter. agy's effort is fixed by its model.
- [x] The worker preamble allows reads and writes in a disposable browser only. Every other network write stays forbidden.
- [x] The prompt for agy read-only runs no longer says "Use the file tools only". It permits browser tools, and its terminal rule matches what the current relay does.
- [x] Dispatch tests cover both prompt changes (cases 32 and 33 after the merge of `main`). All delegate tests pass.
- [x] The delegate skill's Health section says how to run the probes.
- [x] Proof on the Mac: the agy row passes the disposable probe. The first full table is pasted into this ticket as the baseline for 02–04. Agent-profile rows are expected to fail until 06.

## Baseline, 2026-09-11 (Mac)

Built by run `20260911T185952Z-flash-high@agy-dbd98231`; reviewed and fixed by the lead (`9283367`, `b445ecb`, `ea792df`) and merged with `main` (`14b76fd`). All runs read-only, from temporary working directories. Host `Orins-MacBook-Pro.local`.

| harness | CLI version | lane (effort) | probe | PASS/FAIL | reason |
|---|---|---|---|---|---|
| agy | 1.2.1 | `flash-high@agy` | disposable | PASS | title=Example Domain echoed=3de1a2fdc75c |
| agy | 1.2.1 | `flash-high@agy` | agent-profile | FAIL | Agent browser profile via browser extension is not available or supported in Antigravity CLI. |
| codex | 0.154.0 | `luna-low@codex` (high) | disposable | FAIL | no browser tool was available |
| codex | 0.154.0 | `luna-low@codex` (high) | agent-profile | FAIL | agent-profile browser extension unavailable in this session |
| grok | 1.0.25 | `grok46-high@grok` (low) | disposable | FAIL | no MCP tools in the session (the worker's "Playwright MCP handshake failed" is invented; see below) |
| grok | 1.0.25 | `grok46-high@grok` (low) | agent-profile | FAIL | same cause as the disposable row |
| claude | native | `sonnet-high@claude` (native) | disposable | FAIL | no Playwright server in the session; Claude in Chrome has no connected browser |
| claude | native | `sonnet-high@claude` (native) | agent-profile | FAIL | Claude in Chrome: "Browser extension is not connected"; `list_connected_browsers` returned `[]` |

Times (UTC): agy 20:17, codex and grok 20:28, claude 20:33.

What each row rests on:

- **agy disposable**: run `20260911T201523Z-flash-high@agy-c807cf76`, 42 s. Playwright left three page snapshots in the probe's temporary directory — `example.com` with heading "Example Domain", the httpbin form with its "Customer name" box, then httpbin's JSON echo with `"custname": "3de1a2fdc75c"`, the run's nonce.
- **codex**: delegate passes `--ignore-user-config`, which drops every MCP server in the codex config; that is ticket 03. For this table codex ran at Luna high at Orin's request (the runner's default is low). The codex meter was at 8%, under the 10% gate, and a named dispatch did not stop on it.
- **grok**: the FAIL is right and the stated cause is not. The worker's only tool call, `search_tool`, returned `"status": "ready"` and "No MCP tools are available in this session", and grok's config has no Playwright server, so nothing failed a handshake. That is ticket 04's starting point.
- **claude**: the runner marks the row `NATIVE`. The live catalog's only claude lane is `fable-xhigh@claude`, so the session dispatched `sonnet-high@claude` (Orin's choice) against the repo catalog (`--config-dir stow/delegate/.config/delegate`) and spawned `lane-sonnet-high` with each prompt. A native worker gets this session's tools: both workers called Claude in Chrome, and the lead confirmed `list_connected_browsers` returns `[]` from the session. The session has no Playwright server. So ticket 02's premise — lift the claude relay's MCP block — does not apply to native lanes, which never use the relay.

Follow-ups found in the proof:

- The runner grades the worker's own marker, and the nonce is in the brief, so a worker could report it without submitting the form. Today the Playwright snapshots are the only proof. A later change could have the runner look for the nonce in the snapshots.
- A worker's FAIL reason is a claim like any other; grok's was invented. Read the run's transcript before a reason becomes a diagnosis.
- agy's `playwright` server is `npx -y @playwright/mcp@latest` with no `--isolated` and no output directory, so it does not yet follow the setup rules in the research file.
