# Codex CLI (OpenAI) — invocation reference

verified-against: codex-cli 0.145.0 (2026-08-03)

## Read-only
codex exec --ignore-user-config --ephemeral --skip-git-repo-check \
  -C "<workdir>" -m <model> -c 'model_reasoning_effort="<low|medium|high>"' \
  -s read-only "$(cat <promptfile>)" </dev/null

## Write-enabled (only when the user authorized implementation; isolated worktree)
Same as read-only but `-s workspace-write`, `-C` pointing at the worktree.

## Models
gpt-5.6-sol (hard/deep) · gpt-5.6-terra (routine) · gpt-5.6-luna (mechanical).
Catalog: `codex debug models` (see probe.sh).

## Quirks
- `exec` is the only headless path; interactive codex fails under a non-TTY
  ("stdout is not a terminal").
- NO `-a`/approval flag on `exec` — it is inherently non-interactive. Older
  notes showing `-a never` are stale.
- `--skip-git-repo-check` required outside a git repo, else "Not inside a
  trusted directory" (exit 1).
- Reads extra stdin when piped — always close with `</dev/null`.
- Reasoning effort only via `-c model_reasoning_effort="…"`.
