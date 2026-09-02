# Antigravity CLI (agy, Google) — invocation reference

verified-against: 1.1.24 (2026-09-01 browser eval; flags re-checked against --help on 1.1.23 the same day; new since 1.1.18: --agent, --json-schema, --disable-slash-commands) — earlier: 1.1.18 (2026-08-22) — flags re-checked; browser lane live-tested via Playwright MCP. Top-level `--effort low|medium|high` still present (slugs still work). Browser recipe corrected 2026-08-22 PM after live failures (see Browser: no `--mode plan`, two mandatory prompt directives)

## Read-only
agy --model <slug> --mode plan --sandbox --print "$(cat <promptfile>)" </dev/null

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same but `--mode accept-edits`.

## Models
Slug IDs only, from live `agy models` (e.g. gemini-3.6-flash-medium,
gemini-3.1-pro-high). Catalog also lists claude-* and gpt-oss-* lanes.

## Browser (unauthenticated only — disposable Chromium, no logins)
NOT the read-only recipe — drop `--mode plan` for browser delegations:

agy --model <slug> --sandbox --print-timeout 9m --print "$(cat <promptfile>)" </dev/null

In plan mode a multi-step browser task writes an implementation plan and waits
for an interactive "Proceed" that never comes (observed 1.1.18, 2026-08-22;
the eval passed only because its probe task was trivial). Read-only still
holds without `--mode plan`: only the Playwright interaction set is granted,
so edits and terminal auto-deny. The prompt MUST include two directives:
(1) "Execute now with the browser tools; do not write a plan or ask for
approval — non-interactive session, printed output is the deliverable."
(2) "Use ONLY the Playwright browser tools; never run terminal commands —
they are blocked and the attempt kills the session." (Observed: a child
shelling out to python3 to decode a screenshot died on the sandbox denial,
exit 1, empty output.)
The child drives the Playwright MCP server already
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
