# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign **merged to `main`** 2026-09-09; the `delegate-rebuild` branch is deleted and tag `delegate-v1-last` still holds the removed old path. Tickets 01-10 landed; **11 entry points, 12 TUI orientation, 13 model discovery, 14 read-only defect, 15 per-effort lanes** are open in `.scratch/delegate-redesign/issues/`. Spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`; §9 acceptance is five of eight signed off, with the walk recorded in ticket 09. Skill context: `agents/skills/delegate/CLAUDE.md`.
- Branch `effort-data-tooling`, unmerged: `agents/skills/delegate/scripts/effort.py`, a `pack`/`extract`/`check` pipeline that pulls per-effort score-and-cost off benchmark pages for ticket 15. `pack` and `check` are proven against live pages; `extract` has never run. Approved sources and their cautions are in `agents/skills/delegate/assets/sources.json`; the provenance research behind that choice is `.scratch/delegate-redesign/research/2026-09-09-effort-data-sources.md`.
- Ticket 14 is half fixed: grok read-only works via the fork pin, agy still auto-denies and needs `--write`.
- Waiting on Orin: drop `export DELEGATE_BALANCE=1` from `~/.zshrc.local` (spec §9.7); set `meter_weight` and `trust` on `astra-high@codex` in `~/.config/delegate/lanes.json` — the `price` is now sourced as `10 / 1 / 12.5 / 50` from OpenAI's pricing page and just needs pasting, but the other two are judgement no benchmark can make; decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line as ticket 09 asks, which would drop the `why-claude` and "result is a claim" rules.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
