# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign (agreed 2026-09-08, ticketed 2026-09-09, tickets 01-08 landed 2026-09-09 uncommitted, 09 pending Orin's go): tickets in `.scratch/delegate-redesign/issues/`; context in `agents/skills/delegate/CLAUDE.md`; spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
