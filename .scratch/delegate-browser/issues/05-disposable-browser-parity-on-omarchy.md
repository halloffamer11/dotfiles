# 05 — Disposable-browser parity on omarchy

**What to build:** Workers on all four harnesses can use a disposable browser on omarchy, as they can on the Mac. omarchy has all four CLIs, Chromium and Helium, but no MCP server in any harness, no Playwright browsers, and no agy tool grants.

grok's read-only sandbox blocks child-process network on Linux, and the Playwright server is a child process. So the grok read-only row may fail here for a reason that does not exist on the Mac.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 02, 03 and 04.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] omarchy runs the same delegate code as the Mac: its dotfiles checkout carries 01–04, and the relay check passes there.
- [ ] Setup, in conversation with Orin: a browser that Playwright can drive (its own Chromium or a system one, the choice recorded here), a `playwright` server in all four harness configs following the setup rules, and the agy tool grants.
- [ ] The runner runs on omarchy from a herdr pane in the desktop session. Its table is pasted here.
- [ ] Proof: the omarchy disposable column matches the Mac. The only accepted difference is a grok read-only failure caused by its Linux sandbox blocking the Playwright server's network. That is recorded here with its evidence and a follow-up ticket.
