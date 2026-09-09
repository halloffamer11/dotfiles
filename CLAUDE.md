# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign: landed on `delegate-rebuild` (commits 7c76843, 9545e6f; tag `delegate-v1-last` holds the old path). Open: ticket 07b (setup wizard as a TUI, worker in flight) and Orin's items in `.scratch/delegate-redesign/issues/07b-setup-tui.md` and `09-advise-only-hook-and-migration.md`; context in `agents/skills/delegate/CLAUDE.md`; spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
