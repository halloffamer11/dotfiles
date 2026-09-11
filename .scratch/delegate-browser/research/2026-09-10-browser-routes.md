# Browser routes for delegate workers — findings, 2026-09-10

Grilling session with Orin, 2026-09-10. Each fact below was checked against a file, a CLI's `--help`, or an official doc by the lead session. Worker research runs were treated as claims; one was wrong (it said Claude in Chrome does not support Linux; the Claude Code docs say it does).

## Goal and decisions

- The delegate dispatch path must not block a browser that a harness already has. If the harness is set up, a worker can use it; if not, nothing changes.
- No new config file, no per-run flag, no detection, no ranking change. Machine setup (MCP servers in each harness's own config, extensions, sign-ins) is done by Orin in conversation and is not a repo deliverable. Its test is a probe row turning PASS.
- Two browser kinds (terms in the delegate `SKILL.md`): the **disposable browser** (read and write allowed) and the **agent profile** (Helium profile "GenAI", reached through the Playwright extension; on every run for all four harnesses; used only for the sites and actions a brief names). Workers never reach the personal profile: the extension is installed only in the agent profile.
- Relay changes go in our ADS fork, pinned, and are offered upstream.
- Parity means the same probe table on the Mac and on omarchy. Sessions on omarchy run through herdr in the Hyprland desktop, so a visible browser is available.

## Setup rules every ticket's setup follows

- The disposable server (`playwright`, `@playwright/mcp`) runs with `--isolated`, so parallel workers do not share one profile (the README: a persistent profile "can only be used by one browser instance at a time"), and with its output directory outside the project, so its session files do not trip the relays' read-only change check in a repo that does not ignore `.playwright-mcp/`.
- The agent-profile server (`agent-browser`) runs with `--extension` and `--profile-dir-name` for the agent profile, never `--isolated`. Its `PLAYWRIGHT_MCP_EXTENSION_TOKEN` stays on the machine and never enters this public repo.

## What blocks each harness today

| Harness | Blocker in the dispatch path | Source |
|---|---|---|
| claude | The ADS claude relay allows only `Read,Glob,Grep[,Edit,Write,Bash]`, passes `--strict-mcp-config` and `--disallowedTools "mcp__*"`, and uses plan mode on read-only runs. Its header: "Every profile disables configured MCP discovery and Claude.ai connectors, denies all MCP tools". | relay `buildArgv`, `toolSurface`, header comment |
| codex | `delegate.py` passes `--ignore-user-config`, which drops every MCP server in `~/.codex/config.toml`. The ADS docs call the flag "isolated review (skip ambient MCP/user config)". That config also holds `gmail@openai-curated` (enabled), `codex-cli`, `node_repl`, `computer-use` (disabled), `context7`, `openaiDeveloperDocs`. | `run_relay`; codex relay `SKILL.md` |
| grok | Nothing in the relay; read-only is `--sandbox read-only --always-approve`. On Linux that sandbox blocks child-process network through seccomp; on macOS it is a no-op. No per-run MCP flag. The marketplace has a `playwright` plugin. | `~/.grok/docs/user-guide/18-sandbox.md` lines 34, 224; `14-headless-mode.md` |
| agy | Nothing in the relay; read-only passes `--sandbox --dangerously-skip-permissions`. But `delegate.py` tells agy read-only workers "Use the file tools only". Servers in `~/.gemini/config/mcp_config.json`; grants in `~/.gemini/antigravity-cli/settings.json`. No per-run MCP flag. The CLI has no built-in browser; the browser agent is IDE-only. | `build_prompt`; agy builtin skill docs |

## The v1 result (tag `delegate-v1-last`, `evals/browser/`)

2026-09-01, raw CLIs, not through the current relays: codex passed both kinds (live through the ChatGPT extension, disposable through Playwright); claude passed live through Claude in Chrome and failed disposable; agy passed disposable only; grok failed both. The grok Playwright failure was a probe problem: grok imported Orin's `CLAUDE.md`, ran `echo $HERDR_ENV`, and plan mode cancelled the turn. The redesign then removed every browser path.

## Routes not used, and why

- **Codex's own live browser** (ChatGPT extension host `com.openai.codexextension`): its binary ships only as `macos/arm64` under the bundled `chrome` plugin; omarchy has no bundled plugins. It would break parity.
- **Claude in Chrome**: the docs support Chrome, Edge and other Chromium browsers on Linux (not WSL), and it needs a `/login` sign-in. It stays available in interactive sessions; delegate uses the Playwright extension for all four harnesses instead.
- **Moving the agent profile to its own data directory, or a storage-state file**: both work headless, but the first allows one run at a time and needs a new sign-in, and the second goes stale and is a secret file.

## Machine state, 2026-09-10

- **Mac**: Helium runs with profiles "You" (Default, personal; Bitwarden only) and "GenAI" (`Profile 1`; Claude in Chrome and the ChatGPT extension), both in one data directory. Playwright servers exist in codex and agy configs, without `--isolated`. Claude has only `context7` at user scope. grok has only `context7`.
- **omarchy** (Arch, Hyprland, `wayland-1`): claude 2.1.267, codex 0.154.0, grok 1.0.24, agy 1.2.0, Chromium 152, Helium (`/usr/bin/helium-browser`, one profile "You"). No MCP server in any harness, no Playwright browsers, no agy grants, no Claude or ChatGPT native host.

## Playwright extension

The README lists Chrome, Edge and Chromium. Several clients can connect at once, each in its own tab group. Each connection needs approval in the browser unless the token is set; the token is specific to one browser profile, and `--profile-dir-name` selects the profile. Whether Helium on Arch accepts it is unverified until ticket 07.

## Review record

Ticket breakdown reviewed by `grok46-high@grok`, run `20260911T015032Z-grok46-high@grok-01af57fa`. Five findings accepted (four MCP blockers on claude; codex exposure decided per item; probes must prove browser use; the grok Linux exception; `--isolated`). One rejected: that the extension allows one browser at a time.
