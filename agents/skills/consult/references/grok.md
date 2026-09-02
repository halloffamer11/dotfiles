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

## Quota
No headless quota probe exists: `/usage` is a TUI billing view only, and
`grok -p "/usage"` is treated as a prompt (the model starts investigating).
usage.py therefore reports the grok lane as `unknown`; per routing.md §3 an
unknown lane is eligible by pin or capability but never wins a balancing
choice. A `rate_limit` failure (HTTP 429/503/529 text in stderr) is a quota
failure: mark the lane unavailable for the session and re-resolve once.

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
Evaluated 2026-09-01 (1.0.13): FAIL on both probes. Grok has no browser
tool — `grok mcp list` shows only context7 — and the probe output stops
after the model's first sentence, the headless-cancel signature. Not a
browser lane. If a Playwright MCP server is ever added (`grok mcp add`),
re-run evals/browser/run.sh; run_grok is already wired.
