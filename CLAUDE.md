# Dotfiles

Machine configuration and agent tooling managed as one Git repository. The repo is
public.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `CONTEXT.md` for the domain vocabulary (today: delegate's terms).
- Each active skill under `agents/skills/` owns its detailed context.
- A skill directory holds only what the skill executes; `tools/` holds what a skill
  uses but does not execute. Each tool directory owns its own `CLAUDE.md`.
- `references/CLAUDE.md` is a personal steering copy for the work Mac. It does not
  load here and is not an instruction for this repo.

## Where state lives

- Delegate redesign: spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`,
  tickets `.scratch/delegate-redesign/issues/`.
- Delegate dashboard: spec `docs/superpowers/specs/2026-09-13-delegate-dashboard-plugin.md`,
  tickets `.scratch/delegate-dashboard-plugin/issues/`.
- Browser setup and parity: `.scratch/delegate-browser/issues/`.
- Bootstrap and maintenance: `.scratch/dotfiles-bootstrap/issues/`.
- Delegate modular (complete): `.scratch/delegate-modular/CLAUDE.md`.
- A ticket's `**Status:**` line names each open box that waits on Orin.
- Settled decisions: `docs/adr/`. Do not reopen one.

## Standing rules

- `~/.config/delegate/{lanes,routing}.json` are stow links; edit
  `stow/delegate/.config/delegate/`, never the live files.
- A project's `.delegate/` policy never goes to main.
- Never stow or commit `~/.config/delegate/aa-key`.
- Preserve unrelated working-tree changes.
- Validate the smallest affected surface before committing.

## Agent skills

### Issue tracker

Local markdown: tickets in `.scratch/<effort>/issues/`, specs in
`docs/superpowers/specs/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default roles, written as a waiting ticket's `**Status:**` value. See
`docs/agents/triage-labels.md`.

### Worktrees

One slug names the `.scratch/` effort, the `worktree/<slug>` branch and the Herdr
checkout under `~/.herdr/worktrees/`; never `/tmp`. See `docs/agents/worktrees.md`.

### Domain docs

Single-context: the glossary is the root `CONTEXT.md`, and decisions are in
`docs/adr/`. See `docs/agents/domain.md`.
