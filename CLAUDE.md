# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign **merged to `main`** 2026-09-09; the `delegate-rebuild` branch is deleted and tag `delegate-v1-last` still holds the removed old path. Tickets 01-10 landed; **11 entry points, 12 TUI orientation, 13 model discovery, 14 read-only defect, 15 per-effort lanes** are open in `.scratch/delegate-redesign/issues/`. Spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`; §9 acceptance is five of eight signed off, with the walk recorded in ticket 09. Skill context: `agents/skills/delegate/CLAUDE.md`.
- Waiting on Orin: drop `export DELEGATE_BALANCE=1` from `~/.zshrc.local` (spec §9.7); fill the placeholder `meter_weight`, `trust` and null `price` on the new `astra-high@codex` lane in `~/.config/delegate/lanes.json`; decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line as ticket 09 asks, which would drop the `why-claude` and "result is a claim" rules.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
