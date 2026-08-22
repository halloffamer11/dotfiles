# Claude Code headless — invocation reference

verified-against: 2.1.240 (Claude Code) (2026-08-22) — base `-p` form exercised; Browser section added and live-tested

## Read-only / analysis
claude -p --permission-mode plan --model <alias|id> --output-format json \
  "$(cat <promptfile>)" </dev/null

This is the primary form: the child inherits skills/CLAUDE.md context
(fine for most consult delegations), and it's the form that works on
subscription/OAuth auth — Orin's machines. `--permission-mode plan`
mechanically pins read-only, matching codex's `-s read-only` / agy's
`--mode plan` (verified 2.1.220, 2026-08-03: succeeds with a normal
`result` field, no output-shape distortion).

### Conditional: `--bare` (only where ANTHROPIC_API_KEY/apiKeyHelper auth is available)
claude -p --bare --model <alias|id> --output-format json \
  "$(cat <promptfile>)" </dev/null

Anthropic recommends `--bare` for scripted/nested calls where that auth is
available. Per its own `--help` text it skips hooks, LSP, plugin sync,
attribution, auto-memory, background prefetches, keychain reads, and
CLAUDE.md auto-discovery (sets `CLAUDE_CODE_SIMPLE=1`) — reproducible,
isolated children. Skills still resolve via explicit `/skill-name`; auth
under `--bare` is strictly `ANTHROPIC_API_KEY` or `apiKeyHelper` (OAuth and
keychain are never read) — it will fail with "Not logged in" on OAuth-only
machines. Use it only when the child SHOULD be isolated from auto-discovered
skills/project instructions, and say so in the consult record line.

## Browser (authenticated, in the user's real browser)
claude -p --chrome --model <alias|id> "$(cat <promptfile>)" \
  --allowedTools "mcp__claude-in-chrome" </dev/null

Verified 2026-08-22 (2.1.240): headless child attached to the running
browser via the Claude extension, opened a tab in its Claude tab group,
acted in the logged-in session, closed it. All three parts are load-bearing:
- `--chrome` — integration is off by default in `-p`. OAuth login only:
  API-key/`setup-token` auth silently disables it (docs, since 2.1.216).
- Default permission mode, NOT `--permission-mode plan` — plan blocks the
  browser tools (tab creation is a mutation). With only claude-in-chrome
  allowlisted, every other un-allowlisted tool still auto-denies headlessly,
  so the child stays effectively read-only on the filesystem.
- Prompt BEFORE `--allowedTools` — the flag is variadic and swallows a
  trailing positional prompt ("Input must be provided..." error).
Scope-of-access differs from codex: the child cannot see existing tabs
(tab-group privacy boundary) — it acts in tabs it opens itself, with the
user's cookies. Concurrent with an interactive session holding its own
connection (verified). Lane profile: evals/browser/_profile.md.

## Write-enabled (only when the user authorized implementation)
Isolated worktree + `--permission-mode acceptEdits`.
Never `--dangerously-skip-permissions`.

## Models
Aliases sonnet | opus | fable (haiku excluded by routing.md), or full IDs
(e.g. claude-opus-5). No catalog command — see routing.md Refresh.

## Quirks
- `--output-format json` returns `result` + `session_id`; resume a child with
  `--resume <session_id>`.
- `--json-schema <file>` forces validated structured output.
- Nesting is supported; keep depth 1 — children are told not to delegate.
- Observed 2026-08-03: `claude -p --bare --model sonnet "..."` failed
  ("Not logged in · Please run /login") on this machine, which authenticates
  via OAuth/keychain, not `ANTHROPIC_API_KEY` — matches `--help`'s statement
  that `--bare` never reads OAuth/keychain. The same prompt without `--bare`
  succeeded and enumerated the full installed skill catalog by name (auto-
  discovery working); `--bare` was not separately confirmed to expose that
  catalog, but `--help` states explicit `/skill-name` invocation still
  resolves. On OAuth machines (Orin's), use the non-`--bare` form above —
  it just works; reach for `ANTHROPIC_API_KEY`/`apiKeyHelper` provisioning
  only if `--bare` isolation is specifically needed.
