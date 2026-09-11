# 04 — Grok workers can use a disposable browser

**What to build:** A grok worker can use a Playwright server in grok's own config. The relay already maps read-only to `--sandbox read-only --always-approve`, so no relay change is expected. The v1 failure came from plan mode cancelling a shell command, and the relay no longer uses plan mode.

On macOS grok's sandbox does not block network, so a pass here says nothing about Linux. Ticket 05 tests that.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] Setup on the Mac, in conversation with Orin: a `playwright` server in grok's config, as a raw MCP entry or the marketplace plugin (the choice is recorded here), following the setup rules.
- [ ] If headless approval stops the tool, the fix is config first. A relay change is made only if config cannot fix it; it then lands on the fork, is pinned, and is offered upstream.
- [ ] Proof on the Mac: the grok row passes the disposable probe in a read-only run and in a write run.
