# 03 — Codex workers can use a disposable browser

**What to build:** A codex worker can use the Playwright server in Orin's own codex config. Today delegate passes `--ignore-user-config` on every codex run, which drops every MCP server in that config. Removing the flag also exposes everything else in the config to every codex worker, including an enabled Gmail plugin and a server that can start codex, so Orin decides about each item before the flag goes.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** open, ready-for-agent, raised by Orin 2026-09-10

- [ ] Before the change: Orin's decision (workers keep it, or it is disabled) is recorded here for each non-browser plugin and server in the codex config: `gmail@openai-curated`, `codex-cli`, `node_repl`, `computer-use`, `context7`, `openaiDeveloperDocs`, and anything added since.
- [ ] delegate stops passing `--ignore-user-config` on codex runs. The dispatch test that expects the flag changes with it. All delegate tests pass.
- [ ] Setup on the Mac: the codex `playwright` server follows the setup rules. Today it lacks `--isolated`.
- [ ] Proof on the Mac: the codex row passes the disposable probe in a read-only run and in a write run.
