# Antigravity CLI (agy, Google) — invocation reference

verified-against: 1.1.18 (2026-08-22) — flags re-checked; browser lane live-tested via Playwright MCP. Top-level `--effort low|medium|high` still present (slugs still work)

## Read-only
agy --model <slug> --mode plan --sandbox --print "$(cat <promptfile>)" </dev/null

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same but `--mode accept-edits`.

## Models
Slug IDs only, from live `agy models` (e.g. gemini-3.6-flash-medium,
gemini-3.1-pro-high). Catalog also lists claude-* and gpt-oss-* lanes.

## Browser (unauthenticated only — disposable Chromium, no logins)
Same read-only recipe; the child drives the Playwright MCP server already
configured in agy (`agy mcp list` → playwright). Playwright launches its own
fresh Chromium: no cookies, no logged-in sessions. Route authenticated
browser work to codex/claude per evals/browser/_profile.md.
- Permission gate: headless mode auto-denies undeclared MCP tools
  ("user denied permission for mcp(playwright/<tool>)"). Grants live in
  `~/.gemini/antigravity-cli/settings.json` → `permissions.allow`, syntax
  `mcp(server/tool)` exact or `mcp(*)` global (per-server wildcard
  undocumented). Granted 2026-08-22: the full interaction set (21 tools).
  Deliberately NOT granted — never work around these: browser_run_code_unsafe
  (Node-level arbitrary code), browser_file_upload and browser_drop (local-
  file exfiltration channels). New tools in future @playwright/mcp releases
  arrive denied (fail-closed); the denial error names the exact key.
  Orin owns that file — report missing grants, don't edit.
- The IDE's built-in Browser Subagent (CDP into real Chrome, authenticated)
  is NOT available in the agy CLI (Google codelab, checked 2026-08-22).
  On agy updates, re-run evals/browser/run.sh — if agy ever passes the
  authenticated probe, the profile flips it into the authenticated pool.

## Quirks
- Flag order: `--print` swallows the next token as its prompt. Any flag placed
  between `--print` and the prompt (e.g. `--print-timeout`) silently becomes
  the prompt and the real prompt is ignored. Always put `--print "<prompt>"`
  last, all other flags before it (observed 1.1.18, 2026-08-22).
- Hard-fails on unknown `--model` — always pick from live `agy models` output.
- Playwright MCP drops session artifacts (`.playwright-mcp/page-*.yml`) into
  the child's cwd. For browser delegations, run agy from a scratch/temp dir —
  never from inside a repo (they got committed once, 2026-08-22).
- Display names ("Gemini 3.5 Flash (Medium)") are dead; slugs replaced them.
- Serves non-Gemini models too: per routing.md Harness selection, prefer agy
  only for Gemini models (native pairing).
- Cold start (observed 2026-08-03): a session's first --print call can hang
  to the 5m default timeout with zero output, then succeed in seconds on
  identical retry. No output after ~60s → kill and retry once before
  treating it as failure; a second hang is a real failure, not drift.
