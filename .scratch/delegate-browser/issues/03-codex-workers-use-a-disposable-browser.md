# 03 — Codex workers can use a disposable browser

**What to build:** A codex worker can use a disposable browser, and can reach nothing else that is in Orin's own codex config.

The first plan was to stop passing `--ignore-user-config` and let Orin decide, item by item, which of his plugins and servers a worker may keep. That plan is withdrawn. `codex plugin` has no `disable` subcommand — only `add`, `list`, `remove`, `marketplace` — so "turn it off for workers" means uninstalling plugins Orin uses interactively. Dropping the flag also hands every worker his `notify` hook, his `hooks.json`, and `~/.codex/AGENTS.md`, which symlinks his global `CLAUDE.md`; that import is what spoiled the v1 grok probe.

Instead delegate keeps full isolation from `~/.codex` and gives codex a home of its own, holding one MCP server. Orin's objection stands and is answered: Gmail is not a requirement for a worker sent out to do a job, and now a worker never sees it.

Facts and setup rules: `../research/2026-09-10-browser-routes.md`.

**Blocked by:** 01 — Browser probes, proven on agy with a disposable browser.

**Status:** code done 2026-09-12 (`06265cd`) on `main`; the one open box waits on Orin's machine setup on omarchy and the end-to-end probe. Raised by Orin 2026-09-10.

- [x] `delegate.py` points `CODEX_HOME` at `~/.local/share/delegate/codex-home` when that home exists, and drops `--ignore-user-config` for that run. A machine with no home keeps the old isolation, which stays correct and has no browser. `codex_home()` holds the rule; `DELEGATE_CODEX_HOME` overrides the path for tests.
- [x] The home holds one MCP server and nothing else: no plugins (Gmail, GitHub, documents, browser, chrome, computer-use), no `codex-cli`, no `node_repl`, no `context7`, no hooks, no `notify`, no `AGENTS.md`. Verified with `codex mcp list` (one row, `playwright`) and `codex doctor` ("1 server (1 stdio) · 0 disabled").
- [x] Auth still works from the delegate home: `codex login status` prints "Logged in using ChatGPT" with `~/.codex/auth.json` symlinked beside the config. The worker drains the same ChatGPT meter, so `usage.py` is unaffected.
- [x] `approvals_reviewer = "auto_review"` is required and is the whole reason earlier attempts failed. `codex exec` runs at `approval_policy = "never"`, which auto-rejects every approval request, and an MCP tool call raises one. Without the key `browser_navigate` returns "MCP tool call requires approval, but approval policy is never"; with it the call completes. `default_tools_approval_mode = "auto"` does **not** work in codex 0.154.0, though the field exists in Codex's source.
- [x] Bootstrap on a new machine: `make delegate-codex-home` writes the home from `agents/skills/delegate/assets/codex-home/config.toml` and symlinks `auth.json`. `make bootstrap` runs it. The template holds no secret; the auth symlink is outside the repo.
- [x] Dispatch test 9a2 covers the new argv and the `CODEX_HOME` the relay receives. Test 9a still covers the fallback.
- [x] Orin ran `make delegate-codex-home` on the Mac, 2026-09-12. The home holds `config.toml` and an `auth.json` symlink; `codex mcp list` shows one server and `codex login status` prints "Logged in using ChatGPT" from it.
- [ ] The same on omarchy.
- [x] Proof through the delegate dispatch path, not a raw CLI: the codex row of `browser_probes.py` passes the disposable probe in a read-only run, checked against Playwright's page snapshots. See below.
- [x] The same in a write run (`--write`), 2026-09-12. Run `20260912T202301Z-luna-low@codex-0cb235bb`, 36 s, `write=/tmp/codexwrite.H5l1Eb`: marker nonce `112cf928f5ba`, three snapshots at 20:23:22, 20:23:27 and 20:23:39 with httpbin echoing `"custname": "112cf928f5ba"`, and 12 `playwright` tool calls. `touched_files` is `['?? disposable.md']`, the brief placed in the write directory, so the worker edited nothing. `browser_probes.py` has no write mode; this was a direct `delegate.py dispatch --write`.

## Proof through the dispatch path, 2026-09-12 (Mac)

`python3 scripts/browser_probes.py --only codex --probe disposable`, after `make delegate-codex-home`:

| harness | CLI version | probe | PASS/FAIL | reason |
|---|---|---|---|---|
| codex | 0.154.0 | disposable | PASS | title=Example Domain echoed=423ca1ca7395 |

Run `20260912T194854Z-luna-low@codex-e1d1e69b`, lane `luna-low@codex` at low effort, 35 s, status `done`, read-only.

Three things carry this row, and none of them is the worker's own word:

- Playwright wrote three files inside the run's window — `page-…19-49-16-735Z.yml` (heading "Example Domain"), `page-…19-49-20-430Z.yml` (the httpbin form), and `page-…19-49-32-915Z.yml`, which holds httpbin's JSON echo with `"custname": "423ca1ca7395"`. That is the run's own nonce, so the form really was submitted from a browser. The directory was listed before the run, so these files are this run's and not an earlier one's.
- The run's `events.jsonl` holds 12 `mcp_tool_call` entries with `"server":"playwright"`, among them 4 `browser_navigate` and 2 `browser_click`.
- Those calls are themselves the evidence that the new path was taken. A codex run under `--ignore-user-config` has no MCP server at all, so a Playwright tool call is only possible through the delegate-owned home. The real relay writes no `argv.json` — only the fake relay in the tests does — so the flag change cannot be read back from the run directory directly.

## Proof so far, 2026-09-12 (Mac, raw `codex exec`)

Two runs against a delegate-owned home, read-only sandbox, model `gpt-5.6-luna` at low effort:

- minimal home (`approvals_reviewer` + the `playwright` block): `mcp_tool_call` `browser_navigate` `status: completed`, "Page Title: Example Domain".
- the same home built by filtering Orin's real config (no plugins, one server): the same result.

Playwright wrote `page-2026-09-12T19-16-50-060Z.yml` and `page-2026-09-12T19-17-00-402Z.yml` in `~/.cache/playwright-mcp`, both showing `heading "Example Domain"`. The marker was not trusted on its own.

A trap worth recording: `codex exec` keeps reading stdin, so a run started without a closed stdin never finishes. Three test runs looked like hangs and were not. Use `< /dev/null` for any non-interactive codex run.
