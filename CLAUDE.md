# Dotfiles

Machine configuration managed as one Git repository. The repo is public. The skills CLI installs
authored skills from the core Pack (`halloffamer11/skills`) and the personal Pack
(`halloffamer11/skills-personal`).

## Start here

- Read `Makefile` before changing installation or stow behavior.
- `docs/bootstrap.md` is the operator guide (profiles, fresh machine, maintenance);
  `make test-bootstrap` checks it in isolated homes.
- The chezmoi agentic Layer lives in `home/`. Its declarations are in
  `home/.chezmoidata/`. Run `make test-chezmoi` to rehearse it.
- Edit an authored skill in its Pack and push it. Chezmoi selects Packs in
  `home/.chezmoidata/packs.toml`, and `fleet-sync` refreshes installed skills.
  The Stow fallback selects skills in the Makefile. Use `make external-updates`
  to refresh them.
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

### Domain docs

Single-context: a root `CONTEXT.md` and `docs/adr/`, made when the first term or
decision needs one. See `docs/agents/domain.md`.
