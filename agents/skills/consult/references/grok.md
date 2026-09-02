# Grok Build CLI (grok, xAI) — invocation reference

verified-against: grok 1.0.13 (2026-09-01) — headless read-only, write, effort, model, JSON output and catalog all live-tested; browser lane: see evals/browser/_profile.md

## Read-only (the only clean read-only form)
grok --prompt-file <promptfile> --permission-mode plan \
  --tools read_file,list_dir,grep --no-subagents --disable-web-search \
  -m <slug> --reasoning-effort <low|medium|high|xhigh> \
  --output-format json --max-turns <N> --cwd "<workdir>" </dev/null

`--tools` is the guard: it removes the shell and edit tools entirely, so a
write request ends with a clean `BLOCKED` and `stopReason: end_turn`.
`--permission-mode plan` alone is NOT enough — the model still reaches for
`run_terminal_command`, the headless permission prompt auto-cancels, and the
whole turn dies with `stopReason: cancelled` and no answer (observed 1.0.13).
`--sandbox read-only` made that worse, not better (turn cancelled while the
model hunted for a shell) — leave it off for read-only runs.

## Write-enabled (only when the user authorized implementation; isolated worktree)
grok --prompt-file <promptfile> --permission-mode acceptEdits \
  --allow Write --allow Edit --sandbox workspace --no-subagents --disable-web-search \
  -m <slug> --reasoning-effort <effort> --output-format json --max-turns <N> \
  --cwd "<worktree>" </dev/null

Verified: creates files, `stopReason: end_turn`. `--sandbox workspace` is a
built-in OS-level profile confining writes to the working directory. Shell
commands still prompt (and therefore cancel) unless an explicit `--allow
"Bash(<prefix>*)"` rule covers them — add only the exact commands the brief
needs (e.g. `--allow "Bash(npm test*)"`). Never `--always-approve`, `--yolo`,
or `--permission-mode bypassPermissions`.

## Models
`grok models` is the catalog (currently grok-4.6 default, grok-4.5). Role
`grok-code` in scripts/resolve-model.sh resolves to the newest `grok-<ver>`.
Usage output reports the id with a `-build` suffix (grok-4.6-build); pass
the catalog id, not the suffixed one.

## Output
`--output-format json` → `text`, `stopReason` (end_turn | cancelled |
max_turn_requests | refusal), `sessionId`, `usage`, `total_cost_usd`,
`modelUsage`. `--json-schema <schema>` forces structured output.
`-r <sessionId>` resumes a headless session.

## Quota (weekly meter, zero-token probe)
`/usage` is a TUI dialog, but it is fed by an Agent Client Protocol
extension method that is callable headlessly:

  grok agent stdio            # JSON-RPC over stdio
  → initialize {protocolVersion:1, clientCapabilities:{…}}
  → _x.ai/billing {}          # note the leading underscore (ACP extension)

Response: `config.currentPeriod{type,start,end}` (USAGE_PERIOD_TYPE_WEEKLY
on SuperGrok), `subscription_tier`, and — only when non-zero —
`creditUsagePercent`, `includedUsed`, `totalUsed`, `monthlyLimit`,
`onDemandCap/Used`, `prepaidBalance` (field list from the binary's serde
table, 1.0.13; the HTTP path behind it is `/billing?format=credits`).
A missing `creditUsagePercent` means 0% used. There is no 5-hour window.
scripts/usage.py implements this as `probe_grok()`; verified 2026-09-01
against the TUI dialog (0% used, resets Sep 8 22:35 local — identical).
`grok -p "/usage"` does NOT work (treated as a prompt). A `rate_limit`
failure (HTTP 429/503/529 text in stderr) is a quota failure: refresh
usage.py, mark the lane unavailable, re-resolve once.

## Quirks
- Grok imports Claude Code context: `~/.grok/config.toml` adds
  `~/.claude/skills` as an extra skill dir and `claude_import_state.json`
  records a CLAUDE.md import. Children have been seen acting on the global
  CLAUDE.md (checking `HERDR_ENV` before starting). Every brief must open with:
  "Non-interactive session. Use only the file tools. Do not run shell
  commands, do not check environment variables, do not delegate." The
  `--rules "<text>"` flag appends the same to the system prompt.
- Blocks on an open stdin like the others — always `</dev/null`.
- `--worktree` is ignored in headless mode; create the worktree yourself.
- Cold catalog fetch on first `grok models` after login (~2s); cached after.
- Sessions are written to `~/.grok/sessions/<url-encoded cwd>/`; run from a
  scratch dir for probes so they do not pile up under a repo path.

## Browser
Not a browser lane (evaluated 2026-09-01, 1.0.13). `grok mcp list` shows
only context7, but a session can also carry a `playwright` MCP server
imported from Claude/Codex project config (seen in `_x.ai/mcp/servers_updated`),
so tool availability is cwd-dependent. Even with
`--allow "MCPTool(playwright__*)"` the headless probe ended after one turn
with `stopReason: cancelled` — the MCP call still hit the permission prompt.
Route browser work to codex/claude/agy per evals/browser/_profile.md. To
re-test: add playwright with `grok mcp add`, find the rule form that
auto-approves it headlessly, then re-run evals/browser/run.sh (run_grok is
wired).
