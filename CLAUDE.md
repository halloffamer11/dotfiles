# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

- Delegate redesign **merged** 2026-09-09; `delegate-rebuild` is deleted, tag `delegate-v1-last` holds the removed old path. Tickets 01-10 landed; **11, 12, 13, 15 are open** in `.scratch/delegate-redesign/issues/`. Spec `docs/superpowers/specs/2026-09-08-delegate-redesign.md` (amended 2026-09-10). Skill context: `agents/skills/delegate/CLAUDE.md`.
- `effort-data-tooling` **merged** 2026-09-10: `scripts/effort.py`, a `pack`/`extract`/`check` pipeline for per-effort score-and-cost, proven end to end. Approved sources and their cautions: `agents/skills/delegate/assets/sources.json`; provenance research: `.scratch/delegate-redesign/research/2026-09-09-effort-data-sources.md`.
- `trust` **removed and merged** 2026-09-10 (q1a): gone from schema, ranking, wizard, TUI, catalogs, tests and spec. Ranking sorts `(tier asc, pace desc, lane name asc)`; the name term is an arbitrary deterministic tie-break, and a steal now only ever crosses tiers. Tier is the sole human-set ranking input. Decisions and consequences: issues `01-…` and `02-…`.
- Ticket 14 **closed** 2026-09-10: `ADS_COMMIT` pins `integration/read-only-fixes` @ `1ff8bd6`, so grok *and* agy read-only work and `--write` is no longer a workaround. Retire that branch and repoint `ADS_REPO` at `amElnagdy` when PRs #119 and #120 land. Two follow-ups in the ticket. Note `ads.sh install` detaches the shared clone and will move the tree under a working agent.

## Next: the wizard Orin actually asked for

Build in this order — 15 is blocked by both. Each goes out through the delegate skill.

1. **13 — `scripts/discover.py`**: unbuilt and unblocked. Lists every model each harness offers with its lane or `none`, and names lanes whose model has retired.
2. **12 — orientation, legends, side-by-side data**: start screen, tier definition, tier-to-lanes map, margin/gate legend **on the confirm screen too**, and a local HTML page of the gathered benchmark data read beside the tier screens (read-only; decisions stay in the TUI).
3. **15 — per-effort lanes, `enabled`, and the pre-screen**: ~30 lanes from the efforts each harness reports; the pre-screen narrows them by proposing `enabled` from `effort.py` output and sets the starting mark state, never writing the catalog itself.

The side-by-side view and the pre-screen were agreed in earlier sessions and never written down, which is why the 2026-09-10 wizard run came up short. They are now defined in issues `12-…` and `15-…`. Do not rely on chat memory for either.

## Benchmark evidence for the tier pass

- AA key at `~/.config/delegate/aa-key`, mode 600, outside the repo and gitignored. **Never stow it — this repo is public.**
- Epoch reaches six of seven lanes, AA reaches six of seven, but not the same six. `flash-high@agy` (`gemini-3.8-flash-high`) has **no rows in either source**, so its tier is a judgement from its `basis` ledger note. It is currently the live `impl` pick on pace alone.
- AA scores for `gpt-5.6-sol`, `gpt-5.6-terra` and `grok-4.6` were measured at low/medium/medium against lanes that run high; the report prints that caveat per model. Read them as a floor.
- The "AA covers all seven models" claim applies to AA's `/models/releases/` pages that `effort.py` scrapes, not the free API `bench.py` uses.

## Settled — do not re-raise

- `lanes.json` and `routing.json` ship in this public repo via `stow/delegate/`. Orin ruled the subscription costs and vendor notes non-sensitive, so no split to the forge and no constraint on what the ticket-15 pre-screen may write.

## Waiting on Orin

- Drop `export DELEGATE_BALANCE=1` from `~/.zshrc.local` (spec §9.7).
- Set `meter_weight` on `astra-high@codex`; `price` is sourced as `10 / 1 / 12.5 / 50` and just needs pasting.
- Decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line as ticket 09 asks, which would drop the `why-claude` and "result is a claim" rules.

Preserve unrelated working-tree changes. Validate the smallest affected surface before committing.
