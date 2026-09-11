# 02 — Claude workers can use a disposable browser

**What to build:** A claude worker, in a read-only run or a write run, can use the Playwright server in Orin's own Claude config. Today the claude relay in our ADS fork blocks MCP in four ways: its tool allowlist has no MCP names, it passes `--strict-mcp-config`, it denies `mcp__*`, and read-only runs use plan mode, which blocked browser tools in the v1 test. Lift all four for the servers in Orin's own config. Read-only runs must still be unable to change files, and Claude.ai connectors stay off.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] The relay change lands on our fork, the delegate skill pins the new commit, and the relay check passes.
- [ ] The change is offered upstream, and the PR link is recorded here.
- [ ] Read-only claude runs still cannot edit, write, or run a shell. The relay's read-only change check still reports changes.
- [ ] Claude.ai connectors stay off in every run.
- [ ] Setup on the Mac, in conversation with Orin: a `playwright` server in Claude's user config that follows the setup rules. Every other MCP server that config now exposes to workers is listed here.
- [ ] The delegate skill's `CLAUDE.md` names the current ADS pin and describes agy read-only as it now works.
- [ ] Proof on the Mac: the claude row passes the disposable probe in a read-only run and in a write run. A read-only failure does not close this ticket.
