# 02 — Claude workers can use a disposable browser

**What to build:** A claude worker can use the Playwright server in Orin's own Claude config.

This ticket was written before ticket 22 and its premise no longer holds. It targets the claude relay in our ADS fork, which blocks MCP in four ways. Since ticket 22 a claude lane dispatched from a Claude session is **native**: `delegate.py` prints a spawn line and starts no relay at all, so a native worker never meets those four blocks. It inherits this session's tools instead. Lifting the relay's MCP block would change nothing on the path Orin actually uses.

The ticket is therefore rescoped to the native path. The relay work is kept only as a note, for the day a claude lane is dispatched from a non-Claude orchestrator.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** open; rescoped 2026-09-12 after ticket 22. Raised by Orin 2026-09-10.

- [x] Setup on both machines: a `playwright` server in Claude's user config that follows the setup rules. Orin added it 2026-09-12 with `claude mcp add -s user playwright -- npx -y @playwright/mcp@latest --isolated --headless --output-dir ~/.cache/playwright-mcp`; `claude mcp list` shows it Connected on the Mac and on omarchy.
- [ ] A session must restart before its native workers see a new MCP server. Restart, then confirm the session itself has the Playwright tools.
- [ ] Every other MCP server the session exposes to a native worker is listed here. On the Mac today that is `context7` plus the claude.ai connectors Gmail, Google Drive and Google Calendar. A native worker inherits them. The worker preamble forbids messages, but that is an instruction, not a block — decide whether that is acceptable, or whether native lanes need a narrower tool set.
- [ ] Proof on the Mac: the claude row of the baseline table passes the disposable probe. The runner marks the row `NATIVE`, so dispatch the lane with the probe brief and spawn the agent the native line names, then check the pass against Playwright's page snapshot.
- [x] The delegate skill's `CLAUDE.md` names the current ADS pin and describes agy read-only as it now works. Done 2026-09-11 during session close; update the pin line again if ticket 04 pins a new commit.
- [ ] Note, not work for now: the relay still denies MCP to a claude worker through its tool allowlist, `--strict-mcp-config` and `--disallowedTools "mcp__*"`, and read-only runs use plan mode. That matters only for a claude lane dispatched from a non-Claude orchestrator. Raise a new ticket if that case appears.

## Why the claude rows failed in the 2026-09-11 baseline

Both native workers reached for Claude in Chrome, which had no connected browser, and the session had no Playwright server at all. The lead confirmed `list_connected_browsers` returned `[]` from the session itself. The first half is now fixed by the setup above; the agent-profile half waits on ticket 06.
