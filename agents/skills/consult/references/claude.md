# Claude Code headless — invocation reference

verified-against: 2.1.220 (Claude Code) (2026-08-03)

## Read-only / analysis
claude -p --bare --model <alias|id> --output-format json \
  "$(cat <promptfile>)" </dev/null

`--bare` is Anthropic's recommended mode for scripted/nested calls: skips
hooks, skills, plugins, MCP, and CLAUDE.md discovery — reproducible, isolated
children. Omit it only when the child SHOULD see skills/project instructions,
and say so in the consult record line.

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
