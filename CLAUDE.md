# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign **merged to `main`** 2026-09-09; the `delegate-rebuild` branch is deleted and tag `delegate-v1-last` still holds the removed old path. Tickets 01-10 landed; **11 entry points, 12 TUI orientation, 13 model discovery, 14 read-only defect, 15 per-effort lanes** are open in `.scratch/delegate-redesign/issues/`. Spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md`; §9 acceptance is five of eight signed off, with the walk recorded in ticket 09. Skill context: `agents/skills/delegate/CLAUDE.md`.
- `effort-data-tooling` **merged to `main`** 2026-09-10: `agents/skills/delegate/scripts/effort.py`, a `pack`/`extract`/`check` pipeline that pulls per-effort score-and-cost off benchmark pages for ticket 15. All three stages are proven — one `extract` run on `flash-high@agy` returned 26 rows and `check` accepted 26, rejected 0. That output is kept as evidence in `.scratch/delegate-redesign/_data/`. Approved sources and their cautions are in `agents/skills/delegate/assets/sources.json`; the provenance research behind that choice is `.scratch/delegate-redesign/research/2026-09-09-effort-data-sources.md`. Coverage is the gap now: swerb reaches only `gpt-5.6-sol` and `gpt-5.6-luna`, and Artificial Analysis is the one source covering all seven catalog models.
- Ticket 14 **closed out 2026-09-10**: `ADS_COMMIT` now pins `integration/read-only-fixes` @ `1ff8bd6`, which carries both read-only fixes, so grok *and* agy read-only work at runtime and `--write` is no longer a workaround. Upstream PRs #119 and #120 stay independent; retire the integration branch and repoint `ADS_REPO` at `amElnagdy` when they land. Two follow-ups recorded in the ticket: agy's own docs still describe plan mode, and `claude-delegate`/`commandcode-delegate` still push `--permission-mode plan` untested. Note `ads.sh install` detaches the shared clone at `$ADS_COMMIT` and will move the tree under a working agent.
- **Decided 2026-09-10:** `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`. Orin ruled the subscription costs and vendor notes non-sensitive, so no split to the forge and no constraint on what the ticket-15 pre-screen may write. Do not re-raise it.
- Waiting on Orin: drop `export DELEGATE_BALANCE=1` from `~/.zshrc.local` (spec §9.7); set `meter_weight` and `trust` on `astra-high@codex` in `~/.config/delegate/lanes.json` — the `price` is now sourced as `10 / 1 / 12.5 / 50` from OpenAI's pricing page and just needs pasting, but the other two are judgement no benchmark can make; decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line as ticket 09 asks, which would drop the `why-claude` and "result is a claim" rules.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
