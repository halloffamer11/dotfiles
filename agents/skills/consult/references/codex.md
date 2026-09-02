# Codex CLI (OpenAI) — invocation reference

verified-against: codex-cli 0.152.0 (2026-09-01) — exec and review flags re-checked against --help; browser lanes re-evaluated 2026-09-01 (both PASS)

## Read-only
codex exec --ignore-user-config --ephemeral --skip-git-repo-check \
  -C "<workdir>" -m <model> -c 'model_reasoning_effort="<low|medium|high>"' \
  -s read-only "$(cat <promptfile>)" </dev/null

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same as read-only but `-s workspace-write`, `-C` pointing at the worktree.

## Review (native reviewer — the codex-review role)
codex review --uncommitted -c model="<slug>" -c 'model_reasoning_effort="high"' \
  "$(cat <promptfile>)" </dev/null
`--base <branch>` or `--commit <sha>` instead of `--uncommitted` as the brief
specifies. Read-only by construction; the prompt is optional custom review
instructions. Also reachable as `codex exec review`. Prefer this over a
hand-rolled exec prompt for reviewing Claude-authored diffs.

## Structured output (both forms)
`--output-schema <file>` forces the final message to a JSON Schema;
`-o <file>` writes the last message to a file so the caller reads the
deliverable instead of scraping JSONL.

## Models
gpt-5.6-sol (hard/deep) · gpt-5.6-terra (routine) · gpt-5.6-luna (mechanical).
Catalog: `codex debug models` (see probe.sh).

## Browser (authenticated, in the user's real browser)
codex exec --ephemeral --skip-git-repo-check \
  -C "<workdir>" -m <model> -c 'model_reasoning_effort="<effort>"' \
  -s read-only "$(cat <promptfile>)" </dev/null

Same as the standard recipe MINUS `--ignore-user-config`: that flag strips
config.toml's MCP servers, including `node_repl` (the ChatGPT.app browser-use
runtime) — with it, codex has no browser and silently falls back to web.run.
Verified 2026-08-22: this form attached to the user's running browser via the
ChatGPT-for-Chrome extension native host and listed live logged-in tabs, from
a read-only sandbox on gpt-5.6-luna.
- Requires: ChatGPT.app installed, ChatGPT extension in the running browser
  (works from Helium — it reads Chrome's NativeMessagingHosts registrations).
- Per-origin grants persist in `~/.codex/browser/config.toml`; a task on a
  never-approved origin may stall on approval headlessly (untested).
- `-s read-only` guards the filesystem, not the browser: the extension can
  act in logged-in sessions. Scope the brief to the exact sites and actions
  authorized; forbid navigation beyond them.
- Current lane profile: evals/browser/_profile.md (rerun evals/browser/run.sh
  after CLI or extension updates).

## Quirks
- `exec` is the only headless path; interactive codex fails under a non-TTY
  ("stdout is not a terminal").
- NO `-a`/approval flag on `exec` — it is inherently non-interactive. Older
  notes showing `-a never` are stale.
- `--skip-git-repo-check` required outside a git repo, else "Not inside a
  trusted directory" (exit 1).
- Reads extra stdin when piped — always close with `</dev/null`.
- Reasoning effort only via `-c model_reasoning_effort="…"`.
- The playwright MCP server in config.toml now surfaces in exec runs:
  the unauthenticated probe PASSED on 2026-09-01 (0.152.0), so codex has a
  disposable-browser lane as well as the authenticated one. It did not on
  0.149.0 (2026-08-22).
