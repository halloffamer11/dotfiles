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

**Branch `bench-aa-effort-slugs` is unmerged**, 21 commits ahead of `main` and 2
behind, suite green at 367 assertions across 12 files. It contains
`delegate-lane-catalog`, which is 24 commits behind it; that branch is history now,
not a second thread. Tickets 01-17 are implemented. `main` still has none of it, and
`~/.claude/skills/delegate` symlinks to the **main** checkout — so the installed
skill has no `discover.py` and no pre-screen, and the four `/delegate-*` wrappers
cannot be exercised until this merges. Merging conflicts on this file only.

**Open, in priority order:**

1. **The tier screen's own design.** Attribution is fixed (ticket 17), so the
   screen is honest, but two things about it are Orin's to settle: what `[x]`/`[ ]`
   means beside an on/off column, and whether a lane already taken at a higher tier
   greys out; and, downstream of both, which columns win the width at 80, where the
   fit still drops the score columns before `model` and `lane`. TUI work goes to a
   Claude Opus agent under `/frontend-design:frontend-design`.
2. **Add the 14 missing codex lanes** — sol x5, terra x5, luna x4. Only astra has a
   full effort sweep in the catalog, so no other model can be compared across
   efforts. Safe now that a figure reaches one lane only.
3. **Ticket 14** — two real gaps: a cancelled-at-the-gate run returns `partial`
   rather than `blocked` naming the gate, and the cancelled-tool-call regression
   test through `map_result` does not exist. The agy box is satisfied by the ADS pin.
4. **Chunk dispatch does not fit one agy window.** `effort.py` splits a large packet
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
- Reconcile the live catalog with the stowed one, now that the stowed file is the
  authority (see Settled). The live `~/.config/delegate/lanes.json` is a regular
  file, not a stow symlink, and still differs: `sol-high@codex` tier 3 against the
  stowed tier 4, and no `published_as: ["Fable 5.1"]` on the fable lane. Replacing
  it is a mutating command in Orin's own home, so it is his to run.
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

Coverage is uneven and the three sources are not interchangeable: swerb reaches only
`gpt-5.6-sol` and `gpt-5.6-luna` but publishes slugs; Artificial Analysis and
Terminal-Bench are wider but publish display names (ticket 16). Cost is per-task on
swerb and on Artificial Analysis, but Terminal-Bench's `display_cost` is a whole-run
figure. Even the two per-task numbers measure different task sets, so never compare
costs across sources. The AA key is at `~/.config/delegate/aa-key`, mode 600, outside
the repo and in `.gitignore` — never stow it; this repo is public.

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
- `stow/delegate/.config/delegate/lanes.json` is the authoritative catalog; the live
  `~/.config/delegate/lanes.json` follows it, never the other way (Orin,
  2026-09-10).
- `ultra` lanes are generated disabled: no source scores them, and automatic task
  delegation contradicts the worker preamble (ticket 15).

Preserve unrelated working-tree changes. Validate the smallest affected surface
before committing.
