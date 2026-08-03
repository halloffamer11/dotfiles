# Claude Code headless — invocation reference

verified-against: 2.1.220 (Claude Code) (2026-08-03)

## Read-only / analysis
claude -p --bare --model <alias|id> --output-format json \
  "$(cat <promptfile>)" </dev/null

`--bare` is Anthropic's recommended mode for scripted/nested calls. Per its
own `--help` text it skips hooks, LSP, plugin sync, attribution, auto-memory,
background prefetches, keychain reads, and CLAUDE.md auto-discovery (sets
`CLAUDE_CODE_SIMPLE=1`) — reproducible, isolated children. Skills still
resolve via explicit `/skill-name`; auth under `--bare` is strictly
`ANTHROPIC_API_KEY` or `apiKeyHelper` (OAuth and keychain are never read).
Omit `--bare` only when the child SHOULD see auto-discovered skills/project
instructions, and say so in the consult record line.

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
  resolves. Set `ANTHROPIC_API_KEY` (or `apiKeyHelper`) before scripting
  `--bare` calls on machines using OAuth login.
