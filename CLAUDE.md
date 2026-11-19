# Dotfiles

Machine configuration managed as one Git repository. The repo is public. Agent skills
live in their own repo, `halloffamer11/skills`, installed through the skills CLI. They
split out on 2026-10-01 with their history.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- `docs/bootstrap.md` is the operator guide (profiles, fresh machine, maintenance);
  `make test-bootstrap` checks it in isolated homes.
- Skills are declared in the Makefile (`externals`), not stored here. To change a
  personal skill, edit `halloffamer11/skills`, push, then `make external-updates`.
- `tools/` holds machine tools; each tool directory owns its own `CLAUDE.md`.
- `references/CLAUDE.md` is the user's global `~/.claude/CLAUDE.md`; `make configs` links
  it there. Edit it here. It is not an instruction for this repo.

## Where state lives

- Bootstrap and maintenance: `.scratch/dotfiles-bootstrap/issues/`.
- Next-generation layout (chezmoi and the rest): the planning repo
  `~/Documents/dotfiles-refactor`.
- A ticket's `**Status:**` line names each open box that waits on the user.
- Settled decisions: `docs/adr/` (none yet). Do not reopen one.

## Standing rules

- Keep the repo generic. Name no organization, site or machine that a deployment
  serves. Call a target a site deployment or a machine deployment; its specific
  settings stay in machine-local files (`local.mk`, `~/.gitconfig.local`,
  `~/.zshrc.local`) that are never committed.
- Preserve unrelated working-tree changes.
- Validate the smallest affected surface before committing.

## Agent skills

### Issue tracker

Local markdown: each effort in `.scratch/<effort>/`, with its `spec.md` and
`issues/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default roles, written as a waiting ticket's `**Status:**` value. See
`docs/agents/triage-labels.md`.

### Worktrees

One slug names the `.scratch/` effort, the `worktree/<slug>` branch and the Herdr
checkout under `~/.herdr/worktrees/`; never `/tmp`. See `docs/agents/worktrees.md`.

### Domain docs

Single-context: a root `CONTEXT.md` and `docs/adr/`, made when the first term or
decision needs one. See `docs/agents/domain.md`.
