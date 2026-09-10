# Dotfiles

Machine configuration and agent tooling managed as one Git repository.

## Start here

- Read `Makefile` before changing installation or stow behavior.
- Read `references/CLAUDE.md` for repository-wide operating context.
- Each active skill under `agents/skills/` owns its detailed context.

## Active work

The delegate redesign is the only live thread. Spec
`docs/superpowers/specs/2026-09-08-delegate-redesign.md`; tickets in
`.scratch/delegate-redesign/issues/`, each carrying its own decisions and a
"Landed" note; skill context `agents/skills/delegate/CLAUDE.md`.

**Branch `delegate-lane-catalog` is unmerged**, 13 commits ahead of `main` and 2
behind, suite green at 334 assertions. Tickets 01-16 are implemented. `main` still
has none of it, and `~/.claude/skills/delegate` symlinks to the **main** checkout —
so the installed skill has no `discover.py` and no pre-screen, and the four
`/delegate-*` wrappers cannot be exercised until this merges. Merging conflicts on
this file only.

**Open, in priority order:**

1. **Ticket 14** — two real gaps: a cancelled-at-the-gate run returns `partial`
   rather than `blocked` naming the gate, and the cancelled-tool-call regression
   test through `map_result` does not exist. The agy box is satisfied by the ADS pin.
2. **Chunk dispatch does not fit one agy window.** `effort.py` splits a large packet
   correctly, but dispatches the chunks in sequence: both live Artificial Analysis
   runs on 2026-09-10 failed at chunk 6 of 7 when the agy **5-hour** meter hit 0%
   (the weekly had just refilled to 95% — the 5h window is the binding constraint,
   not the weekly). Options and measurements are in ticket 15's last section: run the
   chunks concurrently, spread them across lanes, or both. Raising the budget is not
   a fix.

**Waiting on Orin** (nothing else blocks on these):

- Run the wizard once to close tickets 06, 07, 07b and 15's last box:
  `python3 <this worktree>/agents/skills/delegate/scripts/setup.py --effort-rows <effort.py check accepted.json>`
- Type each of the four `/delegate-*` wrappers once with a plain-language
  constraint (ticket 11) — needs the merge first.
- Two one-liners in his own files, outside this repo (ticket 09):
  `~/.claude/hooks/delegate-gate.py` names `{SKILL_DIR}/delegate.py`, which moved to
  `scripts/delegate.py`, so the hook advises every session to run a path that does
  not exist; and `export DELEGATE_BALANCE=1` is still line 1 of `~/.zshrc.local`.
- Decide which catalog is authoritative: `stow/delegate/.config/delegate/lanes.json`
  says `sol-high@codex` is tier 4, the live `~/.config/delegate/lanes.json` says
  tier 3. The live file is a regular file, not a stow symlink, so neither drives the
  other.
- Decide whether the `~/.claude/CLAUDE.md` Delegation section collapses to one line
  as ticket 09 asks, which would drop the `why-claude` and "a result is a claim"
  rules.
- Walk the eight spec §9 acceptance items and sign each off. §9.2 is signed; §9.6 is
  down to the hook above; §9.7 is the `.zshrc.local` line.

## Benchmark data

`agents/skills/delegate/scripts/effort.py` is a `pack`/`extract`/`check` pipeline;
`check` is the trust boundary and rejects any number not on the page. Approved
sources and their cautions: `agents/skills/delegate/assets/sources.json`; the
provenance research behind that choice:
`.scratch/delegate-redesign/research/2026-09-09-effort-data-sources.md`. Accepted
rows and their packets are kept as evidence in `.scratch/delegate-redesign/_data/`.

Coverage is uneven and the two sources are not interchangeable: swerb reaches only
`gpt-5.6-sol` and `gpt-5.6-luna` but publishes slugs; Artificial Analysis and
Terminal-Bench are wider but publish display names (ticket 16) and their `cost_usd`
is a whole-run figure, not swerb's per-task one, so never compare costs across
sources. The AA key is at `~/.config/delegate/aa-key`, mode 600, outside the repo and
in `.gitignore` — never stow it; this repo is public.

`flash-high@agy` has no rows in any approved source, so its tier is a judgement from
its `basis` note rather than from numbers. The AA figures for `gpt-5.6-sol`,
`gpt-5.6-terra` and `grok-4.6` were measured at low/medium/medium against lanes that
run high; the report prints that caveat per model.

## Settled, do not re-raise

- `lanes.json` and `routing.json` both ship in this public repo via `stow/delegate/`.
  Orin ruled the subscription costs and vendor notes non-sensitive, so no split to a
  forge and no constraint on what the pre-screen may write (2026-09-10).
- `trust` is gone from the design entirely. Ranking sorts
  `(tier asc, pace desc, lane name asc)`; the name term is an arbitrary deterministic
  tie-break, so a steal only ever crosses tiers (tickets 01 and 02).
- `ultra` lanes are generated disabled: no source scores them, and automatic task
  delegation contradicts the worker preamble (ticket 15).

Preserve unrelated working-tree changes. Validate the smallest affected surface
before committing.
