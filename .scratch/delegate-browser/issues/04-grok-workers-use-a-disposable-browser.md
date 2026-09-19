# 04 — Grok workers can use a disposable browser

**What to build:** A grok worker can use a Playwright server in grok's own config, on a read-only run as well as a write run.

The ticket expected no relay change. That expectation is wrong, and the cause is not what the ticket assumed. grok's built-in `read-only` sandbox breaks **every** stdio MCP server on macOS, not only Playwright: in the same failing run `context7` dies too. The relay maps a read-only run to `--sandbox read-only`, so no server survives, and `search_tool` correctly reports an empty catalog. Config alone cannot fix it, which is the condition this ticket set for changing the relay.

On macOS grok's sandbox does not block network, so a pass here says nothing about Linux. Ticket 05 tests that.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** ready-for-agent; root cause found and the fix proven 2026-09-12. Raised by Orin 2026-09-10.

- [x] Setup on the Mac: a `playwright` server in `~/.grok/config.toml` at user scope, with `--isolated --headless --output-dir ~/.cache/playwright-mcp`. Added by Orin 2026-09-12 on the Mac and on omarchy. `grok mcp doctor` reports it healthy with 24 tools, and `grok inspect` lists it as `config`.
- [x] Root cause, from grok's own debug log (`RUST_LOG=debug GROK_LOG_FILE=…`): under `--sandbox read-only` both servers spawn and then fail with "handshake failed: connection closed: initialize response", alongside "Error killing MCP child process group: Operation not permitted (os error 1)". Under the default `workspace` sandbox the same session has `browser_navigate` and `browser_snapshot`. The output directory is not the cause: a temp output dir, which the read-only profile permits, fails the same way.
- [x] The fix is proven at the grok level. A custom profile in `.grok/sandbox.toml`, `[profiles.probe] extends = "read-only"` with `read_write` for `~/.npm`, `~/.cache/playwright-mcp` and `~/Library/Caches/ms-playwright`, makes both handshakes succeed: "MCP handshake succeeded server=playwright … tool_count=24" and "server=context7 … tool_count=2".
- [ ] Narrow the grants. Three were granted together; find the smallest set that works, and write it into the setup rules. Each attempt costs one grok run.
- [ ] Relay change on our ADS fork: a read-only grok run must be able to use a named sandbox profile. Today the relay's parser accepts only `--read-only` and `--full-access`, mapping to the fixed set `workspace-write | read-only | full-access` (`AUTONOMY_MODES`), so no profile name can reach grok. Pin the new commit in `ads.sh`, run `ads.sh check`, and offer the change upstream with the PR link recorded here.
- [ ] Setup on both machines, in conversation with Orin: the profile in `~/.grok/sandbox.toml`, with the narrowed grants.
- [ ] Proof on the Mac: the grok row passes the disposable probe in a read-only run and in a write run, each checked against Playwright's page snapshot.

## What a write run already gives, with no change at all

`autonomyFlags` maps a write run to `--always-approve --sandbox workspace`, and a workspace-sandbox session has the browser tools today. So a grok worker dispatched with `--write` can already use a disposable browser. Only the read-only path is blocked, which is the common path for scouts and probes.

## A worker's stated reason is still a claim

The 2026-09-12 probe run reported "Playwright MCP handshake failed". The failure was real this time, but the worker did not know that: both occurrences of the word in the run's events are streaming deltas of the model's own text, with no system message behind them. Its only sourced evidence was `search_tool` returning an empty catalog. Read the log, not the report.
